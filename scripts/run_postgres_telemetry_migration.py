#!/usr/bin/env python3
"""Apply the PostgreSQL telemetry warehouse migration.

This script materialises the tables, indexes, and metric views described in
``TELEMETRY_SCHEMA.md``.  It is the canonical automation for bringing a fresh
PostgreSQL instance in line with the warehouse contract defined in
``schema/migrations/014_create_telemetry_warehouse_timescale.sql``.  The implementation
prioritises reproducibility and aligns with ``behavior_instrument_metrics_pipeline``
by ensuring the telemetry pipeline is ready for KPI projection.

Usage::

    ./scripts/run_postgres_telemetry_migration.py --dsn postgresql://user:pass@localhost/db

When the ``--dsn`` flag is omitted, the script falls back to the
``AMPREALIZE_TELEMETRY_PG_DSN`` environment variable.  Pass ``--dry-run`` to see
which statements would run without executing them.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MIGRATION = REPO_ROOT / "schema" / "migrations" / "014_create_telemetry_warehouse_timescale.sql"
TELEMETRY_ALEMBIC_INI = REPO_ROOT / "alembic.telemetry.ini"
LEGACY_MIGRATION_PATHS = {
    REPO_ROOT / "schema" / "migrations" / "001_create_telemetry_warehouse.sql",
    DEFAULT_MIGRATION,
}

from _postgres_migration_utils import (
    discover_dsn,
    execute_statements,
    load_migration,
    split_sql_statements,
)


def _run_telemetry_alembic(dsn: str) -> int:
    """Apply the canonical telemetry Alembic migrations."""
    if not TELEMETRY_ALEMBIC_INI.is_file():
        print(f"❌ Telemetry Alembic config not found: {TELEMETRY_ALEMBIC_INI}")
        return 1

    env = os.environ.copy()
    env["TELEMETRY_DATABASE_URL"] = dsn

    cmd = [
        sys.executable,
        "-m",
        "alembic",
        "-c",
        str(TELEMETRY_ALEMBIC_INI),
        "upgrade",
        "head",
    ]

    print("Applying telemetry Alembic migrations using canonical migrations_telemetry/ history")
    return subprocess.call(cmd, cwd=str(REPO_ROOT), env=env)


def _dry_run_telemetry_alembic(dsn: str) -> int:
    """Describe the canonical telemetry Alembic command without executing it."""
    print("-- Dry run --")
    print("Telemetry SQL migration file is unavailable; would run canonical Alembic telemetry migrations:")
    print(
        f"TELEMETRY_DATABASE_URL={dsn} {sys.executable} -m alembic -c {TELEMETRY_ALEMBIC_INI} upgrade head"
    )
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply PostgreSQL telemetry warehouse migration")
    parser.add_argument("--dsn", help="PostgreSQL DSN (overrides AMPREALIZE_TELEMETRY_PG_DSN)")
    parser.add_argument(
        "--migration",
        type=Path,
        default=None,
        help=(
            "Optional path to a legacy telemetry SQL migration file. "
            f"When omitted, the script applies the canonical Alembic telemetry migrations from {TELEMETRY_ALEMBIC_INI.relative_to(REPO_ROOT)}"
        ),
    )
    parser.add_argument("--connect-timeout", type=int, default=10, help="Connection timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Print statements without executing them")

    args = parser.parse_args(argv)

    dsn = discover_dsn(args.dsn, "AMPREALIZE_TELEMETRY_PG_DSN")

    migration_path = args.migration
    if migration_path is None:
        if DEFAULT_MIGRATION.is_file():
            migration_path = DEFAULT_MIGRATION
        else:
            if args.dry_run:
                return _dry_run_telemetry_alembic(dsn)
            return _run_telemetry_alembic(dsn)

    if not migration_path.is_file():
        if migration_path in LEGACY_MIGRATION_PATHS:
            print(
                f"⚠️ Legacy telemetry SQL migration not found: {migration_path}\n"
                "   Falling back to Alembic telemetry migrations instead."
            )
            if args.dry_run:
                return _dry_run_telemetry_alembic(dsn)
            return _run_telemetry_alembic(dsn)

        print(f"❌ Migration file not found: {migration_path}")
        return 1

    migration_sql = load_migration(migration_path)
    statements = split_sql_statements(migration_sql)

    if not statements:
        print("⚠️ No statements found in migration; nothing to do.")
        return 0

    if args.dry_run:
        print("-- Dry run --")
        for index, statement in enumerate(statements, start=1):
            print(f"[{index}] {statement.strip()}\n")
        return 0

    print(f"Applying telemetry migration using DSN: {dsn}")
    print(f"Executing {len(statements)} statements from {migration_path}")

    execute_statements(dsn, statements, connect_timeout=args.connect_timeout)

    print("✅ Migration applied successfully.")
    print(
        "📌 Remember to run 'amprealize record-action' to capture this deployment in the audit log "
        "per behavior_replayable_actions."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
