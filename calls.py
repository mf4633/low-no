"""Discretionary calls: recorded when made, graded when settled.

STRICTLY OUTSIDE THE LEDGER. These are judgement calls made in conversation,
not scored variants and not registered hypotheses. They never enter a band, a
variant table, docs/ledger.json, or any promotion bar, and no pilot may act on
them. The file exists for one reason: a call that is not written down with its
price and its reasoning at the moment it is made cannot be graded later, and
memory reliably improves it.

Records live in docs/calls.jsonl. Grade with:  python calls.py
"""
import datetime as dt
import json
import math
import os
import sys

PATH = "docs/calls.jsonl"
FEE = lambda pc: math.ceil(0.07 * 100 * (pc / 100) * (1 - pc / 100))


def add(rec):
    os.makedirs("docs", exist_ok=True)
    with open(PATH, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print("recorded:", json.dumps(rec))


def load():
    if not os.path.exists(PATH):
        return []
    return [json.loads(l) for l in open(PATH) if l.strip()]


def grade():
    try:
        settles = {tuple(k.split("|")): v
                   for k, v in json.load(open("docs/settlements.json")).items()}
    except Exception:
        settles = {}
    rows = load()
    if not rows:
        print("no calls recorded")
        return
    print(f"{'day':12}{'city':5}{'bucket':10}{'side':5}{'px':>4}{'settle':>8}"
          f"{'result':>9}{'P&L':>7}")
    tot = n = w = 0
    for r in rows:
        s = settles.get((r["day"], r["city"]))
        if s is None:
            print(f"{r['day']:12}{r['city']:5}{r['bucket']:10}{r['side']:5}"
                  f"{r['price']:>4}{'-':>8}{'pending':>9}{'':>7}")
            continue
        lo, hi = r.get("lo"), r.get("hi")
        inside = ((lo is None or s >= lo) and (hi is None or s <= hi))
        won = inside if r["side"] == "YES" else (not inside)
        f = FEE(r["price"])
        pnl = (100 - r["price"] - f) if won else -(r["price"] + f)
        tot += pnl; n += 1; w += 1 if won else 0
        print(f"{r['day']:12}{r['city']:5}{r['bucket']:10}{r['side']:5}"
              f"{r['price']:>4}{s:>8}{('WIN' if won else 'LOSS'):>9}{pnl:>+7.0f}")
    if n:
        print(f"\n{n} settled, {w}W-{n-w}L, {tot:+.0f}c total, {tot/n:+.1f}c/call")
        print("Discretionary and unregistered. Not evidence for or against any "
              "hypothesis.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "add":
        add(json.loads(sys.argv[2]))
    else:
        grade()
