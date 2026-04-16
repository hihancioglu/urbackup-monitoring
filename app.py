from flask import Flask, render_template

from main import MonitoringOrchestrator

app = Flask(__name__)
orchestrator = MonitoringOrchestrator()


@app.route("/")
def dashboard():
    clients = orchestrator.collect_dashboard_clients()
    return render_template("dashboard.html", clients=clients)


@app.route("/debug")
def debug():
    usage = orchestrator.api.usage()
    status = orchestrator.api.status()
    progress = orchestrator.api.progress()

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
