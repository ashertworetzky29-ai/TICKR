import polars as pl
import lightgbm as lgb
import xgboost as xgb
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.model_selection import TimeSeriesSplit
import optuna
import numpy as np
import pandas as pd

FEATURE_COLS = ["ret_1d","ret_5d","ret_20d","ret_60d","dist_sma20","dist_sma60","vol_20","vol_60","vol_ratio","vol_ratio_60","trend","trend_60","intra_position","momentum","momentum_60","realized_vol","rsi_14","skew_20","kurt_20","autocorr_5"]

def compute_rsi(s, n=14):
    delta = s.diff()
    gain = delta.where(delta>0, 0).rolling(n).mean()
    loss = -delta.where(delta<0, 0).rolling(n).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def build_extra_features(pdf):
    pdf['rsi_14'] = pdf.groupby('ticker')['Close'].transform(lambda x: compute_rsi(x))
    pdf['skew_20'] = pdf.groupby('ticker')['ret_1d'].transform(lambda x: x.rolling(20).skew())
    pdf['kurt_20'] = pdf.groupby('ticker')['ret_1d'].transform(lambda x: x.rolling(20).kurt())
    pdf['autocorr_5'] = pdf.groupby('ticker')['ret_1d'].transform(lambda x: x.rolling(20).apply(lambda y: pd.Series(y).autocorr(5) if len(y)>5 else 0, raw=False))
    pdf['ret_60d'] = pdf.groupby('ticker')['Close'].pct_change(60)
    pdf['dist_sma60'] = pdf['Close'] / pdf.groupby('ticker')['Close'].transform(lambda x: x.rolling(60).mean()) - 1
    pdf['vol_60'] = pdf.groupby('ticker')['Close'].transform(lambda x: x.pct_change().rolling(60).std())
    pdf['vol_ratio_60'] = pdf.groupby('ticker')['Volume'].transform(lambda x: x / x.rolling(60).mean())
    pdf['trend_60'] = (pdf.groupby('ticker')['Close'].transform(lambda x: x.rolling(20).mean()) > pdf.groupby('ticker')['Close'].transform(lambda x: x.rolling(60).mean())).astype(int)
    pdf['momentum_60'] = pdf.groupby('ticker')['ret_1d'].transform(lambda x: x.rolling(60).mean())
    return pdf

def train_max_model(feat: pl.DataFrame, cfg):
    pdf = feat.to_pandas()
    pdf = build_extra_features(pdf).dropna()
    X = pdf[FEATURE_COLS].values
    y = pdf["next_5d_return"].values

    # Purged TimeSeries CV - no leakage
    tscv = TimeSeriesSplit(n_splits=cfg['cv_splits'])

    def objective(trial):
        model_type = trial.suggest_categorical("model_type", ["lgbm", "xgb"])
        if model_type == "lgbm":
            params = {
                "objective": "regression",
                "metric": "rmse",
                "verbosity": -1,
                "num_leaves": trial.suggest_int("num_leaves", 31, 256),
                "learning_rate": trial.suggest_float("lr", 0.005, 0.1, log=True),
                "feature_fraction": trial.suggest_float("ff", 0.5, 1.0),
                "bagging_fraction": trial.suggest_float("bf", 0.5, 1.0),
                "bagging_freq": 1,
                "min_data_in_leaf": trial.suggest_int("min_data", 20, 200),
                "lambda_l1": trial.suggest_float("l1", 1e-8, 10.0, log=True),
                "lambda_l2": trial.suggest_float("l2", 1e-8, 10.0, log=True),
            }
            scores=[]
            for train_idx, val_idx in tscv.split(X):
                # purge 5 days gap
                gap = 5
                train_idx = train_idx[train_idx < val_idx[0]-gap]
                dtrain = lgb.Dataset(X[train_idx], label=y[train_idx])
                dval = lgb.Dataset(X[val_idx], label=y[val_idx])
                m = lgb.train(params, dtrain, valid_sets=[dval], num_boost_round=1000, callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)])
                pred = m.predict(X[val_idx])
                ic = np.corrcoef(pred, y[val_idx])[0,1]
                scores.append(ic if not np.isnan(ic) else 0)
            return -np.mean(scores)
        else:
            params = {
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "learning_rate": trial.suggest_float("lr", 0.005, 0.1, log=True),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample", 0.5, 1.0),
                "reg_alpha": trial.suggest_float("l1", 1e-8, 10.0, log=True),
                "reg_lambda": trial.suggest_float("l2", 1e-8, 10.0, log=True),
            }
            scores=[]
            for train_idx, val_idx in tscv.split(X):
                gap=5
                train_idx = train_idx[train_idx < val_idx[0]-gap]
                m = xgb.XGBRegressor(**params, n_estimators=1000, early_stopping_rounds=50, verbosity=0)
                m.fit(X[train_idx], y[train_idx], eval_set=[(X[val_idx], y[val_idx])], verbose=False)
                pred = m.predict(X[val_idx])
                ic = np.corrcoef(pred, y[val_idx])[0,1]
                scores.append(ic if not np.isnan(ic) else 0)
            return -np.mean(scores)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=cfg['optuna_trials'], show_progress_bar=True)
    print(f"MAX MODEL - Best IC: {-study.best_value:.5f} {study.best_params}")

    # Final ensemble - train both best LGBM and XGB and average
    best = study.best_params
    if best['model_type'] == 'lgbm':
        lgb_params = {k: v for k,v in best.items() if k != 'model_type'}
        lgb_params.update({"objective":"regression","verbosity":-1})
        model_lgb = lgb.train(lgb_params, lgb.Dataset(X, label=y), num_boost_round=1500)
        model_xgb = xgb.XGBRegressor(max_depth=6, learning_rate=0.03, n_estimators=1000).fit(X,y)
    else:
        xgb_params = {k: v for k,v in best.items() if k != 'model_type'}
        model_xgb = xgb.XGBRegressor(**xgb_params, n_estimators=1500).fit(X,y)
        model_lgb = lgb.train({"objective":"regression","verbosity":-1}, lgb.Dataset(X, label=y), num_boost_round=1500)

    # ExtraTrees meta-learner for stacking
    meta_X = np.column_stack([model_lgb.predict(X), model_xgb.predict(X)])
    meta = ExtraTreesRegressor(n_estimators=200, max_depth=8, n_jobs=-1).fit(meta_X, y)

    pdf['alpha_lgb'] = model_lgb.predict(X)
    pdf['alpha_xgb'] = model_xgb.predict(X)
    pdf['alpha'] = meta.predict(meta_X)

    # Signal: dollar neutral, rank z-scored
    def make_signals(group):
        group['alpha_z'] = (group['alpha'] - group['alpha'].mean()) / (group['alpha'].std() + 1e-9)
        group['signal'] = np.clip(group['alpha_z'], -2, 2) / 2  # -1 to 1
        return group
    signals = pdf.groupby('Date', group_keys=False).apply(make_signals)

    models = {"lgb": model_lgb, "xgb": model_xgb, "meta": meta}
    return models, signals[['Date','ticker','Close','alpha','alpha_lgb','alpha_xgb','signal']]

def generate_signals(models, new_features):
    # new_features is polars DF, single latest bar per ticker
    import pandas as pd
    pdf = new_features.to_pandas()
    from model import FEATURE_COLS, build_extra_features
    # need at least rolling, so this function expects you pass last 60 rows, not 1
    pdf = build_extra_features(pdf)
    X = pdf[FEATURE_COLS].iloc[-len(new_features):].values
    pred_lgb = models['lgb'].predict(X)
    pred_xgb = models['xgb'].predict(X)
    meta_X = np.column_stack([pred_lgb, pred_xgb])
    return models['meta'].predict(meta_X)
