#!/usr/bin/env python3
"""
Daily Analysis Pipeline
Orchestrates the complete data collection, model prediction, and
bet recommendation workflow. Run daily before placing bets.

Pipeline flow:
  1. Scrape referee stats (with Card Markets Required ON)
  2. Filter referees by betting criteria -> target matches
  3. Scrape team card stats for context
  4. Fetch odds ONLY for target matches (saves API credits)
  5. Build features + predict for target matches
  6. Merge odds + detect value bets (min odds 1.75)
  7. Generate match card images

Usage:
    python daily_analysis.py              # full pipeline
    python daily_analysis.py --refresh-odds # force fresh odds from The Odds API
    python daily_analysis.py --skip-scrape  # skip all scraping, use cached data
    python daily_analysis.py --retrain      # retrain the ML model on latest historical data
"""

import sys
import os
import shutil
import pandas as pd
from datetime import datetime

from src.paths import (
    ensure_dirs, GOOGLE_DRIVE_PATH,
    THEODDS_CSV, TEAM_STATS_DIR,
    COMBINED_ALL_GAMES_CSV, COMBINED_HOME_GAMES_CSV, COMBINED_AWAY_GAMES_CSV,
    REF_STATS_CSV, VALUE_BETS_CSV, RECOMMENDATIONS_CSV, ALL_PREDICTIONS_CSV,
)
from src.utils.name_normalizer import normalize_dataframe


def print_header(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_step(num, title):
    print(f"\n  [{num}] {title}")


# ── Step 1: Referee stats (oddalerts) ────────────────────────────────────

def run_referee_scraper():
    print_step(1, "Collecting referee statistics (oddalerts.com) ...")
    try:
        from src.scrapers.referee import main as referee_main
        referee_main()
        _copy_to_drive([REF_STATS_CSV])
        print("      Referee stats collected")
        return True
    except Exception as e:
        print(f"      Error: {e}")
        return False


# ── Step 2: Filter referees by betting criteria ──────────────────────────

def run_referee_filter():
    print_step(2, "Filtering referees by betting criteria ...")

    from src.analysis.referee_filter import get_target_matches, print_filter_summary

    target_matches = get_target_matches()
    print_filter_summary(target_matches)
    return target_matches


# ── Step 3: Team card stats (betaminic) ──────────────────────────────────

def run_team_scraper():
    print_step(3, "Updating team card statistics (betaminic.com) ...")
    try:
        from src.scrapers.betaminic import ultra_fast_scraper
        ultra_fast_scraper()
        _copy_to_drive([
            COMBINED_ALL_GAMES_CSV,
            COMBINED_HOME_GAMES_CSV,
            COMBINED_AWAY_GAMES_CSV,
        ])
        print("      Team card stats updated")
        return True
    except Exception as e:
        print(f"      Error: {e}")
        return False


# ── Step 4: Targeted odds collection ─────────────────────────────────────

def run_targeted_odds(target_matches, force_refresh=False):
    print_step(4, f"Collecting card odds for {len(target_matches)} target matches ...")

    odds_sources = []

    try:
        from src.scrapers.theodds import fetch_targeted_card_odds
        theodds_df = fetch_targeted_card_odds(target_matches, force_refresh=force_refresh)
        if not theodds_df.empty:
            theodds_df.to_csv(THEODDS_CSV, index=False)
            odds_sources.append(("theodds", theodds_df))
            print(f"        {len(theodds_df)} matches with odds")
        else:
            print("        No card odds found for target matches")
    except Exception as e:
        print(f"        Odds API skipped ({e})")

    return odds_sources


# ── Step 5: Feature engineering + model prediction ───────────────────────

def run_predictions():
    print_step(5, "Running model predictions ...")

    from src.model.features import load_referee_data, load_team_data, build_feature_matrix
    from src.model.card_model import predict_upcoming, CardClassifier

    ref_df = load_referee_data()
    team_df = load_team_data()
    print(f"      Referee data: {len(ref_df)} referees")
    print(f"      Team data: {len(team_df)} teams")

    features = build_feature_matrix(ref_df, team_df)
    complete = features.dropna(subset=["ht_games", "at_games"])
    print(f"      Matches with complete data: {len(complete)} / {len(features)}")

    classifier = CardClassifier()
    if not classifier.load():
        print("      No trained model found -- using Poisson-only predictions")

    predictions = predict_upcoming(features, classifier)
    print(f"      Predictions generated for {len(predictions)} matches")

    return predictions


# ── Step 6: Merge odds into predictions ──────────────────────────────────

def _teams_fuzzy_match(pred_home, pred_away, odds_home, odds_away):
    """
    Substring match in both directions to handle name variants like
    'Real Sociedad' vs 'Real Sociedad San Sebastian'.
    """
    def _match(a, b):
        return a == b or a in b or b in a

    return _match(pred_home, odds_home) and _match(pred_away, odds_away)


def merge_odds(predictions, odds_sources):
    print_step(6, "Merging odds data ...")

    for source_name, source_df in odds_sources:
        try:
            odds_cols = [c for c in source_df.columns if c not in
                         ["home_team", "away_team", "match_id", "commence_time"]]

            matched_count = 0
            new_cols = {c: [] for c in odds_cols}

            for _, pred_row in predictions.iterrows():
                pred_home = str(pred_row["Home Team"]).lower()
                pred_away = str(pred_row["Away Team"]).lower()

                matched = None
                for _, odds_row in source_df.iterrows():
                    odds_home = str(odds_row["home_team"]).lower()
                    odds_away = str(odds_row["away_team"]).lower()
                    if _teams_fuzzy_match(pred_home, pred_away, odds_home, odds_away):
                        matched = odds_row
                        break

                if matched is not None:
                    matched_count += 1
                    for c in odds_cols:
                        new_cols[c].append(matched.get(c))
                else:
                    for c in odds_cols:
                        new_cols[c].append(None)

            for c, vals in new_cols.items():
                predictions[c] = vals

            print(f"      Merged odds: {matched_count} matches")
        except Exception as e:
            print(f"      Warning merging odds: {e}")

    return predictions


# ── Step 7: Value detection + recommendations ────────────────────────────

def run_value_detection(predictions, target_matches=None):
    print_step(7, "Detecting value bets ...")

    from src.analysis.value_detector import detect_value_bets
    from src.analysis.recommendations import (
        build_recommendations_table,
        print_recommendations,
        export_recommendations,
    )

    value_bets = detect_value_bets(predictions, target_matches=target_matches)
    print(f"      Value bets found: {len(value_bets)}")

    recs_table = build_recommendations_table(predictions, value_bets)

    print_recommendations(recs_table, value_bets)
    export_recommendations(recs_table, value_bets, predictions)

    if not value_bets.empty:
        print_step(8, "Generating match cards & overview ...")
        try:
            from src.analysis.match_cards import generate_all_match_cards, generate_overview_image
            generate_all_match_cards()
            generate_overview_image()
        except Exception as e:
            print(f"      Match-card generation failed: {e}")

        print_step(9, "Logging bets to Google Sheets ...")
        try:
            from src.analysis.sheets_logger import log_bets
            bets_to_log = []
            for _, row in value_bets.iterrows():
                bets_to_log.append({
                    "home_team":   row["Home Team"],
                    "away_team":   row["Away Team"],
                    "competition": row.get("Competition", "---"),
                    "signal":      "under" if "Under" in row["Bet"] else "over",
                    "bookmaker":   row["Bookmaker"],
                    "odds":        row["Odds"],
                })
            log_bets(bets_to_log)
        except Exception as e:
            # Never let Sheets-logging failures kill the rest of the pipeline
            # (incl. the toast notification that happens after this returns)
            print(f"      Sheets logging skipped: {e}")

    return recs_table, value_bets


# ── Utilities ────────────────────────────────────────────────────────────

def _copy_to_drive(files):
    if not os.path.exists(GOOGLE_DRIVE_PATH):
        return
    for f in files:
        if os.path.exists(f):
            try:
                shutil.copy2(f, os.path.join(GOOGLE_DRIVE_PATH, os.path.basename(f)))
            except Exception:
                pass


def retrain_model():
    """Retrain the ML model on latest historical data."""
    print_header("RETRAINING MODEL")
    from src.model.historical import download_all_historical_data
    from src.model.card_model import train_final_model, walk_forward_evaluate, load_historical_data

    print_step("R1", "Downloading latest historical data ...")
    download_all_historical_data()

    print_step("R2", "Evaluating model (walk-forward CV) ...")
    hist = load_historical_data()
    if not hist.empty:
        walk_forward_evaluate(hist, n_splits=5)

    print_step("R3", "Training final model ...")
    train_final_model()

    print("\n  Model retrained successfully.")


# ── Main entry point ─────────────────────────────────────────────────────

def main():
    skip_scrape = "--skip-scrape" in sys.argv
    do_retrain = "--retrain" in sys.argv
    refresh_odds = "--refresh-odds" in sys.argv

    ensure_dirs()

    print_header(f"DAILY CARD BETTING ANALYSIS -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if do_retrain:
        retrain_model()
        return

    try:
        if not skip_scrape:
            # Step 1: Get referee stats
            run_referee_scraper()

            # Step 2: Filter by criteria -> only bettable matches
            target_matches = run_referee_filter()

            if not target_matches:
                print_header("NO MATCHES MEET CRITERIA")
                print("  No referees passed the betting criteria today.")
                print("  Criteria: min 50 games, Under: +3.5%<=45 +4.5%<=30, Over: +3.5%>=65 +4.5%>=55")
                from src.notify import send_run_notification
                send_run_notification(None, None, target_count=0)
                return

            # Step 3: Get team stats (for model features)
            run_team_scraper()

            # Step 4: Fetch odds ONLY for target matches
            odds_sources = run_targeted_odds(target_matches, force_refresh=refresh_odds)
        else:
            print("\n  [Skipping scraping -- using cached data]")
            from src.analysis.referee_filter import get_target_matches, print_filter_summary
            target_matches = get_target_matches()
            print_filter_summary(target_matches)

            odds_sources = []
            if os.path.exists(THEODDS_CSV):
                theodds_df = pd.read_csv(THEODDS_CSV)
                odds_sources.append(("theodds", theodds_df))

        # Step 5-6: Predict + merge
        predictions = run_predictions()
        predictions = merge_odds(predictions, odds_sources)

        # Step 7-8: Value detection + match cards
        recs, value_bets = run_value_detection(predictions, target_matches=target_matches)

        # Toast notification — fires every run regardless of bet count
        from src.notify import send_run_notification
        send_run_notification(value_bets, recs, target_count=len(target_matches))

        print_header("ANALYSIS COMPLETE")
        print(f"  Target matches: {len(target_matches)}")
        print(f"  Results saved to: data/output/")
        if not value_bets.empty:
            print(f"  Value bets: {len(value_bets)} | Avg EV: +{value_bets['EV%'].mean():.1f}%")
        else:
            print("  No value bets found in current data.")
        print()

    except KeyboardInterrupt:
        print("\n\n  Analysis interrupted.")
    except Exception as e:
        print(f"\n  Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
