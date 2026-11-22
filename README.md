# Bank Annual Report Analyzer

A modular research project for collecting European banks' annual reports, extracting structured content, storing financial metrics, and building citation-grounded retrieval augmented generation (RAG).

## Scope
Ten banks: Barclays, BNP Paribas, Deutsche Bank, HSBC, ING, Intesa Sanpaolo, Lloyds, Santander, UBS, UniCredit. Default reporting years: 2021–2025 (five completed calendar years as of November 2026). Report availability and fiscal-year definitions vary by bank.

## Architecture
```text
Official bank IR websites / public statistical APIs
    |                       |
    v                       v
Report discovery         Structured metrics ingestion
    |                       |
PDF downloads           PostgreSQL metrics tables
    |
PDF -> page-level Markdown + tables + image/chart assets
    |
Section hierarchy + provenance validation
    |
Chunks + embeddings -> vector index
    |
Hybrid retrieval -> reranking -> evidence-backed answers
```

## Repository map
- `src/bank_analyzer/config.py`: bank registry and project paths
- `src/bank_analyzer/ingestion/download.py`: manifest-based PDF download with skip-if-present
- `src/bank_analyzer/parsing/pdf_to_markdown.py`: page Markdown extraction (baseline; advanced table/chart extraction is future work)
- `src/bank_analyzer/storage/schema.sql`: normalized PostgreSQL schema
- `src/bank_analyzer/retrieval/chunking.py`: section/page-aware chunking baseline
- `docs/architecture.md`: target pipeline and quality gates
- `data/manifest.example.csv`: sample download manifest format

## Quickstart
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp data/manifest.example.csv data/manifest.csv
# Replace example URLs with verified official PDF links before running.
bank-reports-download --manifest data/manifest.csv
bank-reports-parse --input data/raw --output data/processed
```
The downloader ignores blank and comment lines in the CSV. Add at least one complete `bank,year,url` row before running it.

Optional database:
```bash
docker compose up -d postgres
psql postgresql://bank:bank@localhost:5432/bank_reports -f src/bank_analyzer/storage/schema.sql
```

## Status and limitations
This is an initial **working monorepo foundation**, not a completed production RAG system. Prior exploratory scripts and raw reports from earlier conversations are not automatically available in this repository. PDF extraction currently preserves page text and source metadata, but does **not** yet reliably reconstruct charts, complex tables, or exact section hierarchies. No unverified financial figures or fabricated report URLs are included. SEC EDGAR financial-metric and filing-index API adapters (plus optional FMP), annual metric normalization, PostgreSQL upserts, and offline tests are implemented. Verified live API coverage, embeddings, vector DB, answer generation, and end-to-end evaluations are not yet complete.

## Principles
Official sources first; provenance on every document and metric; deterministic reruns; idempotent ingestion; no credentials in Git; cite page numbers in answers; distinguish reported vs calculated metrics.

## Annual financial metrics: PostgreSQL + public APIs

The configurable starting set is **Barclays, BNP Paribas, Deutsche Bank, HSBC, ING** (edit `data/metric_banks.csv` to change the selection). Default historical window: **2021–2025**.

The new `bank-metrics` CLI creates the relational schema, makes bank-specific API calls, writes normalized annual facts with per-source provenance, and updates existing records on reruns. It does **not** insert artificial data for missing bank/metric/year combinations.

```bash
pip install -e ".[dev]"
docker compose up -d postgres
bank-metrics init-db

# SEC EDGAR is keyless, but SEC requires a genuine identifying User-Agent.
export SEC_USER_AGENT="BankAnnualReportAnalyzer/0.1 your-real-email@domain.com"

# Free SEC EDGAR is the default (four mapped banks; BNP skipped explicitly).
bank-metrics sync --start-year 2021 --end-year 2025

# Discover Form 20-F filings and save links in PostgreSQL.
bank-sec-filings --start-year 2021 --end-year 2025

# Optional: download the original filing HTML/iXBRL documents.
bank-sec-filings --download

# Only if you choose the optional paid FMP provider:
# export FMP_API_KEY="YOUR_REAL_FMP_API_KEY"
# bank-metrics sync --provider fmp

# Read observations back as CSV.
bank-metrics show --bank deutsche_bank --year 2025
```

Read [free SEC EDGAR setup and coverage notes](docs/metrics.md) and [example SQL queries](docs/queries_metrics.sql).

**API caveat:** SEC facts include only supported standard XBRL concepts; FMP access/coverage depends on your account. BNP Paribas is not mapped to an issuer-level SEC Company Facts CIK in the initial registry. The code has offline tests, but this repository does not ship a populated database or claim successful end-to-end API downloads.

The free SEC-only run skips BNP Paribas (no verified group-level SEC Form 20-F CIK). This is not complete five-bank coverage. EDGAR primary filings are HTML/iXBRL, not PDFs; converting them to Markdown is a separate parsing step.\n