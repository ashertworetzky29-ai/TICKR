
"""
TICKR v35 - PORTFOLIO ONLY - NO QUANT - NO PAPER
Prices: Stooq + Yahoo direct + yfinance fallback
News: Guaranteed working Yahoo Finance links even when Render IP blocked - never Untitled
"""
import os, traceback, time, csv, io, re
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

try:
    from curl_cffi import requests as cffi_requests
    session = cffi_requests.Session(impersonate="chrome")
except:
    import requests as req
    session = req.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

try:
    import yfinance as yf
    HAS_YFINANCE = True
except:
    HAS_YFINANCE = False

def stooq_symbol(ticker):
    t = ticker.lower().strip()
    if "." not in t: t = t + ".us"
    return t

def get_live_stooq(ticker):
    try:
        sym = stooq_symbol(ticker)
        url = f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv"
        r = session.get(url, timeout=10)
        if not r.ok: return None
        reader = csv.DictReader(io.StringIO(r.text))
        for row in reader:
            try:
                close = float(row.get('Close') or 0)
                if close <= 0: continue
                open_p = float(row.get('Open') or close)
                return {"price": close, "change": close-open_p, "change_percent": (close-open_p)/open_p*100 if open_p else 0, "source":"stooq"}
            except: continue
    except: pass
    return None

def get_history_stooq(ticker, period="1mo"):
    try:
        sym = stooq_symbol(ticker)
        url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
        r = session.get(url, timeout=12)
        if not r.ok: return None
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        if not rows: return None
        need = {"5d":5,"1mo":22,"3mo":66,"6mo":132,"1y":252,"ytd":300,"max":5000}.get(period,22)
        tail = rows[-need:]
        dates=[]; closes=[]
        for row in tail:
            try:
                d=row.get('Date'); c=float(row.get('Close'))
                if c and d: dates.append(d); closes.append(c)
            except: continue
        if closes: return {"dates":dates,"closes":closes,"source":"stooq"}
    except: pass
    return None

def get_live_yahoo_direct(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
        r = session.get(url, timeout=10)
        if not r.ok: return None
        j=r.json(); result=j.get('chart',{}).get('result')
        if not result: return None
        meta=result[0].get('meta',{})
        price=meta.get('regularMarketPrice'); prev=meta.get('previousClose') or meta.get('chartPreviousClose')
        if not price:
            quotes=result[0].get('indicators',{}).get('quote',[{}])[0]
            closes=[c for c in (quotes.get('close',[]) or []) if c is not None]
            if closes: price=closes[-1]; prev=closes[-2] if len(closes)>1 else price
        if price: return {"price":float(price),"change":float(price-prev) if prev else 0,"change_percent":float((price-prev)/prev*100) if prev else 0,"source":"yahoo direct"}
    except: pass
    return None

def get_history_yahoo_direct(ticker, period="1mo"):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={period}"
        resp=session.get(url, timeout=12)
        if not resp.ok: return None
        j=resp.json(); result=j.get('chart',{}).get('result')
        if not result: return None
        res=result[0]; quotes=res.get('indicators',{}).get('quote',[{}])[0]; closes=quotes.get('close',[]); timestamps=res.get('timestamp',[])
        if not closes or not timestamps: return None
        filtered=[]
        for i,c in enumerate(closes):
            if c is not None:
                try: dt=datetime.utcfromtimestamp(timestamps[i]).strftime('%Y-%m-%d')
                except: dt=str(i)
                filtered.append((dt,c))
        if not filtered: return None
        dates=[x[0] for x in filtered]; closes_v=[x[1] for x in filtered]
        return {"dates":dates,"closes":closes_v,"source":"yahoo direct"}
    except: return None

def get_live_yfinance(ticker):
    if not HAS_YFINANCE: return None
    try:
        tk=yf.Ticker(ticker); hist=tk.history(period="2d")
        if len(hist)>=1:
            price=float(hist['Close'].iloc[-1]); prev=float(hist['Close'].iloc[-2]) if len(hist)>=2 else price
            return {"price":price,"change":price-prev,"change_percent":(price-prev)/prev*100 if prev else 0,"source":"yfinance"}
    except: pass
    return None

def get_live_price(ticker):
    for fn in [get_live_yahoo_direct, get_live_stooq, get_live_yfinance]:
        d=fn(ticker)
        if d and d.get('price'): return d
    return None

def get_history(ticker, period="1mo"):
    for fn in [get_history_yahoo_direct, get_history_stooq]:
        d=fn(ticker, period)
        if d and d.get('closes'): return d
    if HAS_YFINANCE:
        try:
            tk=yf.Ticker(ticker); hist=tk.history(period=period if period in ["5d","1mo","3mo","6mo","1y","ytd","max"] else "1mo")
            if not hist.empty:
                dates=[str(i.date()) for i in hist.index]; closes=[float(c) for c in hist['Close'].tolist()]
                return {"dates":dates,"closes":closes,"source":"yfinance"}
        except: pass
    return None

@app.route("/")
def root():
    # Serve the website, not JSON
    try:
        return app.send_static_file("index.html")
    except:
        from flask import send_from_directory
        return send_from_directory(".", "index.html")

@app.route("/health")
def health(): return jsonify({"status":"TICKR v35 portfolio only - no quant","version":"v35"})

@app.route("/api/price/live")
def price_live():
    try:
        tickers=[t.strip().upper() for t in request.args.get("tickers","AAPL,MSFT,NVDA").split(",") if t.strip()][:20]
        out={}
        for t in tickers:
            d=get_live_price(t)
            if d: out[t]=d
            time.sleep(0.06)
        return jsonify(out)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/price/history")
def price_history():
    try:
        tickers=[t.strip().upper() for t in request.args.get("tickers","AAPL").split(",") if t.strip()]
        shares=[float(s) for s in request.args.get("shares","1").split(",") if s.strip()]
        period=request.args.get("period","1mo")
        if len(shares) < len(tickers): shares=shares+[1.0]*(len(tickers)-len(shares))
        all_hist={}
        for t in tickers:
            h=get_history(t, period)
            if h: all_hist[t]=h
            time.sleep(0.06)
        if not all_hist: return jsonify({"error":"No history"}),404
        base_dates=None
        for t in tickers:
            if t in all_hist and (base_dates is None or len(all_hist[t]['dates']) > len(base_dates)): base_dates=all_hist[t]['dates']
        if not base_dates: return jsonify({"error":"No dates"}),404
        equity=[]
        for idx in range(len(base_dates)):
            total=0
            for i,t in enumerate(tickers):
                if t not in all_hist: continue
                h=all_hist[t]
                c=h['closes'][idx] if idx < len(h['closes']) else h['closes'][-1]
                total+=c*shares[i]
            equity.append(total)
        spy_hist=get_history("SPY", period)
        spy=None
        if spy_hist:
            spy=spy_hist['closes']
            if len(spy) < len(base_dates): spy=spy+[spy[-1]]*(len(base_dates)-len(spy))
            else: spy=spy[:len(base_dates)]
        return jsonify({"dates":base_dates,"equity":equity,"spy":spy,"tickers":tickers})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e)}),500

@app.route("/api/company/info")
def company_info():
    try:
        tickers=[t.strip().upper() for t in request.args.get("tickers","AAPL").split(",") if t.strip()][:15]
        out={}
        if HAS_YFINANCE:
            for t in tickers:
                try:
                    tk=yf.Ticker(t); info=tk.info if hasattr(tk,'info') else {}; name=info.get('longName') or info.get('shortName') or t
                    out[t]={"name":name}
                except: out[t]={"name":t}
                time.sleep(0.05)
        else:
            for t in tickers: out[t]={"name":t}
        return jsonify(out)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/news")
def news_api():
    try:
        tickers=[t.strip().upper() for t in request.args.get("tickers","AAPL,MSFT,NVDA,QQQ").split(",") if t.strip()][:8]
        all_news=[]
        for sym in tickers:
            try:
                url=f"https://query2.finance.yahoo.com/v1/finance/search?q={sym}&newsCount=6"
                r=session.get(url, timeout=8)
                if r.ok:
                    j=r.json()
                    for item in j.get('news', [])[:3]:
                        title=(item.get('title') or '').strip(); link=(item.get('link') or '').strip()
                        if not title or len(title) < 10 or title.lower() == 'untitled': continue
                        if not link or 'yahoo.com' not in link: continue
                        if link.startswith('http://'): link=link.replace('http://','https://')
                        all_news.append({"ticker":sym,"title":title,"link":link,"publisher":item.get('publisher') or 'Yahoo Finance',"source":"yahoo live"})
            except: pass
            time.sleep(0.05)
        for sym in tickers[:5]:
            try:
                rss_url=f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
                r=session.get(rss_url, timeout=8)
                if r.ok and '<item>' in r.text:
                    items=re.findall(r'<item>(.*?)</item>', r.text, re.DOTALL)[:4]
                    for it in items:
                        tm=re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>', it); lm=re.search(r'<link>(.*?)</link>', it)
                        title=(tm.group(1) or tm.group(2) or '').strip() if tm else ''; link=(lm.group(1) or '').strip() if lm else ''
                        if not title or len(title) < 15: continue
                        if not link or 'yahoo.com' not in link: continue
                        if any(n['title']==title for n in all_news): continue
                        if link.startswith('http://'): link=link.replace('http://','https://')
                        all_news.append({"ticker":sym,"title":title,"link":link,"publisher":"Yahoo Finance","source":"yahoo rss"})
            except: pass
        if len(all_news) < 10 and HAS_YFINANCE:
            for sym in tickers[:4]:
                try:
                    tk=yf.Ticker(sym); news=getattr(tk,'news',[]) or []
                    for item in news[:3]:
                        if not isinstance(item, dict): continue
                        content=item.get('content',item); title=(content.get('title') or item.get('title') or '').strip()
                        if not title or title.lower()=='untitled' or len(title) < 10: continue
                        link=None
                        if isinstance(content.get('canonicalUrl'), dict): link=content['canonicalUrl'].get('url')
                        if not link and isinstance(content.get('clickThroughUrl'), dict): link=content['clickThroughUrl'].get('url')
                        if not link: link=item.get('link')
                        if not link or 'yahoo.com' not in link: continue
                        if any(n['title']==title for n in all_news): continue
                        if link.startswith('http://'): link=link.replace('http://','https://')
                        all_news.append({"ticker":sym,"title":title,"link":link,"publisher":"Yahoo Finance","source":"yfinance"})
                except: pass
        for sym in tickers:
            cnt=len([n for n in all_news if n['ticker']==sym])
            if cnt < 2: all_news.append({"ticker":sym,"title":f"{sym} — Latest news & earnings on Yahoo Finance","link":f"https://finance.yahoo.com/quote/{sym}/news/","publisher":"Yahoo Finance","source":"guaranteed working"})
            if cnt == 0: all_news.append({"ticker":sym,"title":f"{sym} — Stock price, chart & press releases","link":f"https://finance.yahoo.com/quote/{sym}/","publisher":"Yahoo Finance","source":"guaranteed working"})
        seen=set(); dedup=[]
        arts=[n for n in all_news if n['source'] != 'guaranteed working']; feeds=[n for n in all_news if n['source'] == 'guaranteed working']
        for n in arts+feeds:
            t=n.get('title','').strip()
            if not t or t.lower()=='untitled' or t in seen: continue
            seen.add(t)
            if 'yahoo.com' not in n.get('link',''): n['link']=f"https://finance.yahoo.com/quote/{n.get('ticker','')}/news/"
            if n['link'].startswith('http://'): n['link']=n['link'].replace('http://','https://')
            dedup.append(n)
        return jsonify({"news":dedup[:24],"count":len(dedup),"tickers":tickers,"source":"v35 working yahoo links - no Untitled"})
    except Exception as e:
        traceback.print_exc()
        tickers=["AAPL","MSFT","NVDA"]
        fallback=[{"ticker":t,"title":f"{t} — News on Yahoo Finance","link":f"https://finance.yahoo.com/quote/{t}/news/","publisher":"Yahoo Finance","source":"fallback working"} for t in tickers]
        return jsonify({"news":fallback,"count":len(fallback),"source":"fallback working"}),200

if __name__=="__main__":
    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)
