"""Should the nowcast be projected forward to the target, or held flat?

The live reading is AS OF the alignment target, which trails real time by the
API lag -- 22 minutes when Michael asked. Holding it flat implicitly assumes the
temperature stopped moving at that instant, which on a morning warming curve is
obviously false.

This is NOT the extrapolation rejected in stale_test.py. That projected
individual STALE NEIGHBOURS forward to fill gaps the surviving neighbours had
already covered -- redundant, so nothing to recover. Here there is no other
source for the interval past the target, so the information genuinely is missing
rather than duplicated.

Framed as the validated question: predicting the host's NEXT PRINT. At a cutoff
L minutes before the print, compare

    FLAT       predict the print equals the nowcast at the cutoff
    PROJECTED  carry the observed rate forward across the remaining L minutes
    DAMPED     carry HALF the rate, since a warming curve decelerates and a
               linear carry must overshoot near the peak

If FLAT wins, the current behaviour is right and the live reading only needs
relabelling. If PROJECTED wins, the module should return a projected value too.
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


def run(city, leads=(10, 20, 30, 40, 50)):
    cfg = HOURLY[city]
    hs = [(k, temp_of(v)) for k, v in sorted(load(cfg["station"]).items())
          if temp_of(v) is not None]
    ns = {st: [(k, temp_of(v)) for k, v in sorted(load(st).items())
               if temp_of(v) is not None] for st in cfg["neighbours"]}
    ns = {k: v for k, v in ns.items() if v}
    out = {}
    for L in leads:
        err = {"flat": [], "projected": [], "damped": []}
        for i in range(1, len(hs)):
            t0, v0 = hs[i - 1]
            t1, v1 = hs[i]
            d0 = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
            d1 = dt.datetime.fromisoformat(t1.replace("Z", "+00:00"))
            gap = (d1 - d0).total_seconds() / 60
            if not (40 <= gap <= 80):
                continue
            cut_dt = d1 - dt.timedelta(minutes=L)
            cut = cut_dt.isoformat().replace("+00:00", "Z")[:16] + "Z"
            ds = []
            for st, s in ns.items():
                a, b = at_or_before(s, t0), at_or_before(s, cut)
                if a and b and b[0] > a[0]:
                    ds.append(b[1] - a[1])
            if not ds:
                continue
            nc = v0 + statistics.fmean(ds)
            win_h = (cut_dt - d0).total_seconds() / 3600
            if win_h <= 0:
                continue
            rate = (nc - v0) / win_h                       # F/hr over the window
            err["flat"].append(abs(nc - v1))
            err["projected"].append(abs(nc + rate * (L / 60) - v1))
            err["damped"].append(abs(nc + 0.5 * rate * (L / 60) - v1))
        if len(err["flat"]) >= 20:
            out[L] = err
    return out


def main():
    for city in HOURLY:
        print(f"\n{city}")
        print(f"  {'lead':>6}{'n':>6}{'flat':>9}{'projected':>12}{'damped':>9}"
              f"{'best':>12}{'proj - flat':>26}")
        for L, err in sorted(run(city).items()):
            n = len(err["flat"])
            m = {k: statistics.fmean(v) for k, v in err.items()}
            best = min(m, key=m.get)
            diff = [p - f for p, f in zip(err["projected"], err["flat"])]
            md = statistics.fmean(diff)
            se = statistics.stdev(diff) / math.sqrt(n) if n > 1 else 0
            print(f"  {L:>4}m{n:>6}{m['flat']:>9.2f}{m['projected']:>12.2f}"
                  f"{m['damped']:>9.2f}{best:>12}"
                  f"{f'{md:+.2f} [{md-1.96*se:+.2f},{md+1.96*se:+.2f}]':>26}")
    print("\n'proj - flat' positive means projecting is WORSE. The lead IS the")
    print("projection distance, so the 50m row is the honest analogue of a live")
    print("reading that is ~20-50 minutes behind real time.")


if __name__ == "__main__":
    main()
