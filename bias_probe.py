"""Measure the 5-minute vs METAR max bias across all stations."""
import datetime as dt, zoneinfo
from lowno import sources, gate
from lowno.config import CITIES
print(f"{'city':5} {'5min':>6} {'metar':>6} {'diff':>6}  n5/nM")
tot, n = 0.0, 0
for c, cfg in sorted(CITIES.items()):
    try:
        obs = sources.latest_obs(cfg["station"])
    except Exception as e:
        print(f"{c:5} fetch fail {str(e)[:30]}"); continue
    today = dt.datetime.now(zoneinfo.ZoneInfo(cfg["tz"])).date().isoformat()
    tod = []
    for o in obs:
        try:
            loc = dt.datetime.fromisoformat(o["ts"].replace("Z","+00:00")).astimezone(
                zoneinfo.ZoneInfo(cfg["tz"])).date().isoformat()
        except Exception: continue
        if loc == today: tod.append(o)
    five = [gate.c_to_f(o["tC"]) for o in tod if o.get("tC") is not None and not o.get("raw")]
    met  = [gate.c_to_f(o["tC"]) for o in tod if o.get("tC") is not None and o.get("raw")]
    if five and met:
        d = max(met) - max(five); tot += d; n += 1
        print(f"{c:5} {max(five):6.1f} {max(met):6.1f} {d:+6.1f}  {len(five)}/{len(met)}")
    else:
        print(f"{c:5} {'--':>6} {'--':>6} {'--':>6}  {len(five)}/{len(met)}")
if n: print(f"\nmean bias (METAR - 5min): {tot/n:+.2f} F across {n} stations")
