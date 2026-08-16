"""Empirical P(exceed cap) from the observed remaining-climb distribution.

The Gaussian in prob.py anchors on bias-corrected guide -- i.e. on NBM, the very
input this ledger measures as wrong in 12% of model-market disputes. This module
asks a different and better-posed question:

    Given this station, this local hour, and a running max already at R,
    how often has the day gone on to climb more than (CAP - R)?

That is nonparametric. It captures the left-skew of convective days and the
bimodality of marine burn-off days that a single Gaussian structurally cannot,
and it conditions on what the day HAS DONE rather than what a model predicted at
4am. It also degrades honestly: a cell without enough history returns None and
the caller falls back to the Gaussian, rather than inventing precision.
"""
import json, os
from .config import CITIES

MIN_N = 8              # per station-hour cell before it may be used
MIN_N_POOLED = 25      # per station (all hours) for the pooled fallback


def _cells():
    try:
        return (json.load(open("docs/shadow_summary.json")).get("convergence") or {}).get("cells") or {}
    except Exception:
        return {}


def _raw_climbs():
    """Rebuild raw remaining-climb samples so we can compute exceedance directly
    (the published cells hold quantiles only)."""
    import glob, datetime as dt, zoneinfo
    from collections import defaultdict
    try:
        settles = {tuple(k.split("|")): v
                   for k, v in json.load(open("docs/settlements.json")).items()}
    except Exception:
        return {}
    out = defaultdict(list)
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = r.get("detail")
            if not isinstance(d, dict):
                continue
            rm, city = d.get("run_max"), r.get("city")
            s = settles.get((day, city))
            if rm is None or s is None or city not in CITIES:
                continue
            lh = (dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
                    .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])).hour)
            out[(city, lh)].append(s - rm)
    return out


def p_exceed(city, local_hour, run_max, cap, samples=None):
    """P(daily max > cap) from observed remaining climb. None if unearned.

    Returns dict(p, n, source, needed) or None. `needed` is the climb still
    required (cap - run_max); if already negative the day has cleared the cap
    and p = 1.0 regardless of history.
    """
    if run_max is None or cap is None:
        return None
    needed = cap - run_max
    if needed < 0:
        return dict(p=1.0, n=None, source="already_exceeded", needed=round(needed, 1))
    S = samples if samples is not None else _raw_climbs()
    v = S.get((city, local_hour), [])
    src = f"cell:{city}|{local_hour:02d}"
    if len(v) < MIN_N:
        v = [x for (c, h), lst in S.items() if c == city for x in lst]
        src = f"pooled:{city}"
        if len(v) < MIN_N_POOLED:
            return None
    n = len(v)
    # strict exceedance: settlement must be ABOVE the cap
    k = sum(1 for x in v if x > needed)
    # Laplace smoothing: never report 0.000 or 1.000 off a finite sample
    p = (k + 1) / (n + 2)
    return dict(p=round(p, 4), n=n, source=src, needed=round(needed, 1),
                raw_hits=k)


def blend(p_emp, p_gauss, n):
    """Precision-weighted blend: the empirical estimate takes over as its sample
    grows. At n=MIN_N it carries ~24% weight; by n=50 it carries ~86%."""
    if p_emp is None:
        return p_gauss, "gaussian_only"
    if p_gauss is None:
        return p_emp, "empirical_only"
    w = n / (n + 8.0)
    return round(w * p_emp + (1 - w) * p_gauss, 4), f"blend(w_emp={round(w,2)})"
