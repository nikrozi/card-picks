"""
Windows toast notification helper.

Fires a clickable Windows 10/11 toast after each pipeline run so you
can see at a glance whether value bets were found — without opening
the log file. Clicking the toast opens the overview image.

Falls back silently if winotify is missing or the platform is not
Windows, so the pipeline never breaks because of notifications.
"""

import os
import sys

from src.paths import OUTPUT_DIR, REF_STATS_CSV

OVERVIEW_PNG = os.path.join(OUTPUT_DIR, "value_bets_overview.png")
RECOMMENDATIONS_CSV = os.path.join(OUTPUT_DIR, "recommendations.csv")


def _load_ref_lookup():
    """
    Build {referee_name: {apps, ypg, o35, o45}} from Ref_stats.csv.
    Returns an empty dict if the file is missing — callers degrade
    gracefully rather than failing the toast.
    """
    if not os.path.exists(REF_STATS_CSV):
        return {}
    try:
        import pandas as pd
        df = pd.read_csv(REF_STATS_CSV)
        lookup = {}
        for _, r in df.iterrows():
            name = str(r.get("Name", "")).strip()
            if not name:
                continue
            lookup[name] = {
                "apps": r.get("Apps"),
                "ypg":  r.get("Yellow PG"),
                "o35":  r.get("+3.5%"),
                "o45":  r.get("+4.5%"),
            }
        return lookup
    except Exception:
        return {}


def _format_ref_stats(ref_name, ref_lookup):
    """Format a one-line ref stats summary, e.g. '180g | 2.98 PG | O3.5 35% / O4.5 16%'."""
    if not ref_name or ref_name not in ref_lookup:
        return None
    s = ref_lookup[ref_name]
    parts = []
    apps = s.get("apps")
    if apps is not None:
        try:
            parts.append(f"{int(apps)}g")
        except (ValueError, TypeError):
            pass
    ypg = s.get("ypg")
    if ypg is not None:
        try:
            parts.append(f"{float(ypg):.2f} PG")
        except (ValueError, TypeError):
            pass
    o35 = s.get("o35")
    o45 = s.get("o45")
    pct_bits = []
    if o35 is not None:
        try:
            pct_bits.append(f"O3.5 {float(o35):.0f}%")
        except (ValueError, TypeError):
            pass
    if o45 is not None:
        try:
            pct_bits.append(f"O4.5 {float(o45):.0f}%")
        except (ValueError, TypeError):
            pass
    if pct_bits:
        parts.append(" / ".join(pct_bits))
    return " | ".join(parts) if parts else None


def _format_bet_lines(recs_table, value_bets, max_lines=3):
    """
    Build up to `max_lines` blocks of bet info. Each block is two lines:
    the bet itself and a referee-stats line below.
    """
    src = recs_table if (recs_table is not None and not recs_table.empty) else value_bets
    if src is None or src.empty:
        return []

    ref_lookup = _load_ref_lookup()

    lines = []
    for _, row in src.head(max_lines).iterrows():
        match = row.get("Match")
        if not match:
            match = f"{row.get('Home Team', '?')} vs {row.get('Away Team', '?')}"
        bet = row.get("Bet", "?")
        odds = row.get("Best Odds") or row.get("Odds", "?")
        bk = row.get("Best Bookmaker") or row.get("Bookmaker", "")
        bk_str = f" ({bk})" if bk else ""
        lines.append(f"- {match} | {bet} @ {odds}{bk_str}")

        ref_name = row.get("Referee")
        ref_str = _format_ref_stats(ref_name, ref_lookup) if ref_name else None
        if ref_str:
            lines.append(f"   Ref {ref_name}: {ref_str}")
    return lines


def send_run_notification(value_bets, recs_table, target_count=0):
    """
    Fire a Windows toast summarizing this pipeline run.

    Always called at the end of daily_analysis.main(), regardless of
    whether bets were found, so the user gets feedback every time.
    """
    if sys.platform != "win32":
        return

    try:
        from winotify import Notification, audio
    except ImportError:
        print("  (Toast skipped: winotify not installed -- run `pip install winotify`)")
        return

    n_bets = 0 if value_bets is None or value_bets.empty else len(value_bets)

    if n_bets == 0:
        title = "Card Betting: 0 value bets"
        if target_count:
            msg = (
                f"{target_count} target match{'es' if target_count != 1 else ''} scanned, "
                "no edge found."
            )
        else:
            msg = "No referees passed today's betting criteria."
        sound = audio.Default
        launch_target = None
    else:
        try:
            avg_ev = float(value_bets["EV%"].mean())
            ev_str = f"  |  Avg EV: +{avg_ev:.1f}%"
        except (KeyError, ValueError, TypeError):
            ev_str = ""

        title = f"Card Betting: {n_bets} value bet{'s' if n_bets != 1 else ''} found!"
        lines = _format_bet_lines(recs_table, value_bets, max_lines=3)
        if n_bets > 3:
            lines.append(f"+{n_bets - 3} more...")
        msg = "\n".join(lines) + ev_str if lines else f"{n_bets} bets ready{ev_str}"
        sound = audio.Reminder

        # Prefer overview image; fall back to recommendations CSV
        if os.path.exists(OVERVIEW_PNG):
            launch_target = OVERVIEW_PNG
        elif os.path.exists(RECOMMENDATIONS_CSV):
            launch_target = RECOMMENDATIONS_CSV
        else:
            launch_target = None

    try:
        toast = Notification(
            app_id="Card Betting",
            title=title,
            msg=msg,
            duration="long",  # ~25 seconds before disappearing
            launch=launch_target,
        )
        toast.set_audio(sound, loop=False)
        if launch_target:
            label = "Open overview" if launch_target.endswith(".png") else "Open CSV"
            toast.add_actions(label=label, launch=launch_target)
        toast.show()
    except Exception as e:
        # Never let notification failures break the pipeline
        print(f"  (Toast failed: {e})")


if __name__ == "__main__":
    # Smoke test: load latest CSVs from output dir and fire a real toast
    import pandas as pd
    from src.paths import VALUE_BETS_CSV

    vb = pd.read_csv(VALUE_BETS_CSV) if os.path.exists(VALUE_BETS_CSV) else pd.DataFrame()
    rt = pd.read_csv(RECOMMENDATIONS_CSV) if os.path.exists(RECOMMENDATIONS_CSV) else pd.DataFrame()
    send_run_notification(vb, rt, target_count=5)
    print("Smoke-test toast fired.")
