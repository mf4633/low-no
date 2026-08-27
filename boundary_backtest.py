"""Hypothesis 3 -- the test. Rule fixed in CANDIDATE.md before this file existed.

Universe: bottom-rung cycles at/after the station's measured convergence hour
with 0 <= (cap - run_max) <= 3 (the boundary zone).
Signal:  p_emp = empirical.p_exceed(...)   p_mkt = no_ask / 100
Trade:   buy NO when p_emp - p_mkt >= D, D in {0.05, 0.10, 0.15} only.
One unit per city-day (first qualifying cycle), entry at the ASK, held to
settlement, Kalshi fees. Also reports market calibration inside the zone,
which is the direct test of failure mode 2.
"""
import json, glob, os, math, datetime as dt, zoneinfo
from lowno import empirical, convergence
from lowno.config import CITIES

FEE_RATE = 0.07
DS = (0.05, 0.10, 0.15)
ZONE = 3


def fee(p):
    return math.ceil(FEE_RATE * 100 * (p / 100) * (1 - p / 100))


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def main():
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    verified = set(json.load(open("docs/settlements_verified.json")))
    samples = empirical._raw_climbs()
    conv = (convergence.build() or {}).get("convergence_hour_local", {})

    cands = []
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
            if d.get("world") or city not in CITIES or d.get("run_max") is None:
                continue
            s = settles.get((day, city))
            if s is None:
                continue
            try:
                u = dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
                hour = u.astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])).hour
            except Exception:
                continue
            ch = conv.get(city)
            if ch is None or hour < ch:
                continue
            for g in d.get("rungs", []):
                if g.get("fl") is not None or g.get("cap") is None or g.get("na") is None:
                    continue
                # na == 100 is NOT a price: Kalshi returns it when no ask
                # exists. Buying NO at 100c cannot profit, and treating it as
                # "market implies 100%" corrupted the calibration table on the
                # first run (46 of 75 zone cycles were this artifact). Excluded
                # as a correctness fix; the registered rule is unchanged.
                if g["na"] >= 100:
                    continue
                cap, rm = g["cap"], d["run_max"]
                need = cap - rm
                if not (0 <= need <= ZONE):
                    continue
                pe = empirical.p_exceed(city, hour, rm, cap, samples=samples)
                if not pe or pe.get("p") is None:
                    continue
                cands.append(dict(day=day, city=city, at=r["at"], cap=cap,
                                  run_max=rm, need=need, price=g["na"],
                                  p_emp=pe["p"], p_mkt=g["na"] / 100.0,
                                  settle=s, won=s > cap,
                                  clean=f"{day}|{city}" in verified))
                break

    if not cands:
        print("no boundary-zone candidates")
        return
    cands.sort(key=lambda x: x["at"])

    # Failure mode 2, tested directly: is the market calibrated in this zone?
    print(f"boundary-zone cycles (0 <= cap-run_max <= {ZONE}, at/after convergence): "
          f"{len(cands)}")
    print("\nMARKET CALIBRATION INSIDE THE ZONE (one row per price bucket)")
    print(f"{'no_ask':>8} {'n':>4} {'realized':>9} {'implied':>8} {'edge':>7}")
    buckets = [(1, 50), (51, 80), (81, 90), (91, 95), (96, 98), (99, 100)]
    for lo, hi in buckets:
        g = [c for c in cands if lo <= c["price"] <= hi]
        if not g:
            continue
        w = sum(1 for c in g if c["won"])
        imp = sum(c["p_mkt"] for c in g) / len(g)
        print(f"{lo:>3}-{hi:<4} {len(g):>4} {100*w/len(g):>8.0f}% "
              f"{100*imp:>7.0f}% {100*(w/len(g)-imp):>+6.0f}")

    print("\nMODEL vs MARKET in the zone")
    de = [c["p_emp"] - c["p_mkt"] for c in cands]
    print(f"  mean(p_emp - p_mkt) = {sum(de)/len(de):+.3f}   "
          f"model higher on {100*sum(1 for x in de if x>0)/len(de):.0f}% of cycles")

    print(f"\n{'rule':>16} {'n':>4} {'w':>4} {'hit':>7} {'need':>7} {'LCB':>7} "
          f"{'meanP&L':>9} {'clean_n':>8}")
    for D in DS:
        taken, seen = [], set()
        for c in cands:
            if c["p_emp"] - c["p_mkt"] < D:
                continue
            k = (c["day"], c["city"])
            if k in seen:
                continue
            seen.add(k)
            taken.append(c)
        n = len(taken)
        if n == 0:
            print(f"{'D>=%.2f' % D:>16} {0:>4}")
            continue
        w = sum(1 for c in taken if c["won"])
        pnl = sum(((100 - c["price"]) - fee(c["price"])) if c["won"] else -c["price"]
                  for c in taken)
        mp = sum(c["price"] for c in taken) / n
        f_ = math.ceil(FEE_RATE * 100 * (mp / 100) * (1 - mp / 100))
        be = mp / (100 - f_)
        lo_, _ = wilson(w, n)
        cn = sum(1 for c in taken if c["clean"])
        print(f"{'D>=%.2f' % D:>16} {n:>4} {w:>4} {100*w/n:>6.0f}% {100*be:>6.1f}% "
              f"{100*lo_:>6.0f}% {pnl/n:>8.2f}c {cn:>8}")

    # Failure mode 5: post-fix days only.
    print("\nSAME RULES, POST-2026-08-27 SETTLEMENTS ONLY (out-of-sample check)")
    oos = [c for c in cands if c["day"] > "2026-08-27"]
    print(f"  available out-of-sample cycles: {len(oos)}")


if __name__ == "__main__":
    main()
