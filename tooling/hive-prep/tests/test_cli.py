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


def _plan(tmp_path):
    plan = tmp_path / "plan.yaml"
    plan.write_text("scope: s\ncorpus_root: /tmp\nsubtree: ''\ninclude: []\nexclude: []\n")
    return plan


def test_stamp_refuses_an_atomic_dir_that_is_not_there_and_blames_the_flag(tmp_path,
                                                                          monkeypatch):
    """Stamping a directory that does not exist reported '0 files stamped' and exited 0,
    which is exactly what a correctly-configured run over an already-stamped corpus looks
    like. The refusal must name where the bad value came from: an operator whose .env is
    correct and who typo'd the flag should not be sent to inspect ATOMIC_DIR."""
    from hiveprep.config import get_settings
    good = tmp_path / "atomic"
    good.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATOMIC_DIR", str(good))  # settings are correct; the flag is not
    get_settings.cache_clear()

    r = CliRunner().invoke(cli, ["stamp", "--plan", str(_plan(tmp_path)),
                                 "--atomic", str(tmp_path / "gone")])

    get_settings.cache_clear()
    message = r.output + str(r.exception)
    assert r.exit_code != 0
    assert "--atomic" in message
    assert "ATOMIC_DIR=" not in message, "blamed the setting for a value the flag supplied"


def test_stamp_refuses_an_atomic_dir_from_settings_and_blames_the_setting(tmp_path,
                                                                         monkeypatch):
    """The other half: with no flag, the value did come from ATOMIC_DIR, so that is what
    the refusal must name."""
    from hiveprep.config import get_settings
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATOMIC_DIR", str(tmp_path / "gone"))
    get_settings.cache_clear()

    r = CliRunner().invoke(cli, ["stamp", "--plan", str(_plan(tmp_path))])

    get_settings.cache_clear()
    message = r.output + str(r.exception)
    assert r.exit_code != 0
    assert "ATOMIC_DIR" in message


def test_stamp_refuses_a_blank_atomic_dir_rather_than_stamping_the_working_directory(
        tmp_path, monkeypatch):
    """`ATOMIC_DIR=` in a copied .env is Path(""), which is Path("."), which IS a
    directory - so an is_dir() check passes and the pass globs the working directory
    instead. Nothing there matches the plan, so it prints "0 files stamped in ." and
    exits 0: the same silent success a missing directory used to produce."""
    from hiveprep.config import get_settings
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATOMIC_DIR", "")
    get_settings.cache_clear()
    r = CliRunner().invoke(cli, ["stamp", "--plan", str(_plan(tmp_path))])

    get_settings.cache_clear()
    assert r.exit_code != 0
    assert "ATOMIC_DIR" in r.output or "ATOMIC_DIR" in str(r.exception)
