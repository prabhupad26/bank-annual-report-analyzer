"""Free SEC EDGAR submissions + 20-F document ingestion.

SEC API: https://data.sec.gov/submissions/CIK##########.json
Archives: https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}
No API key. A descriptive contact User-Agent is required.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote

from bank_analyzer.metrics.providers import Bank, _get_json, _session, load_banks

FORMS = {"20-F", "20-F/A"}
ACCESSION_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")
DOCUMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
HISTORY_PATTERN = re.compile(r"^CIK\d+-submissions-\d+\.json$")
MAX_DOCUMENT_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class SecFiling:
    bank: str
    cik: str
    accession: str
    form: str
    fiscal_year: int
    report_date: date
    filed_date: date
    primary_document: str
    document_url: str
    index_url: str


def require_sec_headers() -> dict[str, str]:
    user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if "@" not in user_agent or "your-domain" in user_agent or "example." in user_agent:
        raise ValueError(
            "SEC_USER_AGENT must identify your app and give a real contact email; "
            "e.g. 'BankAnalyzer/1.0 contact@company.com'"
        )
    return {"User-Agent": user_agent, "Accept": "application/json, text/html"}


def _date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def parse_submissions(bank: Bank, data: dict, start_year: int, end_year: int,
                      forms: set[str] | None = None) -> list[SecFiling]:
    """Extract only genuinely reported fiscal periods; never infer from filing date."""
    if not isinstance(data, dict):
        raise ValueError("SEC submission payload must be an object")
    allowed = FORMS if forms is None else forms
    required = ("accessionNumber", "form", "filingDate", "reportDate", "primaryDocument")
    if not all(isinstance(data.get(column), list) for column in required):
        raise ValueError("SEC submission index is missing required column arrays")
    lengths = [len(data[column]) for column in required]
    if len(set(lengths)) != 1:
        raise ValueError("SEC submission column lengths do not match")
    result = []
    for accession, form, filed, reported, document in zip(
        *(data[column] for column in required)
    ):
        if form not in allowed:
            continue
        report_date = _date(reported)
        filed_date = _date(filed)
        if not report_date or not filed_date or not start_year <= report_date.year <= end_year:
            continue
        if not isinstance(accession, str) or not ACCESSION_PATTERN.fullmatch(accession):
            continue
        if not isinstance(document, str) or not DOCUMENT_PATTERN.fullmatch(document):
            continue
        if ".." in document:
            continue
        base = (f"https://www.sec.gov/Archives/edgar/data/{int(bank.sec_cik)}/"
                f"{accession.replace('-', '')}/")
        result.append(SecFiling(
            bank=bank.slug, cik=bank.sec_cik, accession=accession, form=form,
            fiscal_year=report_date.year, report_date=report_date,
            filed_date=filed_date, primary_document=document,
            document_url=base + quote(document, safe=""),
            index_url=base + accession + "-index.html",
        ))
    return result


def fetch_submissions(bank: Bank, start_year: int, end_year: int,
                      session=None) -> list[SecFiling]:
    if not bank.sec_cik:
        raise ValueError(f"{bank.slug} has no group-level SEC 20-F issuer mapping")
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    headers = require_sec_headers()
    client = session or _session()
    url = f"https://data.sec.gov/submissions/CIK{int(bank.sec_cik):010d}.json"
    main = _get_json(client, url, headers=headers)
    if not isinstance(main, dict) or "filings" not in main:
        raise RuntimeError(f"SEC returned no submissions index for {bank.slug}")
    filings = main["filings"]
    if not isinstance(filings, dict) or not isinstance(filings.get("recent"), dict):
        raise RuntimeError("Malformed SEC filings payload")
    found = parse_submissions(bank, filings["recent"], start_year, end_year)
    for file in filings.get("files", []):
        if not isinstance(file, dict):
            continue
        name = file.get("name")
        if not isinstance(name, str) or not HISTORY_PATTERN.fullmatch(name):
            continue
        begin, end = _date(file.get("filingFrom")), _date(file.get("filingTo"))
        # Annual reports may be filed in the year after fiscal year-end.
        if begin and end and (end.year < start_year or begin.year > end_year + 2):
            continue
        time.sleep(0.2)  # Gentle sequential SEC requests; below 10 req/s.
        additional = _get_json(
            client, f"https://data.sec.gov/submissions/{name}", headers=headers,
        )
        found.extend(parse_submissions(bank, additional, start_year, end_year))
    # Keep amendments, but deduplicate entries repeated across recent/archive indexes.
    return sorted({filing.accession: filing for filing in found}.values(),
                  key=lambda item: (item.fiscal_year, item.filed_date, item.accession))


def download_filing(filing: SecFiling, root: str | Path, session=None) -> tuple[Path, str]:
    """Download one official primary document with bounded size and atomic writes."""
    require_sec_headers()
    if not ACCESSION_PATTERN.fullmatch(filing.accession) or not (
        DOCUMENT_PATTERN.fullmatch(filing.primary_document)
    ) or ".." in filing.primary_document:
        raise ValueError("Unsafe accession or document name")
    path = Path(root) / filing.bank / str(filing.fiscal_year) / (
        filing.accession.replace("-", "") + "_" + filing.primary_document
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return path, digest.hexdigest()
    client = session or _session()
    time.sleep(0.2)
    response = client.get(
        filing.document_url, headers=require_sec_headers(),
        stream=True, timeout=(10, 90),
    )
    try:
        response.raise_for_status()
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_DOCUMENT_BYTES:
            raise RuntimeError("SEC filing is larger than the 100 MB download cap")
        tmp = path.with_name(path.name + ".part")
        digest = hashlib.sha256()
        size = 0
        try:
            with tmp.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > MAX_DOCUMENT_BYTES:
                        raise RuntimeError("SEC filing exceeds the 100 MB download cap")
                    stream.write(chunk)
                    digest.update(chunk)
            if size == 0:
                raise RuntimeError("SEC returned an empty filing")
            tmp.replace(path)
            return path, digest.hexdigest()
        finally:
            tmp.unlink(missing_ok=True)
    finally:
        response.close()


def _store_filings(conn, bank: Bank, filings: list[SecFiling]) -> int:
    from bank_analyzer.config import BANKS

    conn.execute(
        """INSERT INTO banks (slug, name) VALUES (%s, %s)
           ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name""",
        (bank.slug, BANKS[bank.slug]),
    )
    bank_id = conn.execute("SELECT id FROM banks WHERE slug = %s", (bank.slug,)).fetchone()[0]
    changed = 0
    for filing in filings:
        changed += conn.execute(
            """INSERT INTO sec_filings
               (bank_id, cik, accession, form, fiscal_year, report_date,
                filed_date, primary_document, document_url, index_url)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (bank_id, accession) DO UPDATE SET
                 form=EXCLUDED.form, fiscal_year=EXCLUDED.fiscal_year,
                 report_date=EXCLUDED.report_date, filed_date=EXCLUDED.filed_date,
                 primary_document=EXCLUDED.primary_document,
                 document_url=EXCLUDED.document_url, index_url=EXCLUDED.index_url,
                 last_seen_at=now()
               WHERE (sec_filings.form, sec_filings.fiscal_year,
                      sec_filings.report_date, sec_filings.filed_date,
                      sec_filings.primary_document, sec_filings.document_url,
                      sec_filings.index_url)
                 IS DISTINCT FROM
                     (EXCLUDED.form, EXCLUDED.fiscal_year,
                      EXCLUDED.report_date, EXCLUDED.filed_date,
                      EXCLUDED.primary_document, EXCLUDED.document_url,
                      EXCLUDED.index_url)""",
            (bank_id, bank.sec_cik, filing.accession, filing.form, filing.fiscal_year,
             filing.report_date, filing.filed_date, filing.primary_document,
             filing.document_url, filing.index_url),
        ).rowcount
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover and optionally download free SEC 20-Fs")
    parser.add_argument("--config", default="data/metric_banks.csv")
    parser.add_argument("--banks", help="Comma-separated bank slugs from configuration")
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--download", action="store_true",
                        help="Download primary HTML/iXBRL filings to data/raw/sec")
    parser.add_argument("--output-dir", default="data/raw/sec")
    parser.add_argument("--dry-run", action="store_true",
                        help="Discover URLs only; no database writes or downloads")
    args = parser.parse_args(argv)
    if args.start_year > args.end_year:
        parser.error("Start year must not exceed end year")
    if args.dry_run and args.download:
        parser.error("--dry-run and --download cannot be combined")
    banks = load_banks(args.config)
    if args.banks:
        chosen = {name.strip() for name in args.banks.split(",") if name.strip()}
        missing = chosen - {bank.slug for bank in banks}
        if missing:
            parser.error(f"Unknown/unconfigured bank(s): {', '.join(sorted(missing))}")
        banks = [bank for bank in banks if bank.slug in chosen]
    conn = None
    if not args.dry_run:
        from bank_analyzer.metrics.db import connect, init_database
        conn = connect()
        try:
            init_database(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            conn.close()
            raise
    writer = csv.writer(sys.stdout)
    writer.writerow(("bank", "fiscal_year", "form", "filing_date", "accession",
                     "document_url"))
    failures = 0
    try:
        for bank in banks:
            if not bank.sec_cik:
                print(f"SKIP {bank.slug}: no matching SEC group-level 20-F issuer",
                      file=sys.stderr)
                continue
            try:
                filings = fetch_submissions(bank, args.start_year, args.end_year)
                if conn is not None:
                    _store_filings(conn, bank, filings)
                    conn.commit()
                for filing in filings:
                    writer.writerow((filing.bank, filing.fiscal_year, filing.form,
                                     filing.filed_date, filing.accession,
                                     filing.document_url))
                    if args.download:
                        path, sha256 = download_filing(filing, args.output_dir)
                        conn.execute(
                            """UPDATE sec_filings SET local_path=%s, document_sha256=%s,
                               downloaded_at=now()
                               WHERE bank_id=(SELECT id FROM banks WHERE slug=%s)
                               AND accession=%s""",
                            (str(path), sha256, bank.slug, filing.accession),
                        )
                        conn.commit()
                print(f"{bank.slug}: {len(filings)} eligible filings",
                      file=sys.stderr)
            except Exception as exc:
                failures += 1
                if conn is not None:
                    conn.rollback()
                print(f"ERROR {bank.slug}: {exc}", file=sys.stderr)
    finally:
        if conn is not None:
            conn.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
