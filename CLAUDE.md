# NFL board

Read `README.md` and `lessons.md` first.

## Combined Daily Boards page (2026-11-25)
After every board build and artifact publish, also update the combined NBA/NFL/NHL page: `python ../hub/build_hub.py nfl`, then publish `../hub/index.html` with the Artifact tool to https://claude.ai/artifact/8c461o8odxGJEV9othmued with files {"nfl.html": "C:\Users\edenc\OneDrive\Desktop\DAILY BOARDS\hub\nfl.html" (absolute source path)} (only the NFL file).

## Prop model v2 (2026-11-25)
Best Picks props use `model/prop_calib.py` (market-anchored calibration, refit each build). The Results tab shows `regrade_card.py`'s re-graded Best Picks record. See `lessons.md`.
