-- Additive migration for the pre-existing metric_observations table.
-- Rerunnable; no existing reports or observations are deleted.
ALTER TABLE metric_observations ADD COLUMN IF NOT EXISTS provider TEXT;
ALTER TABLE metric_observations ADD COLUMN IF NOT EXISTS source_concept TEXT;
ALTER TABLE metric_observations ADD COLUMN IF NOT EXISTS period_end DATE;
ALTER TABLE metric_observations ADD COLUMN IF NOT EXISTS filing_date DATE;
ALTER TABLE metric_observations ADD COLUMN IF NOT EXISTS accession TEXT;
ALTER TABLE metric_observations ADD COLUMN IF NOT EXISTS reported_unit TEXT;

CREATE INDEX IF NOT EXISTS ix_metric_obs_provider_year
    ON metric_observations(provider, fiscal_year);
CREATE INDEX IF NOT EXISTS ix_metric_obs_bank_metric_year
    ON metric_observations(bank_id, metric_id, fiscal_year);

CREATE TABLE IF NOT EXISTS metric_ingestion_runs (
    id BIGSERIAL PRIMARY KEY,
    bank_id BIGINT NOT NULL REFERENCES banks(id),
    provider TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'empty', 'error')),
    facts_seen INTEGER NOT NULL DEFAULT 0,
    rows_changed INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);
