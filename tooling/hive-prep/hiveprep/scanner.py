"""Filesystem scanner, walks a directory tree and catalogs every file.

Produces a streaming CSV inventory with file metadata and parsed folder
segments as classification hints. Memory-efficient: never loads the full
file list into memory.
"""
from __future__ import annotations

import csv
import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

# ── Inventory row ────────────────────────────────────────────────────

INVENTORY_FIELDS = [
    "relative_path",
    "filename",
    "extension",
    "size_bytes",
    "modified_iso",
    "folder_depth",
    "folder_segments",
    # Classification hint columns (populated by folder_parser)
    "client_hint",
    "product_hint",
    "version_hint",
    "category_hint",
]


@dataclass
class FileRecord:
    """One row of the inventory CSV."""
    relative_path: str
    filename: str
    extension: str
    size_bytes: int
    modified_iso: str
    folder_depth: int
    folder_segments: str  # pipe-separated folder names
    client_hint: str = ""
    product_hint: str = ""
    version_hint: str = ""
    category_hint: str = ""


# ── Supported file extensions ────────────────────────────────────────

# Extensions Docling and the ingestion pipeline can handle
SUPPORTED_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    ".xlsx", ".xls", ".csv",
    ".html", ".htm", ".mhtml",
    ".txt", ".md", ".rst",
    ".rtf", ".odt", ".odp", ".ods",
    ".json", ".xml", ".yaml", ".yml",
    ".png", ".jpg", ".jpeg", ".gif", ".tiff", ".bmp",
})


# ── Scanner ──────────────────────────────────────────────────────────

def scan_directory(
    root: Path,
    *,
    include_hidden: bool = False,
    supported_only: bool = True,
    folder_parser=None,
) -> Iterator[FileRecord]:
    """Walk *root* recursively, yielding a FileRecord for every regular file.

    Args:
        root: Directory to scan.
        include_hidden: If False (default), skip files and directories
            starting with '.' or '_'.
        supported_only: If True (default), skip files whose extension
            is not in SUPPORTED_EXTENSIONS.
        folder_parser: Optional callable(relative_path, segments) -> dict
            that returns classification hints from folder structure.

    Yields:
        FileRecord instances in filesystem walk order.
    """
    root = root.resolve()

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune hidden/system directories in-place
        if not include_hidden:
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and not d.startswith("_")
            ]

        current = Path(dirpath)
        rel_dir = current.relative_to(root)
        segments = list(rel_dir.parts) if str(rel_dir) != "." else []
        depth = len(segments)

        for fname in filenames:
            # Skip hidden files
            if not include_hidden and fname.startswith("."):
                continue

            filepath = current / fname
            ext = filepath.suffix.lower()

            # Skip unsupported extensions
            if supported_only and ext not in SUPPORTED_EXTENSIONS:
                continue

            # Stat the file, skip on permission error
            try:
                st = filepath.stat()
            except (PermissionError, OSError) as exc:
                # Caller can log this; we just skip
                yield _error_record(filepath, root, segments, depth, str(exc))
                continue

            # Skip non-regular files (symlinks already excluded by followlinks=False)
            if not stat.S_ISREG(st.st_mode):
                continue

            rel_path = str(filepath.relative_to(root))
            modified = datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat()

            # Parse folder hints
            hints: dict = {}
            if folder_parser and segments:
                try:
                    hints = folder_parser(rel_path, segments)
                except Exception:  # noqa: BLE001, S110 - folder_parser errors are non-fatal
                    pass

            yield FileRecord(
                relative_path=rel_path,
                filename=fname,
                extension=ext,
                size_bytes=st.st_size,
                modified_iso=modified,
                folder_depth=depth,
                folder_segments="|".join(segments),
                client_hint=hints.get("client_hint", ""),
                product_hint=hints.get("product_hint", ""),
                version_hint=hints.get("version_hint", ""),
                category_hint=hints.get("category_hint", ""),
            )


def _error_record(filepath: Path, root: Path, segments: list, depth: int, error: str) -> FileRecord:
    """Create a record for a file that couldn't be stat'd."""
    return FileRecord(
        relative_path=str(filepath.relative_to(root)),
        filename=filepath.name,
        extension=filepath.suffix.lower(),
        size_bytes=-1,
        modified_iso="",
        folder_depth=depth,
        folder_segments="|".join(segments),
        client_hint="",
        product_hint="",
        version_hint="",
        category_hint=f"ERROR: {error}",
    )


# ── CSV writer ───────────────────────────────────────────────────────

def write_inventory_csv(
    records: Iterator[FileRecord],
    output: IO[str],
    *,
    show_progress: bool = True,
) -> int:
    """Stream FileRecord instances to a CSV file.

    Returns the number of records written.
    """
    writer = csv.DictWriter(output, fieldnames=INVENTORY_FIELDS)
    writer.writeheader()

    count = 0
    if show_progress:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Scanning..."),
            BarColumn(bar_width=40),
            TaskProgressColumn(),
            TextColumn("[green]{task.completed} files"),
        ) as progress:
            task = progress.add_task("scan", total=None)
            for rec in records:
                writer.writerow(_record_to_dict(rec))
                count += 1
                progress.update(task, completed=count)
    else:
        for rec in records:
            writer.writerow(_record_to_dict(rec))
            count += 1

    return count


def _record_to_dict(rec: FileRecord) -> dict:
    """Convert a FileRecord to a dict matching INVENTORY_FIELDS."""
    return {f.name: getattr(rec, f.name) for f in fields(rec)}
