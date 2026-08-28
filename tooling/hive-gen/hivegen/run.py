"""Orchestrate the OKF card pipeline (gate-aware) + detached entrypoint."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hivegen.assign import assign_docs
from hivegen.card import distill_concept
from hivegen.llm import ChatLLM
from hivegen.load import Doc
from hivegen.taxonomy import Concept


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
        draft_path = drafts_dir / f"{cid}.md"
        if draft_path.exists():
            continue  # idempotency: never overwrite an existing draft
        try:
            card = distill_concept(
                concept, [docs_by_id[i] for i in doc_ids], distill_llm,
                max_chars=max_chars, today=today,
                related_ids=[c.id for c in concepts if c.id != cid],
            )
            if card is None:
                continue
            draft_path.write_text(card)
            written.append(f"{cid}.md")
        except Exception as exc:  # noqa: BLE001 - one bad concept must not end the batch
            print(f"[hivegen] skipping concept {cid!r}: {exc}", flush=True)
            continue
    return sorted(written)


def main() -> None:
    from hivegen.config import get_settings
    from hivegen.corpus import require_dir
    from hivegen.load import load_area_local, load_docs, load_docs_local, load_subarea_local
    from hivegen.profile import load_profile, missing_profile_error
    from hivegen.taxonomy import load_taxonomy, propose_taxonomy, write_taxonomy

    s = get_settings()
    # Configured, never derived. This was `Path(__file__).parents[3]`, which stopped being
    # the corpus when the corpus became its own repository and started being the engine
    # checkout, where no approved taxonomy has ever lived.
    root = require_dir(s.card_corpus_root, setting="CARD_CORPUS_ROOT",
                       what="the card corpus this pass generates into")
    profile = load_profile(atomic_dir=s.atomic_dir or None)
    area = s.slice_area.strip()
    is_sub = area in profile.subareas
    if area and not is_sub and area not in profile.areas:
        if profile.is_empty:
            raise SystemExit(missing_profile_error("functional areas", area))
        raise SystemExit(
            f"unknown SLICE_AREA '{area}'; {profile.path} defines "
            f"areas: {sorted(profile.areas)}; sub-areas: {sorted(profile.subareas)}")
    label = area or "the whole corpus"
    stem = f"taxonomy.{area}" if area else "taxonomy"  # per-area taxonomy, areas never clobber

    if s.atomic_dir:
        if is_sub:
            docs = load_subarea_local(s.atomic_dir, area, profile)
        elif area:
            docs = load_area_local(s.atomic_dir, area, profile)
        else:
            docs = load_docs_local(s.atomic_dir)
        print(f"loaded {len(docs)} {label} docs from {s.atomic_dir}", flush=True)
    else:
        import boto3
        s3 = boto3.client("s3", endpoint_url=s.r2_endpoint,
                          aws_access_key_id=s.r2_access_key_id,
                          aws_secret_access_key=s.r2_secret_access_key)
        docs = load_docs(s3, s.r2_bucket, s.r2_prefix)
        print(f"loaded {len(docs)} {label} docs from R2 {s.r2_prefix}", flush=True)

    taxonomy_path = root / f"{stem}.yaml"
    if not taxonomy_path.exists():
        from hivegen.llm import BifrostChat
        tx_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.taxonomy_model,
                             timeout_s=s.bifrost_timeout_s)
        concepts = propose_taxonomy(docs, tx_llm)
        draft_path = root / f"{stem}.draft.yaml"
        write_taxonomy(draft_path, concepts)
        # Name the full paths, not bare filenames. Proposing a taxonomy while an approved
        # one sits in a directory nobody looked at is the failure this whole lookup is
        # about, and a bare filename is the one thing that cannot show you it happened.
        print(f"GATE 1 [{label}]: no {taxonomy_path}, so proposed {len(concepts)} concepts "
              f"→ {draft_path}. Review, then save as {stem}.yaml and re-run.", flush=True)
        return

    from hivegen.llm import BifrostChat
    concepts = load_taxonomy(taxonomy_path)
    assign_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.assign_model,
                             timeout_s=s.bifrost_timeout_s)
    distill_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.distill_model,
                              timeout_s=s.bifrost_timeout_s)
    written = generate_drafts(docs, concepts, assign_llm, distill_llm,
                              drafts_dir=root / "drafts", max_chars=s.max_chars,
                              today=datetime.now(UTC).date().isoformat(),
                              pipeline_dir=root / ".pipeline" / (area or "wave-replen"))
    print(f"GATE 2 [{label}]: distilled {taxonomy_path} into {len(written)} draft cards "
          f"→ {root / 'drafts'}. Review, flip status: approved, then run promote.",
          flush=True)


if __name__ == "__main__":
    main()
