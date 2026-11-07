"""All priors and switches live here. Nothing is 'fitted' unless tracking says so."""
import os
from pathlib import Path

ROOT = Path(__file__).parent
CACHE = ROOT / "data" / "cache"
DB_PATH = ROOT / "data" / "nfl.db"

SEASON = 2026
LAST_SEASON = 2025

ALLOWED_BOOKS = ["fanduel", "draftkings", "betmgm", "espnbet", "bovada"]
REFERENCE_BOOK = "fanduel"

# SportsGameOdds (amateur tier: 2,500 entities/month, 10 req/min)
SGO_BASE = "https://api.sportsgameodds.com/v2"
SGO_MONTHLY_ENTITY_BUDGET = 2500
SGO_MIN_SECONDS_BETWEEN_CALLS = 7

# Probability blend: weight on MODEL in logit space (0.5 = 50/50 with de-vigged market)
MODEL_WEIGHT = {"spread": 0.7, "moneyline": 0.7, "total": 0.7, "td": 0.7, "prop": 0.7}   # 70% model / 30% market (user choice)

# EV labels
BET_EV, LEAN_EV = 0.03, 0.01

# Anytime TD tab
TD_MIN_PROB, TD_TOP_N = 0.15, 50

# Injury play probabilities
PLAY_PROB = {"healthy": 1.0, "questionable": 0.75, "doubtful": 0.10, "out": 0.0, "ir": 0.0}

# Public money / line movement: capped points added to projected margin / total
PUBLIC_CAP_SPREAD, PUBLIC_CAP_TOTAL = 0.75, 0.5


# Public money vs tickets (SportsBettingDime): money% minus tickets% on a side
PUBLIC_DIFF_MIN = 10      # >= this many points = "sharp-looking" (money > tickets) / "public" (tickets > money)
PUBLIC_FULL_DIFF = 30     # gap at which the capped adjustment reaches its full cap

# Weather priors (points)
WIND_MPH_THRESHOLD = 15

# ---- Game model priors (tuned by backtest.py on last season's walk-forward errors; see README) ----
OFFSEASON_WEEKS = 20          # season spacing on the time axis (18 weeks + gap)
RATING_HALF_LIFE = 8          # weeks; older games count less
RATING_RIDGE = 12.0           # shrinkage toward league average (about "6 games" of prior)
LEAGUE_PASS_RATE = 0.58       # share of EPA plays that are dropbacks
POINTS_PER_EPA = 1.0          # points per (plays * EPA/play) above league average; backtest tunes
LEAGUE_PTS_PER_TEAM = 23.1
HFA = 2.0                     # home-field advantage in points
HIST_FROM_SEASON = 2006        # NFL margin / total distribution is built from games since this season
MARGIN_KERNEL_BW = 2.0        # points; games with a closing spread near our projection feed the margin distribution
TOTAL_KERNEL_BW = 2.0

# Adjustments (points; priors checked by tracking, never "fitted" beyond the backtest above)
QB_SHRINK_DROPBACKS = 150         # QB EPA/dropback shrunk toward league with this many dropbacks of prior
QB_REPLACEMENT_EPA = -0.12        # EPA/dropback for a QB with no data
SKILL_PTS_PER_TARGET_SHARE = 4.0  # a 28% target-share WR out ~ -1.1 pts
SKILL_PTS_PER_RUSH_SHARE = 1.7
INJURY_CAP_PER_TEAM = 4.0
USAGE_LOOKBACK_GAMES = 5
REST_BYE_BONUS = 0.5              # coming off 10+ days rest
REST_SHORT_PENALTY = -0.5         # 5 days or fewer
TRAVEL_TZ_PENALTY = -0.3          # away team crossing 2+ time zones
WIND_TOTAL_PER_MPH = -0.15        # per mph above WIND_MPH_THRESHOLD, outdoor games only (max -3)
RAIN_TOTAL_ADJ = -1.0             # rain / snow (>=60% precip or wintry wording)
COLD_TOTAL_ADJ = -1.0             # temp below 25F
LINE_MOVE_CAP_SPREAD, LINE_MOVE_CAP_TOTAL = 0.25, 0.25   # share of the public cap used for opening->current movement
QB_ADJ_SCALE = 1.0               # (legacy; the QB now enters the ratings regression as a covariate)

# How much of (our projection - market line) is treated as real when turning a projection into OUR probability.
# Walk-forward backtest (qb_backtest.py, 273 games): margin trust = -0.34 +/- 0.22, total trust = +0.22 +/- 0.22,
# i.e. no demonstrable edge over the closing line yet. Priors kept small until Results tracking says otherwise.
MODEL_TRUST = {"margin": 0.15, "total": 0.20}
QB_RIDGE = 2.0                    # shrinkage on the QB covariate coefficient in the ratings regression
GAME_FLAGS_FILE = "game_flags.csv"   # per team-game down-weights for outlier games (weather, neutral site, mid-game injuries)
HFA_NEUTRAL = 0.0
QB_EXPERIENCE_DROPBACKS = 400     # dropbacks in our window before a QB shrinks toward the league mean instead of replacement
TD_ASSUMED_HOLD = 0.07            # anytime-TD prices have no No side; divide implied prob by (1 + this) as the assumed overround

# ---- Anytime-TD model priors (td_backtest.py picks the starting values; Results tracking judges them) ----
TD_HALF_LIFE_GAMES = 6        # recency weighting of a player's usage, in games
TD_PRIOR_GAMES = 4            # games of role prior mixed into a player's own TD history
TD_HIST_WEIGHT = 0.1          # weight on the player's own TD history vs usage-based lambda
TD_ENV_GAMMA = 0.8            # TD rate scales with (team implied points / 22.5) ** gamma
TD_OPP_STRENGTH = 0.5         # share of opponent TDs-allowed-to-position ratio that is applied
TD_LAMBDA_SCALE = 0.95        # calibration multiplier on lambda
TD_MIN_PROB = 0.15            # tab shows players the model gives at least this chance
TD_TOP_N = 50                 # ... top N by EV
TD_LAMBDA_BASE = 0.03         # TDs that usage bands miss (returns, trick plays, fumble recoveries): backtest underpredicted the lowest-usage players
TD_CAL_KNEE, TD_CAL_SLOPE = 0.35, 0.6   # backtest: players predicted above 35% scored less often than predicted, so the excess is compressed
TD_ROLE_LAMBDA = {"starter": {"RB": 0.12, "WR": 0.09, "TE": 0.08}, "backup": 0.03}   # prior for players with under 3 games of data
GAME_MARKETS = ("spread", "total")     # Game Bets focus: spreads and totals only (moneylines are not shown or graded)
TD_TRUST_BASE, TD_TRUST_DATA = 0.35, 0.45   # share of (model - market) believed = base + data * n_eff/(n_eff+6): thin-data players lean on the market
TD_GAP_PENALTY = 0.5            # trust divides by 1 + this * max(0, model/market ratio - 1.5)

# ---- Player props model (props_backtest.py): variance = a * mean for each market (fitted on 2025 walk-forward residuals) ----
PROP_DISP = {"pass_yds": 35.9, "pass_att": 3.9, "pass_comp": 2.8, "pass_td": 1.04, "pass_int": 1.52, "rush_yds": 27.3, "rush_att": 3.3, "rec_yds": 22.7, "receptions": 1.27}
PROP_HALF_LIFE_GAMES = 6
PROP_SCRIPT_PASS, PROP_SCRIPT_RUSH = 0.006, 0.007     # change in team pass / rush volume per point of expected margin
PROP_PASS_RATE = {"run": 0.0075, "pass": 0.0083}       # change in pass share of plays per 1 sd of opponent run / pass defence (EPA allowed), fitted on 2025 neutral situations
PROP_OPP_STRENGTH = 0.5                                # share of the opponent-vs-position ratio applied (times games/(games+8))
PROP_TRUST = 0.4                                       # share of (model - market) believed; props model is not yet proven against the market
PROP_MARKETS = ["pass_yds", "rush_yds", "rec_yds", "receptions", "rush_att", "pass_td", "pass_comp", "pass_att", "pass_int", "pass_rush_yds", "rush_rec_yds"]
PROP_GAP_PENALTY = 4.0             # trust divides by 1 + this * max(0, |mean - line| / line - 0.2)

# ---- Non-skill injury values: points per full-time starter missing (inj_backtest.py ridge posterior, 2025-26 walk-forward) ----
INJ_PTS = {"OL": 0.45, "DL": 0.56, "LB": 0.45, "CB": 0.80, "S": 0.41, "ST": 0.15}
INJ_CAP_GROUP = 3.5               # cap on points lost to one side's offence-line / defence absences in one game
RB_TARGET_KEEP = 0.6              # share of a missing back's targets that stays with the remaining backs (rest spreads to all receivers)


# ---- parameters nudged by learning.py from graded results (learned.json); bounded and logged, never silent ----
import json as _json
_learned = ROOT / "learned.json"
if _learned.exists():
    try:
        for _k, _v in _json.loads(_learned.read_text(encoding="utf-8")).items():
            if _k.startswith("MODEL_TRUST."):
                MODEL_TRUST[_k.split(".")[1]] = float(_v["value"])
            elif _k in ("TD_LAMBDA_SCALE", "PROP_TRUST"):
                globals()[_k] = float(_v["value"])
    except Exception:            # a damaged file must never stop the board
        pass
