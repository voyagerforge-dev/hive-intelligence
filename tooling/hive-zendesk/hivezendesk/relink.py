"""Derive concept-card links for journal entries, offline.

The first run wrote 96% of entries with `related: []`. The cause was not model quality:
the distiller was asked for "short topic slugs" and invented plausible ones
(`cluster-pick`, `manual-wave`), while the corpus ids are `allocation-process`,
`asn-pre-receipt-allocation-completion`. Exact matching coincided ~4% of the time, and
`resolve_related` dropped the rest - so the original guesses are not recoverable.

So this matches on the entry's own text instead, which is both cheaper (no model) and
better grounded (real words from the ticket rather than an invented slug).

Two deliberate choices:

- **Only `type: concept` targets.** The corpus is 88% `dbobject` cards. Pointing a
  consultant at `ALLOC_PARM` does not explain behaviour; `allocation-process` does.
- **Precision over recall.** The skills instruct readers to follow `related` to learn how
  the product behaves, so a wrong link actively misleads. Entries that cannot be matched
  confidently keep `related: []`, which is honest.
"""
from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .fm import parse_frontmatter
from .profile import load_linking_profile

SKIP_NAMES = {"index.md", "log.md"}

# Words that carry no discriminating signal: English function words plus generic support
# vocabulary. Corpus-specific dead words (a vendor name that appears on every card, say)
# belong in the corpus profile's linking.extra_stopwords, not here.
STOP = {
    "the", "and", "for", "with", "was", "were", "are", "not", "this", "that", "from",
    "has", "have", "had", "but", "all", "any", "can", "could", "would", "should", "did",
    "does", "when", "which", "into", "onto", "out", "its", "their", "there", "then",
    "than", "them", "they", "been", "being", "you", "your", "our", "his", "her",
    "card", "issue", "ticket", "error", "please", "request",
    "problem", "user", "system", "data", "one", "two", "new", "old", "via", "per",
}

# Corpus-specific dead words come from the profile and are folded in at tokenise time.
STOP |= {w for w in load_linking_profile().extra_stopwords}

MIN_SHARED = 2      # one shared word is a coincidence, not a link
MIN_SCORE = 0.30    # share of the target's distinctive mass that must be covered
TOP_N = 3


def _fold(t: str) -> str:
    """Crude plural fold. Without it `doors` never matches `dock-door-management` and
    `waves` never matches `run-wave-execution` - measured to cost 41% of the entries
    that reached the shortlist stage with no candidates at all."""
    return t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric words, minus stopwords and noise-length tokens."""
    return [_fold(t) for t in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(t) > 2 and t not in STOP]


def load_card_ids(concepts_dir: str | Path) -> set[str]:
    """Every card id in the corpus, any type. Used to validate emitted `related` ids."""
    base = Path(concepts_dir)
    return {p.relative_to(base).with_suffix("").as_posix()
            for p in base.rglob("*.md") if p.name not in SKIP_NAMES}


def load_targets(concepts_dir: str | Path) -> dict[str, set[str]]:
    """card_id -> its distinctive tokens, for concept cards only."""
    base = Path(concepts_dir)
    out: dict[str, set[str]] = {}
    for p in base.rglob("*.md"):
        if p.name in SKIP_NAMES:
            continue
        fm = parse_frontmatter(p.read_text())
        if fm.get("type") != "concept":
            continue
        cid = p.relative_to(base).with_suffix("").as_posix()
        # The id itself carries signal ("wave-allocation-process"), as does the title.
        toks = set(tokenize(str(fm.get("title", "")))) | set(tokenize(cid.replace("/", " ")))
        if toks:
            out[cid] = toks
    return out


def build_idf(targets: dict[str, set[str]]) -> dict[str, float]:
    """Smoothed IDF, so a single-target corpus (as in tests) still yields useful weights."""
    n = len(targets)
    df: dict[str, int] = {}
    for toks in targets.values():
        for t in toks:
            df[t] = df.get(t, 0) + 1
    return {t: math.log((n + 1) / (d + 1)) + 1.0 for t, d in df.items()}


def suggest(query: str, targets: dict[str, set[str]], idf: dict[str, float],
            top_n: int = TOP_N, min_score: float = MIN_SCORE,
            min_shared: int = MIN_SHARED) -> list[str]:
    """Best concept-card ids for an entry, or [] when nothing clears the bar.

    Score is the fraction of a target's own IDF mass that the query covers. That ratio is
    scale-free, so the threshold means the same thing on a 1-card test corpus and on the
    real 990-card one - unlike a raw score, which would drift with corpus size.
    """
    q = set(tokenize(query))
    if not q:
        return []
    scored: list[tuple[float, str]] = []
    for cid, toks in targets.items():
        shared = q & toks
        if len(shared) < min_shared:
            continue
        total = sum(idf.get(t, 1.0) for t in toks)
        if total <= 0:
            continue
        score = sum(idf.get(t, 1.0) for t in shared) / total
        if score >= min_score:
            scored.append((score, cid))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [cid for _, cid in scored[:top_n]]


# --- rewriting existing cards -------------------------------------------------------
# Surgical rather than re-rendering: re-rendering would need the card parsed back into an
# IssueCard and would restamp fields such as `timestamp`, quietly rewriting provenance on
# 2,292 cards to fix a link. Only the two places a link appears are touched.

_REL_RE = re.compile(r"^related:(?: \[\]\n|\n(?:- [^\n]*\n)*)", re.MULTILINE)
_SEE_RE = re.compile(r"## See also\n\n(?:- `[^`]*`\n)+")


def apply_links(text: str, links: list[str]) -> str:
    """Set `related:` and the `## See also` block. No links means no change."""
    if not links:
        return text
    block = "related:\n" + "".join(f"- {link}\n" for link in links)
    out = _REL_RE.sub(lambda _: block, text, count=1)
    see = "## See also\n\n" + "".join(f"- `{link}`\n" for link in links)
    if _SEE_RE.search(out):
        out = _SEE_RE.sub(lambda _: see, out, count=1)
    else:
        out = out.rstrip("\n") + "\n\n" + see
    return out


_PROD_RE = re.compile(r"^product: .*$", re.MULTILINE)


def product_of(card_id: str) -> str:
    """The owning product of a concept id - concept ids are `<product>/<slug>`."""
    return card_id.split("/", 1)[0]


# Leaving the default product requires positive evidence in the entry's own words.
#
# Inferring the product from whichever card the model happened to pick misfiled entries
# badly: an application-down ticket was refiled under an unrelated product because one of
# highest. That is worse than a bad link. Retrieval selects on `product`, so an entry
# stamped with the wrong one is invisible to anyone scoped to the right one.
#
# The vocabulary is corpus-specific and comes from the profile. Markers are folded because
# tokenize() folds plurals.
def product_vocabulary(linking=None) -> tuple[str, dict[str, set[str]]]:
    """The default product and its marker vocabulary, folded to match tokenize()."""
    linking = linking if linking is not None else load_linking_profile()
    markers = {prod: {_fold(m) for m in ms} for prod, ms in linking.product_markers.items()}
    return linking.default_product, markers


def allowed_products(text: str, linking=None) -> set[str] | None:
    """Which products this entry may be filed under, or None for "do not confine".

    The default product is always permitted; any other needs a marker word present in the
    entry's own text.

    Returns **None** when the corpus profile defines no product vocabulary at all. That is
    "confinement is not configured", which is different from "no product is permitted".
    Returning an empty set here would reject every candidate and silently link nothing,
    which looks identical to a corpus with no matching cards.
    """
    default, markers = product_vocabulary(linking)
    if not default and not markers:
        return None
    toks = set(tokenize(text))
    base = {default} if default else set()
    return base | {p for p, ms in markers.items() if toks & ms}


def confine_to_one_product(links: list[str]) -> list[str]:
    """Keep only the links belonging to the first pick's product.

    OKF requires 0 cross-product bleed (docs/architecture/pipeline.md). An entry linking to both
    cards from two different products would be exactly that, so the first pick wins the product
    and any pick from another product is dropped.
    """
    if not links:
        return []
    keep = product_of(links[0])
    return [link for link in links if product_of(link) == keep]


def set_product(text: str, product: str) -> str:
    """Stamp the entry's product facet, from the entry's own evidence.

    This is where the facet is decided. `emit.py` deliberately omits `product` when it is
    undecided rather than writing a default, because a card stamped with the wrong product is
    restricted to that product's link targets and can never reach the card that actually
    explains it - which is worse than a card claiming nothing.
    """
    if _PROD_RE.search(text):
        return _PROD_RE.sub(lambda _: f"product: {product}", text, count=1)
    # A card written without the facet still needs one, or it cannot be selected on.
    return re.sub(r"^(client: .*\n)", rf"\1product: {product}\n", text, count=1, flags=re.MULTILINE)


_LINKED_BY_RE = re.compile(r"^linked_by: .*\n", re.MULTILINE)


def set_linked_by(text: str, model: str) -> str:
    """Record which model chose the links.

    `model:` names the distiller, which is not necessarily what did the linking - the
    corpus was distilled by the on-prem Qwen and later re-linked by a stronger model.
    Without this the two are indistinguishable after the fact.
    """
    line = f"linked_by: {model}\n"
    if _LINKED_BY_RE.search(text):
        return _LINKED_BY_RE.sub(lambda _: line, text, count=1)
    for anchor in (r"^(distilled_by: .*\n)", r"^(status: .*\n)"):
        out, n = re.subn(anchor, rf"\1{line}", text, count=1, flags=re.MULTILINE)
        if n:
            return out
    return text


def clear_links(text: str) -> str:
    """Retract links: empty `related:` and drop the `## See also` block."""
    if _SEE_RE.search(text):
        text = _SEE_RE.sub("", text).rstrip("\n") + "\n"
    return _REL_RE.sub(lambda _: "related: []\n", text, count=1)


def entry_query(text: str) -> str:
    """The searchable text of a journal entry: title, summary, module and tags."""
    fm = parse_frontmatter(text)
    parts = [str(fm.get("title", "")), str(fm.get("description", "")),
             str(fm.get("module", "")), " ".join(fm.get("tags") or [])]
    return " ".join(parts)


# --- rerank ---------------------------------------------------------------------------
# Lexical scoring alone reached only ~60% precision on a hand-checked sample: it cannot
# tell that a license-key migration has nothing to do with `serial-number-inquiry`, and
# raising the threshold dropped good links before it dropped bad ones. So the lexical
# pass is demoted to a recall device - it produces a shortlist - and the model decides.
# On the same sample that scored 5 correct out of 5 picks, declining everything else.

SHORTLIST_N = 10
SHORTLIST_MIN_SCORE = 0.18   # deliberately loose: recall here, precision at the rerank
MAX_LINKS = 2

RERANK_SYSTEM = (
    "You link a support incident to reference cards that explain the product behaviour "
    'involved. Reply with ONE JSON object: {"picks":[ids]}.\n'
    "Pick 0-2 ids from the CANDIDATES that a consultant would read to understand this "
    "incident's subject matter. An empty list is the CORRECT answer when none genuinely "
    "match - most candidates are near-misses that share a word but not a topic. "
    "Never pick an id that is not in the list."
)


def load_titles(concepts_dir: str | Path) -> dict[str, str]:
    """card_id -> title, for concept cards. The rerank judges on titles, not ids."""
    base = Path(concepts_dir)
    out: dict[str, str] = {}
    for p in base.rglob("*.md"):
        if p.name in SKIP_NAMES:
            continue
        fm = parse_frontmatter(p.read_text())
        if fm.get("type") == "concept":
            out[p.relative_to(base).with_suffix("").as_posix()] = str(fm.get("title", ""))
    return out


def rerank(title: str, description: str, candidates: list[str], titles: dict[str, str],
           llm) -> list[str]:
    """Ask the model which candidates genuinely explain this incident. Fails closed."""
    if not candidates:
        return []
    from .llm import extract_json
    lines = "\n".join(f"- {cid} :: {titles.get(cid, '')}" for cid in candidates)
    prompt = f"INCIDENT: {title}\nDETAIL: {description}\n\nCANDIDATES:\n{lines}"
    data = extract_json(llm.complete(RERANK_SYSTEM, prompt) or "") or {}
    picks = data.get("picks") or []
    if not isinstance(picks, list):
        return []
    # An id the model invented would point at a card that does not exist.
    seen: list[str] = []
    for p in picks:
        if isinstance(p, str) and p in candidates and p not in seen:
            seen.append(p)
    return seen[:MAX_LINKS]


@dataclass
class RelinkReport:
    scanned: int = 0
    no_shortlist: int = 0
    declined: int = 0
    linked: int = 0
    cleared: int = 0     # stale links retracted because this run found nothing better


def relink_cards(clients: list[str], clients_dir: str | Path, concepts_dir: str | Path,
                 llm, workers: int = 8, dry_run: bool = False,
                 products: tuple[str, ...] | None = None,
                 skip_linked: bool = False, linking=None) -> RelinkReport:
    """Derive and write `related:` links for every issue card of these clients.

    Candidates are drawn from ALL products; the model's choice then determines the
    entry's own product facet, and `confine_to_one_product` keeps the resulting edges
    inside it. That is what lets an entry about a secondary product reach that product's cards
    without ever creating the cross-product edge OKF forbids.
    """
    targets = load_targets(concepts_dir)
    if products:
        targets = {k: v for k, v in targets.items() if product_of(k) in products}
    titles = load_titles(concepts_dir)
    idf = build_idf(targets)
    report = RelinkReport()

    for client in clients:
        d = Path(clients_dir) / client / "issues"
        if not d.exists():
            continue
        paths = sorted(d.glob("*.md"))
        if skip_linked:
            paths = [q for q in paths if "\nrelated: []\n" in q.read_text()]
        report.scanned += len(paths)

        def work(p: Path) -> tuple[Path, list[str], bool]:
            """(path, chosen links, whether the lexical pass offered anything)."""
            text = p.read_text()
            fm = parse_frontmatter(text)
            if not fm:
                return p, [], False
            query = entry_query(text)
            cands = suggest(query, targets, idf,
                            top_n=SHORTLIST_N, min_score=SHORTLIST_MIN_SCORE)
            # Never offer a product the entry shows no evidence of belonging to: the model
            # picks from what it is shown, so filtering here is what prevents the facet
            # being decided by a lexical coincidence.
            permitted = allowed_products(query, linking)
            if permitted is not None:
                cands = [c for c in cands if product_of(c) in permitted]
            if not cands:
                return p, [], False
            links = rerank(str(fm.get("title", "")), str(fm.get("description", "")),
                           cands, titles, llm)
            return p, confine_to_one_product(links), True

        # Write as each result lands rather than collecting the client's whole set first:
        # a long run that dies mid-flight should keep the work it has already done.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work, q) for q in paths]
            results = (f.result() for f in as_completed(futures))
            for p, links, had_candidates in results:
                if not links:
                    if had_candidates:
                        report.declined += 1
                    else:
                        report.no_shortlist += 1
                    # This run is authoritative for `related`. Leaving an old link in place
                    # would preserve exactly the slug-era cross-product errors this pass
                    # exists to remove, so a decision of "no link" is written through.
                    text = p.read_text()
                    cleared = clear_links(text)
                    if cleared != text:
                        report.cleared += 1
                        if not dry_run:
                            p.write_text(cleared)
                    continue
                report.linked += 1
                if not dry_run:
                    # Product first: the entry belongs to whatever product explains it,
                    # then the links, then which model chose them.
                    body = set_product(p.read_text(), product_of(links[0]))
                    body = apply_links(body, links)
                    p.write_text(set_linked_by(body, getattr(llm, "model", "")))
    return report
