"""Prove h18_growing.py measures what it claims, on SYNTHETIC data only.

Run: python test_h18_growing.py     (exits non-zero on any failure)
"""
import json, os, shutil, sys, tempfile
import h18_growing as H

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILURES.append(name)


# OKC is America/Chicago (CDT = UTC-5 in October). Flat curve at 70F all day,
# curve max 80, so dev = temp_now - 70 and the projection = 80 + dev.
CURVE = {str(h): 70.0 for h in range(24)}


def rungs(ya_map):
    """Ladder <=79 / 80-81 / 82-83 / 84-85 / >=86 with YES asks from ya_map."""
    spec = [(None, 79), (80, 81), (82, 83), (84, 85), (86, None)]
    out = []
    for fl, cap in spec:
        ya = ya_map.get((fl, cap), 3)
        out.append(dict(t=f"T-{fl}-{cap}", fl=fl, cap=cap, ya=ya, yb=max(0, ya - 2), na=100 - ya + 2))
    return out


def row(day, hhmm_utc, temp, pop=0, ya_map=None, city="OKC"):
    return dict(city=city, verdict="LADDER", at=f"{day}T{hhmm_utc}:00",
                detail=dict(temp_now=temp, pop=pop, rungs=rungs(ya_map or {}),
                            airmass=dict(curve=CURVE, curve_max_f=80.0)))


def run(rows_by_day, settle):
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, "logs"))
        for day, rows in rows_by_day.items():
            with open(os.path.join(tmp, "logs", f"{day}.jsonl"), "w") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
        sp = os.path.join(tmp, "settle.json")
        json.dump(settle, open(sp, "w"))
        U = H.units(os.path.join(tmp, "logs", "2*.jsonl"), sp)
        V = H.verdict(os.path.join(tmp, "logs", "2*.jsonl"), sp,
                      verdict_file=os.path.join(tmp, "frozen", "v.json"))
        V2 = H.verdict(os.path.join(tmp, "logs", "2*.jsonl"), sp,
                       verdict_file=os.path.join(tmp, "frozen", "v.json"))
        return U, V, V2
    finally:
        shutil.rmtree(tmp)


D = "2026-10-22"
# 15:00Z = 10:00 CDT, 16:00Z = 11:00 CDT
print("trigger logic")
U, _, _ = run({D: [row(D, "15:00", 71.0), row(D, "16:00", 72.5, ya_map={(82, 83): 30})]},
              {f"{D}|OKC": 82})
check("growing warm dev triggers (dev +1 -> +2.5)", len(U) == 1 and U[0]["dev2"] == 2.5)
check("projection = round(curve_max + dev2) = 82 -> 82-83 rung", U and U[0]["proj"] == 82 and U[0]["price"] == 30)
check("win graded with fee on the fill", U and U[0]["won"] and U[0]["pnl"] == 100 - 30 - 2)

U, _, _ = run({D: [row(D, "15:00", 71.8), row(D, "16:00", 72.5)]}, {f"{D}|OKC": 82})
check("growth < 1.0 does not trigger", len(U) == 0)

U, _, _ = run({D: [row(D, "15:00", 69.0), row(D, "16:00", 71.2)]}, {f"{D}|OKC": 82})
check("dev2 < 1.5 does not trigger even with growth", len(U) == 0)

U, _, _ = run({D: [row(D, "15:00", 69.0), row(D, "16:00", 66.0)]}, {f"{D}|OKC": 76})
check("cold growing does NOT trigger (warm only)", len(U) == 0)

U, _, _ = run({D: [row(D, "15:00", 71.0, pop=40), row(D, "16:00", 72.5, pop=40)]}, {f"{D}|OKC": 82})
check("PoP > 20 excluded", len(U) == 0)

U, _, _ = run({D: [row(D, "15:00", 71.0), row(D, "15:30", 72.5)]}, {f"{D}|OKC": 82})
check("gap < 45 min does not pair", len(U) == 0)

U, _, _ = run({D: [row(D, "12:00", 71.0), row(D, "13:00", 72.5)]}, {f"{D}|OKC": 82})
check("before 09:00 local excluded (07:00/08:00 CDT)", len(U) == 0)

U, _, _ = run({"2026-10-20": [row("2026-10-20", "15:00", 71.0), row("2026-10-20", "16:00", 72.5)]},
              {"2026-10-20|OKC": 82})
check("days before START_DAY excluded", len(U) == 0)

U, _, _ = run({D: [row(D, "15:00", 71.0), row(D, "16:00", 72.5, ya_map={(82, 83): 1}),
                   row(D, "17:00", 74.0, ya_map={(84, 85): 30})]}, {f"{D}|OKC": 84})
check("first trigger decides: ask out of range -> no unit, later cycles not tried", len(U) == 0)

U, _, _ = run({D: [row(D, "15:00", 71.0), row(D, "16:00", 72.5, ya_map={(82, 83): 30}),
                   row(D, "17:00", 74.0, ya_map={(84, 85): 30})]}, {f"{D}|OKC": 84})
check("one unit per city-day (first trigger)", len(U) == 1 and U[0]["proj"] == 82 and U[0]["won"] is False)

print("verdict")
rows, settle = {}, {}
import datetime as _dt
for k in range(20):
    day = (_dt.date(2026, 10, 22) + _dt.timedelta(days=k)).isoformat()
    rows[day] = []
    for c in ("OKC", "DAL", "AUS"):
        rows[day] += [row(day, "15:00", 71.0, city=c), row(day, "16:00", 72.5, city=c, ya_map={(82, 83): 30})]
        settle[f"{day}|{c}"] = 82          # every unit wins
U, V, V2 = run(rows, settle)
check("bar met at 60 units / 20 days", V.get("ready") and V["units"] == 60 and V["days"] == 20, str(V.get("units")))
check("all-win set passes (LCB > 0)", V.get("passed") is True)
check("verdict frozen and re-read identically", V2.get("frozen") == V.get("frozen"))

for k in rows:
    for c in ("OKC", "DAL", "AUS"):
        settle[f"{k}|{c}"] = 80            # every unit loses
U, V, _ = run(rows, settle)
check("all-loss set fails", V.get("ready") and V.get("passed") is False)

rows19 = {k: v for i, (k, v) in enumerate(sorted(rows.items())) if i < 19}
U, V, _ = run(rows19, settle)
check("19 days is below the bar even with 57 units", V.get("ready") is False)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("all checks passed")
