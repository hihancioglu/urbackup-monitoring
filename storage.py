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

                CREATE TABLE IF NOT EXISTS sync_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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

    def has_any_backup_logs(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM backup_logs LIMIT 1").fetchone()
            return row is not None

    def get_sync_state(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_value FROM sync_state WHERE state_key = ?",
                (key,),
            ).fetchone()
            if not row:
                return default
            return row["state_value"]

    def get_sync_state_int(self, key: str, default: int = 0) -> int:
        value = self.get_sync_state(key)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def set_sync_state(self, key: str, value: str | int):
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sync_state (state_key, state_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    state_value=excluded.state_value,
                    updated_at=excluded.updated_at
                """,
                (key, str(value), now),
            )

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

    def list_log_clients(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    b.client_id AS client_id,
                    b.client_name AS client_name,
                    COUNT(*) AS log_count,
                    MAX(b.created_ts) AS last_log_ts
                FROM backup_logs b
                WHERE b.client_name IS NOT NULL AND b.client_name != ''
                GROUP BY b.client_id, b.client_name
                ORDER BY client_name COLLATE NOCASE
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_client_log_overview(self, client_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    client_id,
                    MIN(client_name) AS client_name,
                    COUNT(*) AS total_logs,
                    SUM(CASE WHEN has_error = 1 THEN 1 ELSE 0 END) AS error_logs,
                    SUM(CASE WHEN has_warning = 1 THEN 1 ELSE 0 END) AS warning_logs,
                    MAX(created_ts) AS last_log_ts
                FROM backup_logs
                WHERE client_id = ?
                GROUP BY client_id
                """,
                (client_id,),
            ).fetchone()

            if not row:
                return None

            return dict(row)

    def get_backup_log_detail(self, log_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
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
                FROM backup_logs
                WHERE log_id = ?
                """,
                (log_id,),
            ).fetchone()

        if not row:
            return None

        created_at = None
        created_ts = row["created_ts"]
        if created_ts:
            try:
                created_at = datetime.fromtimestamp(int(created_ts))
            except (TypeError, ValueError, OSError):
                created_at = None

        raw_lastact_json = row["raw_lastact_json"] or "{}"
        raw_detail_json = row["raw_detail_json"] or "{}"
        try:
            lastact_payload = json.loads(raw_lastact_json)
        except (TypeError, json.JSONDecodeError):
            lastact_payload = {}
        try:
            detail_payload = json.loads(raw_detail_json)
        except (TypeError, json.JSONDecodeError):
            detail_payload = {}

        detail_messages = []
        payload_logs = detail_payload.get("logs", []) if isinstance(detail_payload, dict) else []
        if isinstance(payload_logs, list):
            for item in payload_logs:
                if isinstance(item, dict):
                    text = (
                        item.get("msg")
                        or item.get("message")
                        or item.get("text")
                        or item.get("details")
                    )
                    if not text:
                        continue
                    at = item.get("time")
                    detail_messages.append(f"[{at}] {text}" if at else str(text))
                elif item is not None:
                    text = str(item).strip()
                    if text:
                        detail_messages.append(text)

        if not detail_messages:
            detail_messages = [line for line in (row["detail_text"] or "").splitlines() if line.strip()]

        return {
            "log_id": row["log_id"],
            "client_name": row["client_name"],
            "client_id": row["client_id"],
            "action": row["action"],
            "created_ts": created_ts,
            "created_at": created_at,
            "detail_text": row["detail_text"] or "",
            "lastact_payload": lastact_payload,
            "detail_payload": detail_payload,
            "detail_messages": detail_messages,
            "has_error": bool(row["has_error"]),
            "has_warning": bool(row["has_warning"]),
            "fetched_at": row["fetched_at"],
        }

    def get_backup_logs_page(
        self,
        *,
        client_id: int | None = None,
        query: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        safe_page = max(1, int(page))
        safe_per_page = max(1, int(per_page))
        offset = (safe_page - 1) * safe_per_page

        where_parts = []
        params: list = []

        if client_id is not None:
            where_parts.append("client_id = ?")
            params.append(client_id)

        search = (query or "").strip()
        if search:
            where_parts.append("(client_name LIKE ? OR action LIKE ? OR detail_text LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        with self._connect() as conn:
            count_row = conn.execute(
                f"SELECT COUNT(*) AS total FROM backup_logs {where_sql}",
                params,
            ).fetchone()
            total = int(count_row["total"]) if count_row else 0

            rows = conn.execute(
                f"""
                SELECT
                    log_id,
                    client_name,
                    client_id,
                    action,
                    created_ts,
                    detail_text,
                    has_error,
                    has_warning
                FROM backup_logs
                {where_sql}
                ORDER BY created_ts DESC, log_id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, safe_per_page, offset],
            ).fetchall()

        items = []
        for row in rows:
            created_ts = row["created_ts"]
            created_at = None
            if created_ts:
                try:
                    created_at = datetime.fromtimestamp(int(created_ts))
                except (TypeError, ValueError, OSError):
                    created_at = None
            detail_text = row["detail_text"] or ""
            items.append(
                {
                    "log_id": row["log_id"],
                    "client_name": row["client_name"],
                    "client_id": row["client_id"],
                    "action": row["action"],
                    "created_ts": created_ts,
                    "created_at": created_at,
                    "detail_text": detail_text,
                    "detail_preview": detail_text[:180],
                    "has_error": bool(row["has_error"]),
                    "has_warning": bool(row["has_warning"]),
                }
            )

        total_pages = (total + safe_per_page - 1) // safe_per_page if total else 1
        return {
            "items": items,
            "total": total,
            "page": safe_page,
            "per_page": safe_per_page,
            "total_pages": total_pages,
        }
