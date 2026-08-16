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


## GitHub + Render Deployment

### Option 1: New GitHub repo (recommended if TICKR is new)

```bash
# From your TICKR folder
cd TICKR

# Initialize git
git init
git add .
git commit -m "v14: TICKR master - website + alpha engine integrated"

# Create repo on GitHub (go to github.com/new, name it TICKR, don't init with README)
# Then link it:
git remote add origin https://github.com/YOUR_USERNAME/TICKR.git
git branch -M main
git push -u origin main
```

### Option 2: You already have tickr_website repo and want to add alpha engine

```bash
# If you already have a repo for tickr_website, move everything into TICKR structure
cd path/to/your/existing/repo

# Copy alpha engine in
cp -r /path/to/tickr_alpha_engine ./tickr_alpha_engine
cp -r /path/to/tickr_website/* ./tickr_website/  # if needed

# Add master files
cp ../TICKR/README.md ./
cp ../TICKR/requirements.txt ./
cp ../TICKR/.gitignore ./
cp ../TICKR/render.yaml ./
cp ../TICKR/Procfile ./

git add .
git commit -m "Add tickr_alpha_engine + master structure"
git push
```

### Render Deployment

**Render will deploy ONLY tickr_website (the alpha engine stays local for training, but its fast inference code is copied via quant_model.py bridge)**

1. Go to https://dashboard.render.com
2. Click **New +** → **Web Service**
3. Connect your GitHub repo `TICKR`
4. Configure:

**Settings A - Root Directory method (simplest):**
- **Root Directory:** `tickr_website`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn server:app`
- **Python Version:** 3.11

**Settings B - Master folder method:**
- **Root Directory:** (leave blank, root)
- **Build Command:** `pip install -r tickr_website/requirements.txt`
- **Start Command:** `cd tickr_website && gunicorn server:app`

5. Click **Create Web Service**
6. Wait 2-3 mins, your site will be live at `https://your-app.onrender.com`

**Important for Render with your structure:**
- Render only needs `tickr_website/` files, but we include `tickr_alpha_engine/quant_model.py` via the bridge. 
- The bridge file `tickr_website/quant_model.py` will try to import from `../tickr_alpha_engine/` — if you set Root Directory to `tickr_website`, you need to also include alpha engine. So use **Option B** (master root) OR copy `tickr_alpha_engine/quant_model.py` into `tickr_website/` as fallback (already done via bridge fallback).

**Easiest Render setup for your new TICKR folder:**

```
Service Type: Web Service
Repository: YOUR_USERNAME/TICKR
Branch: main
Root Directory: (empty - use repo root)
Build Command: pip install -r requirements.txt
Start Command: cd tickr_website && gunicorn server:app
```

This way Render installs from master requirements.txt and runs the website, and the website can still import `../tickr_alpha_engine/quant_model.py` because the whole TICKR folder is present.

### Testing locally before push

```bash
cd TICKR
# Test website
cd tickr_website
python server.py
# Open http://localhost:10000

# In another terminal, test alpha
cd ../tickr_alpha_engine
python -c "import quant_model; print(quant_model.get_model_info())"
```

