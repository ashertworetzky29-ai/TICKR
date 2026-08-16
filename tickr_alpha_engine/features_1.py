import polars as pl
import pandas as pd
import numpy as np

def build_features(df: pl.DataFrame, cfg):
    df = df.sort(["ticker", "Date"])
    # Core
    out = df.with_columns([
        pl.col("Close").pct_change().over("ticker").alias("ret_1d"),
        pl.col("Close").pct_change(5).over("ticker").alias("ret_5d"),
        pl.col("Close").pct_change(20).over("ticker").alias("ret_20d"),
        pl.col("Close").rolling_mean(20).over("ticker").alias("sma_20"),
        pl.col("Close").rolling_mean(60).over("ticker").alias("sma_60"),
        pl.col("Close").rolling_std(20).over("ticker").alias("vol_20"),
        (pl.col("Close") / pl.col("Close").rolling_mean(20).over("ticker") - 1).alias("dist_sma20"),
        (pl.col("Volume") / pl.col("Volume").rolling_mean(20).over("ticker")).alias("vol_ratio"),
        pl.col("Close").rolling_mean(5).over("ticker").alias("sma_5"),
    ])
    out = out.with_columns([
        (pl.col("sma_5") > pl.col("sma_20")).cast(pl.Int8).alias("trend"),
        ((pl.col("Close") - pl.col("Low")) / (pl.col("High") - pl.col("Low") + 1e-9)).alias("intra_position"),
        pl.col("ret_1d").rolling_mean(20).over("ticker").alias("momentum"),
        pl.col("ret_1d").rolling_std(20).over("ticker").alias("realized_vol"),
        pl.col("Close").pct_change(-5).over("ticker").alias("next_5d_return"),
    ])
    return out.drop_nulls()
