# Local Quant v1 - Intelligent Paper Trading Pipeline

Production-ready but runs on your laptop.

## Quick Start
```
pip install -r requirements.txt
python run_pipeline.py
```
1. Downloads data -> data/raw.parquet
2. Builds 10+ alpha factors
3. Trains LightGBM with Optuna + TimeSeriesSplit (maximizes IC, not just MSE)
4. Walk-forward backtest with VectorBT (fees + slippage + SL/TP)
5. Starts PAPER trading loop that logs to DuckDB, no real broker

## Before Live Integration Checklist
- [ ] Replace yfinance with Alpaca/Polygon for live data
- [ ] Swap paper_trade.py with Alpaca Paper API: client.submit_order()
- [ ] Add kill-switch: if drawdown > max_drawdown_kill -> flatten all
- [ ] Add regime filter: disable when VIX > 30 or SPY < 200SMA
- [ ] Log everything to MLflow

## How it makes decisions (intelligent part)
- Not just SMA crossover. It learns non-linear relationships: dist from SMA, vol ratio, momentum, realized vol
- Alpha = predicted next_5d_return
- Signal = long top 50% alpha vs market median, short bottom 50% (market neutral)
- Position size = rank(alpha) * Kelly * max_position

## Safety
Paper mode by default. No real money moves until you wire a broker.
