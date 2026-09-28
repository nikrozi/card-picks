"""
Google Sheets Logger

Appends qualifying bets to the BETS tab of the tracking spreadsheet.
Matches the existing row format: Date, Bookmaker, Sport, (blank), Market,
Card Rules, (blank), Home, Away, Competition, ..., Stake (M), Odds (N)
"""

import os
import gspread
from datetime import datetime

from src.paths import SERVICE_ACCOUNT_JSON

SPREADSHEET_ID = "1LrKhJxH5tjIQriHc0TeBB9h-ITaZqS00Ui-uRwvHOUk"
SHEET_GID      = 581276218
SERVICE_ACCOUNT_FILE = SERVICE_ACCOUNT_JSON

STAKE = 100


def _get_worksheet():
    gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return next(w for w in sh.worksheets() if w.id == SHEET_GID)


def _next_empty_row(ws):
    """Find the first empty row in column A after the data section (row 10+)."""
    col_a = ws.col_values(1)
    for i in range(9, len(col_a)):  # start at row 10 (index 9)
        if not col_a[i].strip():
            return i + 1  # 1-indexed
    return len(col_a) + 1


def _existing_bets_today(ws):
    """
    Return a set of (home, away, market) tuples already logged for today's date.
    Used to skip duplicate inserts when the pipeline runs more than once a day.
    """
    date_today = datetime.now().strftime("%d/%m/%y")
    all_values = ws.get_all_values()
    existing = set()
    for row in all_values[9:]:  # data starts at row 10
        if len(row) < 9 or not row[0].strip():
            continue
        date = row[0].strip()
        if date != date_today:
            continue
        market = row[4].strip() if len(row) > 4 else ""
        home   = row[7].strip() if len(row) > 7 else ""
        away   = row[8].strip() if len(row) > 8 else ""
        existing.add((home.lower(), away.lower(), market.lower()))
    return existing


def log_bets(value_bets_with_odds):
    """
    Write qualifying bets to the BETS sheet.

    Parameters:
        value_bets_with_odds: list of dicts with keys:
            home_team, away_team, competition, signal ('under'/'over'),
            bookmaker ('Bet365'/'Unibet'), odds (float)
    """
    if not value_bets_with_odds:
        print("      No bets to log to Google Sheets")
        return

    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"      Sheets: service_account.json not found, skipping")
        return

    try:
        ws = _get_worksheet()
    except Exception as e:
        print(f"      Sheets: could not connect ({e})")
        return

    date_str = datetime.now().strftime("%d/%m/%y")
    existing = _existing_bets_today(ws)
    skipped = 0

    for bet in value_bets_with_odds:
        signal = bet["signal"]
        line   = "4,5" if signal == "under" else "3,5"
        market = f"Card U {line}" if signal == "under" else f"Card O {line}"
        bk     = bet["bookmaker"].lower()  # 'bet365' or 'unibet'
        odds   = bet["odds"]
        home   = bet["home_team"]
        away   = bet["away_team"]
        comp   = bet.get("competition", "---")

        # Skip if this exact bet (same date, match, market) is already in the sheet
        key = (home.lower(), away.lower(), market.lower())
        if key in existing:
            print(f"      Skipped (already logged today): {home} vs {away} | {market}")
            skipped += 1
            continue

        row_num = _next_empty_row(ws)

        # Columns A-J
        ws.update(values=[[date_str]], range_name=f"A{row_num}")
        ws.update(values=[[bk]],       range_name=f"B{row_num}")
        ws.update(values=[["Football"]], range_name=f"C{row_num}")
        ws.update(values=[[market]],   range_name=f"E{row_num}")
        ws.update(values=[["Card Rules"]], range_name=f"F{row_num}")
        ws.update(values=[[home]],     range_name=f"H{row_num}")
        ws.update(values=[[away]],     range_name=f"I{row_num}")
        ws.update(values=[[comp]],     range_name=f"J{row_num}")
        # Stake and odds
        ws.update(values=[[STAKE]],    range_name=f"M{row_num}")
        ws.update(values=[[odds]],     range_name=f"N{row_num}")

        print(f"      Logged row {row_num}: {home} vs {away} | {market} @ {odds} ({bk})")
