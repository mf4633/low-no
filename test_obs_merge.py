"""Stale-feed fix (2026-10-08): merge_obs must surface the freshest report.
Run: python test_obs_merge.py   (exits non-zero on failure)"""
import sys
from lowno import sources, gate
F = []
def check(n, ok, d=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {n}" + (f"   [{d}]" if d else "")); ok or F.append(n)
# 10/7 KPHX shape: NWS stuck at 13:15Z, METARs kept coming
nws = [dict(ts="2026-10-07T13:15:00+00:00", tC=28.0, raw=None, wx="Clear"),
       dict(ts="2026-10-07T12:51:00+00:00", tC=27.0, raw="METAR a", wx="Clear")]
awc = [dict(ts="2026-10-07T16:51:00Z", tC=32.2, raw="METAR b", src="awc", wx=""),
       dict(ts="2026-10-07T15:51:00Z", tC=30.6, raw="METAR c", src="awc", wx=""),
       dict(ts="2026-10-07T12:51:00Z", tC=27.0, raw="METAR a", src="awc", wx="")]
m, f = sources.merge_obs(nws, awc)
check("freshest first", m[0]["ts"].startswith("2026-10-07T16:51"), m[0]["ts"])
check("duplicate minute dropped", len(m) == 4, len(m))
check("feed ages recorded", f["nws_latest"].startswith("2026-10-07T13:15")
      and f["used_src"] == "awc", f)
check("run_max sees the METAR", abs(gate.running_max_f(m) - 89.96) < 0.01, gate.running_max_f(m))
m2, f2 = sources.merge_obs(nws, [])
check("no AWC data -> old behaviour", m2 == sorted(nws, key=lambda o: o["ts"], reverse=True)
      and f2["used_src"] == "nws")
print("\nALL PASS" if not F else f"\nFAILURES: {F}"); sys.exit(1 if F else 0)
