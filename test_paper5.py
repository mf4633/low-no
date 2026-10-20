"""Synthetic checks for paper5.py's math (no network). Run: python test_paper5.py"""
import json, os, shutil, sys, tempfile
import paper5 as P

F = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        F.append(name)


# probability of a ladder sums to 1 and respects truncation
lad = [(None, 69), (70, 71), (72, 73), (74, 75), (76, None)]
ps = [P.p_rung(fl, cap, 72.4, 2.0, -999) for fl, cap in lad]
check("ladder probabilities sum to 1", abs(sum(ps) - 1) < 1e-9, f"{sum(ps):.6f}")
ps = [P.p_rung(fl, cap, 72.4, 2.0, 74) for fl, cap in lad]
check("truncation at 74 zeroes buckets below", ps[0] == 0 and ps[1] == 0 and ps[2] == 0 and abs(sum(ps) - 1) < 1e-9)

# settle + P&L arithmetic, incl. 2c on every fill
tmp = tempfile.mkdtemp()
cwd = os.getcwd()
try:
    os.chdir(tmp)
    os.makedirs("docs")
    json.dump({"2026-10-21|OKC": 76, "2026-10-21|MSP": 70}, open("docs/settlements.json", "w"))
    L = {"rule": "t", "days": {"2026-10-21": {"picks": [
        dict(city="OKC", side="YES", floor=76, cap=77, price=22, marks={"18": 40, "20": 60, "22": 95},
             p_used=.3, mid=21, edge=5, ticker="x"),
        dict(city="MSP", side="NO", floor=69, cap=70, price=31, marks={"18": 20},
             p_used=.6, mid=75, edge=5, ticker="y")]}}}
    P.save(L)
    P.settle()
    L = P.load()
    a, b = L["days"]["2026-10-21"]["picks"]
    check("YES win: hold = 100 - 22 - 2", a["won"] and a["pnl_hold"] == 76)
    check("YES sell at 20Z bid 60: 60 - 2 - 22 - 2", a["pnl_sell20"] == 34)
    check("NO on 69-70 with settle 70 loses: hold = -31 - 2", (not b["won"]) and b["pnl_hold"] == -33)
    check("NO sell at 18Z bid 20: 20 - 2 - 31 - 2", b["pnl_sell18"] == -15)
    check("missing mark -> no sell P&L recorded", "pnl_sell20" not in b)
    P.report()
    txt = open("docs/paper5.md", encoding="utf-8").read()
    check("report lists both exits and the interlock line", "Hold to settlement" in txt and "nothing proven" in txt.lower())
finally:
    os.chdir(cwd)
    shutil.rmtree(tmp)

print()
if F:
    print(f"{len(F)} FAILED: {F}")
    sys.exit(1)
print("all checks passed")
