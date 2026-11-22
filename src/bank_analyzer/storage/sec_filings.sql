-- Official SEC EDGAR filing metadata. Safe to apply repeatedly.
CREATE TABLE IF NOT EXISTS sec_filings (
    id BIGSERIAL PRIMARY KEY,
    bank_id BIGINT NOT NULL REFERENCES banks(id),
    cik BIGINT NOT NULL,
    accession TEXT NOT NULL,
    form TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    report_date DATE NOT NULL,
    filed_date DATE NOT NULL,
    primary_document TEXT NOT NULL,
    document_url TEXT NOT NULL,
    index_url TEXT NOT NULL,
    local_path TEXT,
    document_sha256 CHAR(64),
    downloaded_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_sec_filings_bank_accession UNIQUE (bank_id, accession)
);
CREATE INDEX IF NOT EXISTS ix_sec_filings_bank_fiscal
    ON sec_filings (bank_id, fiscal_year);
