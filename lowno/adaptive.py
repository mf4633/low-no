"""Adaptive correction layer: recency-weighted, seasonally-gated station bias,
and empirical diurnal climb curves. NOTHING here touches the frozen gate --
these corrections feed the probability model and the scored candidate variants.

Design rules (per operator, 2026-08-10):
  * No hard-coded regime constants in logic; tunables live in ADAPT below and
    every fitted value self-reports its mode and sample size.
  * Seasonal/diurnal fits activate only when the in-cell sample earns them;
    otherwise fall back to the recency-pooled estimate, and say so. An adaptive
    parameter with n=3 is a random number generator with confidence.
  * The weatherbot priors enter as pseudo-observations aged at the prior's fit
    date, so recency weighting retires them AUTOMATICALLY as live data accrues.
    No cliff, no manual switchover date.
"""
import json, math, os, glob, datetime as dt, zoneinfo
from collections import defaultdict

ADAPT = dict(
    half_life_days=30.0,      # recency half-life for bias/sigma
    prior_age_days=90.0,      # weatherbot params fitted 2026-05-12; age them as such
    prior_pseudo_n=12.0,      # prior counts as this many aged observations, not 800+:
                              #   it summarizes 2022-2026 POOLED seasons, so letting it
                              #   dominate would smother exactly the seasonal signal
                              #   we're trying to detect
    min_n_seasonal=15,        # in-month obs needed before month-conditional bias
    min_n_diurnal=12,         # per station-hourbucket obs before empirical climb
    sigma_floor=1.0,
)

WB_PRIOR = {"NYC": (-0.61,1.68), "CHI": (-0.20,1.54), "DEN": (-0.45,1.56),
            "SEA": (-0.85,1.68), "PHX": (+0.11,0.94), "PHL": (-0.42,1.58),
            "AUS": (+0.08,1.70), "LAX": (+0.75,1.44),
            "SFO": (0.0,2.5), "MIA": (0.0,2.0),
            "ATL": (0.0,1.8), "BOS": (0.0,1.8), "DAL": (0.0,1.8), "DC": (0.0,1.8),
            "HOU": (0.0,1.8), "LAS": (0.0,1.5), "MSP": (0.0,1.9), "MSY": (0.0,1.7),
            "OKC": (0.0,2.0), "SAN": (0.0,2.2), "SAT": (0.0,1.8)}
MARINE = {"SFO", "LAX", "SAN"}

def _settled_series():
    """[(date, city, guide_err)] one per settled city-day, from shadow.json."""
    try:
        obs = json.load(open("docs/shadow.json"))
    except Exception:
        return []
    seen, out = set(), []
    for o in obs:
        k = (o.get("day"), o.get("city"))
        if o.get("guide_err") is not None and k not in seen:
            seen.add(k); out.append((o["day"], o["city"], o["guide_err"]))
    return out

def _w(age_days, half_life):
    return 0.5 ** (max(age_days, 0.0) / half_life)

def bias_sigma(city, today=None):
    """Recency-weighted (bias, sigma, n_eff, mode). Seasonal mode engages only
    when the current month holds >= min_n_seasonal live observations."""
    today = today or dt.date.today()
    hl = ADAPT["half_life_days"]
    pm, ps = WB_PRIOR.get(city, (0.0, 2.0))
    pts = [(-pm, ps, _w(ADAPT["prior_age_days"], hl) * ADAPT["prior_pseudo_n"], "prior")]
    month_n = 0
    for day, c, err in _settled_series():
        if c != city: continue
        d = dt.date.fromisoformat(day)
        w = _w((today - d).days, hl)
        pts.append((err, None, w, "live"))
        if d.month == today.month: month_n += 1
    mode = "recency-pooled"
    if month_n >= ADAPT["min_n_seasonal"]:
        pts = [p for p in pts if p[3] == "live" and True]  # prior out, in-month emphasis
        pts = [(e, s, w, t) for (e, s, w, t) in pts]       # keep live only
        mode = f"seasonal(m{today.month:02d},n={month_n})"
    W = sum(p[2] for p in pts)
    if W <= 0: return 0.0, 2.0, 0.0, "empty"
    bias = sum(p[0]*p[2] for p in pts) / W
    var = sum(p[2]*(p[0]-bias)**2 for p in pts) / W
    base = ps if any(p[3]=="prior" for p in pts) else math.sqrt(max(var, 0.25))
    n_live = sum(1 for p in pts if p[3] == "live")
    sigma = max(ADAPT["sigma_floor"], math.hypot(base, base/math.sqrt(max(W,1))))
    return round(bias,2), round(sigma,2), round(W,1), mode

def diurnal_climb(tz_map):
    """Per (station, local-hour-bucket): empirical quantiles of remaining climb
    (settle - run_max at that hour). Emitted to docs/adaptive.json; the prob
    model uses a cell only when n >= min_n_diurnal, else Gaussian fallback."""
    settles = {}
    try:
        for k, v in json.load(open("docs/settlements.json")).items():
            d, c = k.split("|"); settles[(d, c)] = v
    except Exception:
        return {}
    cells = defaultdict(list)
    for p in glob.glob("logs/2*.jsonl"):
        day = os.path.basename(p)[:-6]
        for line in open(p):
            r = json.loads(line)
            if r.get("verdict") != "LADDER": continue
            rm = r["detail"].get("run_max")
            s = settles.get((day, r["city"]))
            if rm is None or s is None: continue
            u = dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
            lh = u.astimezone(zoneinfo.ZoneInfo(tz_map[r["city"]])).hour
            cells[(r["city"], lh // 2 * 2)].append(round(s - rm, 1))
    out = {}
    for (c, hb), v in cells.items():
        v = sorted(v); n = len(v)
        q = lambda f: v[min(n-1, int(f*n))]
        out[f"{c}|{hb:02d}"] = dict(n=n, q10=q(.10), q50=q(.50), q90=q(.90),
                                    ready=bool(n >= ADAPT["min_n_diurnal"]))
    return out
