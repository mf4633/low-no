"""STEP 1 -- run this FIRST. Discovers every Kalshi daily-high temperature series
and prints a ready-to-paste CITIES block for the ones not yet configured.

Nothing is added blind: a wrong series ticker fails SILENTLY as an empty ladder,
which looks identical to a quiet market. This probe proves each ticker against
live markets before it enters config.

    python probe_series.py            # discover + report
    python probe_series.py --json     # machine-readable dump

Run it on a GitHub Actions runner (or any box with Kalshi reachable), not in a
restricted sandbox.
"""
import json, sys, urllib.request, collections

UA = {"User-Agent": "lowno-probe/1.0"}
BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Station metadata for cities we might discover. NWS CLI is indexed by SITE code
# (SFO, DEN, NYC) -- NOT by WFO. lat/lon are the ASOS site used for settlement.
KNOWN = {
    "BOS": ("Boston",        "KBOS", "America/New_York",    42.3606, -71.0097),
    "DFW": ("Dallas",        "KDFW", "America/Chicago",     32.8975,  -97.0381),
    "DCA": ("Washington DC", "KDCA", "America/New_York",    38.8483,  -77.0342),
    "SAT": ("San Antonio",   "KSAT", "America/Chicago",     29.5337,  -98.4698),
    "ATL": ("Atlanta",       "KATL", "America/New_York",    33.6301,  -84.4418),
    "IAH": ("Houston",       "KIAH", "America/Chicago",     29.9902,  -95.3368),
    "HOU": ("Houston Hobby", "KHOU", "America/Chicago",     29.6372,  -95.2820),
    "MSP": ("Minneapolis",   "KMSP", "America/Chicago",     44.8831,  -93.2289),
    "DTW": ("Detroit",       "KDTW", "America/New_York",    42.2313,  -83.3308),
    "BNA": ("Nashville",     "KBNA", "America/Chicago",     36.1189,  -86.6892),
    "LAS": ("Las Vegas",     "KLAS", "America/Los_Angeles", 36.0719, -115.1634),
    "SLC": ("Salt Lake City","KSLC", "America/Denver",      40.7884, -111.9778),
    "PDX": ("Portland",      "KPDX", "America/Los_Angeles", 45.5908, -122.6003),
    "STL": ("St. Louis",     "KSTL", "America/Chicago",     38.7525,  -90.3737),
    "BWI": ("Baltimore",     "KBWI", "America/New_York",    39.1754,  -76.6683),
    "CLT": ("Charlotte",     "KCLT", "America/New_York",    35.2140,  -80.9431),
    "MCO": ("Orlando",       "KMCO", "America/New_York",    28.4339,  -81.3250),
    "SAN": ("San Diego",     "KSAN", "America/Los_Angeles", 32.7336, -117.1831),
    "TPA": ("Tampa",         "KTPA", "America/New_York",    27.9622,  -82.5402),
    "IND": ("Indianapolis",  "KIND", "America/New_York",    39.7173,  -86.2944),
}

# Already in lowno/config.py -- do not re-add.
CONFIGURED = {"KXHIGHAUS", "KXHIGHCHI", "KXHIGHDEN", "KXHIGHLAX", "KXHIGHMIA",
              "KXHIGHNY", "KXHIGHPHIL", "KXHIGHTPHX", "KXHIGHTSEA", "KXHIGHTSFO"}

# Marine-layer stations: bimodal burn-off, a Gaussian cannot price them, and in
# this ledger every single loss has been SFO. New ones inherit the same flag.
MARINE_SUSPECTS = {"SAN", "PDX"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as f:
        return json.loads(f.read())


def discover():
    """Every open KXHIGH* market, grouped by series ticker."""
    series = collections.defaultdict(lambda: {"n": 0, "example": None, "caps": 0})
    cursor = None
    for _ in range(20):                       # hard page cap
        url = f"{BASE}/markets?status=open&limit=1000"
        if cursor:
            url += f"&cursor={cursor}"
        j = get(url)
        for m in j.get("markets", []):
            t = m.get("ticker", "")
            if not t.startswith("KXHIGH"):
                continue
            s = t.split("-")[0]
            series[s]["n"] += 1
            series[s]["example"] = t
            if m.get("cap_strike") is not None:
                series[s]["caps"] += 1
        cursor = j.get("cursor")
        if not cursor:
            break
    return dict(series)


def guess_code(series_ticker):
    """KXHIGHTSEA -> SEA, KXHIGHDFW -> DFW. Kalshi is inconsistent about the
    leading T, so try both."""
    body = series_ticker[len("KXHIGH"):]
    for cand in (body, body[1:] if body.startswith("T") else None):
        if cand and cand in KNOWN:
            return cand
    return body


def main():
    found = discover()
    if "--json" in sys.argv:
        print(json.dumps(found, indent=1))
        return

    print(f"discovered {len(found)} KXHIGH* series\n")
    print(f"{'series':16} {'mkts':>5} {'w/cap':>6}  {'status':12} example")
    new = []
    for s in sorted(found):
        d = found[s]
        status = "CONFIGURED" if s in CONFIGURED else "NEW"
        print(f"{s:16} {d['n']:>5} {d['caps']:>6}  {status:12} {d['example']}")
        if status == "NEW":
            new.append(s)

    print("\n" + "=" * 68)
    if not new:
        print("No unconfigured series found. Current coverage is complete.")
        return
    print("PASTE-READY CITIES ENTRIES (verify each before committing):\n")
    unknown = []
    for s in new:
        code = guess_code(s)
        if code not in KNOWN:
            unknown.append((s, code))
            continue
        name, station, tz, lat, lon = KNOWN[code]
        marine = "   # MARINE SUSPECT -- see note below" if code in MARINE_SUSPECTS else ""
        print(f'    "{code}": dict(name="{name}", station="{station}", '
              f'tz="{tz}", series="{s}", lat={lat}, lon={lon}),{marine}')
    if unknown:
        print("\n# UNRESOLVED -- series exists but no station metadata. Look up the")
        print("# ASOS site NWS uses for CLI settlement before adding:")
        for s, code in unknown:
            print(f"#   {s}  (guessed code {code})")
    print("""
NOTES BEFORE YOU COMMIT
-----------------------
1. Verify CLI availability for each new site FIRST:
     https://api.weather.gov/products/types/CLI/locations
   If the site code is absent there, settlement will never resolve and the
   station will accumulate PENDING flags forever. (MTR/BOU/OKX are NOT valid --
   CLI is indexed by SITE, not by forecast office.)
2. New stations have ZERO settlement history. Their adaptive bias falls back to
   the weatherbot prior, and for sites weatherbot never fit, to a diffuse prior.
   Expect wide sigma and `empirical-pending` for ~2-3 weeks.
3. Marine suspects (SAN, PDX) inherit SFO's problem: bimodal burn-off that a
   Gaussian cannot represent. In this ledger EVERY loss has been SFO. Add them
   to prob.MARINE so the edge board refuses to size them.
4. Sample-rate math: 10 stations produced 6 flags in 13 days. Continental
   stations are 3-0; SFO is 1-2. Adding 5-8 continental sites should roughly
   double flag supply, which is currently the binding constraint on reaching
   60 units.
""")


if __name__ == "__main__":
    main()
