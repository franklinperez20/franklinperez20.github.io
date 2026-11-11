import json, urllib.request
def g(u):
    r=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36","Accept":"application/json"})
    with urllib.request.urlopen(r,timeout=30) as f: return json.load(f)
for u in ["https://api.sofascore.com/api/v1/sport/basketball/scheduled-events/2026-11-11",
          "https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d=2026-11-11&s=Basketball",
          "https://www.thesportsdb.com/api/v1/json/123/eventsday.php?d=2026-11-11&s=Basketball"]:
    try:
        d=g(u); evs=d.get("events") or []
        print("OK",u,len(evs))
        for e in evs[:200]:
            t=json.dumps(e)
            if any(k in t for k in ["Murcia","Aris","Bah"]): print("  ",t[:600])
    except Exception as ex: print("ERR",u,ex)
