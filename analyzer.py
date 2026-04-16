from datetime import datetime


class Analyzer:
    def __init__(self, warning_hours: int = 24, critical_hours: int = 48):
        self.warning_hours = warning_hours
        self.critical_hours = critical_hours

    def compute_health(self, last_ts, file_ok=True, issues=0, now=None):
        now = now or datetime.now()

        if not last_ts:
            return "danger", "No backup", None

        last_dt = datetime.fromtimestamp(last_ts)
        diff_hours = (now - last_dt).total_seconds() / 3600

        if diff_hours > self.critical_hours:
            return "danger", f"{int(diff_hours)}h", last_dt
        if diff_hours > self.warning_hours:
            return "warning", f"{int(diff_hours)}h", last_dt
        if (not file_ok) or issues > 0:
            return "warning", "Issue", last_dt
        return "success", f"{int(diff_hours)}h", last_dt

    def parse_log(self, log_text: str):
        text = (log_text or "").lower()
        has_error = any(k in text for k in ["error", "failed", "exception"])
        has_warning = any(k in text for k in ["warning", "warn"])
        return {
            "has_error": has_error,
            "has_warning": has_warning,
        }

    def alert_logic(self, client_name: str, health: str, parsed_log=None):
        parsed_log = parsed_log or {"has_error": False, "has_warning": False}

        if health == "danger" or parsed_log.get("has_error"):
            return {
                "client": client_name,
                "level": "critical",
                "message": "Backup needs immediate attention",
            }

        if health == "warning" or parsed_log.get("has_warning"):
            return {
                "client": client_name,
                "level": "warning",
                "message": "Backup has warnings",
            }

        return {
            "client": client_name,
            "level": "ok",
            "message": "Backup healthy",
        }
