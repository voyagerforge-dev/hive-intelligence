"""Folder path parser.

Product aliases are one corpus's vocabulary and come from the corpus profile, so these
tests supply a synthetic map. Version and category matching are generic and need none.
"""

import pytest

from hiveprep.folder_parser import CATEGORY_KEYWORDS, parse_folder_segments

# A stand-in vocabulary. Shape matters, contents do not.
ALIASES = {
    "alpha": "ALPHA",
    "acme alpha": "ALPHA",
    "widget management": "ALPHA",
    "beta": "BETA",
    "acme beta": "BETA",
    "gamma sys": "GAMMA",
    "gammasys": "GAMMA",
    "delta": "DELTA",
    "epsilon": "EPSILON",
}


@pytest.fixture
def parse():
    """parse_folder_segments with the synthetic product vocabulary bound in."""
    def _p(path, segments):
        return parse_folder_segments(path, segments, product_aliases=ALIASES)
    return _p


def test_no_client_scoped_doc_types():
    banned = {"client-sdd", "client-addon", "client-knowhow",
              "client-runbook", "client-integration-spec"}
    assert banned.isdisjoint(set(CATEGORY_KEYWORDS.values()))


class TestProductDetection:
    def test_alpha_exact(self, parse):
        result = parse("ACME/ALPHA/v2024/file.pdf", ["ACME", "ALPHA", "v2024"])
        assert result["product_hint"] == "ALPHA"

    def test_scale_exact(self, parse):
        result = parse("X/Beta/file.pdf", ["X", "Beta"])
        assert result["product_hint"] == "BETA"

    def test_tms_exact(self, parse):
        result = parse("General/DELTA/file.pdf", ["General", "DELTA"])
        assert result["product_hint"] == "DELTA"

    def test_lms_exact(self, parse):
        result = parse("X/EPSILON/file.pdf", ["X", "EPSILON"])
        assert result["product_hint"] == "EPSILON"

    def test_case_insensitive(self, parse):
        result = parse("X/alpha/file.pdf", ["X", "alpha"])
        assert result["product_hint"] == "ALPHA"

    def test_alias_warehouse_management(self, parse):
        result = parse("X/Widget Management/file.pdf",
                                        ["X", "Widget Management"])
        assert result["product_hint"] == "ALPHA"

    def test_active_wms(self, parse):
        result = parse("X/Gamma Sys/file.pdf", ["X", "Gamma Sys"])
        assert result["product_hint"] == "GAMMA"


class TestVersionDetection:
    def test_v2024(self, parse):
        result = parse("X/ALPHA/v2024/file.pdf", ["X", "ALPHA", "v2024"])
        assert result["version_hint"] == "2024"

    def test_v2023_1(self, parse):
        result = parse("X/ALPHA/v2023.1/file.pdf", ["X", "ALPHA", "v2023.1"])
        assert result["version_hint"] == "2023.1"

    def test_semver_9_2(self, parse):
        result = parse("X/Beta/v9.2/file.pdf", ["X", "Beta", "v9.2"])
        assert result["version_hint"] == "9.2"

    def test_no_v_prefix(self, parse):
        result = parse("X/ALPHA/2024.1/file.pdf", ["X", "ALPHA", "2024.1"])
        assert result["version_hint"] == "2024.1"

    def test_version_with_sp(self, parse):
        result = parse("X/ALPHA/v2024-SP1/file.pdf", ["X", "ALPHA", "v2024-SP1"])
        assert result["version_hint"] == "2024-SP1"

    def test_triple_semver(self, parse):
        result = parse("X/Beta/9.2.1/file.pdf", ["X", "Beta", "9.2.1"])
        assert result["version_hint"] == "9.2.1"


class TestCategoryDetection:
    def test_config_guides(self, parse):
        result = parse("X/ALPHA/v2024/Config Guides/file.pdf",
                                        ["X", "ALPHA", "v2024", "Config Guides"])
        assert result["category_hint"] == "config-guide"

    def test_user_manuals(self, parse):
        result = parse("X/DELTA/User Manuals/file.pdf",
                                        ["X", "DELTA", "User Manuals"])
        assert result["category_hint"] == "user-manual"

    def test_release_notes(self, parse):
        result = parse("X/ALPHA/Release Notes/file.pdf",
                                        ["X", "ALPHA", "Release Notes"])
        assert result["category_hint"] == "release-notes"

    def test_api_reference(self, parse):
        result = parse("X/Beta/API Reference/file.pdf",
                                        ["X", "Beta", "API Reference"])
        assert result["category_hint"] == "api-reference"

    def test_implementation(self, parse):
        result = parse("X/Beta/Implementation/file.pdf",
                                        ["X", "Beta", "Implementation"])
        assert result["category_hint"] == "implementation-guide"

    def test_best_practices(self, parse):
        result = parse("X/ALPHA/Best Practices/file.pdf",
                                        ["X", "ALPHA", "Best Practices"])
        assert result["category_hint"] == "best-practices"

    def test_training(self, parse):
        result = parse("X/ALPHA/Training/file.pdf",
                                        ["X", "ALPHA", "Training"])
        assert result["category_hint"] == "training-material"

    def test_troubleshooting(self, parse):
        result = parse("X/ALPHA/Troubleshooting/file.pdf",
                                        ["X", "ALPHA", "Troubleshooting"])
        assert result["category_hint"] == "troubleshooting"


class TestClientDetection:
    def test_client_first_segment(self, parse):
        result = parse("ACME/ALPHA/v2024/file.pdf",
                                        ["ACME", "ALPHA", "v2024"])
        assert result["client_hint"] == "ACME"

    def test_general_folder_excluded(self, parse):
        result = parse("General/ALPHA/file.pdf", ["General", "ALPHA"])
        assert "client_hint" not in result

    def test_shared_folder_excluded(self, parse):
        result = parse("Shared/ALPHA/file.pdf", ["Shared", "ALPHA"])
        assert "client_hint" not in result

    def test_docs_folder_excluded(self, parse):
        result = parse("Documentation/ALPHA/file.pdf",
                                        ["Documentation", "ALPHA"])
        assert "client_hint" not in result

    def test_client_with_spaces(self, parse):
        result = parse("Beta Corp/Beta/file.pdf", ["Beta Corp", "Beta"])
        assert result["client_hint"] == "Beta Corp"


class TestFullPaths:
    def test_full_client_path(self, parse):
        """ACME/ALPHA/v2024/Config Guides → all four hints populated."""
        result = parse(
            "ACME/ALPHA/v2024/Config Guides/picking.pdf",
            ["ACME", "ALPHA", "v2024", "Config Guides"],
        )
        assert result == {
            "client_hint": "ACME",
            "product_hint": "ALPHA",
            "version_hint": "2024",
            "category_hint": "config-guide",
        }

    def test_general_path_no_client(self, parse):
        """General/DELTA/User Manuals → product + category, no client."""
        result = parse(
            "General/DELTA/User Manuals/manual.pdf",
            ["General", "DELTA", "User Manuals"],
        )
        assert result == {
            "product_hint": "DELTA",
            "category_hint": "user-manual",
        }

    def test_unknown_segments(self, parse):
        """Random/Unknown/Folders → client_hint from first unknown."""
        result = parse(
            "Random/Unknown/Folders/file.pdf",
            ["Random", "Unknown", "Folders"],
        )
        assert result.get("client_hint") == "Random"
        assert "product_hint" not in result

    def test_empty_segments(self, parse):
        """Root-level file → empty hints."""
        result = parse("file.pdf", [])
        assert result == {}
