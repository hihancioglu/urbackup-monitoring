import os
from datetime import datetime
from pathlib import Path

from analyzer import Analyzer
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
    def __init__(self, api=None, analyzer=None):
        base_url = _get_env("URB_URL", "URBACKUP_URL")
        username = _get_env("URB_USER", "URBACKUP_USER")
        password = _get_env("URB_PASS", "URBACKUP_PASS")

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

    def collect_dashboard_clients(self):
        usage = self.api.usage().get("usage", [])
        status = self.api.status().get("status", [])
        progress = self.api.progress()

        now = datetime.now()
        status_map = {c["name"]: c for c in status}
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
