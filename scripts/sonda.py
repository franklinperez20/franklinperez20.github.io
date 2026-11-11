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
