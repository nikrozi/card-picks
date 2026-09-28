#!/usr/bin/env python3
"""
Automated Referee Scraper (updated for oddalerts.com redesign, April 2026)

New site structure:
  - button.refs-toggle[aria-label="Toggle card markets filter"]
  - .refs-toggle.is-active  -> filter is ON
  - .refs-settings-btn      -> open Customise stats panel
  - label.refs-settings__option > input[value="..."]  -> stat checkboxes
  - .refs-card              -> one entry per referee
  - .refs-card__ko          -> kickoff prefix: "" (today), "Tomorrow HH:MM", "Sat HH:MM" etc.
  - .refs-pagination button[data-page="N"]  -> page navigation

Stats configured to: YC/G, Apps, O3.5%, O4.5%
  yellow_cards_avg  -> Yellow PG column
  recorded          -> Apps column
  o35_yellow_cards_per -> +3.5% column
  o45_yellow_cards_per -> +4.5% column
"""

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import csv
from datetime import datetime, timedelta

from src.utils.name_normalizer import normalize
from src.paths import REF_STATS_CSV, PROJECT_ROOT

# Stats we want (input values on the site)
WANTED_STATS = {
    "yellow_cards_avg",      # YC/G
    "recorded",              # Apps
    "o35_yellow_cards_per",  # O3.5%
    "o45_yellow_cards_per",  # O4.5%
}

DAYS_AHEAD = 3  # scrape today + tomorrow + day after


def setup_driver():
    options = uc.ChromeOptions()
    profile_dir = os.path.join(PROJECT_ROOT, ".chrome_profile")
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # CI sets CHROME_VERSION_MAIN to the runner's installed Chrome major version
    version_main = int(os.environ.get("CHROME_VERSION_MAIN", "153"))
    return uc.Chrome(options=options, version_main=version_main)


# ── JS helpers ──────────────────────────────────────────────────────────────

_JS_CLICK_STAT = """
var labels = document.querySelectorAll('label.refs-settings__option');
for (var i = 0; i < labels.length; i++) {
    var inp = labels[i].querySelector('input');
    if (inp && inp.value === arguments[0]) {
        labels[i].click();
        return inp.checked;
    }
}
return null;
"""

_JS_IS_CHECKED = """
var labels = document.querySelectorAll('label.refs-settings__option');
for (var i = 0; i < labels.length; i++) {
    var inp = labels[i].querySelector('input');
    if (inp && inp.value === arguments[0]) return inp.checked;
}
return null;
"""


# ── Setup steps ─────────────────────────────────────────────────────────────

def ensure_card_markets_on(driver):
    """Activate the Has Card Markets filter if not already on."""
    wait = WebDriverWait(driver, 15)
    try:
        toggle = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "button.refs-toggle")
        ))
        if "is-active" not in (toggle.get_attribute("class") or ""):
            driver.execute_script("arguments[0].click();", toggle)
            time.sleep(1.5)
            print("  Card Markets filter toggled ON")
        else:
            print("  Card Markets filter already ON")
    except Exception as e:
        print(f"  Warning: card markets toggle not found ({e})")


def configure_stats(driver):
    """
    Ensure exactly these 4 stats are selected: YC/G, Apps, O3.5%, O4.5%.
    Uses individual JS clicks with fresh DOM queries to work with Vue reactivity.
    Order: uncheck unwanted first (to free up slots), then check wanted.
    """
    try:
        btn = driver.find_element(By.CSS_SELECTOR, ".refs-settings-btn")
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(0.8)

        # Uncheck anything not wanted (one at a time, re-query each time)
        all_vals = driver.execute_script(
            "return [...document.querySelectorAll('label.refs-settings__option input')]"
            ".map(i => i.value);"
        )
        for val in all_vals:
            if val not in WANTED_STATS:
                is_checked = driver.execute_script(_JS_IS_CHECKED, val)
                if is_checked:
                    driver.execute_script(_JS_CLICK_STAT, val)
                    time.sleep(0.25)

        # Check wanted ones that aren't already on
        for val in WANTED_STATS:
            is_checked = driver.execute_script(_JS_IS_CHECKED, val)
            if not is_checked:
                driver.execute_script(_JS_CLICK_STAT, val)
                time.sleep(0.25)

        # Verify
        now_checked = driver.execute_script(
            "return [...document.querySelectorAll('label.refs-settings__option input')]"
            ".filter(i => i.checked).map(i => i.value);"
        )
        print(f"  Stats active: {now_checked}")

        # Close
        try:
            driver.find_element(By.CSS_SELECTOR, "[aria-label='Close settings']").click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)
        time.sleep(0.5)

    except Exception as e:
        print(f"  Warning: could not configure stats ({e})")


# ── Day filter ───────────────────────────────────────────────────────────────

def _ko_date(ko_text):
    """
    Derive the actual date from a kickoff string.
    "" / "18:30"          → today
    "Tomorrow 18:30"      → tomorrow
    "Mon 18:30" etc.      → next occurrence of that weekday
    Returns a date object.
    """
    today = datetime.now().date()
    parts = ko_text.strip().split()

    if len(parts) == 1:
        return today  # just a time = today

    prefix = parts[0]

    if prefix.lower() == "tomorrow":
        return today + timedelta(days=1)

    # Abbreviated weekday name e.g. "Mon", "Tue", "Sat"
    weekdays = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    if prefix in weekdays:
        target_weekday = weekdays[prefix]
        days_ahead = (target_weekday - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7  # same weekday name = next week, not today
        return today + timedelta(days=days_ahead)
    return today  # fallback


def _ko_prefix(ko_text):
    """Extract the day prefix from a kickoff string like 'Tomorrow 18:30' or '18:30'."""
    parts = ko_text.strip().split()
    return "" if len(parts) == 1 else parts[0]


def _within_days(ko_text, days_ahead):
    """Return True if the match falls within the next `days_ahead` days."""
    today = datetime.now().date()
    match_date = _ko_date(ko_text)
    delta = (match_date - today).days
    return 0 <= delta < days_ahead


# ── Scraping ─────────────────────────────────────────────────────────────────

def get_page_count(driver):
    """Return the number of pagination pages."""
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, ".refs-pagination button[data-page]")
        pages = set()
        for b in buttons:
            try:
                pages.add(int(b.get_attribute("data-page")))
            except Exception:
                pass
        return max(pages) if pages else 1
    except Exception:
        return 1


def go_to_page(driver, page_num):
    """Click a pagination button for the given page number."""
    try:
        btn = driver.find_element(
            By.CSS_SELECTOR, f".refs-pagination button[data-page='{page_num}']"
        )
        # Only click if not already active
        if "is-active" not in (btn.get_attribute("class") or ""):
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1.2)
    except Exception as e:
        print(f"  Warning: could not navigate to page {page_num} ({e})")


def parse_current_page(driver, days_ahead):
    """Parse referee cards on the current page, filtered to the next `days_ahead` days."""
    soup = BeautifulSoup(driver.page_source, "html.parser")
    rows = []

    for card in soup.select(".refs-card"):
        name_el  = card.select_one(".refs-card__name a")
        fix_el   = card.select_one(".refs-card__fixture a")
        ko_el    = card.select_one(".refs-card__ko")
        comp_el  = card.select_one(".refs-card__comp")

        if not name_el or not fix_el:
            continue

        ko_text = ko_el.get_text(strip=True) if ko_el else ""
        if not _within_days(ko_text, days_ahead):
            continue  # outside window

        fixture = fix_el.get_text(strip=True)
        if " vs " not in fixture:
            continue
        home_raw, away_raw = fixture.split(" vs ", 1)

        # Dynamic stats — read whatever labels are shown
        stats = {}
        for stat_el in card.select(".refs-card__stat"):
            val_el   = stat_el.select_one(".refs-card__stat-val")
            label_el = stat_el.select_one(".refs-card__stat-label")
            if val_el and label_el:
                label = label_el.get_text(strip=True)
                raw   = val_el.get_text(strip=True).rstrip("%")
                try:
                    stats[label] = float(raw)
                except ValueError:
                    stats[label] = raw

        rows.append({
            "Name":        name_el.get_text(strip=True),
            "Home Team":   normalize(home_raw.strip()),
            "Away Team":   normalize(away_raw.strip()),
            "Competition": comp_el.get_text(strip=True) if comp_el else "",
            "Kickoff":     ko_text,
            "Yellow PG":   stats.get("YC/G", ""),
            "Apps":        stats.get("Apps", ""),
            "+3.5%":       stats.get("O3.5%", ""),
            "+4.5%":       stats.get("O4.5%", ""),
        })

    return rows


# ── Main ─────────────────────────────────────────────────────────────────────

def save_csv(rows, filename=None):
    if filename is None:
        filename = REF_STATS_CSV
    if not rows:
        print("  No rows to save.")
        return
    fieldnames = ["Name", "Home Team", "Away Team", "Competition", "Kickoff",
                  "Yellow PG", "Apps", "+3.5%", "+4.5%"]
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved {len(rows)} referees to {filename}")


def main():
    print("=== Automated Referee Scraper ===")
    driver = None
    failed = False
    try:
        print("Starting browser...")
        driver = setup_driver()

        print("Navigating to oddalerts.com/referees ...")
        driver.get("https://www.oddalerts.com/referees")
        time.sleep(3)

        ensure_card_markets_on(driver)
        configure_stats(driver)

        # Wait for cards to appear
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".refs-card"))
        )
        time.sleep(1)

        page_count = get_page_count(driver)
        end_date = (datetime.now() + timedelta(days=DAYS_AHEAD - 1)).strftime("%a %d %b")
        print(f"  Pages found: {page_count} | Window: today -> {end_date}")

        all_rows = []
        for page in range(1, page_count + 1):
            if page > 1:
                go_to_page(driver, page)
            rows = parse_current_page(driver, DAYS_AHEAD)
            print(f"  Page {page}: {len(rows)} matches in window")
            all_rows.extend(rows)

        print(f"  Total: {len(all_rows)} referee rows")

        if all_rows:
            save_csv(all_rows)
            for r in all_rows[:8]:
                print(f"    {r['Name']}: {r['Home Team']} vs {r['Away Team']} "
                      f"({r['Kickoff']}) | Apps={r['Apps']} O3.5%={r['+3.5%']} O4.5%={r['+4.5%']}")
            if len(all_rows) > 8:
                print(f"    ... and {len(all_rows)-8} more")
        else:
            print("  No referee data extracted.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        failed = True
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
