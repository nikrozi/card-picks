#!/usr/bin/env python3
"""
Historical Data Collector
Downloads historical match data with card outcomes from football-data.co.uk.
This data is used to train the card prediction model.
"""

import os
import pandas as pd
import requests
from io import StringIO
from src.utils.name_normalizer import normalize, normalize_dataframe
from src.paths import HISTORICAL_DIR, HISTORICAL_MATCHES_CSV

DATA_DIR = HISTORICAL_DIR

# football-data.co.uk CSV URLs by league and season
# Format: https://www.football-data.co.uk/mmz4281/{season_code}/{league_code}.csv
LEAGUES = {
    "Premier League": "E0",
    "Championship": "E1",
    "La Liga": "SP1",
    "La Liga 2": "SP2",
    "Bundesliga": "D1",
    "2 Bundesliga": "D2",
    "Serie A": "I1",
    "Serie B": "I2",
    "Ligue 1": "F1",
    "Ligue 2": "F2",
    "Eredivisie": "N1",
    "Belgian Pro League": "B1",
    "Primeira Liga": "P1",
    "Super Lig": "T1",
    "Scottish Premiership": "SC0",
}

# Season codes: "2425" = 2024/25, "2324" = 2023/24, etc.
SEASONS = ["2526", "2425", "2324", "2223", "2122"]

BASE_URL = "https://www.football-data.co.uk/mmz4281"

# Columns we need from the CSVs
KEEP_COLUMNS = [
    "Div", "Date", "HomeTeam", "AwayTeam",
    "FTHG", "FTAG", "FTR",
    "HY", "AY", "HR", "AR",
    "Referee",
]


def download_season(league_code, season_code):
    """Download a single CSV from football-data.co.uk. Returns DataFrame or None."""
    url = f"{BASE_URL}/{season_code}/{league_code}.csv"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        text = resp.text
        if len(text) < 100:
            return None
        df = pd.read_csv(StringIO(text), on_bad_lines="skip")
        return df
    except Exception as e:
        print(f"    Error downloading {url}: {e}")
        return None


def download_all_historical_data():
    """
    Download historical match data for all leagues and seasons.
    Saves raw CSVs and a combined cleaned file.
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    all_frames = []
    total_downloaded = 0

    for league_name, league_code in LEAGUES.items():
        print(f"\n  {league_name} ({league_code}):")
        for season in SEASONS:
            df = download_season(league_code, season)
            if df is None:
                print(f"    {season}: not available")
                continue

            # Check that card columns exist
            has_cards = all(c in df.columns for c in ["HY", "AY"])
            if not has_cards:
                print(f"    {season}: no card data")
                continue

            # Keep only relevant columns that exist
            cols = [c for c in KEEP_COLUMNS if c in df.columns]
            df = df[cols].copy()
            df["League"] = league_name
            df["Season"] = season

            rows_before = len(df)
            df = df.dropna(subset=["HomeTeam", "AwayTeam", "HY", "AY"])
            print(f"    {season}: {len(df)} matches (dropped {rows_before - len(df)} incomplete)")

            all_frames.append(df)
            total_downloaded += len(df)

    if not all_frames:
        print("\nNo historical data downloaded.")
        return pd.DataFrame()

    combined = pd.concat(all_frames, ignore_index=True)

    # Normalize team names
    normalize_dataframe(combined, ["HomeTeam", "AwayTeam"])

    # Parse numeric card columns
    for col in ["HY", "AY", "HR", "AR"]:
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce")

    # Computed columns
    combined["TotalYellowCards"] = combined["HY"] + combined["AY"]
    combined["TotalRedCards"] = combined.get("HR", 0) + combined.get("AR", 0)
    combined["TotalCards"] = combined["TotalYellowCards"] + combined["TotalRedCards"]

    # Over/under target columns for classification
    for threshold in [2.5, 3.5, 4.5, 5.5]:
        combined[f"Over_{threshold}"] = (combined["TotalCards"] > threshold).astype(int)

    # Save
    output_path = HISTORICAL_MATCHES_CSV
    combined.to_csv(output_path, index=False)
    print(f"\nSaved {len(combined)} matches to {output_path}")
    print(f"Leagues: {combined['League'].nunique()}")
    print(f"Seasons: {combined['Season'].nunique()}")

    # Summary stats
    print(f"\nCard distribution:")
    print(f"  Mean total cards/match: {combined['TotalCards'].mean():.2f}")
    print(f"  Median: {combined['TotalCards'].median():.1f}")
    print(f"  Over 3.5 rate: {combined['Over_3.5'].mean():.1%}")
    print(f"  Over 4.5 rate: {combined['Over_4.5'].mean():.1%}")
    print(f"  Over 5.5 rate: {combined['Over_5.5'].mean():.1%}")

    return combined


def load_historical_data():
    """Load previously downloaded historical data."""
    path = HISTORICAL_MATCHES_CSV
    if not os.path.exists(path):
        print("No historical data found. Run download_all_historical_data() first.")
        return pd.DataFrame()
    return pd.read_csv(path)


def compute_referee_historical_stats(hist_df):
    """
    Compute per-referee historical card stats from the match data.
    Useful for enriching current referee data or cross-validation.
    """
    if "Referee" not in hist_df.columns or hist_df["Referee"].isna().all():
        return pd.DataFrame()

    ref_stats = hist_df.groupby("Referee").agg(
        games=("TotalCards", "count"),
        avg_total_cards=("TotalCards", "mean"),
        avg_yellow=("TotalYellowCards", "mean"),
        avg_hy=("HY", "mean"),
        avg_ay=("AY", "mean"),
        over_35_pct=("Over_3.5", "mean"),
        over_45_pct=("Over_4.5", "mean"),
        over_55_pct=("Over_5.5", "mean"),
    ).reset_index()

    ref_stats["over_35_pct"] = (ref_stats["over_35_pct"] * 100).round(1)
    ref_stats["over_45_pct"] = (ref_stats["over_45_pct"] * 100).round(1)
    ref_stats["over_55_pct"] = (ref_stats["over_55_pct"] * 100).round(1)

    return ref_stats.sort_values("games", ascending=False)


def compute_team_historical_stats(hist_df):
    """
    Compute per-team historical card averages (home and away separately).
    """
    home_stats = hist_df.groupby("HomeTeam").agg(
        home_games=("HY", "count"),
        home_yf=("HY", "mean"),
        home_ya=("AY", "mean"),
    ).reset_index().rename(columns={"HomeTeam": "Team"})

    away_stats = hist_df.groupby("AwayTeam").agg(
        away_games=("AY", "count"),
        away_yf=("AY", "mean"),
        away_ya=("HY", "mean"),
    ).reset_index().rename(columns={"AwayTeam": "Team"})

    team_stats = home_stats.merge(away_stats, on="Team", how="outer")
    team_stats["total_games"] = team_stats["home_games"].fillna(0) + team_stats["away_games"].fillna(0)
    team_stats["avg_cards_for"] = (
        (team_stats["home_yf"].fillna(0) * team_stats["home_games"].fillna(0) +
         team_stats["away_yf"].fillna(0) * team_stats["away_games"].fillna(0))
        / team_stats["total_games"].replace(0, 1)
    )
    team_stats["avg_cards_against"] = (
        (team_stats["home_ya"].fillna(0) * team_stats["home_games"].fillna(0) +
         team_stats["away_ya"].fillna(0) * team_stats["away_games"].fillna(0))
        / team_stats["total_games"].replace(0, 1)
    )

    return team_stats.sort_values("total_games", ascending=False)


if __name__ == "__main__":
    print("=== Historical Data Collector ===\n")
    hist = download_all_historical_data()
    if not hist.empty:
        print("\n--- Referee Stats (top 15) ---")
        ref_stats = compute_referee_historical_stats(hist)
        if not ref_stats.empty:
            print(ref_stats.head(15).to_string(index=False))
        print("\n--- Team Stats (top 15) ---")
        team_stats = compute_team_historical_stats(hist)
        print(team_stats.head(15).to_string(index=False))
