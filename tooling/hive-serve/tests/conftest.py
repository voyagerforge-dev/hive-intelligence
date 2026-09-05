"""Shared fixtures for hive-serve tests.

Two groups. The single-card app scaffold (write a card, build the full HTTP app, open a
TestClient with lifespan) was duplicated across test_metrics.py and test_server_http.py and
lives here. The Postgres ledger fixtures were added with the SQLite-to-Postgres port on
2026-08-19.

WHY A REAL POSTGRES, AND WHY IT IS NOT SKIPPED.

The ledger is Postgres in production. Keeping the tests on SQLite would have been easy and
would have made them worthless: a suite that passes on a different engine than production is
a gate that scores nothing.

Skipping when no database is available is the same failure wearing a different hat, because
a skipped test reports green. So this starts a throwaway container, and if it cannot, it
FAILS with what to do about it.

Set HIVE_LEDGER_TEST_DSN to point at your own Postgres and no container is started.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from hiveserve.config import Settings
from hiveserve.server import build_http_app

CARD = "---\ntitle: Wave Replen\ndescription: replen feeds waves\nrelated: []\nsources: [widgets.md]\n---\nBody.\n"

IMAGE = "docker.io/library/postgres:16-alpine"
PORT = 55433


def _runtime() -> str:
    for cmd in ("docker", "podman"):
        if shutil.which(cmd):
            return cmd
    pytest.fail(
        "The ledger tests need a Postgres. Neither docker nor podman is on PATH.\n"
        "Install one, or set HIVE_LEDGER_TEST_DSN to an existing database.\n"
        "These are deliberately not skipped: a skipped ledger test reports green."
    )


@pytest.fixture(scope="session")
def ledger_dsn():
    dsn = os.environ.get("HIVE_LEDGER_TEST_DSN")
    if dsn:
        yield dsn
        return

    rt = _runtime()
    name = f"hiveserve-test-pg-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [rt, "run", "-d", "--rm", "--name", name,
         "-e", "POSTGRES_PASSWORD=test", "-e", "POSTGRES_USER=test", "-e", "POSTGRES_DB=test",
         "-p", f"{PORT}:5432", IMAGE],
        check=True, capture_output=True,
    )
    dsn = f"postgresql://test:test@127.0.0.1:{PORT}/test"
    try:
        # Wait on the DSN the tests use, not on pg_isready inside the container. The image's
        # entrypoint runs a temporary bootstrap server with listen_addresses='' during initdb:
        # pg_isready answers over the unix socket and reports READY while the published port
        # still refuses, so a probe there returns green ~0.5s before any test can connect and
        # the whole ledger suite errors with "server closed the connection unexpectedly".
        for _ in range(60):
            try:
                psycopg.connect(dsn, connect_timeout=2).close()
                break
            except psycopg.OperationalError:
                time.sleep(1)
        else:
            pytest.fail(f"Postgres in {name} never became ready.")
        yield dsn
    finally:
        subprocess.run([rt, "rm", "-f", name], capture_output=True, check=False)


@pytest.fixture
def clean_ledger(ledger_dsn):
    """The DSN, with every ledger table empty.

    The Postgres container is session-scoped for speed, so rows survive between tests
    unless something removes them. Any test that asserts a COUNT must take this rather
    than ledger_dsn, or it passes alone and fails in a suite.

    TRUNCATE ... CASCADE rather than dropping the database: recreating a database per test
    costs more than the tests do, and this gives the same isolation.
    """
    from hiveserve import ledger

    c = ledger.connect(ledger_dsn)
    try:
        c.execute("TRUNCATE objective, entry, memory RESTART IDENTITY CASCADE")
        c.commit()
    finally:
        c.close()
    return ledger_dsn


@pytest.fixture
def conn(clean_ledger):
    """An open connection to an empty ledger."""
    from hiveserve import ledger

    c = ledger.connect(clean_ledger)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def card_settings(tmp_path, clean_ledger):
    """Settings over a tmp corpus holding one card (id `wave-replen`)."""
    (tmp_path / "wave-replen.md").write_text(CARD)
    return Settings(concepts_dir=str(tmp_path), okf_data_dir=str(tmp_path),
                    ledger_dsn=clean_ledger)


@pytest.fixture
def card_client(card_settings):
    """TestClient over the full HTTP app (lifespan running) for the card corpus."""
    with TestClient(build_http_app(card_settings)) as client:
        yield client
