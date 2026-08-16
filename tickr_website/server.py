"""
TICKR v14 Server - Portfolio Mode - NO HALLUCINATION
All prices from yfinance only
"""
import os, traceback
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

try:
    import yfinance as yf
    HAS_YFINANCE = True
except Exception as e:
    HAS_YFINANCE = False
    print(f"yfinance missing: {e}")

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/quant")
def quant_page():
    return send_from_directory(".", "index.html")

@app.route("/api/health")
def health():
    return jsonify({"status":"ok","yfinance":HAS_YFINANCE,"version":"v14"})

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
        histories = {}
        min_len = None
        for sym in tickers:
            d = get_hist(sym, period)
            if d:
                histories[sym] = d
                if min_len is None or len(d["dates"]) < min_len:
                    min_len = len(d["dates"])
        if not histories:
            return jsonify({"error":"No data"}), 404
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
        spy = get_hist("SPY", period)
        spy_eq = None
        if spy and equity and spy["closes"]:
            spy_cl = spy["closes"][-min_len:]
            if equity[0] and spy_cl[0]:
                factor = equity[0]/spy_cl[0]
                spy_eq = [c*factor for c in spy_cl]
        return jsonify({"dates": base_dates, "equity": equity, "spy": spy_eq, "histories": histories, "tickers": tickers, "period": period, "source":"yfinance"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/price/live")
def price_live():
    try:
        tickers_param = request.args.get("tickers", "")
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
        result = {}
        if HAS_YFINANCE:
            for sym in tickers:
                try:
                    t = yf.Ticker(sym)
                    hist = t.history(period="2d", auto_adjust=True)
                    if not hist.empty:
                        last = float(hist["Close"].iloc[-1])
                        prev = float(hist["Close"].iloc[-2]) if len(hist)>1 else last
                        result[sym] = {"price": last, "change": last-prev, "change_percent": ((last-prev)/prev*100) if prev else 0, "source":"yfinance"}
                except Exception as e:
                    result[sym] = {"error": str(e)}
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/news")
def news_api():
    try:
        tickers_param = request.args.get("tickers", "AAPL")
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()][:10]
        all_news = []
        if HAS_YFINANCE:
            for sym in tickers:
                try:
                    t = yf.Ticker(sym)
                    news = t.news
                    for item in news[:5]:
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
        seen=set()
        dedup=[]
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
        watchlist = body.get("watchlist", [])
        live_prices = body.get("live_prices", {})
        tickers = list(positions.keys())
        total = 0
        SECTOR_MAP = {"AAPL":"Technology","MSFT":"Technology","NVDA":"Technology","GOOGL":"Technology","META":"Technology","TSLA":"Consumer Cyclical","AMZN":"Consumer Cyclical","SPY":"ETF","QQQ":"ETF","JPM":"Financial","XOM":"Energy","JNJ":"Healthcare"}
        sector_counts={}
        for t in tickers:
            sec=SECTOR_MAP.get(t,"Other")
            sector_counts[sec]=sector_counts.get(sec,0)+1
        most=None
        if positions and live_prices:
            vals=[]
            for t,pos in positions.items():
                shares=pos.get("shares",0)
                price=live_prices.get(t,{}).get("price",0)
                val=shares*price
                vals.append((t,val))
                total+=val
            if vals:
                vals.sort(key=lambda x:x[1], reverse=True)
                most=vals[0]
        def resp(text):
            return jsonify({"answer": text, "source":"rule-based"})
        if not tickers and any(k in q for k in ["diversif","risk","summarize","sector"]):
            return resp("Portfolio empty. Add stocks on left panel to analyze.")
        if any(k in q for k in ["diversif","spread","concentrated"]):
            tech=sector_counts.get("Technology",0)/len(tickers)*100 if tickers else 0
            if tech>60:
                return resp(f"Youre {tech:.0f}% Tech. High concentration. Consider XLF, XLV, XLE, or JNJ, JPM. Diversification {max(0,100-int(tech))}/100.")
            return resp(f"You have {len(sector_counts)} sectors: {', '.join([f'{k} {v}' for k,v in sector_counts.items()])}. Score {85-int(tech/3)}/100.")
        if any(k in q for k in ["risk","riskiest","volatile"]):
            if most:
                return resp(f"Riskiest: {most[0]} ${most[1]:,.2f} ({most[1]/total*100 if total else 0:.1f}%). If drops 10%, lose ${most[1]*0.1:,.2f}. Trim if >25%.")
            return resp("Add positions to analyze risk.")
        if any(k in q for k in ["beat spy","vs spy","outperform"]):
            return resp("Check chart vs SPY. If equity above SPY normalized, outperforming.")
        if any(k in q for k in ["sector"]):
            return resp(f"Sector: {', '.join([f'{k}:{v}' for k,v in sector_counts.items()])}." if sector_counts else "No sectors yet.")
        if any(k in q for k in ["summarize","summary","overview"]):
            summary=f"You hold {len(tickers)}: {', '.join(tickers)}. Total ~${total:,.2f} (yfinance). "
            if most:
                summary+=f"Largest {most[0]} {most[1]/total*100 if total else 0:.1f}%. "
            return resp(summary)
        if any(k in q for k in ["hello","hi","help"]):
            return resp("Hi! Try: How can I diversify? Whats riskiest? Am I beating SPY? Summarize.")
        return resp(f"Analyzed {len(tickers)} positions. Total ~${total:,.2f}. Try: How can I diversify?")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"answer": f"Error {e}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
