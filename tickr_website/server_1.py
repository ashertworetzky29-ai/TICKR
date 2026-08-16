
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import yfinance as yf
from datetime import datetime
import uuid
import traceback
import re
import sys
# Add alpha engine to path for quant integration
ALPHA_ENGINE_PATH = os.path.join(os.path.dirname(__file__), '..', 'tickr_alpha_engine')
if ALPHA_ENGINE_PATH not in sys.path:
    sys.path.insert(0, ALPHA_ENGINE_PATH)

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

USERS = {}
TOKENS = {}
PORTFOLIOS = {}
PAPER_PORTFOLIOS = {}  # paper trading per user

def fetch_quote_data(symbol):
    try:
        t = yf.Ticker(symbol)
        h = None
        try:
            h = t.history(period='3mo')
        except:
            h = None
        if h is None or getattr(h, 'empty', True):
            try:
                h = t.history(period='1mo')
            except:
                pass
        if h is None or getattr(h, 'empty', True):
            return None
        try:
            price = float(h['Close'].iloc[-1])
            prev = float(h['Close'].iloc[-2]) if len(h) > 1 else price
            pct = ((price - prev) / prev * 100) if prev else 0
        except:
            return None
        info = {}
        try:
            info = t.info or {}
        except:
            info = {}
        try:
            history_list = [float(x) for x in h['Close'].tolist()[-90:]]
        except:
            history_list = [price]
        return {
            "symbol": symbol.upper(),
            "price": price,
            "changePct": pct,
            "name": (info.get('shortName') or info.get('longName') or symbol.upper()),
            "history": history_list,
            "sector": info.get('sector') or 'Unknown',
            "industry": info.get('industry') or 'Unknown',
            "dividendYield": info.get('dividendYield') or info.get('trailingAnnualDividendYield') or 0,
            "quoteType": info.get('quoteType') or 'EQUITY',
            "marketCap": info.get('marketCap') or 0,
            "pe": info.get('trailingPE') or info.get('forwardPE') or 0,
        }
    except Exception as e:
        print(f"quote error {symbol}: {e}")
        return None

def parse_news_item(item):
    try:
        if not isinstance(item, dict):
            return None
        title = None
        link = None
        pub_time = None
        publisher = None
        if 'content' in item and isinstance(item['content'], dict):
            content = item['content']
            title = content.get('title')
            ct = content.get('clickThroughUrl')
            if ct and isinstance(ct, dict):
                link = ct.get('url')
            if not link:
                can = content.get('canonicalUrl')
                if can and isinstance(can, dict):
                    link = can.get('url')
            if not link:
                link = content.get('link') or content.get('url')
            pub_time = content.get('pubDate') or content.get('displayTime')
            provider = content.get('provider')
            if provider and isinstance(provider, dict):
                publisher = provider.get('displayName')
        else:
            title = item.get('title')
            link = item.get('link') or item.get('url')
            pub_time = item.get('providerPublishTime') or item.get('pubDate')
            publisher = item.get('publisher')
        if not title or not link:
            return None
        if not isinstance(link, str) or not link.startswith('http'):
            return None
        if link.rstrip('/').endswith('yahoo.com') or link.rstrip('/') == 'https://finance.yahoo.com/news':
            return None
        if len(link) < 25:
            return None
        return {"title": title, "link": link, "time": pub_time, "publisher": publisher or "Yahoo Finance"}
    except:
        return None

@app.route('/api/health')
def health():
    return jsonify({"ok": True, "service": "tickr v13 conversational", "time": datetime.now().isoformat()})

@app.route('/api/quote/<symbol>')
def quote(symbol):
    try:
        d = fetch_quote_data(symbol)
        if not d:
            return jsonify({"error": "not found"}), 404
        return jsonify(d)
    except Exception as e:
        print(f"quote {symbol} error {e}")
        return jsonify({"error": "internal"}), 500

@app.route('/api/quotes')
def quotes():
    try:
        syms = [s.strip().upper() for s in request.args.get('symbols','').split(',') if s.strip()][:20]
        out = {}
        for sym in syms:
            try:
                d = fetch_quote_data(sym)
                if d:
                    out[sym] = d
            except:
                continue
        return jsonify(out)
    except:
        return jsonify({}), 200

@app.route('/api/earnings')
def earnings():
    try:
        syms = [s.strip().upper() for s in request.args.get('symbols','').split(',') if s.strip()][:10]
        earnings_list = []
        today = datetime.now()
        for sym in syms:
            try:
                t = yf.Ticker(sym)
                ed = None
                try:
                    ed = t.earnings_dates
                except:
                    ed = None
                if ed is not None and not ed.empty:
                    for idx in ed.index[:4]:
                        try:
                            dt = idx.to_pydatetime()
                            delta = (dt - today).days
                            if -7 <= delta <= 30:
                                earnings_list.append({"symbol": sym, "date": dt.isoformat(), "daysUntil": delta, "time": "Before Open"})
                        except:
                            continue
            except:
                continue
        earnings_list.sort(key=lambda x: x['date'])
        return jsonify({"earnings": earnings_list})
    except:
        return jsonify({"earnings": []}), 200

@app.route('/api/news')
def news():
    try:
        syms = [s.strip().upper() for s in request.args.get('symbols','SPY').split(',') if s.strip()][:8]
        all_news = []
        seen = set()
        for sym in syms:
            try:
                t = yf.Ticker(sym)
                raw_news = getattr(t, 'news', []) or []
                for raw in raw_news[:6]:
                    parsed = parse_news_item(raw)
                    if not parsed:
                        continue
                    if parsed['link'] in seen:
                        continue
                    seen.add(parsed['link'])
                    all_news.append({"symbol": sym, "title": parsed['title'], "link": parsed['link'], "time": parsed['time'], "publisher": parsed['publisher']})
                    if len(all_news) >= 20:
                        break
            except:
                continue
        if not all_news:
            for sym in syms[:4]:
                all_news.append({"symbol": sym, "title": f"{sym} latest news", "link": f"https://finance.yahoo.com/quote/{sym}/news/", "time": datetime.now().isoformat(), "publisher": "Yahoo Finance"})
        return jsonify({"news": all_news[:20]})
    except Exception as e:
        print(f"news error {e}")
        return jsonify({"news": []}), 200

@app.route('/api/auth', methods=['POST'])
@app.route('/api/login', methods=['POST'])
@app.route('/api/register', methods=['POST'])
def auth():
    data = request.get_json() or {}
    u = (data.get('username') or '').strip().lower()
    p = data.get('password') or ''
    if not u or not p:
        return jsonify({"error": "username required"}), 400
    if request.path == '/api/register' and u in USERS:
        return jsonify({"error": "user exists"}), 400
    if u not in USERS:
        USERS[u] = p
        PORTFOLIOS[u] = {"holdings": [{"symbol":"AAPL","quantity":10,"avgCost":175},{"symbol":"JNJ","quantity":5,"avgCost":160},{"symbol":"NEE","quantity":8,"avgCost":70}], "watchlist": ["MSFT","SPY","XLU","VYM","SCHD"]}
    elif USERS[u] != p and request.path != '/api/register':
        return jsonify({"error": "invalid"}), 401
    else:
        USERS[u] = p
    token = str(uuid.uuid4())
    TOKENS[token] = u
    return jsonify({"token": token, "username": u})

@app.route('/api/portfolio', methods=['GET'])
def get_port():
    token = request.headers.get('X-Auth-Token')
    user = TOKENS.get(token)
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(PORTFOLIOS.get(user, {"holdings": [], "watchlist": []}))

@app.route('/api/portfolio', methods=['POST'])
def save_port():
    try:
        data = request.get_json() or {}
        token = data.get('token') or request.headers.get('X-Auth-Token')
        user = TOKENS.get(token)
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        holdings = data.get('holdings', [])
        watchlist = data.get('watchlist', [])
        PORTFOLIOS[user] = {"holdings": holdings, "watchlist": watchlist}
        return jsonify({"ok": True})
    except Exception as e:
        print(f"save error {e}")
        return jsonify({"ok": False}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json() or {}
        prompt = (data.get('prompt') or '').strip()
        lower = prompt.lower()
        holdings = data.get('holdings') or []
        prices = data.get('prices') or {}
        current = data.get('currentSymbol') or 'SPY'

        # Enrich holdings with server-side data if client prices missing or Unknown
        enriched_prices = {}
        enriched_prices.update(prices)  # start with client prices

        total_val = 0
        total_cost = 0
        sectors = {}
        dividend_stocks = []
        gainers = []
        losers = []

        for h in holdings:
            try:
                sym = (h.get('symbol') or '').upper()
                q = enriched_prices.get(sym) or {}
                # If no sector or price, try to fetch server-side
                if not q or q.get('sector') in [None, 'Unknown', ''] or not q.get('price'):
                    fetched = fetch_quote_data(sym)
                    if fetched:
                        enriched_prices[sym] = fetched
                        q = fetched

                qty = float(h.get('quantity') or 0)
                avg = float(h.get('avgCost') or 0)
                price = float(q.get('price') or avg or 0)
                val = qty * price
                cost = qty * avg
                total_val += val
                total_cost += cost
                sector = q.get('sector') or 'Unknown'
                if sector == 'Unknown':
                    # Try to infer from quoteType
                    qt = (q.get('quoteType') or '').upper()
                    if qt == 'ETF':
                        sector = 'ETF'
                sectors[sector] = sectors.get(sector, 0) + val
                dy = q.get('dividendYield') or 0
                if dy > 0.01:
                    dividend_stocks.append((h.get('symbol'), dy, sector, price, qty, val))
                pct = ((price - avg)/avg*100) if avg else 0
                gain = (price - avg) * qty
                if pct > 0.5:
                    gainers.append((h.get('symbol'), pct, gain, price, sector))
                elif pct < -0.5:
                    losers.append((h.get('symbol'), pct, gain, price, sector))
            except Exception as e:
                print(f"enrich error {e}")
                continue

        total_gain = total_val - total_cost
        total_gain_pct = (total_gain/total_cost*100) if total_cost else 0
        top_sector = max(sectors, key=sectors.get) if sectors else None
        top_pct = sectors.get(top_sector, 0)/total_val*100 if total_val and top_sector else 0

        # Diversification helpers
        ALL_SECTORS = {
            'Technology': ['MSFT', 'AAPL', 'GOOGL', 'NVDA', 'AVGO'],
            'Healthcare': ['JNJ', 'UNH', 'ABBV', 'LLY', 'PFE'],
            'Financial Services': ['JPM', 'BRK.B', 'V', 'BAC', 'GS'],
            'Consumer Defensive': ['PG', 'KO', 'COST', 'WMT', 'PEP'],
            'Consumer Cyclical': ['AMZN', 'TSLA', 'HD', 'NKE', 'MCD'],
            'Utilities': ['NEE', 'DUK', 'SO', 'D', 'XEL'],
            'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG'],
            'Industrials': ['CAT', 'HON', 'UPS', 'BA', 'GE'],
            'Communication Services': ['META', 'GOOGL', 'NFLX', 'DIS', 'TMUS'],
            'Real Estate': ['VNQ', 'PLD', 'AMT', 'CCI', 'EQIX'],
            'Basic Materials': ['LIN', 'APD', 'SHW', 'NEM', 'FCX'],
            'ETF': ['VTI', 'VOO', 'QQQ', 'VYM', 'SCHD', 'XLU', 'XLF', 'XLV']
        }

        def get_diversification_suggestions():
            present = set(sectors.keys())
            # Remove Unknown and ETF from missing check, but consider them
            missing = [s for s in ALL_SECTORS.keys() if s not in present and s != 'Unknown']
            # Prioritize sectors that balance portfolio
            suggestions = []
            # If heavily concentrated in one sector (>40%), suggest others
            if top_pct > 40 and top_sector:
                # Suggest 3 sectors not top
                candidates = [s for s in missing if s != top_sector][:4]
                if len(candidates) < 3:
                    candidates += [s for s in ALL_SECTORS.keys() if s != top_sector and s not in candidates][:3]
                for sec in candidates[:3]:
                    tickers = ALL_SECTORS[sec][:2]
                    suggestions.append((sec, tickers))
            else:
                # Suggest missing sectors
                for sec in missing[:4]:
                    tickers = ALL_SECTORS[sec][:2]
                    suggestions.append((sec, tickers))
            if not suggestions:
                # If diversified, suggest broad ETFs
                suggestions = [('ETF', ['VTI', 'VXUS']), ('Consumer Defensive', ['PG', 'KO']), ('Healthcare', ['JNJ', 'UNH'])]
            return suggestions

        # 1. Greetings - conversational, not generic
        if re.match(r'^(yoo?|hey|hi|hello|sup|whats up|what\'s up|howdy|yo whats up|yoo whats up)\b', lower) or lower in ['yo', 'hey', 'hi', 'hello', 'sup']:
            greeting_responses = [
                f"Hey! What's up. You have {len(holdings)} holdings right now totaling about ${total_val:.0f} — you're {'up' if total_gain_pct>0 else 'down' if total_gain_pct<0 else 'about flat'} {abs(total_gain_pct):.1f}% overall. What do you want to talk about?",
                f"Hey there — good to see you. Portfolio check: {len(holdings)} positions, about ${total_val:.0f} total. How are you feeling about things lately?",
                f"What's up! I've got your portfolio pulled up — {len(holdings)} holdings, largest is {top_sector or 'a mix'} at {top_pct:.0f}%. Want to dive into something specific or just chat about the market?"
            ]
            import random
            return jsonify({"response": greeting_responses[0] if len(greeting_responses)==1 else __import__('random').choice(greeting_responses)})

        if any(p in lower for p in ['how are you', 'how r you']):
            return jsonify({"response": f"I'm doing well, thanks. I've been looking at your {len(holdings)} holdings — you're at about ${total_val:.0f} total, {total_gain_pct:+.1f}% overall. The largest piece is {top_sector or 'spread across sectors'} at {top_pct:.0f}%. How are you feeling about your allocation?"})

        if any(p in lower for p in ['who are you', 'what are you', 'what can you do', 'what do you do']):
            return jsonify({"response": f"I'm Tickr AI — I live inside your Tickr portfolio. I can see your actual holdings, live prices, and allocation, so I don't just give generic advice.\n\nI can help you:\n• Understand your sector mix and diversification\n• Break down dividend income, winners and losers\n• Talk through any ticker you're curious about with real data\n• Discuss market conditions and how your portfolio lines up\n• Help you edit holdings — just say 'delete AAPL' or 'edit AAPL to 15 shares'\n\nWhat would be most helpful right now?"})

        # 2. Diversification - the main request failing before
        if any(p in lower for p in ['diversify', 'diversification', 'find new stocks', 'find stocks', 'new stocks', 'suggest stocks', 'recommend stocks', 'add stocks', 'broaden', 'more diversified']):
            suggestions = get_diversification_suggestions()
            # Build current allocation text
            if sectors and total_val > 0 and not (len(sectors)==1 and 'Unknown' in sectors):
                current_text = "Here's your current mix:\n" + "\n".join([f"• {sec}: {val/total_val*100:.0f}% (${val:.0f})" for sec, val in sorted(sectors.items(), key=lambda x: x[1], reverse=True)])
            else:
                # If Unknown, try to show holdings list
                current_text = f"You have {len(holdings)} holdings: " + ", ".join([h.get('symbol','') for h in holdings[:6]])
                if len(holdings) > 6:
                    current_text += f" and {len(holdings)-6} more"
                current_text += ".\nI'm still loading sector data for some of them, but I can still help you diversify."

            suggestion_text = "\n\nTo add diversification, here are some areas you're light on:\n"
            for sec, tickers in suggestions:
                if sec == 'Technology':
                    desc = "adds growth exposure — large, profitable tech"
                elif sec == 'Healthcare':
                    desc = "defensive, tends to hold up better in downturns, often pays dividends"
                elif sec == 'Financial Services':
                    desc = "benefits when rates rise, more cyclical"
                elif sec == 'Consumer Defensive':
                    desc = "staples people buy in any economy — lower volatility"
                elif sec == 'Utilities':
                    desc = "very defensive, strong dividends, less tied to market swings"
                elif sec == 'Energy':
                    desc = "different cycle than tech, can hedge inflation"
                elif sec == 'ETF':
                    desc = "instant diversification across many stocks"
                else:
                    desc = "adds exposure outside your current concentration"
                suggestion_text += f"\n• {sec}: {', '.join(tickers)} — {desc}"

            suggestion_text += f"\n\nYou asked about new ideas — are you looking for:\n1. More dividend income?\n2. More defensive / less volatile holdings?\n3. More growth?\n\nTell me which direction and I can narrow this to 2-3 specific tickers with prices."

            return jsonify({"response": current_text + suggestion_text})

        # 3. Market conversation
        if any(p in lower for p in ["how's market", "how is market", "market doing", "market today", "what's happening in the market", "market update"]):
            spy_q = enriched_prices.get('SPY') or {}
            spy_chg = spy_q.get('changePct', 0)
            if spy_chg > 1:
                market_desc = "having a pretty strong day"
            elif spy_chg > 0.2:
                market_desc = "up modestly today"
            elif spy_chg > -0.2:
                market_desc = "about flat today, chopping around"
            elif spy_chg > -1:
                market_desc = "down a bit today"
            else:
                market_desc = "under some pressure today"
            return jsonify({"response": f"The broader market is {market_desc} — SPY is {spy_chg:+.2f}% on the day if you're watching the S&P 500.\n\nYour portfolio is {total_gain_pct:+.1f}% overall, with {top_sector or 'a mix of sectors'} as your largest at {top_pct:.0f}%. You have {len(gainers)} positions up and {len(losers)} down right now.\n\nIs there a particular area you're watching — tech earnings, rates, energy? I can talk through how your current mix lines up with that."})

        # 4. Specific ticker
        single_sym = None
        if len(prompt.strip().split()) == 1 and prompt.strip().isalpha() and 1 <= len(prompt.strip()) <= 5:
            single_sym = prompt.strip().upper()
        else:
            m = re.search(r'(?:about|on|is|for|think.*|thoughts.*|how.*|what.*)\s+([A-Z]{1,5})\b', prompt.upper())
            if m:
                cand = m.group(1)
                if cand not in ['WHAT','ABOUT','THIS','THAT','YOUR','SHOULD','THERE','THEIR','THINK','THOUGHTS','STOCK','MARKET','MONEY','PORTFOLIO','MY','HOW','MUCH']:
                    single_sym = cand

        if single_sym:
            q = enriched_prices.get(single_sym) or fetch_quote_data(single_sym)
            if q:
                price = q.get('price', 0)
                sector = q.get('sector', 'Unknown')
                dy = q.get('dividendYield', 0)
                chg = q.get('changePct', 0)
                name = q.get('name', single_sym)
                pe = q.get('pe', 0)
                holding = next((h for h in holdings if h.get('symbol','').upper() == single_sym), None)
                if holding:
                    qty = float(holding.get('quantity') or 0)
                    avg = float(holding.get('avgCost') or 0)
                    val = qty * price
                    pct = ((price - avg)/avg*100) if avg else 0
                    return jsonify({"response": f"{single_sym} — {name} — is trading around ${price:.2f}, {chg:+.2f}% today. It's in {sector}{f' with a {dy*100:.1f}% dividend yield' if dy>0.01 else ''}{f' and a P/E around {pe:.1f}' if pe else ''}.\n\nYou own {qty:.0f} shares at an average of ${avg:.2f}, so that position is about ${val:.0f} and you're {pct:+.1f}% on it.\n\nIn your portfolio, {sector} makes up {sectors.get(sector,0)/total_val*100 if total_val else 0:.0f}% of your total. What did you want to think through about it — performance, adding more, or how it compares?"})
                else:
                    return jsonify({"response": f"{single_sym} — {name} — is around ${price:.2f}, {chg:+.2f}% today, in {sector}{f' with a {dy*100:.1f}% dividend yield' if dy>0.01 else ''}.\n\nIt's not in your holdings right now. Adding it would give you more exposure to {sector}. Your portfolio is currently {top_pct:.0f}% {top_sector or 'concentrated'}, so this would {'increase that concentration' if sector==top_sector else 'help diversify into ' + sector}. Are you thinking about it for growth, income, or diversification?"})

        # 5. Dividend
        if 'dividend' in lower:
            if not dividend_stocks:
                return jsonify({"response": f"You don't have any meaningful dividend payers right now — your {len(holdings)} holdings are mostly growth-oriented, totaling about ${total_val:.0f}.\n\nIf income is something you want, a few commonly held examples:\n• JNJ — healthcare, about 3% yield, very stable\n• NEE — utilities, about 3% yield, defensive\n• VYM or SCHD — dividend ETFs that give you a basket of yielders\n\nWould you like me to show you how adding one would change your estimated annual income?"})
            dividend_stocks.sort(key=lambda x: x[1], reverse=True)
            avg_yield = sum(y for _,y,_,_,_,_ in dividend_stocks)/len(dividend_stocks)*100
            lines = [f"• {sym}: {y*100:.1f}% — {sector}, ${p:.0f} x {qty:.0f} = ${val:.0f}" for sym,y,sector,p,qty,val in dividend_stocks]
            total_div_val = sum(val for _,_,_,_,_,val in dividend_stocks)
            return jsonify({"response": f"You have {len(dividend_stocks)} positions paying a dividend, averaging {avg_yield:.1f}% yield. Together they're about ${total_div_val:.0f} of your portfolio.\n\n" + "\n".join(lines) + f"\n\nAt that average, that's roughly ${total_val * (avg_yield/100):.0f} a year in estimated dividend income before taxes. Do you want to lean more into dividend or keep the current mix?"})

        # 6. Sector / tech question
        if any(x in lower for x in ['how much tech', 'tech do i have', 'sector', 'allocation', 'breakdown']):
            if not sectors or (len(sectors)==1 and 'Unknown' in sectors):
                # Try to explain Unknown case
                sym_list = ", ".join([h.get("symbol","") for h in holdings[:5]])
                return jsonify({"response": f"I'm still loading sector data for your holdings — right now I see {len(holdings)} positions: {sym_list}. Let me pull live sector info.\n\nIn the meantime, I can tell you generally: if you're heavy tech, adding healthcare (JNJ, UNH), consumer staples (PG, COST), or utilities (NEE, DUK) tends to reduce volatility. Want me to suggest 2-3 specific tickers once the sector data loads? Try refreshing, or ask 'find new stocks to diversify'."})
            lines = []
            for sec, val in sorted(sectors.items(), key=lambda x: x[1], reverse=True):
                pct = val/total_val*100 if total_val else 0
                lines.append(f"• {sec}: {pct:.0f}% — about ${val:.0f}")
            tech_pct = sum(v for k,v in sectors.items() if 'tech' in k.lower())/total_val*100 if total_val else 0
            extra = ""
            if 'tech' in lower or 'how much tech' in lower:
                extra = f"\n\nTech specifically is about {tech_pct:.0f}% of your portfolio. {'That is quite concentrated — tech can be volatile.' if tech_pct>40 else 'That is a moderate tech allocation.' if tech_pct>20 else 'You are actually light on tech.'}"
            return jsonify({"response": f"Here's your allocation across {len(sectors)} areas, ${total_val:.0f} total:\n\n" + "\n".join(lines) + extra + "\n\nWould you like ideas for balancing it out?"})

        # 7. Performance
        if any(x in lower for x in ['how am i doing', 'how are we doing', 'performance', 'how am i', 'summary']):
            return jsonify({"response": f"Quick summary:\n\nYou have {len(holdings)} holdings totaling about ${total_val:.0f}, with a cost basis around ${total_cost:.0f}. That puts you at {total_gain:+.0f} ({total_gain_pct:+.1f}%) overall.\n\n• Largest sector: {top_sector or 'Mixed'} at {top_pct:.0f}%\n• Winners: {len(gainers)}, Losers: {len(losers)}\n• Dividend payers: {len(dividend_stocks)}\n\nHow are you feeling about that? Want to dig into risk, income, or specific positions?"})

        # 8. Delete
        if any(x in lower for x in ['delete', 'remove']):
            m = re.search(r'\b([A-Z]{1,5})\b', prompt.upper())
            if m:
                sym = m.group(1)
                if sym not in ['DELETE','REMOVE','STOCKS','MY','THIS']:
                    return jsonify({"response": f"You want to remove {sym}? Hover over {sym} in your holdings and click the trash icon, or say 'yes, delete {sym}' and I'll remove it. You have {len(holdings)} holdings right now."})
            return jsonify({"response": "Which holding would you like to remove? Just say 'delete AAPL' and I'll handle it with a confirmation."})

        # 9. Default - truly conversational, not generic
        if len(prompt) < 5:
            return jsonify({"response": f"Could you share a bit more? I can see you have {len(holdings)} holdings totaling ${total_val:.0f}. I can talk about your allocation, any ticker you're curious about, dividend income, or what's happening in the market."})

        # General fallback that is actually helpful and conversational
        return jsonify({"response": f"I hear you — you have {len(holdings)} holdings totaling about ${total_val:.0f}, with {top_sector or 'a mix'} as your largest at {top_pct:.0f}%. You're {total_gain_pct:+.1f}% overall.\n\nFor what you asked — '{prompt}' — here's how I can help:\n• If you're looking for new ideas, say 'find stocks to diversify' and I'll suggest specific sectors and tickers you're light on\n• If it's about a specific company, mention the ticker and I'll pull price, sector, and how it fits\n• If it's about market conditions, ask 'how's the market today?'\n• If you want to understand your mix, ask 'how much tech do I have?' or 'show my dividend stocks'\n\nWhat angle is most useful for you right now?"})

    except Exception as e:
        print(f"chat error {e}")
        traceback.print_exc()
        return jsonify({"response": "I had a brief hiccup pulling your data, but I'm back. What would you like to talk about — your allocation, a specific ticker, or the market more broadly?"}), 200


# ===== PAPER TRADING / QUANT LAB =====

def get_paper_portfolio(user):
    """Get or create paper portfolio for user"""
    if user not in PAPER_PORTFOLIOS:
        PAPER_PORTFOLIOS[user] = {
            "cash": 100000.0,
            "positions": {},  # symbol -> {quantity, avgCost}
            "trades": [],  # list of trades
            "equity_history": [{"date": datetime.now().isoformat(), "equity": 100000.0, "cash": 100000.0}],
            "created_at": datetime.now().isoformat()
        }
    return PAPER_PORTFOLIOS[user]

@app.route('/api/paper/portfolio', methods=['GET'])
def paper_portfolio():
    try:
        token = request.headers.get('X-Auth-Token')
        user = TOKENS.get(token) or 'demo'
        # Allow demo without auth
        paper = get_paper_portfolio(user)
        
        # Calculate current equity with live prices
        total_equity = paper['cash']
        positions_with_pnl = {}
        symbols = list(paper['positions'].keys())
        
        # Fetch live prices for positions
        live_prices = {}
        for sym in symbols[:20]:  # limit
            try:
                q = fetch_quote_data(sym)
                if q:
                    live_prices[sym] = q
            except:
                continue
        
        for sym, pos in paper['positions'].items():
            q = live_prices.get(sym) or {}
            price = q.get('price') or pos.get('avgCost', 0)
            qty = pos.get('quantity', 0)
            avg = pos.get('avgCost', 0)
            market_val = qty * price
            cost = qty * avg
            pnl = market_val - cost
            pnl_pct = (pnl / cost * 100) if cost else 0
            total_equity += market_val
            positions_with_pnl[sym] = {
                "quantity": qty,
                "avgCost": avg,
                "currentPrice": price,
                "marketValue": market_val,
                "pnl": pnl,
                "pnlPct": pnl_pct,
                "sector": q.get('sector') or 'Unknown'
            }
        
        return jsonify({
            "cash": paper['cash'],
            "equity": total_equity,
            "positions": positions_with_pnl,
            "positions_raw": paper['positions'],
            "trades": paper['trades'][-50:],  # last 50
            "equity_history": paper['equity_history'][-100:],
            "total_trades": len(paper['trades']),
            "live_prices": live_prices
        })
    except Exception as e:
        print(f"paper portfolio error {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/paper/trade', methods=['POST'])
def paper_trade():
    try:
        data = request.get_json() or {}
        token = data.get('token') or request.headers.get('X-Auth-Token')
        user = TOKENS.get(token) or 'demo'
        paper = get_paper_portfolio(user)
        
        symbol = (data.get('symbol') or '').strip().upper()
        action = (data.get('action') or 'BUY').upper()
        quantity = float(data.get('quantity') or 0)
        price = data.get('price')  # optional, if not provided fetch live
        
        if not symbol or quantity <= 0:
            return jsonify({"error": "symbol and quantity required"}), 400
        
        # Get live price if not provided
        if not price:
            q = fetch_quote_data(symbol)
            if not q:
                return jsonify({"error": f"Could not fetch price for {symbol}"}), 400
            price = q['price']
        else:
            price = float(price)
        
        cost = quantity * price
        
        if action == 'BUY':
            if paper['cash'] < cost:
                return jsonify({"error": f"Insufficient cash. Need ${cost:.2f}, have ${paper['cash']:.2f}"}), 400
            
            paper['cash'] -= cost
            if symbol in paper['positions']:
                # Average up
                existing = paper['positions'][symbol]
                total_qty = existing['quantity'] + quantity
                total_cost = (existing['quantity'] * existing['avgCost']) + cost
                paper['positions'][symbol] = {
                    "quantity": total_qty,
                    "avgCost": total_cost / total_qty
                }
            else:
                paper['positions'][symbol] = {"quantity": quantity, "avgCost": price}
            
            paper['trades'].append({
                "id": str(uuid.uuid4())[:8],
                "symbol": symbol,
                "action": "BUY",
                "quantity": quantity,
                "price": price,
                "cost": cost,
                "timestamp": datetime.now().isoformat(),
                "reason": data.get('reason') or "Manual buy"
            })
        
        elif action == 'SELL':
            if symbol not in paper['positions']:
                return jsonify({"error": f"No position in {symbol}"}), 400
            
            pos = paper['positions'][symbol]
            if pos['quantity'] < quantity:
                return jsonify({"error": f"Insufficient shares. Have {pos['quantity']}, trying to sell {quantity}"}), 400
            
            paper['cash'] += quantity * price
            pnl = (price - pos['avgCost']) * quantity
            
            if pos['quantity'] == quantity:
                del paper['positions'][symbol]
            else:
                pos['quantity'] -= quantity
            
            paper['trades'].append({
                "id": str(uuid.uuid4())[:8],
                "symbol": symbol,
                "action": "SELL",
                "quantity": quantity,
                "price": price,
                "proceeds": quantity * price,
                "pnl": pnl,
                "timestamp": datetime.now().isoformat(),
                "reason": data.get('reason') or "Manual sell"
            })
        
        else:
            return jsonify({"error": "Action must be BUY or SELL"}), 400
        
        # Update equity history
        total_equity = paper['cash']
        for sym, pos in paper['positions'].items():
            q = fetch_quote_data(sym) if sym == symbol else None
            p = q['price'] if q else price if sym == symbol else pos['avgCost']
            total_equity += pos['quantity'] * p
        
        paper['equity_history'].append({
            "date": datetime.now().isoformat(),
            "equity": total_equity,
            "cash": paper['cash']
        })
        
        # Keep history trimmed
        if len(paper['equity_history']) > 200:
            paper['equity_history'] = paper['equity_history'][-200:]
        
        return jsonify({"ok": True, "cash": paper['cash'], "equity": total_equity, "positions": paper['positions']})
    
    except Exception as e:
        print(f"paper trade error {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/paper/reset', methods=['POST'])
def paper_reset():
    try:
        data = request.get_json() or {}
        token = data.get('token') or request.headers.get('X-Auth-Token')
        user = TOKENS.get(token) or 'demo'
        
        PAPER_PORTFOLIOS[user] = {
            "cash": 100000.0,
            "positions": {},
            "trades": [],
            "equity_history": [{"date": datetime.now().isoformat(), "equity": 100000.0, "cash": 100000.0}],
            "created_at": datetime.now().isoformat()
        }
        return jsonify({"ok": True, "message": "Paper portfolio reset to $100k"})
    except Exception as e:
        print(f"paper reset error {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/quant/info', methods=['GET'])
def quant_info():
    try:
        # Try to import quant_model
        try:
            import quant_model
            info = quant_model.get_model_info() if hasattr(quant_model, 'get_model_info') else {}
            universe = quant_model.get_universe() if hasattr(quant_model, 'get_universe') else []
        except Exception as e:
            info = {"name": "No quant_model.py found", "error": str(e), "description": "Create quant_model.py in same folder as server.py"}
            universe = ["AAPL", "MSFT", "SPY", "QQQ"]
        
        return jsonify({
            "info": info,
            "universe": universe,
            "has_model": os.path.exists('quant_model.py')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/paper/run_quant', methods=['POST'])
def run_quant():
    try:
        data = request.get_json() or {}
        token = data.get('token') or request.headers.get('X-Auth-Token')
        user = TOKENS.get(token) or 'demo'
        paper = get_paper_portfolio(user)
        auto_execute = data.get('auto_execute', False)
        
        # Import quant model
        try:
            # Force reload to get latest code
            import importlib
            import quant_model
            importlib.reload(quant_model)
        except Exception as e:
            return jsonify({"error": f"Could not import quant_model.py: {e}. Create the file first. See /quant_model.py template."}), 400
        
        try:
            universe = quant_model.get_universe()
        except:
            universe = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ", "GOOGL"]
        
        # Fetch price data for universe
        price_data = {}
        for sym in universe[:25]:  # limit to 25
            try:
                q = fetch_quote_data(sym)
                if q:
                    price_data[sym] = q
            except:
                continue
        
        # Call quant model
        try:
            signals = quant_model.generate_signals(price_data, paper['positions'], paper['cash'], paper['cash'] + sum([pos['quantity'] * (price_data.get(sym, {}).get('price') or pos['avgCost']) for sym, pos in paper['positions'].items()]))
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": f"Quant model error: {e}", "price_data_symbols": list(price_data.keys())}), 500
        
        # Optionally auto-execute
        executed = []
        if auto_execute:
            for sig in signals[:5]:  # limit
                try:
                    sym = sig.get('symbol','').upper()
                    action = sig.get('action','BUY').upper()
                    qty = float(sig.get('quantity', 0))
                    if not sym or qty <= 0:
                        continue
                    q = price_data.get(sym)
                    if not q:
                        continue
                    price = q['price']
                    cost = qty * price
                    
                    if action == 'BUY' and paper['cash'] >= cost:
                        paper['cash'] -= cost
                        if sym in paper['positions']:
                            existing = paper['positions'][sym]
                            total_qty = existing['quantity'] + qty
                            total_cost = (existing['quantity'] * existing['avgCost']) + cost
                            paper['positions'][sym] = {"quantity": total_qty, "avgCost": total_cost / total_qty}
                        else:
                            paper['positions'][sym] = {"quantity": qty, "avgCost": price}
                        
                        paper['trades'].append({
                            "id": str(uuid.uuid4())[:8],
                            "symbol": sym,
                            "action": "BUY",
                            "quantity": qty,
                            "price": price,
                            "cost": cost,
                            "timestamp": datetime.now().isoformat(),
                            "reason": sig.get('reason', 'Quant signal'),
                            "model": True
                        })
                        executed.append(sig)
                    
                    elif action == 'SELL' and sym in paper['positions'] and paper['positions'][sym]['quantity'] >= qty:
                        paper['cash'] += qty * price
                        pos = paper['positions'][sym]
                        pnl = (price - pos['avgCost']) * qty
                        if pos['quantity'] == qty:
                            del paper['positions'][sym]
                        else:
                            pos['quantity'] -= qty
                        
                        paper['trades'].append({
                            "id": str(uuid.uuid4())[:8],
                            "symbol": sym,
                            "action": "SELL",
                            "quantity": qty,
                            "price": price,
                            "proceeds": qty * price,
                            "pnl": pnl,
                            "timestamp": datetime.now().isoformat(),
                            "reason": sig.get('reason', 'Quant signal'),
                            "model": True
                        })
                        executed.append(sig)
                except Exception as e:
                    print(f"auto-exec error {e}")
                    continue
        
        return jsonify({
            "signals": signals,
            "executed": executed if auto_execute else [],
            "price_data_count": len(price_data),
            "cash": paper['cash'],
            "positions_count": len(paper['positions'])
        })
    
    except Exception as e:
        print(f"run_quant error {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/paper/backtest', methods=['POST'])
def paper_backtest():
    try:
        data = request.get_json() or {}
        symbol = (data.get('symbol') or 'SPY').upper()
        period = data.get('period', '1y')
        
        t = yf.Ticker(symbol)
        hist = t.history(period=period)
        if hist.empty:
            return jsonify({"error": "No data"}), 400
        
        closes = hist['Close'].tolist()
        dates = [d.isoformat() for d in hist.index]
        
        # Simple backtest using quant model if available
        try:
            import quant_model
            # For backtest, we simulate the model's SMA logic
            # This is a simplified version - your real model should have its own backtest
            equity = 100000
            cash = 100000
            pos = 0
            avg = 0
            trades = []
            equity_curve = []
            
            for i in range(20, len(closes)):
                price = closes[i]
                sma20 = sum(closes[i-20:i]) / 20
                # Very simple: buy when price dips 3% below SMA, sell when 3% above
                if price < sma20 * 0.97 and cash > price * 10 and pos == 0:
                    qty = int((cash * 0.1) / price)
                    cost = qty * price
                    cash -= cost
                    pos = qty
                    avg = price
                    trades.append({"date": dates[i], "action": "BUY", "price": price, "qty": qty})
                elif price > sma20 * 1.03 and pos > 0:
                    cash += pos * price
                    trades.append({"date": dates[i], "action": "SELL", "price": price, "qty": pos, "pnl": (price - avg) * pos})
                    pos = 0
                
                equity = cash + (pos * price if pos else 0)
                equity_curve.append({"date": dates[i], "equity": equity})
            
            # Final stats
            total_return = (equity - 100000) / 100000 * 100
            return jsonify({
                "symbol": symbol,
                "period": period,
                "initial": 100000,
                "final": equity,
                "return_pct": total_return,
                "trades": trades[-20:],
                "equity_curve": equity_curve[-100:],
                "note": "This is a demo backtest using SMA logic from template. Replace with your model's backtest."
            })
        except Exception as e:
            # Fallback simple buy and hold
            initial = closes[0]
            final = closes[-1]
            buy_hold_return = (final - initial) / initial * 100
            return jsonify({
                "symbol": symbol,
                "period": period,
                "initial_price": initial,
                "final_price": final,
                "buy_hold_return": buy_hold_return,
                "note": f"Quant model not loaded: {e}. Showing buy & hold."
            })
    
    except Exception as e:
        print(f"backtest error {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ===== END PAPER TRADING =====



@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    try:
        if path.startswith('api/'):
            return jsonify({"error": "Not Found"}), 404
        if path and os.path.exists(path):
            return send_from_directory('.', path)
        if os.path.exists('index.html'):
            return send_from_directory('.', 'index.html')
        return jsonify({"ok": True, "message": "tickr v13"})
    except Exception as e:
        print(f"serve error {e}")
        return jsonify({"error": "serve error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"tickr v13 conversational + diversification fix starting on {port}")
    app.run(host='0.0.0.0', port=port)
