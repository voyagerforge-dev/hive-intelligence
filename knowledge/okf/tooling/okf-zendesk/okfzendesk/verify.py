"""Hard verification gate. Any failure raises RunError - never a warning."""
from __future__ import annotations

import yaml

from .model import IssueCard, RunError, RunReport
from .scrub import leaks


def _frontmatter_of(text: str) -> dict:
    if not text.startswith("---"):
        raise RunError("card has no frontmatter")
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm) or {}


def verify_card(text: str, card: IssueCard, known: set[str], card_ids: set[str]) -> None:
    fm = _frontmatter_of(text)

    if fm.get("type") != "issue":
        raise RunError(f"ticket {card.ticket_id}: type is not 'issue'")
    if not fm.get("title") or not fm.get("client"):
        raise RunError(f"ticket {card.ticket_id}: missing required frontmatter")

    sources = fm.get("sources") or []
    ref = str(sources[0].get("ref", "")) if sources else ""
    if not ref:
        raise RunError(f"ticket {card.ticket_id}: missing sources.ref")
    if ref != str(card.ticket_id):
        raise RunError(f"ticket {card.ticket_id}: sources.ref {ref!r} does not match")

    found = leaks(text, known)
    if found:
        raise RunError(f"ticket {card.ticket_id}: PII leak in emitted card: {found}")

    for rid in fm.get("related") or []:
        if rid not in card_ids:
            raise RunError(f"ticket {card.ticket_id}: related id {rid!r} resolves to no card")


def verify_run(report: RunReport) -> None:
    if report.at_cap_slices:
        raise RunError(f"fetch hit the connector page cap for: {report.at_cap_slices}")
    accounted = (report.emitted + report.skipped + report.preserved
                 + report.cached + report.pii_held + report.failed)
    if accounted != report.fetched:
        raise RunError(
            f"counts do not reconcile: fetched={report.fetched} != emitted={report.emitted} "
            f"+ skipped={report.skipped} + preserved={report.preserved} "
            f"+ cached={report.cached} + pii_held={report.pii_held} + failed={report.failed}")
