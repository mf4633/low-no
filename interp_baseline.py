"""What does r >= 0.9 actually mean for a temperature interpolator?

Two different questions hide behind one number, and they differ by a lot.

LEVELS   corr(predicted temperature, actual temperature). Temperature is
         massively autocorrelated -- the diurnal cycle alone carries most of the
         variance -- so almost any estimator scores near 1.0 here. A target of
         0.9 on levels is met by predicting "the same as an hour ago".

DELTAS   corr(predicted CHANGE, actual CHANGE) over the interval being
         predicted. This is the part that is actually unknown at decision time,
         and it is the only version of the target worth chasing.

Both are printed so the target can be set against the right one.
"""
import datetime as dt
import json
import math
import os
import statistics

from nowcast import HOURLY, ARCHIVE, at_or_before, temp_of


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


def rows(city, lead=20):
    cfg = HOURLY[city]
    hs = [(k, temp_of(v)) for k, v in sorted(load(cfg["station"]).items())
          if temp_of(v) is not None]
    ns = {st: [(k, temp_of(v)) for k, v in sorted(load(st).items())
               if temp_of(v) is not None] for st in cfg["neighbours"]}
    ns = {k: v for k, v in ns.items() if v}
    out = []
    for i in range(1, len(hs)):
        t0, v0 = hs[i - 1]
        t1, v1 = hs[i]
        d0 = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        d1 = dt.datetime.fromisoformat(t1.replace("Z", "+00:00"))
        if not (40 <= (d1 - d0).total_seconds() / 60 <= 80):
            continue
        cut = (d1 - dt.timedelta(minutes=lead)).isoformat().replace("+00:00", "Z")[:16] + "Z"
        ds = []
        for st, s in ns.items():
            a, b = at_or_before(s, t0), at_or_before(s, cut)
            if a and b and b[0] > a[0]:
                ds.append(b[1] - a[1])
        if not ds:
            continue
        out.append(dict(t1=t1, last=v0, actual=v1,
                        pred=v0 + statistics.fmean(ds),
                        actual_delta=v1 - v0, pred_delta=statistics.fmean(ds)))
    return out


def main():
    print("Baseline: predicted next print = last print + mean neighbour delta")
    print("(the parameter-free estimator already validated in nowcast.py)\n")
    print(f"{'city':5}{'lead':>6}{'n':>5}{'r LEVELS':>11}{'r DELTAS':>11}"
          f"{'delta sd':>10}{'resid sd':>10}{'R2 deltas':>11}")
    for city in HOURLY:
        for lead in (10, 20, 30, 40):
            r = rows(city, lead)
            if len(r) < 20:
                continue
            rl = pearson([x["pred"] for x in r], [x["actual"] for x in r])
            rd = pearson([x["pred_delta"] for x in r], [x["actual_delta"] for x in r])
            sd = statistics.stdev([x["actual_delta"] for x in r])
            resid = statistics.stdev([x["actual"] - x["pred"] for x in r])
            print(f"{city:5}{lead:>5}m{len(r):>5}{rl:>11.3f}{rd:>11.3f}"
                  f"{sd:>10.2f}{resid:>10.2f}{(rd*rd):>11.3f}")
    print()
    print("Read the LEVELS column first: if it is already ~0.99, an r>=0.9 target")
    print("on levels is met by persistence and measures nothing. The DELTAS column")
    print("is the real state of the art, and the honest target to raise.")


if __name__ == "__main__":
    main()
