"""Discover Kalshi daily-high temperature series via the SERIES endpoint.

The markets endpoint returns tens of thousands of open contracts; KXHIGH* did
not appear within a 20-page scan. Series are the right index.
"""
import json, urllib.request, collections
UA={"User-Agent":"lowno-probe/1.0"}
BASE="https://api.elections.kalshi.com/trade-api/v2"
def get(u):
    r=urllib.request.Request(u,headers=UA)
    with urllib.request.urlopen(r,timeout=45) as f: return json.loads(f.read())

print("=== try /series with weather categories ===")
seen={}
for cat in ["Climate and Weather","Weather","Climate"]:
    try:
        j=get(f"{BASE}/series?category={urllib.parse.quote(cat)}")
        arr=j.get("series") or []
        print(f"  category '{cat}': {len(arr)} series")
        for s in arr:
            t=s.get("ticker","")
            seen[t]=s.get("title","")
    except Exception as e:
        print(f"  category '{cat}': {str(e)[:80]}")
import urllib.parse
if not seen:
    try:
        j=get(f"{BASE}/series")
        arr=j.get("series") or []
        print(f"  bare /series: {len(arr)}")
        for s in arr: seen[s.get('ticker','')]=s.get('title','')
    except Exception as e:
        print("  bare /series:",str(e)[:100])

high={k:v for k,v in seen.items() if k.startswith("KXHIGH")}
print(f"\n=== {len(high)} KXHIGH* series ===")
for k in sorted(high): print(f"  {k:18} {high[k][:60]}")

print("\n=== probe known-good + candidate tickers directly ===")
cands=["KXHIGHAUS","KXHIGHCHI","KXHIGHDEN","KXHIGHLAX","KXHIGHMIA","KXHIGHNY",
 "KXHIGHPHIL","KXHIGHTPHX","KXHIGHTSEA","KXHIGHTSFO",
 "KXHIGHBOS","KXHIGHTBOS","KXHIGHDFW","KXHIGHTDFW","KXHIGHDC","KXHIGHTDC",
 "KXHIGHDCA","KXHIGHSAT","KXHIGHTSAT","KXHIGHATL","KXHIGHTATL","KXHIGHHOU",
 "KXHIGHTHOU","KXHIGHMSP","KXHIGHTMSP","KXHIGHDET","KXHIGHTDET","KXHIGHNSH",
 "KXHIGHLAS","KXHIGHTLAS","KXHIGHSLC","KXHIGHTSLC","KXHIGHPDX","KXHIGHTPDX",
 "KXHIGHSTL","KXHIGHTSTL","KXHIGHBWI","KXHIGHBAL","KXHIGHCLT","KXHIGHTCLT",
 "KXHIGHMCO","KXHIGHORL","KXHIGHSAN","KXHIGHTSAN","KXHIGHTPA","KXHIGHTTPA",
 "KXHIGHIND","KXHIGHTIND","KXHIGHPHX","KXHIGHSEA","KXHIGHSFO","KXHIGHNYC"]
live={}
for c in cands:
    try:
        j=get(f"{BASE}/markets?series_ticker={c}&status=open&limit=5")
        m=j.get("markets",[])
        if m:
            live[c]=m[0]["ticker"]
            print(f"  LIVE  {c:14} e.g. {m[0]['ticker']}")
    except Exception:
        pass
print(f"\nlive series: {len(live)}")
json.dump(live, open("live_series.json","w"), indent=1)
