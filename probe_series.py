import json, urllib.request
UA={"User-Agent":"lowno-probe/1.0"}; BASE="https://api.elections.kalshi.com/trade-api/v2"
def get(u):
    r=urllib.request.Request(u,headers=UA)
    with urllib.request.urlopen(r,timeout=45) as f: return json.loads(f.read())
US={ "KXHIGHTATL":("ATL","Atlanta","KATL","America/New_York",33.6301,-84.4418),
 "KXHIGHTBOS":("BOS","Boston","KBOS","America/New_York",42.3606,-71.0097),
 "KXHIGHTDAL":("DAL","Dallas","KDFW","America/Chicago",32.8975,-97.0381),
 "KXHIGHTDC":("DC","Washington DC","KDCA","America/New_York",38.8483,-77.0342),
 "KXHIGHTHOU":("HOU","Houston","KIAH","America/Chicago",29.9902,-95.3368),
 "KXHIGHHOU":("HOU2","Houston alt","KIAH","America/Chicago",29.9902,-95.3368),
 "KXHIGHTKSAN":("SAN","San Diego","KSAN","America/Los_Angeles",32.7336,-117.1831),
 "KXHIGHTSAN":("SAN2","San Diego alt","KSAN","America/Los_Angeles",32.7336,-117.1831),
 "KXHIGHTLV":("LAS","Las Vegas","KLAS","America/Los_Angeles",36.0719,-115.1634),
 "KXHIGHTMIN":("MSP","Minneapolis","KMSP","America/Chicago",44.8831,-93.2289),
 "KXHIGHTNOLA":("MSY","New Orleans","KMSY","America/Chicago",29.9934,-90.2581),
 "KXHIGHTOKC":("OKC","Oklahoma City","KOKC","America/Chicago",35.3889,-97.6008),
 "KXHIGHTSATX":("SAT","San Antonio","KSAT","America/Chicago",29.5337,-98.4698)}
live={}
print(f"{'series':16} {'mkts':>4} {'caps':>4}  example")
for s,(code,name,st,tz,lat,lon) in US.items():
    try:
        j=get(f"{BASE}/markets?series_ticker={s}&status=open&limit=100")
        m=j.get("markets",[])
        caps=sum(1 for x in m if x.get("cap_strike") is not None)
        if m:
            print(f"{s:16} {len(m):>4} {caps:>4}  {m[0]['ticker']}")
            live[s]=dict(code=code,name=name,station=st,tz=tz,lat=lat,lon=lon,
                         n=len(m),caps=caps,example=m[0]['ticker'])
        else:
            print(f"{s:16} {0:>4} {0:>4}  (no open markets)")
    except Exception as e:
        print(f"{s:16}  ERROR {str(e)[:50]}")
json.dump(live,open("live_series.json","w"),indent=1)
print(f"\n{len(live)} live US series with open markets")
# CLI check
print("\n=== CLI settlement availability ===")
locs=get("https://api.weather.gov/products/types/CLI/locations").get("locations",{})
ok=[]
for s,d in live.items():
    site=d["station"][1:]
    inx=site in locs
    n=0
    if inx:
        try: n=len(get(f"https://api.weather.gov/products/types/CLI/locations/{site}").get("@graph",[]))
        except Exception: n=-1
    good = inx and n>0
    print(f"  {'OK ' if good else 'BAD'} {d['code']:5} {site:4} index={inx} products={n}")
    if good: ok.append(s)
json.dump({s:live[s] for s in ok}, open("verified_series.json","w"), indent=1)
print(f"\n{len(ok)} series verified addable")
