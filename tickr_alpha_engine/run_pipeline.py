import yaml, sys
from data_layer import fetch_data, save_parquet
from features import build_features
from model import train_max_model
from backtest import run_backtest
from paper_trade import start_paper_loop

print("=== MAX LOCAL QUANT - NO EXTRA HARDWARE ===")
print("CPU-optimized: Polars + LightGBM + XGBoost + Stacking Ensemble")

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

print("\n[1/5] DATA INGEST")
df = fetch_data(cfg['data']['tickers'], cfg['data']['start_date'])
save_parquet(df, "./data/raw.parquet")

print("\n[2/5] FEATURE ENGINEERING (20 factors)")
feat = build_features(df, cfg['features'])
print(f"Features: {feat.shape} rows, factors include RSI, skew, kurt, autocorr, multi-timeframe vol")

print("\n[3/5] MAX MODEL - ENSEMBLE + OPTUNA + PURGED CV")
print(f"Running {cfg['model']['optuna_trials']} Optuna trials with time-series purge gap...")
models, signals = train_max_model(feat, cfg['model'])

print("\n[4/5] BACKTEST - WALK FORWARD + COSTS + SLIPPAGE + RISK")
stats = run_backtest(feat, signals, cfg['backtest'], cfg['risk'])

print("\n[5/5] PAPER TRADING READY")
print("This is the max you can run locally without GPU:")
print("- 20 alpha factors, 2 base learners + meta learner")
print("- Purged TimeSeries CV to prevent leakage")
print("- Dollar-neutral, vol-targeted, Kelly-sized")
print("- Drawdown kill-switch and regime filter")
print("\nStarting paper loop (mock). Replace with Alpaca Paper API for real paper trading.")
if cfg['paper_trading']['enabled']:
    start_paper_loop(models, cfg)
