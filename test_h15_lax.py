"""Prove h15_lax.py measures what it claims, on SYNTHETIC data only.

Run: python test_h15_lax.py     (exits non-zero on any failure)
"""
import json, os, random, shutil, sys, tempfile, datetime as dt
import h15_lax as H

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)


# Training rows: marine days cool (70-72), clear days warm (80-82), same season.
TRAIN = []
for y in (2022, 2023, 2024, 2025):
    for k in range(60):
        d = (dt.date(y, 9, 1) + dt.timedelta(days=k)).isoformat()
        TRAIN.append((d, "NO_STRATUS", 80 + k % 3))
        TRAIN.append((d, "LATE_BURN", 71 + k % 2))
        TRAIN.append((d, "NO_BURN", 70 + k % 2))
        TRAIN.append((d, "EARLY_BURN", 76))

CLEAR = {h: None for h in range(24)}
MARINE = {h: (1200 if 10 <= h <= 18 else None) for h in range(24)}
NOBURN = {h: (1200 if 10 <= h <= 21 else None) for h in range(24)}


def build(tmp, days, mkt_fn, settle_fn):
    """days: [(day, sky)]. mkt_fn(stratum, settle, cap) -> YES mid cents."""
    os.makedirs(os.path.join(tmp, "poll"), exist_ok=True)
    settles, S = {}, {}
    for d, sk in days:
        S[d] = sk
        st = "MARINE" if sk is not CLEAR else "CONTROL"
        s = settle_fn(st, d)
        settles[f"{d}|LAX"] = s
        cap = 74
        t = f"KXHIGHLAX-{d[2:4]}{['','JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][int(d[5:7])]}{d[8:10]}-T{cap+1}"
        p = mkt_fn(st, s, cap)
        with open(os.path.join(tmp, "poll", f"{d}.jsonl"), "a") as fh:
            for i in range(24):          # 15:00Z..16:55Z + 19:00Z..19:55Z
                hh = 15 + i // 12 if i < 12 else 19
                at = f"{d}T{hh:02d}:{(i % 12) * 5:02d}:00Z"
                fh.write(json.dumps(dict(at=at, rung=dict(ticker=t, cap=cap,
                                                         ya=p + 1, yb=p - 1))) + "\n")
    sp = os.path.join(tmp, "settle.json")
    json.dump(settles, open(sp, "w"))
    return os.path.join(tmp, "poll", "*.jsonl"), sp, S


def days_list(n_m, n_c, start="2026-09-12"):
    d0 = dt.date.fromisoformat(start)
    out = []
    for i in range(n_m + n_c):
        out.append(((d0 + dt.timedelta(days=i)).isoformat(),
                    MARINE if i < n_m else CLEAR))
    return out


def run():
    rnd = random.Random(1)
    tmp = tempfile.mkdtemp()
    try:
        print("ticker / regime plumbing")
        check("ticker_day parses", H.ticker_day("KXHIGHLAX-26OCT13-T68") == "2026-10-13")
        check("NO_BURN day reads marine at 18Z cut", H.regime_at_cut(NOBURN) == "LATE_BURN")
        cell, fc = H.model_cell(NOBURN, "2026-10-01", TRAIN)
        check("marine cell pools LATE+NO_BURN", cell == "MARINE" and 70 <= fc["mean"] <= 72,
              f"{cell} {fc['mean']:.2f}")
        cell, fc = H.model_cell(CLEAR, "2026-10-01", TRAIN)
        check("clear day uses NO_STRATUS cell", cell == "NO_STRATUS" and fc["mean"] > 79)

        # Settles: marine ~71 (YES on <=74 true), clear ~81 (false).
        settle = lambda st, d: 71 if st == "MARINE" else 81

        print("planted: market blind to the regime on marine days")
        sub = os.path.join(tmp, "a")
        g, sp, S = build(sub, days_list(20, 12),
                         lambda st, s, cap: 50 if st == "MARINE" else 3, settle)
        U = H.units(g, sp, S, TRAIN)
        check("only 19Z rows scored", all(u["n_win"] == 12 for u in U), str({u["n_win"] for u in U}))
        vf = os.path.join(sub, "frozen", "v.json")
        v = H.verdict(g, sp, vf, S, TRAIN)
        check("planted mis-shape PASSES", v.get("passed") is True, json.dumps(v.get("context"))[:120])
        check("verdict frozen to disk", os.path.exists(vf))
        json.dump(dict(json.load(open(vf)), passed="SENTINEL"), open(vf, "w"))
        check("frozen verdict is never re-read fresh",
              H.verdict(g, sp, vf, S, TRAIN)["passed"] == "SENTINEL")

        print("null: market prices the regime correctly")
        sub = os.path.join(tmp, "b")
        g, sp, S = build(sub, days_list(20, 12),
                         lambda st, s, cap: 97 if st == "MARINE" else 3, settle)
        v = H.verdict(g, sp, None, S, TRAIN)
        check("fair market does NOT pass", v.get("passed") is False)

        print("below the bar")
        sub = os.path.join(tmp, "c")
        g, sp, S = build(sub, days_list(19, 12),
                         lambda st, s, cap: 50 if st == "MARINE" else 3, settle)
        v = H.verdict(g, sp, None, S, TRAIN)
        check("19 marine days refuses", v["ready"] is False and v["marine_days"] == 19)
        check("no Brier leaks below the bar",
              not any("brier" in k or k in ("context", "frozen") for k in v), str(list(v)))

        print("unit filters")
        sub = os.path.join(tmp, "d")
        g, sp, S = build(sub, days_list(2, 0), lambda st, s, cap: 50, settle)
        d_missing = sorted(S)[0]
        S[d_missing] = {h: v for h, v in S[d_missing].items() if h != 17}
        U = H.units(g, sp, S, TRAIN)
        check("day with a sky gap in 12Z-18Z is not a unit", d_missing not in {u["day"] for u in U})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run()
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)
