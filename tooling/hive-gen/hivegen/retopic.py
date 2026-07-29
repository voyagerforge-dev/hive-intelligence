"""Re-topic a generic catch-all topic bucket into a controlled guide-topic vocabulary.

Curation often leaves a large "reference doc" style bucket that is too coarse to slice on.
This keeps the newest version of each document (year-collapsed), classifies each by CONTENT
into one controlled guide-topic, and rewrites the `topic:` frontmatter in place. Dry run by
default.

Both the bucket name and the guide-topic vocabulary describe one corpus, so they come from
the corpus profile rather than from this module.

Usage: python retopic.py [--apply] [--limit N]
"""
from __future__ import annotations

import pathlib
import re
import sys

# Make `import hivegen.*` work when run directly (python retopic.py): add the
# hive-gen/ package dir (parent of this hivegen/ dir) to sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from hivegen.config import get_settings
from hivegen.llm import BifrostChat, extract_json
from hivegen.profile import load_profile

_PROFILE = load_profile()

# Where atomic documents live. ATOMIC_DIR is the source of truth; the fallback keeps the
# script runnable from inside a corpus checkout.
DOCS = pathlib.Path(get_settings().atomic_dir or
                    (pathlib.Path(__file__).resolve().parents[3] / "atomic"))

# The catch-all topic this pass re-classifies, and the vocabulary it classifies into. Both
# are corpus vocabulary: see hivegen.profile.
BUCKET = _PROFILE.retopic_bucket
TOPICS: dict[str, str] = dict(_PROFILE.guide_topics)

def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return m.group(1) if m else None

def get_field(fm, key):
    m = re.search(rf"^{key}:\s*\"?([^\"\n]+)\"?\s*$", fm, re.MULTILINE)
    return m.group(1).strip() if m else ""

def basename(stem):
    # Long shared filename prefixes carry no signal and crowd the model's view of the
    # title. The prefix itself is corpus naming, so it comes from the profile.
    s = stem
    for prefix in _PROFILE.filename_prefixes:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return re.sub(r"^20\d\d-", "", s)

def newest_docs():
    """One path per guide base-name: the one with the highest version year."""
    best = {}
    for p in sorted(DOCS.glob("*.md")):
        fm = frontmatter(p.read_text())
        if not fm or get_field(fm, "topic") != BUCKET:
            continue
        ver = get_field(fm, "version") or "0"
        base = basename(p.stem)
        if base not in best or ver > best[base][0]:
            best[base] = (ver, p)
    return [v[1] for v in best.values()]

_SYSTEM = (
    "You classify a guide or reference document into exactly ONE topic from the list. "
    "Base it on the document's SUBJECT, not incidental mentions. Reply ONLY {\"topic\": \"<exact topic string>\"}."
)

def classify(text, llm):
    opts = "\n".join(f"- {k}: {v}" for k, v in TOPICS.items())
    title = ""
    fm = frontmatter(text)
    if fm:
        title = get_field(fm, "title")
    body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
    prompt = f"TOPICS:\n{opts}\n\nTITLE: {title}\nDOCUMENT:\n{body[:1200]}"
    data = extract_json(llm.complete(_SYSTEM, prompt) or "")
    t = (data or {}).get("topic", "")
    return t if t in TOPICS else "UNCLASSIFIED"

def set_topic(text, topic):
    return re.sub(r'^(topic:\s*).*$', f'topic: "{topic}"', text, count=1, flags=re.MULTILINE)

def main():
    apply = "--apply" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    s = get_settings()
    llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.assign_model, timeout_s=s.bifrost_timeout_s)
    docs = newest_docs()
    if limit:
        docs = docs[:limit]
    from collections import Counter
    dist = Counter()
    print(f"{'topic':32} {'guide'}")
    for p in docs:
        text = p.read_text()
        topic = classify(text, llm)
        dist[topic] += 1
        print(f"{topic:32} {basename(p.stem)}")
        if apply and topic != "UNCLASSIFIED":
            p.write_text(set_topic(text, topic))
    print("\n=== distribution ===")
    for t, n in dist.most_common():
        print(f"{n:4}  {t}")
    print(f"total: {sum(dist.values())}  applied: {apply}")

if __name__ == "__main__":
    main()
