"""The wrappers are in the wheel, and they run.

This asserts against a REAL wheel, built here, rather than against the source tree or the
installed development environment. That is the whole point of it: for six versions the
wrappers worked perfectly in a checkout and shipped in no artifact at all, because
`packages = ["hivegen"]` covered the library and `scripts/` sat outside it. Every test in
this suite passed throughout, because every one of them read the source tree. A consumer
who pinned `vf-hive-gen==0.6.0` got the library and had to find the command line on a host
somebody had seeded by hand.

So the three things checked here are the three that were not: the modules are inside the
built wheel, the wheel's own `entry_points.txt` declares a console script for each of them,
and each declared target resolves and prints its help when imported from the wheel's copy
and nothing else.
"""
from __future__ import annotations

import configparser
import os
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PACKAGE_ROOT / "hivegen" / "scripts"


def _console_script_name(module: str) -> str:
    """The command a module is published as. `hivegen-` prefixed, dashes for underscores.

    Pinned in a test because it is a published interface: the corpus workflows that stop
    reading these files off a host will call these names, and renaming one is a breaking
    change to them rather than a tidy-up here. The prefix is not decoration either - a
    console script lands on a shared PATH, and `index-generate` is not a name this project
    may claim.
    """
    return "hivegen-" + module.replace("_", "-")


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    """Build a real wheel, in process and offline.

    hatchling is called through its PEP 517 hook rather than through `python -m build` or
    `uv build`: both of those shell out and resolve a build environment from the network,
    and CI installs this package with plain pip and has no uv at all. hatchling is declared
    in the `dev` extra for exactly this, so a missing one is a broken environment and is
    reported as a failure - a skip here would restore the silence this file exists to end.
    """
    try:
        from hatchling.build import build_wheel
    except ImportError as exc:  # pragma: no cover - environment, not behaviour
        pytest.fail(f"hatchling is needed to build the wheel under test ({exc}). "
                    "It is declared in the `dev` extra: pip install -e '.[dev]'.")

    out = tmp_path_factory.mktemp("wheel")
    cwd = Path.cwd()
    os.chdir(PACKAGE_ROOT)  # hatchling reads pyproject.toml from the working directory
    try:
        name = build_wheel(str(out))
    finally:
        os.chdir(cwd)
    return out / name


@pytest.fixture(scope="module")
def declared(wheel: Path) -> dict[str, str]:
    """The wheel's own console_scripts table: command name -> "module:attr"."""
    with zipfile.ZipFile(wheel) as z:
        entries = [n for n in z.namelist() if n.endswith(".dist-info/entry_points.txt")]
        assert entries, f"{wheel.name} declares no entry points at all"
        parser = configparser.ConfigParser()
        parser.read_string(z.read(entries[0]).decode())
    return dict(parser["console_scripts"])


@pytest.fixture(scope="module")
def unpacked(wheel: Path, tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("unpacked")
    with zipfile.ZipFile(wheel) as z:
        z.extractall(root)
    return root


def _modules() -> list[str]:
    """The PUBLIC modules under `hivegen/scripts/`, each of which must be a command.

    A module whose name starts with an underscore is deliberately excluded: that is the
    convention for a private helper, which is expected to ship in the wheel with no command
    over it. `__init__.py` is excluded by the same rule rather than by a special case.
    """
    return sorted(p.stem for p in SCRIPTS_DIR.glob("*.py") if not p.stem.startswith("_"))


def _declared_in_pyproject() -> dict[str, str]:
    """`[project.scripts]`, read at collection time so each command is its own test case.

    The wheel is what every assertion below runs against; this is only the list of names to
    make cases from, and `test_the_declared_entry_point_resolves_and_prints_help` checks
    each one against the wheel's own table before resolving it.
    """
    with (PACKAGE_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["scripts"]


def test_there_are_wrapper_modules_to_check():
    """A glob that matches nothing would make every other test here vacuously true."""
    assert len(_modules()) >= 8, f"expected the eight published wrappers, found {_modules()}"


@pytest.mark.parametrize("module", _modules())
def test_the_wheel_carries_the_module(module: str, wheel: Path):
    with zipfile.ZipFile(wheel) as z:
        names = set(z.namelist())
    assert f"hivegen/scripts/{module}.py" in names, (
        f"hivegen/scripts/{module}.py is not in {wheel.name}; a consumer pinning this "
        "distribution cannot import it")


@pytest.mark.parametrize("module", _modules())
def test_the_wheel_declares_a_console_script_for_the_module(module: str, declared: dict[str, str]):
    name = _console_script_name(module)
    assert name in declared, (
        f"hivegen/scripts/{module}.py ships in the wheel with no command over it. Add "
        f'`{name} = "hivegen.scripts.{module}:main"` to [project.scripts].')
    assert declared[name] == f"hivegen.scripts.{module}:main"


def test_every_public_module_is_declared(declared: dict[str, str]):
    """One direction only: a public wrapper with no command over it ships unreachable.

    The reverse is NOT asserted here. Demanding that the wheel declare nothing beyond these
    modules would forbid a private helper module in `hivegen/scripts/`, which is a rule
    about package layout that this file has no business imposing. A declared command whose
    target is gone is caught instead by resolving each declared entry point below, where it
    fails as itself rather than as a set difference.
    """
    missing = sorted(m for m in _modules() if _console_script_name(m) not in declared)
    assert not missing, (
        f"public modules in hivegen/scripts/ with no command over them: {missing}. "
        "Declare each in [project.scripts], or rename it with a leading underscore if it "
        "is a private helper rather than a command.")


@pytest.fixture(scope="module")
def elsewhere(tmp_path_factory) -> Path:
    """An empty directory to run from.

    `python -c` puts the working directory first on sys.path, so running from the package
    root would import `hivegen/` out of the checkout and this file would be testing the
    source tree again - which is the exact failure it was written to catch. It also keeps
    the corpus profile out of the picture: `load_profile` looks in the working directory,
    and these modules read it at import.
    """
    return tmp_path_factory.mktemp("elsewhere")


@pytest.mark.parametrize("command", sorted(_declared_in_pyproject()))
def test_the_declared_entry_point_resolves_and_prints_help(command: str, declared: dict[str, str],
                                                           unpacked: Path, elsewhere: Path):
    """Import the target from the WHEEL's copy and run it, the way an installed console
    script does. The assertion on __file__ holds it to that: nothing here may resolve out of
    the checkout.

    Parametrized over what is DECLARED rather than over what is on disk, so a command left
    behind by a rename fails here, named, as an entry point that installs and then cannot
    import - which is exactly how a consumer would meet it.
    """
    assert command in declared, (
        f"{command} is in [project.scripts] but not in the built wheel's entry points")
    target, attr = declared[command].split(":")
    program = (f"import sys, {target} as m; print(m.__file__, file=sys.stderr); "
               f"sys.exit(m.{attr}(['--help']))")
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True, text=True, cwd=elsewhere, check=False,
        env={**os.environ, "PYTHONPATH": str(unpacked)},
    )
    assert proc.returncode == 0, f"{target}:{attr} --help failed:\n{proc.stderr}"
    assert str(unpacked) in proc.stderr, (
        f"{target} resolved outside the wheel; this test proved nothing:\n{proc.stderr}")
    assert proc.stdout.startswith(f"usage: {command}"), (
        f"{target}:{attr} printed no usage for its own command name:\n{proc.stdout}")
