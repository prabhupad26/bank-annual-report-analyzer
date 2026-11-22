"""Commands: bank-metrics init-db | sync | show."""
from __future__ import annotations

import argparse
import csv
import sys

from bank_analyzer.metrics.db import connect, init_database, show_metrics, store_facts
from bank_analyzer.metrics.providers import fetch_fmp, fetch_sec, load_banks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest annual, issuer-level banking metrics")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create PostgreSQL schema and apply additive migrations")
    sync = sub.add_parser("sync", help="Backfill or refresh annual financial metrics")
    sync.add_argument("--config", default="data/metric_banks.csv")
    sync.add_argument("--provider", choices=["auto", "sec", "fmp"], default="sec")
    sync.add_argument("--banks", help="Comma-separated bank slugs; defaults to every config row")
    sync.add_argument("--start-year", type=int, default=2021)
    sync.add_argument("--end-year", type=int, default=2025)
    sync.add_argument("--dry-run", action="store_true", help="Fetch without database writes")
    show = sub.add_parser("show", help="Print one bank's stored metric history as CSV")
    show.add_argument("--bank", required=True)
    show.add_argument("--year", type=int)
    args = parser.parse_args(argv)

    if args.command == "init-db":
        with connect() as conn:
            init_database(conn)
        print("PostgreSQL schema ready")
        return 0

    if args.command == "show":
        with connect() as conn:
            rows = show_metrics(conn, args.bank, args.year)
        writer = csv.writer(sys.stdout)
        writer.writerow(("bank", "year", "metric", "value", "currency",
                         "provider", "period_end", "source_concept", "source_url"))
        writer.writerows(rows)
        return 0

    if args.start_year > args.end_year:
        parser.error("--start-year must not exceed --end-year")
    try:
        banks = load_banks(args.config)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.banks:
        selected = {item.strip() for item in args.banks.split(",") if item.strip()}
        unknown = selected - {bank.slug for bank in banks}
        if unknown:
            parser.error(f"Bank(s) not in configuration: {', '.join(sorted(unknown))}")
        banks = [bank for bank in banks if bank.slug in selected]
        if not banks:
            parser.error("No banks selected")
    failures = 0
    skipped = 0
    # Opening the DB first ensures a missing server/driver is reported before API calls.
    if not args.dry_run:
        conn = connect()
        try:
            init_database(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            conn.close()
            raise
    else:
        conn = None
    try:
        for bank in banks:
            provider = (args.provider if args.provider != "auto"
                        else ("sec" if bank.sec_cik else "fmp"))
            if provider == "sec" and not bank.sec_cik:
                skipped += 1
                print(f"{bank.slug}: SEC SKIPPED (no verified group-level 20-F issuer)",
                      file=sys.stderr)
                continue
            try:
                fetch = fetch_sec if provider == "sec" else fetch_fmp
                facts = fetch(bank, args.start_year, args.end_year)
                if conn is None:
                    print(f"{bank.slug}: {provider}: {len(facts)} observations (dry run)")
                    continue
                changed = store_facts(conn, bank.slug, provider, facts)
                conn.commit()
                print(f"{bank.slug}: {provider}: {len(facts)} observations, "
                      f"{changed} inserted/updated")
            except Exception as exc:
                if conn is not None:
                    conn.rollback()
                failures += 1
                print(f"{bank.slug}: {provider}: ERROR: {exc}", file=sys.stderr)
    finally:
        if conn is not None:
            conn.close()
    if skipped:
        print(f"{skipped} bank(s) not supported by SEC-only ingestion", file=sys.stderr)
    if failures:
        print(f"{failures} bank(s) failed; check the API, credentials, and coverage",
              file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
