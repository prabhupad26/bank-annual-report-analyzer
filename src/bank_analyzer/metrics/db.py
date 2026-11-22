"""PostgreSQL bootstrap and idempotent metric writes."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg

from bank_analyzer.config import BANKS
from bank_analyzer.metrics.providers import METRICS, MetricFact

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "storage"

UPSERT_FACT = """
INSERT INTO metric_observations
 (bank_id, metric_id, fiscal_year, value, currency, source_url, methodology,
  provider, source_concept, period_end, filing_date, accession, reported_unit)
VALUES (%s, %s, %s, %s, %s, %s, 'reported', %s, %s, %s, %s, %s, %s)
ON CONFLICT (bank_id, metric_id, fiscal_year, source_url, methodology)
DO UPDATE SET
 value = EXCLUDED.value,
 currency = EXCLUDED.currency,
 provider = EXCLUDED.provider,
 source_concept = EXCLUDED.source_concept,
 period_end = EXCLUDED.period_end,
 filing_date = EXCLUDED.filing_date,
 accession = EXCLUDED.accession,
 reported_unit = EXCLUDED.reported_unit,
 updated_at = now()
WHERE (
 metric_observations.value, metric_observations.currency,
 metric_observations.provider, metric_observations.source_concept,
 metric_observations.period_end, metric_observations.filing_date,
 metric_observations.accession, metric_observations.reported_unit
) IS DISTINCT FROM (
 EXCLUDED.value, EXCLUDED.currency, EXCLUDED.provider, EXCLUDED.source_concept,
 EXCLUDED.period_end, EXCLUDED.filing_date, EXCLUDED.accession, EXCLUDED.reported_unit
)
"""


def connect() -> psycopg.Connection:
    url = os.getenv("DATABASE_URL", "postgresql://bank:bank@localhost:5432/bank_reports")
    return psycopg.connect(url, connect_timeout=10)


def init_database(conn: psycopg.Connection) -> None:
    """Apply existing report schema first, then additive metrics migration."""
    for name in ("schema.sql", "metrics_migration.sql"):
        conn.execute((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    for code, (label, unit, description) in METRICS.items():
        conn.execute(
            """INSERT INTO metric_definitions (code, label, unit, description)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (code) DO UPDATE SET
                 label = EXCLUDED.label, unit = EXCLUDED.unit,
                 description = EXCLUDED.description""",
            (code, label, unit, description),
        )


def store_facts(conn: psycopg.Connection, bank: str, provider: str,
                facts: list[MetricFact]) -> int:
    """One transaction per bank should be committed by the caller."""
    conn.execute(
        """INSERT INTO banks (slug, name) VALUES (%s, %s)
           ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name""",
        (bank, BANKS[bank]),
    )
    bank_id = conn.execute("SELECT id FROM banks WHERE slug = %s", (bank,)).fetchone()[0]
    run_id = conn.execute(
        """INSERT INTO metric_ingestion_runs (bank_id, provider, status, facts_seen)
           VALUES (%s, %s, 'running', %s) RETURNING id""",
        (bank_id, provider, len(facts)),
    ).fetchone()[0]
    codes = {
        code: definition_id for code, definition_id in conn.execute(
            "SELECT code, id FROM metric_definitions"
        ).fetchall()
    }
    changed = 0
    for fact in facts:
        if fact.bank != bank or fact.provider != provider:
            raise ValueError("Bank/provider mismatch in ingestion data")
        changed += conn.execute(UPSERT_FACT, (
            bank_id, codes[fact.code], fact.year, fact.value, fact.currency,
            fact.source_url, fact.provider, fact.source_concept, fact.period_end,
            fact.filing_date, fact.accession, fact.reported_unit,
        )).rowcount
    conn.execute(
        """UPDATE metric_ingestion_runs
           SET finished_at = now(), status = %s, rows_changed = %s
           WHERE id = %s""",
        ("success" if facts else "empty", changed, run_id),
    )
    return changed


def show_metrics(conn: psycopg.Connection, bank: str, year: int | None = None) -> list[tuple]:
    query = """
        SELECT b.slug, o.fiscal_year, m.code, o.value, o.currency,
               o.provider, o.period_end, o.source_concept, o.source_url
        FROM metric_observations o
        JOIN banks b ON b.id = o.bank_id
        JOIN metric_definitions m ON m.id = o.metric_id
        WHERE b.slug = %s
    """
    params: list = [bank]
    if year is not None:
        query += " AND o.fiscal_year = %s"
        params.append(year)
    query += " ORDER BY o.fiscal_year DESC, m.code, o.provider"
    return conn.execute(query, params).fetchall()
