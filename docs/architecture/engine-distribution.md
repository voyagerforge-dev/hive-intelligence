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

Resolving that needs read access to this repository, which was private when the decision below was
taken. So every machine that builds the consumer needed a credential for the engine's **source**,
and in practice that meant one person's key against one host: the consumer built on a single
workstation, its CI never tried, and the deployed tree was placed by hand. Nothing announced any of
this. It looked like a normal dependency until someone else tried to build it.

A git pin has a second problem that outlives the credential and is the reason opening the
repository does not retire this decision: a tag is a repository plus a revision, so a consumer
pinning one is coupled to *where the engine lives*, not to *what it is*. A version on an index is
not.

A released artefact fixes the shape: a consumer pins a version, not a repository.

## What is released

Six distributions, from `tooling/`, as **one engine at one version**:

| package | distribution |
|---|---|
| `hive-gen` | `vf-hive-gen` |
| `hive-prep` | `vf-hive-prep` |
| `hive-serve` | `vf-hive-serve` |
| `hive-dbparse` | `vf-hive-dbparse` |
| `hive-zendesk` | `vf-hive-zendesk` |
| `hive-author` | `vf-hive-author` |

One version across all of them, because that is how they are consumed: a corpus is validated
against a specific distiller *and* a specific serving behaviour, so `v0.7.0` has to mean the same
six distributions every time. `tools/set-release-version.sh` writes it in one place and
`tools/build-release.sh` refuses to build a set that disagrees with itself.

`hive-author` **joined the set at 0.7.0**, and it is the one whose place needs explaining,
because it is still a *service* rather than a library. Nobody imports `hiveauthor`. What
changed is not what it is but where a deployment gets it from: a deployment installs
`vf-hive-author==<version>` and runs the `hiveauthor` console script it puts on the path,
exactly as it installs `vf-hive-serve` and runs `hiveserve`. Before that it was the one
component with no pin at all - built from a checkout of this repository, at whatever revision
that checkout happened to be on - which is the *same* defect as the git-tag pin described
above, surviving in the one place the fix had not reached. Being a service is a reason to run
it differently, not a reason to obtain it differently.

Being released does not make it something a consumer of the cards installs. It holds the only
credential in the system and files issues with it; a corpus pipeline has no use for it. What
installs it is a deployment - see [hive-author](../reference/hive-author.md) for what that
deployment has to configure, and [corrections and memory](../guides/corrections-and-memory.md)
for why the write door is a separate service at all.

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

**PyPI, wheels only, published by GitHub Actions with Trusted Publishing.**

> **The premise below has since changed, and the conclusion has not.** This was decided while the
> repository was private, and the question then was who may hold the artefact. The repository is now
> open, which settles that question in the same direction the decision already went: shape 1, a
> public artefact and no consumer credential. What is no longer true is the paragraph below about
> the rest of the repository staying private - it does not, and nothing in the release path depended
> on it. The record is kept as it was written, because the reasoning is what a future reader needs.

The finding that shaped the choice: **for pure Python, the artefact IS the source.** A wheel
built here contains the package's `.py` files verbatim - `unzip -l` any of them. So "ship
artefacts rather than source" is not a real distinction for these tools, and the question was
only who may hold the artefact. That leaves two shapes and no third:

1. the artefact is public, and no consumer needs a credential at all, or
2. the artefact is gated, and someone holds a secret that must be issued, rotated and handed on.

One candidate that looks like a third shape is not one. Attaching the artefacts to a **release on
a private repository** does not remove source access: reading a release through the GitHub API
requires the fine-grained token permission *Contents (read)*, which is the same permission that
permits cloning the source. There is no download-only release permission. That option moves the
credential rather than removing it.

Shape 1 was chosen. What that publishes is the packages' own modules and nothing else: a
wheel carries the package directory plus `LICENSE` and `NOTICE`. The git history, `docs/`,
`skills/`, the CI, every test suite, every `.env.example` and every deployment example are not in
any wheel - `hive-author` was outside them entirely until it joined the released set at 0.7.0, and
what it ships now is `hiveauthor/` and nothing beside it - not its `deploy/` example, not its
`.env.example`. That was framed at the time as keeping them private; with the repository open it
is simply the difference between what a consumer *installs* and what a reader can *browse*, and
the narrower artefact is still the right one. Sdists are deliberately not built: they would add
tests, lockfiles and a deployment example that buy a consumer nothing, and every file in a published
artefact is a file someone has to have audited.

Trusted Publishing means **no PyPI token exists anywhere**. PyPI verifies a short-lived OIDC
token minted by the release workflow for this repository; there is nothing to store, nothing to
rotate, and nothing for a future maintainer to inherit. Adding a `PYPI_API_TOKEN` secret would
undo the reason this design was chosen.

### Before the first publish of a new name

Trusted Publishing has to be told which workflow may claim each name, and for a project that does
not exist yet that is a **pending publisher**, registered once per distribution at
<https://pypi.org/manage/account/publishing/>. Owner `voyagerforge-dev`, repository
`hive-intelligence`, workflow `release.yml` for all of them - and **one environment each**:

| PyPI project name | GitHub environment |
|---|---|
| `vf-hive-gen` | `pypi-vf-hive-gen` |
| `vf-hive-prep` | `pypi-vf-hive-prep` |
| `vf-hive-serve` | `pypi-vf-hive-serve` |
| `vf-hive-dbparse` | `pypi-vf-hive-dbparse` |
| `vf-hive-zendesk` | `pypi-vf-hive-zendesk` |
| `vf-hive-author` | `pypi-vf-hive-author` |

These are exact strings, not a naming convention to re-derive. PyPI matches all four fields, and a
field that does not match is not an error message - it is a refused upload.

**One environment each is forced, not chosen.** PyPI treats owner + repository + workflow +
environment as one identity, so registering a second project against an identical configuration is
refused: *"A pending trusted publisher matching this configuration has already been registered for
a different project name."* Six names therefore need six environments, six GitHub environments
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
   version cut to carry those five;
4. `vf-hive-author` is the sixth, and repeats the same order at `0.7.0`: **its pending publisher
   and its `pypi-vf-hive-author` environment have to exist before the tag is pushed.** Its
   publish job is already in `release.yml` and `report` already expects it, so a tag pushed
   without them is a red run naming `vf-hive-author` - and a version that went out short of the
   set can never be completed.

The two missing distributions could not be added to the version that skipped them - PyPI never
allows a version to be re-uploaded - so step 3 is a new version number, not a re-run of the tag.
`0.5.0` stays on the index forever as a three-of-five release, and nothing a later run does
changes that. Of the three published at `0.5.0`, `vf-hive-gen` and `vf-hive-prep` are rebuilt at
`0.6.0` with nothing changed at all, while `vf-hive-serve`'s wheel differs from its `0.5.0` one in
recorded dependency metadata: its exact pin moved to `vf-hive-gen==0.6.0`, which is precisely why
the set has to move together. A further distribution repeats the same order: register its
publisher and create its environment first, then add its job, then cut a new version.

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
for n in vf-hive-gen vf-hive-prep vf-hive-serve vf-hive-dbparse vf-hive-zendesk vf-hive-author; do
  printf '%-18s ' "$n"; curl -s -o /dev/null -w '%{http_code}\n' "https://pypi.org/simple/$n/"
done      # 404 means the name is still free; 200 on one already published here is expected
```

Publication is **irreversible**: PyPI does not allow re-uploading a version, and yanking one does
not un-copy what mirrors and caches already took. Audit what is inside the wheels before tagging,
not after.

### Checking the publishers still match, without publishing

Neither side's settings page can answer whether PyPI will accept this repository: PyPI matches four
fields *and* the owner's numeric id against claims in a token that only a real run can mint. So
`release.yml` carries a dispatch-only `trusted-publisher-check` job that does the first half of
what `pypa/gh-action-pypi-publish` does - mints the OIDC token in each environment and
exchanges it at `https://pypi.org/_/oidc/mint-token` - and then stops and reports the HTTP status.
It downloads no artefact, checks nothing out, and never runs the publish action. `200` from every
one of them is the proof; a refusal prints the exact fields to re-register. Run it after
registering a new name, and before the tag that first publishes it: a pending publisher that does
not match is indistinguishable from one that does until something asks PyPI.

```
gh workflow run release.yml --ref <branch> -f trusted_publisher_check=true
```

That flag also skips `build`, and with it `install`, `publish` and `report`, so the run is the
check and nothing else. The job **must stay in `release.yml`**: the workflow file name is one of
the matched fields, carried in the token's `job_workflow_ref` claim, so the same steps in a sibling
workflow would be refused for the wrong reason.

Run it after anything that could have moved a matched field, and before a release that depends on
the answer. **Re-creating this repository is such a change**, and the first real use of the check:
`voyagerforge-dev/hive-intelligence` was deleted and re-created under the same name on 2026-09-05
to clear pre-rewrite pull-request refs, which changed the repository's numeric id while leaving all
four matched fields and the environment names as they were. PyPI accepted all five of the names
that existed then - it pins the **owner** id, not the repository id - so a same-named re-creation
does not invalidate a publisher. Renaming the repository, moving it to another owner, renaming
`release.yml` or renaming an environment each would.

## Cutting a version

```
tools/set-release-version.sh 0.7.0     # one version: pyprojects, the pins, every uv.lock
tools/build-release.sh                 # sync licences, verify, build wheels into dist/
tools/verify-clean-install.sh          # install and run them where no credential of ours exists
git commit -am "release: 0.7.0"
git tag -a v0.7.0 -m "0.7.0" && git push origin v0.7.0
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

- the released packages disagreeing on the version;
- a `uv.lock` still recording the previous one, which no wheel reads and nothing else
  would notice;
- `vf-hive-serve` not requiring `vf-hive-gen==<that version>`, which would let a consumer pinning
  one version resolve a different engine behind it - and `vf-hive-author` not pinning it either,
  which is the same defect one level quieter: it names `vf-hive-gen` only in its `dev` extra, but
  an extra is published metadata a consumer can ask for;
- a clean tree sitting on a tag that contradicts the packages;
- a built wheel whose recorded metadata, or whose licence files, are not what was asked for.

`tools/verify-clean-install.sh` is the part that matters most, because the failure being fixed is
a thing everyone believed worked. It builds a container with no SSH key, no git credentials, no
token, no checkout and no `ssh`, `git` or `gh` client to use one with - and refuses if it finds
any of them, so the retired git+SSH pin could not have been resolved there whatever this
repository's visibility. Then it installs the whole set from the built artefacts and reads pip's
own `--report` to name the URL each of them actually
resolved from - a check that reads the same before and after the names exist on PyPI. Then it runs
each one for real - DDL parsed into cards, atomic markdown validated, a card bundle resolved across
cross-links, `hive-author` building a submission that `hive-gen`'s own parsers read back, and
`hive-serve` answering over HTTP against a real Postgres ledger.
`.github/workflows/release.yml` runs the same smoke script on a GitHub runner, so a release that
only works on the machine that built it fails before it is tagged.

## What a consumer does

The `[tool.uv.sources]` git table goes away, and the packages become ordinary pinned
dependencies resolved from PyPI. Nothing else: no credential, no index configuration, no CI
secret.

```toml
dependencies = [
  "vf-hive-gen==0.7.0",
  "vf-hive-prep==0.7.0",
  "vf-hive-serve==0.7.0",
  "vf-hive-dbparse==0.7.0",
  "vf-hive-zendesk==0.7.0",
]
```

A corpus repository pins the pipeline packages. A **deployment** pins what it runs, which is
`vf-hive-serve` and, where it offers the write door, `vf-hive-author` at the same version - and
then runs the `hiveauthor` console script rather than a checkout it placed itself.

Pin a version whose release run went green: a run goes green only when every distribution
recorded a successful upload, so that is the signal the whole set went out, and a version that
really did carry only some of the set can never be completed afterwards. A red run is not the
mirror image of that - it says the run could not account for the set, not what reached the index.
PyPI answers that question, and only PyPI.

A consumer that pins a version instead of a tag no longer needs `git describe` to know which
engine it is running; `pip show vf-hive-serve` answers that from the installed artefact.
