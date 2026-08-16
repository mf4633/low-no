"""Replay every graded flag through the advisor with TIME-TRUNCATED state.

Blinding rule: the advisor may see only what existed BEFORE the flag's date.
bust_history is built from the ledger, so an un-truncated replay would hand the
advisor "2026-08-09 was a FORECAST_BUST" while testing 2026-08-09 -- a perfect,
meaningless score. Station bias is likewise recomputed from prior days only.

Scoring: the advisor's job is NOT picking winners (the gate does that). It is
catching busts the numbers score clean, without vetoing good positions. So both
directions matter:
    CAUGHT   - OVERRIDE_TO_PASS/ABSTAIN on a flag that LOST   (good)
    MISSED   - CONCUR on a flag that LOST                     (bad)
    KEPT     - CONCUR on a flag that WON                      (good)
    VETOED   - OVERRIDE_TO_PASS on a flag that WON            (costly)
"""
import json, os, sys, copy
from lowno import advisor

led = json.load(open("docs/ledger.json"))
flags = []
for day in led.get("days", []):
    for f in day.get("flags", []):
        if f.get("settle") is not None:
            flags.append((day["date"], f))
flags.sort(key=lambda x: x[0])
print(f"graded flags available: {len(flags)}\n")

_orig_load = advisor._load
def make_truncated_loader(cutoff):
    def _load(path, default):
        data = _orig_load(path, default)
        if path.endswith("ledger.json") and isinstance(data, dict):
            data = copy.deepcopy(data)
            data["days"] = [d for d in data.get("days", []) if d.get("date") < cutoff]
        if path.endswith("shadow.json") and isinstance(data, list):
            data = [o for o in data if o.get("day", "") < cutoff]
        return data
    return _load

rows = []
for date, f in flags:
    d = f["detail"]
    flag = {"city": f.get("city"), "station": f.get("station"), **d}
    advisor._load = make_truncated_loader(date)
    pack = advisor._state_pack(flag)
    ev = d.get("evidence") or {}
    obs_tail, ladder = ev.get("obs_tail", []), ev.get("ladder", [])
    has_ev = bool(obs_tail or ladder)
    out = advisor.advise(flag, obs_tail, ladder)
    advisor._load = _orig_load
    v = str(out.get("verdict", "?")).upper()
    won = f["settle"] > d.get("ceiling", 10**9)
    if won:
        cls = "KEPT" if v == "CONCUR" else "VETOED"
    else:
        cls = "MISSED" if v == "CONCUR" else "CAUGHT"
    if not has_ev:
        cls = "NO_EVIDENCE"      # pre-2026-08-16 flags: evidence pack not stored
    rows.append(dict(date=date, city=f.get("city"), ceiling=d.get("ceiling"),
                     has_evidence=has_ev,
                     price=d.get("no_ask"), settle=f["settle"], won=won,
                     verdict=v, orig=out.get("original_verdict"),
                     guard=bool(out.get("direction_guard")), cls=cls,
                     bias=(pack.get("station_bias") or {}).get("guide_minus_cli_meanF"),
                     hist_n=len(pack.get("bust_history") or []),
                     reasoning=str(out.get("reasoning", ""))[:220]))

print(f"{'date':11} {'city':4} {'ceil':>4} {'@':>5} {'CLI':>4} {'out':>5} "
      f"{'verdict':16} {'guard':5} {'class':7} {'bias':>5} {'hist'}")
for r in rows:
    print(f"{r['date']:11} {r['city']:4} {r['ceiling']:>4} {str(r['price']):>5} "
          f"{r['settle']:>4} {'WIN' if r['won'] else 'LOSS':>5} {r['verdict']:16} "
          f"{str(r['guard']):5} {r['cls']:7} {str(r['bias']):>5} {r['hist_n']}")
print()
from collections import Counter
c = Counter(r["cls"] for r in rows)
print("summary:", dict(c))
ne = c.get("NO_EVIDENCE", 0)
if ne:
    print(f"\n{ne} flag(s) predate evidence-pack persistence (added 2026-08-16) --"
          "\ntheir ABSTAINs reflect missing inputs, NOT advisor judgment. Excluded"
          "\nfrom scoring. Flags from 2026-08-16 forward are replayable.")
print(f"busts caught: {c['CAUGHT']}/{c['CAUGHT']+c['MISSED']} | "
      f"winners kept: {c['KEPT']}/{c['KEPT']+c['VETOED']}")
print("\nNOTE: n is tiny. This is a judgment smoke test, not evidence.\n")
for r in rows:
    print(f"--- {r['date']} {r['city']} [{r['cls']}]\n    {r['reasoning']}")
json.dump(rows, open("docs/advisor_backtest.json", "w"), indent=1)
