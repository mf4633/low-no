"""Hypothesis 5 -- the contested band (81-95c), priced against breakeven.

WRITTEN 2026-08-31, BEFORE ANY QUALIFYING DAY EXISTS. Same discipline as
shape_eval.py and curve_lag.py: a test authored after seeing the data it judges
is not a test. Nothing here may be tuned once units arrive; a change is
recorded in CANDIDATE.md with a reason, like every other correction.

THE CLAIM (CANDIDATE.md, HYPOTHESIS 5). p_exceed conditions on
(city, hour, run_max) and run_max is a MAXIMUM -- monotone, shape-blind. H4a
measured that blindness at 1.48F of remaining climb inside the peak window. A
1.48F shift can only change an answer where 1.48F is decisive: at 96-98c the
needed climb is already zero and H3 showed a real-but-small effect there is
priced. In 81-95c the needed climb is the same order as the signal.

ENTRY, WITH NO FITTED CONSTANT. Enter NO when the shape cell's Wilson 95%
LOWER bound on P(exceed) clears the breakeven implied by the ask. Not the point
estimate. The required margin is therefore whatever the cell's own sample size
demands -- a thin cell must show a larger effect than a deep one, and there is
no threshold anyone can quietly move later.

TWO INTERLOCKS, both deliberate:
  * Subordinate to H4a. Refuses to score until shape_eval.verdict() PASSES.
    Scoring first would build on the unvalidated premise that killed H1.
  * Post-registration days only (>= H5_SINCE). The 24 days that informed the
    framing are disqualified as evidence.

POINT-IN-TIME CELLS. For a decision on day D the shape cells are built from
days STRICTLY BEFORE D. This is not a detail: the corrected_G4 variants use a
station bias measured over the whole history including the days they select,
and that look-ahead is exactly the shape of error that killed H1. A rule that
could not have been traded on the day is not a result.

CROSS-BAND CONTROL. The same rule is scored at 96-98c and reported alongside.
The mechanism predicts the edge is CONCENTRATED in 81-95c and ABSENT there. A
result that looks equally good in both bands falsifies the mechanism even if it
makes money, because something other than "1.48F matters where 1.48F is
decisive" would be driving it.
"""
import datetime as dt
import glob
import json
import math
import os
import zoneinfo
from collections import defaultdict

from lowno import empirical as E
from lowno.config import CITIES
from lowno.shadow import fee_cents

# Registered in CANDIDATE.md 2026-08-31. Earlier days informed the framing.
H5_SINCE = "2026-09-01"

BAND_LO, BAND_HI = 81, 95          # the contested band
CONTROL_LO, CONTROL_HI = 96, 98    # the cross-band control
MIN_UNITS = 60                     # the standing promotion bar
PEAK = E.PEAK_WINDOW               # 13-16 local; the effect inverts outside it
GAP_LO, GAP_HI = 0.5, 2.5          # hours between paired cycles (as shape_eval)


def wilson(k, n, z=1.96):
    """Lower/upper bound on a proportion. Same form used everywhere here."""
    if not n:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - m, c + m


def _rows():
    """Every usable scan row, once, as (day, city, local_hour_float, run_max,
    rungs). Read in one pass so the point-in-time loop below does not rescan
    the logs once per day."""
    out = defaultdict(list)
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = r.get("detail")
            city = r.get("city")
            if not isinstance(d, dict) or d.get("world") or city not in CITIES:
                continue
            rm = d.get("run_max")
            if rm is None:
                continue
            try:
                lt = (dt.datetime.fromisoformat(r["at"])
                      .replace(tzinfo=dt.timezone.utc)
                      .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])))
            except Exception:
                continue
            out[(day, city)].append(
                (lt.hour + lt.minute / 60.0, lt.hour, rm, d.get("rungs") or []))
    for k in out:
        out[k].sort(key=lambda x: x[0])
    return out


def _settles():
    try:
        return {tuple(k.split("|")): v
                for k, v in json.load(open("docs/settlements.json")).items()}
    except Exception:
        return {}


def _cells_through(rows, settles, days):
    """{(city, hour, rate_bucket): [remaining climb]} from `days` only.

    Mirrors shape_eval.build's rated table deliberately -- same 0.5-2.5h gap,
    same rate_bucket, same settled-days-only rule. It is duplicated rather than
    imported because shape_eval.build rescans every log file per call, and this
    harness needs one table per decision day. If the two ever disagree,
    shape_eval is authoritative: it is the validated one.
    """
    R = defaultdict(list)
    for (day, city), v in rows.items():
        if day not in days:
            continue
        s = settles.get((day, city))
        if s is None:
            continue
        for i in range(1, len(v)):
            hf, h, rm, _ = v[i]
            dh = hf - v[i - 1][0]
            if not (GAP_LO <= dh <= GAP_HI):
                continue
            b = E.rate_bucket((rm - v[i - 1][2]) / dh)
            if b is None:
                continue
            R[(city, h, b)].append(s - rm)
    return R


def units(lo=BAND_LO, hi=BAND_HI, since=H5_SINCE):
    """The rule, applied forward in time. One unit per city-day.

    Returns a list of dicts; empty is a legitimate answer and is NOT a null
    result -- see main().
    """
    rows, settles = _rows(), _settles()
    all_days = sorted({d for d, _ in rows})
    taken, seen = [], set()

    for day in all_days:
        if day < since:
            continue
        # Cells from strictly earlier days: what was knowable that morning.
        R = _cells_through(rows, settles, {d for d in all_days if d < day})
        for (d0, city), v in sorted(rows.items()):
            if d0 != day or (day, city) in seen:
                continue
            s = settles.get((day, city))
            if s is None:
                continue
            for i in range(1, len(v)):
                hf, h, rm, rungs = v[i]
                if not (PEAK[0] <= h <= PEAK[1]):
                    continue
                dh = hf - v[i - 1][0]
                if not (GAP_LO <= dh <= GAP_HI):
                    continue
                b = E.rate_bucket((rm - v[i - 1][2]) / dh)
                if b is None:
                    continue
                cell = R.get((city, h, b), [])
                if len(cell) < E.MIN_N_RATE:
                    continue
                bottom = next((g for g in rungs
                               if g.get("fl") is None and g.get("cap") is not None), None)
                if not bottom:
                    continue
                na, cap = bottom.get("na"), bottom.get("cap")
                # na == 100 is "no offer", not a price. Real asks only.
                if na is None or cap is None or not (lo <= na <= hi):
                    continue
                needed = cap - rm
                k = sum(1 for x in cell if x > needed)
                lcb, _ = wilson(k, len(cell))
                breakeven = (na + fee_cents(na)) / 100.0
                if lcb <= breakeven:
                    continue
                won = s > cap
                fee = fee_cents(na)
                taken.append(dict(
                    day=day, city=city, hour=h, ask=na, cap=cap, settle=s,
                    needed=round(needed, 1), cell_n=len(cell), bucket=b,
                    p_lcb=round(lcb, 4), breakeven=round(breakeven, 4), won=won,
                    pnl_c=(100 - na - fee) if won else -(na + fee)))
                seen.add((day, city))
                break
    return taken


def verdict():
    """Machine-readable gate. PASSES only on the standing promotion bar, and
    only once H4a has actually passed."""
    try:
        import shape_eval
        h4a = shape_eval.verdict()
    except Exception as e:
        return dict(id="H5", ready=False, passed=False,
                    reason=f"cannot read H4a: {str(e)[:60]}")
    if not h4a.get("passed"):
        return dict(id="H5", ready=False, passed=False, units=0,
                    reason="blocked: H4a has not passed")
    try:
        u = units()
    except Exception as e:
        return dict(id="H5", ready=False, passed=False, error=str(e)[:120])
    n = len(u)
    if n < MIN_UNITS:
        return dict(id="H5", ready=False, passed=False, units=n,
                    need=MIN_UNITS, reason="unit bar not met")
    k = sum(1 for t in u if t["won"])
    lcb, _ = wilson(k, n)
    be = sum(t["breakeven"] for t in u) / n
    return dict(id="H5", ready=True, passed=bool(lcb > be), units=n, wins=k,
                hit=round(k / n, 4), lcb=round(lcb, 4), breakeven=round(be, 4),
                pnl_c=sum(t["pnl_c"] for t in u))


def _summarise(u, label):
    n = len(u)
    if not n:
        print(f"  {label:12} no qualifying units")
        return None
    k = sum(1 for t in u if t["won"])
    lcb, _ = wilson(k, n)
    be = sum(t["breakeven"] for t in u) / n
    pnl = sum(t["pnl_c"] for t in u)
    print(f"  {label:12} n={n:>4}  {k:>4}W  hit {100*k/n:5.1f}%  "
          f"LCB {100*lcb:5.1f}%  breakeven {100*be:5.1f}%  "
          f"P&L {pnl:+6.0f}c  {'CLEARS' if lcb > be else 'short'}")
    return dict(n=n, wins=k, lcb=lcb, breakeven=be, pnl_c=pnl)


def main():
    print(f"H5 -- contested band {BAND_LO}-{BAND_HI}c, days >= {H5_SINCE}")
    try:
        import shape_eval
        h4a = shape_eval.verdict()
    except Exception as e:
        print(f"cannot read H4a: {e}")
        return
    if not h4a.get("passed"):
        print("\nBLOCKED: H4a has not passed. This rule rests on the shape "
              "cells being validated out of sample, and scoring it first would "
              "repeat the H1 failure. This is the registered behaviour, not a "
              "bug.")
        print(f"  H4a: {json.dumps(h4a)}")
        print(f"\nSupply only, for planning: "
              f"{len(units())} unit(s) would qualify on the entry rule.")
        return

    band = units(BAND_LO, BAND_HI)
    ctrl = units(CONTROL_LO, CONTROL_HI)
    print()
    b = _summarise(band, "81-95c")
    c = _summarise(ctrl, f"{CONTROL_LO}-{CONTROL_HI}c ctl")

    if not b or b["n"] < MIN_UNITS:
        print(f"\nUNIT BAR NOT MET ({b['n'] if b else 0}/{MIN_UNITS}) -- refusing "
              f"to call it. Registered behaviour, not a failure.")
        return

    print("\nverdict on the registered claim:")
    if b["lcb"] > b["breakeven"]:
        print("  81-95c CLEARS its breakeven on the Wilson lower bound.")
        if c and c["lcb"] > c["breakeven"]:
            print("  BUT the 96-98c control clears too. The mechanism predicted the")
            print("  edge would be CONCENTRATED in the contested band. It is not, so")
            print("  the mechanism is FALSIFIED even though the P&L is positive --")
            print("  something else is driving it and it has not been identified.")
        else:
            print("  The 96-98c control does NOT clear, as predicted. This is the")
            print("  necessary condition, NOT a trading result: an edge still has to")
            print("  survive depth, fills and a live quit line.")
    else:
        print("  No. The lower bound does not clear breakeven in the contested band.")
        print("  1.48F of shape information is not worth the gap to fee breakeven here.")


if __name__ == "__main__":
    main()
