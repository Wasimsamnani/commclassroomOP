"""
Entry point for the Senwin ATM monitoring agent.

Usage:
  python monitor.py           # start continuous polling
  python monitor.py --once    # run one poll cycle (dry run, no SMS sent)
"""
import argparse
import sys
import yaml

from apscheduler.schedulers.blocking import BlockingScheduler

import db
import alerts as alert_engine
import notifier
import scraper


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def run_poll(config: dict, dry_run: bool = False):
    print("[monitor] Polling Senwin portal...")
    try:
        atms = scraper.scrape_all_kiosks(config)
    except Exception as exc:
        print(f"[monitor] Scrape failed: {exc}")
        return

    print(f"[monitor] Found {len(atms)} ATMs")

    new_alerts = alert_engine.check_alerts(atms, config.get("alert_thresholds", {}))

    if not new_alerts:
        print("[monitor] No new alerts.")
        return

    for alert in new_alerts:
        notifier.send_alert(alert, config, dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(description="Senwin ATM monitoring agent")
    parser.add_argument("--once", action="store_true", help="Run one poll cycle (dry run)")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    db.init_db()

    if args.once:
        print("[monitor] Running single poll cycle (dry run — no SMS will be sent)")
        run_poll(config, dry_run=True)
        return

    interval = config.get("polling_interval_minutes", 5)
    print(f"[monitor] Starting scheduler — polling every {interval} minutes. Press Ctrl+C to stop.")

    scheduler = BlockingScheduler()
    scheduler.add_job(run_poll, "interval", minutes=interval, args=[config], id="atm_poll")

    # Run once immediately on start
    run_poll(config)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[monitor] Stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
