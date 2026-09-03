# Distributing the engine

This repository is consumed by others. A corpus repository installs the tools to run its card
pipeline and its evaluation sets; a deployment installs `hive-serve` to serve them. How those
consumers *get* the tools is a product decision, and until now it was not one: they pinned a git
tag and resolved it from source.

## What was wrong with pinning the source

A consumer pinned each package at a git tag and a subdirectory:

```toml
[tool.uv.sources]
vf-hive-gen = { git = "ssh://…/hive-intelligence.git", tag = "v0.4.0", subdirectory = "tooling/hive-gen" }
```

Resolving that needs read access to this repository, which is private. So every machine that
builds the consumer needs a credential for the engine's **source**, and in practice that meant
one person's key against one host: the consumer built on a single workstation, its CI never tried,
and the deployed tree was placed by hand. Nothing announced any of this. It looked like a normal
dependency until someone else tried to build it.

A released artefact fixes the shape: a consumer pins a version, not a repository.

## What is released

Five distributions, from `tooling/`, as **one engine at one version**:

| package | distribution |
|---|---|
| `hive-gen` | `vf-hive-gen` |
| `hive-prep` | `vf-hive-prep` |
| `hive-serve` | `vf-hive-serve` |
| `hive-dbparse` | `vf-hive-dbparse` |
| `hive-zendesk` | `vf-hive-zendesk` |

One version across all five, because that is how they are consumed: a corpus is validated
against a specific distiller *and* a specific serving behaviour, so `v0.6.0` has to mean the same
five distributions every time. `tools/set-release-version.sh` writes it in one place and
`tools/build-release.sh` refuses to build a set that disagrees with itself.

`hive-author` is **not** released. It is a service that runs in a deployment, not a tool a
consumer installs, and nothing pins it.

Releasing a further distribution takes **two** edits, and the second is the one that matters.
`tools/released-packages.sh` is the only place the set is stated: the build, the clean-container
install, the index probe, the provenance check and the smoke run all derive it from there - the
shell scripts source it, and the harness passes the same names into the container as
`RELEASED_PACKAGES`, which `tools/released.py` reads. So the first edit is enough to get a new
distribution built, installed and version-checked, and `tools/build-release.sh` additionally
refuses a `dist/` holding anything that is not one of those wheels.

What does not follow is a step that puts it to work. `tools/smoke-installed.py` binds each step
to the distributions it exercises, and one that no step exercises makes the run exit non-zero
with `SMOKE INCOMPLETE`, which fails the install job that `publish` depends on. The second edit
is that step, and until it exists nothing new reaches PyPI.

## Where the artefacts go, and why

**PyPI, wheels only, published by GitHub Actions with Trusted Publishing. This repository stays
private.**

The finding that shaped the choice: **for pure Python, the artefact IS the source.** A wheel
built here contains the package's `.py` files verbatim - `unzip -l` any of them. So "ship
artefacts rather than source" is not a real distinction for these tools, and the question was
only who may hold the artefact. That leaves two shapes and no third:

1. the artefact is public, and no consumer needs a credential at all, or
2. the artefact is gated, and someone holds a secret that must be issued, rotated and handed on.

One candidate that looks like a third shape is not one. Attaching the artefacts to a **release on
this private repository** does not remove source access: reading a release through the GitHub API
requires the fine-grained token permission *Contents (read)*, which is the same permission that
permits cloning the source. There is no download-only release permission. That option moves the
credential rather than removing it.

Shape 1 was chosen. What that publishes is the five packages' own modules and nothing else: a
wheel carries the package directory plus `LICENSE` and `NOTICE`. The git history, `docs/`,
`skills/`, the CI, every test suite, every `.env.example` and the whole of `hive-author` stay
private, and a consumer sees **less** than it did when it resolved a git tag and got the entire
repository. Sdists are deliberately not built: they would add tests, lockfiles and a deployment
example that buy a consumer nothing, and every file in a published artefact is a file someone has
to have audited.

Trusted Publishing means **no PyPI token exists anywhere**. PyPI verifies a short-lived OIDC
token minted by the release workflow for this repository; there is nothing to store, nothing to
rotate, and nothing for a future maintainer to inherit. Adding a `PYPI_API_TOKEN` secret would
undo the reason this design was chosen.

### Before the first publish of a new name

Trusted Publishing has to be told which workflow may claim each name, and for a project that does
not exist yet that is a **pending publisher**, registered once per distribution at
<https://pypi.org/manage/account/publishing/>. Owner `voyagerforge-dev`, repository
`hive-intelligence`, workflow `release.yml` for all five - and **one environment each**:

| PyPI project name | GitHub environment |
|---|---|
| `vf-hive-gen` | `pypi-vf-hive-gen` |
| `vf-hive-prep` | `pypi-vf-hive-prep` |
| `vf-hive-serve` | `pypi-vf-hive-serve` |
| `vf-hive-dbparse` | `pypi-vf-hive-dbparse` |
| `vf-hive-zendesk` | `pypi-vf-hive-zendesk` |

These are exact strings, not a naming convention to re-derive. PyPI matches all four fields, and a
field that does not match is not an error message - it is a refused upload.

**One environment each is forced, not chosen.** PyPI treats owner + repository + workflow +
environment as one identity, so registering a second project against an identical configuration is
refused: *"A pending trusted publisher matching this configuration has already been registered for
a different project name."* Five names therefore need five environments, five GitHub environments
to match, and one publish job each in `release.yml`.

**And they cannot all be registered at once.** PyPI allows at most three publishers to be *pending*
simultaneously - *"You can't register more than 3 pending trusted publishers at once"* - and one
stops being pending only when its project has actually published something. So the first release
was deliberately a partial one, and the last two could only be registered once it had published:

1. `vf-hive-gen`, `vf-hive-prep` and `vf-hive-serve` were registered, with the three matching
   GitHub environments under *Settings > Environments* (that is also the only place a required
   reviewer can be added, and it gates one distribution, not the release);
2. `v0.5.0` was tagged. Those three published; `report` failed the run and named the two that
   did not;
3. those three publishers were then real rather than pending, so `vf-hive-dbparse` and
   `vf-hive-zendesk` were registered and their jobs added to `release.yml`. `0.6.0` is the
   version cut to carry all five.

The two missing distributions could not be added to the version that skipped them - PyPI never
allows a version to be re-uploaded - so step 3 is a new version number, not a re-run of the tag.
`0.5.0` stays on the index forever as a three-of-five release, and nothing a later run does
changes that. Of the three published at `0.5.0`, `vf-hive-gen` and `vf-hive-prep` are rebuilt at
`0.6.0` with nothing changed at all, while `vf-hive-serve`'s wheel differs from its `0.5.0` one in
recorded dependency metadata: its exact pin moved to `vf-hive-gen==0.6.0`, which is precisely why
the set has to move together. A sixth distribution repeats the same order: register its publisher
and create its environment first, then add its job, then cut a new version.

A pushed `v*` tag is the only thing that uploads anything. `report` does not gate that and cannot:
it runs after the publish jobs and has no way to undo an upload. So a red `report` does **not**
mean nothing was published. It means the run could not account for the whole set, and a version
that really is short of the set can never be completed afterwards.

What the per-distribution publish jobs and `report`'s table show is what the run *believes* went
out: a distribution counts as published only if its job recorded a successful upload, so a job
that died before recording one - a cancelled run, a dead runner - reads as not published even when
its wheel is already on the index. That direction is deliberate, because it sends a human to look
rather than claiming an upload nobody made, and it is why **PyPI itself is the authority on what
actually landed**. The two directions are not symmetric, and the asymmetry is the useful part: a
run can only go green when every distribution recorded its upload, so green is worth trusting,
while red says the run could not account for the set - not what is sitting on the index. Check the
index itself before believing a name is still free or a version unused.

A pending publisher **does not reserve the name** - if someone else registers it before the first
publish, the pending publisher is invalidated. So check the names still unclaimed are still free
immediately before tagging, not on yesterday's reading (a name this project has already published
answers 200, and that is the answer you want for it):

```
for n in vf-hive-gen vf-hive-prep vf-hive-serve vf-hive-dbparse vf-hive-zendesk; do
  printf '%-18s ' "$n"; curl -s -o /dev/null -w '%{http_code}\n' "https://pypi.org/simple/$n/"
done      # 404 means the name is still free; 200 on one already published here is expected
```

Publication is **irreversible**: PyPI does not allow re-uploading a version, and yanking one does
not un-copy what mirrors and caches already took. Audit what is inside the wheels before tagging,
not after.

## Cutting a version

```
tools/set-release-version.sh 0.6.0     # one version: pyprojects, the pin, every uv.lock
tools/build-release.sh                 # sync licences, verify, build wheels into dist/
tools/verify-clean-install.sh          # install and run them where no credential of ours exists
git commit -am "release: 0.6.0"
git tag -a v0.6.0 -m "0.6.0" && git push origin v0.6.0
```

Pushing the tag is what publishes, and it is the only thing that does.
`.github/workflows/release.yml` builds and installs on every trigger; each publish job requires a
`push` event AND a `refs/tags/v*` ref, and runs in that distribution's own environment, so a pull
request or a manual dispatch cannot reach PyPI however it is run. The event half of that guard is
not decoration: `workflow_dispatch` accepts a tag as its ref, so a ref-only test would publish from
`gh workflow run release.yml --ref v0.5.0`.

Each publish job uploads **one** wheel, staged into a directory of its own from the artefact the
`build` job made; an identity that may claim one name uploading the whole of `dist/` would collect
four rejections after the first wheel had already gone out and could not be recalled. The jobs are
independent (`fail-fast: false`), so one refused upload neither cancels nor invalidates another,
and what each one did is a separate green or red job on the run.

The `report` job is the one that must not be ignored. It compares `tools/released-packages.sh` -
the one place the released set is stated - against what this run recorded uploading, writes the
whole set as a table on the run summary, and **fails the run** whenever any distribution is
missing, whether because no publisher is registered for it yet or because its upload failed. A
partial release is therefore a red run naming the gap, never a green one that quietly shipped four
of five. It cannot be completed afterwards: register what was missing and cut a new version.

`tools/build-release.sh` refuses rather than producing a release that is quietly wrong:

- the five packages disagreeing on the version;
- a `uv.lock` still recording the previous one, which no wheel reads and nothing else
  would notice;
- `vf-hive-serve` not requiring `vf-hive-gen==<that version>`, which would let a consumer pinning
  one version resolve a different engine behind it;
- a clean tree sitting on a tag that contradicts the packages;
- a built wheel whose recorded metadata, or whose licence files, are not what was asked for.

`tools/verify-clean-install.sh` is the part that matters most, because the failure being fixed is
a thing everyone believed worked. It builds a container with no SSH key, no git credentials, no
token and no checkout, shows that the container cannot read this repository at all, installs the
five from the built artefacts, and reads pip's own `--report` to name the URL each of them actually
resolved from - a check that reads the same before and after the names exist on PyPI. Then it runs
each one for real - DDL parsed into cards, atomic markdown validated, a card bundle resolved across
cross-links, and `hive-serve` answering over HTTP against a real Postgres ledger.
`.github/workflows/release.yml` runs the same smoke script on a GitHub runner, so a release that
only works on the machine that built it fails before it is tagged.

## What a consumer does

The `[tool.uv.sources]` git table goes away, and the five packages become ordinary pinned
dependencies resolved from PyPI. Nothing else: no credential, no index configuration, no CI
secret.

```toml
dependencies = [
  "vf-hive-gen==0.6.0",
  "vf-hive-prep==0.6.0",
  "vf-hive-serve==0.6.0",
  "vf-hive-dbparse==0.6.0",
  "vf-hive-zendesk==0.6.0",
]
```

Pin a version whose release run went green: a run goes green only when every distribution
recorded a successful upload, so that is the signal the whole set went out, and a version that
really did carry only some of the set can never be completed afterwards. A red run is not the
mirror image of that - it says the run could not account for the set, not what reached the index.
PyPI answers that question, and only PyPI.

A consumer that pins a version instead of a tag no longer needs `git describe` to know which
engine it is running; `pip show vf-hive-serve` answers that from the installed artefact.
