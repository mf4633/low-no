"""Can weighting beat the equal-weight mean? Measured, with the overfit exposed.

Three families, in increasing order of how much they can lie to you:

  PARAMETER-FREE      equal, inverse-distance, inverse-distance-squared,
                      elevation-amplitude. Nothing fitted, so in-sample IS
                      out-of-sample and the comparison is honest by construction.

  FITTED, per neighbour   least squares on the neighbour deltas. One coefficient
                      per station. Scored BOTH in-sample and by leave-one-DAY-out,
                      because within a day the transitions share weather and
                      leaving out single observations would leak.

The gap between the fitted in-sample and leave-one-day-out numbers is the
headline, not the best row. On 7 days and ~140 transitions with 5-10 predictors,
a fitted model that gains in-sample and loses out-of-sample is the expected
result, and printing both is the only way to see it.

SEASONALITY IS NOT MODELLED AND CANNOT BE. Every day in the archive is late
August. A seasonal term fitted here would be pure invention. It becomes a real
question once the archive spans months -- the archive now grows nightly, so the
earliest honest attempt is a winter's worth of days away.
"""
import datetime as dt
import json
import math
import os
import statistics
from collections import defaultdict

from interp_wind import coords, load, pearson
from interp_more import haversine
from nowcast import HOURLY, at_or_before, temp_of

ELEV_CACHE = "docs/station_elev.json"


def elevations(stations):
    from lowno import sources
    cache = json.load(open(ELEV_CACHE)) if os.path.exists(ELEV_CACHE) else {}
    for st in stations:
        if st in cache:
            continue
        try:
            j = sources._get(f"https://api.weather.gov/stations/{st}", timeout=25)
            cache[st] = (j.get("properties", {}).get("elevation") or {}).get("value")
        except Exception:
            cache[st] = None
    json.dump(cache, open(ELEV_CACHE, "w"), indent=1, sort_keys=True)
    return cache


def samples(city, lead=20):
    """[(day, actual_delta, {station: neighbour_delta})]"""
    cfg = HOURLY[city]
    hs = [(k, temp_of(v)) for k, v in sorted(load(cfg["station"]).items())
          if temp_of(v) is not None]
    ns = {st: [(k, temp_of(v)) for k, v in sorted(load(st).items())
               if temp_of(v) is not None] for st in cfg["neighbours"]}
    out = []
    for i in range(1, len(hs)):
        t0, v0 = hs[i - 1]
        t1, v1 = hs[i]
        d0 = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        d1 = dt.datetime.fromisoformat(t1.replace("Z", "+00:00"))
        if not (40 <= (d1 - d0).total_seconds() / 60 <= 80):
            continue
        cut = (d1 - dt.timedelta(minutes=lead)).isoformat().replace("+00:00", "Z")[:16] + "Z"
        row = {}
        for st, s in ns.items():
            a, b = at_or_before(s, t0), at_or_before(s, cut)
            if a and b and b[0] > a[0]:
                row[st] = b[1] - a[1]
        if len(row) == len(ns):          # complete rows only, so all models see
            out.append((t1[:10], v1 - v0, row))   # identical data
    return out


def solve(A, y, ridge=1e-6):
    """Least squares via normal equations with a whisker of ridge for stability."""
    k = len(A[0])
    XtX = [[sum(A[r][i] * A[r][j] for r in range(len(A))) + (ridge if i == j else 0)
            for j in range(k)] for i in range(k)]
    Xty = [sum(A[r][i] * y[r] for r in range(len(A))) for i in range(k)]
    # Gauss-Jordan
    M = [row[:] + [Xty[i]] for i, row in enumerate(XtX)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        M[c] = [x / pv for x in M[c]]
        for r in range(k):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [x - f * y_ for x, y_ in zip(M[r], M[c])]
    return [M[i][k] for i in range(k)]


def run(city, lead, C, EL):
    S = samples(city, lead)
    if len(S) < 40:
        return
    sts = sorted(S[0][2])
    host = HOURLY[city]["station"]
    hc, he = C[host], EL.get(host)
    d = {st: haversine(hc, C[st]) for st in sts}
    # Elevation-amplitude: a station 300m higher swings differently; scale its
    # delta by the ratio of dry-adiabatic-adjusted amplitude. No data used.
    amp = {}
    for st in sts:
        e = EL.get(st)
        amp[st] = 1.0 if (e is None or he is None) else 1.0 / (1.0 + abs(e - he) / 1000.0)

    schemes = {
        "equal": {st: 1.0 for st in sts},
        "1/d": {st: 1.0 / max(d[st], 1) for st in sts},
        "1/d^2": {st: 1.0 / max(d[st], 1) ** 2 for st in sts},
        "elev-amp": {st: amp[st] for st in sts},
        "1/d * elev": {st: amp[st] / max(d[st], 1) for st in sts},
    }
    act = [s[1] for s in S]
    res = {}
    for name, w in schemes.items():
        tot = sum(w.values())
        pred = [sum(s[2][st] * w[st] for st in sts) / tot for s in S]
        res[name] = (pearson(pred, act), None)

    # fitted, in-sample and leave-one-DAY-out
    A = [[s[2][st] for st in sts] for s in S]
    beta = solve(A, act)
    if beta:
        pred_in = [sum(a * b for a, b in zip(row, beta)) for row in A]
        days = sorted({s[0] for s in S})
        pred_oos = [None] * len(S)
        for day in days:
            tr = [i for i, s in enumerate(S) if s[0] != day]
            te = [i for i, s in enumerate(S) if s[0] == day]
            if len(tr) < len(sts) + 5:
                continue
            b = solve([A[i] for i in tr], [act[i] for i in tr])
            if not b:
                continue
            for i in te:
                pred_oos[i] = sum(x * y for x, y in zip(A[i], b))
        ok = [i for i, v in enumerate(pred_oos) if v is not None]
        res["FITTED"] = (pearson(pred_in, act),
                         pearson([pred_oos[i] for i in ok], [act[i] for i in ok]))
    return sts, res, len(S)


def main():
    C = coords()
    allst = set()
    for city, cfg in HOURLY.items():
        allst.add(cfg["station"])
        allst.update(cfg["neighbours"])
    EL = elevations(sorted(allst))
    for city in HOURLY:
        for lead in (10, 20):
            got = run(city, lead, C, EL)
            if not got:
                continue
            sts, res, n = got
            print(f"\n{city} @ {lead}m lead, n={n}, {len(sts)} neighbours")
            print(f"  {'scheme':14}{'r in-sample':>14}{'r out-of-sample':>18}")
            for name, (ri, ro) in res.items():
                oos = f"{ro:.3f}" if ro is not None else "(same, unfitted)"
                print(f"  {name:14}{ri:>14.3f}{oos:>18}")
    print("\nCompare FITTED's two columns. A large drop is the overfit, and on")
    print("7 days with this many predictors a drop is the expected outcome.")
    print("Seasonality is deliberately absent: every day here is late August.")


if __name__ == "__main__":
    main()
