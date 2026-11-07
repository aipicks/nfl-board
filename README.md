# NFL board (local only)

Weekly NFL betting board built on SportsGameOdds (five books), nflverse, ESPN injuries, nflweather/Open-Meteo and SportsBettingDime splits.
Tabs: **Game Bets** (spreads and totals), **Deep Dive** (every game), **Public Betting**, **Weather**, **Injuries**, **+EV TD Scorers**, **Player Props**, **Results**, **How it works**.
Nothing is published; `docs/index.html` is written for a future GitHub Pages launch only.

## Weekly commands
| When | Double-click | Command |
|---|---|---|
| Thursday | `Update Thursday.bat` | `python update.py` |
| Saturday | `Update Saturday.bat` | `python update.py` |
| Sunday morning (optional) | `Update Sunday Quick.bat` | `python update.py --quick` |
| Monday/Tuesday (settle results) | any update above | `python update.py --quick` |
| View | `Open Board.bat` | open `board.html` |

`update.py` backs up the database, refreshes nflverse data, validates it (aborts on failure), **settles finished games**, refreshes
injuries / weather / splits / odds (one SportsGameOdds request, about 13 of your 2,500 monthly entities), validates, and rebuilds the board
(TD model, props, a deep dive for every game), **logs every prediction before kickoff**, and rebuilds Results. About 2-3 minutes.
Back up `data/nfl.db` outside this folder now and then: it holds all logged predictions.

## The formulas and where they live (all weights are priors in `config.py`, not fitted edges)
1. **De-vig and EV** (`model/devig.py`): fair p from a two-way pair = (1/dec_a) / (1/dec_a + 1/dec_b); EV = p * payout - (1 - p), a push refunds the stake;
   BET >= +3%, LEAN +1% to +3%, PASS below. Anytime-TD prices have no "No" side: implied p / (1 + `TD_ASSUMED_HOLD`).
2. **Probability blend** (`model/devig.py: blend`): logit(final) = w * logit(model) + (1 - w) * logit(market), w = **0.70** per market (`MODEL_WEIGHT`).
3. **Game ratings** (`model/ratings.py`): time-weighted ridge regression of per-play EPA (pass, rush), success rate and pace on offence and opponent-defence effects,
   with the quarterback's pre-game EPA/dropback as a covariate. Points = league average + (plays x EPA/play above league average) (`model/game.py`), plus home field,
   expected starter, skill injuries, rest, travel, weather on totals, and a capped public-money/line-move nudge (+/-0.75 spread, +/-0.5 total).
4. **Probabilities from real margins** (`model/dist.py`): every NFL game since 2006 whose closing line was near the projection supplies the actual margin or total
   (so 3 and 7 keep their weight); the projection is first shrunk toward the market line (`MODEL_TRUST`) because the backtest found no proven edge.
5. **Anytime TD** (`model/td.py`, `td_board.py`): lambda = sum over six usage zones (targets and carries outside the 20, red zone, goal line) of expected touches x league TD rate,
   x (team implied points / 22.5)^0.8 x opponent-TDs-allowed factor x P(plays), + 0.03; P(TD) = 1 - e^-lambda with a calibration squeeze above 35%.
   Missing teammates' usage is redistributed. Backtest (`td_backtest.py`): log-loss 0.487 vs 0.527 for a flat rate.
6. **Props** (`model/props.py`, `props_board.py`): mean = team volume (game script) x player share x efficiency (shrunk) x opponent factor x wind; yards ~ gamma, counts ~ negative
   binomial, variance = a x mean with `a` fitted in `props_backtest.py`; only `PROP_TRUST` of the model-vs-market gap is believed.
7. **Tracking** (`tracking.py`): `pred_log` saves each pick before kickoff (last pre-kickoff snapshot is graded); settlement from final scores and box scores; Brier, calibration, flat-$1 profit.

## Injuries and learning
- Injury model (`model/game.py`, `model/injuries.py`): QB (expected starter as a ratings covariate), skill players (usage lost x P(misses)), and offensive line, defensive line, linebackers,
  cornerbacks, safeties and kickers (snap share x P(misses) x points per starter from `inj_backtest.py`: OL 0.45, DL 0.56, LB 0.45, CB 0.80, S 0.41). Only active-roster players share usage;
  running-back carries are consolidated among the backs who can play (`model/td.py: redistribute`).
- Learning loop (`learning.py`, run by `update.py` after games settle): reviews settled picks (`reviews/week_N.md`), nudges `MODEL_TRUST`, `TD_LAMBDA_SCALE` and `PROP_TRUST` only with enough graded
  picks, damped and inside hard bounds (`learned.json`, loaded by `config.py`, logged in `lessons_auto.md`). `lessons.md` records every correction from the user with its root cause; each has a
  regression test in `tests/test_lessons.py`. Read `lessons.md` first in every session.

## Where else things live
`adapters/` one file per source; `deep_dive.py`, `deep_extra.py`, `deep_more.py`, `deep_tab.js`, `tabs_new.js`, `weather_tab.js`, `injuries_tab.js` the pages; `game_flags.csv` your per-game down-weights;
`tests/` (`python -m pytest -q`, 53 tests incl. a guard that runs every offline step the weekly update calls); backtests: `backtest.py`, `qb_backtest.py`, `td_backtest.py`, `props_backtest.py`.

## Honest status
Backtest (273 games): the base game model has no proven edge over closing lines, so projections lean on the market. The TD and props models beat naive baselines on
last season but have never been tested against market prices; the Results tab exists to judge them after hundreds of picks. Not modelled: longest pass / rush / reception props,
defensive and offensive-line injuries, alternate lines (not in the odds feed).
