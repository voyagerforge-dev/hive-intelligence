"""Boilerplate stripper, scrub copyright / trademark / confidentiality / page-number noise
from converted markdown, via product-tunable YAML regex rules.

Ported (the Layer-2 regex layer) from the retired gwen-platform ingestion `stripper.py`. The
original also had a Layer-1 *structural* pass that removed page headers/footers via a Docling
DoclingDocument model; hive-prep's converter returns markdown text (not the doc model), so that
layer is a documented follow-up (it would need `DoclingClient` to also return the doc JSON).

Public API:
    strip_boilerplate(markdown_text, product="default", rules_dir=None) -> StrippingResult
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_RULES_DIR = Path(__file__).parent / "stripper_rules"

_FLAG_MAP = {"MULTILINE": re.MULTILINE, "IGNORECASE": re.IGNORECASE, "DOTALL": re.DOTALL}


@dataclass
class StrippingResult:
    """Cleaned text plus diagnostics on how much boilerplate was removed."""

    text: str
    original_length: int
    stripped_length: int
    regex_matches: int = 0
    product: str = "default"


def load_stripping_rules(product: str, rules_dir: Path | None = None) -> list[re.Pattern]:
    """Compile the boilerplate regex rules for a product from ``<rules_dir>/<product>.yaml``,
    falling back to ``default.yaml`` when the product-specific ruleset is absent."""
    base = rules_dir or _RULES_DIR
    path = base / f"{product.lower()}.yaml"
    if not path.exists():
        path = base / "default.yaml"
    config = yaml.safe_load(path.read_text()) or {}
    patterns: list[re.Pattern] = []
    for rule in config.get("patterns", []):
        flags = 0
        flag_str = rule.get("flags", "") or ""
        for name, val in _FLAG_MAP.items():
            if name in flag_str:
                flags |= val
        patterns.append(re.compile(rule["pattern"], flags))
    return patterns


def _apply(text: str, patterns: list[re.Pattern]) -> tuple[str, int]:
    total = 0
    for pattern in patterns:
        text, count = pattern.subn("", text)
        total += count
    text = re.sub(r"\n{3,}", "\n\n", text)  # collapse blank-line runs the removals leave behind
    return text.strip(), total


def strip_boilerplate(markdown_text: str, product: str = "default",
                      rules_dir: Path | None = None) -> StrippingResult:
    """Strip product-specific boilerplate (copyright / trademark / confidentiality / page-number
    lines) from markdown via YAML regex rules. A pure text transform, safe on any markdown."""
    original = len(markdown_text)
    patterns = load_stripping_rules(product, rules_dir)
    cleaned, matches = _apply(markdown_text, patterns)
    return StrippingResult(text=cleaned, original_length=original,
                           stripped_length=len(cleaned), regex_matches=matches, product=product)
