"""Competing daily-high forecasts for one station-day.

Every forecaster returns its predicted daily maximum in F for the LOCAL date at
the station. All failures degrade to None -- a missing forecast must never break
a scan, and a None is honest where a fabricated number is not.

Scored nightly against CLI settlement by lowno.skill.
"""
import json, urllib.request, datetime as dt, zoneinfo


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "lowno/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        return json.loads(f.read())


def _c_to_f(c):
    return None if c is None else c * 9.0 / 5.0 + 32.0


def nws_gridpoint_max(lat, lon, local_date):
    """Forecaster-adjusted NWS grid. Can differ from raw NBM where the local
    office overrides guidance -- that disagreement is itself a signal worth
    measuring."""
    try:
        pts = _get(f"https://api.weather.gov/points/{lat},{lon}")
        grid = pts["properties"]["forecastGridData"]
        g = _get(grid)
        vals = g["properties"]["maxTemperature"]["values"]
        best = None
        for v in vals:
            when = v["validTime"].split("/")[0]
            if when[:10] == local_date:
                f = _c_to_f(v.get("value"))
                if f is not None and (best is None or f > best):
                    best = f
        return round(best, 1) if best is not None else None
    except Exception:
        return None


def open_meteo_max(lat, lon, local_date, model="best_match"):
    """Open-Meteo daily max. Free, no key. model: best_match | ecmwf_ifs025 | gfs_seamless"""
    try:
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               f"&daily=temperature_2m_max&temperature_unit=fahrenheit"
               f"&timezone=auto&start_date={local_date}&end_date={local_date}")
        if model != "best_match":
            url += f"&models={model}"
        j = _get(url)
        vals = (j.get("daily") or {}).get("temperature_2m_max") or []
        return round(vals[0], 1) if vals and vals[0] is not None else None
    except Exception:
        return None


# name -> callable(lat, lon, local_date) -> predicted daily max F
FORECASTERS = {
    "nws_grid": lambda la, lo, d: nws_gridpoint_max(la, lo, d),
    "om_best":  lambda la, lo, d: open_meteo_max(la, lo, d, "best_match"),
    # ifs04 (0.4 deg grid) is decommissioned: Open-Meteo still accepts the name
    # and returns HTTP 200 with null values -- the silent-null trap. ifs025 is
    # the live 0.25 deg grid.
    "om_ecmwf": lambda la, lo, d: open_meteo_max(la, lo, d, "ecmwf_ifs025"),
    "om_gfs":   lambda la, lo, d: open_meteo_max(la, lo, d, "gfs_seamless"),
    # Non-US models: genuinely independent of the NBM/GFS chain, so a miss here
    # is informative rather than correlated with the incumbent's miss.
    "om_icon":  lambda la, lo, d: open_meteo_max(la, lo, d, "icon_seamless"),
    "om_metno": lambda la, lo, d: open_meteo_max(la, lo, d, "metno_seamless"),
}


def collect(city_cfg, local_date):
    """All competing forecasts for one station-day. NBM `guide` is added by
    scan.py, which already fetches it -- no point calling twice."""
    out = {}
    for name, fn in FORECASTERS.items():
        try:
            out[name] = fn(city_cfg["lat"], city_cfg["lon"], local_date)
        except Exception:
            out[name] = None
    return out
