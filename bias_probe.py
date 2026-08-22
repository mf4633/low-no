"""Measure 5-min vs METAR bias PAIRWISE, at matched timestamps.

The first version compared max-of-59 five-minute obs against max-of-1 METAR and
produced a meaningless -1.74F. Maxima over mismatched windows are not a bias.
This pairs each METAR with the 5-minute ob nearest in time (<=3 min) and reports
the per-pair difference -- the only comparison that isolates the instrument.
"""
import datetime as dt, zoneinfo
from lowno import sources, gate
from lowno.config import CITIES

def ts(o):
    return dt.datetime.fromisoformat(o["ts"].replace("Z", "+00:00"))

allpairs = []
print(f"{'city':5} {'pairs':>5} {'meanΔ':>7} {'maxΔ':>6}   sample (metar vs 5min)")
for c, cfg in sorted(CITIES.items()):
    try:
        obs = sources.latest_obs(cfg["station"])
    except Exception:
        continue
    met = [o for o in obs if o.get("raw") and o.get("tC") is not None]
    fiv = [o for o in obs if not o.get("raw") and o.get("tC") is not None]
    if not met or not fiv:
        continue
    diffs, sample = [], ""
    for m in met:
        near = min(fiv, key=lambda f: abs((ts(f) - ts(m)).total_seconds()))
        gap = abs((ts(near) - ts(m)).total_seconds())
        if gap > 180:
            continue
        d = gate.c_to_f(m["tC"]) - gate.c_to_f(near["tC"])
        diffs.append(d)
        if not sample:
            sample = f"{gate.c_to_f(m['tC']):.1f} vs {gate.c_to_f(near['tC']):.1f}"
    if diffs:
        allpairs += diffs
        print(f"{c:5} {len(diffs):>5} {sum(diffs)/len(diffs):>+7.2f} "
              f"{max(diffs, key=abs):>+6.1f}   {sample}")
if allpairs:
    n = len(allpairs)
    mean = sum(allpairs) / n
    print(f"\nPAIRED bias (METAR - nearest 5min): {mean:+.3f} F over {n} pairs")
    print(f"  |diff| > 0.5F in {sum(1 for d in allpairs if abs(d) > 0.5)}/{n} pairs")
    print(f"  METAR warmer in {sum(1 for d in allpairs if d > 0)}/{n}")
    print("\nA mean near zero means the two streams agree and run_max is fine.")
    print("A consistent positive mean means run_max is biased COOL.")
