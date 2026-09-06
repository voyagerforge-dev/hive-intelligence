# Contributing to Hive

Thanks for looking. Hive is free software under [Apache 2.0](LICENSE), and patches from people
running it themselves are the ones that tend to find the real problems.

This repository is the **engine** only. It contains no corpus and no deployment, and both
omissions are load-bearing - [the README](README.md#what-this-repository-is-not) says why. If your
change makes the engine assume a corpus lives at a particular path, it is the wrong change.

[AGENTS.md](AGENTS.md) is the short, authoritative note on how this repository is built, tested and
released, and on the sharp edges (corpus paths, the ruff pin, the ledger tests). It is written for
whoever is next in the code, human or otherwise. Read it before a first pull request; this file
does not repeat it.

Participation here is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Opening an issue

Two forms, and GitHub will offer them:
[a bug report](.github/ISSUE_TEMPLATE/bug_report.yml) and
[a feature request](.github/ISSUE_TEMPLATE/feature_request.yml). Neither is mandatory - a blank
issue is still accepted - but they ask for the things that otherwise cost a round trip.

**Never open a public issue for a security problem**; [SECURITY.md](SECURITY.md) has the private
route. And please do not attach a corpus, customer data or a credential to any issue: describe the
shape instead, and the synthetic fixtures under `tooling/hive-serve/tests/fixtures/corpus/` are
usually enough to reproduce against.

## Getting set up

You need **Python 3.12 or newer**, [**uv**](https://docs.astral.sh/uv/), and - only for
`hive-serve`'s ledger tests - **docker or podman**.

Six packages live under `tooling/`, and each one is a separate distribution with its own venv and
dependencies. There is no root-level install. Work in the package you are changing:

```
cd tooling/hive-serve        # or hive-prep, hive-gen, hive-author, hive-dbparse, hive-zendesk
uv sync --extra dev
uv run pytest -q
```

Tests are colocated in `tests/` beside the package. For how settings are laid out per package, and
the rules a `.env.example` has to keep, see [AGENTS.md](AGENTS.md).

Some assertions depend on a live corpus, on its evaluation datasets, or on the GitHub
card-submission surface. Those skip with a stated reason when their subject is absent, and in this
repository they are expected to skip. `hive-serve`'s ledger tests are the exception: they start a
real Postgres container and **fail rather than skip** when they cannot, because a skipped ledger
test reports green. Point `HIVE_LEDGER_TEST_DSN` at an existing database if you would rather not
run a container.

## Lint and types

```
pip install "ruff>=0.16,<0.17"   # the range CI uses
ruff check .                     # from the package directory
```

Install ruff from that range rather than from the package's `dev` extra, which floors much lower.
A newer minor of ruff turns on new default rules, so a version outside the pinned range can
disagree with CI in either direction and you will not find out until the pull request is open.

Type checking is opt-in per package: CI runs `mypy` for a package that mentions it in its own
`pyproject.toml`, and skips the rest. Each package supplies its own ruff and mypy configuration
there too.

## What CI does to your pull request

[`.github/workflows/fastapi-svcs.yml`](.github/workflows/fastapi-svcs.yml) runs on **every** pull
request and reports a single aggregate check, `ci-ok`. When the pull request touches a `.py` file,
a `tests/` directory, a `pyproject.toml`, a `Dockerfile`, or that workflow, it lints, type-checks
and tests **every** package - so one package's backlog can redden a pull request that never touched
it. A docs-only pull request runs the same workflow but skips the matrix, which costs seconds and
still reports `ci-ok`.

[`release.yml`](.github/workflows/release.yml) also runs on pull requests that touch packaging
(`tooling/*/pyproject.toml`, `tools/**`, `LICENSE`, `NOTICE`), where it builds the wheels and
installs them somewhere clean. It never publishes anything from a pull request.

Please get CI green before asking for a look.

## What a good pull request looks like here

- **One concern.** A fix and a refactor in one branch is two reviews wearing a trenchcoat.
- **A test that fails without your change.** Especially for a bug: the test is the evidence that
  you found the real cause rather than a plausible one.
- **A commit message and description that say why**, not what. The diff already says what. This
  codebase comments the reason a thing is the way it is, and the history is expected to do the
  same.
- **No version bumps.** The five released distributions ship as one engine at one version, and
  `tools/set-release-version.sh` writes it everywhere it is recorded. Changing a version by hand
  desynchronises the lockfiles and the build refuses it. Releases are a maintainer action, made
  from a pushed `v*` tag; see
  [docs/architecture/engine-distribution.md](docs/architecture/engine-distribution.md).
- **Documentation in the same pull request** when behaviour or a setting changes.
  [docs/reference/configuration.md](docs/reference/configuration.md) is where settings are
  described.

[The pull request template](.github/PULL_REQUEST_TEMPLATE.md) is this list as a checklist, and
GitHub fills it in for you.

Big changes go better as an issue first, describing the problem before the solution. That is a
suggestion, not a gate.

## Review

Hive is maintained by a small team who also implement it for customers, so there is no promised
review turnaround and no formal governance to point you at. Pull requests are read, and a stale one
is our fault rather than a verdict - a nudge on the thread is welcome.

## Releases

You do not cut one, but it is worth knowing what a version means here: the five published
distributions ship as one engine at one version.

**Do not add a changelog entry to a pull request, and do not add a changelog file.** There is no
changelog in this repository on purpose - a hand-maintained one rots, and nothing here generates
one. The annotated tag is the record: `tools/set-release-version.sh` stamps the version, the tag
message written at release time says what changed, and it surfaces on
[the releases page](https://github.com/voyagerforge-dev/hive-intelligence/releases). Put the "why"
in your commit message instead, where it is already expected.

## Licensing

By opening a pull request you offer your contribution under the
[Apache License 2.0](LICENSE), the same terms as the rest of the repository. There is no separate
contributor licence agreement to sign.

## Security

Please do not report a vulnerability in a pull request or a public issue. [SECURITY.md](SECURITY.md)
has the private route.
