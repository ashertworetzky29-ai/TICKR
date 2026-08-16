
"""
quant_model.py — Bridge between tickr_website and tickr_alpha_engine
This file lives in tickr_website/ but imports your actual quant logic from ../tickr_alpha_engine/
"""

import os
import sys
import importlib.util

ALPHA_PATH = os.path.join(os.path.dirname(__file__), '..', 'tickr_alpha_engine')
ALPHA_FILE = os.path.join(ALPHA_PATH, 'quant_model.py')

HAS_ALPHA = False
ALPHA_CONFIG = None
alpha_module = None

try:
    # Load alpha engine directly from file to avoid circular import
    if os.path.exists(ALPHA_FILE):
        spec = importlib.util.spec_from_file_location("tickr_alpha_quant", ALPHA_FILE)
        alpha_module = importlib.util.module_from_spec(spec)
        # Add alpha path to sys.path for its dependencies (config.yaml, etc.)
        if ALPHA_PATH not in sys.path:
            sys.path.insert(0, ALPHA_PATH)
        spec.loader.exec_module(alpha_module)
        HAS_ALPHA = True
        print(f"✓ Loaded alpha engine from {ALPHA_FILE}")
        ALPHA_CONFIG = getattr(alpha_module, 'CONFIG', None)
    else:
        print(f"Alpha file not found: {ALPHA_FILE}")
except Exception as e:
    print(f"Alpha engine not available: {e}, using fallback")
    import traceback
    traceback.print_exc()
    HAS_ALPHA = False

# Fallback implementations
def fallback_universe():
    return ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "SPY", "QQQ", "IWM"]

def fallback_generate_signals(price_data, positions, cash, portfolio_value=100000):
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

def fallback_get_model_info():
    return {
        "name": "Fallback Model (alpha engine not loaded)",
        "description": "Could not import tickr_alpha_engine. Check that tickr_alpha_engine/quant_model.py exists and dependencies are installed.",
        "version": "fallback",
        "universe": fallback_universe(),
        "params": {}
    }

# Export the functions that server.py expects
def get_universe():
    if HAS_ALPHA and alpha_module:
        try:
            return alpha_module.get_universe()
        except:
            return fallback_universe()
    return fallback_universe()

def generate_signals(price_data, current_positions, cash, portfolio_value=100000):
    if HAS_ALPHA and alpha_module:
        try:
            return alpha_module.generate_signals(price_data, current_positions, cash, portfolio_value)
        except Exception as e:
            print(f"Alpha generate error, using fallback: {e}")
            import traceback
            traceback.print_exc()
            return fallback_generate_signals(price_data, current_positions, cash, portfolio_value)
    return fallback_generate_signals(price_data, current_positions, cash, portfolio_value)

def get_model_info():
    if HAS_ALPHA and alpha_module:
        try:
            info = alpha_module.get_model_info()
            info['bridge'] = 'tickr_website/quant_model.py -> tickr_alpha_engine/quant_model.py'
            info['has_alpha'] = True
            info['alpha_file'] = ALPHA_FILE
            return info
        except Exception as e:
            print(f"get_model_info error: {e}")
    info = fallback_get_model_info()
    info['bridge'] = 'fallback'
    info['has_alpha'] = False
    return info

def get_config():
    if HAS_ALPHA:
        return ALPHA_CONFIG
    return None

CONFIG = ALPHA_CONFIG
