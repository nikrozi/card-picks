#!/usr/bin/env python3
"""
Recommendations View
Produces the final output: a table telling you what bets to place,
at which bookmakers, with expected value and Kelly stake sizing.
Outputs to both CSV (for Google Sheets) and formatted console.
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime

from src.analysis.value_detector import detect_value_bets, find_best_bookmaker, calculate_kelly_fraction
from src.paths import (
    GOOGLE_DRIVE_PATH, VALUE_BETS_CSV, RECOMMENDATIONS_CSV, ALL_PREDICTIONS_CSV,
)


def build_recommendations_table(predictions_df, value_bets_df):
    """
    Build the final recommendations table combining model predictions
    with value bet analysis.

    Columns:
        Match | Referee | Model P(O3.5) | Model P(O4.5) |
        Best Bet | Odds | Bookmaker | Implied% | Edge | EV% | Kelly%
    """
    if value_bets_df.empty:
        return pd.DataFrame()

    # Get best bookmaker per bet
    best = find_best_bookmaker(value_bets_df)

    # Merge with model probabilities
    display_rows = []
    for _, bet in best.iterrows():
        home = bet["Home Team"]
        away = bet["Away Team"]

        # Find the matching row in predictions
        mask = (predictions_df["Home Team"] == home) & (predictions_df["Away Team"] == away)
        pred_row = predictions_df[mask]

        p_over_35 = None
        p_over_45 = None
        if len(pred_row) > 0:
            pred_row = pred_row.iloc[0]
            p_over_35 = pred_row.get("ensemble_p_over_3.5")
            p_over_45 = pred_row.get("ensemble_p_over_4.5")

        # Extract Bet365/Unibet specific odds for the relevant line
        bet_type = bet["Bet"]  # e.g. "Under 4.5 Cards" or "Over 3.5 Cards"
        try:
            side_str, line_val, *_ = bet_type.split()
            line_str = line_val.replace(".", "_")
            side_lower = side_str.lower()
        except Exception:
            line_str = ""
            side_lower = ""

        def _bk_odds(bk_key):
            col = f"{side_lower}_{line_str}_{bk_key}"
            if len(pred_row) > 0 and col in pred_row:
                v = pred_row.get(col) if not isinstance(pred_row, pd.DataFrame) else pred_row.iloc[0].get(col)
                try:
                    return f"{float(v):.2f}" if pd.notna(v) else "-"
                except (ValueError, TypeError):
                    return "-"
            return "-"

        display_rows.append({
            "Match": f"{home} vs {away}",
            "Referee": bet["Referee"],
            "Model P(O3.5)": f"{p_over_35*100:.0f}%" if pd.notna(p_over_35) else "-",
            "Model P(O4.5)": f"{p_over_45*100:.0f}%" if pd.notna(p_over_45) else "-",
            "Bet": bet_type,
            "Bet365": _bk_odds("bet365"),
            "Unibet": _bk_odds("unibet"),
            "Best Odds": f"{bet['Odds']:.2f}",
            "Best Bookmaker": bet["Bookmaker"],
            "Implied%": f"{bet['Implied Prob']:.0f}%",
            "Edge": f"+{bet['Edge']:.1f}pp",
            "EV%": f"+{bet['EV%']:.1f}%",
            "Kelly%": f"{bet['Kelly%']:.1f}%",
        })

    return pd.DataFrame(display_rows)


def print_recommendations(recs_table, value_bets_df):
    """Print a clean, formatted summary to the console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    print()
    print("=" * 110)
    print(f"  CARD BETTING RECOMMENDATIONS -- {timestamp}")
    print("=" * 110)

    if recs_table.empty:
        print()
        print("  No value bets found for upcoming matches.")
        print("  This can happen when:")
        print("    - Odds are correctly priced (no edge)")
        print("    - Insufficient data for some matches")
        print("    - Model confidence is below threshold")
        print()
        print("=" * 110)
        return

    # Summary stats
    n_bets = len(recs_table)
    avg_ev = value_bets_df["EV%"].mean() if not value_bets_df.empty else 0

    print()
    print(f"  Found {n_bets} value bets | Average EV: +{avg_ev:.1f}%")
    print()

    # Print each recommendation
    for i, (_, row) in enumerate(recs_table.iterrows(), 1):
        print(f"  {i:2d}. {row['Match']}")
        print(f"      Referee: {row['Referee']}")
        print(f"      >>> {row['Bet']}")
        print(f"      Bet365: {row.get('Bet365', '-')}  |  Unibet: {row.get('Unibet', '-')}  |  Best: {row.get('Best Odds', row.get('Odds', '-'))} ({row.get('Best Bookmaker', row.get('Bookmaker', '-'))})")
        print(f"      Model: {row.get('Model P(O3.5)', '-')} / {row.get('Model P(O4.5)', '-')} "
              f"| Implied: {row['Implied%']} | Edge: {row['Edge']} | EV: {row['EV%']}")
        print(f"      Suggested stake: {row['Kelly%']} of bankroll")
        print()

    print("-" * 110)
    print("  LEGEND:")
    print("    Model P(O3.5) = Model probability of Over 3.5 total cards in match")
    print("    Edge = Model probability minus bookmaker implied probability")
    print("    EV% = Expected value of the bet (positive = profitable long-term)")
    print("    Kelly% = Suggested stake as % of bankroll (fractional Kelly, conservative)")
    print("=" * 110)

    # ── Clean betting slip ──────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  BETTING SLIP")
    print("=" * 60)
    for i, (_, row) in enumerate(recs_table.iterrows(), 1):
        match   = row["Match"]
        bet     = row["Bet"]
        b365    = row.get("Bet365", "-")
        uni     = row.get("Unibet", "-")
        best_bk = row.get("Best Bookmaker", "-")
        best_od = row.get("Best Odds", "-")

        # Choose which bookmaker to use and highlight it
        if b365 != "-" and uni != "-":
            b365_f = float(b365)
            uni_f  = float(uni)
            if b365_f >= uni_f:
                use_bk, use_odds = "Bet365", b365
            else:
                use_bk, use_odds = "Unibet", uni
        elif b365 != "-":
            use_bk, use_odds = "Bet365", b365
        elif uni != "-":
            use_bk, use_odds = "Unibet", uni
        else:
            use_bk, use_odds = best_bk, best_od

        print(f"  {i}. {match}")
        print(f"     {bet}  →  {use_bk} @ {use_odds}")
    print("=" * 60)
    print(f"  Total bets: {n_bets}  |  Stake: £100 per bet")
    print("=" * 60)


def export_recommendations(recs_table, value_bets_df, predictions_df):
    """Export results to CSV files, locally and to Google Drive."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    # Save value bets summary
    if not value_bets_df.empty:
        value_bets_df.to_csv(VALUE_BETS_CSV, index=False)
        print(f"  Saved {VALUE_BETS_CSV} ({len(value_bets_df)} bets)")

    # Save recommendations table
    if not recs_table.empty:
        recs_table.to_csv(RECOMMENDATIONS_CSV, index=False)
        print(f"  Saved {RECOMMENDATIONS_CSV} ({len(recs_table)} bets)")

    # Save full predictions (all matches, even non-value)
    if predictions_df is not None and not predictions_df.empty:
        export_cols = [
            "Home Team", "Away Team", "Name",
            "ref_cards_pg", "team_expected_cards",
            "ensemble_p_over_3.5", "ensemble_p_over_4.5",
            "ml_p_over_3.5", "poisson_p_over_3.5",
            "ml_p_over_4.5", "poisson_p_over_4.5",
        ]
        avail = [c for c in export_cols if c in predictions_df.columns]
        predictions_df[avail].to_csv(ALL_PREDICTIONS_CSV, index=False)
        print(f"  Saved all_predictions.csv ({len(predictions_df)} matches)")

    # Copy to Google Drive if available
    if os.path.exists(GOOGLE_DRIVE_PATH):
        import shutil
        for f in [VALUE_BETS_CSV, RECOMMENDATIONS_CSV, ALL_PREDICTIONS_CSV]:
            if os.path.exists(f):
                shutil.copy2(f, os.path.join(GOOGLE_DRIVE_PATH, os.path.basename(f)))
        print(f"  Synced to Google Drive: {GOOGLE_DRIVE_PATH}")
    else:
        print(f"  Google Drive not available at {GOOGLE_DRIVE_PATH} -- local only")


if __name__ == "__main__":
    from src.model.features import load_referee_data, load_team_data, build_feature_matrix
    from src.model.card_model import predict_upcoming, CardClassifier

    print("=== Building Recommendations ===\n")

    ref_df = load_referee_data()
    team_df = load_team_data()
    features = build_feature_matrix(ref_df, team_df)

    classifier = CardClassifier()
    classifier.load()
    predictions = predict_upcoming(features, classifier)

    # Merge odds
    try:
        from src.paths import ONEMILLION_CSV
        odds = pd.read_csv(ONEMILLION_CSV)
        from src.utils.name_normalizer import normalize_dataframe
        normalize_dataframe(odds, ["Home_Team", "Away_Team"])
        odds["Match_Key"] = odds["Home_Team"].str.lower() + "|" + odds["Away_Team"].str.lower()
        predictions["Match_Key"] = predictions["Home Team"].str.lower() + "|" + predictions["Away Team"].str.lower()
        predictions = predictions.merge(
            odds[["Match_Key", "Card_Total", "Over_Odds", "Under_Odds"]],
            on="Match_Key", how="left"
        )
        predictions.drop(columns=["Match_Key"], inplace=True)
    except Exception as e:
        print(f"  Note: odds data not available ({e})")

    value_bets = detect_value_bets(predictions)
    recs_table = build_recommendations_table(predictions, value_bets)

    print_recommendations(recs_table, value_bets)
    export_recommendations(recs_table, value_bets, predictions)
