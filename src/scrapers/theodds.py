"""
odds-api.io - Card Over/Under Odds Collector

Fetches total cards over/under odds from multiple bookmakers via
odds-api.io (https://odds-api.io).

Uses batched /odds/multi requests (up to 10 events each) to stay within
the 100 requests/hour rate limit.

Card markets extracted:
  - "Number of Cards In Match"  (e.g. over/under 3.5)
  - "Bookings Totals"           (e.g. over/under 4.0)
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from src.utils.name_normalizer import normalize
from src.paths import THEODDS_CSV, PROJECT_ROOT

BASE_URL = "https://api.odds-api.io/v3"

# Bookmakers to query — free plan is locked to max 2: Bet365 and Unibet
BOOKMAKERS = "Bet365,Unibet"

# Bookmakers to show as dedicated columns in the output
TRACKED_BOOKMAKERS = ["Bet365", "Unibet"]

# Bookmaker variants to exclude — odds-api.io returns sharp/professional feeds
# (e.g. "Bet365 (no latency)") in addition to the consumer-facing brand. Their
# odds don't match what users see on the public site, so we filter them out
# entirely to avoid recommending bets that can't actually be placed.
EXCLUDED_BOOKMAKER_SUBSTRINGS = ("no latency", "low latency", "sharp", "exchange")


def _is_excluded_bookmaker(bk_name):
    """True if this bookmaker name is a sharp/professional feed we shouldn't surface."""
    if not bk_name:
        return False
    name_lower = str(bk_name).lower()
    return any(sub in name_lower for sub in EXCLUDED_BOOKMAKER_SUBSTRINGS)

# Card market names in the API response
CARD_MARKET_NAMES = {"Number of Cards In Match", "Bookings Totals"}

DAYS_AHEAD = 21


def _load_api_key():
    key = os.environ.get("ODDSAPI_KEY", "")
    if key:
        return key
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ODDSAPI_KEY="):
                    return line.split("=", 1)[1].strip()
    # Fall back to old key name for backwards compat
    env_key = os.environ.get("THEODDS_API_KEY", "")
    if env_key:
        return env_key
    raise RuntimeError("ODDSAPI_KEY not set (add it to .env or the environment)")


API_KEY = _load_api_key()


def _search_events(team_name):
    """
    Search for upcoming events containing team_name.
    Uses /events/search so we only spend 1 request per team rather than
    scanning every league. Returns a list of football event dicts.
    """
    url = f"{BASE_URL}/events/search"
    params = {
        "query": team_name,
        "apiKey": API_KEY,
    }
    resp = requests.get(url, params=params, timeout=15)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        return []
    events = data if isinstance(data, list) else []
    # Keep only football, upcoming events within DAYS_AHEAD
    cutoff = datetime.now(timezone.utc) + timedelta(days=DAYS_AHEAD)
    now = datetime.now(timezone.utc)
    result = []
    for ev in events:
        sport = ev.get("sport", {})
        if isinstance(sport, dict) and sport.get("slug") != "football":
            continue
        raw_date = ev.get("date", "")
        try:
            ev_time = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            if now <= ev_time <= cutoff:
                result.append(ev)
        except Exception:
            result.append(ev)
    return result


def _get_odds_single(event_id):
    """
    Fetch odds for a single event using /odds.
    Returns a single event odds object (dict) or None.
    """
    # Build URL manually — requests would URL-encode commas in BOOKMAKERS to %2C
    # but odds-api.io requires literal commas as separators.
    url = (
        f"{BASE_URL}/odds"
        f"?eventId={event_id}"
        f"&bookmakers={BOOKMAKERS}"
        f"&apiKey={API_KEY}"
    )
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        return None
    return data


def _extract_card_odds(event_odds_obj):
    """
    Parse card markets from a single event odds response.

    Returns list of dicts:
        {home, away, match_id, commence_time, bookmaker, market, hdp, over, under}
    """
    rows = []
    home = normalize(event_odds_obj.get("home", ""))
    away = normalize(event_odds_obj.get("away", ""))
    match_id = event_odds_obj.get("id", "")
    commence = event_odds_obj.get("date", "")
    bookmakers_data = event_odds_obj.get("bookmakers", {})

    if isinstance(bookmakers_data, dict):
        items = bookmakers_data.items()
    else:
        return rows

    for bk_name, markets in items:
        if not isinstance(markets, list):
            continue
        # Skip sharp/non-consumer feeds whose odds aren't bettable on the public site
        if _is_excluded_bookmaker(bk_name):
            continue
        for market in markets:
            if market.get("name") not in CARD_MARKET_NAMES:
                continue
            for odd in market.get("odds", []):
                hdp = odd.get("hdp")
                over = odd.get("over")
                under = odd.get("under")
                if hdp is None or (over is None and under is None):
                    continue
                rows.append({
                    "home_team": home,
                    "away_team": away,
                    "match_id": match_id,
                    "commence_time": commence,
                    "bookmaker": bk_name,
                    "market": market.get("name"),
                    "line": float(hdp),
                    "over_odds": float(over) if over else None,
                    "under_odds": float(under) if under else None,
                })
    return rows


def fetch_targeted_card_odds(target_matches, force_refresh=False):
    """
    Fetch card odds ONLY for specific matches that passed referee criteria.

    Parameters:
        target_matches: list of dicts with 'home_team' and 'away_team' keys
        force_refresh:  bypass cache

    Returns a wide-format DataFrame (one row per match, columns per odds line).
    """
    if not target_matches:
        print("      No target matches to fetch odds for")
        return pd.DataFrame()

    # Cache check
    if not force_refresh and os.path.exists(THEODDS_CSV):
        try:
            cached_df = pd.read_csv(THEODDS_CSV)
            mod_time = datetime.fromtimestamp(os.path.getmtime(THEODDS_CSV), tz=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - mod_time).total_seconds() / 3600
            if age_hours < 12 and not cached_df.empty:
                print(f"      Using cached data ({len(cached_df)} matches, {age_hours:.1f}h old). "
                      "Use --refresh-odds to force update.")
                return cached_df
        except Exception:
            pass

    target_set = {
        (normalize(m["home_team"]).lower(), normalize(m["away_team"]).lower())
        for m in target_matches
    }
    # Also match reversed (oddalerts home/away sometimes differs from betting API)
    target_set_reversed = {(b, a) for a, b in target_set}

    # Step 1: search for each target match by home team name.
    # One request per match instead of scanning all leagues.
    matched_events = {}  # match_id -> event dict
    requests_used = 0

    for idx, match in enumerate(target_matches):
        home_query = normalize(match["home_team"])
        if idx > 0:
            time.sleep(0.5)  # light pacing between search requests
        try:
            events = _search_events(home_query)
            requests_used += 1
        except Exception as e:
            print(f"        Search '{home_query}': error ({e})")
            continue

        for ev in events:
            api_home = normalize(ev.get("home", "")).lower()
            api_away = normalize(ev.get("away", "")).lower()

            # Try exact match first, then substring match (handles e.g.
            # "Real Sociedad" matching "Real Sociedad San Sebastian")
            def _teams_match(t_home, t_away):
                home_ok = (api_home == t_home or t_home in api_home or api_home in t_home)
                away_ok = (api_away == t_away or t_away in api_away or api_away in t_away)
                return home_ok and away_ok

            matched = any(_teams_match(h, a) for h, a in target_set) or \
                      any(_teams_match(h, a) for h, a in target_set_reversed)

            if matched:
                if ev["id"] not in matched_events:
                    matched_events[ev["id"]] = ev
                    league = ev.get("league", {}).get("name", "?") if isinstance(ev.get("league"), dict) else "?"
                    print(f"        Found: {ev.get('home')} vs {ev.get('away')} ({league})")

    if not matched_events:
        print("      No target matches found in upcoming fixtures")
        return pd.DataFrame()

    print(f"      Matched {len(matched_events)} events, fetching odds ...")

    # Step 2: fetch odds one event at a time
    all_rows = []
    event_ids = list(matched_events.keys())

    for i, event_id in enumerate(event_ids):
        ev = matched_events[event_id]
        label = f"{ev.get('home')} vs {ev.get('away')}"
        if i > 0:
            time.sleep(1.5)  # avoid 429 rate limit
        try:
            odds_obj = _get_odds_single(event_id)
            requests_used += 1
            if odds_obj:
                rows = _extract_card_odds(odds_obj)
                if rows:
                    all_rows.extend(rows)
                    print(f"        {label}: {len(rows)} odds rows")
                else:
                    print(f"        {label}: no card markets available yet")
        except Exception as e:
            print(f"        {label}: error ({e})")

    print(f"      Requests used: {requests_used}")

    if not all_rows:
        print("      No card odds found for target matches")
        return pd.DataFrame()

    raw = pd.DataFrame(all_rows)

    # Step 3: pivot to wide format (one row per match, best odds per line)
    result_rows = []
    for (home, away, match_id, commence), group in raw.groupby(
        ["home_team", "away_team", "match_id", "commence_time"]
    ):
        row = {
            "home_team": home,
            "away_team": away,
            "match_id": match_id,
            "commence_time": commence,
        }

        for line, line_group in group.groupby("line"):
            line_str = str(line).replace(".", "_")

            overs = line_group[line_group["over_odds"].notna()]
            unders = line_group[line_group["under_odds"].notna()]

            if not overs.empty:
                best_over = overs.loc[overs["over_odds"].idxmax()]
                row[f"over_{line_str}_odds"] = best_over["over_odds"]
                row[f"over_{line_str}_bookmaker"] = best_over["bookmaker"]

            if not unders.empty:
                best_under = unders.loc[unders["under_odds"].idxmax()]
                row[f"under_{line_str}_odds"] = best_under["under_odds"]
                row[f"under_{line_str}_bookmaker"] = best_under["bookmaker"]

            # Dedicated columns for tracked bookmakers (e.g. Bet365, Unibet)
            for bk in TRACKED_BOOKMAKERS:
                bk_rows = line_group[line_group["bookmaker"].str.lower() == bk.lower()]
                bk_key = bk.lower().replace(" ", "")
                over_bk = bk_rows[bk_rows["over_odds"].notna()]
                under_bk = bk_rows[bk_rows["under_odds"].notna()]
                if not over_bk.empty:
                    row[f"over_{line_str}_{bk_key}"] = over_bk["over_odds"].iloc[0]
                if not under_bk.empty:
                    row[f"under_{line_str}_{bk_key}"] = under_bk["under_odds"].iloc[0]

        result_rows.append(row)

    result = pd.DataFrame(result_rows)
    print(f"      Total: {len(result)} matches with card odds")
    return result


if __name__ == "__main__":
    print("=== odds-api.io - Targeted Card Odds ===\n")
    from src.analysis.referee_filter import get_target_matches, print_filter_summary
    from src.paths import ensure_dirs
    ensure_dirs()

    targets = get_target_matches()
    print_filter_summary(targets)
    print()
    if targets:
        df = fetch_targeted_card_odds(targets, force_refresh=True)
        if not df.empty:
            df.to_csv(THEODDS_CSV, index=False)
            print(f"\nSaved {len(df)} matches to {THEODDS_CSV}")
            print(df.to_string())
        else:
            print("\nNo matching card odds found.")
    else:
        print("No matches passed referee criteria.")
