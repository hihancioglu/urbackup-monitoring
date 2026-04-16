import os

from flask import Flask, abort, render_template, request

from main import MonitoringOrchestrator

app = Flask(__name__)
orchestrator = MonitoringOrchestrator()
sync_interval_seconds = int(os.getenv("URB_SYNC_INTERVAL_SECONDS", "60"))
orchestrator.start_background_sync(interval_seconds=sync_interval_seconds)


@app.route("/")
def dashboard():
    clients = orchestrator.collect_dashboard_clients()
    return render_template("dashboard.html", clients=clients)


@app.route("/logs")
def logs():
    selected_client_id = request.args.get("client_id", "").strip()
    query = request.args.get("q", "").strip()
    page = request.args.get("page", "1")

    try:
        page_num = max(1, int(page))
    except (TypeError, ValueError):
        page_num = 1

    per_page = 50
    clients = orchestrator.collect_log_clients()
    log_page = orchestrator.collect_backup_logs(
        client_id=selected_client_id,
        query=query,
        page=page_num,
        per_page=per_page,
    )
    client_overview = None
    if selected_client_id:
        try:
            client_overview = orchestrator.collect_client_log_overview(int(selected_client_id))
        except (TypeError, ValueError):
            client_overview = None

    return render_template(
        "logs.html",
        clients=clients,
        logs=log_page["items"],
        page=log_page["page"],
        per_page=log_page["per_page"],
        total=log_page["total"],
        total_pages=log_page["total_pages"],
        selected_client_id=selected_client_id,
        query=query,
        client_overview=client_overview,
    )


@app.route("/logs/<int:log_id>")
def log_detail(log_id: int):
    log_item = orchestrator.collect_backup_log_detail(log_id)
    if not log_item:
        abort(404)
    return render_template("log_detail.html", log=log_item)


@app.route("/debug")
def debug():
    usage = orchestrator.api.usage()
    status = orchestrator.api.status()
    progress = orchestrator.api.progress()

    return {
        "debug_enabled": orchestrator.debug_enabled,
        "usage_keys": list(usage.keys()) if isinstance(usage, dict) else str(type(usage)),
        "status_keys": list(status.keys()) if isinstance(status, dict) else str(type(status)),
        "progress_count": len(progress) if isinstance(progress, list) else -1,
        "usage": usage,
        "status": status,
        "progress": progress,
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888)
