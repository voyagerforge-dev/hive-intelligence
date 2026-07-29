"""SQLite-backed objective ledger: per-owner stateful work streams over OKF cards."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

MODES = {"investigate", "implement", "learn"}
STATUSES = {"open", "active", "resolved", "done"}
KINDS = {"plan", "step", "finding", "decision", "quiz_result", "note"}
MEM_VISIBILITY = {"private", "promotion_requested"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id() -> str:
    return uuid.uuid4().hex


def connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


@contextmanager
def session(path):
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS objective (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, mode TEXT NOT NULL,
          goal TEXT NOT NULL, status TEXT NOT NULL,
          external_ref TEXT, visibility TEXT NOT NULL DEFAULT 'private',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS entry (
          id TEXT PRIMARY KEY,
          objective_id TEXT NOT NULL REFERENCES objective(id) ON DELETE CASCADE,
          kind TEXT NOT NULL, content TEXT NOT NULL,
          card_ids TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_obj_owner ON objective(owner);
        CREATE INDEX IF NOT EXISTS idx_entry_obj ON entry(objective_id);
        CREATE TABLE IF NOT EXISTS memory (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, text TEXT NOT NULL,
          client TEXT,
          tags TEXT NOT NULL DEFAULT '[]', card_ids TEXT NOT NULL DEFAULT '[]',
          external_ref TEXT, visibility TEXT NOT NULL DEFAULT 'private',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mem_owner ON memory(owner);
        """
    )
    conn.commit()


def _obj_row(r) -> dict:
    d = dict(r)
    d["external_ref"] = json.loads(d["external_ref"]) if d["external_ref"] else None
    return d


def _owned(conn, owner, objective_id):
    return conn.execute(
        "SELECT * FROM objective WHERE id=? AND owner=?", (objective_id, owner)
    ).fetchone()


def start_objective(conn, *, owner, mode, goal, external_ref=None) -> dict:
    if mode not in MODES:
        raise ValueError(f"bad mode: {mode}")
    oid, ts = _id(), _now()
    conn.execute(
        "INSERT INTO objective(id,owner,mode,goal,status,external_ref,visibility,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
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
    q, args = "SELECT * FROM objective WHERE owner=?", [owner]
    if status:
        q += " AND status=?"
        args.append(status)
    q += " ORDER BY updated_at DESC"
    return [_obj_row(r) for r in conn.execute(q, args).fetchall()]


def get_objective(conn, *, owner, objective_id) -> dict | None:
    row = _owned(conn, owner, objective_id)
    if row is None:
        return None
    out = _obj_row(row)
    out["entries"] = [
        {**dict(e), "card_ids": json.loads(e["card_ids"])}
        for e in conn.execute(
            "SELECT * FROM entry WHERE objective_id=? ORDER BY created_at, rowid", (objective_id,)
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
        "INSERT INTO entry(id,objective_id,kind,content,card_ids,created_at) VALUES(?,?,?,?,?,?)",
        (eid, objective_id, kind, content, json.dumps(card_ids or []), ts),
    )
    conn.execute("UPDATE objective SET updated_at=? WHERE id=?", (ts, objective_id))
    conn.commit()
    return {"id": eid, "objective_id": objective_id, "kind": kind,
            "content": content, "card_ids": card_ids or [], "created_at": ts}


def set_status(conn, *, owner, objective_id, status) -> dict | None:
    if status not in STATUSES:
        raise ValueError(f"bad status: {status}")
    if _owned(conn, owner, objective_id) is None:
        return None
    conn.execute("UPDATE objective SET status=?, updated_at=? WHERE id=? AND owner=?",
                 (status, _now(), objective_id, owner))
    conn.commit()
    return get_objective(conn, owner=owner, objective_id=objective_id)


def record_quiz_result(conn, *, owner, objective_id, concept_id, score, detail=None) -> dict | None:
    content = json.dumps({"concept_id": concept_id, "score": score, "detail": detail})
    return append_entry(conn, owner=owner, objective_id=objective_id,
                        kind="quiz_result", content=content, card_ids=[concept_id])


def _mem_row(r) -> dict:
    d = dict(r)
    d["tags"] = json.loads(d["tags"])
    d["card_ids"] = json.loads(d["card_ids"])
    d["external_ref"] = json.loads(d["external_ref"]) if d["external_ref"] else None
    return d


def remember(conn, *, owner, text, tags=None, card_ids=None, external_ref=None, client=None) -> dict:
    mid, ts = _id(), _now()
    conn.execute(
        "INSERT INTO memory(id,owner,text,client,tags,card_ids,external_ref,visibility,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (mid, owner, text, client, json.dumps(tags or []), json.dumps(card_ids or []),
         json.dumps(external_ref) if external_ref else None, "private", ts, ts),
    )
    conn.commit()
    mem = get_memory(conn, owner=owner, memory_id=mid)
    assert mem is not None  # just inserted above
    return mem


def get_memory(conn, *, owner, memory_id) -> dict | None:
    r = conn.execute("SELECT * FROM memory WHERE id=? AND owner=?", (memory_id, owner)).fetchone()
    return _mem_row(r) if r else None


def recall(conn, *, owner, query=None, tags=None, card_id=None, client=None, limit=20) -> list[dict]:
    rows = [_mem_row(r) for r in conn.execute(
        "SELECT * FROM memory WHERE owner=? ORDER BY updated_at DESC, rowid DESC", (owner,)).fetchall()]

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
    cur = conn.execute("DELETE FROM memory WHERE id=? AND owner=?", (memory_id, owner))
    conn.commit()
    return cur.rowcount > 0


def set_memory_visibility(conn, *, owner, memory_id, visibility) -> dict | None:
    if visibility not in MEM_VISIBILITY:
        raise ValueError(f"bad visibility: {visibility}")
    if get_memory(conn, owner=owner, memory_id=memory_id) is None:
        return None
    conn.execute("UPDATE memory SET visibility=?, updated_at=? WHERE id=? AND owner=?",
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
