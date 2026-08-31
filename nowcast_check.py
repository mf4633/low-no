"""Two checks on the nowcast result before it is believed.

1. CORRECTION. Ten comparisons were run (2 stations x 5 lead times). A nominal
   paired 95% CI is not the right bar for the best of ten.

2. MECHANISM. nowcast.py states a specific mechanism -- an onshore easterly
   cools KLGA before it reaches Central Park, so the EAST-WEST gradient leads
   KNYC. If the skill is the same whether or not that gradient is moving, the
   mechanism is wrong even though the nowcast works, and what is really being
   measured is generic spatial correlation. Stating it in advance is what makes
   it falsifiable, so it gets tested rather than assumed.
"""
import datetime as dt
import json
import math
import os
import statistics
from collections import defaultdict

from nowcast import HOURLY, ARCHIVE, at_or_before

NORM = statistics.NormalDist()


def load(station):
    d = os.path.join(ARCHIVE, station)
    out = {}
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        out.update(json.load(open(os.path.join(d, f))))
    return out


def paired(city, leads=(10, 20, 30, 40, 50)):
    cfg = HOURLY[city]
    hs = sorted(load(cfg["station"]).items())
    ns = {st: sorted(load(st).items()) for st in cfg["neighbours"]}
    ns = {k: v for k, v in ns.items() if v}
    res = {}
    for L in leads:
        diffs, grad = [], []
        for i in range(1, len(hs)):
            t0, v0 = hs[i - 1]
            t1, v1 = hs[i]
            d0 = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
            d1 = dt.datetime.fromisoformat(t1.replace("Z", "+00:00"))
            if not (40 <= (d1 - d0).total_seconds() / 60 <= 80):
                continue
            cut = (d1 - dt.timedelta(minutes=L)).isoformat().replace("+00:00", "Z")[:16] + "Z"
            per_side = defaultdict(list)
            deltas = []
            for st, s in ns.items():
                a, b = at_or_before(s, t0), at_or_before(s, cut)
                if not a or not b or b[0] <= a[0]:
                    continue
                deltas.append(b[1] - a[1])
                per_side[cfg["neighbours"][st]].append(b[1] - a[1])
            if not deltas:
                continue
            diffs.append(abs(v0 - v1) - abs((v0 + statistics.fmean(deltas)) - v1))
            # east-west differential MOVEMENT: how much the gradient changed
            if per_side.get("east") and per_side.get("west"):
                grad.append(statistics.fmean(per_side["east"])
                            - statistics.fmean(per_side["west"]))
            else:
                grad.append(None)
        res[L] = (diffs, grad)
    return res


def main():
    all_res = {c: paired(c) for c in HOURLY}
    tests = sum(len(v) for v in all_res.values())
    z_cor = NORM.inv_cdf(1 - 0.05 / tests)
    print(f"{tests} comparisons run -> Bonferroni z = {z_cor:.2f} (nominal 1.96)\n")
    print(f"{'city':5}{'lead':>6}{'n':>6}{'mean gain':>11}{'95% CI':>20}"
          f"{'corrected CI':>22}  verdict")
    for c, res in all_res.items():
        for L, (diffs, _) in sorted(res.items()):
            n = len(diffs)
            if n < 10:
                continue
            m = statistics.fmean(diffs)
            se = statistics.stdev(diffs) / math.sqrt(n)
            lo, hi = m - 1.96 * se, m + 1.96 * se
            clo, chi = m - z_cor * se, m + z_cor * se
            v = "SURVIVES" if clo > 0 else ("nominal only" if lo > 0 else "no")
            print(f"{c:5}{L:>5}m{n:>6}{m:>+10.2f}F"
                  f"{f'[{lo:+.2f},{hi:+.2f}]':>20}{f'[{clo:+.2f},{chi:+.2f}]':>22}  {v}")

    print("\nMECHANISM TEST -- is it the east-west gradient, or generic correlation?")
    print("Split NYC's 20-minute-lead cases by whether the E-W differential moved.")
    diffs, grad = all_res["NYC"][20]
    pairs = [(d, g) for d, g in zip(diffs, grad) if g is not None]
    if not pairs:
        print("  no gradient data")
        return
    mags = sorted(abs(g) for _, g in pairs)
    cut = mags[len(mags) // 2]
    moving = [d for d, g in pairs if abs(g) >= cut]
    still = [d for d, g in pairs if abs(g) < cut]
    print(f"  median |E-W movement| = {cut:.2f}F over the interval")
    for lbl, xs in (("gradient MOVING", moving), ("gradient still", still)):
        if len(xs) < 10:
            continue
        m = statistics.fmean(xs)
        se = statistics.stdev(xs) / math.sqrt(len(xs))
        print(f"  {lbl:18} n={len(xs):>3}  gain {m:+.2f}F  "
              f"[{m-1.96*se:+.2f},{m+1.96*se:+.2f}]")
    if len(moving) >= 10 and len(still) >= 10:
        dm = statistics.fmean(moving) - statistics.fmean(still)
        sp = math.sqrt(statistics.variance(moving) / len(moving)
                       + statistics.variance(still) / len(still))
        print(f"\n  difference: {dm:+.2f}F  [{dm-1.96*sp:+.2f},{dm+1.96*sp:+.2f}]")
        if dm - 1.96 * sp > 0:
            print("  -> skill CONCENTRATES where the gradient moves. Mechanism supported.")
        else:
            print("  -> skill does NOT concentrate on gradient movement. The nowcast")
            print("     works, but the sea-breeze mechanism as written is NOT what is")
            print("     driving it -- this is closer to generic spatial correlation.")


if __name__ == "__main__":
    main()
