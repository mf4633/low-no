"""Hypothesis 2 (early exit) -- the test. Rule fixed in CANDIDATE.md BEFORE this
file was written; nothing here may be tuned after seeing output.

Universe: the strategy's actual instrument -- the first cycle each city-day
where the bottom-rung NO ask sits in 96-98c. Entry at that ASK.

Exits execute at the logged NO BID (`nb`), never the ask. A winner exited early
counts as a win of only the exit price. No lookahead: the decision at cycle t
uses only run_max/quotes available at t, and the empirical climb distribution.

Prints hold-to-settlement alongside each exit variant on identical units.
"""
import json, glob, os, math, datetime as dt, zoneinfo
from lowno import empirical
from lowno.config import CITIES

FEE_RATE = 0.07
THRESHOLDS = (0.05, 0.10, 0.20)     # declared in CANDIDATE.md, not expanded
BASELINE_HOUR = 16                  # naive 16:00-local comparison


def fee(p):
    return math.ceil(FEE_RATE * 100 * (p / 100) * (1 - p / 100))


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m)


def local_hour(at, city):
    try:
        u = dt.datetime.fromisoformat(at).replace(tzinfo=dt.timezone.utc)
        return u.astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])).hour
    except Exception:
        return None


def paths():
    """city-day -> chronological list of bottom-rung snapshots."""
    out = {}
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
            if d.get("world"):
                continue
            city = r.get("city")
            if city not in CITIES:
                continue
            for g in d.get("rungs", []):
                if g.get("fl") is not None or g.get("cap") is None:
                    continue
                if g.get("na") is None:
                    continue
                out.setdefault((day, city), []).append(dict(
                    at=r["at"], cap=g["cap"], na=g["na"], nb=g.get("nb"),
                    run_max=d.get("run_max"),
                    hour=local_hour(r["at"], city)))
                break
    for k in out:
        out[k].sort(key=lambda x: x["at"])
    return out


def main():
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    samples = empirical._raw_climbs()
    P = paths()

    units = []
    for (day, city), snaps in P.items():
        s = settles.get((day, city))
        if s is None:
            continue
        entry = next((x for x in snaps if 96 <= x["na"] <= 98), None)
        if entry is None:
            continue
        after = [x for x in snaps if x["at"] > entry["at"]]
        units.append(dict(day=day, city=city, cap=entry["cap"],
                          price=entry["na"], settle=s,
                          won=s > entry["cap"], after=after))

    if not units:
        print("no units")
        return

    def hold(u):
        return (100 - u["price"]) - fee(u["price"]) if u["won"] else -u["price"]

    def exit_pnl(u, decide):
        """decide(snapshot) -> True to exit at that snapshot's NO bid."""
        for x in u["after"]:
            if x["nb"] is None or x["run_max"] is None:
                continue
            if x["run_max"] > u["cap"]:
                continue          # already won: never exit a locked winner cheap
            if decide(x, u):
                px = x["nb"]
                # sell at the bid: proceeds px, cost basis entry ask
                return px - u["price"], x["hour"], px
        return hold(u), None, None

    def p_rule(T):
        def f(x, u):
            r = empirical.p_exceed(u["city"], x["hour"], x["run_max"], u["cap"],
                                   samples=samples)
            return r is not None and r.get("p") is not None and r["p"] < T
        return f

    def hour_rule(h):
        return lambda x, u: x["hour"] is not None and x["hour"] >= h

    n = len(units)
    wins = sum(1 for u in units if u["won"])
    hp = [hold(u) for u in units]
    print(f"units (first 96-98c cycle per city-day, settled): {n}, "
          f"{wins} eventual wins ({100*wins/n:.0f}%)")
    print(f"mean entry ask {sum(u['price'] for u in units)/n:.1f}c\n")
    print(f"{'strategy':>22} {'n':>4} {'exits':>6} {'meanP&L':>9} {'total':>9} "
          f"{'cutW':>5} {'LCB':>6}")

    def report(label, res):
        pnls = [r[0] for r in res]
        exits = sum(1 for r in res if r[1] is not None)
        cutw = sum(1 for r, u in zip(res, units) if r[1] is not None and u["won"])
        profitable = sum(1 for p in pnls if p > 0)
        print(f"{label:>22} {n:>4} {exits:>6} {sum(pnls)/n:>8.2f}c "
              f"{sum(pnls):>8.0f}c {cutw:>5} {100*wilson(profitable, n):>5.0f}%")

    report("hold_to_settlement", [(p, None, None) for p in hp])
    for T in THRESHOLDS:
        report(f"exit_p<{T:.2f}", [exit_pnl(u, p_rule(T)) for u in units])
    report(f"exit_hour>={BASELINE_HOUR}", [exit_pnl(u, hour_rule(BASELINE_HOUR))
                                           for u in units])

    # Failure mode 1/2 diagnostics: is there anything to sell, and at what price,
    # on the units that actually lost?
    losers = [u for u in units if not u["won"]]
    print(f"\nLOSERS ({len(losers)}): what the bid offered after entry")
    for u in losers:
        bids = [(x["hour"], x["nb"]) for x in u["after"] if x["nb"] is not None]
        best = max((b for _, b in bids), default=None)
        late = [b for h, b in bids if h is not None and h >= 15]
        print(f"  {u['day']} {u['city']:4} entry {u['price']}c settle {u['settle']} "
              f"cap {u['cap']} | best bid after entry {best} | "
              f"late(>=15h) bids {late[:6]}")


if __name__ == "__main__":
    main()
