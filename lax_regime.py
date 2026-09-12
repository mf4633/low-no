r"""LAX marine-layer regime classifier -- WEATHER leg only.

Built and frozen 2026-09-12 on FREE data, with NO price data in the loop. The
market claim is a separate, later scoring; this file only establishes whether
the regime splits the daily high at all. If it does not, there is nothing to
register.

Regime is decided from MORNING observations only (by 10:00 PDT / 17Z), so it is
knowable before the peak:
  NO_STRATUS  no ceiling below 3000 ft in the 12Z-17Z window
  EARLY_BURN  stratus present at 12Z-14Z, gone by 17Z
  LATE_BURN   stratus still present at 17Z, gone by 20Z
  NO_BURN     stratus still present at 20Z (1pm PDT)
"""
import io,csv,json,urllib.request,statistics as st,os,time
from collections import defaultdict,Counter
os.makedirs('cache',exist_ok=True)
def cached(n,fn):
    p=os.path.join('cache',n)
    if os.path.exists(p) and os.path.getsize(p)>200: return io.open(p,encoding='utf-8').read()
    for a in range(6):
        try: d=fn(); io.open(p,'w',encoding='utf-8').write(d); return d
        except Exception as e:
            if a==5: raise
            time.sleep(6*(a+1))
def metars(y):
    u=("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=LAX"
       "&data=tmpf&data=skyc1&data=skyl1&data=skyc2&data=skyl2"
       "&year1=%d&month1=1&day1=1&year2=%d&month2=1&day2=1&tz=UTC"
       "&format=onlycomma&latlon=no&missing=M&trace=T&direct=no&report_type=3")%(y,y+1)
    return cached('LAXreg_%d.csv'%y,lambda: urllib.request.urlopen(u,timeout=900).read().decode())
def cli():
    out={}
    for y in (2022,2023,2024,2025,2026):
        try:
            d=json.loads(cached('LAXcli_%d.json'%y,lambda: urllib.request.urlopen(
              "https://mesonet.agron.iastate.edu/json/cli.py?station=KLAX&year=%d"%y,timeout=120).read().decode()))
        except Exception: continue
        for r in d.get('results') or []:
            h=r.get('high')
            if h in (None,'','M'): continue
            try: out[r['valid'][:10]]=float(h)
            except Exception: pass
    return out
def ceil_ft(r):
    lo=None
    for c,l in ((r.get('skyc1'),r.get('skyl1')),(r.get('skyc2'),r.get('skyl2'))):
        if c in ('BKN','OVC') and l not in ('M','',None):
            try: v=float(l)
            except Exception: continue
            lo=v if lo is None else min(lo,v)
    return lo
def regime(obs):
    """obs: {utc_hour: ceiling_ft or None} for one day."""
    def st_at(h): 
        c=obs.get(h)
        return c is not None and c<3000
    early=any(st_at(h) for h in (12,13,14))
    at17=any(st_at(h) for h in (16,17,18))
    at20=any(st_at(h) for h in (19,20,21))
    if not early and not at17: return 'NO_STRATUS'
    if at20: return 'NO_BURN'
    if at17: return 'LATE_BURN'
    return 'EARLY_BURN'
if __name__=='__main__':
    C=cli(); days=defaultdict(dict)
    for y in (2022,2023,2024,2025,2026):
        try: txt=metars(y)
        except Exception as e: print('  %d failed: %s'%(y,str(e)[:50])); continue
        for r in csv.DictReader(io.StringIO(txt)):
            v=r['valid']
            days[v[:10]][int(v[11:13])]=ceil_ft(r)
        print('  %d: %d days'%(y,len([d for d in days if d[:4]==str(y)])))
    rows=[]
    for d,obs in days.items():
        if d not in C or len(obs)<18: continue
        rows.append((d,regime(obs),C[d]))
    print('\nn=%d LAX days with CLI + full hourly sky, 2022-2026\n'%len(rows))
    print('%-12s %6s %8s %7s %7s %7s %7s'%('regime','n','mean hi','sd','p10','med','p90'))
    for g in ('NO_STRATUS','EARLY_BURN','LATE_BURN','NO_BURN'):
        v=sorted(x[2] for x in rows if x[1]==g)
        if len(v)<10: print('%-12s %6d  too few'%(g,len(v))); continue
        q=lambda p:v[min(len(v)-1,int(p*len(v)))]
        print('%-12s %6d %8.1f %7.2f %7.0f %7.0f %7.0f'%(g,len(v),st.mean(v),st.pstdev(v),q(.1),q(.5),q(.9)))
    allv=[x[2] for x in rows]
    print('\nALL          %6d %8.1f %7.2f'%(len(allv),st.mean(allv),st.pstdev(allv)))
    io.open('lax_regimes.json','w',encoding='utf-8').write(json.dumps(rows))
