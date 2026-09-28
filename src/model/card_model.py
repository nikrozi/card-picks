#!/usr/bin/env python3
"""
Card Prediction Model
Trains and applies ML models to predict over/under card probabilities.
Uses Poisson regression as baseline + Random Forest for classification.
Supports walk-forward cross-validation for honest evaluation.
"""

import os
import pickle
import warnings
import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

from src.model.historical import load_historical_data, compute_referee_historical_stats, compute_team_historical_stats
from src.utils.name_normalizer import normalize
from src import paths

warnings.filterwarnings("ignore")

MODEL_DIR = paths.MODEL_DIR
os.makedirs(MODEL_DIR, exist_ok=True)

# ── Feature construction from historical match-level data ──────────────────

def build_rolling_features(hist_df, window=10):
    """
    For each match in historical data, compute rolling features from
    prior matches (team rolling card averages, referee rolling averages).
    This avoids data leakage: only past data is used for each row.
    """
    hist = hist_df.sort_values("Date").copy()
    hist["Date"] = pd.to_datetime(hist["Date"], dayfirst=True, errors="coerce")
    hist = hist.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)

    # Pre-compute per-team rolling stats
    home_rolling = {}
    away_rolling = {}
    ref_rolling = {}

    features = []

    for idx, row in hist.iterrows():
        ht = row["HomeTeam"]
        at = row["AwayTeam"]
        ref = row.get("Referee", "")

        # Home team rolling card averages (from their previous home games)
        ht_prev = home_rolling.get(ht, [])
        at_prev = away_rolling.get(at, [])
        ref_prev = ref_rolling.get(ref, [])

        feat = {
            "idx": idx,
            "ht_rolling_yf": np.mean([x[0] for x in ht_prev[-window:]]) if ht_prev else np.nan,
            "ht_rolling_ya": np.mean([x[1] for x in ht_prev[-window:]]) if ht_prev else np.nan,
            "at_rolling_yf": np.mean([x[0] for x in at_prev[-window:]]) if at_prev else np.nan,
            "at_rolling_ya": np.mean([x[1] for x in at_prev[-window:]]) if at_prev else np.nan,
            "ref_rolling_cards": np.mean(ref_prev[-window:]) if ref_prev else np.nan,
            "ht_games_count": len(ht_prev),
            "at_games_count": len(at_prev),
            "ref_games_count": len(ref_prev),
        }
        features.append(feat)

        # Update rolling histories
        hy = row.get("HY", 0) or 0
        ay = row.get("AY", 0) or 0
        total = hy + ay

        home_rolling.setdefault(ht, []).append((hy, ay))
        away_rolling.setdefault(at, []).append((ay, hy))
        if ref and isinstance(ref, str) and len(ref) > 1:
            ref_rolling.setdefault(ref, []).append(total)

    feat_df = pd.DataFrame(features).set_index("idx")
    hist = hist.join(feat_df)

    # Combined features
    hist["expected_cards_rolling"] = (
        hist["ht_rolling_yf"].fillna(0) + hist["ht_rolling_ya"].fillna(0) +
        hist["at_rolling_yf"].fillna(0) + hist["at_rolling_ya"].fillna(0)
    ) / 2.0

    hist["ref_vs_expected"] = hist["ref_rolling_cards"] - hist["expected_cards_rolling"]

    return hist


TRAIN_FEATURES = [
    "ht_rolling_yf", "ht_rolling_ya",
    "at_rolling_yf", "at_rolling_ya",
    "ref_rolling_cards",
    "expected_cards_rolling",
    "ref_vs_expected",
]


# ── Poisson baseline model ────────────────────────────────────────────────

class PoissonCardModel:
    """
    Simple Poisson model: predicts total cards as a Poisson process
    with lambda = mean of rolling expected cards and referee average.
    """

    def predict_proba(self, expected_cards_array):
        """
        Given an array of expected card counts (lambda values),
        return P(Over X.5) for each threshold.
        """
        results = []
        for lam in expected_cards_array:
            if np.isnan(lam) or lam <= 0:
                lam = 4.4  # global average fallback
            row = {}
            for threshold in [2.5, 3.5, 4.5, 5.5]:
                row[f"p_over_{threshold}"] = 1 - poisson.cdf(int(threshold), lam)
                row[f"p_under_{threshold}"] = poisson.cdf(int(threshold), lam)
            results.append(row)
        return pd.DataFrame(results)


# ── ML model (Gradient Boosting) ──────────────────────────────────────────

class CardClassifier:
    """
    Gradient Boosting classifier for Over/Under at each threshold.
    Trains separate binary classifiers for 3.5 and 4.5.
    """

    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.thresholds = [3.5, 4.5]

    def train(self, X, y_dict):
        """
        Train classifiers.
        X: feature DataFrame
        y_dict: {threshold: binary_target_series}
        """
        for t in self.thresholds:
            target = y_dict[t]
            mask = X.notna().all(axis=1) & target.notna()
            X_clean = X[mask]
            y_clean = target[mask]

            if len(X_clean) < 100:
                print(f"  Skipping threshold {t}: only {len(X_clean)} samples")
                continue

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_clean)

            model = GradientBoostingClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                min_samples_leaf=20,
                random_state=42,
            )
            model.fit(X_scaled, y_clean)

            self.models[t] = model
            self.scalers[t] = scaler
            print(f"  Trained Over {t} model: {len(X_clean)} samples, "
                  f"train accuracy = {model.score(X_scaled, y_clean):.3f}")

    def predict_proba(self, X):
        """
        Predict P(Over threshold) for each threshold.
        Returns DataFrame with columns p_over_3.5, p_over_4.5, etc.
        """
        result = pd.DataFrame(index=X.index)
        for t in self.thresholds:
            if t not in self.models:
                result[f"p_over_{t}"] = np.nan
                result[f"p_under_{t}"] = np.nan
                continue

            mask = X.notna().all(axis=1)
            proba = np.full(len(X), np.nan)
            if mask.any():
                X_scaled = self.scalers[t].transform(X[mask])
                proba[mask] = self.models[t].predict_proba(X_scaled)[:, 1]

            result[f"p_over_{t}"] = proba
            result[f"p_under_{t}"] = 1 - proba

        return result

    def save(self, path=None):
        if path is None:
            path = os.path.join(MODEL_DIR, "card_classifier.pkl")
        with open(path, "wb") as f:
            pickle.dump({"models": self.models, "scalers": self.scalers}, f)
        print(f"Model saved to {path}")

    def load(self, path=None):
        if path is None:
            path = os.path.join(MODEL_DIR, "card_classifier.pkl")
        if not os.path.exists(path):
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.models = data["models"]
        self.scalers = data["scalers"]
        print(f"Model loaded from {path}")
        return True


# ── Walk-forward cross-validation ─────────────────────────────────────────

def walk_forward_evaluate(hist_df, n_splits=5):
    """
    Evaluate the model with walk-forward (time-series) cross-validation.
    Returns a summary of performance metrics.
    """
    print("\n=== Walk-Forward Cross-Validation ===")

    hist_feat = build_rolling_features(hist_df, window=10)

    # Only use rows with sufficient history
    mask = hist_feat["ht_games_count"] >= 5
    hist_feat = hist_feat[mask].reset_index(drop=True)

    X = hist_feat[TRAIN_FEATURES]
    valid_mask = X.notna().all(axis=1)
    hist_feat = hist_feat[valid_mask].reset_index(drop=True)
    X = hist_feat[TRAIN_FEATURES]

    tscv = TimeSeriesSplit(n_splits=n_splits)
    results = []

    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]

        for threshold in [3.5, 4.5]:
            target_col = f"Over_{threshold}"
            y_train = hist_feat[target_col].iloc[train_idx]
            y_test = hist_feat[target_col].iloc[test_idx]

            # Train model on this fold
            scaler = StandardScaler()
            X_train_sc = scaler.fit_transform(X_train)
            X_test_sc = scaler.transform(X_test)

            model = GradientBoostingClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, min_samples_leaf=20, random_state=42,
            )
            model.fit(X_train_sc, y_train)

            proba = model.predict_proba(X_test_sc)[:, 1]
            preds = (proba >= 0.5).astype(int)

            acc = accuracy_score(y_test, preds)
            brier = brier_score_loss(y_test, proba)
            ll = log_loss(y_test, proba)

            # Poisson baseline for comparison
            lam = hist_feat["expected_cards_rolling"].iloc[test_idx].values
            lam = np.where(np.isnan(lam) | (lam <= 0), 4.4, lam)
            poisson_proba = 1 - poisson.cdf(int(threshold), lam)
            poisson_preds = (poisson_proba >= 0.5).astype(int)
            poisson_acc = accuracy_score(y_test, poisson_preds)
            poisson_brier = brier_score_loss(y_test, poisson_proba)

            results.append({
                "fold": fold + 1,
                "threshold": threshold,
                "ml_accuracy": acc,
                "ml_brier": brier,
                "ml_logloss": ll,
                "poisson_accuracy": poisson_acc,
                "poisson_brier": poisson_brier,
                "test_size": len(y_test),
                "base_rate": y_test.mean(),
            })

            print(f"  Fold {fold+1} | Over {threshold} | "
                  f"ML acc={acc:.3f} brier={brier:.4f} | "
                  f"Poisson acc={poisson_acc:.3f} brier={poisson_brier:.4f} | "
                  f"n={len(y_test)} base_rate={y_test.mean():.3f}")

    results_df = pd.DataFrame(results)

    print("\n--- Average Performance ---")
    avg = results_df.groupby("threshold")[
        ["ml_accuracy", "ml_brier", "ml_logloss", "poisson_accuracy", "poisson_brier"]
    ].mean()
    print(avg.round(4).to_string())

    return results_df


# ── Train final model ─────────────────────────────────────────────────────

def train_final_model():
    """
    Train the final production model on all available historical data.
    Saves the trained model to disk.
    """
    print("=== Training Final Card Model ===\n")

    hist = load_historical_data()
    if hist.empty:
        print("No historical data. Run historical_data_collector.py first.")
        return None

    print(f"Historical data: {len(hist)} matches")

    # Build features
    hist_feat = build_rolling_features(hist, window=10)
    mask = (hist_feat["ht_games_count"] >= 5) & hist_feat[TRAIN_FEATURES].notna().all(axis=1)
    hist_feat = hist_feat[mask].reset_index(drop=True)
    print(f"Training samples (after filtering): {len(hist_feat)}")

    X = hist_feat[TRAIN_FEATURES]
    y_dict = {
        3.5: hist_feat["Over_3.5"],
        4.5: hist_feat["Over_4.5"],
    }

    classifier = CardClassifier()
    classifier.train(X, y_dict)
    classifier.save()

    # Feature importance
    for t, model in classifier.models.items():
        importances = model.feature_importances_
        feat_imp = sorted(zip(TRAIN_FEATURES, importances), key=lambda x: -x[1])
        print(f"\n  Feature importance (Over {t}):")
        for fname, imp in feat_imp:
            print(f"    {fname:30s} {imp:.4f}")

    return classifier


# ── Predict for upcoming matches ──────────────────────────────────────────

def predict_upcoming(feature_df, classifier=None):
    """
    Given a feature DataFrame (from features.py build_feature_matrix),
    predict over/under probabilities for each match.

    Maps the live features to the model's expected input format:
        ref_cards_pg -> ref_rolling_cards
        ht_cards_for -> ht_rolling_yf
        etc.
    """
    if classifier is None:
        classifier = CardClassifier()
        if not classifier.load():
            print("No trained model found. Train first with train_final_model().")
            return feature_df

    # Map live scraped features to the model's rolling feature names
    mapping = {
        "ht_cards_for": "ht_rolling_yf",
        "ht_cards_against": "ht_rolling_ya",
        "at_cards_for": "at_rolling_yf",
        "at_cards_against": "at_rolling_ya",
        "ref_cards_pg": "ref_rolling_cards",
        "team_expected_cards": "expected_cards_rolling",
    }

    pred_df = feature_df.copy()
    for src, dst in mapping.items():
        if src in pred_df.columns:
            pred_df[dst] = pred_df[src]

    # Compute ref_vs_expected if not present
    if "ref_vs_expected" not in pred_df.columns:
        pred_df["ref_vs_expected"] = (
            pred_df.get("ref_rolling_cards", pd.Series(dtype=float)) -
            pred_df.get("expected_cards_rolling", pd.Series(dtype=float))
        )

    # Ensure all feature columns exist
    for col in TRAIN_FEATURES:
        if col not in pred_df.columns:
            pred_df[col] = np.nan

    X = pred_df[TRAIN_FEATURES]

    # ML predictions
    ml_proba = classifier.predict_proba(X)
    for col in ml_proba.columns:
        pred_df[f"ml_{col}"] = ml_proba[col].values

    # Poisson predictions as alternative
    lam = pred_df["expected_cards_rolling"].values
    poisson_model = PoissonCardModel()
    poisson_proba = poisson_model.predict_proba(lam)
    for col in poisson_proba.columns:
        pred_df[f"poisson_{col}"] = poisson_proba[col].values

    # Ensemble: average of ML and Poisson
    for threshold in [3.5, 4.5]:
        ml_col = f"ml_p_over_{threshold}"
        po_col = f"poisson_p_over_{threshold}"
        if ml_col in pred_df.columns and po_col in pred_df.columns:
            pred_df[f"ensemble_p_over_{threshold}"] = (
                pred_df[ml_col].fillna(pred_df[po_col]) * 0.6 +
                pred_df[po_col].fillna(pred_df[ml_col]) * 0.4
            )
            pred_df[f"ensemble_p_under_{threshold}"] = 1 - pred_df[f"ensemble_p_over_{threshold}"]

    return pred_df


if __name__ == "__main__":
    hist = load_historical_data()
    if hist.empty:
        print("Run historical_data_collector.py first.")
    else:
        # Evaluate with walk-forward CV
        cv_results = walk_forward_evaluate(hist, n_splits=5)

        # Train final model
        classifier = train_final_model()

        if classifier:
            # Quick test: predict on a sample
            from src.model.features import load_referee_data, load_team_data, build_feature_matrix
            ref_df = load_referee_data()
            team_df = load_team_data()
            features = build_feature_matrix(ref_df, team_df)
            predictions = predict_upcoming(features, classifier)

            display_cols = ["Home Team", "Away Team", "Name"]
            for t in [3.5, 4.5]:
                for prefix in ["ml_p_over_", "poisson_p_over_", "ensemble_p_over_"]:
                    col = f"{prefix}{t}"
                    if col in predictions.columns:
                        display_cols.append(col)

            avail = [c for c in display_cols if c in predictions.columns]
            print("\n=== Predictions for Upcoming Matches ===")
            print(predictions[avail].to_string(index=False, float_format="%.3f"))
