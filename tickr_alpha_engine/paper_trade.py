import time, duckdb, datetime, yfinance as yf
import polars as pl
from features import build_features
from model import generate_signals, FEATURE_COLS

def start_paper_loop(model, cfg):
    tickers = cfg['data']['tickers']
    con = duckdb.connect(cfg['paper_trading']['log_file'])
    con.execute("CREATE TABLE IF NOT EXISTS paper_trades (ts TIMESTAMP, ticker VARCHAR, price DOUBLE, alpha DOUBLE, side VARCHAR, qty DOUBLE)")

    print("PAPER TRADING MODE - no real orders. Ctrl+C to stop.")
    print(f"Logging to {cfg['paper_trading']['log_file']}")

    try:
        while True:
            # 1. Fetch latest
            df = yf.download(tickers, period="60d", auto_adjust=True, group_by='ticker')
            import pandas as pd
            rows=[]
            for t in tickers:
                sub = df[t] if len(tickers)>1 else df
                sub = sub.reset_index()
                sub['ticker']=t
                rows.append(sub)
            pdf = pd.concat(rows)
            pl_df = pl.from_pandas(pdf)

            # 2. Features
            feat = build_features(pl_df, cfg['features'])
            latest = feat.group_by("ticker").tail(1)

            # 3. Alpha
            alphas = generate_signals(model, latest)
            latest_pd = latest.to_pandas()
            latest_pd['alpha'] = alphas

            # 4. Simulate order
            for _, row in latest_pd.iterrows():
                side = "BUY" if row['alpha'] > 0 else "SELL"
                qty = 0.05  # 5% target weight example
                print(f"{datetime.datetime.now():%H:%M:%S} PAPER {side} {row['ticker']} @ {row['Close']:.2f} alpha={row['alpha']:.4f}")
                con.execute("INSERT INTO paper_trades VALUES (NOW(), ?, ?, ?, ?, ?)", 
                            [row['ticker'], float(row['Close']), float(row['alpha']), side, float(qty)])

            time.sleep(cfg['paper_trading']['interval_sec'])
    except KeyboardInterrupt:
        print("Stopped paper loop. Check trades with: SELECT * FROM paper_trades ORDER BY ts DESC")
