import os
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


_load_local_dotenv()


class MonitoringOrchestrator:
    def __init__(self, api=None, analyzer=None, store=None):
        base_url = _get_env("URB_URL", "URBACKUP_URL")
        username = _get_env("URB_USER", "URBACKUP_USER")
        password = _get_env("URB_PASS", "URBACKUP_PASS")
        db_path = _get_env("URB_DB_PATH", "URBACKUP_DB_PATH") or "data/urbackup_monitoring.db"

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

    def sync_lastacts_to_db(self):
        progress_payload = self.api.progress(include_lastacts=True, raw=True)
        lastacts = progress_payload.get("lastacts", [])

        status_map = self._build_status_map()
        now = datetime.now()
        synced = 0

        for act in lastacts:
            log_id = act.get("logid")
            if not log_id:
                continue

            client_name = act.get("name") or act.get("clientname")
            status = status_map.get(client_name, {})
            health, text, _ = self.analyzer.compute_health(
                last_ts=status.get("lastbackup"),
                file_ok=status.get("file_ok", True),
                issues=status.get("last_filebackup_issues", 0),
                now=now,
            )

            self.store.upsert_client(
                {
                    "client_name": client_name,
                    "client_id": act.get("id") or status.get("id"),
                    "online": status.get("online", False),
                    "last_backup_ts": status.get("lastbackup"),
                    "health": health,
                    "status_text": text,
                }
            )

            if self.store.has_backup_log(log_id):
                continue

            detail_payload = self.api.logs(log_id=log_id)
            detail_lines = detail_payload.get("logs", [])
            parsed = self.analyzer.parse_log("\n".join(map(str, detail_lines)))

            self.store.insert_backup_log(
                log_id=log_id,
                client_name=client_name,
                client_id=act.get("id") or status.get("id"),
                action=act.get("action") or act.get("details") or act.get("pcdone"),
                created_ts=act.get("time") or act.get("starttime"),
                detail_lines=[str(line) for line in detail_lines],
                lastact_payload=act,
                detail_payload=detail_payload,
                has_error=parsed.get("has_error", False),
                has_warning=parsed.get("has_warning", False),
            )
            synced += 1

        return {
            "lastacts_total": len(lastacts),
            "new_logs_synced": synced,
        }


if __name__ == "__main__":
    orchestrator = MonitoringOrchestrator()
    result = orchestrator.sync_lastacts_to_db()
    print(result)
