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
This is an initial **working monorepo foundation**, not a completed production RAG system. Prior exploratory scripts and raw reports from earlier conversations are not automatically available in this repository. PDF extraction currently preserves page text and source metadata, but does **not** yet reliably reconstruct charts, complex tables, or exact section hierarchies. No unverified financial figures or fabricated report URLs are included. API adapters, metric normalization, embeddings, vector DB, answer generation, and end-to-end evaluations are planned.

## Principles
Official sources first; provenance on every document and metric; deterministic reruns; idempotent ingestion; no credentials in Git; cite page numbers in answers; distinguish reported vs calculated metrics.
