"""DIAGNOSTIC. Conditional profitability where the model DISAGREES with the book
by more than the spread. A worse-calibrated model can still pay on the subset it
disputes -- this is the only sense in which today's work could be an edge.

RULES FIXED BEFORE READING ANY RESULT:
  * ONE trade per (day, city) -- the first poll whose edge clears the bar.
    154 correlated polls per day is how a phantom edge gets manufactured.
  * Cross the spread: buy NO at the ASK, buy YES at the YES ask (= 100 - nb).
  * Kalshi fee = ceil(0.07 * P * (1-P) * 100) cents per contract, both sides.
  * Model is leave-one-DAY-out, same as edge_test.py. No tuning.
"""
import io,json,glob,os,math,datetime as dt,zoneinfo,statistics as st
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
        cap,na,nb=g.get("cap"),g.get("na"),g.get("nb")
        city,lp=r.get("city"),r.get("last_print_f")
        if None in (cap,na,nb,lp) or city not in CITIES: continue
        s=SET.get((day,city))
        if s is None: continue
        try:
            lt=dt.datetime.fromisoformat(r["at"].replace("Z","+00:00")).astimezone(
                zoneinfo.ZoneInfo(CITIES[city]["tz"]))
        except Exception: continue
        rows.append(dict(day=day,city=city,hour=lt.hour,at=r["at"],cap=cap,na=na,nb=nb,
                         print_f=lp,settle=s,y=1.0 if s>cap else 0.0))
def fee(price_c):
    P=price_c/100.0
    return math.ceil(0.07*P*(1-P)*100)
days=sorted({r['day'] for r in rows})
def model_p(r,tr):
    v=tr.get((r['city'],r['hour'])) or tr.get((r['city'],None)) or []
    if len(v)<15: return None
    need=r['cap']-r['print_f']
    return sum(1 for x in v if x>need)/len(v)
for MARGIN in (0.05,0.10,0.15,0.20):
    trades=[]
    for hold in days:
        tr=defaultdict(list)
        for r in rows:
            if r['day']==hold: continue
            tr[(r['city'],r['hour'])].append(r['settle']-r['print_f'])
            tr[(r['city'],None)].append(r['settle']-r['print_f'])
        done=set()
        for r in sorted([x for x in rows if x['day']==hold],key=lambda x:x['at']):
            k=(r['day'],r['city'])
            if k in done: continue
            p=model_p(r,tr)
            if p is None: continue
            if p-r['na']/100.0>MARGIN:                      # buy NO at ask
                cost=r['na']; f=fee(cost)
                pnl=(100-cost-f) if r['y']==1 else -(cost+f)
                trades.append((k,'NO',cost,pnl,r['y'],p,r['hour'])); done.add(k)
            elif (1-p)-(100-r['nb'])/100.0>MARGIN:          # buy YES at ask
                cost=100-r['nb']; f=fee(cost)
                pnl=(100-cost-f) if r['y']==0 else -(cost+f)
                trades.append((k,'YES',cost,pnl,r['y'],p,r['hour'])); done.add(k)
    if not trades:
        print("MARGIN %.0f%%: no trades fired"%(100*MARGIN)); continue
    pnl=[t[3] for t in trades]; wins=sum(1 for t in trades if t[3]>0)
    print("MARGIN %.0f%%  n=%-3d  wins %2d (%3.0f%%)  total %+6dc  mean %+6.2fc/trade  sd %5.1f"%(
        100*MARGIN,len(trades),wins,100*wins/len(trades),sum(pnl),st.mean(pnl),
        st.pstdev(pnl) if len(pnl)>1 else 0))
    if MARGIN==0.10:
        print("     side/price mix: "+", ".join("%s@%dc->%+dc"%(t[1],t[2],t[3]) for t in trades[:12]))
