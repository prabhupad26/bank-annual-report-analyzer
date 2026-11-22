"""Offline contract tests for the two API normalizers."""
from decimal import Decimal

import pytest

from bank_analyzer.metrics.providers import (
    Bank, load_banks, parse_fmp, parse_sec, fetch_fmp, fetch_sec,
)


BARCLAYS = Bank("barclays", "312069", "BCS", "GBP")


def test_sec_annual_durations_latest_filing_and_currency():
    payload = {"facts": {"ifrs-full": {"Assets": {"units": {
        "GBP": [
            {"form": "20-F", "end": "2024-12-31", "val": 100, "filed": "2025-03-01"},
            {"form": "20-F", "end": "2024-12-31", "val": 110, "filed": "2026-03-01"},
            {"form": "6-K", "end": "2025-12-31", "val": 999, "filed": "2026-03-01"},
        ],
        "USD": [{"form": "20-F", "end": "2024-12-31", "val": 200,
                 "filed": "2026-04-01"}],
    }}, "ProfitLoss": {"units": {"GBP": [
        {"form": "20-F", "start": "2024-01-01", "end": "2024-12-31",
         "val": -12, "filed": "2025-03-01"},
        {"form": "20-F", "start": "2024-10-01", "end": "2024-12-31",
         "val": 999, "filed": "2026-03-01"},
    ]}}}}}
    facts = parse_sec(BARCLAYS, payload, 2024, 2024)
    assert {f.code for f in facts} == {"total_assets", "net_income"}
    assets = next(f for f in facts if f.code == "total_assets")
    assert assets.value == Decimal("110")
    assert assets.currency == "GBP"
    assert assets.provider == "sec"
    assert next(f.value for f in facts if f.code == "net_income") == Decimal("-12")


def test_fmp_annual_filtered_currency_and_absent_metrics():
    payload = [
        {"period": "FY", "date": "2025-12-31", "reportedCurrency": "GBP",
         "netIncome": 150, "revenue": 1200, "incomeBeforeTax": None},
        {"period": "Q1", "date": "2025-03-31", "reportedCurrency": "GBP",
         "netIncome": 99},
    ]
    facts = parse_fmp(BARCLAYS, payload, "income-statement", 2021, 2025)
    assert {(f.year, f.code) for f in facts} == {
        (2025, "net_income"), (2025, "total_revenue")}
    assert all(f.currency == "GBP" for f in facts)


def test_fmp_error_payload_not_silently_successful():
    with pytest.raises(RuntimeError, match="error payload"):
        parse_fmp(BARCLAYS, {"Error Message": "Upgrade required"},
                  "income-statement", 2021, 2025)


def test_config_duplicate_and_unknown(tmp_path):
    path = tmp_path / "banks.csv"
    path.write_text("bank,sec_cik,fmp_symbol,reporting_currency\n"
                    "barclays,312069,BCS,GBP\nbarclays,312069,BCS,GBP\n")
    with pytest.raises(ValueError, match="Duplicate"):
        load_banks(path)


def test_missing_credentials_raise_without_network(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        fetch_sec(BARCLAYS, 2024, 2025)
    with pytest.raises(ValueError, match="FMP_API_KEY"):
        fetch_fmp(BARCLAYS, 2024, 2025)
