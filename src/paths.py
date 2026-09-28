"""
Centralized path configuration.
All data file paths are resolved relative to the project root so that
modules work regardless of which directory they're invoked from.
"""

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
TEAM_STATS_DIR = os.path.join(DATA_DIR, "team_stats")
HISTORICAL_DIR = os.path.join(DATA_DIR, "historical")
MODEL_DIR = os.path.join(DATA_DIR, "model")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")

GOOGLE_DRIVE_PATH = r"G:\My Drive\Card_stats"

# Specific file paths
REF_STATS_CSV = os.path.join(OUTPUT_DIR, "Ref_stats.csv")
COMBINED_ALL_GAMES_CSV = os.path.join(TEAM_STATS_DIR, "Combined_All_Games.csv")
COMBINED_HOME_GAMES_CSV = os.path.join(TEAM_STATS_DIR, "Combined_Home_Games.csv")
COMBINED_AWAY_GAMES_CSV = os.path.join(TEAM_STATS_DIR, "Combined_Away_Games.csv")
HISTORICAL_MATCHES_CSV = os.path.join(HISTORICAL_DIR, "historical_matches.csv")
MODEL_PKL = os.path.join(MODEL_DIR, "card_classifier.pkl")

THEODDS_CSV = os.path.join(OUTPUT_DIR, "theodds_card_odds.csv")
SERVICE_ACCOUNT_JSON = os.path.join(PROJECT_ROOT, "secrets", "service_account.json")
VALUE_BETS_CSV = os.path.join(OUTPUT_DIR, "value_bets.csv")
RECOMMENDATIONS_CSV = os.path.join(OUTPUT_DIR, "recommendations.csv")
ALL_PREDICTIONS_CSV = os.path.join(OUTPUT_DIR, "all_predictions.csv")


def ensure_dirs():
    """Create all data directories if they don't exist."""
    for d in [DATA_DIR, TEAM_STATS_DIR, HISTORICAL_DIR, MODEL_DIR, OUTPUT_DIR]:
        os.makedirs(d, exist_ok=True)
