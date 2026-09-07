#!/usr/bin/env python3
"""Exercise the released Hive distributions as an INSTALLED consumer sees them.

This script is the answer to "does the release actually work somewhere other than the
machine that built it". It deliberately imports nothing from this repository: every step
below runs against packages resolved out of site-packages, and step 0 refuses if any of
them resolved to a source checkout instead. Run it from a directory that is not this
repository, in an environment that holds no credential for it.

    . tools/released-packages.sh && RELEASED_PACKAGES="${RELEASED_PACKAGES[*]}" \\
        python3 tools/smoke-installed.py --expect-version 0.5.0 --corpus /path/to/okf/corpus

`RELEASED_PACKAGES` names the distributions to check and is not optional: the set is stated
once, in tools/released-packages.sh, and everything on the release path derives it from there
rather than keeping a copy, so this script refuses instead of checking a set of its own.

`--corpus` is a directory holding `concepts/` and optionally `clients/` - an OKF card
corpus, which a consumer supplies and this repository does not contain. The synthetic
fixture corpus under tooling/hive-serve/tests/fixtures/corpus stands in for one.

Every step is a real operation with a real result: DDL parsed into cards, atomic markdown
validated, a card bundle resolved across cross-links, journal entries linked, a submission
written by the write door and read back by the parsers that receive it. A step the
supplied corpus cannot exercise is skipped by name, and the verdict printed at the end is
derived from the steps that ran rather than written in advance, so it cannot claim more than
the run did. A released distribution that no step exercised makes that verdict INCOMPLETE and
the exit code non-zero, so the gate above this one cannot pass on it either.

Nothing calls a model or a network service. The single stand-in is step 6's reranker, which
answers in the model's own JSON shape from the candidates the installed package shortlisted:
the lexical shortlist and the rewrite it drives are the real ones, so the links that step
asserts were derived here and not inherited from the fixture. Step 7 reaches no forge either:
it builds submissions and starts the server, and files nothing.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata as md
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from released import distributions

failures: list[str] = []


@dataclass
class Step:
    """One step of the proof, and which distributions it puts to work.

    `dists` is what a step EXERCISES, so the verdict can be computed from it. Step 0 lists
    none: it establishes that the released set is installed, which is not the same claim as
    having run it. This binding is the one thing that does NOT follow from
    tools/released-packages.sh - a step has to be written - so a distribution added there
    and nowhere else ends up in `unexercised()` and fails the run.
    """

    title: str
    dists: tuple[str, ...] = field(default_factory=tuple)
    skipped: str = ""


steps: list[Step] = []


def step(title: str, *dists: str) -> None:
    steps.append(Step(title, dists))
    print(f"\n=== {title}", flush=True)


def check(ok: bool, detail: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + detail, flush=True)
    if not ok:
        failures.append(detail)


def skip(reason: str) -> None:
    """A step the supplied corpus cannot exercise. Not a failure, and never silent."""
    steps[-1].skipped = reason
    print("  skip " + reason, flush=True)


def unexercised() -> list[str]:
    """Released distributions that no step which ran put to work.

    Non-empty means the proof did not cover what is about to be published, so it is a
    failure and not a remark: the caller exits non-zero on it.
    """
    exercised = {d for s in steps if not s.skipped for d in s.dists}
    return [d for d in distributions() if d not in exercised]


def verdict() -> str:
    """The one-line result, derived from what ran. No part of it is written in advance."""
    total = len(distributions())
    ran = [s for s in steps if not s.skipped]
    missed = unexercised()
    if failures:
        return f"SMOKE FAILED: {len(failures)} check(s) did not hold"
    if missed:
        was = "was" if len(missed) == 1 else "were"
        return (f"SMOKE INCOMPLETE: {len(ran)} of {len(steps)} steps ran, and "
                f"{', '.join(missed)} {was} never exercised")
    if len(ran) != len(steps):
        return (f"SMOKE PASSED, {len(steps) - len(ran)} step(s) skipped: all "
                f"{total} distributions exercised by the {len(ran)} that ran")
    return (f"SMOKE PASSED: {total} installed distributions, "
            f"{len(steps)} steps, every step a real run")


def run_cli(argv: list[str], **kw) -> subprocess.CompletedProcess:
    """Run an installed console script and echo it, so the transcript is the evidence.

    A bare name is resolved next to `sys.executable` first, so the run exercises the
    scripts THIS interpreter installed rather than whatever an inherited PATH happens to
    shadow them with. That distinction is the whole point of the exercise.
    """
    argv = list(argv)
    candidate = Path(sys.executable).parent / argv[0]
    if candidate.is_file():
        argv[0] = str(candidate)
    print("  $ " + " ".join(argv), flush=True)
    p = subprocess.run(argv, capture_output=True, text=True, check=False, **kw)
    for line in (p.stdout + p.stderr).splitlines():
        print("    | " + line, flush=True)
    return p


def step0_provenance(expect_version: str) -> None:
    step("0. the released distributions are installed, and not from a source tree")
    for dist, module in distributions().items():
        try:
            version = md.version(dist)
        except md.PackageNotFoundError:
            check(False, f"{dist} is not installed")
            continue
        try:
            mod = importlib.import_module(module)
        except ImportError as e:
            check(False, f"{dist} is installed but {module} does not import: {e}")
            continue
        path = Path(mod.__file__).resolve().parent
        check(version == expect_version, f"{dist} {version} (expected {expect_version})")
        # The whole point of the exercise: this must be an installed artefact. A module
        # resolved out of a checkout would make every step below prove nothing at all,
        # and an editable install is a checkout wearing site-packages as a disguise.
        check("site-packages" in path.parts, f"{module} imported from {path}")
        editable = False
        for f in md.distribution(dist).files or []:
            if f.name == "direct_url.json":
                info = json.loads(f.read_text())
                editable = bool(info.get("dir_info", {}).get("editable"))
                break
        check(not editable, f"{dist} is a built artefact, not an editable checkout")


def step1_dbparse(work: Path) -> None:
    step("1. hive-dbparse: Oracle + DB2 DDL -> OKF dbobject cards (deterministic, no model)",
         "vf-hive-dbparse")
    src = work / "ddl"
    (src / "Oracle/DBScripts/Product").mkdir(parents=True)
    (src / "DB2/DBScripts/Product").mkdir(parents=True)
    (src / "Oracle/DBScripts/Product/DOM.sql").write_text(
        'CREATE TABLE "SHIPMENT" ("ID" NUMBER(10,0), "STATUS" VARCHAR2(1), PRIMARY KEY ("ID"));\n'
        "comment on table SHIPMENT is 'one outbound shipment';\n"
        "comment on column SHIPMENT.STATUS is 'S once confirmed';\n"
    )
    (src / "DB2/DBScripts/Product/DOM.sql").write_text(
        'CREATE TABLE "SHIPMENT" ("ID" BIGINT, "STATUS" CHAR(1));\n'
    )
    out = work / "dbcards"
    p = run_cli(["hivedbparse", "--src", str(src), "--out", str(out)])
    check(p.returncode == 0, f"hivedbparse exited {p.returncode}")
    card = out / "tables/SHIPMENT.md"
    check(card.is_file(), f"emitted {card.name}")
    if card.is_file():
        text = card.read_text()
        check("one outbound shipment" in text, "the table comment reached the card")
        check((out / "manifest.jsonl").is_file(), "emitted manifest.jsonl")
        print("    --- card head ---", flush=True)
        for line in text.splitlines()[:12]:
            print("    | " + line, flush=True)


ATOMIC = """---
slug: {slug}
doc_type: {doc_type}
status: active
platform: demo
product: widget
version: "1.0"
related:{related}
---

# {title}

{body}
"""


def step2_prep(work: Path) -> None:
    step("2. hive-prep: validate an atomic-markdown corpus (slugs, enums, link targets)",
         "vf-hive-prep")
    atomic = work / "atomic"
    atomic.mkdir()
    (atomic / "picking-overview.md").write_text(ATOMIC.format(
        slug="picking-overview", doc_type="functional-flow", title="Picking overview",
        related="\n  - wave-release", body="How a wave becomes a pick."))
    (atomic / "wave-release.md").write_text(ATOMIC.format(
        slug="wave-release", doc_type="config-guide", title="Wave release",
        related=" []", body="Releasing a wave to the floor."))
    p = run_cli(["hiveprep", "validate-atomic", str(atomic),
                 "--relations-out", str(work / "relations.yaml")])
    check(p.returncode == 0, f"hiveprep validate-atomic exited {p.returncode}")
    check("0 errors" in p.stdout, "the corpus validated with no errors")
    check((work / "relations.yaml").is_file(), "derived relations.yaml")

    # And the refusal, which is load-bearing behaviour: an unset ATOMIC_DIR is Path("."),
    # a directory that exists, so an unguarded stamp pass silently reports 0 files changed.
    plan = work / "plan.yaml"
    plan.write_text("corpus_root: .\nmodules: []\n")
    env = {**os.environ, "ATOMIC_DIR": ""}
    p = run_cli(["hiveprep", "stamp", "--plan", str(plan)], env=env)
    check(p.returncode != 0, f"hiveprep stamp refused an unset ATOMIC_DIR (exit {p.returncode})")
    check("ATOMIC_DIR" in (p.stdout + p.stderr), "the refusal names the setting")


def step3_gen(work: Path) -> None:
    step("3. hive-gen: the OKF card model, and the corpus-root refusal",
         "vf-hive-gen", "vf-hive-serve")
    from hivegen.card import build_okf_card
    meta = {"okf_version": "0.1", "id": "widget/calibration-routine",
            "title": "Calibration routine", "type": "concept",
            "description": "How a widget is calibrated."}
    card = build_okf_card(meta, "Calibrate before the first pick of a shift.\n")
    check(card.startswith("---"), "build_okf_card emitted frontmatter")
    print("    --- card ---", flush=True)
    for line in card.splitlines()[:10]:
        print("    | " + line, flush=True)
    # The cross-package contract, checked across two separately built distributions:
    # what hive-gen writes is what hive-serve reads back.
    from hiveserve.resolver import parse_frontmatter
    check(parse_frontmatter(card) == meta,
          "hive-serve parses hive-gen's card back to the same frontmatter")

    # CARD_CORPUS_ROOT unset must refuse and name the setting. This was `parents[3]`
    # arithmetic until 2026-08-29, which pointed at the engine checkout after the corpus
    # became its own repository and proposed a taxonomy over a corpus it could not see.
    env = {k: v for k, v in os.environ.items() if k != "CARD_CORPUS_ROOT"}
    # The other required settings are supplied so the refusal under test is the corpus-root
    # one, not a settings-validation error that would pass this check for the wrong reason.
    env.update(CARD_CORPUS_ROOT="", BIFROST_BASE="http://unused.invalid/v1",
               BIFROST_API_KEY="unused")
    p = run_cli([sys.executable, "-m", "hivegen.run"], env=env, cwd=str(work))
    check(p.returncode != 0, f"hivegen refused an unset CARD_CORPUS_ROOT (exit {p.returncode})")
    check("CARD_CORPUS_ROOT" in (p.stdout + p.stderr), "the refusal names the setting")

    # The card wrappers, as COMMANDS. Everything above this proves the library; until 0.7.0
    # that was all the wheel carried, so a consumer who pinned the distribution still read
    # the command line off a tree somebody had seeded on a host by hand. The names come from
    # the installed metadata rather than a list written here, so a console script added to
    # pyproject.toml and never installed fails this rather than going unnoticed.
    commands = sorted(ep.name for ep in md.distribution("vf-hive-gen").entry_points
                      if ep.group == "console_scripts")
    check(len(commands) >= 8, f"vf-hive-gen installed {len(commands)} console script(s)")
    for name in commands:
        check((Path(sys.executable).parent / name).is_file(), f"{name} is on the path")

    # And one of them doing real work, because "the command exists" is a weaker claim than
    # the corpus workflows need from it.
    concepts = work / "concepts" / "widget"
    concepts.mkdir(parents=True)
    (concepts / "calibration-routine.md").write_text(card)
    p = run_cli(["hivegen-index-generate", str(work / "concepts")])
    check(p.returncode == 0, f"hivegen-index-generate exited {p.returncode}")
    check((work / "concepts" / "index.md").is_file(), "it wrote the root index.md")


def step4_serve(corpus: Path) -> None:
    step("4. hive-serve: no-RAG retrieval over a real corpus (index, then cross-link traversal)",
         "vf-hive-serve")
    from hiveserve.resolver import load_index, resolve
    from hiveserve.tools import find_concepts
    concepts, clients = corpus / "concepts", corpus / "clients"
    index = load_index(concepts, clients if clients.is_dir() else None)
    check(len(index) > 0, f"loaded {len(index)} cards from {concepts}")
    for c in index[:6]:
        print(f"    | {c['id']}  {c.get('title', '')}", flush=True)

    hits = find_concepts(concepts, "calibration", clients_dir=clients if clients.is_dir() else None)
    check(len(hits) > 0, f"find_concepts('calibration') matched {len(hits)} cards")
    for h in hits[:3]:
        print(f"    | {h['id']}", flush=True)

    if hits:
        bundle = resolve(concepts, [hits[0]["id"]], depth=1, max_cards=8,
                         clients_dir=clients if clients.is_dir() else None)
        check(bool(bundle), "resolve() returned a bundle")
        print(f"    | bundle: {json.dumps(bundle, default=str)[:200]}...", flush=True)


class StubReranker:
    """The rerank model's place in the linking pass, without a model.

    `relink` shortlists candidates lexically and asks a model which of them genuinely
    explain the incident. This replies with the first candidate it was offered, in the
    model's own JSON shape, so what surrounds it - the lexical shortlist and the rewrite -
    is the installed package doing its real work. A stand-in is what makes the step assert
    an outcome at all: with no model reachable the CLI retries a dead endpoint, links
    nothing, and still exits 0.
    """

    model = "smoke-stub-reranker"

    def complete(self, system: str, prompt: str) -> str:
        _, _, offered = prompt.partition("CANDIDATES:\n")
        ids = [line[2:].split(" :: ", 1)[0]
               for line in offered.splitlines() if line.startswith("- ")]
        return json.dumps({"picks": ids[:1]})


def step5_zendesk_refusal(work: Path, corpus: Path) -> None:
    step("5. hive-zendesk: the documented R2_BUCKET refusal, from the installed console script",
         "vf-hive-zendesk")
    # Separate from the linking step below, and deliberately: this needs no client data, so
    # it holds for every corpus, and hive-zendesk is exercised even by one that carries no
    # journal at all. `rebuild` refuses before it reads anything, because a bucket that is
    # not yours lists nothing and reads exactly like one with nothing staged in it.
    env = {**os.environ, "R2_BUCKET": "", "BIFROST_BASE": "http://unused.invalid/v1",
           "BIFROST_API_KEY": "unused"}
    p = run_cli(["hivezendesk", "rebuild", "--client", "any-client",
                 "--clients-dir", str(work / "clients"),
                 "--concepts-dir", str(corpus / "concepts")],
                env=env, cwd=str(work))
    check(p.returncode != 0, f"hivezendesk refused an unset R2_BUCKET (exit {p.returncode})")
    check("R2_BUCKET" in (p.stdout + p.stderr), "the refusal names the setting")


def step6_zendesk_relink(work: Path, corpus: Path) -> None:
    step("6. hive-zendesk: link client journal entries to concept cards (no model, no network)",
         "vf-hive-zendesk")
    clients = corpus / "clients"
    if not clients.is_dir():
        skip(f"{corpus} has no clients/, which a corpus supplies or does not")
        return
    import shutil

    from hivezendesk.fm import parse_frontmatter
    from hivezendesk.relink import clear_links, load_card_ids, relink_cards

    # relink rewrites the entries it links, so work on a copy rather than the input corpus.
    scratch = work / "journal"
    shutil.copytree(clients, scratch)
    names = sorted(q.name for q in scratch.iterdir() if q.is_dir())
    # Whichever client has a journal, not whichever sorts first: a corpus may carry a client
    # that has only memory/, and that is not a fault in the release being proved.
    journals = {name: sorted((scratch / name / "issues").glob("*.md")) for name in names}
    client = next((name for name in names if journals[name]), None)
    if client is None:
        skip(f"no client under {clients} carries journal entries (clients: {names})")
        return
    entries = journals[client]
    print(f"    | linking {client}: {len(entries)} journal entry file(s)", flush=True)

    # Retract the fixture's own links first, so a link found afterwards was derived by this
    # run rather than survived by it.
    for entry in entries:
        entry.write_text(clear_links(entry.read_text()))
    before = sum(len(parse_frontmatter(e.read_text()).get("related") or []) for e in entries)
    check(before == 0, f"{len(entries)} entr(y/ies) start with no links at all")

    report = relink_cards([client], scratch, corpus / "concepts", StubReranker())
    check(report.scanned == len(entries), f"relink scanned {report.scanned} of {len(entries)}")
    check(report.linked > 0,
          f"relink linked {report.linked} (declined {report.declined}, "
          f"no shortlist {report.no_shortlist})")

    card_ids = load_card_ids(corpus / "concepts")
    written = {e.name: parse_frontmatter(e.read_text()).get("related") or [] for e in entries}
    linked = {name: ids for name, ids in written.items() if ids}
    check(bool(linked), "at least one entry carries a related: link on disk afterwards")
    unknown = sorted({cid for ids in linked.values() for cid in ids} - card_ids)
    check(not unknown, f"every written link resolves to a card in the corpus (unknown: {unknown})")
    for name, ids in sorted(linked.items()):
        print(f"    | {name} -> {ids}", flush=True)


def step7_author(work: Path) -> None:
    step("7. hive-author: the write door - issue bodies hive-gen reads back, and the service",
         "vf-hive-author", "vf-hive-gen")
    from hiveauthor.submissions import build_correction_submission, build_memory_submission

    # The cross-package contract, checked across two separately built distributions, the same
    # way step 3 checks hive-gen against hive-serve. hive-author writes `### <label>` sections
    # that mirror the corpus repository's Issue Forms, and hive-gen's parsers are what read
    # them - whether the issue came from this service or from a person filling in the form. A
    # drift between the two is silent: the issue files, the workflow parses it into a card with
    # empty fields, and nobody sees the gap until the card is reviewed.
    from hivegen.scripts.correction_from_issue import parse_issue as parse_correction
    from hivegen.scripts.memory_from_issue import parse_issue as parse_memory

    memory = build_memory_submission(
        owner="operator@example.invalid", client="alpha", product="widget",
        title="Second scan", lesson="Alpha scans a second time before despatch.",
        context="Alpha only.", related=["widget/calibration-routine"],
        citations=["alpha-runbook.md"])
    check(memory["labels"] == ["hive-memory"], f"memory submission labelled {memory['labels']}")
    rec = parse_memory(memory["body"])
    check(rec["client"] == "alpha" and rec["product"] == "widget",
          f"hive-gen parsed it back as client={rec['client']!r} product={rec['product']!r}")
    check(rec["memory"] == "Alpha scans a second time before despatch.", "the lesson survived")
    check(rec["related"] == ["widget/calibration-routine"], f"related: {rec['related']}")
    check(rec["citations"] == ["alpha-runbook.md"], f"citations: {rec['citations']}")

    correction = build_correction_submission(
        owner="operator@example.invalid", target_concept_id="widget/calibration-routine",
        corrected_fact="Calibration is per shift, not per pick.",
        rationale="The bench guide says so.", citations=["bench-guide.md"])
    check(correction["labels"] == ["hive-correction"],
          f"correction submission labelled {correction['labels']}")
    rec = parse_correction(correction["body"])
    check(rec["corrects"] == "widget/calibration-routine", f"corrects: {rec['corrects']!r}")
    check(rec["correction"] == "Calibration is per shift, not per pick.", "the fact survived")

    # A memory promotion with no client is refused, not guessed at: a memory card with no
    # client is either a concept card or a mistake, and both deserve a rejection.
    try:
        build_memory_submission(owner="operator@example.invalid", client="", product="widget",
                                title="t", lesson="l")
        check(False, "a client-less memory promotion was accepted")
    except ValueError as e:
        check(True, f"a client-less memory promotion is refused ({e})")

    # The service, as a deployment runs it: the installed console script, and the ASGI app it
    # serves. `hiveauthor` unconfigured must refuse at startup rather than serve a client that
    # builds `/repos//issues` and 404s every submission while reporting success.
    env = {**os.environ, "FORGE_API": "", "FORGE_REPO": "", "FORGE_KIND": "",
           "FORGE_TOKEN": "", "FORGE_TOKEN_FILE": ""}
    p = run_cli(["hiveauthor"], env=env, cwd=str(work), timeout=120)
    check(p.returncode != 0, f"hiveauthor refused an unconfigured forge (exit {p.returncode})")
    check("forge_repo" in (p.stdout + p.stderr), "the refusal names the settings")

    # And configured, it answers. The forge is never reached: nothing below files an issue,
    # and the host does not resolve, so this is the server starting and serving, not a write.
    from fastapi.testclient import TestClient
    from hiveauthor.config import Settings
    from hiveauthor.server import build_http_app
    app = build_http_app(Settings(forge_api="http://forge.invalid/api/v1",
                                  forge_repo="example/corpus", forge_token="unused",
                                  forge_kind="forgejo"))
    with TestClient(app) as client:
        health = client.get("/healthz")
        check(health.status_code == 200 and health.json() == {"ok": True},
              f"GET /healthz -> {health.status_code} {health.text.strip()}")
        # Declared before the catch-all MCP mount at "/", or the mount shadows it and this
        # 404s while the deployment looks correctly configured.
        scrape = client.get("/metrics")
        check(scrape.status_code == 200 and "hive_author_submissions_total" in scrape.text,
              f"GET /metrics -> {scrape.status_code}, the write-door counters are exported")
        check(client.get("/mcp").status_code != 404, "the MCP door is mounted at /mcp")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--expect-version", required=True)
    ap.add_argument("--corpus", required=True, type=Path,
                    help="OKF card corpus: a directory holding concepts/ and optionally clients/")
    ap.add_argument("--verdict-out", type=Path,
                    help="write the derived one-line verdict here, for a harness that reports "
                         "what this run proved rather than asserting it a second time")
    args = ap.parse_args()

    corpus = args.corpus.resolve()
    if not (corpus / "concepts").is_dir():
        print(f"error: {corpus}/concepts is not a directory", file=sys.stderr)
        return 2

    print(f"python {sys.version.split()[0]}  ({sys.executable})")
    step0_provenance(args.expect_version)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        step1_dbparse(work)
        step2_prep(work)
        step3_gen(work)
        step4_serve(corpus)
        step5_zendesk_refusal(work, corpus)
        step6_zendesk_relink(work, corpus)
        step7_author(work)

    print()
    for s in steps:
        if s.skipped:
            print(f"  SKIPPED  {s.title}")
            print(f"           {s.skipped}")
    line = verdict()
    if args.verdict_out:
        args.verdict_out.write_text(line + "\n")
    # An incomplete run fails as loudly as a wrong one. Everything above this reads the exit
    # code and not the verdict, and a proof that did not cover a distribution must not be
    # able to satisfy the gate that guards an irreversible upload.
    if failures or unexercised():
        print(line, file=sys.stderr)
        for f in failures:
            print("  - " + f, file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
