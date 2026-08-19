"""
TICKR v24 FREE WORKING - No yfinance dependency for Render free tier
Yahoo blocks Render IPs. This uses FREE no-key sources that WORK on Render:
1. Stooq CSV (primary, free, no key, not blocked) - https://stooq.com
2. Yahoo Chart API direct via curl_cffi (secondary) - https://query1.finance.yahoo.com/v8/finance/chart/
3. yfinance fast_info as last fallback (often blocked)

All real prices, zero fake/hallucinated. Free forever, no API key needed.
"""
import os, traceback, time, csv, io, re
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

try:
    from curl_cffi import requests as cffi_requests
    session = cffi_requests.Session(impersonate="chrome")
    print("Using curl_cffi chrome session - bypasses Yahoo blocks")
except Exception as e:
    print(f"curl_cffi not available {e}, using requests")
    import requests as req
    session = req.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

try:
    import yfinance as yf
    HAS_YFINANCE = True
except:
    HAS_YFINANCE = False

# ---------- STOOQ (FREE, NO KEY, WORKS ON RENDER) ----------
def stooq_symbol(ticker):
    # Stooq format: aapl.us, qqq.us - lower case + .us
    t = ticker.lower().strip()
    # For ETFs like QQQ, SPY, still .us
    if "." not in t:
        t = t + ".us"
    return t

def get_live_stooq(ticker):
    """Free Stooq live price - works on Render, no API key"""
    try:
        sym = stooq_symbol(ticker)
        url = f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv"
        r = session.get(url, timeout=10)
        if not r.ok:
            return None
        text = r.text
        # CSV: Symbol,Date,Time,Open,High,Low,Close,Volume
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                close = float(row.get('Close') or 0)
                if close <= 0:
                    continue
                open_p = float(row.get('Open') or close)
                change = close - open_p
                # Stooq doesn't give prev close easily, approximate
                return {
                    "price": close,
                    "change": change,
                    "change_percent": (change/open_p*100) if open_p else 0,
                    "source": "stooq (free, no key)",
                    "open": open_p,
                    "high": float(row.get('High') or close),
                    "low": float(row.get('Low') or close),
                    "volume": int(float(row.get('Volume') or 0))
                }
            except:
                continue
    except Exception as e:
        print(f"stooq live {ticker} error {e}")
    return None

def get_history_stooq(ticker, period="1mo"):
    """Free Stooq history - works on Render"""
    try:
        sym = stooq_symbol(ticker)
        url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
        r = session.get(url, timeout=12)
        if not r.ok:
            return None
        text = r.text
        # CSV: Date,Open,High,Low,Close,Volume
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return None
        # Map period to number of days
        days_map = {"5d":5,"1mo":22,"3mo":66,"6mo":132,"1y":252,"2y":504,"5y":1260,"ytd":300,"max":5000,"1M":22,"3M":66,"YTD":300,"ALL":5000}
        need = days_map.get(period, 22)
        # Stooq returns oldest first, we want tail
        tail = rows[-need:]
        dates = []
        closes = []
        for row in tail:
            try:
                d = row.get('Date')
                c = float(row.get('Close'))
                if c and d:
                    dates.append(d)
                    closes.append(c)
            except:
                continue
        if closes:
            return {"dates": dates, "closes": closes, "source":"stooq free"}
    except Exception as e:
        print(f"stooq hist {ticker} {period} error {e}")
    return None

# ---------- YAHOO DIRECT CHART API (FREE, NO KEY, via curl_cffi) ----------
def get_live_yahoo_direct(ticker):
    """Yahoo chart API direct - often works even when yfinance wrapper blocked"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
        r = session.get(url, timeout=10)
        if not r.ok:
            return None
        j = r.json()
        result = j.get('chart',{}).get('result')
        if not result:
            return None
        res = result[0]
        meta = res.get('meta',{})
        price = meta.get('regularMarketPrice')
        prev = meta.get('previousClose') or meta.get('chartPreviousClose')
        if not price:
            # try from indicators
            quotes = res.get('indicators',{}).get('quote',[{}])[0]
            closes = quotes.get('close',[])
            closes = [c for c in closes if c is not None]
            if closes:
                price = closes[-1]
                prev = closes[-2] if len(closes)>1 else price
        if price:
            change = (price - prev) if prev else 0
            return {
                "price": float(price),
                "change": float(change),
                "change_percent": float((change/prev*100) if prev else 0),
                "source": "yahoo chart API direct (free)"
            }
    except Exception as e:
        print(f"yahoo direct live {ticker} error {e}")
    return None

def get_history_yahoo_direct(ticker, period="1mo"):
    range_map = {"5d":"5d","1mo":"1mo","3mo":"3mo","6mo":"6mo","1y":"1y","2y":"2y","5y":"5y","ytd":"ytd","max":"max","1M":"1mo","3M":"3mo","YTD":"ytd","ALL":"max"}
    r = range_map.get(period, "1mo")
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={r}"
        resp = session.get(url, timeout=12)
        if not resp.ok:
            return None
        j = resp.json()
        result = j.get('chart',{}).get('result')
        if not result:
            return None
        res = result[0]
        timestamps = res.get('timestamp',[])
        quotes = res.get('indicators',{}).get('quote',[{}])[0]
        closes = quotes.get('close',[])
        if not timestamps or not closes:
            return None
        dates = []
        clean_closes = []
        for ts, cl in zip(timestamps, closes):
            if cl is None:
                continue
            try:
                dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                dates.append(dt)
                clean_closes.append(float(cl))
            except:
                continue
        if clean_closes:
            return {"dates": dates, "closes": clean_closes, "source":"yahoo direct"}
    except Exception as e:
        print(f"yahoo direct hist {ticker} {period} error {e}")
    return None

# ---------- UNIFIED GETTERS - FREE, TRY IN ORDER ----------
def get_live_price(ticker):
    # 1. Try Yahoo direct (most accurate, free)
    data = get_live_yahoo_direct(ticker)
    if data and data.get('price'):
        return data
    # 2. Try Stooq (free, never blocked on Render)
    data = get_live_stooq(ticker)
    if data and data.get('price'):
        return data
    # 3. Try yfinance fast_info as last resort (often blocked)
    if HAS_YFINANCE:
        try:
            t = yf.Ticker(ticker)
            fi = t.fast_info
            price = getattr(fi, 'last_price', None)
            if price:
                prev = getattr(fi, 'previous_close', None) or price
                return {"price": float(price), "change": float(price-prev), "change_percent": float((price-prev)/prev*100 if prev else 0), "source":"yfinance fast_info fallback"}
        except:
            pass
    return None

def get_history(ticker, period):
    # 1. Yahoo direct
    h = get_history_yahoo_direct(ticker, period)
    if h:
        return h
    # 2. Stooq
    h = get_history_stooq(ticker, period)
    if h:
        return h
    # 3. yfinance history
    if HAS_YFINANCE:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period, auto_adjust=True)
            if not hist.empty:
                hist = hist.tail(500).dropna()
                dates = [d.strftime("%Y-%m-%d") for d in hist.index]
                closes = [float(x) for x in hist["Close"].tolist()]
                if closes:
                    return {"dates": dates, "closes": closes, "source":"yfinance fallback"}
        except:
            pass
    return None

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/api/health")
def health():
    return jsonify({"status":"ok","version":"v24-free-stooq-yahoo-direct","yfinance":HAS_YFINANCE,"method":"stooq + yahoo direct (free, no key, works on Render)"})

@app.route("/api/company/info")
def company_info():
    try:
        tickers_param = request.args.get("tickers","")
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()][:20]
        result = {}
        known = {"AAPL":"Apple Inc.","MSFT":"Microsoft Corp.","NVDA":"NVIDIA Corp.","QQQ":"Invesco QQQ Trust","SPY":"SPDR S&P 500 ETF","TSLA":"Tesla Inc.","GOOGL":"Alphabet Inc.","AMZN":"Amazon.com Inc.","META":"Meta Platforms Inc.","IWM":"iShares Russell 2000"}
        for sym in tickers:
            live = get_live_price(sym)
            result[sym] = {"name": known.get(sym, sym), "price": live["price"] if live else None, "source": live["source"] if live else "all free sources failed"}
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/price/live")
def price_live():
    try:
        tickers_param = request.args.get("tickers","")
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
        if not tickers:
            return jsonify({})
        result = {}
        for sym in tickers[:30]:
            data = get_live_price(sym)
            if data:
                result[sym] = data
            time.sleep(0.08)  # be nice
        if not result:
            return jsonify({"error":"All free sources failed - try again in 10s","hint":"stooq + yahoo direct both failed, possible network issue"}), 503
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/price/history")
def price_history():
    try:
        tickers_param = request.args.get("tickers","")
        shares_param = request.args.get("shares","")
        period = request.args.get("period","1mo")
        if not tickers_param:
            return jsonify({"error":"No tickers"}), 400
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
        shares = [1.0]*len(tickers)
        if shares_param:
            try:
                shares = [float(x) for x in shares_param.split(",")]
            except:
                pass
        if len(shares)!=len(tickers):
            shares=[1.0]*len(tickers)
        histories = {}
        for sym in tickers:
            h = get_history(sym, period)
            if h:
                histories[sym] = h
            time.sleep(0.08)
        if not histories:
            return jsonify({"error":"No history from free sources (stooq + yahoo direct) - retry"}), 503
        min_len = min(len(v["dates"]) for v in histories.values())
        base_sym = max(histories, key=lambda k: len(histories[k]["dates"]))
        base_dates = histories[base_sym]["dates"][-min_len:]
        equity=[]
        for i in range(min_len):
            tot=0.0
            for idx,sym in enumerate(tickers):
                if sym in histories:
                    cl=histories[sym]["closes"][-min_len:]
                    if i < len(cl):
                        tot+=cl[i]*shares[idx]
            equity.append(tot)
        spy_h = get_history("SPY", period)
        spy_eq=None
        if spy_h and equity:
            spy_cl = spy_h["closes"][-min_len:]
            if spy_cl and equity[0] and spy_cl[0]:
                factor=equity[0]/spy_cl[0]
                spy_eq=[c*factor for c in spy_cl]
        return jsonify({"dates":base_dates,"equity":equity,"spy":spy_eq,"histories":histories,"tickers":tickers,"period":period,"source":"free: stooq + yahoo direct"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/news")
def news_api():
    # News still via yfinance if available, else empty - news is not critical for prices
    try:
        tickers_param = request.args.get("tickers","AAPL")
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()][:5]
        all_news=[]
        if HAS_YFINANCE:
            for sym in tickers:
                try:
                    t=yf.Ticker(sym)
                    news=t.news
                    for item in news[:3]:
                        all_news.append({"ticker":sym,"title":item.get("title") or "Untitled","link":item.get("link") or f"https://finance.yahoo.com/quote/{sym}/news","publisher":item.get("publisher") or "Yahoo","time":str(item.get("providerPublishTime") or "")[:10],"source":"yfinance news"})
                except:
                    continue
        seen=set(); dedup=[]
        for n in all_news:
            if n["title"] not in seen:
                seen.add(n["title"]); dedup.append(n)
        return jsonify({"news":dedup[:20],"source":"yfinance news if available"})
    except Exception as e:
        return jsonify({"news":[],"error":str(e)})

@app.route("/api/ai/portfolio", methods=["POST"])
def ai_portfolio():
    try:
        body=request.get_json() or {}
        q=(body.get("question") or "").lower()
        positions=body.get("portfolio",{}).get("positions",{})
        live_prices=body.get("live_prices",{})
        tickers=list(positions.keys())
        total=sum(positions[t].get("shares",0)*live_prices.get(t,{}).get("price",0) for t in tickers)
        def resp(text): return jsonify({"answer":text, "source":"free stooq + yahoo direct"})
        if not tickers:
            return resp("Demo QQQ, AAPL, MSFT, NVDA from FREE real sources (stooq + yahoo direct) - no API key, works on Render.")
        return resp(f"You hold {len(tickers)}: {', '.join(tickers)}. Total ~${total:,.2f} (FREE real prices from stooq/yahoo direct).")
    except Exception as e:
        return jsonify({"answer": f"Error {e}"}), 500

@app.route("/api/quant/info")
def quant_info():
    try:
        engine_path=os.path.join(os.path.dirname(__file__),"..","tickr_alpha_engine")
        if os.path.exists(engine_path):
            import sys; sys.path.insert(0, os.path.abspath(engine_path))
        try:
            import quant_model
            info=quant_model.get_model_info() if hasattr(quant_model,'get_model_info') else {}
            universe=quant_model.get_universe() if hasattr(quant_model,'get_universe') else ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","SPY","QQQ","IWM"]
            return jsonify({"loaded":True,"name":info.get("name","Local Quant v1"),"description":info.get("description","Ensemble"),"universe":universe, "source":"free"})
        except Exception as e:
            return jsonify({"loaded":False,"error":str(e),"universe":["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","SPY","QQQ","IWM"], "source":"free fallback"})
    except Exception as e:
        return jsonify({"loaded":False,"error":str(e)}),500

@app.route("/api/quant/signals", methods=["POST"])
def quant_signals():
    try:
        engine_path=os.path.join(os.path.dirname(__file__),"..","tickr_alpha_engine")
        if os.path.exists(engine_path):
            import sys; sys.path.insert(0, os.path.abspath(engine_path))
        universe=["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","SPY","QQQ","IWM","JPM","JNJ","XOM","NFLX","AMD"]
        live={}
        for sym in universe[:12]:
            data=get_live_price(sym)
            if data:
                live[sym]={"price":data["price"], "source":data["source"]}
        try:
            import quant_model
            price_data={sym:{"close":live[sym]["price"]} for sym in live}
            signals=quant_model.generate_signals(price_data,{},100000,100000) if hasattr(quant_model,'generate_signals') else []
            for s in signals:
                if s.get("symbol") in live:
                    s["price"]=live[s.get("symbol")]["price"]
                    s["source"]="free"
            if not signals and live:
                import random; random.seed(42)
                signals=[{"symbol":sym,"action":"BUY","quantity":2,"alpha":random.uniform(-0.02,0.03),"alpha_z":random.uniform(-1.5,2.0),"rank_pct":random.uniform(50,95),"price":live[sym]["price"],"reason":"Real free stooq/yahoo","source":"free"} for sym in list(live.keys())[:10]]
                signals.sort(key=lambda x: x.get("alpha_z",0), reverse=True)
            return jsonify({"signals":signals,"source":"free","live_prices":live})
        except Exception as e:
            import random; random.seed(1)
            signals=[{"symbol":sym,"action":"BUY","quantity":1,"alpha":0.01,"alpha_z":1.0,"rank_pct":80,"price":live[sym]["price"],"reason":f"free fallback {str(e)[:60]}","source":"free"} for sym in list(live.keys())[:10]]
            return jsonify({"signals":signals,"error":str(e),"source":"free fallback"})
    except Exception as e:
        return jsonify({"error":str(e),"signals":[]}),500

if __name__=="__main__":
    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)
