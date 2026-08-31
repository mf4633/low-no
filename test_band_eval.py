"""Prove band_eval.py measures what it claims, without looking at real history.

Running H5 over the 24 days that informed its framing is precisely the peek the
registration forbids, and it would answer the question instead of testing the
instrument. So the harness is verified against SYNTHETIC data where the truth is
known by construction: it must find a planted edge, must report null on noise,
must refuse when H4a has not passed, must ignore pre-registration days, and must
never let a day see its own outcome.

Run: python test_band_eval.py     (exits non-zero on any failure)
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile

CITIES4 = ["NYC", "PHL", "BOS", "DC"]      # all America/New_York, so local 14/15 = 18/19Z
TRAIN_DAYS = 45                            # enough for Wilson to clear a 91% breakeven
ASK = 90                                   # breakeven (90 + 1c fee)/100 = 0.91


def _iso(day, utc_hour):
    return f"{day}T{utc_hour:02d}:00:00+00:00"


def _row(day, city, utc_hour, run_max, cap=None, na=None):
    rungs = []
    if cap is not None:
        rungs = [{"fl": None, "cap": cap, "na": na}]
    return json.dumps({"at": _iso(day, utc_hour), "city": city,
                       "verdict": "LADDER",
                       "detail": {"run_max": run_max, "rungs": rungs}})


def build_world(root, decision_days, win_pattern, since="2026-09-01"):
    """Write logs + settlements into `root`.

    Training days: a CLIMBING pair at local 14->15 whose settlement sits 1F
    above the 15:00 running max, so every cell sample exceeds a needed climb of
    0. That makes the cell's Wilson lower bound clear the 91% breakeven.

    Decision days: identical shape, with a bottom rung at 90c and a cap equal to
    the 15:00 running max (needed climb = 0). `win_pattern(i)` decides whether
    that day actually exceeds.
    """
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    settles = {}

    start = dt.date(2026, 9, 1) - dt.timedelta(days=TRAIN_DAYS)
    for i in range(TRAIN_DAYS):
        day = (start + dt.timedelta(days=i)).isoformat()
        lines = []
        for c in CITIES4:
            base = 80.0
            cap = int(base + 2)
            lines.append(_row(day, c, 18, base))                          # local 14
            # Priced like a decision day so the `since` filter is actually
            # exercised: these are eligible on every criterion EXCEPT date.
            lines.append(_row(day, c, 19, base + 2.0, cap=cap, na=ASK))   # rate 2.0 = climbing
            settles[f"{day}|{c}"] = base + 3.0             # remaining climb from 15:00 = +1
        open(os.path.join(root, "logs", f"{day}.jsonl"), "w").write("\n".join(lines) + "\n")

    for i, day in enumerate(decision_days):
        lines = []
        for c in CITIES4:
            base = 80.0
            cap = int(base + 2)                             # needed climb = 0 at 15:00
            lines.append(_row(day, c, 18, base))
            lines.append(_row(day, c, 19, base + 2.0, cap=cap, na=ASK))
            settles[f"{day}|{c}"] = cap + (1 if win_pattern(i) else 0)
        open(os.path.join(root, "logs", f"{day}.jsonl"), "w").write("\n".join(lines) + "\n")

    json.dump(settles, open(os.path.join(root, "docs", "settlements.json"), "w"))


def run_in(root, fn):
    """Execute fn() with `root` as cwd and band_eval freshly imported there."""
    cwd = os.getcwd()
    os.chdir(root)
    # Only band_eval is reloaded. shape_eval is left alone on purpose: the
    # caller injects a fake to exercise the H4a interlock, and popping it here
    # threw that away and made every case look blocked.
    sys.modules.pop("band_eval", None)
    try:
        import band_eval
        return fn(band_eval)
    finally:
        os.chdir(cwd)
        sys.modules.pop("band_eval", None)


def fake_h4a(passed):
    """Stand in for shape_eval so the H4a interlock can be exercised both ways."""
    import types
    m = types.ModuleType("shape_eval")
    m.verdict = lambda: {"id": "H4a", "ready": True, "passed": passed}
    sys.modules["shape_eval"] = m


FAILURES = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def main():
    repo = os.path.dirname(os.path.abspath(__file__))
    days20 = [(dt.date(2026, 9, 1) + dt.timedelta(days=i)).isoformat() for i in range(20)]

    # (label, outcome pattern, expect a pass, expect the full 80 units)
    #
    # The no-edge world deliberately does NOT yield 80 units, and that is a
    # property worth asserting rather than a shortfall. Decision days feed the
    # point-in-time cells of later decision days, so as losses accumulate the
    # cell's lower bound falls back under breakeven and the gate SHUTS ITSELF.
    # A rule that kept firing 80 times into a coin flip would be the broken one.
    for label, pattern, expect_pass, expect_full in (
            ("PLANTED EDGE (every unit wins)", lambda i: True, True, True),
            ("NO EDGE (alternating outcome)", lambda i: i % 2 == 0, False, False)):
        print(f"\n{label}")
        root = tempfile.mkdtemp(prefix="h5test_")
        try:
            for f in ("band_eval.py",):
                shutil.copy(os.path.join(repo, f), root)
            shutil.copytree(os.path.join(repo, "lowno"), os.path.join(root, "lowno"))
            build_world(root, days20, pattern)

            fake_h4a(True)
            v = run_in(root, lambda be: be.verdict())
            n = v.get("units")
            if expect_full:
                check("every eligible city-day becomes a unit (4 x 20 = 80)", n == 80,
                      f"got {n}")
                check("unit bar met, so it reports", v.get("ready") is True, json.dumps(v))
                check("verdict PASSES on a planted edge", v.get("passed") is True,
                      f"hit={v.get('hit')} lcb={v.get('lcb')} be={v.get('breakeven')}")
                check("P&L positive on a planted edge", v.get("pnl_c", 0) > 0,
                      f"{v.get('pnl_c')}c")
            else:
                check("the gate SHUTS ITSELF as contrary evidence lands",
                      0 < n < 80, f"{n} units before the cells learned better")
                check("does not reach the unit bar on noise", v.get("ready") is False,
                      json.dumps(v))
                check("never reported as a pass", v.get("passed") is False)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # ---- interlocks -------------------------------------------------------
    print("\nINTERLOCKS")
    root = tempfile.mkdtemp(prefix="h5test_")
    try:
        shutil.copy(os.path.join(repo, "band_eval.py"), root)
        shutil.copytree(os.path.join(repo, "lowno"), os.path.join(root, "lowno"))
        build_world(root, days20, lambda i: True)

        fake_h4a(False)
        v = run_in(root, lambda be: be.verdict())
        check("refuses while H4a has not passed",
              v.get("passed") is False and "H4a" in str(v.get("reason")), json.dumps(v))

        fake_h4a(True)
        n_all = run_in(root, lambda be: len(be.units(since="2026-01-01")))
        n_reg = run_in(root, lambda be: len(be.units()))
        check("pre-registration days are excluded",
              n_reg == 80 and n_all > n_reg, f"since-2026-01-01={n_all}, registered={n_reg}")

        # A day must not be able to use its own outcome. Give the FIRST decision
        # day no prior history at all: with no cells, it cannot produce a unit.
        root2 = tempfile.mkdtemp(prefix="h5test_")
        try:
            shutil.copy(os.path.join(repo, "band_eval.py"), root2)
            shutil.copytree(os.path.join(repo, "lowno"), os.path.join(root2, "lowno"))
            os.makedirs(os.path.join(root2, "logs")); os.makedirs(os.path.join(root2, "docs"))
            settles = {}
            lines = []
            for c in CITIES4:
                lines.append(_row("2026-09-01", c, 18, 80.0))
                lines.append(_row("2026-09-01", c, 19, 82.0, cap=82, na=ASK))
                settles[f"2026-09-01|{c}"] = 83
            open(os.path.join(root2, "logs", "2026-09-01.jsonl"), "w").write("\n".join(lines) + "\n")
            json.dump(settles, open(os.path.join(root2, "docs", "settlements.json"), "w"))
            fake_h4a(True)
            n = run_in(root2, lambda be: len(be.units()))
            check("a day cannot trade on its own outcome (no prior cells -> 0 units)",
                  n == 0, f"got {n}")
        finally:
            shutil.rmtree(root2, ignore_errors=True)

        # Band selectivity: the control band must select a different population.
        fake_h4a(True)
        n_ctl = run_in(root, lambda be: len(be.units(96, 98)))
        check("96-98c control selects nothing when every ask is 90c",
              n_ctl == 0, f"got {n_ctl}")
    finally:
        shutil.rmtree(root, ignore_errors=True)
        sys.modules.pop("shape_eval", None)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("all checks passed -- the harness measures what it claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())
