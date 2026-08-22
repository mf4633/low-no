"""Multisource forecast collector.

Six competing highs for a station's local calendar date, for skill
comparison: NWS gridpoint, NBM / ECMWF / GFS / ICON via Open-Meteo, and
MET Norway locationforecast. Each source is best-effort and independent:
a source that can't be fetched reports None rather than being silently
dropped, so the caller can see exactly which models weighed in (same
stale-data discipline as sources.py).
"""
import datetime as dt
import statistics
import zoneinfo

from .sources import _get

# Open-Meteo model identifiers -> short labels used in the output dict.
OPEN_METEO_MODELS = {
    "ncep_nbm_conus": "nbm",
    "ecmwf_ifs025": "ecmwf",
    "gfs_seamless": "gfs",
    "icon_seamless": "icon",
}


def nws_high(lat, lon, date_iso):
    """Daytime-period high (F) from the NWS gridpoint forecast for date_iso,
    or None if the date is outside the forecast window or the fetch fails."""
    try:
        meta = _get(f"https://api.weather.gov/points/{lat},{lon}")
        fc = _get(meta["properties"]["forecast"])
        for period in fc["properties"]["periods"]:
            if period["isDaytime"] and period["startTime"][:10] == date_iso:
                return float(period["temperature"])
    except Exception:
        pass
    return None


def open_meteo_highs(lat, lon, tz, date_iso):
    """Per-model daily max temp (F) for the local date. Returns
    {label: highF-or-None} covering every model in OPEN_METEO_MODELS."""
    out = {label: None for label in OPEN_METEO_MODELS.values()}
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           "&daily=temperature_2m_max&temperature_unit=fahrenheit"
           f"&timezone={tz}&start_date={date_iso}&end_date={date_iso}"
           f"&models={','.join(OPEN_METEO_MODELS)}")
    try:
        daily = _get(url).get("daily", {})
    except Exception:
        return out
    for model, label in OPEN_METEO_MODELS.items():
        # multi-model responses suffix the variable; single-model does not
        vals = daily.get(f"temperature_2m_max_{model}") or daily.get("temperature_2m_max")
        if vals and vals[0] is not None:
            out[label] = round(float(vals[0]), 1)
    return out


def metno_high(lat, lon, tz, date_iso):
    """Daily max (F) from MET Norway locationforecast. Max over instant
    temps stamped on the local date, plus 6-hour-window maxes that start
    before 18:00 local so the window can't spill past midnight."""
    zone = zoneinfo.ZoneInfo(tz)
    try:
        j = _get("https://api.met.no/weatherapi/locationforecast/2.0/complete"
                 f"?lat={lat}&lon={lon}")
        temps = []
        for entry in j["properties"]["timeseries"]:
            when = dt.datetime.fromisoformat(entry["time"].replace("Z", "+00:00")).astimezone(zone)
            if when.date().isoformat() != date_iso:
                continue
            data = entry["data"]
            t = data.get("instant", {}).get("details", {}).get("air_temperature")
            if t is not None:
                temps.append(t)
            if when.hour < 18:
                t6 = (data.get("next_6_hours", {}).get("details", {}) or {}).get("air_temperature_max")
                if t6 is not None:
                    temps.append(t6)
        if temps:
            return round(max(temps) * 9 / 5 + 32, 1)
    except Exception:
        pass
    return None


def collect(city, date_iso):
    """All-source forecast highs for one city (a CITIES entry) on date_iso.

    Returns dict(station, date, sources, n, mean, median, spread) where
    sources maps source label -> highF or None, and the stats cover only
    the sources that answered. n=0 means nothing answered -- callers must
    treat that as no-data, not as a zero-degree forecast.
    """
    sources = {"nws": nws_high(city["lat"], city["lon"], date_iso)}
    sources.update(open_meteo_highs(city["lat"], city["lon"], city["tz"], date_iso))
    sources["metno"] = metno_high(city["lat"], city["lon"], city["tz"], date_iso)
    got = [v for v in sources.values() if v is not None]
    return dict(
        station=city["station"],
        date=date_iso,
        sources=sources,
        n=len(got),
        mean=round(statistics.mean(got), 1) if got else None,
        median=round(statistics.median(got), 1) if got else None,
        spread=round(max(got) - min(got), 1) if got else None,
    )
