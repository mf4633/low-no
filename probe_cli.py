import json, sys
sys.path.insert(0,'.')
from lowno.sources import _get, _parse_cli
locs = _get("https://api.weather.gov/products/types/CLI/locations").get("locations", {})
print("total CLI locations:", len(locs))
for k in ["MTR","SFO","OAK","SJC","BOU","DEN","OKX","NYC","LOX","LAX"]:
    print(f"  {k}: {'YES' if k in locs else 'no'} {locs.get(k,'')}")
for code in ["SFO","MTR"]:
    if code not in locs: continue
    g = _get(f"https://api.weather.gov/products/types/CLI/locations/{code}").get("@graph",[])
    print(f"\n== {code}: {len(g)} products ==")
    for item in g[:8]:
        t = _get(item["@id"]).get("productText","") or ""
        print("  ", item.get("issuanceTime","")[:16], _parse_cli(t))
