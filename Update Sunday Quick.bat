@echo off
cd /d "%~dp0"
echo NFL board: quick Sunday-morning re-run (skips the nflverse rebuild)
python update.py --quick
pause
