"""If you MUST take one trade a day, which one is least bad?

A different question from "is there an edge". The edge sweep asks whether any
rule beats fee breakeven; this asks, given that abstaining is not allowed, which
single daily choice loses least. The answer can be -- and is -- negative for
every candidate, which is itself the useful output: it prices the constraint.

Rules must be decidable from ONE snapshot of the board, so the pick is made at
the first scan cycle at or after DECIDE_UTC each day. Only fields present in the
log at that moment are used: price, bid, needed climb, guide, PoP, volume,
depth. No model probability -- it is not logged, and recomputing it now would
leak the adaptive bias fitted on later days.

Grading uses the CAP-CORRECTED outcome (pre-fix rows carry the raw threshold),
because this is a decision question and the pessimistic grading exists to
protect a promotion bar, not to answer one.
"""
import glob
import json
import math
import os
import random
import statistics

DECIDE_UTC = "17:00"          # one board, one moment, every day
CAP_FIX = "2026-08-24"
FEE = lambda pc: math.ceil(0.07 * 100 * (pc / 100) * (1 - pc / 100))


def wilson_mean_ci(xs, z=1.96):
    """CI on a mean of cents -- these are not proportions, so t/normal on the
    sample sd, not Wilson."""
    n = len(xs)
    if n < 2:
        return (None, None)
    m = statistics.mean(xs)
    se = statistics.stdev(xs) / math.sqrt(n)
    return (m - z * se, m + z * se)


def snapshots():
    """day -> list of candidate rungs visible at the decision moment."""
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    out = {}
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        best = {}                       # city -> (at, detail) first at/after cut
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d, city, at = r.get("detail"), r.get("city"), r.get("at")
            if not isinstance(d, dict) or d.get("world") or not city or not at:
                continue
            if at[11:16] < DECIDE_UTC:
                continue
            if city in best and best[city][0] <= at:
                continue
            best[city] = (at, d)
        cands = []
        for city, (at, d) in best.items():
            s = settles.get((day, city))
            if s is None:
                continue
            rm, guide = d.get("run_max"), d.get("guide")
            for g in (d.get("rungs") or []):
                fl, cap, na, nb, ya = (g.get("fl"), g.get("cap"), g.get("na"),
                                       g.get("nb"), g.get("ya"))
                if fl is not None or cap is None:
                    continue            # bottom rungs only
                eff = cap - 1 if day < CAP_FIX else cap
                cands.append(dict(
                    day=day, city=city, cap=cap, eff=eff, settle=s,
                    na=na, nb=nb, ya=ya, run_max=rm, guide=guide,
                    pop=d.get("pop"), vol=g.get("vol") or 0,
                    needed=(cap - rm) if rm is not None else None,
                    G=(guide - cap) if guide is not None else None,
                    spread=(na - nb) if (na is not None and nb is not None) else None,
                    no_win=s > eff, yes_win=s <= eff))
        if cands:
            out[day] = cands
    return out


def pnl(c, side):
    px = c["na"] if side == "NO" else c["ya"]
    if px is None or not (1 <= px <= 98):
        return None
    won = c["no_win"] if side == "NO" else c["yes_win"]
    f = FEE(px)
    return (100 - px - f) if won else -(px + f)


RULES = [
    ("NO  dearest bottom <=98",  "NO",  lambda cs: max((c for c in cs if c["na"] and c["na"] <= 98), key=lambda c: c["na"], default=None)),
    ("NO  largest G",            "NO",  lambda cs: max((c for c in cs if c["G"] is not None and c["na"] and c["na"] <= 98), key=lambda c: c["G"], default=None)),
    ("NO  smallest needed climb","NO",  lambda cs: min((c for c in cs if c["needed"] is not None and c["na"] and c["na"] <= 98), key=lambda c: c["needed"], default=None)),
    ("NO  tightest spread",      "NO",  lambda cs: min((c for c in cs if c["spread"] is not None and c["na"] and c["na"] <= 98), key=lambda c: (c["spread"], -c["na"]), default=None)),
    ("NO  most traded",          "NO",  lambda cs: max((c for c in cs if c["na"] and c["na"] <= 98), key=lambda c: c["vol"], default=None)),
    ("NO  cheapest",             "NO",  lambda cs: min((c for c in cs if c["na"] and c["na"] >= 1), key=lambda c: c["na"], default=None)),
    ("YES cheapest",             "YES", lambda cs: min((c for c in cs if c["ya"] and c["ya"] >= 1), key=lambda c: c["ya"], default=None)),
    ("YES dearest <=98",         "YES", lambda cs: max((c for c in cs if c["ya"] and c["ya"] <= 98), key=lambda c: c["ya"], default=None)),
    ("YES largest G",            "YES", lambda cs: max((c for c in cs if c["G"] is not None and c["ya"] and c["ya"] <= 98), key=lambda c: c["G"], default=None)),
]


def main():
    snaps = snapshots()
    days = sorted(snaps)
    print(f"decision moment: first cycle at/after {DECIDE_UTC}Z")
    print(f"days with a usable board and a settlement: {len(days)}")
    print()
    print(f"{'rule':28}{'days':>6}{'W-L':>9}{'mean c/day':>12}{'95% CI':>20}{'total':>9}")
    rows = []
    for name, side, pick in RULES:
        xs = []
        w = 0
        for d in days:
            c = pick(snaps[d])
            if not c:
                continue
            p = pnl(c, side)
            if p is None:
                continue
            xs.append(p)
            w += 1 if p > 0 else 0
        if len(xs) < 5:
            continue
        m = statistics.mean(xs)
        lo, hi = wilson_mean_ci(xs)
        rows.append((m, name, len(xs), w, lo, hi, sum(xs)))
    random.seed(7)
    xs = []
    w = 0
    for d in days:
        c = random.choice([c for c in snaps[d] if c["na"] and 1 <= c["na"] <= 98] or [None])
        if not c:
            continue
        p = pnl(c, "NO")
        if p is None:
            continue
        xs.append(p); w += 1 if p > 0 else 0
    if len(xs) >= 5:
        lo, hi = wilson_mean_ci(xs)
        rows.append((statistics.mean(xs), "NO  random bottom", len(xs), w, lo, hi, sum(xs)))

    for m, name, n, w, lo, hi, tot in sorted(rows, reverse=True):
        ci = f"[{lo:+6.1f}, {hi:+6.1f}]" if lo is not None else ""
        print(f"{name:28}{n:>6}{f'{w}-{n-w}':>9}{m:>+12.2f}{ci:>20}{tot:>+9.0f}")
    print()
    print("Reference: abstaining is 0.00c/day with no variance.")
    print(f"{len(rows)} rules compared, so the best row is the max of "
          f"{len(rows)} noisy estimates -- read its CI, not its rank.")


if __name__ == "__main__":
    main()
