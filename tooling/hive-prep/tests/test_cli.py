from click.testing import CliRunner

from hiveprep.cli import cli


def test_cli_lists_sovereign_commands():
    out = CliRunner().invoke(cli, ["--help"]).output
    for cmd in ["scan", "dups", "validate-plan", "dedup-formats", "normalize",
                "route", "transform", "stamp", "validate-atomic"]:
        assert cmd in out
    # decommissioned commands must NOT exist
    for gone in ["stage", "stage-source", "promote"]:
        assert gone not in out


def test_validate_atomic_on_fixture(tmp_path):
    d = tmp_path / "atomic"; d.mkdir()
    (d / "a.md").write_text('---\ntitle: "A"\nslug: a\nplatform: PLATFORM\nproduct: WIDGETS\n'
                            'version: "2013"\ndoc_type: functional-flow\nstatus: active\n---\n\nBody\n')
    r = CliRunner().invoke(cli, ["validate-atomic", str(d)])
    assert r.exit_code == 0 and "0 errors" in r.output
