"""Tests for the filesystem scanner."""
import csv
import io
from pathlib import Path

import pytest

from hiveprep.scanner import (
    scan_directory,
    write_inventory_csv,
)


@pytest.fixture
def sample_tree(tmp_path):
    """Create a sample directory tree for testing."""
    # Client/Product/Version/Category structure
    d1 = tmp_path / "ACME" / "WMOS" / "v2024" / "Config Guides"
    d1.mkdir(parents=True)
    (d1 / "picking-config.pdf").write_text("content")
    (d1 / "screenshot.png").write_text("image data")

    d2 = tmp_path / "ACME" / "WMOS" / "v2024" / "Training"
    d2.mkdir(parents=True)
    (d2 / "basics.docx").write_text("training content")

    # General folder (no client)
    d3 = tmp_path / "General" / "TMS" / "User Manuals"
    d3.mkdir(parents=True)
    (d3 / "manual.pdf").write_text("manual")

    # Hidden files and dirs
    hd = tmp_path / ".hidden"
    hd.mkdir()
    (hd / "secret.pdf").write_text("hidden")

    # Unsupported extension
    (tmp_path / "ACME" / "WMOS" / "v2024" / "Thumbs.db").write_text("thumbs")

    # Empty directory
    (tmp_path / "EmptyDir").mkdir()

    return tmp_path


class TestScanDirectory:
    def test_basic_scan_counts(self, sample_tree):
        records = list(scan_directory(sample_tree))
        # 4 supported files: picking-config.pdf, screenshot.png, basics.docx, manual.pdf
        assert len(records) == 4

    def test_excludes_hidden_by_default(self, sample_tree):
        records = list(scan_directory(sample_tree))
        paths = [r.relative_path for r in records]
        assert not any(".hidden" in p for p in paths)

    def test_includes_hidden_when_flag_set(self, sample_tree):
        records = list(scan_directory(sample_tree, include_hidden=True))
        paths = [r.relative_path for r in records]
        assert any(".hidden" in p for p in paths)

    def test_excludes_unsupported_extensions(self, sample_tree):
        records = list(scan_directory(sample_tree))
        exts = [r.extension for r in records]
        assert ".db" not in exts

    def test_includes_all_types_when_flag_set(self, sample_tree):
        records = list(scan_directory(sample_tree, supported_only=False))
        exts = [r.extension for r in records]
        assert ".db" in exts

    def test_record_fields(self, sample_tree):
        records = list(scan_directory(sample_tree))
        pdf = next(r for r in records if r.filename == "picking-config.pdf")
        assert pdf.extension == ".pdf"
        assert pdf.size_bytes > 0
        assert pdf.modified_iso  # non-empty ISO timestamp
        assert pdf.folder_depth == 4
        assert "ACME" in pdf.folder_segments
        assert "WMOS" in pdf.folder_segments

    def test_folder_segments_pipe_separated(self, sample_tree):
        records = list(scan_directory(sample_tree))
        manual = next(r for r in records if r.filename == "manual.pdf")
        assert manual.folder_segments == "General|TMS|User Manuals"

    def test_empty_dirs_produce_no_records(self, sample_tree):
        records = list(scan_directory(sample_tree))
        paths = [r.relative_path for r in records]
        assert not any("EmptyDir" in p for p in paths)

    def test_folder_parser_integration(self, sample_tree):
        """When a folder_parser is provided, hint columns are populated."""
        def mock_parser(rel_path, segments):
            return {"product_hint": "WMOS", "client_hint": "ACME"}

        records = list(scan_directory(sample_tree, folder_parser=mock_parser))
        for rec in records:
            assert rec.product_hint == "WMOS"
            assert rec.client_hint == "ACME"

    def test_folder_parser_error_non_fatal(self, sample_tree):
        """A crashing folder_parser doesn't break scanning."""
        def bad_parser(rel_path, segments):
            raise ValueError("parser exploded")

        records = list(scan_directory(sample_tree, folder_parser=bad_parser))
        assert len(records) == 4  # all files still scanned

    def test_permission_error_produces_error_record(self, tmp_path):
        """Files that can't be stat'd get a size_bytes=-1 error record.

        On Linux, stat() on a file you own succeeds even with mode 0o000.
        Instead, we test via monkeypatch to simulate a PermissionError.
        """
        d = tmp_path / "restricted"
        d.mkdir()
        f = d / "locked.pdf"
        f.write_text("data")

        # Monkeypatch os.walk doesn't help — patch Path.stat via scanner
        import hiveprep.scanner as scanner_mod
        original_stat = Path.stat

        call_count = 0
        def patched_stat(self, *args, **kwargs):
            nonlocal call_count
            if self.name == "locked.pdf":
                raise PermissionError("Permission denied")
            return original_stat(self, *args, **kwargs)

        scanner_mod.Path.stat = patched_stat
        try:
            records = list(scan_directory(tmp_path))
            error_recs = [r for r in records if r.size_bytes == -1]
            assert len(error_recs) == 1
            assert "ERROR" in error_recs[0].category_hint
        finally:
            scanner_mod.Path.stat = original_stat


class TestWriteInventoryCSV:
    def test_writes_header_and_records(self, sample_tree):
        records = scan_directory(sample_tree)
        buf = io.StringIO()
        count = write_inventory_csv(records, buf, show_progress=False)
        assert count == 4
        buf.seek(0)
        reader = csv.DictReader(buf)
        rows = list(reader)
        assert len(rows) == 4
        assert "relative_path" in rows[0]
        assert "extension" in rows[0]

    def test_empty_directory_writes_header_only(self, tmp_path):
        (tmp_path / "empty").mkdir()
        records = scan_directory(tmp_path / "empty")
        buf = io.StringIO()
        count = write_inventory_csv(records, buf, show_progress=False)
        assert count == 0
        buf.seek(0)
        reader = csv.DictReader(buf)
        assert list(reader) == []
