#!/usr/bin/env python3
"""
Betaminic Ultra-Fast Scraper
Maximum speed optimization - let's see how fast we can go!
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import glob
import threading
import csv
from datetime import datetime
from src.utils.name_normalizer import normalize
from src.paths import TEAM_STATS_DIR

def setup_ultra_fast_driver():
    """Setup Chrome driver with maximum speed optimizations"""
    chrome_options = Options()
    
    # Maximum speed optimizations
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-client-side-phishing-detection")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--disable-ipc-flooding-protection")
    chrome_options.add_argument("--disable-hang-monitor")
    chrome_options.add_argument("--disable-prompt-on-repost")
    chrome_options.add_argument("--disable-domain-reliability")
    chrome_options.add_argument("--disable-features=TranslateUI")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    # chrome_options.add_argument("--disable-javascript")  # This breaks CSV downloads
    chrome_options.add_argument("--disable-css")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Create download directory
    download_dir = TEAM_STATS_DIR
    os.makedirs(download_dir, exist_ok=True)
    
    # Download preferences
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False,
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "profile.content_settings.exceptions.automatic_downloads.*.setting": 1,
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.media_stream": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_current_csv_files():
    """Get list of current CSV files"""
    return set(glob.glob(os.path.join(TEAM_STATS_DIR, "*.csv")))

def wait_for_new_csv_files(initial_files, timeout=5):
    """Wait for new CSV files to appear - ultra fast timeout"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        current_files = get_current_csv_files()
        new_files = current_files - initial_files
        if new_files:
            return list(new_files)
        time.sleep(0.1)  # Check every 100ms
    return []

def clean_and_rename_files(league_name):
    """Clean old files and rename to consistent names - ultra fast"""
    download_dir = TEAM_STATS_DIR
    
    # Define file patterns and target names
    patterns = {
        "All Games": (f"*{league_name}*Average Yellow Cards All Games*.csv", f"{league_name} - All Games.csv"),
        "Home": (f"*{league_name}*Average Yellow Card Games played at home*.csv", f"{league_name} - Home Games.csv"),
        "Away": (f"*{league_name}*Average Yellow Cards Games played away*.csv", f"{league_name} - Away Games.csv")
    }
    
    for table_type, (pattern, target_name) in patterns.items():
        matching_files = glob.glob(os.path.join(download_dir, pattern))
        if matching_files:
            # Sort by modification time (newest first)
            matching_files.sort(key=os.path.getmtime, reverse=True)
            
            # Delete old files
            for file in matching_files[1:]:
                try:
                    os.remove(file)
                    print(f"  🗑️ Deleted old {table_type} file")
                except:
                    pass
            
            # Rename newest file
            newest_file = matching_files[0]
            target_path = os.path.join(download_dir, target_name)
            if newest_file != target_path:
                try:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    os.rename(newest_file, target_path)
                    print(f"  📝 Renamed to: {target_name}")
                except:
                    pass

def create_combined_csv_files():
    """Create combined CSV files for All Games, Home, and Away with all leagues"""
    print("\n🔄 Creating combined CSV files...")
    
    download_dir = TEAM_STATS_DIR
    
    # Define the three categories and their file patterns
    categories = {
        "All Games": {
            "pattern": "* - All Games.csv",
            "output_file": "Combined_All_Games.csv",
            "columns": ["Team", "TG", "YF", "YA", "O3.5", "U3.5", "O4.5", "U4.5", "O5.5", "U5.5", "League"]
        },
        "Home Games": {
            "pattern": "* - Home Games.csv",
            "output_file": "Combined_Home_Games.csv",
            "columns": ["Team", "GH", "YFH", "YAH", "O3.5H", "U3.5H", "O4.5H", "U4.5H", "O5.5H", "U5.5H", "League"]
        },
        "Away Games": {
            "pattern": "* - Away Games.csv",
            "output_file": "Combined_Away_Games.csv",
            "columns": ["Team", "GA", "YFA", "YAA", "O3.5A", "U3.5A", "O4.5A", "U4.5A", "O5.5A", "U5.5A", "League"]
        }
    }
    
    for category, config in categories.items():
        print(f"\n📊 Processing {category}...")
        
        # Find all files matching the pattern
        pattern_path = os.path.join(download_dir, config["pattern"])
        matching_files = glob.glob(pattern_path)
        
        if not matching_files:
            print(f"  ⚠️ No {category} files found")
            continue
        
        combined_data = []
        
        # Process each league file
        for file_path in matching_files:
            league_name = os.path.basename(file_path).replace(f" - {category}.csv", "")
            print(f"  📁 Processing {league_name}...")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        row['League'] = league_name
                        if 'Team' in row:
                            row['Team'] = normalize(row['Team'])
                        combined_data.append(row)
                        
                print(f"    ✅ Added {len(list(csv.DictReader(open(file_path, 'r', encoding='utf-8'))))} teams from {league_name}")
                
            except Exception as e:
                print(f"    ❌ Error processing {league_name}: {e}")
        
        # Write combined CSV
        if combined_data:
            output_path = os.path.join(download_dir, config["output_file"])
            try:
                with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=config["columns"])
                    writer.writeheader()
                    writer.writerows(combined_data)
                
                print(f"  ✅ Created {config['output_file']} with {len(combined_data)} teams")
                
            except Exception as e:
                print(f"  ❌ Error creating {config['output_file']}: {e}")
        else:
            print(f"  ⚠️ No data to combine for {category}")

def download_league_ultra_fast(driver, league_name, league_url, is_first_league=False):
    """Ultra-fast league download with minimal waits"""
    print(f"\n🚀 {league_name} - ULTRA FAST MODE")
    
    try:
        # Navigate
        driver.get(league_url)
        
        # Add extra wait for first league to ensure proper file detection
        if is_first_league:
            time.sleep(1.5)  # Extra wait for first league
        else:
            time.sleep(0.5)  # Minimal wait for others
        
        # Hide cookie banner instantly
        try:
            driver.execute_script("document.getElementById('cookie-law-info-bar').style.display = 'none';")
        except:
            pass
        
        initial_files = get_current_csv_files()
        
        # Download all 3 CSVs as fast as possible
        for table_id, table_type in [("table_2", "All Games"), ("table_4", "Home"), ("table_6", "Away")]:
            try:
                # Find and click immediately
                table = driver.find_element(By.CSS_SELECTOR, f"table#{table_id}")
                driver.execute_script("arguments[0].scrollIntoView();", table)
                
                csv_button = driver.find_element(By.CSS_SELECTOR, f"button[aria-controls='{table_id}'].buttons-csv")
                driver.execute_script("arguments[0].click();", csv_button)
                
                print(f"  ⚡ {table_type} clicked")
                time.sleep(0.2)  # Minimal wait between clicks
                
            except Exception as e:
                print(f"  ❌ {table_type} failed: {e}")
        
        # Wait for downloads - longer wait for first league
        if is_first_league:
            time.sleep(2)  # Extra wait for first league
        else:
            time.sleep(1)  # Normal wait for others
            
        new_files = wait_for_new_csv_files(initial_files, timeout=5 if is_first_league else 3)
        
        if new_files:
            print(f"  ✅ Downloaded {len(new_files)} files")
            # Clean up old files and rename to consistent names
            clean_and_rename_files(league_name)
        else:
            print(f"  ⚠️ No new files detected")
        
        return True
        
    except Exception as e:
        print(f"  ❌ {league_name} failed: {e}")
        return False

def ultra_fast_scraper():
    """Ultra-fast scraper - let's break some speed records!"""
    driver = None
    try:
        print("🏎️ ULTRA-FAST BETAMINIC SCRAPER 🏎️")
        print("Testing maximum speed limits...")
        print()
        
        leagues = {
            "Premier League": "https://www.betaminic.com/statistics/yellow-card-stats-premier-league/",
            "La Liga": "https://www.betaminic.com/statistics/yellow-card-stats-la-liga/",
            "Bundesliga": "https://www.betaminic.com/statistics/yellow-card-stats-bundesliga/",
            "Serie A": "https://www.betaminic.com/statistics/yellow-card-stats-serie-a/",
            "Ligue 1": "https://www.betaminic.com/statistics/yellow-card-stats-ligue-1/",
        }
        
        print("Starting ultra-fast browser...")
        start_time = time.time()
        driver = setup_ultra_fast_driver()
        
        successful = 0
        failed = 0
        
        for i, (league_name, league_url) in enumerate(leagues.items()):
            league_start = time.time()
            
            # Add extra wait for the first league to ensure proper file detection
            if i == 0:
                print("  ⏳ First league - adding extra wait for file detection...")
                time.sleep(1)
            
            success = download_league_ultra_fast(driver, league_name, league_url, is_first_league=(i == 0))
            league_time = time.time() - league_start
            
            if success:
                successful += 1
                print(f"  ✅ {league_name} completed in {league_time:.2f}s")
            else:
                failed += 1
                print(f"  ❌ {league_name} failed in {league_time:.2f}s")
            
            # No wait between leagues - maximum speed!
        
        total_time = time.time() - start_time
        
        print(f"\n🏁 RACE COMPLETE!")
        print(f"⏱️ Total time: {total_time:.2f} seconds")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"🏎️ Average per league: {total_time/len(leagues):.2f}s")
        
        # Check results
        final_files = get_current_csv_files()
        print(f"\n📁 Total files in team_card_stats: {len(final_files)}")
        
        # Show files by league
        print("\nFiles by league:")
        for league_name in leagues.keys():
            league_files = [f for f in final_files if league_name in f]
            if league_files:
                print(f"  {league_name}: {len(league_files)} files")
                for file in sorted(league_files):
                    print(f"    - {os.path.basename(file)}")
            else:
                print(f"  {league_name}: No files")
        
        # Create combined CSV files
        create_combined_csv_files()
        
        # Show final file count including combined files
        final_files_after_combined = get_current_csv_files()
        print(f"\n📁 Total files after combining: {len(final_files_after_combined)}")
        
        print("\nBrowser closing in 2 seconds...")
        time.sleep(2)
        
    except Exception as e:
        print(f"💥 CRASH: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    ultra_fast_scraper()
