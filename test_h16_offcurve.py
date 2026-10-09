"""Prove h16_offcurve.py measures what it claims, on SYNTHETIC logs only.

H16 is forward-only; running it on real history before 2026-10-07 would be
exactly the re-slicing CANDIDATE.md forbids. So the instrument is checked where
the truth is known by construction: it must find a planted underpricing, read
null on a fairly priced market, refuse below its bar, look only at the first
10-12 local cycle, interpolate the curve to the minute, and freeze its verdict.

Run: python test_h16_offcurve.py     (exits non-zero on any failure)
"""
import json, os, random, shutil, sys, tempfile, datetime as dt
import h16_offcurve as H

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)


CURVE = {str(h): 60.0 + max(0, min(h, 15) - 6) * 2.5 for h in range(24)}  # max 82.5 at 15


def ladder_row(day, city, utc_hm, temp_now, pick_price, other_price=50):
    """DAL is UTC-5 in October: 15:30Z = 10:30 local. Rungs 2F wide around 80."""
    rungs = [dict(t="B", fl=None, cap=77, ya=1, yb=0)]
    for lo in range(78, 92, 2):
        rungs.append(dict(t=f"R{lo}", fl=lo, cap=lo + 1, ya=other_price, yb=other_price - 2))
    rungs.append(dict(t="TOP", fl=92, cap=None, ya=1, yb=0))
    return json.dumps(dict(city=city, station="K" + city, verdict="LADDER",
                           at=f"{day}T{utc_hm}:00.000000",
                           detail=dict(temp_now=temp_now,
                                       airmass=dict(curve=CURVE, curve_max_f=82.5),
                                       rungs=rungs)))


def set_price(line, ticker, price):
    r = json.loads(line)
    for g in r["detail"]["rungs"]:
        if g["t"] == ticker:
            g["ya"], g["yb"] = price, max(0, price - 2)
    return json.dumps(r)


def world(root, n_days, price, p_win, seed=3, start="2026-10-07"):
    rnd = random.Random(seed)
    os.makedirs(os.path.join(root, "logs"))
    settle = {}
    d0 = dt.date.fromisoformat(start)
    for i in range(n_days):
        day = (d0 + dt.timedelta(days=i)).isoformat()
        lines = []
        for city in ("DAL", "AUS", "HOU"):
            # 10:30 local: curve = 70.0*0.5 + 72.5*0.5 = 71.25; temp 74.25 -> dev +3.0
            # proj = round(82.5 + 3.0) = 86 (round half even) -> R86 bucket
            ln = set_price(ladder_row(day, city, "15:30", 74.25, price), "R86", price)
            lines.append(ln)
            settle[f"{day}|{city}"] = 86 if rnd.random() < p_win else 83
        open(os.path.join(root, "logs", f"{day}.jsonl"), "w").write("\n".join(lines) + "\n")
    json.dump(settle, open(os.path.join(root, "settle.json"), "w"))
    return os.path.join(root, "logs", "2*.jsonl"), os.path.join(root, "settle.json")


def main():
    tmp = tempfile.mkdtemp()
    try:
        # 1. interpolation: 10:30 local -> halfway between hours 10 and 11
        t = dt.datetime(2026, 10, 7, 10, 30)
        dev = H.interp_dev(dict(temp_now=74.25, airmass=dict(curve=CURVE)), t)
        check("interpolates curve to the minute", dev == 3.0, f"dev={dev}")

        # 2. planted underpricing: bucket priced 20c, wins 60% -> must PASS
        a = os.path.join(tmp, "a")
        g, s = world(a, 25, price=20, p_win=0.60, start=H.START_DAY)
        v = H.verdict(g, s, os.path.join(a, "v.json"))
        check("finds planted underpricing", v.get("ready") and v.get("passed"),
              json.dumps(v.get("frozen", {}).get("at_read")))
        U = H.units(g, s)
        check("picks the full-carry bucket", all(u["ticker"] == "R86" for u in U),
              U[0]["ticker"] if U else "none")

        # 3. fair market: priced 30c, wins 30% -> must NOT pass (fees make it negative)
        b = os.path.join(tmp, "b")
        g, s = world(b, 25, price=30, p_win=0.30, seed=11, start=H.START_DAY)
        v = H.verdict(g, s, os.path.join(b, "v.json"))
        check("null on fairly priced market", v.get("ready") and not v.get("passed"),
              json.dumps(v.get("frozen", {}).get("at_read")))

        # 4. below the bar: 25 days x 3 = 75 units but only 15 days -> refuse
        c = os.path.join(tmp, "c")
        g, s = world(c, 15, price=20, p_win=0.9, start=H.START_DAY)
        v = H.verdict(g, s, os.path.join(c, "v.json"))
        check("refuses below the day bar", not v.get("ready") and not v.get("passed"),
              f"units={v.get('units')} days={v.get('days')}")

        # 5. pre-registration days are ignored
        d = os.path.join(tmp, "d")
        g, s = world(d, 10, price=20, p_win=0.9,
                     start=(dt.date.fromisoformat(H.START_DAY) - dt.timedelta(days=7)).isoformat())
        check("ignores days before START_DAY", len(H.units(g, s)) == 9,
              f"n={len(H.units(g, s))}")

        # 6. first cycle only: a later qualifying cycle must not rescue a city-day
        e = os.path.join(tmp, "e")
        os.makedirs(os.path.join(e, "logs"))
        early = ladder_row("2026-10-10", "DAL", "15:10", 71.0, 20)   # dev ~ -0.4: no unit
        late = set_price(ladder_row("2026-10-10", "DAL", "16:20", 77.0, 20), "R86", 20)
        open(os.path.join(e, "logs", "2026-10-10.jsonl"), "w").write(late + "\n" + early + "\n")
        json.dump({}, open(os.path.join(e, "s.json"), "w"))
        n = len(H.units(os.path.join(e, "logs", "2*.jsonl"), os.path.join(e, "s.json")))
        check("first 10-12 local cycle only, no shopping", n == 0, f"n={n}")

        # 7. outside the window (09:30 local) is never a look
        f = os.path.join(tmp, "f")
        os.makedirs(os.path.join(f, "logs"))
        open(os.path.join(f, "logs", "2026-10-10.jsonl"), "w").write(
            set_price(ladder_row("2026-10-10", "DAL", "14:30", 72.0, 20), "R86", 20) + "\n")
        n = len(H.units(os.path.join(f, "logs", "2*.jsonl"), os.path.join(e, "s.json")))
        check("09:30 local is outside the window", n == 0, f"n={n}")

        # 8. no ask (ya 100 / None) -> no unit
        hh = os.path.join(tmp, "h")
        os.makedirs(os.path.join(hh, "logs"))
        open(os.path.join(hh, "logs", "2026-10-10.jsonl"), "w").write(
            set_price(ladder_row("2026-10-10", "DAL", "15:30", 74.25, 100), "R86", 100) + "\n")
        n = len(H.units(os.path.join(hh, "logs", "2*.jsonl"), os.path.join(e, "s.json")))
        check("no offer, no unit", n == 0, f"n={n}")

        # 9. fees charged on losses too
        check("fee on a losing fill", H.yes_pnl(20, False) == -20 - H.fee_cents(20),
              f"{H.yes_pnl(20, False)}")

        # 10. verdict is frozen at first read: a later, different world keeps it
        k = os.path.join(tmp, "k")
        g, s = world(k, 25, price=20, p_win=0.60, start=H.START_DAY)
        vf = os.path.join(k, "v.json")
        first = H.verdict(g, s, vf)
        sv = {kk: 83 for kk in json.load(open(s))}          # every unit now loses
        json.dump(sv, open(s, "w"))
        again = H.verdict(g, s, vf)
        check("verdict frozen at first read", first["passed"] and again["passed"]
              and again["context"]["current"]["mean_pnl_c"] < 0,
              f"now mean {again['context']['current']['mean_pnl_c']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nALL PASS" if not FAILURES else f"\n{len(FAILURES)} FAILURE(S): {FAILURES}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
