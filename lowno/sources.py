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
                        dewC=(p.get("dewpoint", {}) or {}).get("value"),
                        # rawMessage is present ONLY on the :53 METARs. The other
                        # observations are 5-minute automated obs converted from
                        # whole degrees C, so in F they land on odd values only
                        # (91/93/95, never 92/94). CLI settles from the official
                        # observation, so dropping this field made run_max biased
                        # COOL by up to 1F -- KMSY read 94F on the 2026-08-22
                        # 2:53 METAR while every neighbouring 5-min ob read 93F.
                        raw=p.get("rawMessage"),
                        clouds=p.get("cloudLayers") or [],
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

def _fp_int(v):
    """2026 *_fp count fields arrive as decimal STRINGS ("152.00")."""
    try:
        return None if v in (None, "") else int(float(v))
    except (TypeError, ValueError):
        return None

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
    # date_yymmdd=None returns ALL open markets (any event day) -- used by the
    # world-series launch watch, where assuming which local date is "today"
    # would be a bug across 14 timezones.
    markets = [m for m in j.get("markets", [])
               if date_yymmdd is None or date_yymmdd in m.get("ticker", "")]

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
        # Kalshi T-tickers name a THRESHOLD, not an inclusive cap: KXHIGHTSATX-T101
        # is the contract "100 or below", yet the API's cap_strike says 101.
        # Verified across all 21 stations (2026-08-25): the bottom rung's raw
        # cap_strike always equals the FIRST RANGE bucket's floor_strike, which is
        # impossible for inclusive buckets -- they would overlap. So subtract 1,
        # for the BOTTOM rung ONLY (floor_strike is None); range and top rungs'
        # strikes are already inclusive and correct. Do NOT "fix" this back to the
        # raw API value -- the raw value is preserved in cap_strike_raw.
        cap_raw = m.get("cap_strike")
        floor = m.get("floor_strike")
        cap = cap_raw - 1 if (floor is None and cap_raw is not None) else cap_raw
        # 2026 schema renamed the count fields to *_fp decimal strings; the
        # legacy integers are gone (they logged as None for weeks unnoticed).
        # Explicit None checks, never `or` -- 0 is a real value (gotcha #6).
        oi = m.get("open_interest")
        if oi is None:
            oi = _fp_int(m.get("open_interest_fp"))
        vol = m.get("volume")
        if vol is None:
            vol = _fp_int(m.get("volume_fp"))
        rungs.append(dict(ticker=m["ticker"],
                          cap=cap, floor=floor, cap_strike_raw=cap_raw,
                          yes_bid=yes_bid, yes_ask=yes_ask,
                          no_ask=no_ask, no_bid=no_bid, quote_src=src,
                          oi=oi, vol=vol))
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
            # Both fields arrive as decimal STRINGS ("0.9700", "953.00").
            # int("953.00") raises, which silently emptied every level.
            px, sz = float(px), int(float(sz))
            if px <= 1.0:          # dollars schema
                px = px * 100
            if sz <= 0:
                continue
            out.append((int(round(px)), sz))
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
    ob = j.get("orderbook_fp") or j.get("orderbook") or j
    if probe_path:
        try:
            os.makedirs(os.path.dirname(probe_path), exist_ok=True)
            json.dump({"ticker": ticker, "keys": sorted(ob.keys()) if isinstance(ob, dict) else None,
                       "raw": j}, open(probe_path, "w"), indent=1)
        except Exception:
            pass
    if not isinstance(ob, dict):
        return dict(src="unparsed")

    # Probe finding (2026-08-12): Kalshi returns orderbook_fp with BOTH sides as
    # resting BIDS -- no_dollars are NO bids, yes_dollars are YES bids. There is
    # no ask side. To BUY NO at price P you must lift a resting YES bid at
    # (100 - P). So NO-side liquidity available to a buyer = the YES bid stack,
    # inverted. Reading no_dollars as asks would report the wrong side entirely.
    yes_lv = _ob_levels(ob.get("yes_dollars") or ob.get("yes"))
    no_lv = [(100 - px, sz) for px, sz in yes_lv if 0 < px < 100]
    src = "from_yes_bids" if no_lv else "empty"

    # YES-side liquidity from the SAME payload (zero extra calls): buying YES at
    # P lifts a resting NO bid at (100-P), so the no_dollars stack, inverted, is
    # what a YES buyer can fill. Logged for the YES pilot's fill-reality model
    # (CANDIDATE.md): the paper P&L assumes full fills at the logged ask, and
    # this is the only record of whether the contracts actually existed. Books
    # are EPHEMERAL -- this cannot be reconstructed after the fact.
    nb_lv = _ob_levels(ob.get("no_dollars") or ob.get("no"))
    yes_ask_lv = sorted([(100 - px, sz) for px, sz in nb_lv if 0 < px < 100])
    yes_fill = [(px, sz) for px, sz in yes_ask_lv if px <= 10]
    yes_side = dict(
        yes_best_ask=(yes_ask_lv[0][0] if yes_ask_lv else None),
        yes_ctr_le_10c=sum(sz for _, sz in yes_fill),
        yes_usd_le_10c=round(sum(px * sz for px, sz in yes_fill) / 100.0, 2))

    if not no_lv:
        return dict(src=src, best_no_ask=None, depth_le_max=0,
                    notional_le_max=0.0, **yes_side)

    buyable = sorted([(px, sz) for px, sz in no_lv if px <= max_price])
    best = buyable[0][0] if buyable else None
    depth_best = sum(sz for px, sz in buyable if px == best) if best is not None else 0
    depth_all = sum(sz for _, sz in buyable)
    notional = sum(px * sz for px, sz in buyable) / 100.0
    return dict(src=src, best_no_ask=best, depth_at_best=depth_best,
                depth_le_max=depth_all, notional_le_max=round(notional, 2),
                levels=buyable[:8], **yes_side)


def buoy_sst(buoy_id):
    """Latest water temperature from an NDBC buoy, F. The ocean/lake half of
    the land-sea delta-T that drives sea-breeze / lake-breeze / stratus caps.
    Telemetry only; degrades to None. NDBC serves plain text; WTMP is Celsius,
    'MM' means missing."""
    try:
        req = urllib.request.Request(
            f"https://www.ndbc.noaa.gov/data/realtime2/{buoy_id}.txt",
            headers={"User-Agent": "lowno/1.0"})
        with urllib.request.urlopen(req, timeout=20) as f:
            lines = f.read().decode("utf-8", "replace").splitlines()
        hdr = lines[0].split()
        if "WTMP" not in hdr:
            return None
        wi = hdr.index("WTMP")
        for ln in lines[2:12]:          # newest rows first; skip units row
            parts = ln.split()
            if len(parts) > wi and parts[wi] not in ("MM", "999.0"):
                return dict(buoy=buoy_id,
                            sst_f=round(float(parts[wi]) * 9 / 5 + 32, 1),
                            obs_utc="-".join(parts[0:3]) + "T" + ":".join(parts[3:5]))
        return None
    except Exception:
        return None


def metar_now(icaos):
    """Latest METAR for a list of ICAO ids -- GLOBAL coverage via
    aviationweather.gov (api.weather.gov is US-only, and the world-series
    launch watch needs obs the day a market appears). Live-verified
    2026-08-26 on EGLL/RJTT/YSSY/MMMX. Returns {icao: {...}}, {} on failure."""
    try:
        j = _get(f"https://aviationweather.gov/api/data/metar"
                 f"?ids={','.join(icaos)}&format=json")
        out = {}
        for m in j or []:
            t, d = m.get("temp"), m.get("dewp")
            out[m.get("icaoId")] = dict(
                temp_f=None if t is None else round(t * 9 / 5 + 32, 1),
                dew_f=None if d is None else round(d * 9 / 5 + 32, 1),
                wdir=m.get("wdir"), wspd_kt=m.get("wspd"),
                ts=m.get("reportTime"))
        return out
    except Exception:
        return {}


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


def _obs_stream(o):
    """Which stream an observation came from.

    METARs carry rawMessage; 5-minute automated obs do not. The 5-minute values
    are converted from whole degrees C, so in F they land only on odd numbers --
    a second, independent tell used as a fallback when rawMessage is absent.
    """
    if o.get("raw"):
        return "metar"
    f = o.get("tF")
    if f is not None and abs(f - round(f)) < 0.01 and int(round(f)) % 2 == 1:
        return "fivemin_or_odd"
    return "fivemin"


def sky_from_obs(o):
    """Compact sky condition: worst (most covering) layer plus its height."""
    order = {"CLR": 0, "SKC": 0, "FEW": 1, "SCT": 2, "BKN": 3, "OVC": 4}
    layers = o.get("clouds") or []
    if not layers:
        return dict(cover=None, base_ft=None, layers=[])
    best = None
    for L in layers:
        amt = (L.get("amount") or "").upper()[:3]
        ft = L.get("base")
        if isinstance(ft, dict):
            ft = ft.get("value")
        ft = None if ft is None else round(ft * 3.28084)
        if best is None or order.get(amt, 0) > order.get(best[0], 0):
            best = (amt, ft)
    return dict(cover=best[0], base_ft=best[1],
                layers=[dict(amount=(L.get("amount") or "")[:3],
                             base_ft=(None if (L.get("base") or {}).get("value") is None
                                      else round((L["base"]["value"]) * 3.28084)))
                        for L in layers][:4],
                note="obscuring cover only matters at BKN/OVC; FEW/SCT trims "
                     "little insolation. High BKN (>20000ft) is cirrus -- a "
                     "modest trim, not a cap.")
