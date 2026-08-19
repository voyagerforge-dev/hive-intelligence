"""Postgres-backed objective ledger: per-owner stateful work streams over OKF cards.

WHY POSTGRES, AND WHY NOT BOTH.

This was SQLite on a bind-mounted file until 2026-08-19. It moved for one reason: it is the
only mutable state this service holds, and a managed platform will back up a database it
manages and will not back up a file in a volume. Coolify, which is what EXAMPLECO's deployment is
heading for, schedules Postgres dumps to S3 and has no concept of "that SQLite file over
there". Being a database is what makes it get backed up.

There is deliberately NO dual-engine support. Keeping both would mean two placeholder styles
(`?` and `%s`) in one module, chosen at runtime, and the failure mode is a query that is
syntactically fine against the engine you tested and broken against the one you deployed.
That is the shape of nearly every silent failure in this estate.

The tests run against a real Postgres for the same reason: a suite that passes on a
different engine than production is a gate that scores nothing.
"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row

MODES = {"investigate", "implement", "learn"}
STATUSES = {"open", "active", "resolved", "done"}
KINDS = {"plan", "step", "finding", "decision", "quiz_result", "note"}
MEM_VISIBILITY = {"private", "promotion_requested"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id() -> str:
    return uuid.uuid4().hex


# Every statement, run one at a time. psycopg will happily execute a multi-statement string,
# but it reports a failure against the whole batch rather than the statement, which turns a
# typo in one index into "something in init_db broke".
SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS objective (
      id TEXT PRIMARY KEY, owner TEXT NOT NULL, mode TEXT NOT NULL,
      goal TEXT NOT NULL, status TEXT NOT NULL,
      external_ref TEXT, visibility TEXT NOT NULL DEFAULT 'private',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )
    """,
    # seq replaces SQLite's rowid. Two queries ordered by `rowid` as a tiebreaker for
    # equal timestamps, and Postgres has no rowid: without an explicit column the order of
    # two entries written in the same clock tick is whatever the planner returns, which is
    # stable in testing and not guaranteed. This is the one schema addition.
    """
    CREATE TABLE IF NOT EXISTS entry (
      id TEXT PRIMARY KEY,
      seq BIGSERIAL NOT NULL,
      objective_id TEXT NOT NULL REFERENCES objective(id) ON DELETE CASCADE,
      kind TEXT NOT NULL, content TEXT NOT NULL,
      card_ids TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory (
      id TEXT PRIMARY KEY,
      seq BIGSERIAL NOT NULL,
      owner TEXT NOT NULL, text TEXT NOT NULL,
      client TEXT,
      tags TEXT NOT NULL DEFAULT '[]', card_ids TEXT NOT NULL DEFAULT '[]',
      external_ref TEXT, visibility TEXT NOT NULL DEFAULT 'private',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_obj_owner ON objective(owner)",
    "CREATE INDEX IF NOT EXISTS idx_entry_obj ON entry(objective_id)",
    "CREATE INDEX IF NOT EXISTS idx_mem_owner ON memory(owner)",
)


def connect(dsn: str) -> psycopg.Connection:
    """Open a connection with dict rows and the schema present.

    dict_row is not cosmetic: every reader here does `dict(r)` and indexes by column name,
    which is what sqlite3.Row gave for free. The default tuple rows would fail at the first
    `d["external_ref"]` rather than at the query.
    """
    conn = psycopg.connect(dsn, row_factory=dict_row)
    init_db(conn)
    return conn


@contextmanager
def session(dsn: str):
    conn = connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn) -> None:
    for stmt in SCHEMA:
        conn.execute(stmt)
    conn.commit()


def _obj_row(r) -> dict:
    d = dict(r)
    d.pop("seq", None)
    d["external_ref"] = json.loads(d["external_ref"]) if d["external_ref"] else None
    return d


def _owned(conn, owner, objective_id):
    return conn.execute(
        "SELECT * FROM objective WHERE id=%s AND owner=%s", (objective_id, owner)
    ).fetchone()


def start_objective(conn, *, owner, mode, goal, external_ref=None) -> dict:
    if mode not in MODES:
        raise ValueError(f"bad mode: {mode}")
    oid, ts = _id(), _now()
    conn.execute(
        "INSERT INTO objective(id,owner,mode,goal,status,external_ref,visibility,created_at,updated_at)"
        " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (oid, owner, mode, goal, "open",
         json.dumps(external_ref) if external_ref else None, "private", ts, ts),
    )
    conn.commit()
    obj = get_objective(conn, owner=owner, objective_id=oid)
    assert obj is not None  # just inserted above
    return obj


def list_objectives(conn, *, owner, status=None) -> list[dict]:
    if status is not None and status not in STATUSES:
        raise ValueError(f"bad status: {status}")
    q, args = "SELECT * FROM objective WHERE owner=%s", [owner]
    if status:
        q += " AND status=%s"
        args.append(status)
    q += " ORDER BY updated_at DESC"
    return [_obj_row(r) for r in conn.execute(q, args).fetchall()]


def get_objective(conn, *, owner, objective_id) -> dict | None:
    row = _owned(conn, owner, objective_id)
    if row is None:
        return None
    out = _obj_row(row)
    out["entries"] = [
        {**{k: v for k, v in dict(e).items() if k != "seq"},
         "card_ids": json.loads(e["card_ids"])}
        for e in conn.execute(
            "SELECT * FROM entry WHERE objective_id=%s ORDER BY created_at, seq", (objective_id,)
        ).fetchall()
    ]
    return out


def append_entry(conn, *, owner, objective_id, kind, content, card_ids=None) -> dict | None:
    if kind not in KINDS:
        raise ValueError(f"bad kind: {kind}")
    if _owned(conn, owner, objective_id) is None:
        return None
    eid, ts = _id(), _now()
    conn.execute(
        "INSERT INTO entry(id,objective_id,kind,content,card_ids,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
        (eid, objective_id, kind, content, json.dumps(card_ids or []), ts),
    )
    conn.execute("UPDATE objective SET updated_at=%s WHERE id=%s", (ts, objective_id))
    conn.commit()
    return {"id": eid, "objective_id": objective_id, "kind": kind,
            "content": content, "card_ids": card_ids or [], "created_at": ts}


def set_status(conn, *, owner, objective_id, status) -> dict | None:
    if status not in STATUSES:
        raise ValueError(f"bad status: {status}")
    if _owned(conn, owner, objective_id) is None:
        return None
    conn.execute("UPDATE objective SET status=%s, updated_at=%s WHERE id=%s AND owner=%s",
                 (status, _now(), objective_id, owner))
    conn.commit()
    return get_objective(conn, owner=owner, objective_id=objective_id)


def record_quiz_result(conn, *, owner, objective_id, concept_id, score, detail=None) -> dict | None:
    content = json.dumps({"concept_id": concept_id, "score": score, "detail": detail})
    return append_entry(conn, owner=owner, objective_id=objective_id,
                        kind="quiz_result", content=content, card_ids=[concept_id])


def _mem_row(r) -> dict:
    # seq is an internal ordering column added with the Postgres port. It exists only to
    # replace SQLite's rowid as a tiebreaker and is not part of the API, so it is dropped
    # here rather than allowed to appear in every recall() result.
    d = dict(r)
    d.pop("seq", None)
    d["tags"] = json.loads(d["tags"])
    d["card_ids"] = json.loads(d["card_ids"])
    d["external_ref"] = json.loads(d["external_ref"]) if d["external_ref"] else None
    return d


def remember(conn, *, owner, text, tags=None, card_ids=None, external_ref=None, client=None) -> dict:
    mid, ts = _id(), _now()
    conn.execute(
        "INSERT INTO memory(id,owner,text,client,tags,card_ids,external_ref,visibility,created_at,updated_at)"
        " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (mid, owner, text, client, json.dumps(tags or []), json.dumps(card_ids or []),
         json.dumps(external_ref) if external_ref else None, "private", ts, ts),
    )
    conn.commit()
    mem = get_memory(conn, owner=owner, memory_id=mid)
    assert mem is not None  # just inserted above
    return mem


def get_memory(conn, *, owner, memory_id) -> dict | None:
    r = conn.execute("SELECT * FROM memory WHERE id=%s AND owner=%s", (memory_id, owner)).fetchone()
    return _mem_row(r) if r else None


def recall(conn, *, owner, query=None, tags=None, card_id=None, client=None, limit=20) -> list[dict]:
    rows = [_mem_row(r) for r in conn.execute(
        "SELECT * FROM memory WHERE owner=%s ORDER BY updated_at DESC, seq DESC", (owner,)).fetchall()]

    def match(m) -> bool:
        if client is not None and m["client"] != client:
            return False
        if card_id is not None and card_id not in m["card_ids"]:
            return False
        if tags and not set(tags) <= set(m["tags"]):
            return False
        if query:
            q = query.lower()
            hay = [m["text"].lower(), *(t.lower() for t in m["tags"])]
            if not any(q in h for h in hay):
                return False
        return True

    return [m for m in rows if match(m)][:limit]


def forget(conn, *, owner, memory_id) -> bool:
    cur = conn.execute("DELETE FROM memory WHERE id=%s AND owner=%s", (memory_id, owner))
    conn.commit()
    return cur.rowcount > 0


def set_memory_visibility(conn, *, owner, memory_id, visibility) -> dict | None:
    if visibility not in MEM_VISIBILITY:
        raise ValueError(f"bad visibility: {visibility}")
    if get_memory(conn, owner=owner, memory_id=memory_id) is None:
        return None
    conn.execute("UPDATE memory SET visibility=%s, updated_at=%s WHERE id=%s AND owner=%s",
                 (visibility, _now(), memory_id, owner))
    conn.commit()
    return get_memory(conn, owner=owner, memory_id=memory_id)


def promotion_record(memory: dict, owner: str) -> dict:
    """Build the neutral promotion record from a memory row (consumed by hivegen.memory in Phase 3c)."""
    return {
        "client": memory.get("client") or "",
        "product": "", "title": "",
        "memory": memory["text"], "context": "",
        "platform": "", "related": list(memory.get("card_ids", [])),
        "tags": list(memory.get("tags", [])), "citations": [], "supersedes": [],
        "external_ref": memory.get("external_ref"),
        "submitted_by": owner, "status": "approved",
    }


def promote_memory(conn, *, owner, memory_id) -> dict:
    """Guarded promotion prep: returns an error dict, or flips the row to
    promotion_requested and returns {memory_id, record}. Requires a client."""
    m = get_memory(conn, owner=owner, memory_id=memory_id)
    if m is None:
        return {"error": "not_found"}
    if not m.get("client"):
        return {"error": "client_required"}
    set_memory_visibility(conn, owner=owner, memory_id=memory_id, visibility="promotion_requested")
    return {"memory_id": memory_id, "record": promotion_record(m, owner)}
