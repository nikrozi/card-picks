#!/usr/bin/env python3
"""
Value Bet Detector
Compares model-predicted probabilities against bookmaker odds to identify
positive expected value (EV) bets.
"""

import pandas as pd
import numpy as np


# Minimum edge required to flag a bet as a recommendation
MIN_EV_THRESHOLD = 0.03  # 3%

# Minimum model confidence to consider a bet
MIN_CONFIDENCE = 0.40

# Minimum decimal odds to consider a bet (from referee criteria)
MIN_ODDS = 1.75


def odds_to_implied_prob(decimal_odds):
    """Convert decimal odds to implied probability."""
    if pd.isna(decimal_odds) or decimal_odds <= 1.0:
        return np.nan
    return 1.0 / decimal_odds


def implied_prob_to_fair_odds(prob):
    """Convert a probability to fair decimal odds."""
    if pd.isna(prob) or prob <= 0:
        return np.nan
    return 1.0 / prob


def calculate_ev(model_prob, decimal_odds):
    """
    Calculate expected value of a bet.
    EV = (model_prob * net_payout) - (1 - model_prob) * stake
    With unit stake of 1: EV = model_prob * (odds - 1) - (1 - model_prob)
    """
    if pd.isna(model_prob) or pd.isna(decimal_odds) or decimal_odds <= 1.0:
        return np.nan
    return model_prob * (decimal_odds - 1) - (1 - model_prob)


def calculate_kelly_fraction(model_prob, decimal_odds, fraction=0.25):
    """
    Kelly criterion for optimal bet sizing.
    Returns fraction of bankroll to bet.
    Uses fractional Kelly (default 25%) for safety.

    Full Kelly: f = (p * (b+1) - 1) / b  where b = odds - 1, p = model_prob
    """
    if pd.isna(model_prob) or pd.isna(decimal_odds) or decimal_odds <= 1.0:
        return 0.0
    b = decimal_odds - 1
    full_kelly = (model_prob * (b + 1) - 1) / b
    if full_kelly <= 0:
        return 0.0
    return full_kelly * fraction


def detect_value_bets(predictions_df, odds_df=None, target_matches=None):
    """
    Core value detection function.

    Parameters:
        predictions_df: DataFrame from card_model.predict_upcoming() with columns:
            Home Team, Away Team, ensemble_p_over_3.5, ensemble_p_over_4.5, etc.
        odds_df: DataFrame with bookmaker odds. If None, uses odds columns
                 already present in predictions_df (from onemillionpredictions merge).
        target_matches: list of dicts from referee_filter with 'home_team',
                        'away_team', 'signal' keys. When provided, only the
                        approved bet direction is evaluated per match.

    Returns:
        DataFrame of recommended bets sorted by EV descending.
    """
    df = predictions_df.copy()
    recommendations = []

    # Build signal lookup: (home_lower, away_lower) -> "over" or "under"
    signal_map = {}
    if target_matches:
        for m in target_matches:
            key = (m["home_team"].lower(), m["away_team"].lower())
            signal_map[key] = m["signal"]

    # Build a list of (threshold, bet_side, model_prob_col) combos to evaluate
    bet_specs = []
    for threshold in [3.5, 4.5]:
        over_col = f"ensemble_p_over_{threshold}"
        under_col = f"ensemble_p_under_{threshold}"
        if over_col in df.columns:
            bet_specs.append((threshold, "Over", over_col))
        if under_col in df.columns:
            bet_specs.append((threshold, "Under", under_col))

    # Determine which odds columns are available
    bookmaker_cols = {}

    # Check for Betfair columns
    if "betfair_over_back" in df.columns:
        bookmaker_cols["betfair"] = {
            "over": "betfair_over_back",
            "under": "betfair_under_back",
        }

    # Check for generic Over_Odds / Under_Odds (from onemillionpredictions)
    if "Over_Odds" in df.columns:
        bookmaker_cols["market_consensus"] = {
            "over": "Over_Odds",
            "under": "Under_Odds",
        }
    if "Over Odds" in df.columns:
        bookmaker_cols["market_consensus"] = {
            "over": "Over Odds",
            "under": "Under Odds",
        }

    # Check for The Odds API columns: over_{line}_odds / under_{line}_odds
    theodds_lines = set()
    for col in df.columns:
        if col.startswith("over_") and col.endswith("_odds"):
            line_str = col.replace("over_", "").replace("_odds", "")
            theodds_lines.add(line_str)

    for idx, row in df.iterrows():
        home = row.get("Home Team", "")
        away = row.get("Away Team", "")
        referee = row.get("Name", "")
        competition = row.get("Competition", "---")

        for threshold, side, prob_col in bet_specs:
            # Enforce referee filter signal and correct bet lines
            if signal_map:
                match_key = (str(home).lower(), str(away).lower())
                allowed_signal = signal_map.get(match_key)
                if allowed_signal is None:
                    continue
                # Under signal: only Under bets on lines 4.5+
                if allowed_signal == "under":
                    if side != "Under" or threshold < 4.5:
                        continue
                # Over signal: only Over bets on lines below 4.5
                if allowed_signal == "over":
                    if side != "Over" or threshold >= 4.5:
                        continue

            model_prob = row.get(prob_col)
            if pd.isna(model_prob) or model_prob < MIN_CONFIDENCE:
                continue

            card_line = row.get("Card_Total") or row.get("Card Total") or row.get("card_line")
            if pd.notna(card_line):
                try:
                    card_line = float(card_line)
                except (ValueError, TypeError):
                    card_line = None

            # Collect odds from ALL sources, then pick the best
            candidates = []

            # Source: Betfair (line-agnostic exchange odds)
            if "betfair" in bookmaker_cols:
                bk_cols = bookmaker_cols["betfair"]
                odds_col = bk_cols["over"] if side == "Over" else bk_cols["under"]
                try:
                    odds_val = float(row.get(odds_col, np.nan))
                except (ValueError, TypeError):
                    odds_val = np.nan
                if not pd.isna(odds_val) and odds_val >= MIN_ODDS:
                    candidates.append((odds_val, "betfair"))

            # Source: OneMillionPredictions — only when Card_Total matches threshold
            if "market_consensus" in bookmaker_cols:
                row_card_total = None
                for ct_col in ("Card_Total", "Card Total", "card_line"):
                    try:
                        row_card_total = float(row.get(ct_col, np.nan))
                        if not pd.isna(row_card_total):
                            break
                    except (ValueError, TypeError):
                        continue
                if pd.notna(row_card_total) and abs(row_card_total - threshold) < 0.01:
                    bk_cols = bookmaker_cols["market_consensus"]
                    odds_col = bk_cols["over"] if side == "Over" else bk_cols["under"]
                    try:
                        odds_val = float(row.get(odds_col, np.nan))
                    except (ValueError, TypeError):
                        odds_val = np.nan
                    if not pd.isna(odds_val) and odds_val >= MIN_ODDS:
                        candidates.append((odds_val, "market_consensus"))

            # Source: The Odds API per-line columns (best + specific bookmakers)
            line_str = str(threshold).replace(".", "_")
            if line_str in theodds_lines:
                side_lower = side.lower()

                # Specific tracked bookmakers first (Bet365, Unibet)
                for bk in ("bet365", "unibet"):
                    bk_col = f"{side_lower}_{line_str}_{bk}"
                    if bk_col in df.columns:
                        try:
                            odds_val = float(row.get(bk_col, np.nan))
                        except (ValueError, TypeError):
                            odds_val = np.nan
                        if not pd.isna(odds_val) and odds_val >= MIN_ODDS:
                            candidates.append((odds_val, bk.capitalize()))

                # Also include the overall best (may be a different bookmaker)
                odds_col = f"{side_lower}_{line_str}_odds"
                bk_col   = f"{side_lower}_{line_str}_bookmaker"
                try:
                    odds_val = float(row.get(odds_col, np.nan))
                except (ValueError, TypeError):
                    odds_val = np.nan
                if not pd.isna(odds_val) and odds_val >= MIN_ODDS:
                    bk_name = row.get(bk_col, "theodds")
                    if pd.isna(bk_name):
                        bk_name = "theodds"
                    candidates.append((odds_val, bk_name))

            if not candidates:
                continue

            # Pick the BEST odds across all sources
            best_odds, best_bk = max(candidates, key=lambda x: x[0])

            implied = odds_to_implied_prob(best_odds)
            ev = calculate_ev(model_prob, best_odds)
            kelly = calculate_kelly_fraction(model_prob, best_odds)

            if ev >= MIN_EV_THRESHOLD:
                recommendations.append({
                    "Home Team": home,
                    "Away Team": away,
                    "Competition": competition,
                    "Referee": referee,
                    "Bet": f"{side} {threshold} Cards",
                    "Model Prob": round(model_prob * 100, 1),
                    "Implied Prob": round(implied * 100, 1),
                    "Edge": round((model_prob - implied) * 100, 1),
                    "Odds": best_odds,
                    "Bookmaker": best_bk,
                    "EV%": round(ev * 100, 1),
                    "Kelly%": round(kelly * 100, 1),
                    "Card Line": card_line or threshold,
                })

    if not recommendations:
        return pd.DataFrame()

    result = pd.DataFrame(recommendations)
    result = result.sort_values("EV%", ascending=False).reset_index(drop=True)

    return result


def find_best_bookmaker(recommendations_df):
    """
    For each unique bet (match + side + threshold), find which bookmaker
    offers the best odds.
    """
    if recommendations_df.empty:
        return pd.DataFrame()

    group_cols = ["Home Team", "Away Team", "Bet"]
    best_rows = []

    for key, group in recommendations_df.groupby(group_cols):
        best = group.loc[group["Odds"].idxmax()]
        best_rows.append(best)

    return pd.DataFrame(best_rows).sort_values("EV%", ascending=False).reset_index(drop=True)


def format_recommendations(recs_df):
    """Format recommendations for display."""
    if recs_df.empty:
        print("\nNo value bets found with current data and thresholds.")
        print(f"(Minimum EV threshold: {MIN_EV_THRESHOLD*100:.0f}%)")
        return

    print("\n" + "=" * 100)
    print("RECOMMENDED BETS (sorted by Expected Value)")
    print("=" * 100)

    for _, row in recs_df.iterrows():
        match = f"{row['Home Team']} vs {row['Away Team']}"
        print(f"\n  {match}")
        print(f"    Referee: {row['Referee']}")
        print(f"    Bet: {row['Bet']} @ {row['Odds']:.2f} ({row['Bookmaker']})")
        print(f"    Model: {row['Model Prob']:.1f}% | Implied: {row['Implied Prob']:.1f}% | Edge: +{row['Edge']:.1f}pp")
        print(f"    EV: +{row['EV%']:.1f}% | Kelly stake: {row['Kelly%']:.1f}% of bankroll")

    print("\n" + "=" * 100)
    print(f"Total value bets found: {len(recs_df)}")
    print(f"Average EV: +{recs_df['EV%'].mean():.1f}%")
    print(f"Average edge: +{recs_df['Edge'].mean():.1f}pp")
    print("=" * 100)


if __name__ == "__main__":
    print("=== Value Detector Test ===")

    # Load model predictions
    from src.model.features import load_referee_data, load_team_data, build_feature_matrix
    from src.model.card_model import predict_upcoming, CardClassifier

    ref_df = load_referee_data()
    team_df = load_team_data()
    features = build_feature_matrix(ref_df, team_df)

    classifier = CardClassifier()
    classifier.load()
    predictions = predict_upcoming(features, classifier)

    # Merge with odds data
    try:
        from src.paths import ONEMILLION_CSV, VALUE_BETS_CSV
        odds = pd.read_csv(ONEMILLION_CSV)
        from src.utils.name_normalizer import normalize, normalize_dataframe
        normalize_dataframe(odds, ["Home_Team", "Away_Team"])
        odds["Match_Key"] = odds["Home_Team"].str.lower() + "|" + odds["Away_Team"].str.lower()
        predictions["Match_Key"] = predictions["Home Team"].str.lower() + "|" + predictions["Away Team"].str.lower()
        predictions = predictions.merge(
            odds[["Match_Key", "Card_Total", "Over_Odds", "Under_Odds"]],
            on="Match_Key", how="left"
        )
        predictions.drop(columns=["Match_Key"], inplace=True)
        print(f"Merged odds for {predictions['Over_Odds'].notna().sum()} matches")
    except Exception as e:
        print(f"Could not load odds: {e}")

    # Detect value bets
    recs = detect_value_bets(predictions)
    if not recs.empty:
        best = find_best_bookmaker(recs)
        format_recommendations(best)
        best.to_csv(VALUE_BETS_CSV, index=False)
        print(f"\nSaved to {VALUE_BETS_CSV}")
    else:
        format_recommendations(recs)
