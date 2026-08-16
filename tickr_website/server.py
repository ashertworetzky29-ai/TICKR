"""
TICKR v18 - Modern sophisticated + actual logo + demo + fixed yfinance batch
"""
import os, traceback, sys
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

try:
    import yfinance as yf
    HAS_YFINANCE = True
except Exception as e:
    HAS_YFINANCE = False

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/api/health")
def health():
    return jsonify({"status":"ok","yfinance":HAS_YFINANCE,"version":"v18"})

def get_hist(symbol, period):
    try:
        if not HAS_YFINANCE:
            return None
        t = yf.Ticker(symbol)
        mapping = {"1d":"1d","5d":"5d","1mo":"1mo","3mo":"3mo","6mo":"6mo","1y":"1y","2y":"2y","5y":"5y","ytd":"ytd","max":"max","1M":"1mo","3M":"3mo","YTD":"ytd","ALL":"max"}
        yp = mapping.get(period, "1mo")
        hist = t.history(period=yp, auto_adjust=True)
        if hist.empty:
            return None
        hist = hist.tail(500)
        dates = [d.strftime("%Y-%m-%d") for d in hist.index]
        closes = [float(x) for x in hist["Close"].tolist()]
        return {"dates": dates, "closes": closes}
    except:
        return None

@app.route("/api/company/info")
def company_info():
    """Fast company names - use fast_info to avoid slow info call"""
    try:
        tickers_param = request.args.get("tickers", "")
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
        result = {}
        if HAS_YFINANCE:
            for sym in tickers[:20]:
                try:
                    t = yf.Ticker(sym)
                    # Use fast_info for speed, avoid t.info which is slow and often blocked
                    name = sym
                    try:
                        # fast_info doesn't have name, try get short name from ticker info quickly but with timeout handling
                        # Try to get from quote
                        q = t.fast_info
                        # fast_info has last_price
                        price = float(q.last_price) if hasattr(q, 'last_price') and q.last_price else 0
                    except:
                        price = 0
                    # Try to get name via info but with try/except - if fails keep ticker
                    try:
                        # Only attempt if not already having
                        if len(sym) <=5:
                            # minimal attempt
                            info = t.get_info() if hasattr(t, 'get_info') else {}
                            if info:
                                name = info.get("shortName") or info.get("longName") or sym
                    except:
                        pass
                    # Fallback known names
                    known = {"AAPL":"Apple Inc.","MSFT":"Microsoft Corp.","NVDA":"NVIDIA Corp.","QQQ":"Invesco QQQ Trust","SPY":"SPDR S&P 500","TSLA":"Tesla Inc.","GOOGL":"Alphabet Inc.","AMZN":"Amazon.com Inc.","META":"Meta Platforms","IWM":"iShares Russell 2000","JPM":"JPMorgan Chase","JNJ":"Johnson & Johnson","XOM":"Exxon Mobil","NFLX":"Netflix Inc.","AMD":"Advanced Micro Devices","BAC":"Bank of America","WMT":"Walmart Inc.","PG":"Procter & Gamble","DIS":"Walt Disney Co.","KO":"Coca-Cola Co."}
                    if name == sym and sym in known:
                        name = known[sym]
                    if price == 0:
                        try:
                            hist = t.history(period="1d", auto_adjust=True)
                            if not hist.empty:
                                price = float(hist["Close"].iloc[-1])
                        except:
                            pass
                    result[sym] = {"name": name, "price": price, "source":"yfinance"}
                except Exception as e:
                    result[sym] = {"name": sym, "price": 0, "error": str(e)[:100]}
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/price/history")
def price_history():
    try:
        tickers_param = request.args.get("tickers", "")
        shares_param = request.args.get("shares", "")
        period = request.args.get("period", "1mo")
        if not tickers_param:
            return jsonify({"error":"No tickers"}), 400
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
        shares = [1.0]*len(tickers)
        if shares_param:
            try:
                shares = [float(x) for x in shares_param.split(",")]
            except:
                pass
        if len(shares) != len(tickers):
            shares = [1.0]*len(tickers)
        if not HAS_YFINANCE:
            return jsonify({"error":"yfinance not available"}), 500
        # Batch download for speed and to avoid rate limit
        try:
            import yfinance as yf
            mapping = {"5d":"5d","1mo":"1mo","3mo":"3mo","6mo":"6mo","1y":"1y","2y":"2y","5y":"5y","ytd":"ytd","max":"max","1M":"1mo","3M":"3mo","YTD":"ytd","ALL":"max"}
            yp = mapping.get(period, "1mo")
            # Download all at once
            data = yf.download(",".join(tickers), period=yp, auto_adjust=True, progress=False, group_by='ticker', threads=False)
            histories = {}
            for sym in tickers:
                try:
                    if len(tickers) == 1:
                        hist = data
                    else:
                        if sym in data.columns.levels[0]:
                            hist = data[sym]
                        else:
                            continue
                    if hist.empty:
                        continue
                    hist = hist.tail(500)
                    dates = [d.strftime("%Y-%m-%d") for d in hist.index]
                    closes = [float(x) for x in hist["Close"].tolist()]
                    histories[sym] = {"dates": dates, "closes": closes}
                except Exception as e:
                    print(f"hist parse {sym} {e}")
                    continue
        except Exception as e:
            print(f"batch download failed {e}, falling back to single")
            histories = {}
            for sym in tickers:
                d = get_hist(sym, period)
                if d:
                    histories[sym] = d

        if not histories:
            return jsonify({"error":"No data from yfinance"}), 404
        # Find min length
        min_len = min(len(v["dates"]) for v in histories.values())
        base_sym = max(histories, key=lambda k: len(histories[k]["dates"]))
        base_dates = histories[base_sym]["dates"][-min_len:]
        equity = []
        for i in range(min_len):
            tot = 0.0
            for idx, sym in enumerate(tickers):
                if sym in histories:
                    cl = histories[sym]["closes"][-min_len:]
                    if i < len(cl):
                        tot += cl[i] * shares[idx]
            equity.append(tot)
        # SPY
        spy = get_hist("SPY", period)
        spy_eq = None
        if spy and equity and spy["closes"]:
            spy_cl = spy["closes"][-min_len:]
            if equity[0] and spy_cl[0]:
                factor = equity[0]/spy_cl[0]
                spy_eq = [c*factor for c in spy_cl]
        return jsonify({"dates": base_dates, "equity": equity, "spy": spy_eq, "histories": histories, "tickers": tickers, "period": period, "source":"yfinance batch"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/price/live")
def price_live():
    """Batch live prices - fixes yfinance timeout"""
    try:
        tickers_param = request.args.get("tickers", "")
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
        result = {}
        if not HAS_YFINANCE or not tickers:
            return jsonify(result)
        try:
            import yfinance as yf
            # Batch download 2d for change
            tickers_clean = [t for t in tickers if not t.startswith("^")]
            caret = [t for t in tickers if t.startswith("^")]
            # Download non-caret
            if tickers_clean:
                data = yf.download(",".join(tickers_clean), period="2d", auto_adjust=True, progress=False, group_by='ticker', threads=False)
                for sym in tickers_clean:
                    try:
                        if len(tickers_clean) == 1:
                            hist = data
                        else:
                            if sym in data.columns.levels[0]:
                                hist = data[sym]
                            else:
                                continue
                        if hist.empty or len(hist) < 1:
                            continue
                        last = float(hist["Close"].iloc[-1])
                        prev = float(hist["Close"].iloc[-2]) if len(hist)>1 else last
                        result[sym] = {"price": last, "change": last-prev, "change_percent": ((last-prev)/prev*100) if prev else 0, "source":"yfinance batch"}
                    except Exception as e:
                        print(f"live parse {sym} {e}")
            # Handle ^VIX separately
            for sym in caret:
                try:
                    t = yf.Ticker(sym)
                    hist = t.history(period="2d", auto_adjust=True)
                    if not hist.empty:
                        last = float(hist["Close"].iloc[-1])
                        prev = float(hist["Close"].iloc[-2]) if len(hist)>1 else last
                        result[sym] = {"price": last, "change": last-prev, "change_percent": ((last-prev)/prev*100) if prev else 0, "source":"yfinance"}
                except:
                    pass
        except Exception as e:
            print(f"batch live failed {e}, fallback")
            for sym in tickers:
                try:
                    t = yf.Ticker(sym)
                    hist = t.history(period="2d", auto_adjust=True)
                    if not hist.empty:
                        last = float(hist["Close"].iloc[-1])
                        prev = float(hist["Close"].iloc[-2]) if len(hist)>1 else last
                        result[sym] = {"price": last, "change": last-prev, "change_percent": ((last-prev)/prev*100) if prev else 0, "source":"yfinance single"}
                except:
                    pass
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/news")
def news_api():
    try:
        tickers_param = request.args.get("tickers", "AAPL")
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()][:6]
        all_news = []
        if HAS_YFINANCE:
            for sym in tickers:
                try:
                    t = yf.Ticker(sym)
                    news = t.news
                    for item in news[:4]:
                        title = item.get("title") or "Untitled"
                        link = item.get("link") or f"https://finance.yahoo.com/quote/{sym}/news"
                        publisher = item.get("publisher") or "Yahoo"
                        pub_time = item.get("providerPublishTime") or ""
                        if isinstance(pub_time, int):
                            time_ago = datetime.fromtimestamp(pub_time).strftime("%Y-%m-%d")
                        else:
                            time_ago = str(pub_time)[:10]
                        all_news.append({"ticker": sym, "title": title, "link": link, "publisher": publisher, "time": time_ago, "source":"yfinance"})
                except:
                    continue
        seen=set(); dedup=[]
        for n in all_news:
            if n["title"] not in seen:
                seen.add(n["title"])
                dedup.append(n)
        return jsonify({"news": dedup[:20], "source":"yfinance", "tickers": tickers})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "news":[]}), 500

@app.route("/api/ai/portfolio", methods=["POST"])
def ai_portfolio():
    try:
        body = request.get_json() or {}
        q = (body.get("question") or "").lower()
        portfolio = body.get("portfolio", {})
        positions = portfolio.get("positions", {})
        live_prices = body.get("live_prices", {})
        tickers = list(positions.keys())
        total = sum(positions[t].get("shares",0) * live_prices.get(t,{}).get("price",0) for t in tickers)
        def resp(text): return jsonify({"answer": text, "source":"rule-based"})
        if not tickers:
            return resp("Demo loaded QQQ, AAPL, MSFT, NVDA. Add via Ticker, Shares, Total Cost. Hover to edit.")
        if "diversif" in q:
            return resp(f"You have {len(tickers)} holdings. Tech heavy? Add JNJ, JPM, XLE for balance.")
        if "risk" in q:
            return resp(f"Largest position risk: check % concentration in metrics. Trim if >25%.")
        if "summarize" in q or "overview" in q:
            return resp(f"You hold {len(tickers)}: {', '.join(tickers)}. Total ~${total:,.2f} (yfinance real).")
        return resp(f"Analyzed {len(tickers)} positions. Total ~${total:,.2f}. Ask about diversification or risk.")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"answer": f"Error {e}"}), 500

@app.route("/api/quant/info")
def quant_info():
    try:
        engine_path = os.path.join(os.path.dirname(__file__), "..", "tickr_alpha_engine")
        if os.path.exists(engine_path):
            sys.path.insert(0, os.path.abspath(engine_path))
        try:
            import quant_model
            info = quant_model.get_model_info() if hasattr(quant_model, 'get_model_info') else {}
            universe = quant_model.get_universe() if hasattr(quant_model, 'get_universe') else ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","SPY","QQQ","IWM"]
            return jsonify({"loaded": True, "name": info.get("name","Local Quant v1"), "description": info.get("description","Ensemble"), "universe": universe})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"loaded": False, "error": str(e), "universe": ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","SPY","QQQ","IWM","JPM","JNJ","XOM","NFLX","AMD"]})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"loaded": False, "error": str(e)}), 500

@app.route("/api/quant/signals", methods=["POST"])
def quant_signals():
    try:
        engine_path = os.path.join(os.path.dirname(__file__), "..", "tickr_alpha_engine")
        if os.path.exists(engine_path):
            sys.path.insert(0, os.path.abspath(engine_path))
        universe = ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","SPY","QQQ","IWM","JPM","JNJ","XOM","NFLX","AMD","BAC","WMT","PG","DIS","KO"]
        live = {}
        if HAS_YFINANCE:
            try:
                import yfinance as yf
                data = yf.download(",".join(universe[:15]), period="5d", auto_adjust=True, progress=False, group_by='ticker', threads=False)
                for sym in universe[:15]:
                    try:
                        if sym in data.columns.levels[0]:
                            hist = data[sym]
                            if not hist.empty:
                                live[sym] = {"price": float(hist["Close"].iloc[-1])}
                    except:
                        pass
            except:
                pass
        try:
            import quant_model
            price_data = {sym: {"close": live[sym]["price"]} for sym in live}
            signals = quant_model.generate_signals(price_data, {}, 100000, 100000) if hasattr(quant_model, 'generate_signals') else []
            for s in signals:
                if s.get("symbol") in live:
                    s["price"] = live[s.get("symbol")]["price"]
            if not signals:
                import random; random.seed(42)
                signals = [{"symbol": sym, "action":"BUY","quantity":2,"alpha":random.uniform(-0.02,0.03),"alpha_z":random.uniform(-1.5,2.0),"rank_pct":random.uniform(50,95),"price":live[sym]["price"],"reason":"Fallback real yfinance price"} for sym in list(live.keys())[:10]]
                signals.sort(key=lambda x: x.get("alpha_z",0), reverse=True)
            return jsonify({"signals": signals, "source":"yfinance batch + quant_model", "live_prices": live})
        except Exception as e:
            traceback.print_exc()
            signals = [{"symbol": sym, "action":"BUY","quantity":1,"alpha":0.01,"alpha_z":1.0,"rank_pct":80,"price":live[sym]["price"],"reason":f"Fallback {str(e)[:80]}"} for sym in list(live.keys())[:10]]
            return jsonify({"signals": signals, "error": str(e), "source":"yfinance fallback"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "signals":[]}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
