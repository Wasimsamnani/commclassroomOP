"""
Scrapes live ATM/kiosk data from the Senwin web portal.

Each ATM record returned is a dict with:
  id, name, status, cash_percent, last_seen, error_code
"""
import re
from playwright.sync_api import sync_playwright, Browser, Page


def login(page: Page, config: dict):
    base = config["senwin"]["url"]
    page.goto(f"{base}/login", wait_until="networkidle")
    page.fill('input[name="email"], input[type="email"], input[name="username"]', config["senwin"]["username"])
    page.fill('input[name="password"], input[type="password"]', config["senwin"]["password"])
    page.click('button[type="submit"], input[type="submit"]')
    page.wait_for_load_state("networkidle")


def _get_total_pages(page: Page) -> int:
    # Try common pagination patterns
    try:
        # Look for last page number link
        links = page.query_selector_all("a[href*='page=']")
        pages = []
        for link in links:
            href = link.get_attribute("href") or ""
            m = re.search(r"page=(\d+)", href)
            if m:
                pages.append(int(m.group(1)))
        if pages:
            return max(pages)
    except Exception:
        pass
    return 1


def _parse_kiosks_on_page(page: Page) -> list[dict]:
    """
    Parse ATM rows from the current kiosks page.
    Tries table rows first, then card-style layouts.
    Field detection is flexible — maps common Senwin column names.
    """
    atms = []

    # --- Try table layout ---
    rows = page.query_selector_all("table tbody tr")
    if rows:
        headers = [
            th.inner_text().strip().lower()
            for th in page.query_selector_all("table thead th")
        ]
        for row in rows:
            cells = [td.inner_text().strip() for td in row.query_selector_all("td")]
            if not cells:
                continue
            record = _map_columns(headers, cells)
            atms.append(record)
        return atms

    # --- Fallback: card / list layout ---
    cards = page.query_selector_all("[class*='kiosk'], [class*='atm'], [class*='card']")
    for card in cards:
        text = card.inner_text()
        record = _parse_card_text(text, card)
        atms.append(record)

    return atms


def _map_columns(headers: list[str], cells: list[str]) -> dict:
    """Map table columns to a normalized ATM record."""
    def find(keys):
        for k in keys:
            for i, h in enumerate(headers):
                if k in h and i < len(cells):
                    return cells[i]
        return None

    raw_id = find(["id", "#", "serial", "terminal"])
    name = find(["name", "location", "site", "label"])
    status = find(["status", "state", "online", "condition"])
    cash_raw = find(["cash", "notes", "currency", "balance"])
    last_seen = find(["last seen", "updated", "timestamp", "time", "date"])
    error_code = find(["error", "fault", "code", "message"])

    return {
        "id": raw_id or f"row-{id(cells)}",
        "name": name or "Unknown",
        "status": _normalize_status(status),
        "cash_percent": _parse_cash_percent(cash_raw),
        "last_seen": last_seen or "",
        "error_code": error_code or "",
    }


def _parse_card_text(text: str, card) -> dict:
    """Best-effort extraction from free-form card text."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    atm_id = ""
    for line in lines:
        m = re.search(r"(?:id|#|terminal)[:\s]*([A-Z0-9\-]+)", line, re.IGNORECASE)
        if m:
            atm_id = m.group(1)
            break
    status_text = ""
    for line in lines:
        if any(w in line.lower() for w in ["online", "offline", "active", "inactive", "fault", "error"]):
            status_text = line
            break
    cash_text = ""
    for line in lines:
        if "%" in line or any(w in line.lower() for w in ["cash", "notes"]):
            cash_text = line
            break
    return {
        "id": atm_id or f"card-{id(card)}",
        "name": lines[0] if lines else "Unknown",
        "status": _normalize_status(status_text),
        "cash_percent": _parse_cash_percent(cash_text),
        "last_seen": "",
        "error_code": "",
    }


def _normalize_status(raw: str | None) -> str:
    if not raw:
        return "unknown"
    lower = raw.lower()
    if any(w in lower for w in ["offline", "inactive", "down", "disconnected", "unreachable"]):
        return "offline"
    if any(w in lower for w in ["online", "active", "up", "connected", "ok"]):
        return "online"
    if any(w in lower for w in ["fault", "error", "alarm", "warning"]):
        return "fault"
    return "unknown"


def _parse_cash_percent(raw: str | None) -> float | None:
    if not raw:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", raw)
    if m:
        return float(m.group(1))
    return None


def scrape_all_kiosks(config: dict) -> list[dict]:
    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            login(page, config)
            base = config["senwin"]["url"]
            page.goto(f"{base}/kiosks?page=1", wait_until="networkidle")
            total_pages = _get_total_pages(page)
            all_atms = _parse_kiosks_on_page(page)
            for p in range(2, total_pages + 1):
                page.goto(f"{base}/kiosks?page={p}", wait_until="networkidle")
                all_atms.extend(_parse_kiosks_on_page(page))
            return all_atms
        finally:
            browser.close()
