@echo off
cd /d "%~dp0"
echo NFL board: Thursday update (refresh lines, injuries, weather, splits; rebuild every game)
python update.py
pause
