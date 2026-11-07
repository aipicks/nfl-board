@echo off
cd /d "%~dp0"
echo Rebuilding board...
python build_board.py --nolog
if errorlevel 1 (echo Build failed. Nothing published. & pause & exit /b 1)
git add -A
git commit -m "Board update %date% %time%"
git push
echo.
echo Done. Phone link: https://aipicks.github.io/nfl-board/  (reload in about a minute)
pause
