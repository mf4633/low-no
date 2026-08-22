"""Discover Kalshi daily-high series by probing candidate tickers directly.

The bulk /markets listing did not return KXHIGH* markets (returned 0), so this
uses the SAME call shape that works in lowno/sources.py:
    /markets?series_ticker=<S>&status=open&limit=100
Kalshi is inconsistent about a leading T (KXHIGHTSEA vs KXHIGHDEN), so both
forms are tried for every candidate.
"""
import json, urllib.request, datetime as dt

UA = {"User-Agent": "lowno-probe/1.0"}
BASE = "https://api.elections.kalshi.com/trade-api/v2"

KNOWN = {
    "BOS": ("Boston","KBOS","America/New_York",42.3606,-71.0097),
    "DFW": ("Dallas","KDFW","America/Chicago",32.8975,-97.0381),
    "DCA": ("Washington DC","KDCA","America/New_York",38.8483,-77.0342),
    "SAT": ("San Antonio","KSAT","America/Chicago",29.5337,-98.4698),
    "ATL": ("Atlanta","KATL","America/New_York",33.6301,-84.4418),
    "IAH": ("Houston","KIAH","America/Chicago",29.9902,-95.3368),
    "HOU": ("Houston Hobby","KHOU","America/Chicago",29.6372,-95.2820),
    "MSP": ("Minneapolis","KMSP","America/Chicago",44.8831,-93.2289),
    "DTW": ("Detroit","KDTW","America/New_York",42.2313,-83.3308),
    "BNA": ("Nashville","KBNA","America/Chicago",36.1189,-86.6892),
    "LAS": ("Las Vegas","KLAS","America/Los_Angeles",36.0719,-115.1634),
    "SLC": ("Salt Lake City","KSLC","America/Denver",40.7884,-111.9778),
    "PDX": ("Portland","KPDX","America/Los_Angeles",45.5908,-122.6003),
    "STL": ("St. Louis","KSTL","America/Chicago",38.7525,-90.3737),
    "BWI": ("Baltimore","KBWI","America/New_York",39.1754,-76.6683),
    "CLT": ("Charlotte","KCLT","America/New_York",35.2140,-80.9431),
    "MCO": ("Orlando","KMCO","America/New_York",28.4339,-81.3250),
    "SAN": ("San Diego","KSAN","America/Los_Angeles",32.7336,-117.1831),
    "TPA": ("Tampa","KTPA","America/New_York",27.9622,-82.5402),
    "IND": ("Indianapolis","KIND","America/New_York",39.7173,-86.2944),
    "PIT": ("Pittsburgh","KPIT","America/New_York",40.4915,-80.2329),
    "CVG": ("Cincinnati","KCVG","America/New_York",39.0489,-84.6678),
    "MEM": ("Memphis","KMEM","America/Chicago",35.0424,-89.9767),
    "OKC": ("Oklahoma City","KOKC","America/Chicago",35.3931,-97.6007),
    "ABQ": ("Albuquerque","KABQ","America/Denver",35.0402,-106.6091),
    "BOI": ("Boise","KBOI","America/Denver",43.5644,-116.2228),
    "SMF": ("Sacramento","KSMF","America/Los_Angeles",38.6954,-121.5901),
    "MKE": ("Milwaukee","KMKE","America/Chicago",42.9550,-87.9045),
    "CLE": ("Cleveland","KCLE","America/New_York",41.4053,-81.8520),
    "RDU": ("Raleigh","KRDU","America/New_York",35.8923,-78.7819),
    "JAX": ("Jacksonville","KJAX","America/New_York",30.4941,-81.6879),
    "OMA": ("Omaha","KOMA","America/Chicago",41.3032,-95.8940),
    "ICT": ("Wichita","KICT","America/Chicago",37.6499,-97.4331),
    "TUS": ("Tucson","KTUS","America/Phoenix",32.1314,-110.9553),
    "ELP": ("El Paso","KELP","America/Denver",31.8111,-106.3760),
}
CONFIGURED_CODES = {"AUS","CHI","DEN","LAX","MIA","NYC","PHL","PHX","SEA","SFO"}
MARINE_SUSPECTS = {"SAN","PDX","SMF"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.loads(f.read())

def probe(series):
    try:
        j = get(f"{BASE}/markets?series_ticker={series}&status=open&limit=100")
    except Exception:
        return None
    mk = j.get("markets", [])
    if not mk:
        return None
    caps = sum(1 for m in mk if m.get("cap_strike") is not None)
    return dict(n=len(mk), caps=caps, example=mk[0].get("ticker"))

def main():
    print(f"probing {len(KNOWN)} candidate cities, both ticker forms\n")
    hits, misses = [], []
    for code in sorted(KNOWN):
        found = None
        for form in (f"KXHIGH{code}", f"KXHIGHT{code}"):
            r = probe(form)
            if r:
                found = (form, r); break
        if found:
            form, r = found
            tag = "ALREADY CONFIGURED" if code in CONFIGURED_CODES else "NEW"
            print(f"  {code:4} {form:14} mkts={r['n']:>3} caps={r['caps']:>3}  {tag}")
            if code not in CONFIGURED_CODES:
                hits.append((code, form, r))
        else:
            misses.append(code)
    print(f"\nno market found for: {', '.join(misses) if misses else '(none)'}")
    print("\n" + "="*70)
    if not hits:
        print("No new series available. Coverage is already complete.")
        return
    print(f"{len(hits)} NEW SERIES FOUND -- paste into lowno/config.py CITIES:\n")
    for code, form, r in hits:
        name, station, tz, lat, lon = KNOWN[code]
        marine = "   # MARINE -- add to prob.MARINE" if code in MARINE_SUSPECTS else ""
        print(f'    "{code}": dict(name="{name}", station="{station}", '
              f'tz="{tz}", series="{form}", lat={lat}, lon={lon}),{marine}')
    print("\nVERIFY CLI SETTLEMENT FIRST -- see verify_cli_out.txt in this run.")

if __name__ == "__main__":
    main()
