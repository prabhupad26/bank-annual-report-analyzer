# Architecture and delivery plan

## 1. Ingestion
Maintain a curated manifest of official investor-relations PDF URLs. Record bank, fiscal year, original URL, file SHA-256, and retrieval timestamp. Skip existing files; support deliberate refresh in a later version.

## 2. Document understanding
Current baseline: page-wise PyMuPDF text to Markdown. Target: document layout model, explicit section tree, extracted tables with row/column semantics, figure assets with caption and OCR/vision-derived values, footnotes, and cross-page table stitching. Each extracted element should retain page number, bounding box, source file hash, and extraction confidence. Human review for ambiguous numeric data.

## 3. Financial data
Load public regulatory/statistical APIs and bank-reported tables into PostgreSQL with canonical metric definitions. Normalize reporting period, consolidated scope, currency, units, accounting basis, and restatements. Never treat incompatible definitions as directly comparable.

## 4. Retrieval
Index text chunks and table descriptions separately, with bank/year/section/page metadata. Combine keyword and vector search, apply metadata filters and reranking, then generate responses with source citations. Validate that cited evidence supports each numeric claim. Proposed options: PostgreSQL + pgvector for small scale; Qdrant for dedicated vector serving.

## 5. Evaluation
Golden questions: bank/year metric lookup, year-over-year comparison, cross-bank comparison, table-cell retrieval, figure interpretation, and multi-document synthesis. Track evidence recall@k, citation correctness, numeric exactness, table accuracy, latency and extraction coverage.

## 6. Roadmap
1. Verified source manifest and download tests
2. Layout/table/chart extraction and section hierarchy
3. API connectors, metrics normalization and upserts
4. Embedding pipeline and vector storage
5. Hybrid RAG service and evaluation suite
6. Dashboard and CI/CD

## Security
Keep API keys in environment or secret manager. No raw confidential reports or credentials in version control. Respect source terms, licensing, and rate limits.
