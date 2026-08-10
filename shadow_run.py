"""Nightly shadow grading: settle every scanned rung, roll up band statistics.

Writes docs/shadow.json (row-level) and docs/shadow_summary.json (band rollup
with Wilson bounds vs. fee breakeven). Deduplicates to one entry per
city-day-band so n reflects independent observations, not scan cycles.
"""
import json, math, datetime as dt
from collections import defaultdict
from lowno import shadow

BANDS = [(1,10),(11,20),(21,30),(31,40),(41,50),(51,60),(61,70),(71,80),(81,90),(91,95),(96,98)]

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 1.0)
    p = k/n; d = 1 + z*z/n; c = (p + z*z/(2*n))/d
    m = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return (max(0.0, c-m), min(1.0, c+m))

def band_of(p):
    for lo, hi in BANDS:
        if lo <= p <= hi: return f"{lo}-{hi}"
    return None

def main():
    obs = shadow.build()
    json.dump(obs, open("docs/shadow.json", "w"), indent=1)

    units = {}
    for o in sorted(obs, key=lambda x: x["at"]):
        if o["price"] > 98: continue
        b = band_of(o["price"])
        if b is None: continue
        units.setdefault((o["day"], o["city"], b), o)   # first cycle in band

    roll = []
    for b in [f"{lo}-{hi}" for lo, hi in BANDS]:
        g = [v for k, v in units.items() if k[2] == b]
        n = len(g); k = sum(1 for x in g if x["won"])
        if n == 0:
            roll.append(dict(band=b, n=0)); continue
        mp = sum(x["price"] for x in g)/n
        fee = math.ceil(0.07*100*(mp/100)*(1-mp/100))
        need = mp/(100-fee)
        lo_, hi_ = wilson(k, n)
        roll.append(dict(band=b, n=n, wins=k, hit=k/n, mean_price=round(mp,1),
                         breakeven=round(need,4), lcb=round(lo_,4), ucb=round(hi_,4),
                         mean_pnl_c=round(sum(x["pnl"] for x in g)/n,2),
                         proven=bool(lo_ > need)))
    out = dict(generated=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z"),
               n_rung_obs=len(obs), n_units=len(units),
               days=sorted({o["day"] for o in obs}), bands=roll)
    json.dump(out, open("docs/shadow_summary.json", "w"), indent=1)

    print(f"rung-obs {len(obs)} -> {len(units)} independent units over {len(out['days'])} days")
    print(f"{'band':>6} {'n':>3} {'w':>3} {'hit':>6} {'need':>6} {'LCB':>6} {'pnl':>7} {'proven':>7}")
    for r in roll:
        if not r["n"]: continue
        print(f"{r['band']:>6} {r['n']:>3} {r['wins']:>3} {r['hit']:>6.0%} "
              f"{r['breakeven']:>6.1%} {r['lcb']:>6.0%} {r['mean_pnl_c']:>7.1f} {str(r['proven']):>7}")
    if not any(r.get("proven") for r in roll):
        print("\nNo band's 95% lower bound clears its fee breakeven. Nothing proven.")

if __name__ == "__main__":
    main()
