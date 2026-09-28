@echo off
echo ============================================
echo  Card Betting Daily Analysis
echo ============================================
echo.
echo Running full pipeline (scrape + predict + recommend)...
echo.
.venv\Scripts\python.exe daily_analysis.py %*
echo.
echo ============================================
echo  Done. Check data\output\ for results.
echo ============================================
pause
