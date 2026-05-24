"""
Determines which ATMs need alerts based on current status and thresholds.
Returns only NEW alerts (not already active) to prevent duplicate notifications.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

import db


@dataclass
class Alert:
    atm_id: str
    atm_name: str
    alert_type: str   # OFFLINE | LOW_CASH | HARDWARE_FAULT | SLA_BREACH
    detail: str


def check_alerts(atms: list[dict], thresholds: dict) -> list[Alert]:
    new_alerts: list[Alert] = []
    cash_threshold = thresholds.get("cash_low_percent", 15)
    sla_minutes = thresholds.get("sla_breach_minutes", 60)

    for atm in atms:
        atm_id = str(atm["id"])
        name = atm.get("name", atm_id)
        status = atm.get("status", "unknown")
        cash_pct = atm.get("cash_percent")
        error_code = atm.get("error_code", "")

        # --- OFFLINE ---
        if status == "offline":
            if not db.is_active(atm_id, "OFFLINE"):
                db.open_alert(atm_id, "OFFLINE")
                new_alerts.append(Alert(atm_id, name, "OFFLINE", "ATM is not reachable"))
            # --- SLA_BREACH ---
            first_down = db.get_first_triggered_at(atm_id, "OFFLINE")
            if first_down:
                minutes_down = (datetime.now(timezone.utc) - first_down.replace(tzinfo=timezone.utc)).total_seconds() / 60
                if minutes_down >= sla_minutes and not db.is_active(atm_id, "SLA_BREACH"):
                    db.open_alert(atm_id, "SLA_BREACH")
                    new_alerts.append(Alert(
                        atm_id, name, "SLA_BREACH",
                        f"ATM has been offline for {int(minutes_down)} minutes (SLA: {sla_minutes} min)",
                    ))
        else:
            # ATM is back online — close offline/SLA alerts
            if db.is_active(atm_id, "OFFLINE"):
                db.close_alert(atm_id, "OFFLINE")
            if db.is_active(atm_id, "SLA_BREACH"):
                db.close_alert(atm_id, "SLA_BREACH")

        # --- LOW_CASH ---
        if cash_pct is not None and cash_pct < cash_threshold:
            if not db.is_active(atm_id, "LOW_CASH"):
                db.open_alert(atm_id, "LOW_CASH")
                new_alerts.append(Alert(
                    atm_id, name, "LOW_CASH",
                    f"Cash level at {cash_pct:.1f}% (threshold: {cash_threshold}%)",
                ))
        else:
            if db.is_active(atm_id, "LOW_CASH"):
                db.close_alert(atm_id, "LOW_CASH")

        # --- HARDWARE_FAULT ---
        if status == "fault" or (error_code and error_code.lower() not in ("", "none", "ok", "normal")):
            if not db.is_active(atm_id, "HARDWARE_FAULT"):
                db.open_alert(atm_id, "HARDWARE_FAULT")
                new_alerts.append(Alert(
                    atm_id, name, "HARDWARE_FAULT",
                    f"Error reported: {error_code or 'hardware fault'}",
                ))
        else:
            if db.is_active(atm_id, "HARDWARE_FAULT"):
                db.close_alert(atm_id, "HARDWARE_FAULT")

    return new_alerts
