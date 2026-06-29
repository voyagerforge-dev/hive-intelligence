"""Orchestrate the OKF card pipeline (gate-aware) + detached entrypoint."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from okfgen.assign import assign_docs
from okfgen.card import distill_concept
from okfgen.llm import ChatLLM
from okfgen.load import Doc
from okfgen.taxonomy import Concept


def generate_drafts(docs: list[Doc], concepts: list[Concept], assign_llm: ChatLLM,
                    distill_llm: ChatLLM, *, drafts_dir, max_chars: int, today: str,
                    pipeline_dir=None) -> list[str]:
    drafts_dir = Path(drafts_dir)
    drafts_dir.mkdir(parents=True, exist_ok=True)
    assignments, excluded = assign_docs(docs, concepts, assign_llm)
    if pipeline_dir is not None:
        import yaml
        pdir = Path(pipeline_dir)
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "assignments.yaml").write_text(
            yaml.safe_dump({"assignments": assignments, "excluded": excluded}, sort_keys=False))
    by_id = {c.id: c for c in concepts}
    docs_by_id = {d.id: d for d in docs}
    written: list[str] = []
    for cid, doc_ids in assignments.items():
        concept = by_id.get(cid)
        if not concept:
            continue
        card = distill_concept(concept, [docs_by_id[i] for i in doc_ids], distill_llm,
                               max_chars=max_chars, today=today)
        if card is None:
            continue
        (drafts_dir / f"{cid}.md").write_text(card)
        written.append(f"{cid}.md")
    return sorted(written)


def main() -> None:  # pragma: no cover — live wiring (detached)
    import boto3

    from okfgen.config import get_settings
    from okfgen.load import load_docs
    from okfgen.taxonomy import load_taxonomy, propose_taxonomy, write_taxonomy

    s = get_settings()
    root = Path(__file__).resolve().parents[3]  # voyagerforge-knowledge repo root
    s3 = boto3.client("s3", endpoint_url=s.r2_endpoint,
                      aws_access_key_id=s.r2_access_key_id,
                      aws_secret_access_key=s.r2_secret_access_key)
    docs = load_docs(s3, s.r2_bucket, s.r2_prefix)
    print(f"loaded {len(docs)} Wave/Replenishment docs", flush=True)

    taxonomy_path = root / "taxonomy.yaml"
    if not taxonomy_path.exists():
        from okfgen.llm import BifrostChat
        tx_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.taxonomy_model)
        concepts = propose_taxonomy(docs, tx_llm)
        write_taxonomy(root / "taxonomy.draft.yaml", concepts)
        print(f"GATE 1: proposed {len(concepts)} concepts → taxonomy.draft.yaml. "
              "Review, then save as taxonomy.yaml and re-run.", flush=True)
        return

    from okfgen.llm import BifrostChat
    concepts = load_taxonomy(taxonomy_path)
    assign_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.assign_model)
    distill_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.distill_model)
    written = generate_drafts(docs, concepts, assign_llm, distill_llm,
                              drafts_dir=root / "drafts", max_chars=s.max_chars,
                              today=date.today().isoformat(), pipeline_dir=root / ".pipeline")
    print(f"GATE 2: wrote {len(written)} draft cards → drafts/. Review, flip status: approved, "
          "then run promote.", flush=True)


if __name__ == "__main__":
    main()
