"""Prove h19_late.py measures what it claims, on SYNTHETIC data only.

Run: python test_h19_late.py     (exits non-zero on any failure)
"""
import json, os, shutil, sys, tempfile, datetime as dt, zoneinfo
import h19_late as H

FAILURES = []
TZ = "America/Chicago"            # CDT = UTC-5 on 2026-10-26; LST midnight = 06:00Z
DAY = dt.date(2026, 10, 26)
Z = zoneinfo.ZoneInfo(TZ)


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)


def ts(hhmm, day=DAY):
    h, m = map(int, hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), Z).timestamp()


def met(*pairs):
    return sorted((ts(t), v) for t, v in pairs)


def q(*rows):
    return [[ts(t), a, b] for t, a, b in rows]


R = dict(t="KX-B80.5", fl=80, cap=81)          # range bucket 80-81
TOP = dict(t="KX-T85", fl=86, cap=None)        # top bucket >=86
print("entry rules")
# A: running max 80.6 -> r=81, inside 80-81; mid 80 -> buy YES at ask 81
e = H.entries_for_rung(R, q(("15:59", 81, 79)), met(("15:53", 80.6)), TZ, DAY)
check("A fires when the bucket holds the running max, mid 71-90", len(e) == 1 and e[0]["leg"] == "A" and e[0]["price"] == 81 and e[0]["local"] == "16:00", str(e))
# not before 16:00: a 15:45 quote is used only at the 16:00 look
e = H.entries_for_rung(R, q(("15:30", 81, 79), ("16:20", 95, 93)), met(("15:53", 80.6)), TZ, DAY)
check("first look is 16:00 local, using the latest quote <= 16:00", len(e) == 1 and e[0]["price"] == 81)
# first qualifying look only: price later falls to 72, still the 16:00 entry
e = H.entries_for_rung(R, q(("15:59", 85, 83), ("16:40", 73, 71)), met(("15:53", 80.6)), TZ, DAY)
check("first trigger only, no shopping for a better price", len(e) == 1 and e[0]["price"] == 85)
# mid boundaries for A
e = H.entries_for_rung(R, q(("15:59", 71, 69)), met(("15:53", 80.6)), TZ, DAY)
check("A excludes mid 70", e == [])
e = H.entries_for_rung(R, q(("15:59", 91, 89)), met(("15:53", 80.6)), TZ, DAY)
check("A includes mid 90", len(e) == 1 and e[0]["leg"] == "A")
# dead bucket: r = 82 >= cap+1
e = H.entries_for_rung(R, q(("15:59", 81, 79)), met(("15:53", 81.9)), TZ, DAY)
check("A never buys a dead bucket", e == [])
# B: r = 78 (78.1), fl 80 -> gap 2, mid 20 -> buy NO at 100 - bid 19 = 81
e = H.entries_for_rung(R, q(("15:59", 21, 19)), met(("15:53", 78.1)), TZ, DAY)
check("B fires 1-2F below the floor, mid 11-30, NO at 100-bid", len(e) == 1 and e[0]["leg"] == "B" and e[0]["side"] == "NO" and e[0]["price"] == 81, str(e))
e = H.entries_for_rung(R, q(("15:59", 21, 19)), met(("15:53", 77.0)), TZ, DAY)
check("B skips a 3F gap", e == [])
e = H.entries_for_rung(R, q(("15:59", 11, 9)), met(("15:53", 78.1)), TZ, DAY)
check("B excludes mid 10", e == [])
e = H.entries_for_rung(R, q(("15:59", 31, 29)), met(("15:53", 78.1)), TZ, DAY)
check("B includes mid 30", len(e) == 1)
e = H.entries_for_rung(TOP, q(("15:59", 21, 19)), met(("15:53", 84.4)), TZ, DAY)
check("B works on a top bucket (fl only)", len(e) == 1 and e[0]["leg"] == "B")
# both legs on one rung at different looks: B at 16:00 (r=79), A at 17:00 (r=80, mid 80)
e = H.entries_for_rung(R, q(("15:59", 25, 23), ("16:55", 81, 79)), met(("15:53", 79.0), ("16:53", 80.1)), TZ, DAY)
check("one A and one B on the same rung both count", sorted(x["leg"] for x in e) == ["A", "B"])
# stale quote: last candle 15:20 -> 40 min old at 16:00, still the only quote
e = H.entries_for_rung(R, q(("15:20", 81, 79)), met(("15:53", 80.6)), TZ, DAY)
check("a quote older than 30 min is not a quote", e == [])
# window end: 19:00 included, 19:15 not
e = H.entries_for_rung(R, q(("18:59", 81, 79)), met(("15:53", 80.6)), TZ, DAY)
check("19:00 local is the last look (included)", len(e) == 1 and e[0]["local"] == "19:00")
e = H.entries_for_rung(R, q(("19:05", 81, 79)), met(("15:53", 80.6)), TZ, DAY)
check("nothing after 19:00", e == [])
# LST: an obs at 00:30 CDT is 23:30 LST of the previous day -> excluded
e = H.entries_for_rung(R, q(("15:59", 81, 79)), met(("00:30", 81.0), ("15:53", 75.0)), TZ, DAY)
check("running max starts at local STANDARD midnight", e == [])
# obs after the look is not used
e = H.entries_for_rung(R, q(("15:59", 81, 79), ("16:59", 81, 79)), met(("16:53", 80.6)), TZ, DAY)
check("an obs after the look is not used at that look", len(e) == 1 and e[0]["local"] == "17:00", str(e))

print("grading")
w, p = H.grade(dict(fl=80, cap=81, side="YES", price=81), 81)
check("YES wins inside, pays 100-81-ceil fee(2)", w and p == 100 - 81 - 2, str(p))
w, p = H.grade(dict(fl=80, cap=81, side="YES", price=81), 82)
check("YES loses above", (not w) and p == -83)
w, p = H.grade(dict(fl=80, cap=81, side="NO", price=81), 79)
check("NO wins below the floor", w and p == 17)
check("ceil fee >= exact fee", all(H.fee_ceil(c) >= H.fee_exact(c) for c in range(1, 100)))

print("verdict")
tmp = tempfile.mkdtemp()
try:
    out = os.path.join(tmp, "h19"); os.makedirs(out)
    vf = os.path.join(tmp, "frozen", "v.json")
    settle = {}
    def write_days(n_days, per_day, start=dt.date(2026, 10, 25), won=True):
        for i in range(n_days):
            d = (start + dt.timedelta(days=i)).isoformat()
            ents = [dict(day=d, city="OKC", ticker=f"T{i}-{k}", fl=80, cap=81, side="YES", leg="A",
                         price=50, local="16:00", ask=50, bid=48, run_max=80.0) for k in range(per_day)]
            json.dump(dict(day=d, entries=ents), open(os.path.join(out, d + ".json"), "w"))
            settle[f"{d}|OKC"] = 80 if won else 90
        json.dump(settle, open(os.path.join(tmp, "s.json"), "w"))
    # a pre-start day must be ignored
    json.dump(dict(day="2026-10-20", entries=[dict(day="2026-10-20", city="OKC", ticker="old", fl=80, cap=81,
              side="YES", leg="A", price=50)]), open(os.path.join(out, "2026-10-20.json"), "w"))
    settle["2026-10-20|OKC"] = 80
    write_days(19, 4)
    v = H.verdict(out, os.path.join(tmp, "s.json"), vf)
    check("19 days x 4 units: bar not met (days bind)", not v["ready"] and v["units"] == 76 and v["days"] == 19, str(v))
    check("pre-start day ignored", v["units"] == 76)
    # pending: a day with no settlement
    json.dump(dict(day="2026-11-20", entries=[dict(day="2026-11-20", city="OKC", ticker="p", fl=80, cap=81,
              side="YES", leg="A", price=50)]), open(os.path.join(out, "2026-11-20.json"), "w"))
    v = H.verdict(out, os.path.join(tmp, "s.json"), vf)
    check("unsettled units are pending, not graded", v["pending"] == 1 and v["units"] == 76)
    write_days(20, 4)
    v = H.verdict(out, os.path.join(tmp, "s.json"), vf)
    check("20 days x 4 units, all won: ready and PASSED", v["ready"] and v["passed"], str(v.get("frozen")))
    check("verdict frozen to file", os.path.exists(vf))
    # flip every outcome to a loss: the frozen verdict must not change
    write_days(20, 4, won=False)
    v2 = H.verdict(out, os.path.join(tmp, "s.json"), vf)
    check("frozen verdict is read ONCE (later losses do not flip it)", v2["passed"] and v2["context"]["current"]["mean_pnl_c"] < 0)
    os.remove(vf)
    v3 = H.verdict(out, os.path.join(tmp, "s.json"), vf)
    check("all-loss population fails", v3["ready"] and not v3["passed"])
finally:
    shutil.rmtree(tmp)

print(f"\n{'ALL PASS' if not FAILURES else str(len(FAILURES)) + ' FAILED: ' + ', '.join(FAILURES)}")
sys.exit(1 if FAILURES else 0)
