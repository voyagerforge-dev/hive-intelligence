# The product and deployment boundary

This repository contains the Hive Intelligence product. It does not contain any deployment.

That distinction is enforced rather than aspirational, and it is what makes the repository useful to
anyone who is not us.

## The rule

**Product is what you could run. Deployment is how one particular installation runs it.**

A file belongs here if it would mean something on infrastructure we have never seen. A file that names
a host, an address, a domain, a mount path or a scheduler instance belongs to whoever operates that
installation, and lives in their infrastructure repository.

## What that means in practice

| In this repository | Not in this repository |
|---|---|
| `Dockerfile` | `compose.yml` bound to a host |
| `compose.example.yml` with neutral values | reverse-proxy and edge routing config |
| `.env.example` with documented keys | `.env` with real addresses |
| configuration **schema** and defaults | one installation's values |
| the packages under `tooling/` | schedulers, timers and cron |
| synthetic fixture corpus | any real corpus |

A `Dockerfile` is product. Without it you cannot run the software, so it ships here.

A `compose.yml` that binds a specific address and mounts specific paths describes one machine. It ships
with that machine.

## Corpus

The product ships **no knowledge cards** beyond the synthetic fixture corpus under
`tooling/hive-serve/tests/fixtures/corpus/`, which exists so the test suite can run and so a first
deployment has something to serve.

Real corpora are the property of whoever produced them. They live in their own repository, are mounted
at runtime, and are never vendored here. A deployment is a fork of this repository plus a corpus.

## Evaluation data

Evaluation question sets are corpus-specific: they name concepts and reference card ids that only exist
in one corpus. They are therefore deployment artifacts, not product, and live with the corpus they
measure.

The product ships the harness. It does not ship the questions.

## Why this is enforced

Three reasons, in increasing order of how much they cost when ignored.

1. Code that hardcodes an address is not portable, so the boundary and the ability to deploy for a
   customer are the same piece of work.
2. Publishing internal topology from a company that sells data boundaries is a poor advertisement.
3. Corpora contain client material. A boundary that depends on remembering to check is not a boundary.
