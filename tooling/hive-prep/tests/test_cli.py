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


def test_stamp_refuses_an_atomic_dir_that_is_not_there(tmp_path):
    """Stamping a directory that does not exist reported '0 files stamped' and exited 0,
    which is exactly what a correctly-configured run over an already-stamped corpus looks
    like. The dead ATOMIC_DIR in .env.example made that the first thing a new operator saw."""
    plan = tmp_path / "plan.yaml"
    plan.write_text("scope: s\ncorpus_root: /tmp\nsubtree: ''\ninclude: []\nexclude: []\n")
    r = CliRunner().invoke(cli, ["stamp", "--plan", str(plan),
                                 "--atomic", str(tmp_path / "gone")])
    assert r.exit_code != 0
    assert "ATOMIC_DIR" in r.output or "ATOMIC_DIR" in str(r.exception)
