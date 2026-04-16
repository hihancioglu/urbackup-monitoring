import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable


class MonitoringStore:
    def __init__(self, db_path: str = "urbackup_monitoring.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    client_name TEXT PRIMARY KEY,
                    client_id INTEGER,
                    online INTEGER,
                    last_backup_ts INTEGER,
                    health TEXT,
                    status_text TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS backup_logs (
                    log_id INTEGER PRIMARY KEY,
                    client_name TEXT,
                    client_id INTEGER,
                    action TEXT,
                    created_ts INTEGER,
                    detail_text TEXT,
                    raw_lastact_json TEXT NOT NULL,
                    raw_detail_json TEXT NOT NULL,
                    has_error INTEGER NOT NULL,
                    has_warning INTEGER NOT NULL,
                    fetched_at TEXT NOT NULL,
                    FOREIGN KEY(client_name) REFERENCES clients(client_name)
                );
                """
            )

    def upsert_client(self, client_payload: dict):
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO clients (
                    client_name, client_id, online, last_backup_ts, health, status_text, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_name) DO UPDATE SET
                    client_id=excluded.client_id,
                    online=excluded.online,
                    last_backup_ts=excluded.last_backup_ts,
                    health=excluded.health,
                    status_text=excluded.status_text,
                    updated_at=excluded.updated_at
                """,
                (
                    client_payload.get("client_name"),
                    client_payload.get("client_id"),
                    1 if client_payload.get("online") else 0,
                    client_payload.get("last_backup_ts"),
                    client_payload.get("health"),
                    client_payload.get("status_text"),
                    now,
                ),
            )

    def has_backup_log(self, log_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM backup_logs WHERE log_id = ?",
                (log_id,),
            ).fetchone()
            return row is not None

    def insert_backup_log(
        self,
        *,
        log_id: int,
        client_name: str | None,
        client_id: int | None,
        action: str | None,
        created_ts: int | None,
        detail_lines: Iterable[str],
        lastact_payload: dict,
        detail_payload: dict,
        has_error: bool,
        has_warning: bool,
    ):
        fetched_at = datetime.utcnow().isoformat(timespec="seconds")
        detail_text = "\n".join(detail_lines)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO backup_logs (
                    log_id,
                    client_name,
                    client_id,
                    action,
                    created_ts,
                    detail_text,
                    raw_lastact_json,
                    raw_detail_json,
                    has_error,
                    has_warning,
                    fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    client_name,
                    client_id,
                    action,
                    created_ts,
                    detail_text,
                    json.dumps(lastact_payload, ensure_ascii=False),
                    json.dumps(detail_payload, ensure_ascii=False),
                    1 if has_error else 0,
                    1 if has_warning else 0,
                    fetched_at,
                ),
            )
