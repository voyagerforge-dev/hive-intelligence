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
from hivegen.corpus import require_dir
from hivegen.llm import BifrostChat, extract_json
from hivegen.profile import load_profile, missing_profile_error


def docs_dir() -> pathlib.Path:
    """Where the atomic documents are. Configured, never derived, and resolved here rather
    than at import so importing this module has no side effect.

    This used to fall back to `Path(__file__).parents[3] / "atomic"`, which after the
    2026-08-11 split is the engine repository. Globbing a directory that is not there
    yields nothing and raises nothing, so the pass reported zero documents re-topiced
    and exited 0.
    """
    return require_dir(get_settings().atomic_dir, setting="ATOMIC_DIR",
                       what="the atomic documents to re-topic")


def corpus_vocabulary():
    """The documents, then the corpus profile that describes them. In that order.

    The order is the point. `load_profile` looks for corpus-profile.yaml beside ATOMIC_DIR,
    so resolving the profile first turns a dead or unset ATOMIC_DIR into "no corpus profile
    found" and sends the operator after CORPUS_PROFILE, which is not the setting that is
    wrong. `hivegen.run.main` is ordered the same way for the same reason.

    Resolved here rather than at import, and from the validated settings rather than from
    `os.environ`. Settings are `.env`-backed and pydantic-settings never writes back to the
    environment, so ATOMIC_DIR and CORPUS_PROFILE set in `.env` - which is what this
    package's own `.env.example` tells an operator to do - are both invisible to a bare
    `load_profile()`. The profile then reads as missing and the refusal names remedies
    ("Set CORPUS_PROFILE, or put corpus-profile.yaml beside ATOMIC_DIR") the operator has
    already followed. Worse than the message: an ignored CORPUS_PROFILE lets a different
    corpus-profile.yaml in the working directory win silently, and the pass then classifies
    against the wrong vocabulary with no error at all.

    A missing profile is deliberately not an error in `load_profile`; it becomes one here,
    where something asks for a vocabulary nothing defines. Without it the bucket is "" and
    the topics are {}, so every document carrying a topic is skipped, anything without one
    classifies to UNCLASSIFIED and is never applied, and the pass prints
    "total: 0  applied: True" and exits 0 - indistinguishable from a corpus with nothing
    left to re-topic.
    """
    docs = docs_dir()
    s = get_settings()
    profile = load_profile(explicit=s.corpus_profile or None, atomic_dir=str(docs))
    missing = [key for key, value in (("retopic_bucket", profile.retopic_bucket),
                                      ("guide_topics", profile.guide_topics)) if not value]
    if not missing:
        return docs, profile
    if profile.path is None:
        raise SystemExit(missing_profile_error("guide topics", "the re-topic pass"))
    raise SystemExit(
        f"{profile.path} defines no {' and no '.join(missing)}, so there is nothing to "
        "re-topic. retopic_bucket names the catch-all topic to re-classify and "
        "guide_topics the controlled topics to classify into; both describe one corpus's "
        "vocabulary. Without them every document is skipped and the pass reports zero "
        "changed, which reads exactly like a corpus with nothing left to do.")

def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return m.group(1) if m else None

def get_field(fm, key):
    m = re.search(rf"^{key}:\s*\"?([^\"\n]+)\"?\s*$", fm, re.MULTILINE)
    return m.group(1).strip() if m else ""

def basename(stem, prefixes=()):
    # Long shared filename prefixes carry no signal and crowd the model's view of the
    # title. The prefix itself is corpus naming, so it comes from the profile.
    s = stem
    for prefix in prefixes:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return re.sub(r"^20\d\d-", "", s)

def newest_docs(docs=None, profile=None):
    """One path per guide base-name: the one with the highest version year."""
    if docs is None or profile is None:
        docs, profile = corpus_vocabulary()
    best = {}
    for p in sorted(docs.glob("*.md")):
        fm = frontmatter(p.read_text())
        if not fm or get_field(fm, "topic") != profile.retopic_bucket:
            continue
        ver = get_field(fm, "version") or "0"
        base = basename(p.stem, profile.filename_prefixes)
        if base not in best or ver > best[base][0]:
            best[base] = (ver, p)
    return [v[1] for v in best.values()]

_SYSTEM = (
    "You classify a guide or reference document into exactly ONE topic from the list. "
    "Base it on the document's SUBJECT, not incidental mentions. Reply ONLY {\"topic\": \"<exact topic string>\"}."
)

def classify(text, llm, topics):
    opts = "\n".join(f"- {k}: {v}" for k, v in topics.items())
    title = ""
    fm = frontmatter(text)
    if fm:
        title = get_field(fm, "title")
    body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
    prompt = f"TOPICS:\n{opts}\n\nTITLE: {title}\nDOCUMENT:\n{body[:1200]}"
    data = extract_json(llm.complete(_SYSTEM, prompt) or "")
    t = (data or {}).get("topic", "")
    return t if t in topics else "UNCLASSIFIED"

def set_topic(text, topic):
    return re.sub(r'^(topic:\s*).*$', f'topic: "{topic}"', text, count=1, flags=re.MULTILINE)

def main():
    apply = "--apply" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    s = get_settings()
    docs_root, profile = corpus_vocabulary()
    llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.assign_model, timeout_s=s.bifrost_timeout_s)
    docs = newest_docs(docs_root, profile)
    if limit:
        docs = docs[:limit]
    from collections import Counter
    dist = Counter()
    print(f"{'topic':32} {'guide'}")
    for p in docs:
        text = p.read_text()
        topic = classify(text, llm, profile.guide_topics)
        dist[topic] += 1
        print(f"{topic:32} {basename(p.stem, profile.filename_prefixes)}")
        if apply and topic != "UNCLASSIFIED":
            p.write_text(set_topic(text, topic))
    print("\n=== distribution ===")
    for t, n in dist.most_common():
        print(f"{n:4}  {t}")
    print(f"total: {sum(dist.values())}  applied: {apply}")

if __name__ == "__main__":
    main()
