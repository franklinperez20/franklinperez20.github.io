import json, urllib.request
def g(u):
    r=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    with urllib.request.urlopen(r,timeout=30) as f: return json.load(f)
d=g("https://gamma-api.polymarket.com/sports")
print("NSPORTS",len(d))
for s in d: print("S|",s.get("id"),"|",s.get("sport"),"|",s.get("name"),"|",s.get("series"),"|",s.get("tags"))
for sid in ["10188","10204"]:
    try:
        ev=g(f"https://gamma-api.polymarket.com/events?series_id={sid}&closed=false&limit=5")
        for e in ev[:3]:
            print("E|",sid,e.get("slug"),e.get("startTime"),e.get("title"))
            for m in e.get("markets",[]): 
                if m.get("sportsMarketType")=="moneyline": print("   M|",m.get("question"),m.get("outcomes"),m.get("outcomePrices"),m.get("groupItemTitle"),m.get("bestBid"),m.get("bestAsk"),m.get("lastTradePrice"),m.get("acceptingOrders"),m.get("gameStartTime"))
    except Exception as ex: print("ERR",sid,ex)
k=g("https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=2&series_ticker=KXNBAGAME")
print("KALSHI",json.dumps(k["markets"][0])[:1500])
for p in ["basketball/euroleague","tennis/atp","soccer/uefa.champions","basketball/nba"]:
    try:
        x=g(f"https://site.api.espn.com/apis/site/v2/sports/{p}/scoreboard")
        evs=x.get("events",[]); print("ESPN",p,len(evs), json.dumps((evs[0]["competitions"][0].get("odds") or [None])[0])[:300] if evs else "")
    except Exception as ex: print("ESPN ERR",p,ex)
print("==== closed test")
for q in ["closed=true","closed=false",""]:
    ev=g(f"https://gamma-api.polymarket.com/events?series_id=10345&limit=5&end_date_min=2026-11-11T00:00:00Z&end_date_max=2026-11-12T00:00:00Z&{q}")
    print(q,len(ev),[ (e['slug'],e.get('closed'),e.get('live'),e.get('score'),e.get('period'),e.get('ended')) for e in ev])
ev=g("https://gamma-api.polymarket.com/events?slug=bkeurocup-bah-lie-2026-11-11")
print("slug",json.dumps(ev)[:800])
ev=g("https://gamma-api.polymarket.com/public-search?q=Bahcesehir&limit_per_type=5&events_status=closed")
print("srch",[(e['slug'],e.get('closed'),e.get('score'),e.get('endDate')) for e in ev.get('events',[])])
