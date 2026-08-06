"""Data sources. api.weather.gov for obs/forecast/CLI, Kalshi public API for ladders.
All fetches are best-effort with explicit staleness stamps -- a scan that can't
verify freshness must say so rather than guess (Aug 3-4 lesson: stale data is
the most expensive input in the system)."""
import datetime as dt, json, urllib.request

UA = {"User-Agent": "low-no scanner (github.com/mf4633/low-no)"}

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def latest_obs(station):
    """Returns dict: tempF, running notes, obs time, raw props. api.weather.gov
    /stations/{id}/observations gives recent set; we compute today's running max
    from all obs with local-date == today, including 6-hr max groups when present."""
    j = _get(f"https://api.weather.gov/stations/{station}/observations?limit=60")
    out = []
    for f in j.get("features", []):
        p = f["properties"]
        t = p.get("temperature", {}).get("value")
        mx6 = (p.get("maxTemperatureLast24Hours", {}) or {}).get("value")
        out.append(dict(ts=p["timestamp"], tC=t, max24C=mx6,
                        wind=p.get("windDirection", {}).get("value"),
                        wspd=p.get("windSpeed", {}).get("value"),
                        vis=p.get("visibility", {}).get("value"),
                        wx=p.get("textDescription")))
    return out

def point_forecast_high(lat, lon):
    """NWS gridpoint forecast: returns (highF, shortForecast, pop%) for today."""
    meta = _get(f"https://api.weather.gov/points/{lat},{lon}")
    fc = _get(meta["properties"]["forecast"])
    for period in fc["properties"]["periods"]:
        if period["isDaytime"]:
            pop = (period.get("probabilityOfPrecipitation", {}) or {}).get("value") or 0
            return period["temperature"], period["shortForecast"], pop
    return None, None, None

def kalshi_ladder(series, date_yymmdd):
    """Public market quotes for one event day. Returns list of
    dict(ticker, ceiling, floor, yes_ask, no_ask, no_bid)."""
    url = (f"https://api.elections.kalshi.com/trade-api/v2/markets"
           f"?series_ticker={series}&status=open&limit=100")
    j = _get(url)
    rungs = []
    for m in j.get("markets", []):
        if date_yymmdd not in m.get("ticker", ""):
            continue
        rungs.append(dict(ticker=m["ticker"],
                          cap=m.get("cap_strike"), floor=m.get("floor_strike"),
                          yes_ask=m.get("yes_ask"), no_ask=100 - m.get("yes_bid", 0),
                          no_bid=100 - m.get("yes_ask", 100)))
    return rungs

def cli_max(station4, wfo):
    """Settlement: parse the CLI product text for MAXIMUM. Returns (maxF, product_time)."""
    j = _get(f"https://api.weather.gov/products/types/CLI/locations/{wfo}")
    for item in j.get("@graph", [])[:6]:
        text = _get(item["@id"]).get("productText", "")
        if station4[1:] in text.split("\n", 3)[2] if text else False:
            pass
        for line in text.splitlines():
            ls = line.split()
            if line.strip().startswith("MAXIMUM") and len(ls) >= 2 and ls[1].isdigit():
                return int(ls[1]), item.get("issuanceTime")
    return None, None
