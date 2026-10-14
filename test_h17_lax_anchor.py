"""Prove h17_lax_anchor.py measures what it claims, on SYNTHETIC data only.

Run: python test_h17_lax_anchor.py     (exits non-zero on any failure)
"""
import json, os, shutil, sys, tempfile, datetime as dt
import h17_lax_anchor as H

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)


# Training: every cell rises exactly +3 from t18 (deterministic forecast).
TRAIN = [[(dt.date(2023, 9, 1) + dt.timedelta(days=i)).isoformat(), c, 70.0, 70.0, 73.0]
         for i in range(60) for c in ("NO_STRATUS", "EARLY_BURN", "MARINE")]
CLEAR = {"sky": {str(h): None for h in range(24)}, "tmp": {str(h): 70.0 for h in range(24)}}


def write_day(tmp, day, prices, hour="19", src="scan"):
    """prices: {(lo,hi): (ya, yb, na)}. Bucket 73 = the model's certainty."""
    os.makedirs(os.path.join(tmp, "logs", "lax_book"), exist_ok=True)
    if src == "scan":
        rungs = [dict(fl=lo, cap=hi, ya=p[0], yb=p[1], na=p[2]) for (lo, hi), p in prices.items()]
        with open(os.path.join(tmp, "logs", f"{day}.jsonl"), "a") as fh:
            fh.write(json.dumps(dict(city="LAX", verdict="LADDER", at=f"{day}T{hour}:20:00",
                                     detail=dict(rungs=rungs))) + "\n")
    else:
        rungs = [dict(floor=lo, cap=hi, ya=p[0], yb=p[1], na=p[2]) for (lo, hi), p in prices.items()]
        with open(os.path.join(tmp, "logs", "lax_book", f"{day}.jsonl"), "a") as fh:
            fh.write(json.dumps(dict(at=f"{day}T{hour}:05:00Z", rungs=rungs)) + "\n")


def ladder_prices(p73):
    """73-74 bucket YES at p73; others share the rest."""
    o = max(1, (100 - p73) // 3)
    return {(None, 70): (o, o - 1, 100 - o + 1), (71, 72): (o, o - 1, 100 - o + 1),
            (73, 74): (p73, p73 - 2, 100 - p73 + 2), (75, None): (o, o - 1, 100 - o + 1)}


def build(tmp, n_days, p73, start="2026-10-15", src="scan"):
    days = [(dt.date.fromisoformat(start) + dt.timedelta(days=i)).isoformat() for i in range(n_days)]
    for d in days:
        write_day(tmp, d, ladder_prices(p73), src=src)
    json.dump({f"{d}|LAX": 73 for d in days}, open(os.path.join(tmp, "s.json"), "w"))
    return days, {d: CLEAR for d in days}


def kw(tmp, O):
    return dict(settle_path=os.path.join(tmp, "s.json"), obs_data=O, rows=TRAIN,
                log_dir=os.path.join(tmp, "logs"), book_dir=os.path.join(tmp, "logs", "lax_book"))


def run():
    tmp = tempfile.mkdtemp()
    try:
        print("model")
        f = H.forecast("MARINE", "2026-09-15", 75.0, 75.0, TRAIN)
        check("anchors on t18 (+3)", f == {78: 1.0}, str(f))
        f = H.forecast("MARINE", "2026-09-15", 70.0, 76.0, TRAIN)
        check("truncates below the 13-18Z max", min(f) >= 76, str(f))
        sky = {str(h): (1200 if 12 <= h <= 18 else None) for h in range(24)}
        check("marine sky -> MARINE cell", H.inputs({"sky": sky, "tmp": {"18": 70.0, "13": 65.0}})[0] == "MARINE")

        print("planted underpricing: the certain bucket at 40c")
        a = os.path.join(tmp, "a"); days, O = build(a, 22, 40)
        v = H.verdict(os.path.join(a, "v.json"), None, end=days[-1], **kw(a, O))
        check("planted edge PASSES", v["passed"] is True, json.dumps(v.get("context"))[:140])
        check("verdict frozen", os.path.exists(os.path.join(a, "v.json")))

        print("fair market: the certain bucket at 97c")
        b = os.path.join(tmp, "b"); days, O = build(b, 22, 97)
        v = H.verdict(None, None, end=days[-1], **kw(b, O))
        check("no trades on a fair market -> not ready, not passed", v["passed"] is False and v["units"] < 60, str(v))

        print("below the bar")
        c = os.path.join(tmp, "c"); days, O = build(c, 15, 40)
        v = H.verdict(None, None, end=days[-1], **kw(c, O))
        check("15 days refuses", v["ready"] is False and v["days"] == 15)
        check("no P&L leaks below the bar", "context" not in v and "frozen" not in v, str(list(v)))

        print("look discipline")
        d = os.path.join(tmp, "d"); os.makedirs(os.path.join(d, "logs"))
        write_day(d, "2026-10-15", ladder_prices(40), hour="21")
        check("a 21Z-only scan is not a look", H.ladder("2026-10-15", os.path.join(d, "logs"),
                                                      os.path.join(d, "logs", "lax_book"))[0] is None)
        write_day(d, "2026-10-15", ladder_prices(40), src="book")
        check("falls back to the 19Z lax_book record",
              H.ladder("2026-10-15", os.path.join(d, "logs"), os.path.join(d, "logs", "lax_book"))[1] == "lax_book")

        print("retro gate")
        e = os.path.join(tmp, "e"); days, O = build(e, 5, 60, start="2026-08-10")
        # model certain on 73 (60c ask) but truth is 71: model loses, market less wrong
        json.dump({f"{x}|LAX": 71 for x in days}, open(os.path.join(e, "s.json"), "w"))
        old = H.RETRO; H.RETRO = (days[0], days[-1])
        try:
            r = H.retro(write=os.path.join(e, "r.json"), **kw(e, O))
            check("losing + worse Brier -> KILLED", r["killed"] is True, json.dumps(r["summary"])[:120])
            v = H.verdict(None, os.path.join(e, "r.json"), end="2026-11-30", **kw(e, O))
            check("killed retro blocks the forward verdict", "KILLED" in v.get("reason", ""))
        finally:
            H.RETRO = old
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run()
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)
