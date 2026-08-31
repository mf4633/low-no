"""If averaging is what works, does averaging MORE work better?

The wind test failed because upwind weighting throws neighbours away, and with
1-degree-C quantized predictors the noise reduction from averaging is worth more
than the physical routing. That diagnosis makes a prediction: adding more
5-minute stations should help, until distance degrades the signal faster than
the extra averaging cleans it up.

Parameter-free again -- the only choice is which stations are in the set, and
that is decided by cadence and distance, not fitted.
"""
import json
import math
import os
import sys

from lowno import sources
from interp_wind import coords, bearing, load, pearson, COORD_CACHE
from nowcast import HOURLY, ARCHIVE, temp_of

CANDIDATES = {
    "NYC": ["KLGA", "KEWR", "KTEB", "KHPN", "KISP", "KCDW", "KMMU", "KBLM",
            "KTTN", "KBDR", "KHVN", "KSWF", "KPOU", "KMGJ", "KDXR", "KOXC"],
    "DEN": ["KAPA", "KGXY", "KEIK", "KLMO", "KBDU", "KFNL", "KBKF", "KFTG",
            "KCOS", "KLIC", "KAKO", "KGJT", "KPUB", "KMNH"],
}


def haversine(a, b):
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def probe(st):
    """(cadence_min, lat, lon) or None."""
    import datetime as dt
    try:
        j = sources._get(f"https://api.weather.gov/stations/{st}/observations?limit=15",
                         timeout=25)
        ts = [f["properties"]["timestamp"] for f in j.get("features", [])]
        if len(ts) < 4:
            return None
        a = dt.datetime.fromisoformat(ts[0].replace("Z", "+00:00"))
        b = dt.datetime.fromisoformat(ts[-1].replace("Z", "+00:00"))
        cad = (a - b).total_seconds() / 60 / (len(ts) - 1)
        g = sources._get(f"https://api.weather.gov/stations/{st}", timeout=25)
        lon, lat = g["geometry"]["coordinates"][:2]
        return cad, lat, lon
    except Exception:
        return None


def main():
    C = coords()
    survey = {}
    for city, cands in CANDIDATES.items():
        hs = C[HOURLY[city]["station"]]
        rows = []
        for st in cands:
            if st in C:
                lat, lon = C[st]
                cad = None
            else:
                r = probe(st)
                if not r:
                    continue
                cad, lat, lon = r
                C[st] = [lat, lon]
            km = haversine(hs, [lat, lon])
            rows.append((st, cad, km))
        survey[city] = sorted(rows, key=lambda r: r[2])
        print(f"\n{city} candidate pool (sorted by distance):")
        for st, cad, km in survey[city]:
            print(f"   {st}  {km:>6.1f} km  cadence "
                  + (f"{cad:>4.0f}m" if cad is not None else "known"))
    json.dump(C, open(COORD_CACHE, "w"), indent=1, sort_keys=True)
    print(f"\ncoords cached: {len(C)}")
    print("\nRun nowcast.py after widening HOURLY[city]['neighbours'] to fetch"
          "\nand archive the new stations, then re-score.")


if __name__ == "__main__":
    main()
