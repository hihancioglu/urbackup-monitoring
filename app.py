from flask import Flask, render_template, jsonify
from datetime import datetime

from urbackup_client import UrBackupClient
import os

app = Flask(__name__)

ur = UrBackupClient(
    base = os.getenv("URB_URL"),
    username = os.getenv("URB_USER"),
    password = os.getenv("URB_PASS")
)

THRESHOLD_WARNING = 24
THRESHOLD_CRITICAL = 48


@app.route("/")
def dashboard():
    usage = ur.get_usage().get("usage", [])
    status = ur.get_status().get("status", [])
    progress = ur.get_progress()

    now = datetime.now()

    status_map = {c["name"]: c for c in status}
    progress_map = {p["name"]: p for p in progress}

    clients = []

    for c in usage:
        name = c["name"]
        size = c.get("used", 0)

        st = status_map.get(name, {})

        last_ts = st.get("lastbackup")
        online = st.get("online", False)
        file_ok = st.get("file_ok", True)
        issues = st.get("last_filebackup_issues", 0)

        if last_ts:
            last_dt = datetime.fromtimestamp(last_ts)
            diff_hours = (now - last_dt).total_seconds() / 3600
        else:
            last_dt = None
            diff_hours = None

        # STATUS LOGIC
        if not last_ts:
            health = "danger"
            text = "No backup"
        elif diff_hours > THRESHOLD_CRITICAL:
            health = "danger"
            text = f"{int(diff_hours)}h"
        elif diff_hours > THRESHOLD_WARNING:
            health = "warning"
            text = f"{int(diff_hours)}h"
        elif not file_ok or issues > 0:
            health = "warning"
            text = "Issue"
        else:
            health = "success"
            text = f"{int(diff_hours)}h"

        # ACTIVE JOB
        active = name in progress_map

        clients.append({
            "name": name,
            "size": round(size / (1024**3), 2),
            "last_backup": last_dt,
            "health": health,
            "status_text": text,
            "online": online,
            "active": active
        })

    return render_template("dashboard.html", clients=clients)


@app.route("/debug")
def debug():
    usage = ur.get_usage()
    status = ur.get_status()
    progress = ur.get_progress()

    return {
        "usage_keys": list(usage.keys()) if isinstance(usage, dict) else str(type(usage)),
        "status_keys": list(status.keys()) if isinstance(status, dict) else str(type(status)),
        "progress_count": len(progress) if isinstance(progress, list) else -1,
        "usage": usage,
        "status": status,
        "progress": progress,
    }

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888)
