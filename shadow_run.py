"""Nightly shadow grading: settle every scanned rung, roll up band statistics.

Writes docs/shadow.json (row-level) and docs/shadow_summary.json (band rollup
with Wilson bounds vs. fee breakeven). Deduplicates to one entry per
city-day-band so n reflects independent observations, not scan cycles.
"""
import json, math, datetime as dt, zoneinfo
from collections import defaultdict
from lowno import shadow, adaptive, convergence, spend
from lowno.config import CITIES

MARINE_CITIES = {"SFO", "LAX", "SAN"}   # keep in sync with lowno.prob.MARINE

BANDS = [(1,10),(11,20),(21,30),(31,40),(41,50),(51,60),(61,70),(71,80),(81,90),(91,95),(96,98)]

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 1.0)
    p = k/n; d = 1 + z*z/n; c = (p + z*z/(2*n))/d
    m = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return (max(0.0, c-m), min(1.0, c+m))

def band_of(p):
    for lo, hi in BANDS:
        if lo <= p <= hi: return f"{lo}-{hi}"
    return None

def main():
    obs = shadow.build()
    json.dump(obs, open("docs/shadow.json", "w"), indent=1)

    bottom = [o for o in obs if o.get("kind", "bottom") == "bottom"]
    units = {}
    for o in sorted(bottom, key=lambda x: x["at"]):
        if o["price"] > 98: continue
        b = band_of(o["price"])
        if b is None: continue
        units.setdefault((o["day"], o["city"], b), o)   # first cycle in band

    roll = []
    for b in [f"{lo}-{hi}" for lo, hi in BANDS]:
        g = [v for k, v in units.items() if k[2] == b]
        n = len(g); k = sum(1 for x in g if x["won"])
        if n == 0:
            roll.append(dict(band=b, n=0)); continue
        mp = sum(x["price"] for x in g)/n
        fee = math.ceil(0.07*100*(mp/100)*(1-mp/100))
        need = mp/(100-fee)
        lo_, hi_ = wilson(k, n)
        roll.append(dict(band=b, n=n, wins=k, hit=k/n, mean_price=round(mp,1),
                         breakeven=round(need,4), lcb=round(lo_,4), ucb=round(hi_,4),
                         mean_pnl_c=round(sum(x["pnl"] for x in g)/n,2),
                         proven=bool(lo_ > need)))
    # Per-station guide bias from settled days: mean(guide - CLI). This is the
    # transfer-function candidate (same shape as the EWR-3.5 KNYC correction).
    bias_acc = defaultdict(list)
    seen_cd = set()
    for o in obs:   # bias uses ALL kinds: guide_err is per city-day, kind-independent
        cd = (o["day"], o["city"])
        if o.get("guide_err") is not None and cd not in seen_cd:
            seen_cd.add(cd); bias_acc[o["city"]].append(o["guide_err"])
    bias = {c: round(sum(v)/len(v), 2) for c, v in bias_acc.items()}

    # Candidate rules scored on the SAME deduped city-day units, one entry each.
    # frozen: the live gate's shape (G>=4, price<=98, no floor)
    # corrected: G computed from bias-corrected guide
    # corrected+floor: adds the 90c floor the band data motivates
    def score_rule(name, keep):
        taken, seen = [], set()
        for o in sorted(bottom, key=lambda x: x["at"]):
            if o["price"] > 98 or o["G"] is None: continue
            cd = (o["day"], o["city"])
            if cd in seen or not keep(o): continue
            seen.add(cd); taken.append(o)
        n = len(taken); k = sum(1 for t in taken if t["won"])
        lo_, _ = wilson(k, n)
        return dict(rule=name, n=n, wins=k, hit=(k/n if n else None),
                    lcb=round(lo_, 3), pnl_c=sum(t["pnl"] for t in taken),
                    mean_pnl_c=(round(sum(t["pnl"] for t in taken)/n, 2) if n else None))
    abias = {c: adaptive.bias_sigma(c)[0] for c in bias} or \
            {c: adaptive.bias_sigma(c)[0] for c in {o["city"] for o in obs}}
    def gcorr(o): return o["G"] - abias.get(o["city"], 0.0)
    # Per-station entry windows from MEASURED convergence hours. The frozen gate
    # uses one 10:30-13:30 window for all ten stations; the convergence data says
    # LAX resolves by 12:00 while DEN has not resolved by any earned hour. This
    # variant enters only at/after a station's convergence hour (when the median
    # remaining climb is <=1F), i.e. when the day is effectively decided.
    conv = (convergence.build() or {}).get("convergence_hour_local", {})

    def _local_hour(o):
        try:
            u = dt.datetime.fromisoformat(o["at"]).replace(tzinfo=dt.timezone.utc)
            return u.astimezone(zoneinfo.ZoneInfo(CITIES[o["city"]]["tz"])).hour
        except Exception:
            return None

    def in_conv_window(o):
        h, ch = _local_hour(o), conv.get(o["city"])
        if h is None or ch is None:
            return False          # station has not earned a convergence hour yet
        return ch <= h <= ch + 3

    # Minimum depth: is the 96-98c band actually INVESTABLE? Every P&L figure
    # assumes a fill at the logged ask; DEN showed 3 contracts resting there.
    # Depth logging began 2026-08-13, so this variant's n starts from that date.
    def has_depth(o, need=25):
        d = o.get("depth") or {}
        return (d.get("depth_le_max") or 0) >= need

    variants = [
        score_rule("frozen_G4",            lambda o: o["G"] >= 4),
        # Marine-layer stations are bimodal (burn-off vs. cap); a Gaussian cannot
        # price them and prob.py already zeroes their size. As of 2026-08-19 every
        # loss in the ledger is SFO. Scored, not enforced -- SFO is also half the
        # flag supply, so exclusion trades accuracy for sample rate.
        score_rule("exclude_marine",       lambda o: o["G"] >= 4 and o["city"] not in MARINE_CITIES),
        score_rule("floor96_ex_marine",    lambda o: 96 <= o["price"] <= 98 and o["city"] not in MARINE_CITIES),
        score_rule("conv_window_96_98",    lambda o: 96 <= o["price"] <= 98 and in_conv_window(o)),
        score_rule("floor96_depth25",      lambda o: 96 <= o["price"] <= 98 and has_depth(o)),
        score_rule("corrected_G4",         lambda o: gcorr(o) >= 4),
        score_rule("corrected_G4_floor90", lambda o: gcorr(o) >= 4 and o["price"] >= 90),
        score_rule("floor96_only",         lambda o: 96 <= o["price"] <= 98),
    ]

    out = dict(generated=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z"),
               n_rung_obs=len(obs), n_bottom_obs=len(bottom), n_units=len(units),
               days=sorted({o["day"] for o in obs}), bands=roll,
               station_guide_bias=bias,
               adaptive={c: dict(zip(("bias","sigma","n_eff","mode"),
                                     adaptive.bias_sigma(c)))
                         for c in {o["city"] for o in obs}},
               diurnal=adaptive.diurnal_climb({k: v["tz"] for k, v in CITIES.items()}),
               convergence=convergence.build(),
               boundary_cases=convergence.boundary_report(),
               variants=variants, brier=_brier())
    json.dump(out, open("docs/shadow_summary.json", "w"), indent=1)
    try:
        spend.write()
    except Exception as e:
        print("spend: skipped -", str(e)[:100])

    print(f"rung-obs {len(obs)} -> {len(units)} independent units over {len(out['days'])} days")
    print(f"{'band':>6} {'n':>3} {'w':>3} {'hit':>6} {'need':>6} {'LCB':>6} {'pnl':>7} {'proven':>7}")
    for r in roll:
        if not r["n"]: continue
        print(f"{r['band']:>6} {r['n']:>3} {r['wins']:>3} {r['hit']:>6.0%} "
              f"{r['breakeven']:>6.1%} {r['lcb']:>6.0%} {r['mean_pnl_c']:>7.1f} {str(r['proven']):>7}")
    print("\nstation guide bias (guide - CLI):", dict(sorted(bias.items(), key=lambda kv: -abs(kv[1]))))
    print(f"\n{'rule':>22} {'n':>3} {'w':>3} {'hit':>6} {'LCB':>5} {'meanP&L':>8}")
    for v in variants:
        h = f"{v['hit']:.0%}" if v['hit'] is not None else "--"
        m = v['mean_pnl_c'] if v['mean_pnl_c'] is not None else "--"
        print(f"{v['rule']:>22} {v['n']:>3} {v['wins']:>3} {h:>6} {v['lcb']:>5.0%} {m:>8}")
    if not any(r.get("proven") for r in roll):
        print("\nNo band's 95% lower bound clears its fee breakeven. Nothing proven.")



def _brier():
    """Score the forecasters against settlement. A verdict cannot be calibrated;
    a probability can. Both the model's p and the advisor's p_exceed are graded
    on every settled flag, so 'does the LLM add signal over the model' becomes a
    measured question rather than an opinion."""
    try:
        led = json.load(open("docs/ledger.json"))
    except Exception:
        return None
    rows = []
    for day in led.get("days", []):
        for f in day.get("flags", []):
            s, d = f.get("settle"), (f.get("detail") or {})
            cap = d.get("ceiling")
            if s is None or cap is None:
                continue
            y = 1.0 if s > cap else 0.0
            adv = f.get("advisor") or {}
            rows.append(dict(date=day["date"], city=f.get("city"), outcome=y,
                             p_model=(d.get("model") or {}).get("p_exceed_cap"),
                             p_advisor=adv.get("p_exceed")))
    def score(key):
        v = [(r[key], r["outcome"]) for r in rows if isinstance(r.get(key), (int, float))]
        if not v:
            return dict(n=0, brier=None)
        return dict(n=len(v), brier=round(sum((p - y) ** 2 for p, y in v) / len(v), 4))
    return dict(n_settled=len(rows), model=score("p_model"),
                advisor=score("p_advisor"), rows=rows[-20:],
                note="Brier: lower is better. 0.25 = always saying 50%. "
                     "Needs ~30+ settled flags before the comparison means anything.")


if __name__ == "__main__":
    main()
