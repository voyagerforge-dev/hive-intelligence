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
    # Validated before load_profile, not after: load_profile looks for corpus-profile.yaml
    # beside ATOMIC_DIR, so a typo there surfaces one step later as "no corpus profile
    # found" and sends the operator after CORPUS_PROFILE, which is not the setting that is
    # wrong. Optional by design - empty falls back to the R2 reader below - so the check
    # runs only when it is set.
    atomic = (require_dir(s.atomic_dir, setting="ATOMIC_DIR",
                          what="the atomic documents to generate from")
              if s.atomic_dir else None)
    profile = load_profile(explicit=s.corpus_profile or None,
                           atomic_dir=str(atomic) if atomic is not None else None)
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

    if atomic is not None:
        if is_sub:
            docs = load_subarea_local(atomic, area, profile)
        elif area:
            docs = load_area_local(atomic, area, profile)
        else:
            docs = load_docs_local(atomic)
        source = f"ATOMIC_DIR={atomic}"
    else:
        # ATOMIC_DIR is empty, so the documents come from R2 and the location has to be
        # given. Refusing here beats the alternative: unset, botocore raises
        # "Invalid endpoint:" from four frames down, which names nothing an operator can
        # act on, and a wrong-but-set location reads as a corpus with nothing in it.
        for value, setting, what in (
            (s.r2_bucket, "R2_BUCKET", "the bucket the atomic documents are in"),
            (s.r2_prefix, "R2_PREFIX",
             "the prefix they sit under, since a bucket holds more than one dataset"),
            (s.r2_endpoint, "R2_ENDPOINT",
             ("the account the bucket is reached through - unset, botocore raises "
              '"Invalid endpoint:" several frames down instead of naming this setting')),
        ):
            if not value.strip():
                raise SystemExit(
                    f"ATOMIC_DIR is empty, so this pass reads from R2, but {setting} is not "
                    f"set and there is no way to find {what}. Set ATOMIC_DIR to read local "
                    f"atomic markdown instead, or set {setting}. See .env.example.")
        import boto3
        s3 = boto3.client("s3", endpoint_url=s.r2_endpoint,
                          aws_access_key_id=s.r2_access_key_id,
                          aws_secret_access_key=s.r2_secret_access_key)
        docs = load_docs(s3, s.r2_bucket, s.r2_prefix)
        source = f"R2 {s.r2_bucket}/{s.r2_prefix}"
    print(f"loaded {len(docs)} {label} docs from {source}", flush=True)
    if not docs:
        # Before gate 1, because gate 1 is where zero documents stops being empty and
        # starts being wrong: propose_taxonomy hands an empty inventory to a prompt that
        # asks for 25-45 concepts, so the model invents them and write_taxonomy persists
        # the invention as though it had been derived from documents.
        which = (f"the sub-area filter SLICE_AREA={area!r}" if is_sub else
                 f"the area filter SLICE_AREA={area!r}" if area else
                 "no SLICE_AREA filter, so every document under it")
        raise SystemExit(
            f"{source} yielded no documents for {label} ({which}). There is nothing to "
            "generate from, and a taxonomy proposed from an empty inventory is invented "
            f"rather than derived - it would have been written into {root}. Either the "
            "source holds no atomic markdown, or the filter matches none of it.")

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
