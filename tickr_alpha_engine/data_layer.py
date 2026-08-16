import yfinance as yf
import polars as pl
import pandas as pd

def fetch_data(tickers, start):
    data = yf.download(tickers, start=start, auto_adjust=True, group_by='ticker')
    # Flatten to long format
    rows = []
    for t in tickers:
        try:
            sub = data[t] if len(tickers)>1 else data
            sub = sub.reset_index()
            sub['ticker'] = t
            rows.append(sub)
        except Exception as e:
            print(f"skip {t}: {e}")
    df = pd.concat(rows)
    return pl.from_pandas(df)

def save_parquet(df, path):
    df.write_parquet(path)
    print(f"Saved {path} -> {df.shape}")
