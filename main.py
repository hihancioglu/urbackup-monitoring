import os
import threading
import time
from datetime import datetime
from pathlib import Path

from analyzer import Analyzer
from storage import MonitoringStore
from urbackup_api import UrBackupAPI


def _load_local_dotenv(path: str = ".env") -> None:
    env_file = Path(path)
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def _get_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _default_db_path() -> str:
    data_mount = Path("/data")
    if data_mount.exists() and data_mount.is_dir():
        return str(data_mount / "urbackup_monitoring.db")
    return "data/urbackup_monitoring.db"


_load_local_dotenv()


class MonitoringOrchestrator:
    def __init__(self, api=None, analyzer=None, store=None):
        base_url = _get_env("URB_URL", "URBACKUP_URL")
        username = _get_env("URB_USER", "URBACKUP_USER")
        password = _get_env("URB_PASS", "URBACKUP_PASS")
        db_path = _get_env("URB_DB_PATH", "URBACKUP_DB_PATH") or _default_db_path()

        if api is None and not base_url:
            raise ValueError(
                "Missing UrBackup URL. Set URB_URL (or URBACKUP_URL) in your environment/.env file."
            )

        self.api = api or UrBackupAPI(
            base_url=base_url,
            username=username,
            password=password,
        )
        self.analyzer = analyzer or Analyzer()
        self.store = store or MonitoringStore(db_path=db_path)
        self._sync_thread = None
        self._sync_stop = threading.Event()

    @staticmethod
    def _extract_log_id(item: dict) -> int | None:
        for key in ("logid", "log_id", "logId"):
            value = item.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _extract_client_id(item: dict) -> int | None:
        for key in ("clientid", "client_id", "id"):
            value = item.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def _fetch_historical_activities(
        self,
        since_log_id: int,
        *,
        max_pages: int | None = None,
    ) -> list[dict]:
        if max_pages is None:
            max_pages = int(os.getenv("URB_HISTORY_MAX_PAGES", "200"))

        activities = []
        offset = 0
        fetched_pages = 0

        while True:
            if max_pages > 0 and fetched_pages >= max_pages:
                break

            payload = self.api.logs(ll=offset)
            page_logs = payload.get("logs", [])
            fetched_pages += 1

            if not isinstance(page_logs, list) or not page_logs:
                break

            reached_synced_boundary = False
            for item in page_logs:
                if not isinstance(item, dict):
                    continue
                log_id = self._extract_log_id(item)
                if log_id is None:
                    continue

                if since_log_id and log_id <= since_log_id:
                    reached_synced_boundary = True
                    continue

                activities.append(item)

            if reached_synced_boundary:
                break

            offset += len(page_logs)

        return activities

    def _build_status_map(self):
        status = self.api.status().get("status", [])
        return {item.get("name"): item for item in status}

    def collect_dashboard_clients(self):
        usage = self.api.usage().get("usage", [])
        progress = self.api.progress()

        now = datetime.now()
        status_map = self._build_status_map()
        progress_map = {p["name"]: p for p in progress}

        clients = []
        for usage_item in usage:
            name = usage_item["name"]
            size = usage_item.get("used", 0)

            st = status_map.get(name, {})
            health, text, last_dt = self.analyzer.compute_health(
                last_ts=st.get("lastbackup"),
                file_ok=st.get("file_ok", True),
                issues=st.get("last_filebackup_issues", 0),
                now=now,
            )

            clients.append(
                {
                    "name": name,
                    "size": round(size / (1024**3), 2),
                    "last_backup": last_dt,
                    "health": health,
                    "status_text": text,
                    "online": st.get("online", False),
                    "active": name in progress_map,
                }
            )

        return clients

    def collect_log_clients(self):
        return self.store.list_log_clients()

    def collect_client_log_overview(self, client_id: int):
        return self.store.get_client_log_overview(client_id)

    def collect_backup_logs(self, *, client_id=None, query=None, page: int = 1, per_page: int = 50):
        parsed_client_id = None
        if client_id not in (None, "", "all"):
            try:
                parsed_client_id = int(client_id)
            except (TypeError, ValueError):
                parsed_client_id = None

        return self.store.get_backup_logs_page(
            client_id=parsed_client_id,
            query=query,
            page=page,
            per_page=per_page,
        )

    def collect_backup_log_detail(self, log_id: int):
        return self.store.get_backup_log_detail(log_id)

    @staticmethod
    def _normalize_detail_lines(detail_payload: dict) -> list[str]:
        if not isinstance(detail_payload, dict):
            return []

        raw_logs = detail_payload.get("logs", [])
        if not isinstance(raw_logs, list):
            return []

        normalized = []
        for entry in raw_logs:
            if isinstance(entry, dict):
                text = (
                    entry.get("msg")
                    or entry.get("message")
                    or entry.get("text")
                    or entry.get("details")
                )
                if not text:
                    continue
                at = entry.get("time")
                normalized.append(f"[{at}] {text}" if at else str(text))
            elif entry is not None:
                text = str(entry).strip()
                if text:
                    normalized.append(text)

        return normalized

    def _should_run_initial_full_sync(self, last_processed_log_id: int) -> bool:
        if last_processed_log_id > 0:
            return False
        return not self.store.has_any_backup_logs()

    def sync_lastacts_to_db(self, *, force_full_history: bool = False):
        progress_payload = self.api.progress(include_lastacts=True, raw=True)
        lastacts = progress_payload.get("lastacts", [])
        last_processed_log_id = self.store.get_sync_state_int("last_processed_log_id", default=0)
        effective_force_full_history = force_full_history or self._should_run_initial_full_sync(
            last_processed_log_id
        )
        if effective_force_full_history:
            last_processed_log_id = 0

        historical_acts = self._fetch_historical_activities(
            since_log_id=last_processed_log_id,
            max_pages=0 if effective_force_full_history else None,
        )

        combined = {}
        for act in [*historical_acts, *lastacts]:
            if not isinstance(act, dict):
                continue
            log_id = self._extract_log_id(act)
            if log_id is None:
                continue
            combined[log_id] = act

        status_map = self._build_status_map()
        status_by_id = {item.get("id"): item for item in status_map.values() if item.get("id") is not None}
        now = datetime.now()
        synced = 0
        max_seen_log_id = last_processed_log_id

        for log_id in sorted(combined):
            act = combined[log_id]
            max_seen_log_id = max(max_seen_log_id, log_id)

            client_name = act.get("name") or act.get("clientname")
            client_id = self._extract_client_id(act)
            status = status_map.get(client_name, {})
            if not status:
                status = status_by_id.get(client_id) or {}
            health, text, _ = self.analyzer.compute_health(
                last_ts=status.get("lastbackup"),
                file_ok=status.get("file_ok", True),
                issues=status.get("last_filebackup_issues", 0),
                now=now,
            )

            self.store.upsert_client(
                {
                    "client_name": client_name,
                    "client_id": client_id or status.get("id"),
                    "online": status.get("online", False),
                    "last_backup_ts": status.get("lastbackup"),
                    "health": health,
                    "status_text": text,
                }
            )

            if self.store.has_backup_log(log_id):
                continue

            detail_payload = self.api.logs(log_id=log_id)
            detail_lines = self._normalize_detail_lines(detail_payload)
            parsed = self.analyzer.parse_log("\n".join(map(str, detail_lines)))

            self.store.insert_backup_log(
                log_id=log_id,
                client_name=client_name,
                client_id=client_id or status.get("id"),
                action=act.get("action") or act.get("details") or act.get("pcdone"),
                created_ts=act.get("time") or act.get("starttime"),
                detail_lines=detail_lines,
                lastact_payload=act,
                detail_payload=detail_payload,
                has_error=parsed.get("has_error", False),
                has_warning=parsed.get("has_warning", False),
            )
            synced += 1

        if max_seen_log_id > last_processed_log_id:
            self.store.set_sync_state("last_processed_log_id", max_seen_log_id)

        return {
            "lastacts_total": len(lastacts),
            "historical_total": len(historical_acts),
            "new_logs_synced": synced,
            "last_processed_log_id": max_seen_log_id,
        }

    def _background_sync_loop(self, interval_seconds: int):
        while not self._sync_stop.is_set():
            try:
                self.sync_lastacts_to_db()
            except Exception as exc:
                print(f"[background-sync] sync failed: {exc}")

            self._sync_stop.wait(interval_seconds)

    def start_background_sync(self, interval_seconds: int = 60):
        if self._sync_thread and self._sync_thread.is_alive():
            return

        self._sync_stop.clear()
        self._sync_thread = threading.Thread(
            target=self._background_sync_loop,
            args=(interval_seconds,),
            name="urbackup-background-sync",
            daemon=True,
        )
        self._sync_thread.start()

    def stop_background_sync(self):
        self._sync_stop.set()
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=3)


if __name__ == "__main__":
    orchestrator = MonitoringOrchestrator()
    mode = (os.getenv("URB_SYNC_MODE") or "oneshot").strip().lower()

    if mode == "daemon":
        interval = int(os.getenv("URB_SYNC_INTERVAL_SECONDS", "60"))
        print(f"Starting background sync loop (interval={interval}s)")
        orchestrator.start_background_sync(interval_seconds=interval)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            orchestrator.stop_background_sync()
    else:
        result = orchestrator.sync_lastacts_to_db()
        print(result)
