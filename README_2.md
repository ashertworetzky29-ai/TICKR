# TICKR — Website + Alpha Engine

Master folder structure:

```
TICKR/
├── tickr_website/          # Flask website (what you deploy to Render)
│   ├── index.html          # Frontend
│   ├── server.py           # Backend + paper trading API
│   ├── quant_model.py      # BRIDGE → imports from tickr_alpha_engine
│   ├── manifest.json
│   └── ...
│
└── tickr_alpha_engine/     # Your quant model (runs locally)
    ├── config.yaml         # Universe, risk, backtest params
    ├── data_layer.py       # yfinance -> parquet
    ├── features.py         # 10+ alpha factors
    ├── model.py            # LightGBM + XGBoost + Optuna + Stacking
    ├── backtest.py         # VectorBT backtest with fees/slippage/SL/TP
    ├── paper_trade.py      # Paper trading loop (logs to DuckDB)
    ├── quant_model.py      # INTEGRATED: fast inference for website
    ├── run_pipeline.py     # Full pipeline: data -> features -> train -> backtest -> paper
    └── data/               # raw.parquet, trades.db, models/
```

## How it works

### Local Development (Full Quant)

```bash
cd tickr_alpha_engine
pip install -r requirements-full.txt
python run_pipeline.py
# 1. Downloads data -> data/raw.parquet
# 2. Builds 20 factors (dist_sma, vol_ratio, RSI, skew, etc.)
# 3. Trains ensemble with Optuna (100 trials, purged TimeSeriesSplit, maximizes IC)
# 4. Backtests with VectorBT (fees + slippage + SL/TP)
# 5. Starts paper trading loop -> data/paper_trades.db
```

### Website (Deployed)

```bash
cd tickr_website
pip install -r ../requirements.txt
python server.py
# Runs on http://localhost:10000
# - Your portfolio tracker (auto-load, sector sort, etc.)
# - Paper trading: $100k virtual
# - Quant Lab button -> calls tickr_alpha_engine/quant_model.py for signals
```

The bridge `tickr_website/quant_model.py` imports from `tickr_alpha_engine/quant_model.py`, so your real alpha logic runs on the website's paper trading.

### Deployment to Render

Render only needs `tickr_website/`:

- Build Command: `pip install -r requirements.txt` (from master) or `pip install flask flask-cors yfinance pandas`
- Start Command: `cd tickr_website && gunicorn server:app`
- Or set Root Directory to `tickr_website` in Render settings

Your alpha engine stays local for training, but the fast inference version (`quant_model.py`) is deployed with the website.

## Integration Points

1. **Universe**: Edit `tickr_alpha_engine/config.yaml` -> `data.tickers`
2. **Risk**: Edit `config.yaml` -> `risk.max_position_pct`, `kelly_fraction`
3. **Features**: Edit `tickr_alpha_engine/features.py` to add factors
4. **Model**: `tickr_alpha_engine/model.py` handles training. For website inference, edit `quant_model.py` -> `generate_alpha_simple()` or add model loading.

## Paper Trading Flow

```
User clicks "Run Model" in website
  -> POST /api/paper/run_quant
  -> server.py imports tickr_alpha_engine/quant_model.py
  -> quant_model.py fetches 60d OHLCV via yfinance
  -> builds 20 factors (same as features.py)
  -> generates alpha = predicted next_5d_return
  -> ranks, creates signals: long top 50% vs median, short bottom 50%
  -> position size = rank * Kelly * max_position
  -> Returns signals to frontend
  -> User clicks Execute -> POST /api/paper/trade -> paper portfolio updated
```

## Before Live Broker Integration

From your README checklist:
- [ ] Replace yfinance with Alpaca/Polygon for live data
- [ ] Swap paper_trade.py with Alpaca Paper API: client.submit_order()
- [ ] Add kill-switch: if drawdown > max_drawdown_kill -> flatten all
- [ ] Add regime filter: disable when VIX > 30 or SPY < 200SMA
- [ ] Log everything to MLflow

## Quick Start

```bash
# Clone your TICKR folder
cd TICKR

# Run website locally
cd tickr_website
python server.py
# Open http://localhost:10000 -> click Quant Lab -> Run Model

# Run full quant locally (separate terminal)
cd ../tickr_alpha_engine
python run_pipeline.py
```
