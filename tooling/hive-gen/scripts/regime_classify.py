# knowledge/okf/tooling/hive-gen/scripts/regime_classify.py
"""Classify every card in a concepts dir by regime → a reviewable regime-classification.yaml.
Usage: python scripts/regime_classify.py <concepts_dir> <out.yaml>  (reads Bifrost creds from env)."""
import sys
from pathlib import Path

import yaml

from hivegen.classify_regime import classify_card_regime
from hivegen.config import get_settings  # existing hivegen env/config loader (pydantic-settings)
from hivegen.llm import BifrostChat


def main(concepts_dir: str, out_path: str) -> None:
    cfg = get_settings()  # reads .env: bifrost_base, bifrost_api_key, assign_model
    llm = BifrostChat(cfg.bifrost_base, cfg.bifrost_api_key, cfg.assign_model,
                      timeout_s=cfg.bifrost_timeout_s)
    records = []
    for p in sorted(Path(concepts_dir).glob("*.md")):
        if p.name == "index.md":
            continue
        r = classify_card_regime(p.read_text(), llm)
        records.append({
            "id": p.stem, "label": r["label"], "rationale": r["rationale"],
            "confidence": r["confidence"],
            "needs_review": r["label"] != "none" and r["confidence"] < 0.75,
        })
    Path(out_path).write_text(yaml.safe_dump(records, sort_keys=False))
    n_ops = sum(1 for r in records if r["label"] == "ops")
    n_trad = sum(1 for r in records if r["label"] == "traditional")
    print(f"classified {len(records)} cards: ops={n_ops} traditional={n_trad} "
          f"none={len(records)-n_ops-n_trad}; wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
