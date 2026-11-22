# Public banking metrics integration

## Coverage and sources

The default registry (`data/metric_banks.csv`) intentionally contains five banks. It is an editable subset of the existing ten-bank registry and can be expanded without changing the relational schema.

| Bank | SEC Company Facts | FMP symbol |
| --- | --- | --- |
| Barclays | CIK 0000312069 | BCS |
| BNP Paribas | No group-level SEC CIK configured | BNP.PA |
| Deutsche Bank | CIK 0001159508 | DB |
| HSBC | CIK 0001089113 | HSBC |
| ING | CIK 0001039765 | ING |

**SEC EDGAR**: Official, no API key, but set `SEC_USER_AGENT` to a descriptive application string and your real email address. The code fetches `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`, uses standard IFRS or US-GAAP taxonomy tags, filters annual 20-F / 20-F/A data, restricts annual flow concepts to approximately one-year periods, and records filed date, accession, unit and exact SEC concept. Some banks/concepts may not be present in this standardized API; company-specific extension tags are deliberately excluded.

**FMP**: `https://financialmodelingprep.com/stable/income-statement`, `balance-sheet-statement`, and `cash-flow-statement` (with `symbol`, `period=annual`, `limit`, and your private `apikey` query parameter). Your FMP plan determines which historical statements, symbols and fields are accessible. Bank symbols are initial mappings: validate instrument/consolidated-group coverage against each institution's filing before financial comparisons.

These sources give *accounting-statement metrics*, not automatically CET1 ratio, NPL ratio, RWA or liquidity coverage ratio (LCR). EBA Transparency Exercise bank-level CSV datasets are a separate possible future connector; they are not implied to be a real-time metrics REST API.

## Install and run

From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d postgres

# Copy values from .env.example as needed; do not commit your .env file.
export DATABASE_URL="postgresql://bank:bank@localhost:5432/bank_reports"
export SEC_USER_AGENT="BankAnnualReportAnalyzer/0.1 real-contact@yourdomain.com"
# Needed for BNP Paribas via FMP:
export FMP_API_KEY="YOUR_PRIVATE_KEY"

bank-metrics init-db
bank-metrics sync --provider auto --start-year 2021 --end-year 2025
bank-metrics show --bank barclays --year 2025
```

Use `--provider sec` with `--banks barclays,deutsche_bank,hsbc,ing` for a four-bank keyless SEC-only run, or `--provider fmp` with `FMP_API_KEY` to try FMP for all five banks. `--dry-run` performs API requests without database changes. An API failure for any bank produces an error and a nonzero exit code, while other banks can still complete. If the source has no eligible facts, the bank is logged as an empty run instead of inventing figures.

## Relational data model

The pre-existing `banks`, `metric_definitions`, and `metric_observations` tables are retained. `metrics_migration.sql` adds provenance fields to observations and a `metric_ingestion_runs` audit table. `bank-metrics init-db` creates both schemas in one invocation and is rerunnable.

Observation identity: `(bank_id, metric_id, fiscal_year, source_url, methodology)`, which preserves SEC/FMP records separately. **Important:** `source_url` is the stable, key-free API URL, not a per-filing report PDF; `accession`, `filing_date`, `period_end`, `provider`, `source_concept`, and `reported_unit` preserve retrieval provenance. Newer restated values overwrite the previous observation from the *same provider*, while repeat runs with unchanged facts do not update the row's timestamp. Ingestion transactions are committed per bank.

Amounts are stored as full monetary units (not thousands/millions), using `NUMERIC` and the returned currency; if the source omits currency, the value is left with NULL currency rather than guessing. **Do not compare amounts across different currencies without FX conversion, or conflate IFRS total equity with equity attributable to shareholders.** Revenue, profit and cash flow field definitions should be checked against source filings before peer comparisons.

Use `docs/queries_metrics.sql` for the core historical, coverage, provider-disagreement and audit SQL queries. No credentials are written to URLs in the database or logged by the API client.

## Tests and maintenance

Run `pytest -q` for offline normalization/credential/config tests, including the existing document-processing tests. Re-run `bank-metrics sync` after each reporting season; existing observations are upserted, missing figures are left absent. Data quality and live coverage remain dependent on source availability. If adding new bank mappings, use the existing slug in `src/bank_analyzer/config.py`, the exact issuer's CIK when available, and a verified FMP symbol.

Sources: [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [FMP statement APIs](https://site.financialmodelingprep.com/developer/docs), [EBA Transparency Exercise](https://www.eba.europa.eu/risk-and-data-analysis/risk-analysis/eu-wide-transparency-exercise).
