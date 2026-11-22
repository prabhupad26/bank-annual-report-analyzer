-- Form 20-F and amendment index by bank and fiscal year.
SELECT b.slug AS bank, s.fiscal_year, s.form, s.filed_date, s.accession,
       s.document_url, s.index_url, s.local_path, s.document_sha256
FROM sec_filings s
JOIN banks b ON b.id = s.bank_id
WHERE s.fiscal_year BETWEEN 2021 AND 2025
ORDER BY b.slug, s.fiscal_year, s.filed_date;

-- Confirm coverage by institution and year.
SELECT b.slug, s.fiscal_year, COUNT(*) AS filings,
       COUNT(*) FILTER (WHERE s.local_path IS NOT NULL) AS downloaded
FROM sec_filings s
JOIN banks b ON b.id = s.bank_id
GROUP BY b.slug, s.fiscal_year
ORDER BY b.slug, s.fiscal_year;
