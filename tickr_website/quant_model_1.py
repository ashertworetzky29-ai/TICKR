
"""
quant_model.py — Bridge between tickr_website and tickr_alpha_engine
This file lives in tickr_website/ but imports your actual quant logic from ../tickr_alpha_engine/
"""

import sys
import os

# Add alpha engine to path
ALPHA_PATH = os.path.join(os.path.dirname(__file__), '..', 'tickr_alpha_engine')
if ALPHA_PATH not in sys.path:
    sys.path.insert(0, ALPHA_PATH)

# Try to import your integrated model
try:
    from quant_model import (
        get_universe as alpha_get_universe,
        generate_signals as alpha_generate_signals,
        get_model_info as alpha_get_model_info,
        CONFIG as ALPHA_CONFIG
    )
    HAS_ALPHA = True
    print("✓ Loaded alpha engine from tickr_alpha_engine/")
except Exception as e:
    print(f"Alpha engine not available: {e}, using fallback")
    HAS_ALPHA = False
    ALPHA_CONFIG = None

    # Fallback implementations
    def alpha_get_universe():
        return ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "SPY", "QQQ", "IWM"]
    
    def alpha_generate_signals(price_data, positions, cash, portfolio_value=100000):
        # Simple fallback if alpha engine fails
        signals = []
        for sym, data in price_data.items():
            hist = data.get('history', [])
            if len(hist) < 20:
                continue
            price = data.get('price', 0)
            sma20 = sum(hist[-20:]) / 20
            if price < sma20 * 0.97 and cash > price * 5:
                signals.append({
                    "symbol": sym,
                    "action": "BUY",
                    "quantity": max(1, int((cash * 0.05) / price)),
                    "reason": f"Mean reversion: ${price:.0f} below SMA ${sma20:.0f}",
                    "confidence": 0.6,
                    "alpha": (sma20 - price) / price
                })
        return signals[:5]
    
    def alpha_get_model_info():
        return {
            "name": "Fallback Model (alpha engine not loaded)",
            "description": "Could not import tickr_alpha_engine. Check that tickr_alpha_engine/quant_model.py exists and dependencies are installed.",
            "version": "fallback",
            "universe": alpha_get_universe(),
            "params": {}
        }

# Export the functions that server.py expects
def get_universe():
    return alpha_get_universe()

def generate_signals(price_data, current_positions, cash, portfolio_value=100000):
    return alpha_generate_signals(price_data, current_positions, cash, portfolio_value)

def get_model_info():
    info = alpha_get_model_info()
    info['bridge'] = 'tickr_website/quant_model.py -> tickr_alpha_engine/'
    info['has_alpha'] = HAS_ALPHA
    return info

def get_config():
    return ALPHA_CONFIG

CONFIG = ALPHA_CONFIG
