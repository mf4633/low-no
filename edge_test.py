"""DIAGNOSTIC. Is any of 2026-09-12's measurement work an EDGE, or is it priced?

Scores a model P(settle <= cap) against the MARKET's implied P from the same
orderbook row, on the realised settlement. This is the comparison H3 exists to
demand and the one today's work never made.

Model is deliberately simple and leave-one-DAY-out: the empirical distribution
of (settle - last_print) conditioned on (city, local hour), fitted on the other
12 days only. No tuning, no cell splitting -- the H4a failure says fine cells
cost more than they pay.
"""
import io,json,glob,os,datetime as dt,zoneinfo,statistics as st
from collections import defaultdict
from lowno.config import CITIES
SET={tuple(k.split("|")):v for k,v in json.load(open("docs/settlements.json")).items()}
rows=[]
for p in sorted(glob.glob("logs/poll/*.jsonl")):
    day=os.path.basename(p)[:-6]
    for line in io.open(p,encoding='utf-8'):
        try: r=json.loads(line)
        except Exception: continue
        g=r.get("rung") or {}
        cap=g.get("cap"); na,nb=g.get("na"),g.get("nb")
        city=r.get("city"); lp=r.get("last_print_f")
        if cap is None or na is None or nb is None or city not in CITIES or lp is None: continue
        s=SET.get((day,city))
        if s is None: continue
        try:
            lt=dt.datetime.fromisoformat(r["at"].replace("Z","+00:00")).astimezone(
                zoneinfo.ZoneInfo(CITIES[city]["tz"]))
        except Exception: continue
        rows.append(dict(day=day,city=city,hour=lt.hour,cap=cap,
                         mid=(na+nb)/200.0,     # NO mid as a probability
                         ask=na/100.0,
                         print_f=lp,nowcast=r.get("nowcast_f"),
                         stale=r.get("stale_min"),settle=s,
                         y=1.0 if s>cap else 0.0,   # NO wins if day runs HOTTER than cap
                         oi=g.get("oi"),vol=g.get("vol")))
print("poll rows with a settlement and a cap: %d over %d days, %d cities"%(
    len(rows),len({r['day'] for r in rows}),len({r['city'] for r in rows})))
print("realised NO-win rate (settle > cap):   %.3f"%st.mean(r['y'] for r in rows))
print("market mean implied P(NO):          %.3f"%st.mean(r['mid'] for r in rows))
# leave-one-day-out empirical distribution of settle - print, by (city, hour)
def model_p(r,train):
    key=(r['city'],r['hour'])
    v=train.get(key) or train.get((r['city'],None)) or []
    if len(v)<15: return None
    need=r['cap']-r['print_f']            # NO wins if settle-print > need
    return sum(1 for x in v if x>need)/len(v)
days=sorted({r['day'] for r in rows})
mB,mM,n=[],[],0
per=defaultdict(lambda:[0,0.0,0.0])
for hold in days:
    tr=defaultdict(list)
    for r in rows:
        if r['day']==hold: continue
        tr[(r['city'],r['hour'])].append(r['settle']-r['print_f'])
        tr[(r['city'],None)].append(r['settle']-r['print_f'])
    for r in rows:
        if r['day']!=hold: continue
        p=model_p(r,tr)
        if p is None: continue
        mB.append((p-r['y'])**2); mM.append((r['mid']-r['y'])**2); n+=1
        k=r['city']; per[k][0]+=1; per[k][1]+=(p-r['y'])**2; per[k][2]+=(r['mid']-r['y'])**2
print("\n%-34s %6s %9s %9s"%("","n","Brier","vs market"))
print("%-34s %6d %9.4f"%("MARKET (NO mid)",n,sum(mM)/n))
print("%-34s %6d %9.4f %+9.4f"%("MODEL (leave-one-day-out)",n,sum(mB)/n,sum(mB)/n-sum(mM)/n))
print("\n--- per city ---")
print("%-6s %6s %9s %9s %9s"%("city","n","model","market","delta"))
for k in sorted(per):
    c,b,m=per[k]
    print("%-6s %6d %9.4f %9.4f %+9.4f"%(k,c,b/c,m/c,b/c-m/c))
