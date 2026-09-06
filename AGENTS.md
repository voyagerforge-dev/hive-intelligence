# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

## What this repository is

The Hive **engine** only. The corpus (cards, taxonomies, eval sets, corpus profile) has lived in a
separate repository since the 2026-08-11 split, and consumers pin this one at a version - see
"Releasing it" for what a version means here and where it is recorded. Nothing here should read
or write a corpus path it was not given.

**A corpus path that is unset, empty, or not a directory must refuse with a message naming the
setting.** Never resolve it to something plausible instead. Deriving one by walking up from
`__file__` is the loudest version of that mistake - the arithmetic used to stay inside one tree and
now lands in this repository, where no cards or taxonomies exist - but empty and set-but-wrong fail
the same silent way, and more often. `Path("")` is `Path(".")`, which exists, so an unset setting
that reaches pathlib scans the working directory and answers out of this repository; a glob over a
directory that is not there yields nothing and raises nothing. Where a value is legitimately
optional (`CLIENTS_DIR` disables client memory), empty must mean *off* at the shared boundary, not
*the working directory*.

Corpus locations are settings (`CARD_CORPUS_ROOT` for hive-gen's card corpus output,
`CONCEPTS_DIR`, `CLIENTS_DIR`, `EVAL_DIR`), validated at the point of use, and an emptiness check
must count what the consumer counts. hive-prep's `CORPUS_ROOT` is the exception and not a
counter-example: nothing validates it because no command reads it for the raw tree, which comes from
the curation plan or the command argument. It is a corpus-profile lookup hint, read from the
environment, so it must be **exported** to have any effect at all. See
[docs/reference/configuration.md](docs/reference/configuration.md), section "Where the corpus is".
`__file__` arithmetic is still right for a package's own files.

The same rule covers `.env.example`: no absolute path under anyone's home directory. Those files
are what a new operator copies, and a dead path there is invisible until it produces nothing.

Before changing client handling, read [the serving trust boundary](docs/guides/serving-cards.md#identity-and-what-it-is-not)
and [the retrieval scope contract](docs/reference/hive-serve.md#the-resolver). Do not turn
caller-selected context into identity-bound authorization.

## Working on it

Each package under `tooling/` is its own distribution with its own venv, `pyproject.toml` and tests.
Where a package has settings, its `config.py` is the authority for them and its `.env.example` is
what an operator copies. `hive-dbparse` is the exception: no settings, no `config.py`, no
`.env.example` - it is configured entirely on the command line. Per package:
`uv sync --extra dev && uv run pytest`. Tests are colocated in `tests/` beside the package.

CI (`.github/workflows/fastapi-svcs.yml`) runs `ruff check .`, `mypy` and `pytest` for **every**
package whenever a PR touches any `.py`, so one package's backlog reddens everyone's PR. It runs
again on every push to `main`, where it never filters by changed paths - that run is what the
README's CI badge reports, so it has to mean the whole engine is green. Type
checking is opt-in per package (the workflow greps `pyproject.toml` for mypy) and all six declare
`[tool.mypy]`; a package added without it is skipped with a `::warning::`, not silently.
Both linters are installed at the JOB level, not from any package's dev extras, so
`uv sync --extra dev` does not give you either one - install them into the venv to check locally.
CI pins `ruff>=0.16,<0.17` while the packages' dev extras say `ruff>=0.7`: the locally resolved ruff
can disagree with CI in both directions, so check with the pinned range before claiming green.
`mypy` is unpinned (`>=1.10`), so a new release lands on all six packages at once.

CI runs `mypy` against the **package directory**, not the package root: `mypy hivegen`, never
`mypy .`. Running it the second way reports errors in `tests/` and `scripts/` that CI never sees,
so a local `mypy .` is not evidence of anything.

Every distribution is named `vf-hive-*` while the package it installs is `hive*`, so anything that
reads its own installed metadata must be told the **distribution** name: `hiveprep --version`
raised `PackageNotFoundError` in the published wheel for exactly this reason, because
`click.version_option()` looks the name up under the module. A CLI's `--version` is also the one
command a `CliRunner` test cannot vouch for - it resolves metadata that only an install has - so
test it by running the console script.

`hive-serve`'s ledger tests start a real Postgres container (docker or podman) and deliberately fail
rather than skip when they cannot. `hiveserve serve` itself also refuses to start without
`LEDGER_DSN`, on either transport, so any doc or script that runs it needs a database.

## Releasing it

Five distributions (`hive-author` is not one of them) ship as **one engine at one version**:
`tools/set-release-version.sh` writes that version everywhere it is recorded - the five
pyprojects, hive-serve's pin on hive-gen, and every `uv.lock` under `tooling/`, hive-author's
included because it pins hive-gen. `tools/build-release.sh` refuses a set that disagrees with
itself, a lockfile still on the previous version, or a wheel whose own metadata is wrong, and
`tools/verify-clean-install.sh` installs and runs the built artefacts in a container holding no
credential of ours. Run all three before believing a release works; a build nobody installed
elsewhere is the failure this path exists to end.

Publication is **PyPI, wheels only, Trusted Publishing, no token anywhere**, and it happens ONLY
from a pushed `v*` tag. It is irreversible - PyPI refuses a re-upload and a yank does not un-copy
what mirrors took - so audit what is inside the wheels before tagging, not after, and re-check
the names are still free immediately before. A new distribution name additionally needs a pending
publisher registered on PyPI first, in **its own GitHub environment**: a trusted publisher is
(owner, repository, workflow, environment), so distributions cannot share one, and only three may
be pending at a time. Whether PyPI still matches those four fields is answerable without
publishing anything - `gh workflow run release.yml --ref <branch> -f trusted_publisher_check=true`
exchanges one OIDC token per environment and reports the status - and that check has to stay in
`release.yml`, because the workflow file name is one of the four. A release can therefore
legitimately be partial; the workflow's `report` job fails the run and names what it could not
account for, and the gap is closed by a NEW version, never by re-running the tag.
[docs/architecture/engine-distribution.md](docs/architecture/engine-distribution.md) has all of
it, including why attaching artefacts to a GitHub release was not an option. That decision was
taken while this repository was private; it is now public, which does not change the release path
but does invalidate any statement that the source is not readable.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
