"""Bank metrics from SEC Company Facts and Financial Modeling Prep.

SEC facts are issuer-level, annual, non-custom XBRL tags only. We keep
concept and currency provenance instead of guessing unsupported metrics.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bank_analyzer.config import BANKS


# Monetary amounts are stored in the original reporting units (not millions).
METRICS = {
    "total_assets": ("Total assets", "currency", "Total assets of the consolidated group"),
    "total_liabilities": ("Total liabilities", "currency", "Total liabilities"),
    "total_equity": ("Total equity", "currency", "Including non-controlling interests"),
    "shareholders_equity": ("Equity attributable to owners", "currency", "Excluding non-controlling interests"),
    "net_income": ("Profit or loss", "currency", "Net income / profit for the year"),
    "profit_before_tax": ("Profit before tax", "currency", "Annual pre-tax income"),
    "total_revenue": ("Revenue", "currency", "Provider-reported revenue; compare accounting definitions"),
    "interest_income": ("Interest income", "currency", "Reported interest revenue, if supplied"),
    "cash_and_cash_equivalents": ("Cash and cash equivalents", "currency", "Balance at period end"),
    "operating_cash_flow": ("Net operating cash flow", "currency", "Cash from operating activities"),
}

# IFRS and US-GAAP are not merged blindly: IFRS has precedence.
SEC_TAGS = {
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "total_equity": ("Equity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "shareholders_equity": ("EquityAttributableToOwnersOfParent", "StockholdersEquity"),
    "net_income": ("ProfitLoss", "NetIncomeLoss"),
    "profit_before_tax": ("ProfitLossBeforeTax", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"),
    "total_revenue": ("Revenue", "Revenues"),
    "interest_income": ("InterestRevenueCalculatedUsingEffectiveInterestMethod", "InterestIncomeExpenseAfterProvisionForLoanLoss"),
    "cash_and_cash_equivalents": ("CashAndCashEquivalents", "CashAndCashEquivalentsAtCarryingValue"),
    "operating_cash_flow": ("CashFlowsFromUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivities"),
}
FMP_FIELDS = {
    "income-statement": {
        "netIncome": "net_income",
        "incomeBeforeTax": "profit_before_tax",
        "revenue": "total_revenue",
        "interestIncome": "interest_income",
    },
    "balance-sheet-statement": {
        "totalAssets": "total_assets",
        "totalLiabilities": "total_liabilities",
        "totalEquity": "total_equity",
        "totalStockholdersEquity": "shareholders_equity",
        "cashAndCashEquivalents": "cash_and_cash_equivalents",
    },
    "cash-flow-statement": {
        "netCashProvidedByOperatingActivities": "operating_cash_flow",
    },
}


@dataclass(frozen=True)
class Bank:
    slug: str
    sec_cik: str
    fmp_symbol: str
    reporting_currency: str


@dataclass(frozen=True)
class MetricFact:
    bank: str
    year: int
    code: str
    value: Decimal
    currency: str | None
    provider: str
    source_url: str
    source_concept: str
    period_end: date
    filing_date: date | None = None
    accession: str | None = None
    reported_unit: str | None = None


def load_banks(path: str | Path) -> list[Bank]:
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not {"bank", "sec_cik", "fmp_symbol", "reporting_currency"}.issubset(reader.fieldnames or []):
            raise ValueError("Bank CSV must contain bank,sec_cik,fmp_symbol,reporting_currency")
        banks = []
        for row in reader:
            slug = row["bank"].strip()
            if not slug or slug.startswith("#"):
                continue
            if slug not in BANKS:
                raise ValueError(f"Unknown bank slug: {slug}")
            currency = row["reporting_currency"].strip().upper()
            if len(currency) != 3 or not currency.isalpha():
                raise ValueError(f"Invalid reporting currency for {slug}")
            banks.append(Bank(slug, row["sec_cik"].strip(), row["fmp_symbol"].strip(), currency))
    if len({b.slug for b in banks}) != len(banks):
        raise ValueError("Duplicate bank in configuration")
    if not banks:
        raise ValueError("Bank configuration has no rows")
    return banks


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _get_json(session: requests.Session, url: str, params: dict | None = None,
              headers: dict | None = None) -> object:
    # Do not expose FMP_API_KEY in exception messages or logging.
    try:
        response = session.get(url, params=params, headers=headers, timeout=(8, 45))
    except requests.RequestException as exc:
        raise RuntimeError(f"API transport failed ({type(exc).__name__}) at {url}") from None
    if response.status_code != 200:
        raise RuntimeError(f"API HTTP {response.status_code} at {url}; check credentials/limits")
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(f"Non-JSON API response at {url}") from None
    return payload


def parse_sec(bank: Bank, payload: dict, start_year: int, end_year: int) -> list[MetricFact]:
    """Prefer annual 20-F facts, annual durations, latest filings and reporting currency.

    Comparative figures in newer filings are allowed: updated/restated values replace
    the earlier observation on rerun. Nonstandard, company-extension tags are excluded.
    """
    facts = payload.get("facts", {})
    chosen: dict[tuple[str, int], tuple[tuple, MetricFact]] = {}
    source = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(bank.sec_cik):010d}.json"
    for code, aliases in SEC_TAGS.items():
        for taxonomy_rank, taxonomy in enumerate(("ifrs-full", "us-gaap")):
            concepts = facts.get(taxonomy, {})
            for alias_rank, tag in enumerate(aliases):
                if tag not in concepts:
                    continue
                for raw_unit, entries in concepts[tag].get("units", {}).items():
                    if not (len(raw_unit) == 3 and raw_unit.isalpha()):
                        continue  # monetary data only; no shares or ratios
                    unit = raw_unit.upper()
                    for item in entries:
                        if item.get("form") not in ("20-F", "20-F/A"):
                            continue
                        period_end = _date(item.get("end"))
                        if not period_end or not (start_year <= period_end.year <= end_year):
                            continue
                        start = _date(item.get("start"))
                        if start and not (330 <= (period_end - start).days <= 400):
                            continue
                        if not start and period_end.month < 9:
                            continue  # instant values must be close to fiscal year end
                        value = _decimal(item.get("val"))
                        if value is None:
                            continue
                        reported = MetricFact(
                            bank=bank.slug, year=period_end.year, code=code, value=value,
                            currency=unit, provider="sec", source_url=source,
                            source_concept=f"{taxonomy}:{tag}", period_end=period_end,
                            filing_date=_date(item.get("filed")),
                            accession=item.get("accn"), reported_unit=raw_unit,
                        )
                        ranking = (
                            -taxonomy_rank, -alias_rank,
                            unit == bank.reporting_currency,
                            item.get("filed") or "",
                            item.get("accn") or "",
                        )
                        key = (code, period_end.year)
                        if key not in chosen or ranking > chosen[key][0]:
                            chosen[key] = (ranking, reported)
    return sorted((entry[1] for entry in chosen.values()), key=lambda f: (f.year, f.code))


def fetch_sec(bank: Bank, start_year: int, end_year: int,
              session: requests.Session | None = None) -> list[MetricFact]:
    if not bank.sec_cik:
        raise ValueError(f"No SEC CIK mapped for {bank.slug}; use FMP for this bank")
    agent = os.getenv("SEC_USER_AGENT", "").strip()
    if "@" not in agent or "example." in agent or "your-domain" in agent:
        raise ValueError("Set SEC_USER_AGENT to an app name and real contact email")
    source = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(bank.sec_cik):010d}.json"
    payload = _get_json(session or _session(), source, headers={
        "User-Agent": agent, "Accept": "application/json",
    })
    if not isinstance(payload, dict) or "facts" not in payload:
        raise RuntimeError(f"SEC returned no companyfacts object for {bank.slug}")
    return parse_sec(bank, payload, start_year, end_year)


def parse_fmp(bank: Bank, payload: list, endpoint: str, start_year: int,
              end_year: int) -> list[MetricFact]:
    if not isinstance(payload, list):
        raise RuntimeError(f"FMP {endpoint} returned an error payload instead of a list")
    if endpoint not in FMP_FIELDS:
        raise ValueError(f"Unsupported FMP endpoint: {endpoint}")
    source = (f"https://financialmodelingprep.com/stable/{endpoint}"
              f"?symbol={quote(bank.fmp_symbol, safe='')}")
    facts: list[MetricFact] = []
    for item in payload:
        if not isinstance(item, dict) or str(item.get("period", "FY")).upper() not in ("FY", "ANNUAL"):
            continue
        period_end = _date(item.get("date"))
        if not period_end or not start_year <= period_end.year <= end_year:
            continue
        raw_currency = str(item.get("reportedCurrency") or "").strip().upper()
        currency = raw_currency if len(raw_currency) == 3 and raw_currency.isalpha() else None
        for field, code in FMP_FIELDS[endpoint].items():
            value = _decimal(item.get(field))
            if value is None:
                continue
            facts.append(MetricFact(
                bank=bank.slug, year=period_end.year, code=code, value=value,
                currency=currency, provider="fmp", source_url=source,
                source_concept=field, period_end=period_end,
                filing_date=_date(item.get("fillingDate") or item.get("filingDate")),
                accession=item.get("acceptedDate"), reported_unit=currency,
            ))
    return facts


def fetch_fmp(bank: Bank, start_year: int, end_year: int,
              session: requests.Session | None = None) -> list[MetricFact]:
    key = os.getenv("FMP_API_KEY", "").strip()
    if not key:
        raise ValueError(f"FMP_API_KEY is required for FMP metrics ({bank.slug})")
    if not bank.fmp_symbol:
        raise ValueError(f"No FMP symbol mapped for {bank.slug}")
    client = session or _session()
    facts: list[MetricFact] = []
    for endpoint in FMP_FIELDS:
        url = f"https://financialmodelingprep.com/stable/{endpoint}"
        payload = _get_json(client, url, {
            "symbol": bank.fmp_symbol, "period": "annual",
            "limit": max(5, end_year - start_year + 3), "apikey": key,
        })
        facts.extend(parse_fmp(bank, payload, endpoint, start_year, end_year))
    # Data vendors may return duplicate fiscal-year rows. Prefer the most recently filed.
    latest: dict[tuple[str, int], MetricFact] = {}
    for fact in facts:
        key = (fact.code, fact.year)
        old = latest.get(key)
        if old is None or ((fact.filing_date or date.min), fact.period_end) > (
                (old.filing_date or date.min), old.period_end):
            latest[key] = fact
    return sorted(latest.values(), key=lambda f: (f.year, f.code))
