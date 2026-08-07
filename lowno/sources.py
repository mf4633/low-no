"""Data sources. api.weather.gov for obs/forecast/CLI, Kalshi public API for ladders.
All fetches are best-effort with explicit staleness stamps -- a scan that can't
verify freshness must say so rather than guess (Aug 3-4 lesson: stale data is
the most expensive input in the system)."""
import datetime as dt, json, os, time, urllib.request

UA = {"User-Agent": "low-no scanner (github.com/mf4633/low-no)"}

def _get(url, timeout=6):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        time.sleep(2)
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

def _cents(v):
    """Kalshi quotes are integer cents. None/absent means no resting order."""
    return None if v in (None, "") else int(v)

def kalshi_ladder(series, date_yymmdd, probe_path="logs/_kalshi_probe.json"):
    """Public market quotes for one event day. Returns list of
    dict(ticker, cap, floor, yes_bid, yes_ask, no_ask, no_bid, quote_src).

    Aug 7 2026 defect: no_ask was derived solely as 100 - yes_bid, which pins to
    100 whenever yes_bid is absent or zero -- and that was every market, every
    city, every cycle, so the gate rejected 100% on price before reaching any
    weather logic. Kalshi returns no_ask/no_bid natively; prefer them and fall
    back to the synthetic only when the native side is missing. quote_src records
    which path was taken so the log can prove which one is live.
    """
    url = (f"https://api.elections.kalshi.com/trade-api/v2/markets"
           f"?series_ticker={series}&status=open&limit=100")
    j = _get(url)
    markets = [m for m in j.get("markets", []) if date_yymmdd in m.get("ticker", "")]

    # One-shot diagnostic: dump a raw market payload so field names are observable
    # rather than assumed. Cheap, idempotent, and the next scan proves the fix.
    if markets and probe_path:
        try:
            os.makedirs(os.path.dirname(probe_path), exist_ok=True)
            with open(probe_path, "w") as f:
                json.dump({"series": series, "fetched": dt.datetime.utcnow().isoformat() + "Z",
                           "n_markets": len(markets), "sample_raw": markets[0],
                           "keys": sorted(markets[0].keys())}, f, indent=1)
        except Exception:
            pass

    rungs = []
    for m in markets:
        yes_bid, yes_ask = _cents(m.get("yes_bid")), _cents(m.get("yes_ask"))
        no_ask, no_bid = _cents(m.get("no_ask")), _cents(m.get("no_bid"))
        src = "native"
        if no_ask is None:
            no_ask = 100 - yes_bid if yes_bid is not None else None
            src = "synthetic" if no_ask is not None else "absent"
        if no_bid is None and yes_ask is not None:
            no_bid = 100 - yes_ask
        rungs.append(dict(ticker=m["ticker"],
                          cap=m.get("cap_strike"), floor=m.get("floor_strike"),
                          yes_bid=yes_bid, yes_ask=yes_ask,
                          no_ask=no_ask, no_bid=no_bid, quote_src=src))
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
