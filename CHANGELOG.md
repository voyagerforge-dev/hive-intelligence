# Changelog

The five released distributions (`vf-hive-prep`, `vf-hive-gen`, `vf-hive-serve`, `vf-hive-dbparse`,
`vf-hive-zendesk`) ship as **one engine at one version**, so there is one list here rather than five.
`hive-author` is versioned separately and is not published to PyPI; see
[docs/architecture/engine-distribution.md](docs/architecture/engine-distribution.md) for why.

**Where the record lives.** The annotated git tags `v0.1.0` to `v0.6.0` are the record, and this file
mirrors them. There are no GitHub Releases: publication happens from a pushed `v*` tag, and the tag
message written at that moment is the thing that was true. `git show v0.6.0` is always the primary
source; if this file and a tag disagree, the tag wins.

Versions from `v0.5.0` are on PyPI. Earlier ones were tagged before publication existed and are
reachable only from this repository.

Dates are the tag dates. This project does not follow strict semantic versioning: a minor version
has carried a breaking change for deployers where the alternative was leaving a silent failure in
place, and each such entry says so.

---

## [0.6.0] - 2026-09-04

**All five engine distributions published.** `vf-hive-dbparse` and `vf-hive-zendesk` joined the
three published at 0.5.0, each with its own PyPI trusted publisher in its own GitHub environment,
because a trusted publisher is the tuple (owner, repository, workflow, environment) and two
distributions cannot share one.

## [0.5.0] - 2026-09-03

**First published release.** `vf-hive-prep`, `vf-hive-gen` and `vf-hive-serve` reached PyPI as
wheels, over Trusted Publishing, with no API token stored anywhere.

Packaging work behind it: `tools/set-release-version.sh` writes the version everywhere it is
recorded, `tools/build-release.sh` refuses a set that disagrees with itself, and
`tools/verify-clean-install.sh` installs and runs the built artefacts in a container holding none of
our credentials.

The R2 settings (`R2_ENDPOINT`, `R2_BUCKET`, `R2_PREFIX`) lost their defaults in this cycle. Two of
them named a real private bucket and a real prefix inside it, which the published wheels would have
disclosed to everyone who installed them. Object storage makes the silent-fallback version worse
than a filesystem does: a listing against a bucket you cannot see returns an empty list, not an
error.

## [0.4.0] - 2026-08-29

**Corpus paths refuse rather than resolve to nothing.**

Four places derived a corpus path from the engine tree, or accepted an unset, empty or wrong path,
and then silently found nothing:

- `hive-gen` `run.py` resolved the corpus to the engine root, so gate 1 never saw an approved
  taxonomy and every run re-proposed instead of distilling.
- `hive-gen` `retopic.py` globbed a non-existent atomic directory and reported zero documents
  re-topiced, exit 0.
- `hive-serve` `run_eval.py` could not find the cards or the eval sets, and scored client-scoped
  rows as misses against an index built without them.
- `hive-prep` `.env.example` started a new operator from two paths that do not exist.

**Behaviour change.** These now refuse with a message naming the setting rather than proceeding over
an empty result. A caller that relied on a silent zero sees an error.

The strongest case found: a mistyped `ATOMIC_DIR` loaded zero documents, and the taxonomy prompt
then fabricated a taxonomy from an empty inventory and persisted it.

## [0.3.0] - 2026-08-19

**The `hive-serve` ledger is Postgres.** Moved off a SQLite file in a bind mount so a managed
platform can back it up: such a platform schedules Postgres dumps to object storage and has no
concept of a file in a volume. Being a database is what makes it get backed up.

**Breaking for deployers.** `LEDGER_DSN` replaces `LEDGER_DIR` and has no default. `hive-serve`
refuses to start without it rather than creating an empty ledger and serving it as if it were real.
The deploy example carries a `ledger-db` service; point `LEDGER_DSN` at a platform-managed Postgres
instead if you have one.

**Existing data must be migrated. There is no automatic conversion.**

The test suite moved with it and now starts a real Postgres container, failing rather than skipping
when it cannot: a suite that passes on a different engine than production is a gate that scores
nothing.

## [0.2.0] - 2026-08-15

**`hive-author` files issues on GitHub as well as Forgejo.** One field forces two clients: GitHub's
`labels` takes names, Forgejo's takes integer IDs and answers a name with 422. `FORGE_KIND` selects
between them and is refused at startup rather than at the first submission.

`FORGE_TOKEN_FILE` was added because a GitHub App installation token lasts an hour while the server
runs for days, so the token is read per request rather than once at startup.

## [0.1.1] - 2026-08-12

`hive-author` files issues on Forgejo. `forge_*` settings, and a startup guard on them.

## [0.1.0] - 2026-08-11

**First tagged release of the engine**, and the first version anything could pin.

Hive had been consumed as a fork until this point, so nothing ever needed a version. The corpus
split on 2026-08-11 made the engine a dependency, and a pin to a moving branch is not a pin.

Contents: the six `hive-*` packages, the agent skills, the product documentation and the synthetic
fixture corpus. No corpus and no deployment, per
[docs/architecture/product-deployment-boundary.md](docs/architecture/product-deployment-boundary.md).

---

[0.6.0]: https://github.com/voyagerforge-dev/hive-intelligence/releases/tag/v0.6.0
[0.5.0]: https://github.com/voyagerforge-dev/hive-intelligence/releases/tag/v0.5.0
[0.4.0]: https://github.com/voyagerforge-dev/hive-intelligence/releases/tag/v0.4.0
[0.3.0]: https://github.com/voyagerforge-dev/hive-intelligence/releases/tag/v0.3.0
[0.2.0]: https://github.com/voyagerforge-dev/hive-intelligence/releases/tag/v0.2.0
[0.1.1]: https://github.com/voyagerforge-dev/hive-intelligence/releases/tag/v0.1.1
[0.1.0]: https://github.com/voyagerforge-dev/hive-intelligence/releases/tag/v0.1.0
