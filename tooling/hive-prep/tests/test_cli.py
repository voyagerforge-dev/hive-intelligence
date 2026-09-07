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


# --- a product-less include is refused, not crashed on -------------------------------
# `product` leads every slug, so `assign_slugs` refuses an include without one. That
# refusal reaches an operator through route/transform/stamp, and each must present it the
# way every other operator-facing refusal here does: the message alone, no traceback.

def _product_less_plan(tmp_path):
    plan = tmp_path / "plan.yaml"
    plan.write_text(f"scope: s\ncorpus_root: {tmp_path}\nsubtree: ''\n"
                    "include:\n"
                    "  - path: w/Work Order.pdf\n"
                    "    doc_type: functional-flow\n"
                    "exclude: []\n")
    return plan


def _assert_clean_refusal(result):
    assert result.exit_code != 0
    assert isinstance(result.exception, SystemExit), "the exception escaped the command"
    assert "w/Work Order.pdf" in result.output and "product" in result.output
    assert "validate-plan" in result.output
    assert "Traceback" not in result.output


def test_route_refuses_a_product_less_include_without_a_traceback(tmp_path, monkeypatch):
    from hiveprep.config import get_settings
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    r = CliRunner().invoke(cli, ["route", "--plan", str(_product_less_plan(tmp_path))])

    get_settings.cache_clear()
    _assert_clean_refusal(r)


def test_transform_refuses_a_product_less_include_without_a_traceback(tmp_path, monkeypatch):
    from hiveprep.config import get_settings
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    r = CliRunner().invoke(cli, ["transform", "--plan", str(_product_less_plan(tmp_path))])

    get_settings.cache_clear()
    _assert_clean_refusal(r)


def test_stamp_refuses_a_product_less_include_without_a_traceback(tmp_path, monkeypatch):
    from hiveprep.config import get_settings
    atomic = tmp_path / "atomic"
    atomic.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATOMIC_DIR", str(atomic))
    get_settings.cache_clear()

    r = CliRunner().invoke(cli, ["stamp", "--plan", str(_product_less_plan(tmp_path))])

    get_settings.cache_clear()
    _assert_clean_refusal(r)


# --------------------------------------------------------------------------
# `--version`'s whole job is to answer from installed distribution metadata.
# `click.version_option()` with no `package_name` looks that up under the
# *module* name, `hiveprep`, and this distribution is `vf-hive-prep`, so in an
# editable install - where nothing maps the module back to a distribution - it
# raised `RuntimeError: 'hiveprep' is not installed` for anyone who ran it.
# `CliRunner` exercises the same lookup; what it cannot vouch for is the
# console entry point, which is the command that ships, so this runs it in a
# subprocess - a green unit test over a broken installed command is exactly the
# false positive this guards.
# --------------------------------------------------------------------------

def test_version_answers_through_the_installed_console_entry_point():
    import shutil
    import subprocess
    import sys
    from importlib.metadata import version
    from pathlib import Path

    # The interpreter's own bin directory, and only there: the binary under test and the
    # metadata it is asserted against must come from one environment.
    bindir = str(Path(sys.executable).parent)
    exe = shutil.which("hiveprep", path=bindir)
    assert exe, "hiveprep console script is not installed in this environment"
    # check=False: the exit code is the assertion, and raising here would hide the
    # stderr that says which lookup failed. timeout: a regression must fail, not hang.
    r = subprocess.run([exe, "--version"], capture_output=True, text=True, check=False,
                       timeout=60)

    assert r.returncode == 0, f"hiveprep --version exited {r.returncode}: {r.stderr}"
    assert "Traceback" not in r.stderr, r.stderr
    assert version("vf-hive-prep") in r.stdout, r.stdout
