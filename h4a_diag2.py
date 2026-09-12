"""DIAGNOSTIC ONLY. Is the underlying INFORMATION claim still there, separate
from the Brier failure? Pooled peak-window remaining climb by rate bucket."""
import glob,os,statistics as st
from collections import defaultdict
import shape_eval as SE
from lowno import empirical as E
days=sorted(os.path.basename(p)[:-6] for p in glob.glob("logs/2*.jsonl"))
S,R=SE.build(set(days))          # ALL days pooled -- information claim, not a forecast
print("total log days: %d"%len(days))
pool=defaultdict(list)
for (city,hour,b),v in R.items():
    if E.PEAK_WINDOW[0]<=hour<=E.PEAK_WINDOW[1]: pool[b]+=v
print("\nPOOLED remaining climb (settle - run_max) inside the peak window:")
for b in ("stalled","mid","climbing"):
    v=pool.get(b,[])
    if len(v)<20: print("  %-9s n=%-5d too few"%(b,len(v))); continue
    print("  %-9s n=%-5d mean %+.2fF  median %+.1f  sd %.2f"%(b,len(v),st.mean(v),st.median(v),st.pstdev(v)))
if pool.get("stalled") and pool.get("climbing"):
    d=st.mean(pool["climbing"])-st.mean(pool["stalled"])
    se=(st.pstdev(pool["climbing"])**2/len(pool["climbing"])+st.pstdev(pool["stalled"])**2/len(pool["stalled"]))**0.5
    print("\n  climbing - stalled = %+.2fF   se %.2f   z=%.1f"%(d,se,d/se))
    print("  (registration cited +1.48F on 1,877 samples)")
print("\nCELL POPULATION -- the binding problem")
cnt=defaultdict(int)
for (city,hour,b),v in R.items():
    if E.PEAK_WINDOW[0]<=hour<=E.PEAK_WINDOW[1]: cnt[len(v)>=E.MIN_N_RATE]+=1
print("  peak-window cells: %d total, %d at n>=%d (%.0f%%)"%(
    sum(cnt.values()),cnt[True],E.MIN_N_RATE,100*cnt[True]/max(sum(cnt.values()),1)))
sizes=sorted(len(v) for (c,h,b),v in R.items() if E.PEAK_WINDOW[0]<=h<=E.PEAK_WINDOW[1])
print("  cell size quartiles: %s"%[sizes[int(q*len(sizes))] for q in (0.25,0.5,0.75,0.95)])
print("\n  noise floor: a probability from n=12 has se ~ sqrt(.25/12) = %.3f"%((0.25/12)**0.5))
print("  expected Brier penalty from that estimation variance ~ %.4f"%(0.25/12))
print("  observed shape-base delta                            = +0.0072")
