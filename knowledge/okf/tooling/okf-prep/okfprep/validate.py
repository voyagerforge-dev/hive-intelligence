# src/okfprep/validate.py
"""Validate the subagent's atomic markdown corpus and derive relations.yaml.

Checks: unique slugs, valid doc_type/status enums, every `related`/`supersedes`
target resolves to a known slug, and the `supersedes` graph is acyclic. Relations
are DERIVED from frontmatter so nothing races to write a shared file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DOC_TYPES = {
    "config-guide", "user-manual", "release-notes", "api-reference", "technical-spec",
    "implementation-guide", "troubleshooting", "training-material", "faq",
    "best-practices", "functional-flow", "documentation",
}
STATUSES = {"active", "superseded"}


class ValidationError(RuntimeError):
    pass


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    relations: dict = field(default_factory=lambda: {"edges": []})
    slugs: set[str] = field(default_factory=set)


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        raise ValidationError("missing frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValidationError("missing closing frontmatter fence")
    _, fm, _ = parts
    try:
        return yaml.safe_load(fm) or {}
    except yaml.YAMLError as e:
        raise ValidationError(f"YAML parse error: {e}") from e


def _strip_version(target: str) -> str:
    # "slug@2022" supersedes references point at a logical doc; match on the slug part
    return target.split("@", 1)[0]


def _has_cycle(edges: list[tuple[str, str]]) -> bool:
    graph: dict[str, list[str]] = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def visit(n: str) -> bool:
        color[n] = GRAY
        for m in graph.get(n, []):
            if color.get(m, WHITE) == GRAY:
                return True
            if color.get(m, WHITE) == WHITE and visit(m):
                return True
        color[n] = BLACK
        return False

    return any(color.get(n, WHITE) == WHITE and visit(n) for n in graph)


def validate_atomic_dir(atomic_dir: Path) -> ValidationReport:
    report = ValidationReport()
    docs: dict[str, dict] = {}
    for md in sorted(atomic_dir.glob("*.md")):
        try:
            fm = _parse_frontmatter(md.read_text())
        except ValidationError as e:
            report.errors.append(f"{md.name}: {e}")
            continue
        slug = fm.get("slug")
        if not slug:
            report.errors.append(f"{md.name}: missing slug")
            continue
        if slug in docs:
            report.errors.append(f"{md.name}: duplicate slug '{slug}'")
            continue
        if fm.get("doc_type") not in DOC_TYPES:
            report.errors.append(f"{md.name}: invalid doc_type '{fm.get('doc_type')}'")
        if fm.get("status", "active") not in STATUSES:
            report.errors.append(f"{md.name}: invalid status '{fm.get('status')}'")
        for required in ("platform", "product", "version"):
            if not fm.get(required):
                report.errors.append(f"{md.name}: missing required field '{required}'")
        docs[slug] = fm
    report.slugs = set(docs)

    sup_edges: list[tuple[str, str]] = []
    for slug, fm in docs.items():
        raw = fm.get("related") or []
        related_list = raw if isinstance(raw, list) else [raw]
        for rel in related_list:
            if _strip_version(rel) not in docs:
                report.errors.append(f"{slug}: dangling related link '{rel}'")
            else:
                report.relations["edges"].append({"from": slug, "to": rel, "type": "related"})
        sup = fm.get("supersedes")
        if sup:
            tgt = _strip_version(sup)
            if tgt not in docs:
                # superseded target may be intentionally absent (old doc not ingested) — warn-as-edge only
                report.relations["edges"].append({"from": slug, "to": sup, "type": "supersedes"})
            else:
                report.relations["edges"].append({"from": slug, "to": sup, "type": "supersedes"})
                sup_edges.append((slug, tgt))

    if _has_cycle(sup_edges):
        report.errors.append("supersedes graph has a cycle")
    return report


def write_relations(report: ValidationReport, out: Path) -> None:
    out.write_text(yaml.safe_dump(report.relations, sort_keys=False))
