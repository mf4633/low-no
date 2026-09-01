"""When a neighbour goes stale, is it better to DROP it or EXTRAPOLATE it?

Michael's idea: rather than discarding a stale station, project it forward from
its own recent tendency and weight it by how stale it is. Worth testing rather
than assuming, because the interpolator has now falsified three plausible
mechanisms (sea breeze, upwind weighting, transit matching) and the dull option
has won every time.

METHOD. The archive holds complete 5-minute neighbour data, so staleness can be
SIMULATED exactly: at each host transition, pretend a given fraction of
neighbours last reported S minutes before the target time, and compare
strategies on the resulting next-print error. Every strategy sees identical
data, so the comparison is like-for-like.

  DROP          exclude the stale ones (current behaviour after hardening)
  NAIVE         use their last value as if it were current (the ORIGINAL bug --
                included as the baseline both others must beat)
  EXTRAP        project each stale neighbour forward at its own rate over the
                20 minutes before it went quiet
  EXTRAP+CONF   same, but weighted w = 1/(1 + S/30) so a 30-minute-stale
                station counts half. Parameter chosen for shape, not fitted;
                the sweep over S is what carries the answer.

If DROP wins, the hardening is right as written and nothing changes.
"""
import datetime as dt
import json
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


def rate_before(series, ts, back_min=20):
    """The neighbour's own F/hr over the `back_min` before ts."""
    b = at_or_before(series, ts)
    if not b:
        return None
    t0 = (dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
          - dt.timedelta(minutes=back_min)).isoformat().replace("+00:00", "Z")[:16] + "Z"
    a = at_or_before(series, t0)
    if not a or a[0] >= b[0]:
        return None
    dh = ((dt.datetime.fromisoformat(b[0].replace("Z", "+00:00"))
           - dt.datetime.fromisoformat(a[0].replace("Z", "+00:00"))).total_seconds() / 3600.0)
    return (b[1] - a[1]) / dh if dh > 0 else None


def run(city, lead=20, stale_min=30, frac=0.5):
    cfg = HOURLY[city]
    hs = [(k, temp_of(v)) for k, v in sorted(load(cfg["station"]).items())
          if temp_of(v) is not None]
    ns = {st: [(k, temp_of(v)) for k, v in sorted(load(st).items())
               if temp_of(v) is not None] for st in cfg["neighbours"]}
    ns = {k: v for k, v in ns.items() if v}
    sts = sorted(ns)
    n_stale = max(1, int(round(frac * len(sts))))
    err = {k: [] for k in ("perfect", "drop", "naive", "extrap", "extrap_conf")}
    for i in range(1, len(hs)):
        t0, v0 = hs[i - 1]
        t1, v1 = hs[i]
        d0 = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        d1 = dt.datetime.fromisoformat(t1.replace("Z", "+00:00"))
        if not (40 <= (d1 - d0).total_seconds() / 60 <= 80):
            continue
        cut = (d1 - dt.timedelta(minutes=lead)).isoformat().replace("+00:00", "Z")[:16] + "Z"
        # deterministic rotation of which stations are stale, so every
        # transition is a different draw but the sequence is reproducible
        stale = set(sts[(i % len(sts)):] + sts[:(i % len(sts))][:0])
        stale = set((sts * 2)[i % len(sts): i % len(sts) + n_stale])
        cutS = (dt.datetime.fromisoformat(cut.replace("Z", "+00:00"))
                - dt.timedelta(minutes=stale_min)).isoformat().replace("+00:00", "Z")[:16] + "Z"
        pools = {k: [] for k in err}
        weights = {k: [] for k in err}
        for st in sts:
            base = at_or_before(ns[st], t0)
            if not base:
                continue
            fresh = at_or_before(ns[st], cut)
            if fresh and fresh[0] > base[0]:
                pools["perfect"].append(fresh[1] - base[1]); weights["perfect"].append(1)
            if st not in stale:
                if fresh and fresh[0] > base[0]:
                    for k in ("drop", "naive", "extrap", "extrap_conf"):
                        pools[k].append(fresh[1] - base[1]); weights[k].append(1)
                continue
            old = at_or_before(ns[st], cutS)
            if not old or old[0] <= base[0]:
                continue
            pools["naive"].append(old[1] - base[1]); weights["naive"].append(1)
            r = rate_before(ns[st], cutS)
            if r is None:
                continue
            proj = old[1] + r * (stale_min / 60.0)
            pools["extrap"].append(proj - base[1]); weights["extrap"].append(1)
            pools["extrap_conf"].append(proj - base[1])
            weights["extrap_conf"].append(1.0 / (1.0 + stale_min / 30.0))
        for k in err:
            if len(pools[k]) >= 3:
                w = weights[k]
                pred = v0 + sum(p * q for p, q in zip(pools[k], w)) / sum(w)
                err[k].append(abs(pred - v1))
    return {k: (len(v), statistics.fmean(v)) for k, v in err.items() if len(v) >= 20}


def main():
    print("Simulated staleness. 'perfect' = no staleness, the unreachable ceiling.\n")
    for city in HOURLY:
        for frac in (0.3, 0.6):
            print(f"{city}  {int(100*frac)}% of neighbours stale")
            print(f"  {'stale by':>9}{'perfect':>10}{'drop':>9}{'naive':>9}"
                  f"{'extrap':>9}{'extrap+conf':>13}   best")
            for S in (15, 30, 45, 60):
                r = run(city, stale_min=S, frac=frac)
                if "drop" not in r:
                    continue
                cells = {k: r[k][1] for k in r}
                best = min((v, k) for k, v in cells.items() if k != "perfect")[1]
                row = "".join(f"{cells.get(k, float('nan')):>9.2f}" if k != "extrap_conf"
                              else f"{cells.get(k, float('nan')):>13.2f}"
                              for k in ("perfect", "drop", "naive", "extrap", "extrap_conf"))
                print(f"  {S:>7}m{row}   {best}")
            print()


if __name__ == "__main__":
    main()
