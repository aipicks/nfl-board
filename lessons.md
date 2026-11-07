# Lessons (read this first, every session)

Corrections from the user and what we learned from results. Newest at the bottom. Each entry: what was wrong, why, what changed. The Results tab shows these.
Automatic parameter changes made by `learning.py` are listed separately in `lessons_auto.md`.

## 2026-10-10: a feed can drop a field without warning
SportsGameOdds sent a player entry with no `name` and the odds refresh crashed, so the board stopped updating. Adapters must tolerate missing or renamed fields, fall back to cache, and never let one bad row stop the run. Changed: name fallback in `adapters/sgo.py`, regression test added.

## 2026-10-14: a bad game is not a bad team
The user pointed out that PIT's 3-point game came in heavy rain with a key receiver out, ATL and WAS scored 13 with backup quarterbacks, the IND at WAS game was in London with the starters out, and HOU lacked Nico Collins. Ratings treated all of these as normal games. Changed: quarterback quality is a covariate in the ratings, backup QBs start from replacement level, neutral-site games get no home-field edge, and `game_flags.csv` down-weights outlier games.

## 2026-10-14: show 2026 team stats, not last year's
Team tables mixed 2025 into rankings and edges. Changed: every team statistic and rank is 2026; 2025 sits behind a toggle. Last season is only a light prior for individual players.

## 2026-10-15: show every injury update, with who steps in
The first injury table hid the newest reports and the next man up. Changed: full ESPN and official report with timestamps, practice status, usage and depth-chart replacements.

## 2026-10-16: the pick is the side the projection says covers
SF projected by 9.6 on a -7.5 line, yet the card pointed at WAS because the bet probability had been pulled toward the market and 7 sits on the underdog side of -7.5. The user said picks must follow the projection, whether or not the price is +EV, and gave IND (projected +8.6 vs -7) as the example. Changed: "If you had to bet" and "Picks at a glance" use the projected margin or total versus the line, show the cushion in points, and show EV separately. Only the BET/LEAN tags are about price.

## 2026-10-16: spreads and totals only, no parlays
The user does not want moneyline or underdog hunting, and does not need the Parlay Ideas tab. Changed: Game Bets show spreads and totals only; the parlay tab, code, logging and tests are removed.

## 2026-10-16: injuries matter a ton, and roles consolidate
Dameon Pierce's props leaned under although Barkley is out, Shipley is on IR, and the other Eagles backs are on reserve or the practice squad, so Pierce is the lead back. Causes: the roster still listed non-active backs, and a missing player's carries were spread to everyone instead of staying with the backs who can play. Changed: only players on the active roster (or who played in the last 2 weeks) share usage; running-back carries are consolidated among the available backs; most of a missing back's targets stay with the remaining backs; offensive line, defensive line, linebacker, cornerback, safety and kicker absences now move the spread and total (values fitted by `inj_backtest.py`).
Still to do: judge star quality, not just snap share, for defenders and linemen.

## 2026-10-16: keep learning
The user wants an analyst that studies every settled game and gets smarter weekly, for NFL, then NBA and NHL. Changed: `learning.py` reviews graded picks each run (reviews/week_N.md), nudges a few priors only with enough data and inside bounds, and logs every change. Rule for the analyst: when a correction arrives, find the root cause, fix it, add a regression test, and write the entry here.

## 2026-10-16: speak in plain English and group the stats the way a person reads them
The team tables were correct but unreadable: jargon (CPOE) and passing, rushing and other stats were interleaved. Changed: CPOE is now "completion % above expected" (with a glossary), every table lists all passing stats, then all rushing stats, then everything else (sacks, 3rd down, red zone, points, penalties). Above the tables, every game now has a written "What stands out" section (run game, passing game, biggest gaps, injuries that change the game, how we expect it to go) generated from the ranks, the injury report and the projection. Example the user gave: JAX allows a 32.6% rush success rate and HOU runs poorly, and David Montgomery is out, so HOU will struggle to run.

## 2026-10-16: a questionable player usually plays
The model treated "questionable" as a 60% chance to play. In the NFL it is closer to 75%. Changed: `PLAY_PROB["questionable"]` = 0.75 (affects QB expectation, skill and line/defence injury values, TD and prop availability). Doubtful stays 10%. Results tracking should check this: log how often questionable players actually play.

## 2026-10-17 Best Props tab
User wants, per game, 1 QB + 2 WR + 2 RB + 1 TE props priced +120 to -140, chosen for win chance not EV, plus a watchlist (Metcalf, Wan'Dale Robinson, Garrett Wilson, Kincaid). Implemented in best_props.py; picks logged before kickoff and graded under "Best props picks". Regression: tests/test_best_props.py (price window, slot caps, unique players).

## 2026-10-17 Props: matchups and 2026-only games
User: don't use last year's games or "last 8" that reach into 2025 (5 games this year is enough); focus on the game dynamic (e.g. a great run defence means the opponent throws more) rather than only a player's recent games. Changes: props_board.py uses 2026 stats and usage only; opponent run/pass defence (EPA allowed) now shifts team pass vs carry volume (config.PROP_PASS_RATE, fitted on 2025 neutral-situation pass rate: only about +-1% attempts per 1 sd, so small but real); receiving uses what the defence allows to that position (catch rate, yards per catch). Pick text names the matchup. Regression: tests/test_best_props.py.

## 2026-10-24 Injured-reserve players were missing from the injury lists
User: Michael Pittman Jr. and Roman Wilson (PIT) are out on IR but were not shown. Cause: ESPN and the weekly report only list players flagged THIS week. Fix: adapters/injuries.long_term() adds every roster-reserve (IR/PUP/NFI) player with a real role (played in 2026 before IR, or 20%+ snaps / 15+ targets or carries in 2025), for both teams of every game, shown as season-long. Display only: team ratings come from games played, so counting them again would double count. Rule: injury lists must include everyone who is out, not only this week's report. Test: tests/test_boards.py.

## 2026-10-24 TE touchdown tab
User asked for the top three tight ends most likely to score tomorrow against defences that allow TE TDs, TE red-zone targets and have bad pass / red-zone defence. te_board.py: TE score = 60% TD-model probability percentile + 40% defence rank average (2026 only), one TE per team in the top three, tab "TE TDs". Test in tests/test_boards.py.

- Injuries merge: nflverse's official report lagged ESPN on Saturday downgrades (A.J. Brown, TreVeyon Henderson showed questionable while ESPN said out). A harsher ESPN status now wins over the official one.

- Injury history (inj_history.py): every injured player now shows games missed in a row, last game played and snap share before, season snap average and role, and weeks on the report. Roster file lacks pfr ids for some players (Ioane), so snaps fall back to name+team; no snap rows means "unknown", never "has not played".

- Monday Night Football section (best_props.mnf): top of the Best Props tab shows the 5 best bets for the Monday game, ranked by win chance, one bet per player, mixing props, anytime TDs, spread and total. All were "Lean" (under 57
- Monday Night Football section (best_props.mnf): top of the Best Props tab shows the 5 best bets for the Monday game, ranked by win chance, one bet per player, mixing props, anytime TDs, spread and total. All five were "Lean" (under 57 percent) in week 8, so the board says so.

- Weather: nflweather posts no numbers for some outdoor games (CIN-ATL week 9 neutral-site game, 'Read More'). Outdoor gaps now get a labelled mild/calm placeholder instead of failing validation. The deep dive for a neutral-site game still looks up the home team's city, so its weather there is not the real venue's.

- Spread option lines are stored from the HOME team's view; an away pick's real line is the negative (board_template.html already does this). best_props._game_bets printed the home sign for away picks; fixed with a test. Any new code that prints a spread pick must flip the sign for away.
