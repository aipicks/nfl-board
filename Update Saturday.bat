@echo off
cd /d "%~dp0"
echo NFL board: Saturday update (final refresh before Sunday)
python update.py
pause
