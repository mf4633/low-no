"""Prove settle_conv_eval.py measures what it claims, on synthetic worlds.

Running H9 on the real ledger before this passes would be answering the
question with an unverified instrument. So: a world where settlement is a
FLOOR must pass; a world where it is a ROUND must fail; a uniform improvement
that is not concentrated at the boundary must fail; and below the bar it
refuses regardless of the planted truth.

Run: python test_settle_conv_eval.py     (exits non-zero on any failure)
"""
import math
import random
import sys

import settle_conv_eval as H

FAILURES = []
MODEL = {"bias": 0.0, "sigma": 2.5}


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)


def world(n_days, convention, seed=3, cities=("A", "B", "C", "D")):
    """Each city-day: true max T ~ N(guide, sigma); settle = convention(T).
    Two rungs per city-day, one at the boundary and one in the tail."""
    rnd = random.Random(seed)
    rs = []
    for d in range(n_days):
        day = f"2026-07-{d % 28 + 1:02d}x{d}"
        for c in cities:
            guide = 80.0
            # The model is a Gaussian TRUNCATED at run_max: P(T > x | T >= rm)
            # = Q(x)/Q(rm). For the test to isolate the constant, the world
            # must make that conditional exactly right -- so run_max is drawn
            # INDEPENDENTLY of T and the pair is kept only when T >= run_max.
            # Two earlier drafts got this wrong (min(T, const) leaked T; a
            # uniform climb-left made both arms wrong) and the constant that
            # "won" was an artefact of the mismatch, not of the convention.
            run_max = rnd.uniform(guide - 4.0, guide + 1.0)
            while True:
                T = rnd.gauss(guide, MODEL["sigma"])
                if T >= run_max:
                    break
            settle = math.floor(T) if convention == "floor" else round(T)
            for cap in (math.floor(run_max) + 1, math.floor(run_max) + 4):
                rs.append(dict(day=day, city=c, guide=guide, run_max=run_max,
                               cap=cap, settle=settle, need=cap - run_max))
    return rs


def run(rs):
    units = H.score(rs, models={c: dict(MODEL) for c in "ABCD"})
    nb, nt = len(units.get("boundary", [])), len(units.get("tail", []))
    if nb < H.MIN_UNITS or nt < H.MIN_UNITS:
        return dict(ready=False, passed=False, boundary=nb, tail=nt)
    mb, lb, hb = H._ci(units["boundary"])
    mt, lt, ht = H._ci(units["tail"])
    return dict(ready=True, passed=H.passes(mb, lb, mt),
                boundary=dict(n=nb, mean=mb, ci=[lb, hb]),
                tail=dict(n=nt, mean=mt, ci=[lt, ht]))


def main():
    print("settle_conv_eval on synthetic worlds\n")

    v = run(world(1500, "floor"))
    check("a FLOOR world passes", v.get("passed") is True, str(v.get("boundary")))
    check("...and the effect is concentrated at the boundary",
          v.get("ready") and v["boundary"]["mean"] >= H.CONCENTRATION * max(v["tail"]["mean"], 0),
          f"boundary {v.get('boundary', {}).get('mean')} vs tail {v.get('tail', {}).get('mean')}")

    v = run(world(1500, "round", seed=8))
    check("a ROUND world fails (round is already the model)", v.get("passed") is False,
          str(v.get("boundary")))

    v = run(world(20, "floor"))          # 80 city-days, under the 100 bar
    check("refuses below the bar even on a floor world", v.get("ready") is False,
          f"boundary {v.get('boundary')} / tail {v.get('tail')}")

    # A world where BOTH zones favour floor equally is not the mechanism:
    # fake it by handing the scorer a tail whose rows behave like the boundary.
    rs = world(1500, "floor", seed=5)
    for r in rs:
        if r["need"] >= H.TAIL_MIN:
            r["need"] = 3.0          # keep the tail label
            r["cap"] = math.floor(r["run_max"]) + 1   # ...but price it at the boundary
    v = run(rs)
    check("a uniform improvement (tail moves too) fails", v.get("passed") is False,
          str(v.get("tail")))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("all checks passed -- the harness measures what it claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())
