"""Build the journal from the cards already staged on R2.

Three phases, deliberately separated:

1. **Index** (serial, fast) - list R2 keys, and pull each org's ticket list once so every
   entry gets a real closed date and subject without a per-ticket API call.
2. **Reshape** (CONCURRENT) - the only expensive step, ~20s per entry against the on-prem
   Qwen. Pure: card in, entry out, no shared state, so it parallelises safely.
3. **Write + verify** (serial) - keeps file writes and the PII gate single-threaded, so
   there are no write races and failures stay attributable.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import __version__
from .emit import render, write_card
from .link import load_card_ids, resolve_related
from .model import RunReport
from .r2 import R2Reader
from .reshape import reshape
from .scrub import leaks
from .verify import verify_card, verify_run

log = logging.getLogger("okfzendesk")


def ticket_meta(connector, org_ids: list[int]) -> dict[int, tuple[str, str]]:
    """ticket_id -> (closed_at, subject), from one list call per org rather than per ticket."""
    out: dict[int, tuple[str, str]] = {}
    for org_id in org_ids:
        for raw in connector.list_closed(org_id=org_id, since="1970-01-01"):
            try:
                out[int(raw["id"])] = (raw.get("updated_at") or "", raw.get("subject") or "")
            except (KeyError, TypeError, ValueError):
                continue
    return out


def rebuild(clients, org_ids, r2: R2Reader, connector, llm, clients_dir, concepts_dir,
            workers: int = 6, force: bool = False, limit: int | None = None,
            dry_run: bool = False) -> RunReport:
    report = RunReport()
    card_ids = load_card_ids(concepts_dir) if Path(concepts_dir).exists() else set()

    for client in clients:
        keys = r2.list_cards(client)
        meta = ticket_meta(connector, org_ids[client]) if connector else {}
        if limit:
            keys = keys[:limit]
        report.fetched += len(keys)
        log.info("%s: %d staged cards on R2", client, len(keys))

        # --- phase 1: which still need work (serial, no network) ---
        from .run import already_carded
        todo = []
        for key in keys:
            staged = r2.get_card(key)
            if staged is None:
                report.skipped += 1
                report.skipped_reasons.append((0, f"unparsable-key:{key}"))
                continue
            if not force and already_carded(clients_dir, client, staged.ticket_id):
                report.cached += 1
                continue
            todo.append(staged)

        if dry_run:
            report.emitted += len(todo)
            continue

        # --- phase 2: reshape concurrently (the only slow step) ---
        log.info("%s: reshaping %d entries with %d workers", client, len(todo), workers)
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for staged in todo:
                closed_at, subject = meta.get(staged.ticket_id, ("", ""))
                futures[pool.submit(reshape, staged, llm, set(), closed_at, subject)] = staged
            for fut in as_completed(futures):
                staged = futures[fut]
                done += 1
                if done % 50 == 0:
                    log.info("  %s: %d/%d reshaped", client, done, len(todo))
                try:
                    card = fut.result()
                except Exception as e:      # noqa: BLE001 - isolate one entry
                    report.failed += 1
                    report.failures.append((staged.ticket_id, str(e)))
                    continue
                if card is None:
                    report.skipped += 1
                    report.skipped_reasons.append((staged.ticket_id, "reshape-failed"))
                    continue

                # --- phase 3: link, PII gate, write, verify (serial) ---
                card.related = resolve_related(card.related, card_ids)
                rendered = render(card, __version__)
                kinds = leaks(rendered, set())
                if kinds:
                    report.pii_held += 1
                    report.pii_tickets.append((card.ticket_id, kinds))
                    continue
                path, status = write_card(clients_dir, card, __version__, force=force)
                if status == "preserved":
                    report.preserved += 1
                else:
                    report.emitted += 1
                    verify_card(path.read_text(), card, set(), card_ids)

    verify_run(report)
    return report
