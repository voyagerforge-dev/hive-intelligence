"""CLI orchestration: fetch -> gate -> scrub -> distil -> link -> emit -> verify.

`--dry-run` fetches and gates but never calls the LLM and never writes. That is how a
backfill is sized and costed before any money is spent.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import __version__
from .config import Settings
from .distill import distill
from .emit import write_card
from .fetch import ConnectorClient, to_ticket
from .gate import content_hash, keep
from .link import load_card_ids, resolve_related
from .llm import BifrostChat
from .model import RunError, RunReport
from .orgs import load_org_ids
from .scrub import known_values
from .state import load_state, replay_since, save_state
from .verify import verify_card, verify_run

log = logging.getLogger("okfzendesk")


def ingest(clients, org_ids, connector, llm, clients_dir, concepts_dir, state_dir,
           dry_run: bool = False, force: bool = False, limit: int | None = None) -> RunReport:
    report = RunReport()
    seen: set[str] = set()
    card_ids = load_card_ids(concepts_dir) if Path(concepts_dir).exists() else set()

    for client in clients:
        cursor = load_state(state_dir, client)
        new_cursor = dict(cursor)

        for org_id in org_ids[client]:
            since = replay_since(cursor.get(str(org_id)), None)
            rows = connector.list_closed(org_id=org_id, since=since)
            report.fetched += len(rows)
            newest = since

            for raw in rows[: limit or len(rows)]:
                detail = connector.get_ticket(int(raw["id"]))
                ticket = to_ticket(raw, client=client, comments=detail.get("comments") or [])
                newest = max(newest, ticket.closed_at or "")

                ok, reason = keep(ticket, seen)
                if not ok:
                    report.skipped += 1
                    report.skipped_reasons.append((ticket.id, reason))
                    continue
                seen.add(content_hash(ticket))

                if dry_run:
                    report.emitted += 1   # counted as "would emit"
                    continue

                known = known_values(ticket)
                card = distill(ticket, llm, known)
                if card is None:
                    report.skipped += 1
                    report.skipped_reasons.append((ticket.id, "distill-failed"))
                    continue

                card.related = resolve_related(card.related, card_ids)
                path, status = write_card(clients_dir, card, __version__, force=force)
                if status == "preserved":
                    report.preserved += 1
                else:
                    report.emitted += 1
                    verify_card(path.read_text(), card, known, card_ids)

            new_cursor[str(org_id)] = newest

        if not dry_run:
            save_state(state_dir, client, new_cursor)

    verify_run(report)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(prog="okfzendesk")
    ap.add_argument("mode", choices=["backfill", "incremental"])
    ap.add_argument("--client", action="append", required=True)
    ap.add_argument("--customers", required=True, help="path to customers.yaml")
    ap.add_argument("--clients-dir", required=True)
    ap.add_argument("--concepts-dir", required=True)
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    s = Settings()
    org_ids = load_org_ids(args.customers, args.client)
    connector = ConnectorClient(s.connector_base, s.connector_api_key,
                                s.connector_page_cap, s.cap_warn_ratio)
    llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.distill_model, s.bifrost_timeout_s)

    try:
        report = ingest(args.client, org_ids, connector, llm, args.clients_dir,
                        args.concepts_dir, args.state_dir, dry_run=args.dry_run,
                        force=args.force, limit=args.limit)
    except RunError as e:
        log.error("run failed: %s", e)
        return 1

    log.info("fetched=%d emitted=%d skipped=%d preserved=%d",
             report.fetched, report.emitted, report.skipped, report.preserved)
    for tid, reason in report.skipped_reasons[:20]:
        log.info("  skipped %s: %s", tid, reason)
    return 0
