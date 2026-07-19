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
from .emit import card_dir, render, write_card
from .fetch import ConnectorClient, to_ticket
from .gate import content_hash, keep
from .link import load_card_ids, resolve_related
from .llm import BifrostChat
from .model import RunError, RunReport
from .orgs import load_org_ids
from .scrub import known_values, leaks
from .state import load_state, replay_since, save_state
from .verify import verify_card, verify_run

log = logging.getLogger("okfzendesk")


def already_carded(clients_dir, client: str, ticket_id: int) -> bool:
    d = card_dir(clients_dir, client)
    return d.exists() and any(d.glob(f"{ticket_id}-*.md"))


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
            # Apply the sampling limit BEFORE counting, so `fetched` reflects what was
            # actually processed and the reconciliation gate still holds. Counting the
            # full list here would make --limit always fail verification.
            if limit:
                rows = rows[:limit]
            report.fetched += len(rows)
            newest = since

            for raw in rows:
                ticket_id = int(raw["id"])
                newest = max(newest, raw.get("updated_at") or "")

                # Closed tickets are immutable, so a ticket already carded is never
                # re-fetched and never re-distilled. This is what makes the replayed
                # window cheap: without it every replay re-spends on the whole window.
                if not force and already_carded(clients_dir, client, ticket_id):
                    report.cached += 1
                    continue

                try:
                    detail = connector.get_ticket(ticket_id)
                    ticket = to_ticket(raw, client=client, comments=detail.get("comments") or [])

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

                    # PII quarantine: hold this one card and carry on. Aborting a
                    # several-hundred-ticket backfill over a single bad card would be
                    # worse than surfacing it for review. The card is never written.
                    rendered = render(card, __version__)
                    kinds = leaks(rendered, known)
                    if kinds:
                        report.pii_held += 1
                        report.pii_tickets.append((ticket.id, kinds))
                        continue

                    path, status = write_card(clients_dir, card, __version__, force=force)
                    if status == "preserved":
                        report.preserved += 1
                    else:
                        report.emitted += 1
                        # Belt and braces: PII was already quarantined above, so a hit
                        # here means a logic bug and must fail loudly.
                        verify_card(path.read_text(), card, known, card_ids)
                except RunError:
                    raise
                except Exception as e:      # noqa: BLE001 - isolate one bad ticket
                    report.failed += 1
                    report.failures.append((ticket_id, str(e)))
                    continue

            new_cursor[str(org_id)] = newest

        if not dry_run:
            save_state(state_dir, client, new_cursor)

    verify_run(report)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(prog="okfzendesk")
    ap.add_argument("mode", choices=["backfill", "incremental", "rebuild"])
    ap.add_argument("--client", action="append", required=True)
    ap.add_argument("--customers", required=True, help="path to customers.yaml")
    ap.add_argument("--clients-dir", required=True)
    ap.add_argument("--concepts-dir", required=True)
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, help="concurrency for rebuild (default from config)")
    ap.add_argument("--batch-size", type=int, help="cards per LLM call in rebuild")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    s = Settings()
    org_ids = load_org_ids(args.customers, args.client)
    connector = ConnectorClient(s.connector_base, s.connector_api_key,
                                s.connector_page_cap, s.cap_warn_ratio)
    llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.distill_model,
                      s.bifrost_timeout_s, max_tokens=s.distill_max_tokens)

    try:
        if args.mode == "rebuild":
            import boto3

            from .r2 import R2Reader
            from .rebuild import rebuild
            s3 = boto3.client("s3", endpoint_url=s.r2_endpoint,
                              aws_access_key_id=s.r2_access_key_id,
                              aws_secret_access_key=s.r2_secret_access_key,
                              region_name="auto")
            report = rebuild(args.client, org_ids, R2Reader(s3, s.r2_bucket), connector, llm,
                             args.clients_dir, args.concepts_dir,
                             workers=args.workers or s.reshape_workers,
                             batch_size=args.batch_size or s.reshape_batch_size,
                             force=args.force, limit=args.limit, dry_run=args.dry_run)
        else:
            report = ingest(args.client, org_ids, connector, llm, args.clients_dir,
                            args.concepts_dir, args.state_dir, dry_run=args.dry_run,
                            force=args.force, limit=args.limit)
    except RunError as e:
        log.error("run failed: %s", e)
        return 1

    log.info("fetched=%d emitted=%d skipped=%d cached=%d preserved=%d pii_held=%d failed=%d",
             report.fetched, report.emitted, report.skipped, report.cached,
             report.preserved, report.pii_held, report.failed)
    for tid, reason in report.skipped_reasons[:20]:
        log.info("  skipped %s: %s", tid, reason)
    # Kinds only - never the offending values.
    for tid, kinds in report.pii_tickets:
        log.warning("  PII HELD %s: %s (card not written; needs review)", tid, kinds)
    for tid, err in report.failures[:20]:
        log.error("  failed %s: %s", tid, err)
    return 0
