"""Probability engine for the low-no ladder: P(daily max > ceiling) per rung,
edge vs. market, sigma, half-Kelly with an LCB shrink.

Conventions ported from weatherbot (mf4633/weatherbot) so numbers on the two
sites read the same way:
  halfKelly(p, c) = max(0, (p*b - (1-p)) / b) / 2,  b = (1-c)/c   [analyze_best_case.js]
  normCdf via Abramowitz & Stegun 7.1.26 erf                       [erf.js]
  Kelly-LCB shrink: size on the LOWER confidence bound of pWin, not the point
  estimate; a rung whose LCB-Kelly is 0 shows edge but earns no size.

Model (documented so the site can say exactly what it believes):
  T_max ~ Normal(mu, sigma), where
    mu    = guide - bias(city)
    bias  = precision-weighted blend of the weatherbot prior (y_mean at guide
            scale, n>=820 days, 2022-2026) and the live settlement ledger
            (n = days settled so far). Live data dominates as it accumulates.
    sigma = sigma_seed(city) from weatherbot warm-regime params, inflated by
            bias-estimation uncertainty; floored at 1.0F.
  Hard truncation: if run_max already exceeds the ceiling, P(over) = 1. Else
  condition on T_max >= run_max (the max can't be less than what's been seen):
    P(over ceiling | max >= run_max) = Q(ceil) / Q(run_max), Q(x)=1-Phi((x-mu)/sig)

NON-NORMAL STATIONS: SFO and LAX marine-layer days are bimodal (burn-off vs.
cap), and SFO has no weatherbot prior at all. A single Gaussian CANNOT price
these -- the model marks them dist="marine/unfit" and refuses a half-Kelly
(size 0) until an empirical error distribution exists (n>=20 settled days).
Numbers shown for them are Gaussian reference values, explicitly untrusted.
"""
import json, math, os
from collections import defaultdict

# weatherbot per_city_kalman_params.json, high side, warm regime (fitted 2026-05-12)
WB_PRIOR = {  # city: (y_mean = mean(CLI - guide-scale est), sigma_obs_warm, n)
    "NYC": (-0.61, 1.68, 825), "CHI": (-0.20, 1.54, 845), "DEN": (-0.45, 1.56, 837),
    "SEA": (-0.85, 1.68, 822), "PHX": (+0.11, 0.94, 821), "PHL": (-0.42, 1.58, 823),
    "AUS": (+0.08, 1.70, 822), "LAX": (+0.75, 1.44, 820),
    # SFO, MIA: no weatherbot fit. Diffuse prior: zero bias, wide sigma, tiny n.
    "SFO": (0.0, 2.5, 4), "MIA": (0.0, 2.0, 4),
    # New stations 2026-08-22: no weatherbot fit exists. Diffuse priors -- wide
    # sigma, tiny pseudo-n, so live settlements dominate within ~2 weeks.
    "ATL": (0.0, 1.8, 4), "BOS": (0.0, 1.8, 4), "DAL": (0.0, 1.8, 4),
    "DC": (0.0, 1.8, 4), "HOU": (0.0, 1.8, 4), "LAS": (0.0, 1.5, 4),
    "MSP": (0.0, 1.9, 4), "MSY": (0.0, 1.7, 4), "OKC": (0.0, 2.0, 4),
    "SAN": (0.0, 2.2, 4), "SAT": (0.0, 1.8, 4),
}
MARINE = {"SFO", "LAX", "SAN"}   # bimodal burn-off; Gaussian unfit. SAN added 2026-08-22.          # bimodal burn-off regime: Gaussian unfit
EMPIRICAL_MIN_N = 20             # settled days needed before trusting a fit
FEE = lambda pc: math.ceil(7 * (pc/100) * (1 - pc/100)) / 100  # dollars

def norm_cdf(z):
    # A&S 7.1.26 via erf, matching weatherbot/erf.js to ~1.5e-7
    a1,a2,a3,a4,a5,p = 0.254829592,-0.284496736,1.421413741,-1.453152027,1.061405429,0.3275911
    x = z / math.sqrt(2); sign = -1 if x < 0 else 1; x = abs(x)
    t = 1/(1+p*x)
    y = 1-(((((a5*t+a4)*t)+a3)*t+a2)*t+a1)*t*math.exp(-x*x)
    return 0.5*(1+sign*y)

def half_kelly(p, c):
    """p = P(win) buying at price c (0..1). weatherbot analyze_best_case.js."""
    if c <= 0 or c >= 1: return 0.0
    b = (1-c)/c
    return max(0.0, (p*b - (1-p))/b) / 2

def live_bias(city):
    """(mean_err, n_days) from the settlement-vs-guide ledger, via shadow.json."""
    try:
        obs = json.load(open("docs/shadow.json"))
    except Exception:
        return 0.0, 0
    seen, errs = set(), []
    for o in obs:
        cd = (o.get("day"), o.get("city"))
        if o.get("city") == city and o.get("guide_err") is not None and cd not in seen:
            seen.add(cd); errs.append(o["guide_err"])
    if not errs: return 0.0, 0
    return sum(errs)/len(errs), len(errs)

def station_model(city):
    """Adaptive bias/sigma from lowno.adaptive: recency-weighted, seasonal when
    earned, priors retired automatically as live data accrues. Trust taxonomy
    unchanged: marine stations stay unfit for a Gaussian regardless of n until
    an explicit empirical distribution replaces it."""
    from . import adaptive
    bias, sigma, n_eff, mode = adaptive.bias_sigma(city)
    _, ln = live_bias(city)
    if city in MARINE:
        dist = "marine/unfit"
    elif ln < EMPIRICAL_MIN_N:
        dist = "no-prior/unfit" if city == "MIA" and ln < 5 else "empirical-pending"
    else:
        dist = "normal"
    return dict(bias=bias, sigma=sigma, n_live=ln, n_prior=round(n_eff,1),
                mode=mode, dist=dist)

def rung_probability(ceiling, guide, run_max, model):
    """P(daily max > ceiling), truncated at the observed running max."""
    if guide is None or ceiling is None:
        return None
    if run_max is not None and run_max > ceiling:
        return 1.0
    mu = guide - model["bias"]
    sig = model["sigma"]
    q = lambda x: 1 - norm_cdf((x - mu)/sig)
    p_over = q(ceiling + 0.5)          # settle in whole degrees: > ceiling means >= ceiling+1
    if run_max is not None:
        denom = q(run_max)
        if denom > 1e-9:
            p_over = min(1.0, p_over/denom)
    return p_over

def evaluate_ladder(city, rungs, guide, run_max, pop, local_hour=None,
                    emp_samples=None):
    """Per-rung: pWin(NO), market pWin, edge, EV, half-Kelly point + LCB."""
    m = station_model(city)
    out = []
    for r in rungs:
        cap, fl, na = r.get("cap"), r.get("floor"), r.get("no_ask")
        if na is None or (cap is None and fl is None): continue
        if guide is None: continue
        mu, sig = guide - m["bias"], m["sigma"]
        Q = lambda x: 1 - norm_cdf((x - mu)/sig)     # P(T_max > x)
        trunc = Q(run_max) if (run_max is not None and Q(run_max) > 1e-9) else 1.0
        if fl is None:            # bottom "T<=cap": NO wins iff T > cap
            kind, label = "bottom", f"<={cap}"
            p_no = 1.0 if (run_max is not None and run_max > cap) else min(1.0, Q(cap+0.5)/trunc)
            z_ref = (cap+0.5-mu)/sig
        elif cap is None:         # top "T>=fl": NO wins iff T < fl
            kind, label = "top", f">={fl}"
            p_no = 0.0 if (run_max is not None and run_max >= fl) else                    max(0.0, (Q(run_max if run_max is not None else -999) - Q(fl-0.5))/trunc)
            z_ref = (fl-0.5-mu)/sig
        else:                     # range "fl<=T<=cap": NO wins iff T outside
            kind, label = "range", f"{fl}-{cap}"
            if run_max is not None and run_max > cap:
                p_no = 1.0        # already busted high
            else:
                p_in = max(0.0, (Q(fl-0.5) - Q(cap+0.5))/trunc)
                p_no = max(0.0, min(1.0, 1.0 - p_in))
            z_ref = (cap+0.5-mu)/sig
        p_over = p_no  # kept name for LCB block below

        # Empirical override/blend: P(remaining climb > cap - run_max) observed
        # at this station-hour. Nonparametric, so it represents skew and
        # bimodality the Gaussian cannot; blended by its own sample size so it
        # takes over only as it earns the weight.
        emp = None
        if kind == "bottom" and local_hour is not None:
            try:
                from . import empirical
                emp = empirical.p_exceed(city, local_hour, run_max, cap,
                                         samples=emp_samples)
                if emp:
                    p_no, blend_src = empirical.blend(emp["p"], p_no, emp.get("n") or 0)
                else:
                    blend_src = "gaussian_only"
            except Exception:
                blend_src = "gaussian_error"
        else:
            blend_src = "gaussian_only"
        price = na/100.0
        fee = FEE(na)
        ev = p_no*(1 - price - fee) - (1-p_no)*price      # $ per $1 contract
        # LCB: shift pWin down by 1.96 * |dP/dmu| * se(bias).
        # (Audit fix 2026-08-10: previous version multiplied by an extra sigma,
        # UNDER-shrinking wherever sigma > 1 -- i.e., less conservative than
        # advertised at every station except PHX.)
        se = m["sigma"]/math.sqrt(max(m["n_prior"]+m["n_live"],1))
        dpdmu = math.exp(-z_ref*z_ref/2)/math.sqrt(2*math.pi)/m["sigma"]
        p_lcb = max(0.0, p_no - 1.96*dpdmu*se)
        hk, hk_lcb = half_kelly(p_no, price), half_kelly(p_lcb, price)
        # Unconditional position ceiling (config GATE.max_position_frac). Kelly at
        # a 97c near-certainty says 40%+; that is right arithmetic on an unproven p,
        # and Kelly with a mis-estimated p ruins rather than underperforms.
        from .config import GATE as _G
        _cap = _G.get("max_position_frac", 0.05)
        hk_capped, hk_lcb_capped = min(hk, _cap), min(hk_lcb, _cap)
        dist = m["dist"]
        warn = []
        if pop is not None and pop > 20:
            # Convective days left-skew the max (outflow/anvil cap). The Gaussian
            # cannot represent that; do not size on it. Mirrors the gate's PoP rule.
            dist += "+convective"; warn.append(f"PoP {pop} -- Gaussian unfit on storm days")
        yb = r.get("yes_bid")
        p_mkt_v = (100-yb)/100 if yb is not None else na/100   # None-check: yb=0 is a real quote
        if abs(p_no - p_mkt_v) > 0.15:
            # Own shadow finding: on model-vs-market divergence the market was
            # right 7/8. Divergence is a red flag here, not an opportunity.
            warn.append("model-market divergence >15pts -- market historically wins this regime")
            hk_lcb = 0.0
        if dist.endswith("unfit") or "+convective" in dist:
            hk_lcb = 0.0                       # refuse size where the model is unfit
        out.append(dict(ticker=r.get("ticker") or r.get("t"), ceiling=cap, floor=fl,
            kind=kind, label=label,
            price=na, p_no=round(p_no,4), p_mkt=round(p_mkt_v,4),
            edge=round(p_no - price,4), ev_c=round(ev*100,1),
            sigma=m["sigma"], bias=m["bias"], dist=dist, warn=warn,
            p_empirical=(emp or {}).get("p"), emp_n=(emp or {}).get("n"),
            emp_source=(emp or {}).get("source"), p_source=blend_src,
            half_kelly=round(hk,4), half_kelly_lcb=round(hk_lcb,4),
            size_frac=round(hk_lcb_capped,4), size_cap=_cap,
            cap_binding=bool(hk_lcb > _cap)))
    return dict(city=city, model=m, guide=guide, run_max=run_max, pop=pop, rungs=out)
