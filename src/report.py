"""
Build a Markdown summary of today's qualifying card matches.

Combines referee_filter targets (from Ref_stats.csv) with the odds in
theodds_card_odds.csv and writes results/latest.md. Used by the GitHub
Actions workflow, but runs locally too:

    python -m src.report
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.analysis.referee_filter import get_target_matches
from src.paths import PROJECT_ROOT, THEODDS_CSV, REF_STATS_CSV
from src.scrapers.referee import _ko_date
from src.utils.name_normalizer import normalize

RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
REPORT_MD = os.path.join(RESULTS_DIR, "latest.md")

BOOKMAKERS = [("bet365", "Bet365"), ("unibet", "Unibet")]


def _kickoff_dt(ko_text):
    """Local kickoff datetime from oddalerts text like '18:30' or 'Tomorrow 18:30'."""
    ko_text = str(ko_text or "").strip()
    try:
        hh, mm = ko_text.split()[-1].split(":")
        day = _ko_date(ko_text)
        return datetime(day.year, day.month, day.day, int(hh), int(mm)).astimezone()
    except Exception:
        return None


def _same_team(a, b):
    a, b = normalize(str(a)).lower(), normalize(str(b)).lower()
    return a == b or a in b or b in a


def _find_odds_row(odds_df, home, away):
    for _, row in odds_df.iterrows():
        if (_same_team(row["home_team"], home) and _same_team(row["away_team"], away)) or \
           (_same_team(row["home_team"], away) and _same_team(row["away_team"], home)):
            return row
    return None


TARGET_LINE = {"over": "3.5", "under": "4.5"}
MIN_ODDS = 1.75


def _lines_for(row, side):
    """Returns odds for the one line we bet: Over 3.5 or Under 4.5.
    Returns empty list if no bookmaker meets the minimum odds threshold."""
    target = TARGET_LINE[side].replace(".", "_")
    result = {}
    for key, label in BOOKMAKERS:
        col = f"{side}_{target}_{key}"
        if col in row.index and pd.notna(row[col]) and float(row[col]) >= MIN_ODDS:
            result[label] = float(row[col])
    return [(TARGET_LINE[side], result)] if result else []


def _fmt(v):
    return f"{v:.2f}" if v is not None else "—"


def build_report():
    targets = get_target_matches()
    odds_df = pd.read_csv(THEODDS_CSV) if os.path.exists(THEODDS_CSV) else pd.DataFrame()
    ref_df = pd.read_csv(REF_STATS_CSV) if os.path.exists(REF_STATS_CSV) else pd.DataFrame()
    now = datetime.now().astimezone()

    out = [
        "# Daily Card Picks",
        "",
        f"_Updated {now:%a %d %b %Y, %H:%M %Z} · {len(ref_df)} fixtures scanned · "
        f"{len(targets)} qualify_",
        "",
    ]

    if not targets:
        out.append("No matches meet the referee criteria today.")
        return "\n".join(out) + "\n"

    ko_lookup = {(r["Home Team"], r["Away Team"]): r.get("Kickoff", "") for _, r in ref_df.iterrows()}

    out += [
        "| Match | Kickoff | Signal | Line | Bet365 | Unibet | Referee | Games | +3.5% | +4.5% |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    skipped = []
    for t in targets:
        home, away, side = t["home_team"], t["away_team"], t["signal"]
        match = f"{home} vs {away}"
        ko = _kickoff_dt(ko_lookup.get((home, away)))
        if ko and ko <= now:
            skipped.append(match)
            continue

        ref = (f"{t['referee']} | {int(t['est_games'])} | "
               f"{t['over_3_5_pct']:.0f}% | {t['over_4_5_pct']:.0f}%")
        ko_str = f"{ko:%a %d %b %H:%M}" if ko else "?"
        row = _find_odds_row(odds_df, home, away) if not odds_df.empty else None
        lines = _lines_for(row, side) if row is not None else []

        if not lines:
            continue
        for i, (line, books) in enumerate(lines):
            first = i == 0
            out.append(
                f"| {match if first else '↳'} | {ko_str if first else ''} | "
                f"**{side.upper()}** | {side.capitalize()} {line} | "
                f"{_fmt(books.get('Bet365'))} | {_fmt(books.get('Unibet'))} | "
                f"{ref if first else '| | |'} |"
            )

    if skipped:
        out += ["", f"Skipped (already kicked off): {', '.join(skipped)}"]
    return "\n".join(out) + "\n"


def main():
    md = build_report()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(md)
    print(md.encode("ascii", "replace").decode())
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(md)


if __name__ == "__main__":
    main()
