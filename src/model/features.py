#!/usr/bin/env python3
"""
Feature Engineering Module
Builds the feature matrix for card prediction from referee stats, team stats,
and contextual information.
"""

import pandas as pd
import numpy as np
from src.utils.name_normalizer import normalize, normalize_dataframe
from src.paths import REF_STATS_CSV, COMBINED_ALL_GAMES_CSV


def load_referee_data(path=None):
    """Load and clean referee statistics."""
    if path is None:
        path = REF_STATS_CSV
    df = pd.read_csv(path)
    normalize_dataframe(df, ["Home Team", "Away Team"])

    numeric_cols = [
        "Yellows", "Reds", "Yellow PG", "Reds PG", "Home PG", "Away PG",
        "1H PG", "2H PG", "BTC %", "BTC 1H %", "BTC 2H %",
        "+0.5%", "+1.5%", "+2.5%", "+3.5%", "+4.5%",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def load_team_data(path=None):
    """Load and clean team card statistics."""
    if path is None:
        path = COMBINED_ALL_GAMES_CSV
    df = pd.read_csv(path)
    normalize_dataframe(df, ["Team"])

    numeric_cols = ["TG", "YF", "YA", "O3.5", "U3.5", "O4.5", "U4.5", "O5.5", "U5.5"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def compute_league_averages(team_df):
    """Compute league-level aggregated card averages."""
    if "League" not in team_df.columns:
        return pd.DataFrame()

    agg = team_df.groupby("League").agg(
        league_avg_yf=("YF", "mean"),
        league_avg_ya=("YA", "mean"),
        league_avg_o35=("O3.5", "mean"),
        league_avg_o45=("O4.5", "mean"),
    ).reset_index()

    return agg


def build_feature_matrix(referee_df, team_df):
    """
    Merge referee + team data and engineer prediction features.

    Returns a DataFrame with one row per match and all features needed
    for the card prediction model.
    """
    # Only keep referees with an upcoming match
    matches = referee_df.dropna(subset=["Home Team", "Away Team"]).copy()
    matches = matches[matches["Home Team"].str.len() > 0].copy()

    # --- Merge home team stats ---
    home_cols = {
        "Team": "Home Team",
        "TG": "ht_games",
        "YF": "ht_cards_for",
        "YA": "ht_cards_against",
        "O3.5": "ht_o35",
        "U3.5": "ht_u35",
        "O4.5": "ht_o45",
        "U4.5": "ht_u45",
        "O5.5": "ht_o55",
        "U5.5": "ht_u55",
        "League": "ht_league",
    }
    home_merge = team_df.rename(columns=home_cols)
    matches = matches.merge(home_merge, on="Home Team", how="left")

    # --- Merge away team stats ---
    away_cols = {
        "Team": "Away Team",
        "TG": "at_games",
        "YF": "at_cards_for",
        "YA": "at_cards_against",
        "O3.5": "at_o35",
        "U3.5": "at_u35",
        "O4.5": "at_o45",
        "U4.5": "at_u45",
        "O5.5": "at_o55",
        "U5.5": "at_u55",
        "League": "at_league",
    }
    away_merge = team_df.rename(columns=away_cols)
    matches = matches.merge(away_merge, on="Away Team", how="left")

    # --- Engineered features ---

    # Average total cards per game for each team (for + against)
    matches["ht_total_cards_pg"] = matches["ht_cards_for"] + matches["ht_cards_against"]
    matches["at_total_cards_pg"] = matches["at_cards_for"] + matches["at_cards_against"]

    # Combined expected cards from team stats alone
    matches["team_expected_cards"] = (
        matches["ht_total_cards_pg"] + matches["at_total_cards_pg"]
    ) / 2.0

    # Referee card intensity features
    matches["ref_cards_pg"] = matches["Yellow PG"]
    # Home/Away PG and 2H PG are optional (not always scraped)
    if "Home PG" in matches.columns and "Away PG" in matches.columns:
        matches["ref_home_bias"] = matches["Home PG"] - matches["Away PG"]
    else:
        matches["ref_home_bias"] = 0.0
    if "2H PG" in matches.columns:
        matches["ref_2h_ratio"] = matches["2H PG"] / matches["Yellow PG"].replace(0, np.nan)
    else:
        matches["ref_2h_ratio"] = np.nan

    # Interaction: referee tendency * team tendency
    matches["ref_x_team_cards"] = matches["ref_cards_pg"] * matches["team_expected_cards"]

    # Over threshold agreement between referee and teams
    for threshold in ["35", "45"]:
        ref_col = f"+{threshold[0]}.{threshold[1]}%"
        ht_col = f"ht_o{threshold}"
        at_col = f"at_o{threshold}"
        feat = f"combined_o{threshold}"
        if ref_col in matches.columns:
            matches[feat] = (
                matches[ref_col] * 0.4
                + matches[ht_col].fillna(50) * 0.3
                + matches[at_col].fillna(50) * 0.3
            )

    # League context: merge league averages
    league_avgs = compute_league_averages(team_df)
    if not league_avgs.empty:
        matches = matches.merge(
            league_avgs, left_on="ht_league", right_on="League", how="left"
        )
        matches.drop(columns=["League"], inplace=True, errors="ignore")

        # How much this match deviates from league average
        matches["cards_vs_league_avg"] = (
            matches["team_expected_cards"] - (matches["league_avg_yf"] + matches["league_avg_ya"])
        )

    # BTC (Both Teams Carded) - useful predictor of high-card games (optional)
    if "BTC %" in matches.columns:
        matches["ref_btc_pct"] = matches["BTC %"]
    else:
        matches["ref_btc_pct"] = np.nan

    return matches


# Column subsets for the ML model
FEATURE_COLUMNS = [
    "ref_cards_pg",
    "ref_home_bias",
    "ref_2h_ratio",
    "ref_btc_pct",
    "+3.5%",
    "+4.5%",
    "ht_cards_for",
    "ht_cards_against",
    "at_cards_for",
    "at_cards_against",
    "ht_total_cards_pg",
    "at_total_cards_pg",
    "team_expected_cards",
    "ref_x_team_cards",
    "combined_o35",
    "combined_o45",
    "ht_o35",
    "ht_o45",
    "at_o35",
    "at_o45",
]

FEATURE_COLUMNS_WITH_LEAGUE = FEATURE_COLUMNS + [
    "league_avg_yf",
    "league_avg_ya",
    "league_avg_o35",
    "league_avg_o45",
    "cards_vs_league_avg",
]


if __name__ == "__main__":
    print("=== Feature Engineering Test ===")
    referee_df = load_referee_data()
    team_df = load_team_data()
    print(f"Referee data: {referee_df.shape}")
    print(f"Team data: {team_df.shape}")

    features = build_feature_matrix(referee_df, team_df)
    print(f"\nFeature matrix: {features.shape}")
    print(f"Columns: {list(features.columns)}")

    # Show matches that now have complete data
    complete = features.dropna(subset=["ht_games", "at_games"])
    print(f"\nMatches with complete team data: {len(complete)} / {len(features)}")
    if len(complete) > 0:
        display_cols = [
            "Home Team", "Away Team", "Name",
            "ref_cards_pg", "team_expected_cards",
            "combined_o35", "combined_o45",
        ]
        available = [c for c in display_cols if c in complete.columns]
        print(complete[available].to_string(index=False))
