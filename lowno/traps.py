"""Classify rungs that show positive edge but carry known trap signals.

Writes docs/traps.json each scan. Pure analysis over the edge board plus the
adaptive/convergence state -- no gate input, no trading effect.
"""
import json, os, datetime as dt, zoneinfo
from .config import CITIES, GATE

DIVERGENCE_PTS = 0.15      # shadow finding: market won 7/8 disputes above this
MIN_DEPTH = 25             # contracts at or under max_price
GRAVEYARD = (20, 90)       # cents; every band in here has negative mean P&L
MIN_N_EFF_TRUSTED = 20     # below this the bias is essentially the prior


def _local_hour(city):
    tz = CITIES.get(city, {}).get("tz")
    if not tz:
        return None
    return dt.datetime.now(dt.timezone.utc).astimezone(zoneinfo.ZoneInfo(tz)).hour


def signals(city, rung, summary):
    """Return a list of (code, explanation) for one rung. Empty means clean."""
    out = []
    price = rung.get("price")
    p_model = rung.get("p_no")
    p_mkt = rung.get("p_mkt")
    dist = str(rung.get("dist") or "")
    depth = (rung.get("depth") or {}).get("depth_le_max")

    g = rung.get("G")
    if g is None and rung.get("guide") is not None and rung.get("ceiling") is not None:
        g = rung["guide"] - rung["ceiling"]
    if g is not None and g < GATE.get("min_g_deg", 4.0):
        out.append(("BOUNDARY",
                    f"G={g:.0f}F is inside guidance's own error bar "
                    f"(measured sigma 1.5-2.0F). The 'edge' is noise."))

    if p_model is not None and p_mkt is not None and abs(p_model - p_mkt) > DIVERGENCE_PTS:
        out.append(("DIVERGENCE",
                    f"model and market differ by {100*abs(p_model-p_mkt):.0f} pts. "
                    f"In this ledger the market won 7 of 8 such disputes."))

    adaptive = (summary.get("adaptive") or {}).get(city) or {}
    n_eff = adaptive.get("n_eff")
    if n_eff is not None and n_eff < MIN_N_EFF_TRUSTED:
        out.append(("NO_HISTORY",
                    f"n_eff={n_eff} settled days at this station -- the "
                    f"probability rests on a diffuse prior, not observation."))

    if "unfit" in dist:
        out.append(("UNFIT_DIST",
                    "marine-layer station: bimodal burn-off, a Gaussian cannot "
                    "price it. Every loss in this ledger has been one of these."))
    if "convective" in dist:
        out.append(("UNFIT_DIST",
                    "PoP above threshold: convective days left-skew the max, "
                    "which the Gaussian cannot represent."))

    if price is not None and GRAVEYARD[0] <= price <= GRAVEYARD[1]:
        out.append(("GRAVEYARD",
                    f"{price}c sits in the 20-90c range: 0 wins in 14 measured "
                    f"units below 50c, negative mean P&L in every band under 90c."))

    if depth is not None and depth < MIN_DEPTH:
        out.append(("THIN_BOOK",
                    f"only {depth} contracts resting at or under "
                    f"{int(100*GATE.get('max_price',0.98))}c -- not fillable at size."))

    conv = (summary.get("convergence") or {}).get("convergence_hour_local", {}).get(city)
    lh = _local_hour(city)
    rm, cap = rung.get("run_max"), rung.get("ceiling")
    if (conv is not None and lh is not None and lh >= conv
            and rm is not None and cap is not None and rm <= cap):
        out.append(("PAST_PEAK",
                    f"local hour {lh:02d}:00 is past this station's measured "
                    f"convergence hour ({conv:02d}:00) with the running max still "
                    f"{cap-rm:.1f}F short. The climb window has closed."))
    return out


def build(edge=None, summary=None):
    edge = edge if edge is not None else json.load(open("docs/edge.json"))
    if summary is None:
        try:
            summary = json.load(open("docs/shadow_summary.json"))
        except Exception:
            summary = {}
    rows = []
    for c in edge.get("cities", []):
        city = c.get("city")
        guide = c.get("guide")
        run_max = c.get("run_max")
        for r in c.get("rungs", []):
            if r.get("kind") != "bottom":
                continue
            edge_pts = r.get("edge")
            if edge_pts is None or edge_pts <= 0:
                continue          # only rungs that LOOK attractive
            enriched = dict(r, guide=guide, run_max=run_max)
            sig = signals(city, enriched, summary)
            if not sig:
                continue
            rows.append(dict(city=city, ceiling=r.get("ceiling"), price=r.get("price"),
                             p_model=r.get("p_no"), p_market=r.get("p_mkt"),
                             edge_pts=round(100 * edge_pts, 1),
                             size_lcb=r.get("half_kelly_lcb"),
                             signals=[{"code": k, "why": v} for k, v in sig]))
    rows.sort(key=lambda x: -x["edge_pts"])
    return dict(at=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                traps=rows,
                note=("Rungs with POSITIVE model edge that carry at least one "
                      "measured trap signal. The board sorts by edge; the largest "
                      "edges are systematically the worst bets, because a big "
                      "model-market gap at a station the model barely knows is a "
                      "statement about the model."))


def write(path="docs/traps.json", edge=None, summary=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = build(edge, summary)
    json.dump(out, open(path, "w"), indent=1)
    print(f"traps: {len(out['traps'])} positive-edge rung(s) carrying trap signals")
    for t in out["traps"]:
        print(f"   {t['city']} <={t['ceiling']} @{t['price']}c edge +{t['edge_pts']} "
              f"-> {', '.join(s['code'] for s in t['signals'])}")
    return out
