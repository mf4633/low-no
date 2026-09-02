"""Prove shape_pair_eval.py measures what it claims, without looking at real history.

Same reason as test_band_eval.py and test_h6_eval.py: running H8 over the days
that suggested it would answer the question instead of testing the instrument.
Verified against SYNTHETIC logs where the truth is known by construction -- it
must find a planted gap effect, report null when the gap does nothing, refuse
below its four-group bar, respect the pre-declared DIRECTION, and require BOTH
buckets rather than passing on one.

Run: python test_shape_pair_eval.py     (exits non-zero on any failure)
"""
import datetime as dt
import json
import os
import random
import shutil
import sys
import tempfile

FAILURES = []
CITY = "NYC"          # America/New_York: local 14:00 = 18:00Z, inside 13-16


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)


def row(day, utc_hour, minute, run_max, temp_now):
    return json.dumps({
        "at": f"{day}T{utc_hour:02d}:{minute:02d}:00+00:00", "city": CITY,
        "verdict": "LADDER",
        "detail": {"run_max": run_max, "temp_now": temp_now, "rungs": []}})


def world(root, n_days, off_peak_effect, seed=5, climbing_share=0.5):
    """Two paired peak-window cycles per day.

    Each day is either CLIMBING or STALLED on temp_now, and independently
    either off-peak (run_max well above temp_now) or not. Remaining climb is
    settle - run_max, and `off_peak_effect` is added to it for flagged days --
    so a NEGATIVE effect is the registered prediction.
    """
    rnd = random.Random(seed)
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    settles = {}
    start = dt.date(2026, 7, 1)
    for i in range(n_days):
        day = (start + dt.timedelta(days=i)).isoformat()
        lines = []
        climbing = rnd.random() < climbing_share
        flagged = rnd.random() < 0.5
        base_temp = 78.0
        # run_max sits above temp_now by the gap; 3.0F clears the 1.8F cut.
        gap = 3.0 if flagged else 0.0
        rate = 2.5 if climbing else 0.0            # F/hr on temp_now
        t0, t1 = base_temp, base_temp + rate       # one hour apart
        run_max = max(t0, t1) + gap
        lines.append(row(day, 17, 30, run_max, t0))     # local 13:30
        lines.append(row(day, 18, 30, run_max, t1))     # local 14:30
        remaining = 2.0 + (off_peak_effect if flagged else 0.0) + rnd.gauss(0, 0.5)
        settles[f"{day}|{CITY}"] = round(run_max + remaining, 2)
        with open(os.path.join(root, "logs", f"{day}.jsonl"), "w") as fh:
            fh.write("\n".join(lines) + "\n")
    json.dump(settles, open(os.path.join(root, "docs", "settlements.json"), "w"))


def run_in(root, fn):
    cwd = os.getcwd()
    try:
        os.chdir(root)
        sys.modules.pop("shape_pair_eval", None)
        sys.path.insert(0, cwd)
        import shape_pair_eval as H
        return fn(H)
    finally:
        sys.path.remove(cwd)
        os.chdir(cwd)
        sys.modules.pop("shape_pair_eval", None)


def main():
    print("shape_pair_eval on synthetic worlds\n")

    # 1. A planted effect in the registered direction must be found.
    root = tempfile.mkdtemp(prefix="h8a_")
    try:
        world(root, 1400, off_peak_effect=-1.5)
        v = run_in(root, lambda H: H.verdict())
        check("finds a planted off-peak effect", v.get("passed") is True, str(v.get("legs"))[:150])
        check("both buckets cleared the group bar", v.get("ready") is True, str(v.get("counts")))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # 2. No effect must not pass.
    root = tempfile.mkdtemp(prefix="h8b_")
    try:
        world(root, 1400, off_peak_effect=0.0, seed=9)
        v = run_in(root, lambda H: H.verdict())
        check("reports null when the gap does nothing", v.get("passed") is False,
              str(v.get("legs"))[:150])
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # 3. DIRECTION: an effect the wrong way must FAIL, not pass on magnitude.
    root = tempfile.mkdtemp(prefix="h8c_")
    try:
        world(root, 1400, off_peak_effect=+1.5, seed=13)
        v = run_in(root, lambda H: H.verdict())
        check("an effect in the WRONG direction fails", v.get("passed") is False,
              "diff should be positive: " + str(v.get("legs", {}).get("stalled", {}).get("diff")))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # 4. One bucket alone is not enough -- the climbing group is starved.
    root = tempfile.mkdtemp(prefix="h8d_")
    try:
        world(root, 1400, off_peak_effect=-1.5, seed=21, climbing_share=0.02)
        v = run_in(root, lambda H: H.verdict())
        check("a starved second bucket blocks the verdict",
              v.get("ready") is False and v.get("passed") is False,
              str(v.get("counts")))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # 5. Below the bar it refuses however large the planted effect.
    root = tempfile.mkdtemp(prefix="h8e_")
    try:
        world(root, 40, off_peak_effect=-6.0)
        v = run_in(root, lambda H: H.verdict())
        check("refuses below the data bar with a huge planted effect",
              v.get("ready") is False and v.get("passed") is False, v.get("reason", ""))
        check("refusal names the per-group bar", v.get("need_per_group") == 150)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # 6. The threshold is a real cut: a gap under 1.8F must not flag.
    root = tempfile.mkdtemp(prefix="h8f_")
    try:
        os.makedirs(os.path.join(root, "logs"))
        os.makedirs(os.path.join(root, "docs"))
        day = "2026-07-01"
        with open(os.path.join(root, "logs", f"{day}.jsonl"), "w") as fh:
            fh.write(row(day, 17, 30, 81.0, 80.0) + "\n")     # gap 1.0 -> not flagged
            fh.write(row(day, 18, 30, 81.0, 80.0) + "\n")
        json.dump({f"{day}|{CITY}": 83.0},
                  open(os.path.join(root, "docs", "settlements.json"), "w"))
        s = run_in(root, lambda H: H.samples())
        check("a 1.0F gap is quantization, not off-peak",
              len(s) == 1 and s[0]["off_peak"] is False,
              f"{len(s)} sample(s), off_peak={s[0]['off_peak'] if s else '--'}")

        with open(os.path.join(root, "logs", f"{day}.jsonl"), "w") as fh:
            fh.write(row(day, 17, 30, 84.0, 80.0) + "\n")     # gap 4.0 -> flagged
            fh.write(row(day, 18, 30, 84.0, 80.0) + "\n")
        json.dump({f"{day}|{CITY}": 86.0},
                  open(os.path.join(root, "docs", "settlements.json"), "w"))
        s = run_in(root, lambda H: H.samples())
        check("a 4.0F gap is off-peak",
              len(s) == 1 and s[0]["off_peak"] is True,
              f"off_peak={s[0]['off_peak'] if s else '--'}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("all checks passed -- the harness measures what it claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())
