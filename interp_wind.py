"""Does weighting neighbours by wind direction beat averaging them equally?

Michael's hypothesis: the interpolator should know which neighbour is UPWIND.
Averaging KLGA and KEWR equally is wrong when the flow is westerly -- Newark is
then carrying the airmass that Central Park is about to get, and Flushing is
carrying the one it already had.

PARAMETER-FREE, deliberately. Weight = max(0, cos(angle between the bearing to
the neighbour and the direction the wind is coming FROM)). Fully upwind scores
1, crosswind 0, downwind 0. No thresholds, no fitted coefficients, so this can
be compared to the equal-weight baseline directly with no train/test split --
there is nothing to overfit.

Falls back to the equal-weight mean when the wind is missing, calm, or no
neighbour lies upwind. The fallback rate is reported, because a "wind model"
that silently falls back nine times in ten is an equal-weight model.
"""
import datetime as dt
import json
import math
import os
import statistics

from lowno import sources
from nowcast import HOURLY, ARCHIVE, at_or_before, temp_of, field_of

COORD_CACHE = "docs/station_coords.json"


def coords():
    if os.path.exists(COORD_CACHE):
        return json.load(open(COORD_CACHE))
    out = {}
    wanted = set()
    for cfg in HOURLY.values():
        wanted.add(cfg["station"])
        wanted.update(cfg["neighbours"])
    for st in sorted(wanted):
        try:
            j = sources._get(f"https://api.weather.gov/stations/{st}", timeout=25)
            lon, lat = j["geometry"]["coordinates"][:2]
            out[st] = [lat, lon]
        except Exception as e:
            print(f"  coords {st}: {str(e)[:40]}")
    json.dump(out, open(COORD_CACHE, "w"), indent=1, sort_keys=True)
    return out


def bearing(lat1, lon1, lat2, lon2):
    """Initial bearing from 1 to 2, degrees clockwise from north."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def load(station):
    d = os.path.join(ARCHIVE, station)
    out = {}
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            out.update(json.load(open(os.path.join(d, f))))
    return out


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def evaluate(city, C, lead=20):
    cfg = HOURLY[city]
    hostraw = load(cfg["station"])
    hs = [(k, temp_of(v)) for k, v in sorted(hostraw.items()) if temp_of(v) is not None]
    raw = {st: sorted(load(st).items()) for st in cfg["neighbours"]}
    ns = {st: [(k, temp_of(v)) for k, v in sr if temp_of(v) is not None]
          for st, sr in raw.items()}
    hlat, hlon = C.get(cfg["station"], (None, None))
    brg = {st: bearing(hlat, hlon, *C[st]) for st in ns if st in C and hlat}

    eq_d, wd_d, act = [], [], []
    fell_back = 0
    for i in range(1, len(hs)):
        t0, v0 = hs[i - 1]
        t1, v1 = hs[i]
        d0 = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        d1 = dt.datetime.fromisoformat(t1.replace("Z", "+00:00"))
        if not (40 <= (d1 - d0).total_seconds() / 60 <= 80):
            continue
        cut = (d1 - dt.timedelta(minutes=lead)).isoformat().replace("+00:00", "Z")[:16] + "Z"

        deltas, weights = [], []
        for st, s in ns.items():
            a, b = at_or_before(s, t0), at_or_before(s, cut)
            if not a or not b or b[0] <= a[0]:
                continue
            deltas.append(b[1] - a[1])
            # wind AT the neighbour, at the cutoff: direction it is coming FROM
            rec = raw[st][min(range(len(raw[st])),
                              key=lambda j: abs((raw[st][j][0] > cut) - 0)) ] if False else None
            wdir = None
            for ts, rr in reversed(raw[st]):
                if ts <= cut:
                    wdir = field_of(rr, "wd")
                    break
            if wdir is None or st not in brg:
                weights.append(None)
            else:
                ang = math.radians(brg[st] - wdir)
                weights.append(max(0.0, math.cos(ang)))
        if not deltas:
            continue
        eq = statistics.fmean(deltas)
        good = [(d, w) for d, w in zip(deltas, weights) if w is not None and w > 0]
        tot = sum(w for _, w in good)
        if tot > 0:
            wdp = sum(d * w for d, w in good) / tot
        else:
            wdp = eq
            fell_back += 1
        eq_d.append(eq)
        wd_d.append(wdp)
        act.append(v1 - v0)

    n = len(act)
    if n < 20:
        return None
    return dict(city=city, lead=lead, n=n, fallback=fell_back,
                r_eq=pearson(eq_d, act), r_wd=pearson(wd_d, act),
                mae_eq=statistics.fmean(abs(a - b) for a, b in zip(eq_d, act)),
                mae_wd=statistics.fmean(abs(a - b) for a, b in zip(wd_d, act)))


def main():
    C = coords()
    print(f"station coords: {len(C)} cached in {COORD_CACHE}\n")
    print(f"{'city':5}{'lead':>6}{'n':>5}{'fallback':>10}{'r equal':>10}"
          f"{'r wind':>9}{'MAE equal':>11}{'MAE wind':>10}{'verdict':>12}")
    for city in HOURLY:
        for lead in (10, 20, 30, 40):
            r = evaluate(city, C, lead)
            if not r:
                continue
            better = r["r_wd"] > r["r_eq"] and r["mae_wd"] < r["mae_eq"]
            print(f"{r['city']:5}{lead:>5}m{r['n']:>5}"
                  f"{100*r['fallback']/r['n']:>9.0f}%{r['r_eq']:>10.3f}"
                  f"{r['r_wd']:>9.3f}{r['mae_eq']:>11.2f}{r['mae_wd']:>10.2f}"
                  f"{'wind better' if better else 'no':>12}")
    print()
    print("Parameter-free on both sides, so this is a like-for-like comparison")
    print("with nothing fitted. Check the fallback column before reading the rest.")


if __name__ == "__main__":
    main()
