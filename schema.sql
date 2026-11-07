CREATE TABLE IF NOT EXISTS teams(abbr TEXT PRIMARY KEY, name TEXT, sgo_id TEXT, dome INTEGER, lat REAL, lon REAL);
CREATE TABLE IF NOT EXISTS games(game_id TEXT PRIMARY KEY, season INT, week INT, kickoff_utc TEXT, home TEXT, away TEXT,
  roof TEXT, home_score INT, away_score INT, sgo_event_id TEXT, rest_home INT, rest_away INT, location TEXT);
CREATE TABLE IF NOT EXISTS players(player_id TEXT PRIMARY KEY, name TEXT, pos TEXT, team TEXT, sgo_id TEXT, draft_pick INT, nfl_seasons INT);
CREATE TABLE IF NOT EXISTS team_week(season INT, week INT, team TEXT, plays INT, off_epa_pass REAL, off_epa_rush REAL,
  off_sr REAL, def_epa_pass REAL, def_epa_rush REAL, def_sr REAL, pts_for INT, pts_against INT,
  PRIMARY KEY(season,week,team));
CREATE TABLE IF NOT EXISTS player_week(season INT, week INT, player_id TEXT, team TEXT, opp TEXT, stats_json TEXT,
  snap_pct REAL, PRIMARY KEY(season,week,player_id));
CREATE TABLE IF NOT EXISTS odds_snap(snap_ts TEXT, event_id TEXT, odd_id TEXT, market TEXT, player_id TEXT, side TEXT,
  line REAL, book TEXT, price INT, open_price INT, open_line REAL, is_alt INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_odds ON odds_snap(event_id, odd_id);
CREATE TABLE IF NOT EXISTS injuries(snap_ts TEXT, player_id TEXT, name TEXT, team TEXT, pos TEXT, injury TEXT, status TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS weather(snap_ts TEXT, game_id TEXT, temp_f REAL, wind_mph REAL, precip_pct REAL, conditions TEXT, indoor INT);
CREATE TABLE IF NOT EXISTS public_splits(snap_ts TEXT, game_id TEXT, market TEXT, side TEXT, tickets_pct REAL, money_pct REAL);
CREATE TABLE IF NOT EXISTS pred_log(pred_id INTEGER PRIMARY KEY AUTOINCREMENT, logged_ts TEXT, game_id TEXT, market TEXT,
  player_id TEXT, side TEXT, line REAL, book TEXT, price INT, p_model REAL, p_market REAL, p_final REAL, ev REAL,
  label TEXT, is_parlay_leg INT DEFAULT 0, parlay_id TEXT,
  result TEXT, actual REAL, settled_ts TEXT);   -- result: win/loss/push
CREATE TABLE IF NOT EXISTS run_log(ts TEXT, step TEXT, ok INT, note TEXT);

CREATE TABLE IF NOT EXISTS parlays(parlay_id TEXT PRIMARY KEY, logged_ts TEXT, kind TEXT, n_legs INT, book TEXT, decimal REAL, p_est REAL, ev REAL, legs_json TEXT,
  first_kickoff TEXT, result TEXT, settled_ts TEXT);
