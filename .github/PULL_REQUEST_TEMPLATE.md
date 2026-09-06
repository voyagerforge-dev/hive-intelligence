<!--
CONTRIBUTING.md is what this checklist comes from; it has the reasoning behind each line.
Delete anything that does not apply rather than leaving it unticked and unexplained.
-->

## What this changes, and why

<!-- The diff already says what. Say why: what was wrong, or what could not be done before. -->

## How it was verified

<!--
Which package, and what you ran. `cd tooling/<package> && uv sync --extra dev && uv run pytest -q`
is the usual answer. For a documentation change, say that you ran the commands you wrote down.
-->

## Checklist

- [ ] **One concern.** A fix and a refactor in one branch is two reviews wearing a trenchcoat.
- [ ] **A test that fails without this change**, for a bug fix. That test is the evidence the real
      cause was found rather than a plausible one.
- [ ] `ruff check .` passes from the package directory, with ruff from the range CI pins
      (`ruff>=0.16,<0.17`), not the much lower floor in the package's dev extra.
- [ ] **No version bump.** The five released distributions ship as one engine at one version, and
      `tools/set-release-version.sh` writes it everywhere. Changing a version by hand
      desynchronises the lockfiles and the build refuses it.
- [ ] **No corpus path, host, address or client name** is introduced anywhere, including in a
      `.env.example` or a test fixture.
- [ ] **Documentation updated in this pull request** if behaviour or a setting changed.
      [docs/reference/configuration.md](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/docs/reference/configuration.md) is where
      settings are described.

## Anything a reviewer should look at twice

<!-- Known gaps, decisions you were unsure about, follow-up you deliberately left out. -->
