"""Upstream advection signal and intraday stall detection.

Telemetry only. Nothing here feeds the frozen gate; both signals are logged so
they can be scored as variants once enough settled days exist to test them.
"""
import json, math, os, urllib.request, datetime as dt, zoneinfo
from .config import CITIES

NEIGHBOR_CACHE = "docs/neighbors.json"
BEARING_TOLERANCE = 50      # degrees either side of the upwind bearing
MIN_KM, MAX_KM = 25, 150    # too close is the same airmass; too far is a different one
STALL_MIN_MINUTES = 45      # flat this long at peak hour counts as topped out


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "lowno/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.loads(f.read())


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def _bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1)*math.sin(p2) - math.sin(p1)*math.cos(p2)*math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _angle_diff(a, b):
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def load_neighbors(refresh=False):
    """Cached map city -> [{id, name, lat, lon, km, bearing}]. Discovered once
    from api.weather.gov so there is no hand-maintained station table to rot."""
    cache = {}
    if os.path.exists(NEIGHBOR_CACHE) and not refresh:
        try:
            cache = json.load(open(NEIGHBOR_CACHE))
        except Exception:
            cache = {}
    changed = False
    for city, cfg in CITIES.items():
        if city in cache and cache[city]:
            continue
        try:
            j = _get(f"https://api.weather.gov/points/{cfg['lat']},{cfg['lon']}/stations")
        except Exception:
            continue
        found = []
        for feat in (j.get("features") or [])[:60]:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or []
            sid = props.get("stationIdentifier")
            if not sid or len(coords) < 2:
                continue
            lon, lat = coords[0], coords[1]
            km = _haversine_km(cfg["lat"], cfg["lon"], lat, lon)
            if not (MIN_KM <= km <= MAX_KM):
                continue
            found.append(dict(id=sid, name=props.get("name"), lat=lat, lon=lon,
                              km=round(km, 1),
                              bearing=round(_bearing_deg(cfg["lat"], cfg["lon"], lat, lon), 1)))
        found.sort(key=lambda x: x["km"])
        cache[city] = found[:12]
        changed = True
    if changed:
        os.makedirs(os.path.dirname(NEIGHBOR_CACHE), exist_ok=True)
        json.dump(cache, open(NEIGHBOR_CACHE, "w"), indent=1)
    return cache


def _latest(station):
    """Latest obs for one station: temp F, dew point F, wind dir/speed."""
    try:
        j = _get(f"https://api.weather.gov/stations/{station}/observations/latest")
    except Exception:
        return None
    p = j.get("properties") or {}
    def val(k):
        v = (p.get(k) or {}).get("value")
        return v
    tC, dC = val("temperature"), val("dewpoint")
    return dict(station=station, ts=p.get("timestamp"),
                temp_f=None if tC is None else round(tC * 9/5 + 32, 1),
                dew_f=None if dC is None else round(dC * 9/5 + 32, 1),
                wind_dir=val("windDirection"),
                wind_mps=val("windSpeed"))


def upstream(city, target_obs=None, neighbors=None):
    """Advection signal from stations upwind of `city`.

    Returns None when wind is calm or undefined -- with no flow there is no
    advection, and pretending otherwise would manufacture a signal.
    """
    cfg = CITIES.get(city)
    if not cfg:
        return None
    tgt = target_obs or _latest(cfg["station"])
    if not tgt or tgt.get("wind_dir") is None or not tgt.get("wind_mps"):
        return dict(city=city, status="calm_or_unknown",
                    note="no defined flow; upstream signal is meaningless")

    # NWS windDirection is the direction the wind BLOWS FROM, so it already
    # points upwind. (First draft added 180 and then overwrote it -- that would
    # have selected DOWNWIND stations and inverted the entire signal.)
    upwind = tgt["wind_dir"]
    nb = (neighbors or load_neighbors()).get(city, [])
    picks = [n for n in nb if _angle_diff(n["bearing"], upwind) <= BEARING_TOLERANCE]
    picks.sort(key=lambda n: (_angle_diff(n["bearing"], upwind), n["km"]))
    reads = []
    for n in picks[:3]:
        o = _latest(n["id"])
        if o and o.get("temp_f") is not None:
            reads.append(dict(**o, km=n["km"], bearing=n["bearing"], name=n.get("name")))
    if not reads:
        return dict(city=city, status="no_upstream_obs", upwind_bearing=upwind)

    hot = max(reads, key=lambda r: r["temp_f"])
    dews = [r["dew_f"] for r in reads if r.get("dew_f") is not None]
    return dict(city=city, status="ok",
                upwind_bearing=upwind,
                target_temp_f=tgt.get("temp_f"), target_dew_f=tgt.get("dew_f"),
                wind_mps=tgt.get("wind_mps"),
                upstream=reads,
                max_upstream_temp_f=hot["temp_f"],
                advection_potential_f=(None if tgt.get("temp_f") is None
                                       else round(hot["temp_f"] - tgt["temp_f"], 1)),
                dew_differential_f=(None if (tgt.get("dew_f") is None or not dews)
                                    else round(max(dews) - tgt["dew_f"], 1)),
                note=("advection_potential is headroom IF the air arrived unmodified. "
                      "At light wind, transport over 100km takes many hours -- read this "
                      "as a regional airmass ceiling, not a forecast. A POSITIVE "
                      "dew_differential means the incoming air is MOISTER, which lowers "
                      "the wet-bulb ceiling regardless of how warm it is."))


def stall(city, day_rows):
    """Has the running max gone flat, and is the dew point mixing out or not?

    day_rows: this day's gate rows for one city, chronological, each with
    detail.run_max and an `at` timestamp.
    """
    pts = []
    for r in day_rows:
        d = r.get("detail") or {}
        if not isinstance(d, dict) or d.get("run_max") is None:
            continue
        pts.append((r.get("at"), d["run_max"]))
    if len(pts) < 2:
        return None
    last_val = pts[-1][1]
    flat_since = pts[-1][0]
    for ts, v in reversed(pts[:-1]):
        if abs(v - last_val) < 0.05:
            flat_since = ts
        else:
            break
    try:
        mins = (dt.datetime.fromisoformat(pts[-1][0])
                - dt.datetime.fromisoformat(flat_since)).total_seconds() / 60
    except Exception:
        mins = 0
    lh = None
    try:
        lh = (dt.datetime.fromisoformat(pts[-1][0]).replace(tzinfo=dt.timezone.utc)
              .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])).hour)
    except Exception:
        pass
    return dict(city=city, run_max=last_val, flat_minutes=round(mins),
                local_hour=lh,
                stalled=bool(mins >= STALL_MIN_MINUTES and lh is not None and 12 <= lh <= 17),
                note=("flat run_max through peak heating hours is a topped-out day. "
                      "Cross-reference dew_differential: a dew point that is RISING "
                      "while the max is flat means the layer is moistening, not mixing."))
