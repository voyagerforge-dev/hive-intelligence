import pytest

from hivezendesk.orgs import load_org_ids

YAML = """
customers:
  - code: alpha
    platform: BENCH
    zendesk_orgs:
      - id: 10000000000001
  - code: beta
    platform: BENCH
    zendesk_orgs:
      - id: 10000000002
        umbrella: true
      - id: 10000000003
  - code: other
    platform: SCALE
    zendesk_orgs:
      - id: 999
"""


def test_loads_only_requested_clients(tmp_path):
    p = tmp_path / "customers.yaml"
    p.write_text(YAML)
    out = load_org_ids(p, ["alpha", "beta"])
    assert out == {"alpha": [10000000000001], "beta": [10000000002, 10000000003]}


def test_unknown_client_is_an_error(tmp_path):
    p = tmp_path / "customers.yaml"
    p.write_text(YAML)
    with pytest.raises(KeyError, match="nosuch"):
        load_org_ids(p, ["nosuch"])
