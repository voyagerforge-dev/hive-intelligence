"""Pure builders for OKF authoring issues. The issue body emits `### <label>` sections that
match the memory.yml / correction.yml Issue Forms exactly, so the Action parsers round-trip
them. The two build_* functions are hard-separated: memory REQUIRES a client and labels
okf-memory; correction targets a concept id and labels okf-correction."""
from __future__ import annotations


def _section(label: str, value: str) -> str:
    return f"### {label}\n\n{value if value else '_No response_'}\n"


def _prefix(submitted_by: str) -> str:
    return f"_Submitted via hive-author by {submitted_by}._\n\n" if submitted_by else ""


def memory_issue_body(*, client, product, title, lesson, context="", platform="",
                      related=None, citations=None, submitted_by="") -> str:
    return _prefix(submitted_by) + "\n".join([
        _section("Product", product),
        _section("Client", client),
        _section("Title", title),
        _section("The lesson (de-personalised)", lesson),
        _section("When it applies", context),
        _section("Platform (optional)", platform),
        _section("Related concept ids (optional)", "\n".join(related or [])),
        _section("Citation source files (optional)", "\n".join(citations or [])),
    ])


def correction_issue_body(*, target_concept_id, corrected_fact, rationale,
                          citations=None, supersedes=None, submitted_by="") -> str:
    return _prefix(submitted_by) + "\n".join([
        _section("Target concept id", target_concept_id),
        _section("Corrected fact", corrected_fact),
        _section("Rationale", rationale),
        _section("Citation source files", "\n".join(citations or [])),
        _section("Supersedes (optional)", "\n".join(supersedes or [])),
    ])


def build_memory_submission(*, owner, client, product, title, lesson, context="",
                            platform="", related=None, citations=None) -> dict:
    if not client or not str(client).strip():
        raise ValueError("client_required")
    body = memory_issue_body(client=str(client).strip().lower(), product=product, title=title,
                             lesson=lesson, context=context, platform=platform,
                             related=related, citations=citations, submitted_by=owner)
    return {"title": f"[memory] {title}", "body": body, "labels": ["okf-memory"]}


def build_correction_submission(*, owner, target_concept_id, corrected_fact, rationale,
                                citations=None, supersedes=None) -> dict:
    body = correction_issue_body(target_concept_id=target_concept_id, corrected_fact=corrected_fact,
                                 rationale=rationale, citations=citations, supersedes=supersedes,
                                 submitted_by=owner)
    return {"title": f"[correction] {target_concept_id}", "body": body, "labels": ["okf-correction"]}
