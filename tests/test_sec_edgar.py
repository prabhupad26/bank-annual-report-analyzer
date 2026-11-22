"""Offline tests for free SEC submissions and safe filing downloads."""
from datetime import date
from hashlib import sha256

import pytest

from bank_analyzer.ingestion.sec_edgar import (
    download_filing,
    fetch_submissions,
    parse_submissions,
    require_sec_headers,
)
from bank_analyzer.metrics.providers import Bank

BANK = Bank("barclays", "312069", "BCS", "GBP")


def _rows(accession="0000312069-26-000004", year=2025):
    return {
        "accessionNumber": [accession, "0000312069-26-000001", "0000312069-26-000002"],
        "form": ["20-F", "6-K", "20-F/A"],
        "filingDate": ["2026-02-10", "2026-01-01", "2026-05-15"],
        "reportDate": [f"{year}-12-31", "2025-09-30", f"{year}-12-31"],
        "primaryDocument": ["bcs-20251231.htm", "irrelevant.htm", "amend.htm"],
    }


def test_parse_only_annual_filing_and_amendment_with_true_report_year():
    filings = parse_submissions(BANK, _rows(), 2025, 2025)
    assert len(filings) == 2
    assert {f.form for f in filings} == {"20-F", "20-F/A"}
    assert all(f.fiscal_year == 2025 for f in filings)
    assert filings[0].document_url == (
        "https://www.sec.gov/Archives/edgar/data/312069/"
        "000031206926000004/bcs-20251231.htm"
    )
    assert filings[0].report_date == date(2025, 12, 31)


def test_parse_excludes_unverified_periods_and_unsafe_paths():
    rows = _rows()
    rows["reportDate"][0] = ""
    rows["primaryDocument"][2] = "../escape.htm"
    assert parse_submissions(BANK, rows, 2021, 2025) == []
    rows = _rows()
    rows["accessionNumber"].pop()
    with pytest.raises(ValueError, match="column lengths"):
        parse_submissions(BANK, rows, 2021, 2025)


def test_missing_contact_rejected(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        require_sec_headers()


class Client:
    def __init__(self, payloads):
        self.payloads = payloads
        self.urls = []
    def get(self, url, **kwargs):
        self.urls.append(url)
        return Response(self.payloads[url])


class Response:
    status_code = 200
    headers = {"Content-Length": "12"}

    def __init__(self, payload):
        self.payload = payload
    def json(self):
        return self.payload
    def raise_for_status(self):
        return None
    def iter_content(self, chunk_size):
        yield b"hello sec 20f"
    def close(self):
        pass


def test_fetch_follows_historical_submission_index(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "BankAnalyzer/1.0 contact@firm.org")
    url = "https://data.sec.gov/submissions/CIK0000312069.json"
    backfill_url = "https://data.sec.gov/submissions/CIK0000312069-submissions-001.json"
    main = {"filings": {"recent": {
        "accessionNumber": [], "form": [], "filingDate": [],
        "reportDate": [], "primaryDocument": [],
    }, "files": [{
        "name": "CIK0000312069-submissions-001.json",
        "filingFrom": "2020-01-01", "filingTo": "2024-12-31",
    }]}}
    client = Client({url: main, backfill_url: _rows(year=2021)})
    monkeypatch.setattr("bank_analyzer.ingestion.sec_edgar.time.sleep", lambda _: None)
    records = fetch_submissions(BANK, 2021, 2021, session=client)
    assert len(records) == 2
    assert [x.fiscal_year for x in records] == [2021, 2021]
    assert client.urls == [url, backfill_url]


def test_download_is_idempotent_and_hashes_file(monkeypatch, tmp_path):
    monkeypatch.setenv("SEC_USER_AGENT", "BankAnalyzer/1.0 contact@firm.org")
    monkeypatch.setattr("bank_analyzer.ingestion.sec_edgar.time.sleep", lambda _: None)
    filing = parse_submissions(BANK, _rows(), 2025, 2025)[0]
    client = Client({filing.document_url: {}})
    first_path, first_hash = download_filing(filing, tmp_path, session=client)
    second_path, second_hash = download_filing(filing, tmp_path, session=client)
    assert first_path == second_path
    assert first_hash == second_hash == sha256(b"hello sec 20f").hexdigest()
    assert len(client.urls) == 1


def test_unmapped_bnp_cannot_fetch_sec(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "BankAnalyzer/1.0 contact@firm.org")
    bnp = Bank("bnp_paribas", "", "BNP.PA", "EUR")
    with pytest.raises(ValueError, match="no group-level SEC"):
        fetch_submissions(bnp, 2021, 2025)
