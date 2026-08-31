"""Close the two gaps in the sweep: per-CITY, and EXITS.

hunt.py tested side x contract type x band x one conditioner at a time. It did
NOT test individual cities (only marine/inland), and it held every position to
settlement, so it said nothing about exits. Both were in the question; neither
was in the answer.

Grading is cap-corrected (pre-fix rows carry the raw threshold).
"""
import glob
import json
import math
import os
import statistics
from collections import defaultdict

CAP_FIX = "2026-08-24"
DECIDE_UTC = "17:00"
FEE = lambda pc: math.ceil(0.07 * 100 * (pc / 100) * (1 - pc / 100))
MIN_N = 20
NORM = statistics.NormalDist()


def wilson_lcb(k, n, z):
    if not n:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - m


def series():
    """(day, city) -> chronological [(at, local-ish utc hhmm, rungs, run_max)]"""
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    out = defaultdict(list)
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d, city, at = r.get("detail"), r.get("city"), r.get("at")
            if not isinstance(d, dict) or d.get("world") or not city or not at:
                continue
            if settles.get((day, city)) is None:
                continue
            out[(day, city)].append((at, d.get("rungs") or []))
    for k in out:
        out[k].sort(key=lambda x: x[0])
    return out, settles


def bottom(rungs):
    for g in rungs:
        if g.get("fl") is None and g.get("cap") is not None:
            return g
    return None


def per_city(S, settles):
    print("=" * 72)
    print("GAP 1 -- per CITY (pooled across bands; hunt.py only did marine/inland)")
    cells = defaultdict(dict)
    for (day, city), v in S.items():
        s = settles[(day, city)]
        eff = None
        for at, rungs in v:
            g = bottom(rungs)
            if not g:
                continue
            cap = g["cap"]
            eff = cap - 1 if day < CAP_FIX else cap
            na, ya = g.get("na"), g.get("ya")
            if na is not None and 1 <= na <= 98:
                cells[("NO", city)].setdefault((day, city), (na, s > eff))
            if ya is not None and 1 <= ya <= 98:
                cells[("YES", city)].setdefault((day, city), (ya, s <= eff))
            break                      # first cycle of the day only
    tested = {k: v for k, v in cells.items() if len(v) >= MIN_N}
    N = len(tested)
    z_nom, z_cor = NORM.inv_cdf(0.95), NORM.inv_cdf(1 - 0.05 / max(N, 1))
    print(f"city-slices with n >= {MIN_N}: {N}   (Bonferroni z = {z_cor:.2f})")
    hits = []
    for (side, city), u in sorted(tested.items()):
        n = len(u)
        k = sum(1 for _, w in u.values() if w)
        mp = sum(p for p, _ in u.values()) / n
        be = (mp + FEE(mp)) / 100
        if wilson_lcb(k, n, z_nom) > be:
            hits.append((side, city, n, k / n, be, wilson_lcb(k, n, z_cor)))
    print(f"clearing breakeven at nominal 95%: {len(hits)}   "
          f"(chance predicts ~{0.05*N:.0f})")
    for side, city, n, hit, be, lcbc in hits:
        print(f"    {side:4}{city:5} n={n:>3} hit={100*hit:5.1f}% be={100*be:5.1f}% "
              f"LCBcor={100*lcbc:5.1f}%{'  SURVIVES' if lcbc > be else ''}")
    if not hits:
        print("    none")


def exits(S, settles):
    print()
    print("=" * 72)
    print("GAP 2 -- EXITS (hunt.py held everything to settlement)")
    print(f"entry: NO on the bottom rung, first cycle at/after {DECIDE_UTC}Z, at the ask")
    print("exit:  sell at the NO BID k cycles later; both legs pay a fee")
    strat = defaultdict(list)
    for (day, city), v in S.items():
        s = settles[(day, city)]
        idx = next((i for i, (at, _) in enumerate(v) if at[11:16] >= DECIDE_UTC), None)
        if idx is None:
            continue
        g0 = bottom(v[idx][1])
        if not g0:
            continue
        na, cap = g0.get("na"), g0.get("cap")
        if na is None or not (1 <= na <= 98):
            continue
        eff = cap - 1 if day < CAP_FIX else cap
        entry_fee = FEE(na)
        strat["hold to settlement"].append(
            (100 - na - entry_fee) if s > eff else -(na + entry_fee))
        for k in (1, 2, 3, 4):
            j = idx + k
            if j >= len(v):
                continue
            gk = bottom(v[j][1])
            if not gk or gk.get("nb") is None or gk["nb"] <= 0:
                continue
            nb = gk["nb"]
            strat[f"exit +{k} cycle(s) at bid"].append(nb - na - entry_fee - FEE(nb))
    print()
    print(f"{'strategy':26}{'n':>5}{'mean c':>9}{'median':>9}{'95% CI':>22}")
    for name in ["hold to settlement"] + [f"exit +{k} cycle(s) at bid" for k in (1, 2, 3, 4)]:
        xs = strat.get(name) or []
        if len(xs) < 10:
            continue
        m = statistics.mean(xs)
        se = statistics.stdev(xs) / math.sqrt(len(xs))
        print(f"{name:26}{len(xs):>5}{m:>+9.2f}{statistics.median(xs):>+9.1f}"
              f"{f'[{m-1.96*se:+7.2f},{m+1.96*se:+7.2f}]':>22}")
    print()
    print("H2 refuted exits on the 18 flagged positions. This is the same question")
    print("across the whole board, and the ordering is what matters: if no exit")
    print("beats holding, expectancy really is set at entry.")


def main():
    S, settles = series()
    print(f"city-days with a settlement: {len(S)}")
    per_city(S, settles)
    exits(S, settles)


if __name__ == "__main__":
    main()
