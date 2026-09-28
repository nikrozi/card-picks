"""
Result Checker
==============
Looks up completed match card statistics and marks pending bets in Google Sheet.

Card counting rules (Bet365 / standard bookmaker market):
    Yellow card                     = 1
    Red card (direct)               = 2
    Second yellow → red (yellowRed) = 2  (the dismissal counts as a red)

    Example: player gets yellow (1) then second yellow/red (2) = 3 total for that player.

Bet resolution rules:
    Standard line  (e.g. "Card U 4,5"):
        Under: card_total <= line  → Y (win),  card_total > line  → N (loss)
        Over:  card_total >= line  → Y (win),  card_total < line  → N (loss)
        (no half-unit lines = no push possible)

    Asian whole-number line  (e.g. "Card U 4 Asian"):
        Under: total < line → Y,  total == line → PU (push),  total > line → N
        Over:  total > line → Y,  total == line → PU (push),  total < line → N

    Asian half-unit line  (e.g. "Card U 4 Asian" where effective line is X.5):
        Behaves the same as a standard .5 line — no push possible.

Uses API-Football (via RapidAPI) for match event data.
Free tier: 100 requests / day.  Sign up at https://rapidapi.com/api-sports/api/api-football
Add your key to the project .env file:  APIFOOTBALL_KEY=your_key_here
"""

import os
import re
import time
import requests
from datetime import datetime, timedelta

import gspread

from src.paths import PROJECT_ROOT, SERVICE_ACCOUNT_JSON

# ── Google Sheets config (same as sheets_logger) ─────────────────────────────
SPREADSHEET_ID   = "1LrKhJxH5tjIQriHc0TeBB9h-ITaZqS00Ui-uRwvHOUk"
SHEET_GID        = 581276218
DATA_START_ROW   = 10          # first row containing bet data
RESULT_COL       = "P"         # column that holds Y / N / PU

# Column indices (0-based within the row list)
COL_DATE   = 0   # A
COL_BK     = 1   # B
COL_SPORT  = 2   # C
COL_MARKET = 4   # E  (bet type like "Card U 4,5")
COL_HOME   = 7   # H
COL_AWAY   = 8   # I
COL_STAKE  = 12  # M
COL_ODDS   = 13  # N
COL_RESULT = 15  # P  (Y / N / PU)

# ── Card counting weights ─────────────────────────────────────────────────────
CARD_WEIGHTS = {
    "Yellow Card":      1,
    "Red Card":         2,   # direct red
    "Yellow Red Card":  2,   # second yellow → dismissal counts as a red
}

# ── API-Football (RapidAPI) ───────────────────────────────────────────────────
APIFOOTBALL_BASE = "https://api-football-v1.p.rapidapi.com/v3"


def _load_api_key():
    key = os.environ.get("APIFOOTBALL_KEY", "")
    if key:
        return key
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("APIFOOTBALL_KEY="):
                    return line.split("=", 1)[1].strip()
    return ""


def _api_headers():
    key = _load_api_key()
    return {
        "X-RapidAPI-Key":  key,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
    }


# ── Fixture lookup ────────────────────────────────────────────────────────────

def _parse_date(date_str):
    """Parse DD/MM/YY or DD/MM/YYYY to a date object."""
    date_str = date_str.strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def find_fixture(home_team, away_team, match_date):
    """
    Search API-Football for a fixture matching home/away team names on match_date.
    Returns the fixture dict or None.
    Tries ±1 day window to handle timezone differences.
    """
    headers = _api_headers()
    if not headers["X-RapidAPI-Key"]:
        return None

    for delta in [0, -1, 1]:
        date = match_date + timedelta(days=delta)
        url = f"{APIFOOTBALL_BASE}/fixtures"
        params = {"date": date.strftime("%Y-%m-%d")}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            fixtures = resp.json().get("response", [])
        except Exception as e:
            print(f"    API error searching fixtures: {e}")
            return None

        for fix in fixtures:
            teams = fix.get("teams", {})
            api_home = teams.get("home", {}).get("name", "").lower()
            api_away = teams.get("away", {}).get("name", "").lower()
            t_home   = home_team.lower()
            t_away   = away_team.lower()

            def _match(a, b):
                return a == b or a in b or b in a

            if _match(t_home, api_home) and _match(t_away, api_away):
                return fix

        time.sleep(0.3)

    return None


def get_card_events(fixture_id):
    """
    Fetch all card events for a fixture.
    Returns list of dicts: {player, team, type, detail, minute}
    """
    headers = _api_headers()
    url = f"{APIFOOTBALL_BASE}/fixtures/events"
    params = {"fixture": fixture_id, "type": "Card"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("response", [])
    except Exception as e:
        print(f"    API error fetching events: {e}")
        return []


# ── Card total calculation ────────────────────────────────────────────────────

def calculate_card_total(card_events):
    """
    Apply card counting rules to a list of card events.
    Returns (total, breakdown_str).
    """
    total   = 0
    details = []

    for ev in card_events:
        detail  = ev.get("detail", "")
        player  = (ev.get("player", {}) or {}).get("name", "?")
        team    = (ev.get("team",   {}) or {}).get("name", "?")
        minute  = ev.get("time",    {}).get("elapsed", "?")
        weight  = CARD_WEIGHTS.get(detail, 1)   # default 1 if unknown type
        total  += weight
        details.append(f"{minute}' {player} ({team}) [{detail}=+{weight}]")

    breakdown = ", ".join(details) if details else "no cards"
    return total, breakdown


# ── Bet line parsing ──────────────────────────────────────────────────────────

def parse_bet_type(market_str):
    """
    Parse a bet type string like 'Card U 4,5' or 'Card O 4 Asian'.
    Returns (direction, line, is_asian).
        direction : 'under' or 'over'
        line      : float (e.g. 4.5, 4.0)
        is_asian  : True if whole-number Asian line
    """
    s = market_str.strip().upper()

    direction = "under" if " U " in s else "over" if " O " in s else None
    if direction is None:
        return None, None, None

    is_asian = "ASIAN" in s

    # Extract numeric line: handle "4,5" or "4.5" or "4"
    numbers = re.findall(r"\d+[,.]?\d*", s)
    # Skip the first token if it's just "CARD" (no digits)
    line = None
    for n in numbers:
        n_clean = n.replace(",", ".")
        try:
            val = float(n_clean)
            if val >= 1:          # skip single digit that might be "U" parse artifact
                line = val
                break
        except ValueError:
            continue

    return direction, line, is_asian


def resolve_bet(card_total, direction, line, is_asian):
    """
    Determine bet result.
    Returns 'Y' (win), 'N' (loss), or 'PU' (push).
    """
    if direction is None or line is None:
        return None

    # Asian whole-number lines can push
    if is_asian and line == int(line):
        if direction == "under":
            if card_total < line:  return "Y"
            if card_total == line: return "PU"
            return "N"
        else:  # over
            if card_total > line:  return "Y"
            if card_total == line: return "PU"
            return "N"
    else:
        # Standard .5 line (or Asian .5) — no push possible
        if direction == "under":
            return "Y" if card_total < line else "N"
        else:
            return "Y" if card_total > line else "N"


# ── Google Sheet helpers ──────────────────────────────────────────────────────

def _get_worksheet():
    gc = gspread.service_account(filename=SERVICE_ACCOUNT_JSON)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return next(w for w in sh.worksheets() if w.id == SHEET_GID)


def get_pending_bets(ws):
    """Return list of (row_number, row_data) for rows with no result yet."""
    all_rows = ws.get(f"A{DATA_START_ROW}:P300")
    pending  = []
    for i, row in enumerate(all_rows, DATA_START_ROW):
        # Pad row to at least 16 columns
        row = row + [""] * (16 - len(row))
        sport   = row[COL_SPORT].strip()
        market  = row[COL_MARKET].strip()
        home    = row[COL_HOME].strip()
        result  = row[COL_RESULT].strip().upper()

        # Only check Football card bets that are pending
        if not home:
            continue
        if sport.lower() != "football":
            continue
        if not market.upper().startswith("CARD"):
            continue
        if result in ("Y", "N", "PU"):
            continue  # already resolved

        pending.append((i, row))

    return pending


def mark_result(ws, row_num, result):
    """Write Y / N / PU into column P for the given row."""
    ws.update(values=[[result]], range_name=f"{RESULT_COL}{row_num}")


# ── Main runner ───────────────────────────────────────────────────────────────

def check_and_mark_results(dry_run=False):
    """
    Main entry point. Scans the sheet for pending bets, looks up results,
    and marks them correctly.

    Parameters:
        dry_run: if True, prints what would be written but doesn't update the sheet.
    """
    api_key = _load_api_key()
    if not api_key:
        print("  No APIFOOTBALL_KEY found in .env — cannot look up results automatically.")
        print("  Add APIFOOTBALL_KEY=<your_key> to the project .env file.")
        print("  Free API key: https://rapidapi.com/api-sports/api/api-football")
        return

    print("=== Result Checker ===\n")

    ws = _get_worksheet()
    pending = get_pending_bets(ws)

    if not pending:
        print("  No pending bets found in the sheet.")
        return

    print(f"  Found {len(pending)} pending bet(s):\n")

    today = datetime.now().date()
    updated = 0

    for row_num, row in pending:
        date_str = row[COL_DATE].strip()
        home     = row[COL_HOME].strip()
        away     = row[COL_AWAY].strip()
        market   = row[COL_MARKET].strip()

        match_date = _parse_date(date_str)
        if match_date is None:
            print(f"  Row {row_num}: Could not parse date '{date_str}' — skipping")
            continue

        # Don't check future matches
        if match_date > today:
            print(f"  Row {row_num}: {home} vs {away} ({date_str}) — future match, skipping")
            continue

        print(f"  Row {row_num}: {home} vs {away} | {date_str} | {market}")

        direction, line, is_asian = parse_bet_type(market)
        if direction is None:
            print(f"    Could not parse bet type '{market}' — skipping")
            continue

        # Look up fixture
        fixture = find_fixture(home, away, match_date)
        if fixture is None:
            print(f"    Fixture not found via API — skipping")
            continue

        fixture_id     = fixture["fixture"]["id"]
        status         = fixture["fixture"]["status"]["short"]
        api_home       = fixture["teams"]["home"]["name"]
        api_away       = fixture["teams"]["away"]["name"]

        # Only process finished matches
        if status not in ("FT", "AET", "PEN", "AWD"):
            print(f"    Match not finished yet (status: {status}) — skipping")
            continue

        print(f"    Matched: {api_home} vs {api_away} (id={fixture_id}, status={status})")

        # Fetch card events
        events      = get_card_events(fixture_id)
        total, breakdown = calculate_card_total(events)
        result      = resolve_bet(total, direction, line, is_asian)

        print(f"    Cards: {total} ({breakdown})")
        print(f"    Bet: {direction.upper()} {line} {'Asian' if is_asian else ''}")
        print(f"    Result: {result}")

        if not dry_run and result:
            mark_result(ws, row_num, result)
            print(f"    → Sheet row {row_num} marked as {result}")
            updated += 1
        elif dry_run:
            print(f"    → [DRY RUN] Would mark row {row_num} as {result}")

        print()
        time.sleep(0.5)   # gentle rate limiting

    print(f"  Done. {updated} bet(s) updated.")


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    check_and_mark_results(dry_run=dry)
