"""
Value Bet Match Card Generator

Creates a visual stat card (PNG image) for each match flagged as a value bet.
Cards include referee stats, team data, model probabilities, odds, and edge.
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from datetime import datetime

from src.paths import (
    OUTPUT_DIR, VALUE_BETS_CSV, ALL_PREDICTIONS_CSV, REF_STATS_CSV,
    THEODDS_CSV,
)

CARDS_DIR = os.path.join(OUTPUT_DIR, "match_cards")


# ── Colors ────────────────────────────────────────────────────────────────

BG_DARK    = "#1a1a2e"
BG_CARD    = "#16213e"
BG_SECTION = "#0f3460"
ACCENT     = "#e94560"
ACCENT2    = "#53a8b6"
GREEN      = "#4ecca3"
GOLD       = "#f5c542"
WHITE      = "#eaeaea"
GREY       = "#8a8a9a"
RED_CARD   = "#e94560"


def _draw_rounded_rect(ax, x, y, w, h, color, radius=0.02, alpha=1.0):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=color, edgecolor="none", alpha=alpha,
        transform=ax.transAxes, zorder=1,
    )
    ax.add_patch(box)


def _bar(ax, x, y, width, pct, color_fill, color_bg="#2a2a4a", height=0.018):
    _draw_rounded_rect(ax, x, y, width, height, color_bg, radius=0.005)
    fill_w = width * max(0, min(1, pct / 100))
    if fill_w > 0.001:
        _draw_rounded_rect(ax, x, y, fill_w, height, color_fill, radius=0.005)


def generate_match_card(value_bet, prediction, ref_stats, odds_row, output_path):
    """Generate a single match card image."""

    home = value_bet["Home Team"]
    away = value_bet["Away Team"]
    referee = value_bet.get("Referee", "")
    bet_label = value_bet["Bet"]
    model_prob = value_bet["Model Prob"]
    implied_prob = value_bet["Implied Prob"]
    edge = value_bet["Edge"]
    odds = value_bet["Odds"]
    bookmaker = value_bet["Bookmaker"]
    ev_pct = value_bet["EV%"]
    kelly_pct = value_bet["Kelly%"]

    fig, ax = plt.subplots(1, 1, figsize=(7, 9.5), dpi=150)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor(BG_DARK)
    ax.set_facecolor(BG_DARK)

    # ── Main card background ──
    _draw_rounded_rect(ax, 0.03, 0.02, 0.94, 0.96, BG_CARD, radius=0.02)

    # ── Header: match info ──
    _draw_rounded_rect(ax, 0.05, 0.88, 0.90, 0.08, ACCENT, radius=0.015)
    ax.text(0.50, 0.935, "VALUE BET", ha="center", va="center",
            fontsize=9, color=WHITE, fontweight="bold", alpha=0.7,
            transform=ax.transAxes, zorder=5)
    ax.text(0.50, 0.905, f"{home}  vs  {away}", ha="center", va="center",
            fontsize=14, color="white", fontweight="bold",
            transform=ax.transAxes, zorder=5)

    # ── Bet recommendation box ──
    _draw_rounded_rect(ax, 0.05, 0.795, 0.90, 0.07, BG_SECTION, radius=0.012)
    ax.text(0.50, 0.845, bet_label, ha="center", va="center",
            fontsize=16, color=GOLD, fontweight="bold",
            transform=ax.transAxes, zorder=5)
    ax.text(0.50, 0.813, f"@ {odds:.2f}  •  {bookmaker}", ha="center", va="center",
            fontsize=11, color=WHITE, transform=ax.transAxes, zorder=5)

    # ── Key metrics row ──
    y_metrics = 0.735
    metrics = [
        ("Model", f"{model_prob:.1f}%", GREEN),
        ("Implied", f"{implied_prob:.1f}%", GREY),
        ("Edge", f"+{edge:.1f}pp", ACCENT),
        ("EV", f"+{ev_pct:.1f}%", GOLD),
        ("Kelly", f"{kelly_pct:.1f}%", ACCENT2),
    ]
    box_w = 0.90 / len(metrics)
    for i, (label, val, color) in enumerate(metrics):
        cx = 0.05 + box_w * i + box_w / 2
        _draw_rounded_rect(ax, 0.05 + box_w * i + 0.005, y_metrics, box_w - 0.01, 0.045, BG_SECTION, radius=0.008)
        ax.text(cx, y_metrics + 0.032, val, ha="center", va="center",
                fontsize=12, color=color, fontweight="bold",
                transform=ax.transAxes, zorder=5)
        ax.text(cx, y_metrics + 0.012, label, ha="center", va="center",
                fontsize=7, color=GREY, transform=ax.transAxes, zorder=5)

    # ── Referee section ──
    y_ref = 0.545
    _draw_rounded_rect(ax, 0.05, y_ref, 0.90, 0.17, BG_SECTION, radius=0.012)
    ax.text(0.10, y_ref + 0.145, f"REFEREE: {referee}", ha="left", va="center",
            fontsize=10, color=WHITE, fontweight="bold",
            transform=ax.transAxes, zorder=5)

    if ref_stats is not None and not ref_stats.empty:
        rs = ref_stats.iloc[0]
        ypg = rs.get("Yellow PG", 0)
        rpg = rs.get("Reds PG", 0)
        total_y = rs.get("Yellows", 0)
        home_pg = rs.get("Home PG", 0)
        away_pg = rs.get("Away PG", 0)

        ref_items_l = [
            ("Yellows/Game", f"{ypg:.2f}", ypg / 6 * 100),
            ("Reds/Game", f"{rpg:.2f}", rpg / 1 * 100),
            ("Home Cards/G", f"{home_pg:.2f}", home_pg / 4 * 100),
            ("Away Cards/G", f"{away_pg:.2f}", away_pg / 4 * 100),
        ]
        for i, (label, val, pct) in enumerate(ref_items_l):
            yi = y_ref + 0.115 - i * 0.028
            ax.text(0.10, yi, label, ha="left", va="center",
                    fontsize=8, color=GREY, transform=ax.transAxes, zorder=5)
            ax.text(0.35, yi, val, ha="right", va="center",
                    fontsize=8, color=WHITE, fontweight="bold",
                    transform=ax.transAxes, zorder=5)
            _bar(ax, 0.37, yi - 0.009, 0.18, pct, ACCENT2)

        over_pcts = {
            "+3.5%": rs.get("+3.5%", 0),
            "+4.5%": rs.get("+4.5%", 0),
        }
        ax.text(0.65, y_ref + 0.145, "Over %", ha="left", va="center",
                fontsize=8, color=GREY, transform=ax.transAxes, zorder=5)
        for i, (label, pct) in enumerate(over_pcts.items()):
            yi = y_ref + 0.115 - i * 0.035
            ax.text(0.65, yi, label, ha="left", va="center",
                    fontsize=9, color=GREY, transform=ax.transAxes, zorder=5)
            color = GREEN if pct > 50 else ACCENT if pct < 30 else WHITE
            ax.text(0.82, yi, f"{pct:.1f}%", ha="left", va="center",
                    fontsize=11, color=color, fontweight="bold",
                    transform=ax.transAxes, zorder=5)
            _bar(ax, 0.65, yi - 0.015, 0.28, pct, color)

    # ── Model breakdown section ──
    y_model = 0.38
    _draw_rounded_rect(ax, 0.05, y_model, 0.90, 0.15, BG_SECTION, radius=0.012)
    ax.text(0.10, y_model + 0.125, "MODEL BREAKDOWN", ha="left", va="center",
            fontsize=10, color=WHITE, fontweight="bold",
            transform=ax.transAxes, zorder=5)

    if prediction is not None and not prediction.empty:
        p = prediction.iloc[0]
        ref_cpg = p.get("ref_cards_pg", 0)
        team_exp = p.get("team_expected_cards", 0)

        model_items = [
            ("Ref cards/game", f"{ref_cpg:.2f}" if pd.notna(ref_cpg) else "N/A"),
            ("Team expected cards", f"{team_exp:.2f}" if pd.notna(team_exp) else "N/A"),
        ]
        for thresh in [3.5, 4.5]:
            ens = p.get(f"ensemble_p_over_{thresh}")
            ml = p.get(f"ml_p_over_{thresh}")
            poi = p.get(f"poisson_p_over_{thresh}")
            if pd.notna(ens):
                model_items.append((f"P(Over {thresh})", f"{ens*100:.1f}%  (ML {ml*100:.0f}% / Poi {poi*100:.0f}%)"))

        for i, (label, val) in enumerate(model_items):
            yi = y_model + 0.09 - i * 0.025
            ax.text(0.10, yi, label, ha="left", va="center",
                    fontsize=8, color=GREY, transform=ax.transAxes, zorder=5)
            ax.text(0.90, yi, val, ha="right", va="center",
                    fontsize=8, color=WHITE, fontweight="bold",
                    transform=ax.transAxes, zorder=5)

    # ── Available odds section ──
    y_odds = 0.19
    _draw_rounded_rect(ax, 0.05, y_odds, 0.90, 0.175, BG_SECTION, radius=0.012)
    ax.text(0.10, y_odds + 0.15, "BOOKMAKER ODDS (Best Available)", ha="left", va="center",
            fontsize=10, color=WHITE, fontweight="bold",
            transform=ax.transAxes, zorder=5)

    if odds_row is not None and not odds_row.empty:
        o = odds_row.iloc[0]
        odds_items = []
        for col in o.index:
            if col.endswith("_odds") and ("over_" in col or "under_" in col):
                val = o[col]
                if pd.notna(val):
                    bk_col = col.replace("_odds", "_bookmaker")
                    bk = o.get(bk_col, "")
                    parts = col.replace("_odds", "").split("_")
                    side = parts[0].title()
                    line = ".".join(parts[1:])
                    is_our_bet = bet_label.lower().startswith(side.lower()) and line in bet_label
                    odds_items.append((f"{side} {line}", val, bk, is_our_bet))

        odds_items.sort(key=lambda x: (0 if x[3] else 1, x[0]))
        for i, (label, val, bk, is_ours) in enumerate(odds_items[:5]):
            yi = y_odds + 0.115 - i * 0.024
            color = GOLD if is_ours else WHITE
            marker = "  <<<" if is_ours else ""
            ax.text(0.10, yi, label, ha="left", va="center",
                    fontsize=8, color=GREY, transform=ax.transAxes, zorder=5)
            ax.text(0.50, yi, f"{val:.2f}", ha="center", va="center",
                    fontsize=9, color=color, fontweight="bold",
                    transform=ax.transAxes, zorder=5)
            ax.text(0.65, yi, str(bk), ha="left", va="center",
                    fontsize=7, color=GREY, transform=ax.transAxes, zorder=5)
            if is_ours:
                ax.text(0.90, yi, "YOUR BET", ha="right", va="center",
                        fontsize=7, color=GOLD, fontweight="bold",
                        transform=ax.transAxes, zorder=5)

    # ── Footer ──
    _draw_rounded_rect(ax, 0.05, 0.04, 0.90, 0.04, BG_SECTION, radius=0.008, alpha=0.5)
    ax.text(0.50, 0.06, f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}  •  Card Betting Model",
            ha="center", va="center", fontsize=7, color=GREY,
            transform=ax.transAxes, zorder=5)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight", facecolor=BG_DARK, pad_inches=0.1)
    plt.close(fig)


def generate_all_match_cards():
    """Generate match card images only for value bets with real bookmaker odds."""

    if not os.path.exists(VALUE_BETS_CSV):
        print("  No value_bets.csv found. Run the pipeline first.")
        return []

    vb = pd.read_csv(VALUE_BETS_CSV)
    if vb.empty:
        print("  No value bets to visualize.")
        return []

    # Only generate cards for bets with actual bookmaker odds (not market_consensus)
    bettable = vb[vb["Bookmaker"] != "market_consensus"].copy()
    skipped = len(vb) - len(bettable)
    if skipped:
        print(f"    Skipping {skipped} bets without real bookmaker odds")

    if bettable.empty:
        print("  No bettable value bets (all are market_consensus). Skipping individual cards.")
        return []

    pred = pd.read_csv(ALL_PREDICTIONS_CSV) if os.path.exists(ALL_PREDICTIONS_CSV) else pd.DataFrame()
    refs = pd.read_csv(REF_STATS_CSV) if os.path.exists(REF_STATS_CSV) else pd.DataFrame()
    odds = pd.read_csv(THEODDS_CSV) if os.path.exists(THEODDS_CSV) else pd.DataFrame()

    os.makedirs(CARDS_DIR, exist_ok=True)
    generated = []

    for _, bet in bettable.iterrows():
        home = bet["Home Team"]
        away = bet["Away Team"]
        ref_name = bet.get("Referee", "")

        match_pred = pred[(pred["Home Team"] == home) & (pred["Away Team"] == away)] if not pred.empty else pd.DataFrame()

        match_ref = refs[refs["Name"] == ref_name] if not refs.empty and ref_name else pd.DataFrame()

        match_odds = pd.DataFrame()
        if not odds.empty:
            match_odds = odds[
                (odds["home_team"].str.lower() == home.lower()) &
                (odds["away_team"].str.lower() == away.lower())
            ]

        safe_name = f"{home}_vs_{away}".replace(" ", "_").replace("/", "-")
        path = os.path.join(CARDS_DIR, f"{safe_name}.png")

        try:
            generate_match_card(bet, match_pred, match_ref, match_odds, path)
            generated.append(path)
            print(f"    {home} vs {away} -> {os.path.basename(path)}")
        except Exception as e:
            print(f"    {home} vs {away}: error ({e})")

    print(f"\n  {len(generated)} match card(s) saved to {CARDS_DIR}")
    return generated


# ── Overview image ────────────────────────────────────────────────────────

def generate_overview_image():
    """Generate a single overview PNG of all bettable value bets."""

    if not os.path.exists(VALUE_BETS_CSV):
        print("  No value_bets.csv found.")
        return None

    vb = pd.read_csv(VALUE_BETS_CSV)
    if vb.empty:
        print("  No value bets for overview.")
        return None

    bettable = vb[vb["Bookmaker"] != "market_consensus"].copy()
    if bettable.empty:
        print("  No bettable value bets for overview.")
        return None

    # Keep best bet per match (highest EV)
    bettable = bettable.sort_values("EV%", ascending=False)
    best_per_match = bettable.drop_duplicates(subset=["Home Team", "Away Team"], keep="first")

    n_rows = len(best_per_match)
    row_h = 0.065
    header_h = 0.12
    footer_h = 0.06
    fig_height = max(6, 2 + n_rows * 0.55)

    fig, ax = plt.subplots(1, 1, figsize=(12, fig_height), dpi=150)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor(BG_DARK)
    ax.set_facecolor(BG_DARK)

    # Background
    _draw_rounded_rect(ax, 0.01, 0.01, 0.98, 0.98, BG_CARD, radius=0.015)

    # Title
    _draw_rounded_rect(ax, 0.02, 1 - header_h, 0.96, header_h - 0.02, ACCENT, radius=0.012)
    ax.text(0.50, 1 - header_h / 2 - 0.005, "VALUE BETS OVERVIEW", ha="center", va="center",
            fontsize=18, color="white", fontweight="bold",
            transform=ax.transAxes, zorder=5)
    ax.text(0.50, 1 - header_h + 0.02,
            f"{datetime.now().strftime('%A %d %B %Y')}  |  {n_rows} bettable matches",
            ha="center", va="center", fontsize=10, color=WHITE, alpha=0.8,
            transform=ax.transAxes, zorder=5)

    # Column headers
    y_hdr = 1 - header_h - 0.035
    cols = [
        (0.04, "Match", "left"),
        (0.35, "Referee", "left"),
        (0.52, "Bet", "left"),
        (0.67, "Odds", "center"),
        (0.74, "Bookmaker", "left"),
        (0.87, "Edge", "center"),
        (0.94, "EV%", "center"),
    ]
    for cx, label, ha in cols:
        ax.text(cx, y_hdr, label, ha=ha, va="center",
                fontsize=8, color=GOLD, fontweight="bold",
                transform=ax.transAxes, zorder=5)

    # Draw separator line
    ax.plot([0.03, 0.97], [y_hdr - 0.015, y_hdr - 0.015],
            color=GREY, linewidth=0.5, alpha=0.4, transform=ax.transAxes, zorder=5)

    # Rows
    y_start = y_hdr - 0.04
    for i, (_, bet) in enumerate(best_per_match.iterrows()):
        y = y_start - i * row_h

        if y < footer_h + 0.02:
            break

        # Alternate row background
        if i % 2 == 0:
            _draw_rounded_rect(ax, 0.02, y - 0.01, 0.96, row_h - 0.005,
                               BG_SECTION, radius=0.005, alpha=0.4)

        match_str = f"{bet['Home Team']} vs {bet['Away Team']}"
        if len(match_str) > 32:
            match_str = match_str[:30] + ".."

        ev = bet["EV%"]
        edge = bet["Edge"]
        ev_color = GREEN if ev >= 20 else GOLD if ev >= 10 else WHITE

        ax.text(0.04, y + 0.015, match_str, ha="left", va="center",
                fontsize=8, color=WHITE, fontweight="bold",
                transform=ax.transAxes, zorder=5)
        ax.text(0.35, y + 0.015, str(bet.get("Referee", "")), ha="left", va="center",
                fontsize=7, color=GREY, transform=ax.transAxes, zorder=5)
        ax.text(0.52, y + 0.015, str(bet["Bet"]), ha="left", va="center",
                fontsize=8, color=ACCENT2, fontweight="bold",
                transform=ax.transAxes, zorder=5)
        ax.text(0.67, y + 0.015, f"{bet['Odds']:.2f}", ha="center", va="center",
                fontsize=9, color=GOLD, fontweight="bold",
                transform=ax.transAxes, zorder=5)
        ax.text(0.74, y + 0.015, str(bet["Bookmaker"]), ha="left", va="center",
                fontsize=7, color=GREY, transform=ax.transAxes, zorder=5)
        ax.text(0.87, y + 0.015, f"+{edge:.1f}pp", ha="center", va="center",
                fontsize=8, color=ACCENT, fontweight="bold",
                transform=ax.transAxes, zorder=5)
        ax.text(0.94, y + 0.015, f"+{ev:.1f}%", ha="center", va="center",
                fontsize=9, color=ev_color, fontweight="bold",
                transform=ax.transAxes, zorder=5)

    # Footer
    _draw_rounded_rect(ax, 0.02, 0.015, 0.96, 0.035, BG_SECTION, radius=0.008, alpha=0.5)
    avg_ev = best_per_match["EV%"].mean()
    avg_edge = best_per_match["Edge"].mean()
    ax.text(0.50, 0.032,
            f"Avg EV: +{avg_ev:.1f}%  |  Avg Edge: +{avg_edge:.1f}pp  |  "
            f"Min odds: {MIN_ODDS}  |  Generated {datetime.now().strftime('%H:%M')}",
            ha="center", va="center", fontsize=7, color=GREY,
            transform=ax.transAxes, zorder=5)

    path = os.path.join(OUTPUT_DIR, "value_bets_overview.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, bbox_inches="tight", facecolor=BG_DARK, pad_inches=0.1)
    plt.close(fig)

    print(f"  Overview saved to {path}")
    return path


MIN_ODDS = 1.75


if __name__ == "__main__":
    print("=== Match Card Generator ===\n")
    generate_all_match_cards()
    print()
    generate_overview_image()
