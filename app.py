"""
Combined Flask dashboard + background ATM monitor.
Entry point for Railway deployment and local use.
"""
import os
import threading
from datetime import datetime, timezone

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template

import alerts as alert_engine
import db
import notifier
import scraper

app = Flask(__name__)
_config: dict = {}
_last_poll: str = "Never"


def load_config(path: str = "config.yaml") -> dict:
    cfg: dict = {}
    try:
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        pass

    # Environment variables override config.yaml (used on Railway)
    if os.environ.get("SENWIN_USERNAME"):
        cfg.setdefault("senwin", {})
        cfg["senwin"]["url"] = os.environ.get("SENWIN_URL", "https://www.senwin.co")
        cfg["senwin"]["username"] = os.environ["SENWIN_USERNAME"]
        cfg["senwin"]["password"] = os.environ.get("SENWIN_PASSWORD", "")

    if os.environ.get("TWILIO_ACCOUNT_SID"):
        cfg.setdefault("twilio", {})
        cfg["twilio"]["account_sid"] = os.environ["TWILIO_ACCOUNT_SID"]
        cfg["twilio"]["auth_token"] = os.environ.get("TWILIO_AUTH_TOKEN", "")
        cfg["twilio"]["from_number"] = os.environ.get("TWILIO_FROM_NUMBER", "")
        raw = os.environ.get("TWILIO_TO_NUMBERS", "")
        cfg["twilio"]["to_numbers"] = [n.strip() for n in raw.split(",") if n.strip()]

    cfg.setdefault("alert_thresholds", {})
    if os.environ.get("CASH_LOW_PERCENT"):
        cfg["alert_thresholds"]["cash_low_percent"] = int(os.environ["CASH_LOW_PERCENT"])
    if os.environ.get("SLA_BREACH_MINUTES"):
        cfg["alert_thresholds"]["sla_breach_minutes"] = int(os.environ["SLA_BREACH_MINUTES"])
    if os.environ.get("POLLING_INTERVAL_MINUTES"):
        cfg["polling_interval_minutes"] = int(os.environ["POLLING_INTERVAL_MINUTES"])

    return cfg


def run_poll():
    global _last_poll
    print("[monitor] Polling Senwin portal...")
    try:
        atms = scraper.scrape_all_kiosks(_config)
        db.save_kiosk_states(atms)
        _last_poll = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"[monitor] {len(atms)} ATMs scraped at {_last_poll}")
        new_alerts = alert_engine.check_alerts(atms, _config.get("alert_thresholds", {}))
        for alert in new_alerts:
            notifier.send_alert(alert, _config)
    except Exception as exc:
        print(f"[monitor] Poll error: {exc}")


@app.route("/")
def dashboard():
    atms = db.get_all_kiosk_states()
    active_alerts = db.get_active_alerts()
    stats = {
        "total": len(atms),
        "online": sum(1 for a in atms if a["status"] == "online"),
        "offline": sum(1 for a in atms if a["status"] == "offline"),
        "alerts": len(active_alerts),
    }
    return render_template(
        "index.html",
        atms=atms,
        active_alerts=active_alerts,
        stats=stats,
        last_poll=_last_poll,
    )


@app.route("/api/atms")
def api_atms():
    return jsonify({
        "atms": db.get_all_kiosk_states(),
        "alerts": db.get_active_alerts(),
        "last_poll": _last_poll,
    })


if __name__ == "__main__":
    _config = load_config()
    db.init_db()

    interval = _config.get("polling_interval_minutes", 5)
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_poll, "interval", minutes=interval, id="atm_poll")
    scheduler.start()

    threading.Thread(target=run_poll, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
