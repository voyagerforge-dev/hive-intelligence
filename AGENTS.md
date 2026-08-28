# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

## What this repository is

The Hive **engine** only. The corpus (cards, taxonomies, eval sets, corpus profile) has lived in a
separate repository since the 2026-08-11 split, and consumers pin this one by annotated `vX.Y.Z`
git tag. Nothing here should read or write a corpus path it was not given.

**Never derive a corpus path by walking up from `__file__`.** That arithmetic used to stay inside
one tree and now lands in this repository, where no cards or taxonomies exist, and it fails
silently: a glob over a directory that is not there yields nothing and raises nothing. Corpus
locations are settings (`CORPUS_ROOT`, `CONCEPTS_DIR`, `CLIENTS_DIR`, `EVAL_DIR`), validated at the
point of use. See [docs/reference/configuration.md](docs/reference/configuration.md), section
"Where the corpus is". `__file__` arithmetic is still right for a package's own files.

The same rule covers `.env.example`: no absolute path under anyone's home directory. Those files
are what a new operator copies, and a dead path there is invisible until it produces nothing.

## Working on it

Each package under `tooling/` is its own distribution with its own venv, `.env.example`, tests and
`config.py` (the authority for its settings). Per package: `uv sync --extra dev && uv run pytest`.
Tests are colocated in `tests/` beside the package.

CI (`.github/workflows/fastapi-svcs.yml`) runs `ruff check .`, opt-in `mypy`, and `pytest` for
**every** package whenever a PR touches any `.py`, so one package's backlog reddens everyone's PR.
CI pins `ruff>=0.16,<0.17` while the packages' dev extras say `ruff>=0.7`: the locally resolved ruff
can disagree with CI in both directions, so check with the pinned range before claiming green.

`hive-serve`'s ledger tests start a real Postgres container (docker or podman) and deliberately fail
rather than skip when they cannot.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
