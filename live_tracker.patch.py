"""STEP 7 -- live intraday tracker for active flags.

What this answers: once a rung flags at 11am, is the day actually climbing
toward the ceiling, or stalling? Right now nothing shows that. The ledger tells
you the outcome the NEXT MORNING; the edge board shows a snapshot with no
history. For a position whose whole thesis is "the high will exceed CAP", the
useful view is the temperature trace against the ceiling, updating hourly, with
a projection.

Writes docs/active.json each scan cycle:
  * the day's observed temperature trace (from the same obs the gate uses)
  * running max so far
  * the ceiling it must exceed, and the gap remaining
  * an interpolated projected max, from the EMPIRICAL remaining-climb
    distribution at this station and local hour -- q10/q50/q90, so it is a
    range, not a false point estimate
  * whether the station has passed its measured convergence hour (after which
    the day is effectively decided)

Only tracks cities with a QUALIFIED flag today, plus any within 2F of
qualifying, so the file stays small and the panel stays legible.

Apply from repo root:  python live_tracker.patch.py
"""
import os
import sys

MODULE = '''"""Intraday tracking for flags that are live right now.

The ledger grades yesterday. The edge board is a snapshot. Neither shows the
thing that matters while a position is open: is the temperature actually
climbing toward the ceiling it has to clear?

Projection uses the empirical remaining-climb distribution (lowno.empirical),
not the Gaussian, and is reported as q10/q50/q90 -- a range. A point estimate
here would imply precision the sample size does not support.
"""
import json, os, datetime as dt, zoneinfo
from .config import CITIES


def _quantiles(samples, qs=(0.10, 0.50, 0.90)):
    if not samples:
        return None
    v = sorted(samples)
    n = len(v)
    return {f"q{int(q*100)}": round(v[min(n - 1, int(q * n))], 1) for q in qs}


def build(records, emp_samples=None, conv_hours=None):
    """records: the scan's results list (gate rows carry obs/ceiling/run_max)."""
    from . import empirical
    S = emp_samples if emp_samples is not None else empirical._raw_climbs()
    conv = conv_hours or {}
    now = dt.datetime.now(dt.timezone.utc)
    out = []

    for r in records:
        if r.get("verdict") == "LADDER":
            continue
        d = r.get("detail")
        if not isinstance(d, dict):
            continue
        city, cap, rmax = r.get("city"), d.get("ceiling"), d.get("run_max")
        if city not in CITIES or cap is None or rmax is None:
            continue

        gap = cap - rmax
        qualified = r.get("verdict") in ("QUALIFIED", "DEAD_SCAVENGE")
        # keep the file small: live flags, plus near-misses worth watching
        if not qualified and not (d.get("G") is not None and d["G"] >= 2):
            continue

        lh = now.astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])).hour
        climbs = S.get((city, lh), [])
        q = _quantiles(climbs)
        proj = None
        if q:
            proj = {k: round(rmax + v, 1) for k, v in q.items()}

        p_emp = empirical.p_exceed(city, lh, rmax, cap, samples=S)
        ch = conv.get(city)

        out.append(dict(
            city=city, station=r.get("station"), ticker=d.get("ticker"),
            verdict=r.get("verdict"), qualified=qualified,
            ceiling=cap, run_max=rmax, gap_to_clear=round(gap, 1),
            already_cleared=bool(gap < 0),
            guide=d.get("guide"), pop=d.get("pop"), no_ask=d.get("no_ask"),
            local_hour=lh,
            obs_trace=[{"ts": o.get("ts"), "f": o.get("f")}
                       for o in (d.get("evidence", {}).get("obs_tail") or [])][:12],
            remaining_climb=q, projected_max=proj,
            p_exceed_empirical=(p_emp or {}).get("p"),
            emp_n=(p_emp or {}).get("n"),
            convergence_hour=ch,
            past_convergence=(ch is not None and lh >= ch),
            note=("day effectively decided" if (ch is not None and lh >= ch)
                  else "still unresolved -- climb window open")))

    return dict(at=now.isoformat().replace("+00:00", "Z"),
                tracked=out,
                note=("Projection is the EMPIRICAL remaining-climb range at this "
                      "station and local hour, added to the running max. q10/q50/q90, "
                      "not a point forecast. NO pays only if the max EXCEEDS the ceiling."))


def write(records, emp_samples=None, conv_hours=None, path="docs/active.json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = build(records, emp_samples, conv_hours)
    json.dump(out, open(path, "w"), indent=1)
    live = sum(1 for t in out["tracked"] if t["qualified"])
    print(f"active tracker: {len(out['tracked'])} tracked, {live} qualified")
    return out
'''

SCAN_HOOK = '''    # Live intraday tracker for anything flagged or near-flagging today.
    try:
        from . import live
        _conv = {}
        try:
            _cv = json.load(open("docs/shadow_summary.json"))
            _conv = (_cv.get("convergence") or {}).get("convergence_hour_local", {})
        except Exception:
            pass
        live.write(results, emp_samples=_samples if "_samples" in dir() else None,
                   conv_hours=_conv)
    except Exception as _e:
        print("live tracker: skipped -", str(_e)[:120])

    os.makedirs("logs", exist_ok=True)'''


def main():
    if not os.path.isdir("lowno"):
        print("run from repo root")
        sys.exit(1)

    if os.path.exists("lowno/live.py"):
        print("lowno/live.py exists -- leaving alone")
    else:
        open("lowno/live.py", "w").write(MODULE)
        print("wrote lowno/live.py")

    s = open("lowno/scan.py").read()
    if "from . import live" in s:
        print("scan.py already hooked")
    elif '    os.makedirs("logs", exist_ok=True)' in s:
        s = s.replace('    os.makedirs("logs", exist_ok=True)', SCAN_HOOK, 1)
        open("lowno/scan.py", "w").write(s)
        print("hooked live tracker into scan.py")
    else:
        print("WARNING: anchor not found. Add manually before logs dir creation:")
        print(SCAN_HOOK)

    print("""
NOTE ON obs_trace
  It reads d["evidence"]["obs_tail"], which scan.py only attaches to QUALIFIED
  flags. Near-miss rows will show an empty trace until you widen that -- one
  line in scan.py if you want traces on everything.

  Also: obs_tail stores tC (Celsius). The panel converts. If you want F stored
  directly, change the evidence pack, not the tracker.
""")


if __name__ == "__main__":
    main()
