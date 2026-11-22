-- Choose the reporting year and bank slug for annual metrics.
SELECT b.name AS bank, o.fiscal_year, d.code, d.label,
       o.value, o.currency, o.provider, o.period_end,
       o.source_concept, o.source_url, o.filing_date
FROM metric_observations o
JOIN banks b ON b.id = o.bank_id
JOIN metric_definitions d ON d.id = o.metric_id
WHERE b.slug = 'deutsche_bank'
  AND o.fiscal_year BETWEEN 2021 AND 2025
ORDER BY o.fiscal_year, d.code, o.provider;

-- Compare assets across banks and years; NEVER add currencies without FX conversion.
SELECT b.slug, o.fiscal_year, o.value, o.currency, o.provider, o.source_url
FROM metric_observations o
JOIN banks b ON b.id = o.bank_id
JOIN metric_definitions d ON d.id = o.metric_id
WHERE d.code = 'total_assets'
ORDER BY o.fiscal_year DESC, b.slug, o.provider;

-- Check coverage (no fabricated zeros for missing source observations).
SELECT b.slug, o.fiscal_year, o.provider, COUNT(*) AS available_metrics
FROM metric_observations o
JOIN banks b ON b.id = o.bank_id
GROUP BY b.slug, o.fiscal_year, o.provider
ORDER BY b.slug, o.fiscal_year DESC, o.provider;

-- Detect provider disagreements for a metric/year. Compare only like currencies.
SELECT b.slug, o.fiscal_year, d.code, o.currency,
       MIN(o.value) AS min_reported, MAX(o.value) AS max_reported
FROM metric_observations o
JOIN banks b ON b.id = o.bank_id
JOIN metric_definitions d ON d.id = o.metric_id
GROUP BY b.slug, o.fiscal_year, d.code, o.currency
HAVING COUNT(DISTINCT o.provider) > 1
   AND MIN(o.value) <> MAX(o.value)
ORDER BY b.slug, o.fiscal_year DESC;

-- Review latest sync attempts.
SELECT b.slug, r.provider, r.started_at, r.status,
       r.facts_seen, r.rows_changed, r.error_message
FROM metric_ingestion_runs r
JOIN banks b ON b.id = r.bank_id
ORDER BY r.started_at DESC LIMIT 50;
