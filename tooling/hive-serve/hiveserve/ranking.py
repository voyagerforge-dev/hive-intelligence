"""Shared keyword ranking for the two LLM-free search doors.

Both `find_concepts` (concept cards) and `find_db_objects` (database-object manifests)
used to score a row by counting how many raw whitespace-split query tokens appeared as
*substrings* of its joined text. Measured over a real ~990-card corpus with 70 labelled
questions, that scorer put the right card in the top 20 only 77.1% of the time although it
matched it 98.6% of the time, and it got worse as the corpus grew (88.6% at 100 cards).
Four things caused that, and this module fixes all four:

* **Punctuation stuck to query tokens.** `"...in release 12?"` split on whitespace yields
  `12?`, which matches nothing - and the discarded token is usually the most specific word
  in the question. Tokenising on `[a-z0-9]+` after lowercasing keeps it.
* **No stopword removal.** `in`, `and`, `a` scored exactly as much as the topic word, so
  the median question "matched" 98% of the corpus.
* **Substring containment.** `t in hay` let `at` match inside `catalogue` and `it` match
  inside `activity`; whole-token matching is what a reader means by a word appearing.
* **Undifferentiated integer scores.** Hundreds of rows tied, so the alphabetical
  tie-break on id did most of the ordering. Inverse document frequency makes a rare word
  worth more than a ubiquitous one, and sublinear term frequency rewards a row that says
  the word repeatedly without letting repetition run away.

Still deliberately absent: embeddings, a network call, any runtime dependency beyond the
standard library, and any persistent state. Document frequencies are computed per call
from the candidate rows the caller passes in, which is the collection actually being
ranked - so a product- or module-filtered search weights terms against that subset.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any

_WORD = re.compile(r"[a-z0-9]+")

# A small fixed English function-word list. Deliberately not a linguistic stopword corpus:
# these are the words that carried most of the old scorer's mass across the 70 measured
# questions ('in' appeared in 22 of them and matched 98% of the corpus), and nothing longer
# is needed. Domain vocabulary is never listed here - discrimination between domain words
# is idf's job, not this list's.
STOPWORDS = frozenset([
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does", "for",
    "from", "how", "i", "if", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "to", "was", "what",
    "when", "where", "which", "who", "why", "will", "with",
])


def tokenize(text: str | None) -> list[str]:
    """Lowercase, split on runs of letters/digits, drop stopwords.

    Splitting on `[a-z0-9]+` is what strips punctuation, and it is also what gives a card
    id its words: `widget/calibration-priority-rules` becomes the same four tokens a title
    would, which is why an id that restates the query ranks the card first.
    """
    return [t for t in _WORD.findall((text or "").lower()) if t not in STOPWORDS]


def rank(query: str,
         documents: Iterable[tuple[Any, str]],
         limit: int,
         tiebreak: Callable[[Any], str]) -> list[Any]:
    """Rank `documents` against `query`, best first, and return at most `limit` payloads.

    `documents` yields `(payload, text)`; `text` is the row's searchable fields already
    joined by the caller. `tiebreak` is the last sort key, so equal scores stay in a
    stable, caller-defined order rather than an arbitrary one.

    A query of only stopwords (or only punctuation) has no terms and matches nothing, so
    the result is empty rather than the whole collection.
    """
    terms = set(tokenize(query))
    if not terms:
        return []

    counted = [(payload, Counter(tokenize(text))) for payload, text in documents]
    total = len(counted)
    if not total:
        return []

    doc_freq: Counter[str] = Counter()
    for _, tf in counted:
        doc_freq.update(t for t in terms if t in tf)

    # Smoothed idf, always positive: a term in every row still counts for something, a term
    # in one row counts for much more. Sublinear tf keeps a row that repeats a word ahead of
    # one that mentions it once without letting a long description win on repetition alone.
    idf = {t: math.log((1 + total) / (1 + doc_freq[t])) + 1.0 for t in terms}

    hits = []
    for payload, tf in counted:
        score = sum(idf[t] * (1.0 + math.log(tf[t])) for t in terms if t in tf)
        if score > 0:
            hits.append((score, payload))

    hits.sort(key=lambda sp: (-sp[0], tiebreak(sp[1])))
    return [payload for _, payload in hits[:limit]]
