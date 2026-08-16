"""
TICKR Website Server — Fixed for Render
Serves index.html + paper trading + quant lab
Works both locally and on Render with gunicorn
"""
import os
import sys
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# --- Quant model import (works both locally and on Render) ---
# Your real model is in tickr_alpha_engine, but on Render we only have tickr_website
# So try both
try:
    # Try local structure: ../tickr_alpha_engine
    engine_path = os.path.join(os.path.dirname(__file__), "..", "tickr_alpha_engine")
    if os.path.exists(engine_path):
        sys.path.insert(0, os.path.abspath(engine_path))
    
    import quant_model
    HAS_QUANT = True
    print(f"✓ Loaded quant_model from {quant_model.__file__}")
except Exception as e:
    print(f"⚠ Failed to load quant_model: {e}")
    # Create dummy fallback so website still loads
    HAS_QUANT = False
    class DummyQuant:
        def get_universe(self): return ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","SPY","QQQ","IWM"]
        def get_model_info(self): return {"name":"Quant (fallback)","description":"Real model not loaded","version":"fallback"}
        def generate_signals(self, *a, **kw): return []
    quant_model = DummyQuant()

# Flask setup - serve from this folder
app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# In-memory paper portfolio (for Render demo)
paper_portfolio = {
    "cash": 100000.0,
    "positions": {},  # symbol -> {quantity, avg_price}
    "trades": []
}

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/<path:path>")
def serve_static(path):
    # Serve manifest, icons, etc
    if os.path.exists(os.path.join(".", path)):
        return send_from_directory(".", path)
    # Otherwise return index.html for SPA routing
    return send_from_directory(".", "index.html")

@app.route("/api/health")
def health():
    return jsonify({"status":"ok", "quant_loaded": HAS_QUANT})

@app.route("/api/model/info")
def model_info():
    try:
        info = quant_model.get_model_info()
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e), "name":"Error loading model"}), 500

@app.route("/api/paper/portfolio")
def paper_portfolio_api():
    return jsonify(paper_portfolio)

@app.route("/api/paper/run_quant", methods=["POST"])
def run_quant():
    try:
        body = request.get_json() or {}
        # Expecting price_data from frontend, or fetch live if empty
        price_data = body.get("price_data", {})
        current_positions = paper_portfolio.get("positions", {})
        cash = paper_portfolio.get("cash", 100000)
        portfolio_value = body.get("portfolio_value", cash)

        # If frontend didn't send price_data, build empty and let quant_model fetch via yfinance
        if not price_data and HAS_QUANT:
            # quant_model will fetch its own data if price_data empty (from your implementation)
            pass

        signals = quant_model.generate_signals(price_data, current_positions, cash, portfolio_value)
        return jsonify({"signals": signals, "count": len(signals)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "signals": []}), 500

@app.route("/api/paper/trade", methods=["POST"])
def paper_trade():
    try:
        body = request.get_json()
        symbol = body.get("symbol")
        action = body.get("action")  # BUY/SELL
        quantity = int(body.get("quantity", 0))
        price = float(body.get("price", 0))

        if not symbol or quantity <= 0:
            return jsonify({"error":"Invalid trade"}), 400

        if action == "BUY":
            cost = quantity * price
            if paper_portfolio["cash"] < cost:
                return jsonify({"error":"Not enough cash"}), 400
            paper_portfolio["cash"] -= cost
            pos = paper_portfolio["positions"].get(symbol, {"quantity":0, "avg_price":0})
            total_cost = pos["quantity"]*pos["avg_price"] + cost
            pos["quantity"] += quantity
            pos["avg_price"] = total_cost / pos["quantity"] if pos["quantity"] else 0
            paper_portfolio["positions"][symbol] = pos

        elif action == "SELL":
            pos = paper_portfolio["positions"].get(symbol)
            if not pos or pos["quantity"] < quantity:
                return jsonify({"error":"Not enough shares"}), 400
            paper_portfolio["cash"] += quantity * price
            pos["quantity"] -= quantity
            if pos["quantity"] == 0:
                del paper_portfolio["positions"][symbol]

        paper_portfolio["trades"].append({
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": price,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat()
        })

        return jsonify(paper_portfolio)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/price/<symbol>")
def price_api(symbol):
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1mo")
        if hist.empty:
            return jsonify({"error":"No data"}), 404
        return jsonify({
            "symbol": symbol,
            "price": float(hist["Close"].iloc[-1]),
            "history": hist["Close"].tail(60).tolist()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting TICKR on http://localhost:{port}")
    print(f"Quant loaded: {HAS_QUANT}")
    app.run(host="0.0.0.0", port=port, debug=True)
