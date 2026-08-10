"""Diagnostic: what CLI products does MTR actually have, and what do they parse to?"""
import json, sys
sys.path.insert(0, '.')
from lowno.sources import _get, _parse_cli
j = _get("https://api.weather.gov/products/types/CLI/locations/MTR")
g = j.get("@graph", [])
print(f"products returned: {len(g)}")
out = []
for item in g[:25]:
    try:
        t = _get(item["@id"]).get("productText", "") or ""
    except Exception as e:
        print("fetch fail", e); continue
    a, s, m = _parse_cli(t)
    out.append((item.get("issuanceTime", "")[:16], a, s, m))
for row in out:
    print(row)
