"""Hypothesis 4b -- does the market LAG the diurnal-curve deviation?

WRITTEN 2026-08-27, BEFORE ANY curve_dev DATA EXISTED. That is deliberate: a
test authored after seeing the data it judges is not a test. Nothing in this
file may be tuned once data arrives; if it needs changing, the change is
recorded in CANDIDATE.md with a reason, like every other correction here.

The claim (Michael's desk observation): markets reprice midday when the
temperature trajectory departs from the day's expected curve. If repricing
LAGS the deviation, a deviation at cycle t predicts the price move from t to
t+1. If the market is efficient, the move happens WITH the deviation (t-1 to
t) and nothing is left to trade.

Direction: curve_dev rising = running hotter than forecast = more likely to
exceed the cap = the NO contract is worth MORE. So a lag implies a POSITIVE
correlation between d(curve_dev) at t and d(price) from t to t+1.

Refuses to report unless the registered data bar is met:
    >= 200 events AND >= 20 distinct days
"""
import json, glob, os, math, statistics, datetime as dt, zoneinfo
from collections import defaultdict
from lowno.config import CITIES

MIN_EVENTS, MIN_DAYS = 200, 20
MATERIAL = 1.0        # |d(curve_dev)| in F that counts as an event
GAP_LO, GAP_HI = 0.5, 2.5     # hours between consecutive cycles


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def fisher_ci(r, n, z=1.96):
    """95% CI for a correlation, so 'positive' means something."""
    if r is None or n < 4 or abs(r) >= 1:
        return (None, None)
    zf = 0.5 * math.log((1 + r) / (1 - r))
    se = 1 / math.sqrt(n - 3)
    lo, hi = zf - z * se, zf + z * se
    t = lambda v: (math.exp(2 * v) - 1) / (math.exp(2 * v) + 1)
    return (round(t(lo), 3), round(t(hi), 3))


def series():
    """city-day -> chronological [(hour, curve_dev, price, run_max, cap)]."""
    out = defaultdict(list)
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("verdict") != "LADDER":
                continue
            d = r.get("detail") or {}
            city = r.get("city")
            if d.get("world") or city not in CITIES:
                continue
            dev = d.get("curve_dev")
            if dev is None:
                continue
            bottom = None
            for g in d.get("rungs", []):
                if g.get("fl") is None and g.get("cap") is not None:
                    bottom = g
                    break
            if not bottom or bottom.get("na") is None:
                continue
            na, nb = bottom["na"], bottom.get("nb")
            # na == 100 is "no offer", not a price (see H3 result). Use the mid
            # when both sides are real, else the ask.
            if na >= 100:
                continue
            price = (na + nb) / 2.0 if (nb is not None and 0 < nb < 100) else float(na)
            try:
                lt = (dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
                        .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])))
            except Exception:
                continue
            out[(day, city)].append((lt.hour + lt.minute / 60.0, dev, price,
                                     d.get("run_max"), bottom["cap"]))
    for k in out:
        out[k].sort(key=lambda x: x[0])
    return out


def verdict():
    """Machine-readable gate for autonomous pilot activation.

    PASSES only when the LAG correlation's 95% CI excludes zero on the
    registered data bar. Conditions fixed before any curve_dev data existed.
    """
    try:
        S = series()
        events = _events(S)
    except Exception as e:
        return dict(id="H4b", ready=False, passed=False, error=str(e)[:120])
    days = {e["day"] for e in events}
    if len(events) < MIN_EVENTS or len(days) < MIN_DAYS:
        return dict(id="H4b", ready=False, passed=False,
                    events=len(events), need_events=MIN_EVENTS,
                    days=len(days), need_days=MIN_DAYS,
                    reason="data bar not met")
    dd = [e["ddev"] for e in events]
    rn = pearson(dd, [e["move_next"] for e in events])
    lo, hi = fisher_ci(rn, len(events))
    return dict(id="H4b", ready=True,
                passed=bool(lo is not None and lo > 0),
                events=len(events), days=len(days),
                lag_corr=(round(rn, 3) if rn is not None else None),
                lag_ci=[lo, hi])


def _events(S):
    events = []
    for (day, city), v in S.items():
        for i in range(1, len(v) - 1):
            h0, d0, p0, _, _ = v[i - 1]
            h1, d1, p1, rm, cap = v[i]
            h2, d2, p2, _, _ = v[i + 1]
            if not (GAP_LO <= h1 - h0 <= GAP_HI and GAP_LO <= h2 - h1 <= GAP_HI):
                continue
            ddev = d1 - d0
            if abs(ddev) < MATERIAL:
                continue
            events.append(dict(day=day, city=city, hour=h1, ddev=ddev,
                               move_with=p1 - p0, move_next=p2 - p1))
    return events


def main():
    S = series()
    events = _events(S)
    days = {e["day"] for e in events}
    print(f"H4b events: {len(events)} (bar {MIN_EVENTS}) over "
          f"{len(days)} distinct days (bar {MIN_DAYS})")
    if len(events) < MIN_EVENTS or len(days) < MIN_DAYS:
        print("DATA BAR NOT MET -- refusing to report a result. "
              "This is the registered behaviour, not a failure.")
        return

    dd = [e["ddev"] for e in events]
    rw = pearson(dd, [e["move_with"] for e in events])
    rn = pearson(dd, [e["move_next"] for e in events])
    print(f"\n{'window':>26} {'corr':>8} {'95% CI':>18}")
    print(f"{'contemporaneous (t-1->t)':>26} {rw:>8.3f} "
          f"{str(fisher_ci(rw, len(events))):>18}")
    print(f"{'LAG (t->t+1)':>26} {rn:>8.3f} "
          f"{str(fisher_ci(rn, len(events))):>18}")

    lo, _ = fisher_ci(rn, len(events))
    print("\nverdict on the registered claim:")
    if lo is not None and lo > 0:
        print("  LAG CORRELATION IS POSITIVE with a 95% CI excluding zero.")
        print("  This is the necessary condition, NOT a trading result: an edge")
        print("  still has to survive fees, depth and the 60-unit bar.")
    else:
        print("  No positive lag correlation distinguishable from zero.")
        print("  The market moves WITH the deviation, not after it -- the")
        print("  observation is real but not exploitable on this evidence.")

    # Direction split, since a lag might exist only one way (heat vs cooling).
    print(f"\n{'subset':>18} {'n':>5} {'mean move_next':>16}")
    for name, f in (("dev rising", lambda e: e["ddev"] > 0),
                    ("dev falling", lambda e: e["ddev"] < 0)):
        g = [e["move_next"] for e in events if f(e)]
        if len(g) >= 10:
            print(f"{name:>18} {len(g):>5} {statistics.mean(g):>15.2f}c")


if __name__ == "__main__":
    main()
