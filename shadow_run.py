import json
from lowno import shadow
obs = shadow.build()
json.dump(obs, open("docs/shadow.json","w"), indent=1)
print(f"observations: {len(obs)}  days: {sorted(set(o['day'] for o in obs))}")
print(f"cities settled: {sorted(set(o['city'] for o in obs))}")
w = sum(1 for o in obs if o['won'])
print(f"rung-observations where NO would have won: {w}/{len(obs)}")
print("\n== guide error (NWS guide - CLI actual), by city ==")
import statistics as st
by = {}
for o in obs:
    if o['guide_err'] is not None: by.setdefault(o['city'],[]).append(o['guide_err'])
for c,v in sorted(by.items(), key=lambda kv:-st.mean(kv[1])):
    print(f"  {c:4} n={len(v):3} mean={st.mean(v):+5.1f}F  max={max(v):+3}  min={min(v):+3}")
print("\n== variant grid (one entry per city-day) ==")
print(f"{'G':>2} {'floor':>5} {'n':>3} {'wins':>4} {'hit':>6} {'pnl_c':>7} {'per':>7}")
for r in shadow.grid(obs):
    if r['n']==0: continue
    print(f"{r['G']:>2} {r['floor']:>5} {r['n']:>3} {r['wins']:>4} {r['hit']*100:>5.0f}% {r['pnl']:>7} {r['per']:>7.1f}")
