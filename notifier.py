"""Sends WhatsApp/SMS alerts via Twilio."""
from datetime import datetime, timezone

from twilio.rest import Client

from alerts import Alert


def send_alert(alert: Alert, config: dict, dry_run: bool = False) -> bool:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = (
        f"[SENWIN ALERT] ATM #{alert.atm_id} — {alert.atm_name}\n"
        f"Type   : {alert.alert_type}\n"
        f"Detail : {alert.detail}\n"
        f"Time   : {timestamp}"
    )

    if dry_run:
        print(f"[DRY RUN] Would send:\n{body}\n")
        return True

    twilio_cfg = config["twilio"]
    client = Client(twilio_cfg["account_sid"], twilio_cfg["auth_token"])
    from_number = twilio_cfg["from_number"]
    success = True
    for to_number in twilio_cfg.get("to_numbers", []):
        try:
            client.messages.create(body=body, from_=from_number, to=to_number)
            print(f"[notifier] Alert sent to {to_number}: {alert.alert_type} on ATM {alert.atm_id}")
        except Exception as exc:
            print(f"[notifier] ERROR sending to {to_number}: {exc}")
            success = False
    return success
