#!/bin/bash
# Run TICKR alpha engine full pipeline locally
cd "$(dirname "$0")/tickr_alpha_engine"
echo "Running full quant pipeline..."
echo "1. Data ingest"
echo "2. Feature engineering (20 factors)"
echo "3. Optuna + LGBM/XGB ensemble"
echo "4. VectorBT backtest"
echo "5. Paper trading loop"
python run_pipeline.py
