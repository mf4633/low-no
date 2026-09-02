"""Hypothesis 9 -- the settlement convention: does CLI ROUND or FLOOR?

WRITTEN 2026-09-02, BEFORE ANY H9 QUANTITY WAS COMPUTED. prob.py is not edited.
Both candidate corrections are evaluated side by side on identical inputs, so
this file can only ever REPORT which constant the data supports; the gate keeps
the constant it has until a scored variant carries the other one.

THE CLAIM. `prob.py` prices P(daily max > ceiling) with a continuity
correction, `q(ceiling + 0.5)`, commented "settle in whole degrees". That is
the ROUND convention: round(T) >= cap+1 iff T >= cap+0.5. If CLI instead
reports the whole-degree value AT OR BELOW the true max -- a FLOOR -- the
correct constant is +1.0: floor(T) >= cap+1 iff T >= cap+1. The two differ by
half a degree at the threshold, which is 4-9 probability points at the
boundary and nothing in the tail.

WHERE IT COMES FROM. The climb-integrity audit (2026-09-02) found `run_max`
sitting up to 1.8F above the settlement on the whole-degree-C grid. Two rows
exceed what symmetric rounding can produce: AUS 2026-08-12, run_max 102.20 =
39.0C exactly, CLI 101; MIA 2026-08-29, 86.00 = 30.0C, CLI 85. Both fit a
floor. Two rows are not a convention, so this is a test rather than a fix.

THE DIFFERENTIAL PREDICTION IS THE WHOLE TEST. The two corrections converge
away from the threshold, so if the floor is right the improvement must be
CONCENTRATED in the boundary zone and ABSENT in the tail. A uniform
improvement, or one that lives in the tail, falsifies the mechanism even if
it is an improvement -- something other than the convention would be driving
it. This is also the protection against fitting: the pooled 96-98c shortfall
(disclosed below) was already known, but it does not imply the boundary/tail
split, and only the split passes.

WHAT A PASS MEANS. That our model has been OVERSTATING P(NO wins) at the
boundary by ~half a degree of threshold. That is a phantom edge removed, not
an edge found. It does not touch the market and cannot promote anything. If it
passes, the +1.0 correction enters as a SCORED VARIANT in shadow_run.py, never
as an edit to the frozen gate's inputs.

INPUTS ARE IDENTICAL FOR BOTH ARMS, deliberately. mu and sigma come from the
same station model, run_max is the same C-inflated value, the truncation is
the same. Whatever is wrong with those is wrong for both arms equally and
cancels in the paired difference. The only thing that differs is the constant.

UNITS AND BAR. The unit is a city-day, not a rung-observation: the Brier gap is
averaged within each (day, city) first, then compared across city-days with a
normal 95% interval on the mean paired difference. Bar: >= MIN_UNITS city-days
in the boundary zone AND >= MIN_UNITS in the tail. Zones are fixed by needed
climb at scoring time, cap - run_max: BOUNDARY <= 1.0F, TAIL >= 3.0F, the band
between is left undefined on purpose (as H4a leaves "mid").

PASS RULE, fixed now (and corrected ONCE, on the synthetic test, before any
real data was scored -- see below):
  * boundary: mean(brier_round - brier_floor) > 0 with the 95% CI excluding 0
  * concentration: the boundary mean is at least CONCENTRATION times the tail
    mean (tail may be positive; it must be materially SMALLER)
Both, or it fails.

Why concentration and not "tail includes zero": the first draft required the
tail difference to be indistinguishable from zero, and the synthetic FLOOR
world failed it -- correctly, because the two constants still differ by ~1
point at 4F of needed climb, and with thousands of units any nonzero gap is
significant. "Absent in the tail" was the wrong idealisation; the mechanism
predicts the gap SHRINKS with distance, and by how much is fixed by the
Gaussian itself: at sigma 2.5 the gap is ~7 points at 0.5F needed and ~1.3
points at 4F, a ratio near 5. Requiring >= 2 is well inside that and is not
met by a uniform improvement, which the synthetic test also checks.

DISCLOSURE -- known when this was written:
  * 96-98c NO: n=126, realized 92.7%, breakeven 98.2%, retired 2026-08-31
  * every 96-98c loss on record is a boundary day (H3 sub-finding)
  * the two rows named above, and the 13% impossible-sample count
  * the size of the correction at the boundary (the table in CANDIDATE.md)
No Brier under either constant had been computed.
"""
import json
import math
import statistics
from collections import defaultdict

from lowno.prob import norm_cdf, station_model

ROUND_C, FLOOR_C = 0.5, 1.0
BOUNDARY_MAX, TAIL_MIN = 1.0, 3.0
MIN_UNITS = 100
CONCENTRATION = 2.0     # boundary effect must be >= this multiple of the tail's


def passes(mb, lb, mt):
    """The registered rule, in one place so the test and the verdict agree."""
    if mb is None or lb is None or mt is None:
        return False
    return bool(lb > 0 and mb >= CONCENTRATION * max(mt, 0.0))


def p_no(guide, run_max, cap, model, c):
    """P(settle > cap) with continuity constant `c`, mirroring rung_probability
    exactly, including the run_max truncation. Returns None where prob.py would."""
    if guide is None or cap is None:
        return None
    if run_max is not None and run_max > cap:
        return 1.0
    mu, sig = guide - model["bias"], model["sigma"]
    if not sig or sig <= 0:
        return None
    q = lambda x: 1 - norm_cdf((x - mu) / sig)
    p = q(cap + c)
    if run_max is not None:
        d = q(run_max)
        if d > 1e-9:
            p = min(1.0, p / d)
    return p


def rows(path="docs/shadow.json"):
    """Settled bottom-rung observations with everything both arms need."""
    try:
        obs = json.load(open(path))
    except Exception:
        return []
    out = []
    for o in obs:
        if o.get("kind", "bottom") != "bottom" or o.get("settle") is None:
            continue
        cap, rm, g = o.get("ceiling"), o.get("run_max"), o.get("guide")
        if cap is None or rm is None or g is None:
            continue
        if rm > cap:
            continue            # already decided; both arms return 1.0
        out.append(dict(day=o["day"], city=o["city"], guide=g, run_max=rm,
                        cap=cap, settle=o["settle"], need=cap - rm))
    return out


def score(rs, models=None):
    """(day, city) -> dict(zone, d) with d = mean(brier_round - brier_floor)."""
    models = models or {}
    acc = defaultdict(lambda: defaultdict(list))
    for r in rs:
        m = models.get(r["city"])
        if m is None:
            try:
                m = models[r["city"]] = station_model(r["city"])
            except Exception:
                continue
        pr = p_no(r["guide"], r["run_max"], r["cap"], m, ROUND_C)
        pf = p_no(r["guide"], r["run_max"], r["cap"], m, FLOOR_C)
        if pr is None or pf is None:
            continue
        y = 1.0 if r["settle"] > r["cap"] else 0.0
        zone = ("boundary" if r["need"] <= BOUNDARY_MAX else
                "tail" if r["need"] >= TAIL_MIN else None)
        if zone is None:
            continue
        acc[(r["day"], r["city"])][zone].append((pr - y) ** 2 - (pf - y) ** 2)
    units = defaultdict(list)
    for k, zones in acc.items():
        for zone, ds in zones.items():
            units[zone].append(statistics.mean(ds))
    return units


def _ci(xs, z=1.96):
    n = len(xs)
    if n < 2:
        return (None, None, None)
    m = statistics.mean(xs)
    se = statistics.stdev(xs) / math.sqrt(n)
    return (round(m, 5), round(m - z * se, 5), round(m + z * se, 5))


def verdict():
    try:
        units = score(rows())
    except Exception as e:
        return dict(id="H9", ready=False, passed=False, error=str(e)[:120])
    nb, nt = len(units.get("boundary", [])), len(units.get("tail", []))
    if nb < MIN_UNITS or nt < MIN_UNITS:
        return dict(id="H9", ready=False, passed=False, boundary=nb, tail=nt,
                    need=MIN_UNITS, reason="data bar not met (city-days per zone)")
    mb, lb, hb = _ci(units["boundary"])
    mt, lt, ht = _ci(units["tail"])
    passed = passes(mb, lb, mt)
    return dict(id="H9", ready=True, passed=passed,
                boundary=dict(n=nb, mean=mb, ci=[lb, hb]),
                tail=dict(n=nt, mean=mt, ci=[lt, ht]))


def main():
    v = verdict()
    print("H9 -- continuity correction: round (+0.5) vs floor (+1.0)")
    if not v.get("ready"):
        print(f"  city-days: boundary {v.get('boundary')} / tail {v.get('tail')} "
              f"(bar {MIN_UNITS} each)")
        print("  DATA BAR NOT MET -- refusing to report a result. "
              "This is the registered behaviour, not a failure.")
        return
    print(f"\n  {'zone':>10} {'city-days':>10} {'brier(round)-brier(floor)':>26} {'95% CI':>22}")
    for z in ("boundary", "tail"):
        d = v[z]
        print(f"  {z:>10} {d['n']:>10} {d['mean']:>+26.5f} {str(d['ci']):>22}")
    print("\n  positive = the FLOOR constant scores better.")
    print("  verdict on the registered claim:")
    if v["passed"]:
        print("  FLOOR wins at the boundary and the gap shrinks in the tail --")
        print("  the differential prediction holds. prob.py has been overstating")
        print("  P(NO wins) near the cap. Phantom edge removed, none found;")
        print("  ship +1.0 as a scored variant, not as an edit to the gate.")
    else:
        print("  The split the mechanism requires is not there. Either the")
        print("  convention is not a floor, or the model's error lives elsewhere.")


if __name__ == "__main__":
    main()
