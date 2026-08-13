"""Data sources. api.weather.gov for obs/forecast/CLI, Kalshi public API for ladders.
All fetches are best-effort with explicit staleness stamps -- a scan that can't
verify freshness must say so rather than guess (Aug 3-4 lesson: stale data is
the most expensive input in the system)."""
import datetime as dt, json, os, re, time, urllib.request, zoneinfo

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
    """Kalshi now publishes quotes as *_dollars (e.g. "0.98"). Convert to cents.
    None/absent means no resting order -- distinct from a 100c quote."""
    if v in (None, ""):
        return None
    try:
        return int(round(float(v) * 100))
    except (TypeError, ValueError):
        return None

def _legacy(v):
    """Pre-2026 integer-cent fields, kept as a fallback."""
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
                           "n_markets": len(markets), "keys": sorted(markets[0].keys()),
                           "rungs": [{k: m.get(k) for k in
                                      ("ticker", "status", "strike_type", "floor_strike",
                                       "cap_strike", "yes_bid_dollars", "yes_ask_dollars",
                                       "no_bid_dollars", "no_ask_dollars", "volume_fp")}
                                     for m in markets],
                           "sample_raw": markets[0]}, f, indent=1)
        except Exception:
            pass

    rungs = []
    for m in markets:
        # Prefer the current *_dollars schema; fall back to the legacy integer
        # fields so this keeps working if Kalshi serves either shape.
        yes_bid = _cents(m.get("yes_bid_dollars")) or _legacy(m.get("yes_bid"))
        yes_ask = _cents(m.get("yes_ask_dollars")) or _legacy(m.get("yes_ask"))
        no_ask = _cents(m.get("no_ask_dollars")) or _legacy(m.get("no_ask"))
        no_bid = _cents(m.get("no_bid_dollars")) or _legacy(m.get("no_bid"))
        src = "native"
        if no_ask is None:
            no_ask = 100 - yes_bid if yes_bid is not None else None
            src = "synthetic" if no_ask is not None else "absent"
        if no_bid is None and yes_ask is not None:
            no_bid = 100 - yes_ask
        rungs.append(dict(ticker=m["ticker"],
                          cap=m.get("cap_strike"), floor=m.get("floor_strike"),
                          yes_bid=yes_bid, yes_ask=yes_ask,
                          no_ask=no_ask, no_bid=no_bid, quote_src=src,
                          oi=m.get("open_interest"), vol=m.get("volume")))
    return rungs


def _ob_levels(node):
    """Kalshi orderbook sides appear as [[price_cents, size], ...] (and have also
    been served as [{"price":..,"size":..}]). Normalize both, tolerate neither."""
    out = []
    if not isinstance(node, list):
        return out
    for lvl in node:
        try:
            if isinstance(lvl, dict):
                px, sz = lvl.get("price"), lvl.get("size") or lvl.get("quantity")
            else:
                px, sz = lvl[0], lvl[1]
            if px is None or sz is None:
                continue
            px = float(px)
            if px <= 1.0:          # dollars schema
                px = px * 100
            out.append((int(round(px)), int(sz)))
        except Exception:
            continue
    return out


def orderbook_depth(ticker, max_price=98, probe_path=None):
    """How many NO contracts are actually buyable at or under max_price.

    Every P&L number in this ledger assumes a fill at the logged ask. That is an
    assumption about DEPTH, not price, and it has never been measured: a 97c rung
    with 8 contracts resting is a real edge that is not investable. Returns
    dict(best_no_ask, depth_at_best, depth_le_max, notional_le_max, levels, src)
    with None fields rather than raising -- depth is telemetry, never a gate input.

    NO-side asks are derived from YES bids when the book only publishes one side:
    buying NO at P is selling YES at (100-P), so resting YES bids at (100-P) are
    the contracts a NO buyer can lift.
    """
    try:
        j = _get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}/orderbook")
    except Exception as e:
        return dict(src="fetch_failed", err=str(e)[:80])
    ob = j.get("orderbook") or j
    if probe_path:
        try:
            os.makedirs(os.path.dirname(probe_path), exist_ok=True)
            json.dump({"ticker": ticker, "keys": sorted(ob.keys()) if isinstance(ob, dict) else None,
                       "raw": j}, open(probe_path, "w"), indent=1)
        except Exception:
            pass
    if not isinstance(ob, dict):
        return dict(src="unparsed")

    no_lv = _ob_levels(ob.get("no"))
    src = "native_no"
    if not no_lv:
        # derive NO asks from resting YES bids
        yes_lv = _ob_levels(ob.get("yes"))
        no_lv = [(100 - px, sz) for px, sz in yes_lv if 0 < px < 100]
        src = "derived_from_yes" if no_lv else "empty"
    if not no_lv:
        return dict(src=src, best_no_ask=None, depth_le_max=0, notional_le_max=0.0)

    buyable = sorted([(px, sz) for px, sz in no_lv if px <= max_price])
    best = buyable[0][0] if buyable else None
    depth_best = sum(sz for px, sz in buyable if px == best) if best is not None else 0
    depth_all = sum(sz for _, sz in buyable)
    notional = sum(px * sz for px, sz in buyable) / 100.0
    return dict(src=src, best_no_ask=best, depth_at_best=depth_best,
                depth_le_max=depth_all, notional_le_max=round(notional, 2),
                levels=buyable[:8])


def asos_1min_max(station4, date=None):
    """True 1-minute ASOS maximum -- the settlement premium the CLI rounds away.

    Hourly METAR undersamples the peak by ~0.5-1F (the known KDEN effect). When a
    rung settles within a degree of its ceiling, the tenths decide the trade, so
    BOUNDARY attributions are unanalyzable without this. Source: Iowa Environmental
    Mesonet 1-minute ASOS archive. Degrades to None on any failure; never gates.
    """
    site = station4[1:].upper()
    if date is None:
        date = dt.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date().isoformat()
    y, m, d = date.split("-")
    url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos1min.py"
           f"?station={site}&tz=UTC&year1={y}&month1={m}&day1={d}"
           f"&year2={y}&month2={m}&day2={d}&vars=tmpf&sample=1min&what=download&delim=comma")
    try:
        with urllib.request.urlopen(url, timeout=45) as r:
            txt = r.read().decode("utf-8", "replace")
    except Exception as e:
        return dict(src="fetch_failed", err=str(e)[:80], max_f=None)
    best, n, hdr = None, 0, None
    for line in txt.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = [c.strip() for c in line.split(",")]
        if hdr is None:
            hdr = parts
            continue
        try:
            i = hdr.index("tmpf")
            v = float(parts[i])
        except Exception:
            continue
        n += 1
        if best is None or v > best:
            best = v
    return dict(src="iem_1min", max_f=best, n_obs=n)

def _parse_cli(text):
    """Return (awips_id, summary_date, max_f) from one CLI product, or (None,None,None).

    Anchors, in order of reliability:
      line 3-ish  CLISFO            <- AWIPS id, identifies the STATION
      ...THE ... CLIMATE SUMMARY FOR AUGUST 9 2026...
      MAXIMUM         76   1:53 PM
    """
    awips = summary = maxf = None
    for line in text.splitlines()[:8]:
        t = line.strip()
        if re.fullmatch(r"CLI[A-Z]{3}", t):
            awips = t
            break
    m = re.search(r"SUMMARY FOR\s+([A-Z]+)\s+(\d{1,2})\s+(\d{4})", text)
    if m:
        try:
            summary = dt.datetime.strptime(
                f"{m.group(1).title()} {m.group(2)} {m.group(3)}", "%B %d %Y").date().isoformat()
        except ValueError:
            summary = None
    for line in text.splitlines():
        if line.strip().startswith("MAXIMUM"):
            parts = line.split()
            if len(parts) >= 2 and re.fullmatch(r"-?\d+", parts[1]):
                maxf = int(parts[1])
                break
    return awips, summary, maxf

def cli_max(station4, wfo, date=None):
    """Settlement: the CLI MAXIMUM for a SPECIFIC station on a SPECIFIC date.

    The prior version returned the first MAXIMUM found in the six most recent
    products for the WFO, matching neither station nor date -- MTR alone issues
    CLISFO/CLIOAK/CLISJC, so a grade could silently come from the wrong city on
    the wrong day. Both are now hard-matched; no match returns None (PENDING)
    rather than a plausible-looking wrong number.
    """
    site = station4[1:].upper()
    want_awips = "CLI" + site
    if date is None:
        date = dt.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date().isoformat()
    # CLI products are indexed by SITE (SFO, DEN, NYC), not by issuing office --
    # "MTR" returns zero products, as do BOU/OKX/LOX. WFO kept as a fallback only.
    graph = []
    for loc in [site, wfo]:
        if not loc:
            continue
        try:
            graph = _get(f"https://api.weather.gov/products/types/CLI/locations/{loc}").get("@graph", [])
        except Exception:
            graph = []
        if graph:
            break
    for item in graph:
        try:
            text = _get(item["@id"]).get("productText", "") or ""
        except Exception:
            continue
        awips, summary, maxf = _parse_cli(text)
        if awips == want_awips and summary == date and maxf is not None:
            return maxf, item.get("issuanceTime")
    return None, None
