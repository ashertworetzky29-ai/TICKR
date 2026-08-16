import vectorbt as vbt
import pandas as pd
import numpy as np

def run_backtest(feat, signals_df, backtest_cfg, risk_cfg):
    # Pivot signals to wide matrix: date x ticker
    close_wide = feat.to_pandas().pivot(index='Date', columns='ticker', values='Close').sort_index()
    signal_wide = signals_df.pivot(index='Date', columns='ticker', values='signal').reindex(close_wide.index).fillna(0)

    # Position sizing: Kelly fraction * max_position
    # alpha -> weight
    alpha_wide = signals_df.pivot(index='Date', columns='ticker', values='alpha').reindex(close_wide.index).fillna(0)
    # Rank and scale
    weights = alpha_wide.rank(axis=1, pct=True) - 0.5  # -0.5 to 0.5
    weights = weights.clip(-risk_cfg['max_position_pct'], risk_cfg['max_position_pct'])

    # VectorBT backtest
    pf = vbt.Portfolio.from_orders(
        close=close_wide,
        size=weights * risk_cfg['kelly_fraction'],
        size_type='targetpercent',
        fees=backtest_cfg['fees'],
        slippage=backtest_cfg['slippage'],
        init_cash=backtest_cfg['initial_cash'],
        freq='1D',
        sl_stop=backtest_cfg['stop_loss'],
        tp_stop=backtest_cfg['take_profit']
    )

    stats = pf.stats()
    # Add custom metrics
    print(f"Total Return: {stats['Total Return [%]']:.2f}%")
    print(f"Sharpe: {stats['Sharpe Ratio']:.2f}")
    print(f"Max DD: {stats['Max Drawdown [%]']:.2f}%")
    print(f"Win Rate: {stats['Win Rate [%]']:.2f}%")

    # Save trades
    pf.trades.records_readable.to_csv("./data/trades.csv")
    return stats
