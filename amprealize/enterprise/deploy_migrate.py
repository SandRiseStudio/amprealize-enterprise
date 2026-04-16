"""Enterprise deploy migration.

Imported by ``amprealize.deploy_migrate`` when enterprise package is installed.
Provides data export/import/sync for deployment mode transitions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _get_cloud_client():
    """Get an authenticated cloud client."""
    from amprealize.enterprise.cloud_client import CloudClient
    from amprealize.config.loader import get_config

    cfg = get_config()
    client = CloudClient(cloud_url=cfg.deployment.cloud_url)
    return client


def export_data(*, path: str | None = None) -> dict[str, Any]:
    """Export all local data to a portable JSON file.

    Args:
        path: Output file path. Defaults to ~/.amprealize/data/export-<timestamp>.json.

    Returns:
        Dict with export metadata (path, record_count, timestamp).
    """
    from amprealize.config.loader import get_config

    cfg = get_config()
    timestamp = int(time.time())

    if path is None:
        export_dir = Path.home() / ".amprealize" / "data"
        export_dir.mkdir(parents=True, exist_ok=True)
        path = str(export_dir / f"export-{timestamp}.json")

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Collect exportable data from storage
    export_payload: dict[str, Any] = {
        "version": 1,
        "timestamp": timestamp,
        "source_mode": cfg.deployment.mode,
        "data": {},
    }

    # Export from configured storage backend
    backend = cfg.storage.backend if hasattr(cfg.storage, "backend") else "sqlite"

    if backend == "sqlite":
        sqlite_cfg = getattr(cfg.storage, "sqlite", None)
        db_path = getattr(sqlite_cfg, "path", None) if sqlite_cfg else None
        if db_path is None:
            db_path = str(Path(".amprealize") / "data" / "amprealize.db")

        db_file = Path(db_path).expanduser()
        if db_file.exists():
            import sqlite3

            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.cursor()
                # Get all table names
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic_%'"
                )
                tables = [row[0] for row in cursor.fetchall()]

                record_count = 0
                for table in tables:
                    cursor.execute(f"SELECT * FROM [{table}]")  # noqa: S608
                    rows = [dict(row) for row in cursor.fetchall()]
                    export_payload["data"][table] = rows
                    record_count += len(rows)
            finally:
                conn.close()

            export_payload["record_count"] = record_count
        else:
            export_payload["record_count"] = 0

    target.write_text(json.dumps(export_payload, indent=2, default=str), encoding="utf-8")

    return {
        "status": "success",
        "path": str(target),
        "record_count": export_payload.get("record_count", 0),
        "timestamp": timestamp,
    }


def import_data(*, path: str | None = None) -> dict[str, Any]:
    """Import data from a portable JSON file into local storage.

    Args:
        path: Input file path. If None, uses the most recent export.

    Returns:
        Dict with import metadata (record_count, tables_imported).
    """
    if path is None:
        export_dir = Path.home() / ".amprealize" / "data"
        exports = sorted(export_dir.glob("export-*.json"), reverse=True)
        if not exports:
            raise FileNotFoundError(
                "No export files found. Run 'amprealize deploy migrate export' first."
            )
        path = str(exports[0])

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Export file not found: {path}")

    payload = json.loads(source.read_text(encoding="utf-8"))

    if payload.get("version") != 1:
        raise ValueError(f"Unsupported export version: {payload.get('version')}")

    data = payload.get("data", {})
    from amprealize.config.loader import get_config

    cfg = get_config()
    backend = cfg.storage.backend if hasattr(cfg.storage, "backend") else "sqlite"

    record_count = 0
    tables_imported = []

    if backend == "sqlite":
        sqlite_cfg = getattr(cfg.storage, "sqlite", None)
        db_path = getattr(sqlite_cfg, "path", None) if sqlite_cfg else None
        if db_path is None:
            db_path = str(Path(".amprealize") / "data" / "amprealize.db")

        db_file = Path(db_path).expanduser()
        db_file.parent.mkdir(parents=True, exist_ok=True)

        import sqlite3

        conn = sqlite3.connect(str(db_file))
        try:
            cursor = conn.cursor()
            for table, rows in data.items():
                if not rows:
                    continue
                columns = list(rows[0].keys())
                placeholders = ", ".join("?" for _ in columns)
                col_names = ", ".join(f"[{c}]" for c in columns)

                for row in rows:
                    values = [row.get(c) for c in columns]
                    cursor.execute(
                        f"INSERT OR REPLACE INTO [{table}] ({col_names}) "  # noqa: S608
                        f"VALUES ({placeholders})",
                        values,
                    )
                    record_count += 1
                tables_imported.append(table)
            conn.commit()
        finally:
            conn.close()

    return {
        "status": "success",
        "source": str(source),
        "record_count": record_count,
        "tables_imported": tables_imported,
    }


def sync_to_cloud() -> dict[str, Any]:
    """Sync local data to the Amprealize cloud."""
    # Export locally first
    export_result = export_data()
    export_path = export_result["path"]

    # Upload to cloud
    client = _get_cloud_client()
    data = Path(export_path).read_bytes()
    upload_result = client.upload(
        key=f"sync/{Path(export_path).name}",
        data=data,
        content_type="application/json",
        metadata={"type": "sync", "direction": "up"},
    )

    return {
        "status": "success",
        "export": export_result,
        "upload": upload_result,
    }


def sync_from_cloud() -> dict[str, Any]:
    """Sync data from the Amprealize cloud to local storage."""
    client = _get_cloud_client()

    # Download latest sync file
    data = client.download(key="sync/latest.json")

    # Write to temp file and import
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".json", delete=False
    ) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        import_result = import_data(path=tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {
        "status": "success",
        "import": import_result,
    }


def migrate_deployment(
    *,
    from_mode: str,
    to_mode: str,
) -> dict[str, Any]:
    """Full deployment migration between modes.

    Exports data from the current storage, switches mode, and imports
    into the new storage backend.

    Args:
        from_mode: Current deployment mode.
        to_mode: Target deployment mode.

    Returns:
        Dict with migration results.
    """
    results: dict[str, Any] = {
        "from_mode": from_mode,
        "to_mode": to_mode,
        "steps": [],
    }

    # Step 1: Export from current mode
    export_result = export_data()
    results["steps"].append({"step": "export", "result": export_result})

    # Step 2: If syncing to cloud, upload
    if to_mode in ("cloud", "hybrid"):
        try:
            sync_result = sync_to_cloud()
            results["steps"].append({"step": "sync_to_cloud", "result": sync_result})
        except Exception as e:
            results["steps"].append({
                "step": "sync_to_cloud",
                "result": {"status": "error", "error": str(e)},
            })

    # Step 3: If syncing from cloud, download
    if from_mode in ("cloud", "hybrid") and to_mode == "local":
        try:
            sync_result = sync_from_cloud()
            results["steps"].append({"step": "sync_from_cloud", "result": sync_result})
        except Exception as e:
            results["steps"].append({
                "step": "sync_from_cloud",
                "result": {"status": "error", "error": str(e)},
            })

    results["status"] = "success"
    return results
