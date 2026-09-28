"""
Referee Criteria Filter

Filters referees from OddAlerts data to identify matches worth betting on
BEFORE fetching odds from the API. This saves API credits by only querying
matches that meet the statistical criteria.

Criteria:
  Under cards (bet Under on lines 4.5+):
    - min 50 matches
    - +3.5% <= 45  (at most 45% of games go over 3.5 cards)
    - +4.5% <= 30  (at most 30% of games go over 4.5 cards)
    - min odds 1.75

  Over cards (bet Over on lines below 4.5, i.e. Over 3.5):
    - min 50 matches
    - +3.5% >= 65  (at least 65% of games go over 3.5 cards)
    - +4.5% >= 55  (at least 55% of games go over 4.5 cards)
    - min odds 1.75
"""

import pandas as pd
from src.paths import REF_STATS_CSV

MIN_MATCHES = 50
MIN_ODDS = 1.75

UNDER_CRITERIA = {
    "max_over_3_5_pct": 45.0,
    "max_over_4_5_pct": 30.0,
}

OVER_CRITERIA = {
    "min_over_3_5_pct": 65.0,
    "min_over_4_5_pct": 55.0,
}


def filter_referees(ref_df=None):
    """
    Apply betting criteria to referee stats.

    Returns a DataFrame with columns:
        Name, Home Team, Away Team, signal ('under' or 'over'),
        plus all original referee stats.
    """
    if ref_df is None:
        ref_df = pd.read_csv(REF_STATS_CSV)

    if ref_df.empty:
        return pd.DataFrame()

    ref_df["+3.5%"] = pd.to_numeric(ref_df["+3.5%"], errors="coerce")
    ref_df["+4.5%"] = pd.to_numeric(ref_df["+4.5%"], errors="coerce")

    # Game count: use Apps column (new scraper) or fall back to Yellows/Yellow PG
    if "Apps" in ref_df.columns:
        ref_df["est_games"] = pd.to_numeric(ref_df["Apps"], errors="coerce")
    else:
        ref_df["Yellow PG"] = pd.to_numeric(ref_df["Yellow PG"], errors="coerce")
        ref_df["Yellows"] = pd.to_numeric(ref_df["Yellows"], errors="coerce")
        ref_df["est_games"] = (ref_df["Yellows"] / ref_df["Yellow PG"]).round(0)

    has_match = ref_df["Home Team"].notna() & (ref_df["Home Team"] != "")
    enough_games = ref_df["est_games"] >= MIN_MATCHES

    base = ref_df[has_match & enough_games].copy()

    if base.empty:
        return pd.DataFrame()

    # Under criteria: low over percentages -> bet Under on lines 4.5+
    under_mask = (
        (base["+3.5%"] <= UNDER_CRITERIA["max_over_3_5_pct"]) &
        (base["+4.5%"] <= UNDER_CRITERIA["max_over_4_5_pct"])
    )

    # Over criteria: high over percentages -> bet Over on lines below 4.5
    over_mask = (
        (base["+3.5%"] >= OVER_CRITERIA["min_over_3_5_pct"]) &
        (base["+4.5%"] >= OVER_CRITERIA["min_over_4_5_pct"])
    )

    under_matches = base[under_mask].copy()
    under_matches["signal"] = "under"

    over_matches = base[over_mask].copy()
    over_matches["signal"] = "over"

    result = pd.concat([under_matches, over_matches], ignore_index=True)
    return result


def get_target_matches(ref_df=None):
    """
    Returns a list of (home_team, away_team, signal) tuples for matches
    that pass the referee criteria. These are the only matches we need
    to fetch odds for.
    """
    filtered = filter_referees(ref_df)
    if filtered.empty:
        return []

    matches = []
    for _, row in filtered.iterrows():
        matches.append({
            "home_team": row["Home Team"],
            "away_team": row["Away Team"],
            "referee": row["Name"],
            "signal": row["signal"],
            "est_games": row["est_games"],
            "over_3_5_pct": row["+3.5%"],
            "over_4_5_pct": row["+4.5%"],
            "yellow_pg": row.get("Yellow PG", row.get("Apps", "")),
        })

    return matches


def print_filter_summary(matches):
    """Print a summary of filtered matches."""
    if not matches:
        print("      No matches meet the criteria")
        return

    under = [m for m in matches if m["signal"] == "under"]
    over = [m for m in matches if m["signal"] == "over"]

    print(f"      {len(matches)} matches qualify ({len(under)} under, {len(over)} over)")
    print()
    for m in matches:
        arrow = "UNDER" if m["signal"] == "under" else "OVER"
        print(f"      {arrow} {m['home_team']} vs {m['away_team']}")
        print(f"        Ref: {m['referee']} ({int(m['est_games'])} games) "
              f"| +3.5%: {m['over_3_5_pct']:.1f} | +4.5%: {m['over_4_5_pct']:.1f} "
              f"| {m['yellow_pg']:.2f} cards/g")


if __name__ == "__main__":
    print("=== Referee Filter ===\n")
    matches = get_target_matches()
    print_filter_summary(matches)
