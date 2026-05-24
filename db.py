import sqlite3
from datetime import datetime

DB_PATH = "atm_alerts.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_state (
                atm_id       TEXT NOT NULL,
                alert_type   TEXT NOT NULL,
                active       INTEGER NOT NULL DEFAULT 1,
                first_triggered_at TEXT NOT NULL,
                last_notified_at   TEXT NOT NULL,
                PRIMARY KEY (atm_id, alert_type)
            )
        """)
        conn.commit()


def is_active(atm_id: str, alert_type: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT active FROM alert_state WHERE atm_id=? AND alert_type=?",
            (atm_id, alert_type),
        ).fetchone()
        return bool(row and row["active"])


def open_alert(atm_id: str, alert_type: str):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO alert_state (atm_id, alert_type, active, first_triggered_at, last_notified_at)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(atm_id, alert_type) DO UPDATE SET
                active=1,
                first_triggered_at=CASE WHEN active=0 THEN excluded.first_triggered_at ELSE first_triggered_at END,
                last_notified_at=excluded.last_notified_at
            """,
            (atm_id, alert_type, now, now),
        )
        conn.commit()


def close_alert(atm_id: str, alert_type: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE alert_state SET active=0 WHERE atm_id=? AND alert_type=?",
            (atm_id, alert_type),
        )
        conn.commit()


def get_first_triggered_at(atm_id: str, alert_type: str) -> datetime | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT first_triggered_at FROM alert_state WHERE atm_id=? AND alert_type=? AND active=1",
            (atm_id, alert_type),
        ).fetchone()
        if row:
            return datetime.fromisoformat(row["first_triggered_at"])
        return None
