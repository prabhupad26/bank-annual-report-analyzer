CREATE TABLE IF NOT EXISTS banks (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id BIGSERIAL PRIMARY KEY,
    bank_id BIGINT NOT NULL REFERENCES banks(id),
    fiscal_year INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    sha256 CHAR(64),
    downloaded_at TIMESTAMPTZ,
    UNIQUE(bank_id, fiscal_year, source_url)
);
CREATE TABLE IF NOT EXISTS report_pages (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL CHECK (page_number > 0),
    markdown TEXT NOT NULL,
    UNIQUE(report_id, page_number)
);
CREATE TABLE IF NOT EXISTS metric_definitions (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    unit TEXT,
    description TEXT
);
CREATE TABLE IF NOT EXISTS metric_observations (
    id BIGSERIAL PRIMARY KEY,
    bank_id BIGINT NOT NULL REFERENCES banks(id),
    metric_id BIGINT NOT NULL REFERENCES metric_definitions(id),
    fiscal_year INTEGER NOT NULL,
    value NUMERIC NOT NULL,
    currency CHAR(3),
    source_url TEXT NOT NULL,
    source_report_id BIGINT REFERENCES reports(id),
    source_page INTEGER,
    methodology TEXT NOT NULL DEFAULT 'reported',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(bank_id, metric_id, fiscal_year, source_url, methodology)
);
CREATE INDEX IF NOT EXISTS ix_observations_bank_year ON metric_observations(bank_id, fiscal_year);
CREATE INDEX IF NOT EXISTS ix_reports_bank_year ON reports(bank_id, fiscal_year);
