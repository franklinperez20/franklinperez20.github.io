import json, urllib.request
def g(u):
    r=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    with urllib.request.urlopen(r,timeout=30) as f: return json.load(f)
def show(t,u,fn):
    print("=====",t,u)
    try: fn(g(u))
    except Exception as e: print("ERR",e)
show("pm sports","https://gamma-api.polymarket.com/sports",lambda d:print(json.dumps(d)[:3000]))
def ev(d):
    print(len(d))
    for e in d[:40]:
        print(e.get("slug"),"|",e.get("title"),"|",e.get("startTime") or e.get("startDate"),"|",[ (m.get("question"),m.get("outcomes"),m.get("outcomePrices"),m.get("sportsMarketType")) for m in e.get("markets",[])[:3]])
show("pm events games","https://gamma-api.polymarket.com/events?closed=false&tag_slug=games&limit=100&order=startDate&ascending=true&end_date_min=2026-11-11",ev)
show("pm events nba","https://gamma-api.polymarket.com/events?closed=false&series_id=10345&limit=20",ev)
show("pm search","https://gamma-api.polymarket.com/public-search?q=Real%20Madrid&limit_per_type=3&events_status=active",lambda d:print(json.dumps(d)[:2500]))
def ks(d):
    ms=d.get("markets",[]); print(len(ms), d.get("cursor"))
    for m in ms[:30]: print(m.get("ticker"),"|",m.get("title"),"|",m.get("yes_sub_title"),m.get("last_price"),m.get("yes_bid"),m.get("yes_ask"),m.get("close_time"))
show("kalshi","https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=100&series_ticker=KXNBAGAME",ks)
show("kalshi series","https://api.elections.kalshi.com/trade-api/v2/series?category=Sports",lambda d:print([s.get("ticker") for s in d.get("series",[])][:400]))
show("espn euroleague","https://site.api.espn.com/apis/site/v2/sports/basketball/euroleague/scoreboard",lambda d:print(len(d.get("events",[]))))
show("espn tennis","https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard",lambda d:print(len(d.get("events",[]))))
