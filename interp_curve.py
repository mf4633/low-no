"""r as a function of how many 5-minute neighbours are averaged.

The wind test failed because weighting DISCARDS neighbours. If that diagnosis is
right -- that averaging is buying noise reduction against 1-degree-C quantized
predictors -- then adding stations should raise r until distance degrades the
signal faster than the extra averaging cleans it.

The whole curve is printed rather than a chosen N. Picking the peak of a noisy
curve is a selection; showing the shape is a measurement. A broad plateau is a
real result, a single spike is not.
"""
import datetime as dt
import json
import math
import os
import statistics

from interp_wind import coords, load, pearson
from interp_more import haversine
from nowcast import HOURLY, ARCHIVE, at_or_before, temp_of, load_or_fetch

EXTRA = {
    "NYC": ["KCDW", "KBLM", "KISP", "KDXR", "KBDR", "KMGJ", "KTTN", "KPOU",
            "KOXC", "KHVN"],
    "DEN": ["KFNL", "KLIC", "KCOS", "KAKO", "KPUB"],
}


def main():
    C = coords()
    today = dt.datetime.now(dt.timezone.utc).date()
    days = [(today - dt.timedelta(days=i)).isoformat() for i in range(7, 0, -1)]

    for city, cfg in HOURLY.items():
        pool = list(cfg["neighbours"]) + [s for s in EXTRA[city]
                                          if s not in cfg["neighbours"]]
        hs_coord = C[cfg["station"]]
        pool = sorted((s for s in pool if s in C),
                      key=lambda s: haversine(hs_coord, C[s]))
        print(f"\n{'='*70}\n{city}: fetching {len(pool)} neighbours over 7 days")
        series = {}
        for st in pool:
            raw = load_or_fetch(st, days)
            v = [(k, temp_of(r)) for k, r in sorted(raw.items())
                 if temp_of(r) is not None]
            if len(v) > 200:                 # 5-minute stations only
                series[st] = v
        pool = [s for s in pool if s in series]
        print(f"  usable 5-minute neighbours: {len(pool)}")

        hostraw = load(cfg["station"])
        hs = [(k, temp_of(v)) for k, v in sorted(hostraw.items())
              if temp_of(v) is not None]

        print(f"\n  {'N':>3}{'nearest added':>16}{'km':>7}"
              + "".join(f"{'r@'+str(L)+'m':>9}" for L in (10, 20, 30, 40)))
        for N in range(1, len(pool) + 1):
            use = pool[:N]
            cells = []
            for L in (10, 20, 30, 40):
                pred, act = [], []
                for i in range(1, len(hs)):
                    t0, v0 = hs[i - 1]
                    t1, v1 = hs[i]
                    d0 = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
                    d1 = dt.datetime.fromisoformat(t1.replace("Z", "+00:00"))
                    if not (40 <= (d1 - d0).total_seconds() / 60 <= 80):
                        continue
                    cut = ((d1 - dt.timedelta(minutes=L)).isoformat()
                           .replace("+00:00", "Z")[:16] + "Z")
                    ds = []
                    for st in use:
                        a = at_or_before(series[st], t0)
                        b = at_or_before(series[st], cut)
                        if a and b and b[0] > a[0]:
                            ds.append(b[1] - a[1])
                    if not ds:
                        continue
                    pred.append(statistics.fmean(ds))
                    act.append(v1 - v0)
                r = pearson(pred, act) if len(act) >= 20 else None
                cells.append(r)
            km = haversine(hs_coord, C[use[-1]])
            print(f"  {N:>3}{use[-1]:>16}{km:>7.0f}"
                  + "".join(f"{(c if c is not None else float('nan')):>9.3f}"
                            for c in cells))


if __name__ == "__main__":
    main()
