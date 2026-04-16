import os
from datetime import datetime

from analyzer import Analyzer
from urbackup_api import UrBackupAPI


class MonitoringOrchestrator:
    def __init__(self, api=None, analyzer=None):
        self.api = api or UrBackupAPI(
            base_url=os.getenv("URB_URL"),
            username=os.getenv("URB_USER"),
            password=os.getenv("URB_PASS"),
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
