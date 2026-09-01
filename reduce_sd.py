"""Can anything reduce the nowcast's RESIDUAL SD? Backtested, leave-one-day-out.

The target is residual sd -- the spread of (actual next print - nowcast) -- not
the ensemble spread, which spread_ci.py showed does not predict error. DEN sits
at 2.25F, which is what makes the 95% band nine degrees wide.

Five candidates. The first three are parameter-free; the last two are fitted and
therefore scored leave-one-DAY-out, because transitions within a day share
weather and leaving out single observations would leak.

  mean          the incumbent
  median        robust to one bad station
  trimmed       drop the highest and lowest delta, then mean
  no_precip     exclude neighbours reporting precipitation in the last hour --
                evaporative cooling and downdrafts make a raining station's
                temperature unrepresentative of a dry host
  topK_skill    keep only the K neighbours whose deltas have historically
                tracked the host's best, K swept, skill measured on TRAINING
                days only

Prior is against all of this: wind weighting, inverse distance, elevation and
free OLS weights have all already lost to the plain mean, because the neighbours
are near-exchangeable. Included anyway because "which stations to trust" is a
different question from "where are they".
"""
import datetime as dt
import json
import math
import os
import statistics
from collections import defaultdict

from nowcast import HOURLY, ARCHIVE, at_or_before, temp_of


def load(st):
    d = os.path.join(ARCHIVE, st)
    o = {}
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            o.update(json.load(open(os.path.join(d, f))))
    return o


def field(rec, k):
    return None if isinstance(rec, (int, float)) else (rec or {}).get(k)


def samples(city, lead=20):
    """[(day, actual_delta, {st: (delta, precip)})]"""
    cfg = HOURLY[city]
    raw = {st: sorted(load(st).items()) for st in cfg["neighbours"]}
    ser = {st: [(k, temp_of(v)) for k, v in s if temp_of(v) is not None]
           for st, s in raw.items()}
    hs = [(k, temp_of(v)) for k, v in sorted(load(cfg["station"]).items())
          if temp_of(v) is not None]
    out = []
    for i in range(1, len(hs)):
        t0, v0 = hs[i - 1]
        t1, v1 = hs[i]
        d0 = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        d1 = dt.datetime.fromisoformat(t1.replace("Z", "+00:00"))
        if not (40 <= (d1 - d0).total_seconds() / 60 <= 80):
            continue
        cut = (d1 - dt.timedelta(minutes=lead)).isoformat().replace("+00:00", "Z")[:16] + "Z"
        per = {}
        for st in ser:
            a, b = at_or_before(ser[st], t0), at_or_before(ser[st], cut)
            if not a or not b or b[0] <= a[0]:
                continue
            pr = None
            for ts, rr in reversed(raw[st]):
                if ts <= cut:
                    pr = field(rr, "pr")
                    break
            per[st] = (b[1] - a[1], pr)
        if len(per) >= 3:
            out.append((t1[:10], v1 - v0, per))
    return out


def agg(per, how, keep=None):
    ds = [d for st, (d, pr) in per.items()
          if (keep is None or st in keep)
          and not (how == "no_precip" and pr not in (None, 0))]
    if len(ds) < 3:
        ds = [d for st, (d, _) in per.items() if keep is None or st in keep]
    if len(ds) < 2:
        return None
    if how == "median":
        return statistics.median(ds)
    if how == "trimmed" and len(ds) >= 4:
        return statistics.fmean(sorted(ds)[1:-1])
    return statistics.fmean(ds)


def main():
    for city in HOURLY:
        S = samples(city)
        if len(S) < 40:
            continue
        days = sorted({d for d, _, _ in S})
        print(f"\n{city}  n={len(S)} transitions over {len(days)} days")
        print(f"  {'method':16}{'residual sd':>13}{'MAE':>8}{'vs mean':>10}")
        base = None
        for how in ("mean", "median", "trimmed", "no_precip"):
            e = [a - agg(p, how) for _, a, p in S if agg(p, how) is not None]
            sd, mae = statistics.pstdev(e), statistics.fmean(abs(x) for x in e)
            if how == "mean":
                base = sd
            print(f"  {how:16}{sd:>13.2f}{mae:>8.2f}"
                  f"{(sd-base):>+10.2f}")
        # top-K by skill, leave-one-DAY-out
        for K in (3, 5, 7):
            if K >= len(HOURLY[city]["neighbours"]):
                continue
            e = []
            for day in days:
                tr = [(a, p) for d, a, p in S if d != day]
                if len(tr) < 20:
                    continue
                sk = defaultdict(list)
                for a, p in tr:
                    for st, (dd, _) in p.items():
                        sk[st].append(abs(dd - a))
                rank = sorted(sk, key=lambda st: statistics.fmean(sk[st]))[:K]
                for d, a, p in S:
                    if d != day:
                        continue
                    g = agg(p, "mean", keep=set(rank))
                    if g is not None:
                        e.append(a - g)
            if len(e) >= 40:
                sd = statistics.pstdev(e)
                print(f"  {'topK skill K=' + str(K):16}{sd:>13.2f}"
                      f"{statistics.fmean(abs(x) for x in e):>8.2f}{(sd-base):>+10.2f}")
    print("\n'vs mean' negative = better than the incumbent. Fitted rows are")
    print("leave-one-day-out, so their numbers are out-of-sample.")


if __name__ == "__main__":
    main()
