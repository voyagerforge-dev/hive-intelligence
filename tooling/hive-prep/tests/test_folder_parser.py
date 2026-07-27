"""Tests for the folder path parser."""

from hiveprep.folder_parser import parse_folder_segments, CATEGORY_KEYWORDS


def test_no_client_scoped_doc_types():
    banned = {"client-sdd", "client-addon", "client-knowhow",
              "client-runbook", "client-integration-spec"}
    assert banned.isdisjoint(set(CATEGORY_KEYWORDS.values()))


class TestProductDetection:
    def test_wmos_exact(self):
        result = parse_folder_segments("ACME/WMOS/v2024/file.pdf", ["ACME", "WMOS", "v2024"])
        assert result["product_hint"] == "WMOS"

    def test_scale_exact(self):
        result = parse_folder_segments("X/Scale/file.pdf", ["X", "Scale"])
        assert result["product_hint"] == "SCALE"

    def test_tms_exact(self):
        result = parse_folder_segments("General/TMS/file.pdf", ["General", "TMS"])
        assert result["product_hint"] == "TMS"

    def test_lms_exact(self):
        result = parse_folder_segments("X/LMS/file.pdf", ["X", "LMS"])
        assert result["product_hint"] == "LMS"

    def test_case_insensitive(self):
        result = parse_folder_segments("X/wmos/file.pdf", ["X", "wmos"])
        assert result["product_hint"] == "WMOS"

    def test_alias_warehouse_management(self):
        result = parse_folder_segments("X/Warehouse Management/file.pdf",
                                        ["X", "Warehouse Management"])
        assert result["product_hint"] == "WMOS"

    def test_active_wms(self):
        result = parse_folder_segments("X/Active WMS/file.pdf", ["X", "Active WMS"])
        assert result["product_hint"] == "ACTIVE_WMS"


class TestVersionDetection:
    def test_v2024(self):
        result = parse_folder_segments("X/WMOS/v2024/file.pdf", ["X", "WMOS", "v2024"])
        assert result["version_hint"] == "2024"

    def test_v2023_1(self):
        result = parse_folder_segments("X/WMOS/v2023.1/file.pdf", ["X", "WMOS", "v2023.1"])
        assert result["version_hint"] == "2023.1"

    def test_semver_9_2(self):
        result = parse_folder_segments("X/Scale/v9.2/file.pdf", ["X", "Scale", "v9.2"])
        assert result["version_hint"] == "9.2"

    def test_no_v_prefix(self):
        result = parse_folder_segments("X/WMOS/2024.1/file.pdf", ["X", "WMOS", "2024.1"])
        assert result["version_hint"] == "2024.1"

    def test_version_with_sp(self):
        result = parse_folder_segments("X/WMOS/v2024-SP1/file.pdf", ["X", "WMOS", "v2024-SP1"])
        assert result["version_hint"] == "2024-SP1"

    def test_triple_semver(self):
        result = parse_folder_segments("X/Scale/9.2.1/file.pdf", ["X", "Scale", "9.2.1"])
        assert result["version_hint"] == "9.2.1"


class TestCategoryDetection:
    def test_config_guides(self):
        result = parse_folder_segments("X/WMOS/v2024/Config Guides/file.pdf",
                                        ["X", "WMOS", "v2024", "Config Guides"])
        assert result["category_hint"] == "config-guide"

    def test_user_manuals(self):
        result = parse_folder_segments("X/TMS/User Manuals/file.pdf",
                                        ["X", "TMS", "User Manuals"])
        assert result["category_hint"] == "user-manual"

    def test_release_notes(self):
        result = parse_folder_segments("X/WMOS/Release Notes/file.pdf",
                                        ["X", "WMOS", "Release Notes"])
        assert result["category_hint"] == "release-notes"

    def test_api_reference(self):
        result = parse_folder_segments("X/Scale/API Reference/file.pdf",
                                        ["X", "Scale", "API Reference"])
        assert result["category_hint"] == "api-reference"

    def test_implementation(self):
        result = parse_folder_segments("X/Scale/Implementation/file.pdf",
                                        ["X", "Scale", "Implementation"])
        assert result["category_hint"] == "implementation-guide"

    def test_best_practices(self):
        result = parse_folder_segments("X/WMOS/Best Practices/file.pdf",
                                        ["X", "WMOS", "Best Practices"])
        assert result["category_hint"] == "best-practices"

    def test_training(self):
        result = parse_folder_segments("X/WMOS/Training/file.pdf",
                                        ["X", "WMOS", "Training"])
        assert result["category_hint"] == "training-material"

    def test_troubleshooting(self):
        result = parse_folder_segments("X/WMOS/Troubleshooting/file.pdf",
                                        ["X", "WMOS", "Troubleshooting"])
        assert result["category_hint"] == "troubleshooting"


class TestClientDetection:
    def test_client_first_segment(self):
        result = parse_folder_segments("ACME/WMOS/v2024/file.pdf",
                                        ["ACME", "WMOS", "v2024"])
        assert result["client_hint"] == "ACME"

    def test_general_folder_excluded(self):
        result = parse_folder_segments("General/WMOS/file.pdf", ["General", "WMOS"])
        assert "client_hint" not in result

    def test_shared_folder_excluded(self):
        result = parse_folder_segments("Shared/WMOS/file.pdf", ["Shared", "WMOS"])
        assert "client_hint" not in result

    def test_docs_folder_excluded(self):
        result = parse_folder_segments("Documentation/WMOS/file.pdf",
                                        ["Documentation", "WMOS"])
        assert "client_hint" not in result

    def test_client_with_spaces(self):
        result = parse_folder_segments("Beta Corp/Scale/file.pdf", ["Beta Corp", "Scale"])
        assert result["client_hint"] == "Beta Corp"


class TestFullPaths:
    def test_full_client_path(self):
        """ACME/WMOS/v2024/Config Guides → all four hints populated."""
        result = parse_folder_segments(
            "ACME/WMOS/v2024/Config Guides/picking.pdf",
            ["ACME", "WMOS", "v2024", "Config Guides"],
        )
        assert result == {
            "client_hint": "ACME",
            "product_hint": "WMOS",
            "version_hint": "2024",
            "category_hint": "config-guide",
        }

    def test_general_path_no_client(self):
        """General/TMS/User Manuals → product + category, no client."""
        result = parse_folder_segments(
            "General/TMS/User Manuals/manual.pdf",
            ["General", "TMS", "User Manuals"],
        )
        assert result == {
            "product_hint": "TMS",
            "category_hint": "user-manual",
        }

    def test_unknown_segments(self):
        """Random/Unknown/Folders → client_hint from first unknown."""
        result = parse_folder_segments(
            "Random/Unknown/Folders/file.pdf",
            ["Random", "Unknown", "Folders"],
        )
        assert result.get("client_hint") == "Random"
        assert "product_hint" not in result

    def test_empty_segments(self):
        """Root-level file → empty hints."""
        result = parse_folder_segments("file.pdf", [])
        assert result == {}
