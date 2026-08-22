"""Intraday tracking for flags that are live right now.

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
