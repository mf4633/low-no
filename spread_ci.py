"""Does neighbour spread predict nowcast error? If so the interval should breathe.

Michael asked for the nowcast to carry a +/- range. Two candidates for the sigma
and they are not the same thing:

  ENSEMBLE SPREAD   how much the neighbours disagree with each other. Cheap,
                    available live, but it measures internal disagreement, not
                    error against the truth.
  RESIDUAL SD       the measured spread of (actual next print - nowcast). This
                    is the right basis for an interval, but it is a constant
                    unless something conditions it.

The useful question is whether the first predicts the second. If a wide ensemble
reliably precedes a big miss, the interval can widen exactly when it should --
and today is suggestive: DEN's spread hit 3.39F, the highest recorded, right
around the worst miss of the day.

Tested by binning transitions on spread and measuring residual sd within each
bin. If the bins are flat, use a fixed interval and say so.
"""
import datetime as dt
import json
import math
import os
import statistics

from nowcast import HOURLY, ARCHIVE, at_or_before, temp_of


def load(st):
    d = os.path.join(ARCHIVE, st)
    o = {}
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            o.update(json.load(open(os.path.join(d, f))))
    return o


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
        if len(ds) < 3:
            continue
        nc = v0 + statistics.fmean(ds)
        out.append((statistics.pstdev(ds), v1 - nc))
    return out


def pearson(xs, ys):
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return None if sx == 0 or sy == 0 else sum(
        (x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def main():
    for city in HOURLY:
        r = rows(city)
        if len(r) < 40:
            continue
        r.sort()
        n = len(r)
        print(f"\n{city}  n={n}")
        print(f"  {'spread bin':18}{'n':>5}{'mean spread':>13}{'residual sd':>14}"
              f"{'mean |err|':>12}")
        k = 3
        for j in range(k):
            chunk = r[j * n // k:(j + 1) * n // k]
            sp = [a for a, _ in chunk]
            er = [b for _, b in chunk]
            lab = f"{'low' if j==0 else 'mid' if j==1 else 'high'} ({sp[0]:.2f}-{sp[-1]:.2f})"
            print(f"  {lab:18}{len(chunk):>5}{statistics.fmean(sp):>13.2f}"
                  f"{statistics.pstdev(er):>14.2f}{statistics.fmean(abs(e) for e in er):>12.2f}")
        rr = pearson([a for a, _ in r], [abs(b) for _, b in r])
        se = 1 / math.sqrt(len(r) - 3)
        z = 0.5 * math.log((1 + rr) / (1 - rr))
        lo, hi = (math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se))
        print(f"  corr(spread, |error|) = {rr:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]"
              + ("   PREDICTIVE" if lo > 0 else "   not distinguishable from zero"))
        allsd = statistics.pstdev([b for _, b in r])
        print(f"  overall residual sd = {allsd:.2f}F  -> fixed +/-2sd = +/-{2*allsd:.1f}F")


if __name__ == "__main__":
    main()
