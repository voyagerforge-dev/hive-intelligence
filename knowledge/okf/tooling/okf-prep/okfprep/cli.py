"""okfprep CLI — sovereign WMS doc-prep: inventory → curate (agent) → validate → normalize →
transform (Docling/Qwen) → stamp → validate-atomic → okfgen. No R2/Dify staging."""
from __future__ import annotations

from pathlib import Path

import click
import yaml
from rich.console import Console

console = Console()


@click.group()
@click.version_option()
def cli():
    """okfprep: sovereign WMS doc-prep CLI."""


# --- scan / validate-plan / dedup-formats: recovered verbatim from gwen-prep cli.py (import-renamed) ---

@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--output", "-o", default="inventory.csv", help="Output CSV path (default: inventory.csv)")
@click.option("--include-hidden", is_flag=True, default=False, help="Include hidden files/dirs (starting with . or _)")
@click.option("--all-types", is_flag=True, default=False, help="Include all file types, not just supported ones")
@click.option("--no-progress", is_flag=True, default=False, help="Disable progress bar")
def scan(path: str, output: str, include_hidden: bool, all_types: bool, no_progress: bool):
    """Scan a directory tree and produce a file inventory CSV.

    Walks PATH recursively, catalogs every file with metadata (size, type,
    modified date, folder depth), and parses folder segments as classification
    hints for downstream LLM classification.

    \b
    Output columns:
      relative_path, filename, extension, size_bytes, modified_iso,
      folder_depth, folder_segments, client_hint, product_hint,
      version_hint, category_hint
    """
    from okfprep.scanner import scan_directory, write_inventory_csv

    # Try to load folder_parser (optional — works without it)
    folder_parser_fn = None
    try:
        from okfprep.folder_parser import parse_folder_segments
        folder_parser_fn = parse_folder_segments
    except ImportError:
        pass

    root = Path(path)
    output_path = Path(output)

    console.print(f"[bold]Scanning:[/] {root}")
    console.print(f"[bold]Output:[/]   {output_path}")
    if include_hidden:
        console.print("[dim]Including hidden files/directories[/]")
    if all_types:
        console.print("[dim]Including all file types[/]")
    console.print()

    records = scan_directory(
        root,
        include_hidden=include_hidden,
        supported_only=not all_types,
        folder_parser=folder_parser_fn,
    )

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        count = write_inventory_csv(records, f, show_progress=not no_progress)

    console.print()
    console.print(f"[bold green]✓[/] Scanned [bold]{count:,}[/] files → {output_path}")

    # Quick stats
    _print_stats(output_path)


def _print_stats(csv_path: Path):
    """Print quick summary stats from the inventory CSV."""
    import csv
    from collections import Counter

    ext_counts: Counter = Counter()
    total_size = 0
    error_count = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ext_counts[row["extension"]] += 1
            size = int(row["size_bytes"])
            if size < 0:
                error_count += 1
            else:
                total_size += size

    console.print()
    console.print("[bold]Extension breakdown:[/]")
    for ext, count in ext_counts.most_common(15):
        console.print(f"  {ext or '(none)':>12s}  {count:>8,}")
    if len(ext_counts) > 15:
        console.print(f"  {'... and more':>12s}  {len(ext_counts) - 15:>8,} types")

    # Human-readable size
    if total_size > 1_073_741_824:
        size_str = f"{total_size / 1_073_741_824:.1f} GB"
    elif total_size > 1_048_576:
        size_str = f"{total_size / 1_048_576:.1f} MB"
    else:
        size_str = f"{total_size / 1024:.1f} KB"

    console.print(f"\n[bold]Total size:[/] {size_str}")
    if error_count:
        console.print(f"[yellow]⚠ {error_count} files with access errors[/]")


@cli.command(name="validate-plan")
@click.argument("plan_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--corpus-root", default="", help="Override corpus_root from the plan")
def validate_plan_cmd(plan_path: str, corpus_root: str):
    """Validate a wms-curation.yaml before execution."""
    from okfprep.curation_plan import load_plan, validate_plan

    plan = load_plan(Path(plan_path))
    errs = validate_plan(plan, corpus_root=Path(corpus_root) if corpus_root else None)
    for e in errs:
        console.print(f"  [red]✗[/] {e}")
    console.print(f"\n[bold]{len(errs)} errors[/]; include={len(plan.include)} exclude={len(plan.exclude)}")
    if errs:
        raise SystemExit(1)


@cli.command(name="dedup-formats")
@click.argument("plan_path", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--out", default="", help="output plan path (default: overwrite PLAN_PATH)")
def dedup_formats_cmd(plan_path: str, out: str):
    """Collapse same-document format variants (X.doc + X.docx → keep richest) so each doc has one
    unique slug/output path. Records dropped variants as dedup_groups."""
    from okfprep.curation_plan import load_plan, dedup_format_variants

    plan = load_plan(Path(plan_path))
    before = len(plan.include)
    deduped = dedup_format_variants(plan)
    after = len(deduped.include)
    out_path = Path(out) if out else Path(plan_path)
    manifest = {
        "scope": deduped.scope, "corpus_root": deduped.corpus_root, "subtree": deduped.subtree,
        "generated_by": "dedup-formats", "include": deduped.include,
        "exclude": deduped.exclude, "dedup_groups": deduped.dedup_groups, "supersedes": deduped.supersedes,
    }
    out_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
    console.print(f"[bold]include {before} → {after}[/] ({before - after} format-variants folded into dedup_groups)")
    console.print(f"plan → {out_path}")


@cli.command()
@click.argument("source", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("-o", "--out", default="dups.yaml")
def dups(source, out):
    """Report byte-identical duplicate sets under SOURCE."""
    from okfprep.dups import group_duplicates
    exts = {".pdf", ".docx", ".pptx", ".xlsx"}
    files = [p for p in Path(source).rglob("*") if p.is_file() and p.suffix.lower() in exts]
    groups = group_duplicates(files)
    Path(out).write_text(yaml.safe_dump({"duplicate_groups": groups}, sort_keys=False))
    console.print(f"[bold]{len(groups)} duplicate sets[/] → {out}")


@cli.command()
@click.option("--plan", "plan_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--work", "-w", default="", help="work dir (default: settings.work_dir)")
@click.option("--jobs", "-j", default=0, help="LibreOffice workers (default: settings.lo_jobs)")
def normalize(plan_path, work, jobs):
    """Normalize a plan's includes to PDF intermediates (LibreOffice)."""
    from okfprep.config import get_settings
    from okfprep.curation_plan import load_plan
    from okfprep.normalize import normalize_plan
    s = get_settings()
    plan = load_plan(Path(plan_path))
    work_dir = Path(work or s.work_dir)
    res = normalize_plan(plan, work_dir, base_dir=Path(plan.corpus_root), jobs=jobs or s.lo_jobs)
    ok = sum(1 for r in res if r.ok)
    console.print(f"[bold]{ok}/{len(res)} normalized[/] → {work_dir}/pdf")


@cli.command()
@click.option("--plan", "plan_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--work", "-w", default="")
def route(plan_path, work):
    """GPU-free precheck: report text/vision/passthrough tier per doc (no conversion)."""
    from collections import Counter
    from okfprep.config import get_settings
    from okfprep.curation_plan import load_plan
    from okfprep.transform import route_plan
    s = get_settings()
    rows = route_plan(load_plan(Path(plan_path)), Path(work or s.work_dir), s.vision_min_chars)
    tally = Counter(r.tier for r in rows)
    for r in rows:
        console.print(f"  {r.tier:11s} {r.slug}")
    console.print(f"\n[bold]{dict(tally)}[/] ({len(rows)} docs)")


@cli.command()
@click.option("--plan", "plan_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--work", "-w", default="")
def transform(plan_path, work):
    """Convert normalized PDFs + passthrough sources to atomic markdown (Docling / Qwen)."""
    from collections import Counter
    from okfprep.config import get_settings
    from okfprep.curation_plan import load_plan
    from okfprep.docling_client import DoclingClient
    from okfprep.vision import QwenVisionClient
    from okfprep.transform import transform_plan
    s = get_settings()
    docling = DoclingClient(base=s.docling_base, api_key=s.docling_api_key,
                            timeout_s=s.docling_timeout_s, ca_bundle=s.docling_ca_bundle) \
        if (s.prefer_docling and s.docling_base) else None
    vision = QwenVisionClient(base=s.qwen_base, api_key=s.qwen_api_key, model=s.qwen_model,
                              timeout_s=s.qwen_timeout_s)
    res = transform_plan(load_plan(Path(plan_path)), Path(work or s.work_dir),
                         docling=docling, vision=vision, vision_min_chars=s.vision_min_chars,
                         prefer_docling=s.prefer_docling,
                         strip_product=s.strip_product if s.strip_boilerplate else None)
    tally = Counter(r.tier if r.ok else "error" for r in res)
    console.print(f"[bold]{dict(tally)}[/] ({len(res)} docs) → atomic")


@cli.command()
@click.option("--plan", "plan_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--atomic", "atomic_dir", default="", help="default: settings.atomic_dir")
@click.option("--overwrite", is_flag=True, default=False)
def stamp(plan_path, atomic_dir, overwrite):
    """Stamp platform/product/version/doc_type/topic frontmatter from the curation plan."""
    from okfprep.config import get_settings
    from okfprep.curation_plan import load_plan
    from okfprep.stamp import stamp_from_plan
    s = get_settings()
    changed = stamp_from_plan(Path(atomic_dir or s.atomic_dir), load_plan(Path(plan_path)),
                              only_missing=not overwrite)
    console.print(f"[bold]{len(changed)} files stamped[/]")


@cli.command(name="validate-atomic")
@click.argument("atomic_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--relations-out", default="", help="write derived relations.yaml here")
def validate_atomic_cmd(atomic_dir, relations_out):
    """Validate the atomic-markdown corpus (unique slugs, doc_type/status enums, resolvable links)."""
    from okfprep.validate import validate_atomic_dir, write_relations
    rep = validate_atomic_dir(Path(atomic_dir))
    for e in rep.errors:
        console.print(f"  [red]x[/] {e}")
    if relations_out:
        write_relations(rep, Path(relations_out))
    console.print(f"\n[bold]{len(rep.errors)} errors[/] ({len(rep.slugs)} docs, "
                  f"{len(rep.relations['edges'])} edges)")
    if rep.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
