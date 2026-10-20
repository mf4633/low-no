"""paper5 -- daily PAPER trader: the 5 most "mispriced" buckets by a fixed rule.

Asked for 2026-10-20: automate picking the 5 most mispriced buckets, "buy" and
"sell" them at the statistically best entry/exit times, report daily, assume a
2c-per-contract transaction cost.

WHAT THIS IS. A paper measurement, outside the frozen gate, the shadow ledger
and every registered hypothesis. It places no orders and recommends none. Every
backtest on this project so far says the market prices these buckets about
right, so the expected result is a small loss per trade (roughly the 2c costs).
It exists to measure that, with the same rules every day.

THE RULE (fixed 2026-10-20, from that day's lessons; changing it = a new paper
account, not an edit):
  * Entry: one run at 16:10Z (12:10 ET, 11:10 CT, 10:10 MT, 9:10 PT).
    Why then: the by-hour study (2026-10-20, 9/1-10/19) found spreads cheapest
    in the morning and no hour with positive blind P&L; this is the latest hour
    at which every city is still before its peak.
  * Center = 0.5 * mean(model curve max) + 0.5 * NWS guide + carry, where
    dev = obs now - curve interpolated to the minute, carry = dev if dev > 0
    else dev / 3 (cold mornings revert +2.6F, warm overshoots mostly hold).
    ECMWF dropped at LAX/SAN/PHX (off-grid there). sd = 2.0F.
  * P(rung) = normal(center, sd) truncated below round(run_max) - 1, then
    shrunk halfway to the market's mid (I run ~2x overconfident).
  * Candidates: YES at the ask or NO at the ask (= 100 - YES bid), price
    6-94c (no YES at <=5c, ever: 0/8 hand picks). Edge = P - (ask + 2c).
    Rungs the market already holds at >=96 / <=4 are skipped (decided).
  * Pick: best edge per city, then the top 5 by edge with edge > 0. Fewer than
    5 if fewer qualify.
  * Costs: 2c per contract on every fill (entry and any sale). Settlement
    payout has no cost. Kalshi's own fee is NOT added (the 2c stands in).
  * Exits, all recorded on every position: HOLD to settlement, or SELL at the
    held side's bid at 18Z, 20Z, 22Z (minus 2c). The report compares them; the
    "best exit" is whichever has the higher mean P&L so far, reported with its
    day-clustered 95% interval. It is a measurement, not a switch.

Commands: enter | mark | settle | report   (all idempotent per day)
"""
import json, math, os, sys, datetime as dt, zoneinfo, urllib.request
from lowno import sources, gate
from lowno.config import CITIES

ET = zoneinfo.ZoneInfo("America/New_York")
LEDGER = "logs/paper5/ledger.json"      # not docs/*.json: push_retry regenerates those
REPORT = "docs/paper5.md"
COST = 2
SD = 2.0
N_PICKS = 5
PRICE_LO, PRICE_HI = 6, 94
MARKS = ("18", "20", "22")
NO_ECMWF = {"LAX", "SAN", "PHX"}
SETTLE = "docs/settlements.json"


def Phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "lowno/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def load():
    if os.path.exists(LEDGER):
        return json.load(open(LEDGER))
    return {"rule": "paper5 v1 (2026-10-20)", "days": {}}


def save(L):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    json.dump(L, open(LEDGER, "w"), indent=1)


def today_et():
    return dt.datetime.now(ET).date()


def p_rung(fl, cap, mu, sd, lo):
    """P(settle in [fl, cap]) under N(mu, sd) truncated below lo (whole F)."""
    Z = 1 - Phi((lo - 0.5 - mu) / sd)
    if Z <= 1e-9:
        return None

    def le(x):
        if x < lo:
            return 0.0
        return (Phi((x + 0.5 - mu) / sd) - Phi((lo - 0.5 - mu) / sd)) / Z
    if cap is None:
        return 1 - le(fl - 1)
    return le(cap) - (le(fl - 1) if fl is not None else 0.0)


def city_inputs(k, today):
    import mispricing_read as MR
    c = CITIES[k]
    tz = zoneinfo.ZoneInfo(c["tz"])
    ln = dt.datetime.now(tz)
    j = _get(f"https://api.open-meteo.com/v1/forecast?latitude={c['lat']}&longitude={c['lon']}"
             f"&hourly=temperature_2m&temperature_unit=fahrenheit&timezone={c['tz']}"
             f"&start_date={today}&end_date={today}&models=gfs_seamless,ecmwf_ifs025")
    h = j["hourly"]
    H, f = ln.hour, ln.minute / 60
    now_c, mx = [], []
    for m, v in h.items():
        if not m.startswith("temperature"):
            continue
        if "ecmwf" in m and k in NO_ECMWF:
            continue
        vals = [x for x in v if x is not None]
        if not vals or H + 1 >= len(v) or v[H] is None or v[H + 1] is None:
            continue
        now_c.append(v[H] * (1 - f) + v[H + 1] * f)
        mx.append(max(vals))
    obs = MR._day_obs(k, today)
    tnow = round(obs[0]["tC"] * 1.8 + 32, 1) if obs and obs[0]["tC"] is not None else None
    rmax = gate.running_max_f(obs)
    guide, short, pop = sources.point_forecast_high(c["lat"], c["lon"])
    if not mx or tnow is None:
        return None
    cmax = sum(mx) / len(mx)
    dev = tnow - sum(now_c) / len(now_c)
    carry = dev if dev > 0 else dev / 3
    base = cmax if guide is None else 0.5 * cmax + 0.5 * guide
    return dict(center=round(base + carry, 2), dev=round(dev, 2), carry=round(carry, 2),
                curve_max=round(cmax, 1), guide=guide, pop=pop, temp_now=tnow,
                run_max=rmax, local=ln.strftime("%H:%M"))


def candidates(k, today):
    c = CITIES[k]
    inp = city_inputs(k, today)
    if inp is None:
        return None, []
    rungs = sources.kalshi_ladder(c["series"], today.strftime("%y%b%d").upper(),
                                  probe_path="logs/_paper5_probe.json")
    lo = round(inp["run_max"]) - 1 if inp["run_max"] is not None else -999
    out = []
    for r in rungs or []:
        ya, yb = r.get("yes_ask"), r.get("yes_bid")
        if ya is None:
            continue
        mid = (ya + yb) / 2 if yb is not None else ya / 2
        if mid >= 96 or mid <= 4:
            continue
        pm = p_rung(r["floor"], r["cap"], inp["center"], SD, lo)
        if pm is None:
            continue
        p = 0.5 * pm + 0.5 * mid / 100
        here = []
        if PRICE_LO <= ya <= PRICE_HI:
            here.append(dict(side="YES", price=ya, edge=round(100 * p - ya - COST, 1)))
        na = r.get("no_ask")
        if na is not None and PRICE_LO <= na <= PRICE_HI:
            here.append(dict(side="NO", price=na, edge=round(100 * (1 - p) - na - COST, 1)))
        for o in here:
            o.update(ticker=r["ticker"], floor=r["floor"], cap=r["cap"],
                     p_model=round(pm, 3), p_used=round(p, 3), mid=mid)
        out += here
    return inp, out


def enter():
    L = load()
    day = today_et().isoformat()
    if day in L["days"] and L["days"][day].get("picks") is not None:
        print("already entered", day)
        return
    best, inputs, errs = [], {}, {}
    for k in sorted(CITIES):
        try:
            inp, cands = candidates(k, today_et())
        except Exception as e:
            errs[k] = str(e)[:80]
            continue
        if inp:
            inputs[k] = inp
        if cands:
            b = max(cands, key=lambda x: x["edge"])
            if b["edge"] > 0:
                best.append(dict(b, city=k))
    best.sort(key=lambda x: -x["edge"])
    picks = best[:N_PICKS]
    now = dt.datetime.now(dt.timezone.utc).isoformat()[:16] + "Z"
    for p in picks:
        p.update(entered_at=now, cost_in=COST, marks={})
    L["days"][day] = dict(picks=picks, inputs=inputs, errors=errs, entered_at=now)
    save(L)
    print(f"{day}: {len(picks)} picks")
    for p in picks:
        print(f"  {p['city']:4} {p['side']:3} {label(p):>7} @{p['price']}c  P={p['p_used']:.2f}  edge {p['edge']:+.1f}c")


def label(p):
    fl, cap = p.get("floor"), p.get("cap")
    if fl is None:
        return f"<={cap}"
    if cap is None:
        return f">={fl}"
    return f"{fl}-{cap}"


def mark():
    L = load()
    day = today_et().isoformat()
    d = L["days"].get(day)
    if not d or not d.get("picks"):
        print("nothing open")
        return
    hh = dt.datetime.now(dt.timezone.utc).strftime("%H")
    slot = min(MARKS, key=lambda m: abs(int(m) - int(hh)))
    for p in d["picks"]:
        if slot in p["marks"]:
            continue
        try:
            rungs = sources.kalshi_ladder(CITIES[p["city"]]["series"],
                                          today_et().strftime("%y%b%d").upper(),
                                          probe_path="logs/_paper5_probe.json")
            r = next((x for x in rungs if x["ticker"] == p["ticker"]), None)
            bid = None if r is None else (r.get("yes_bid") if p["side"] == "YES" else r.get("no_bid"))
            p["marks"][slot] = 0 if bid is None else bid
        except Exception as e:
            p["marks"][slot + "_err"] = str(e)[:60]
    save(L)
    print(f"marked {slot}Z for {day}")


def _contains(p, T):
    fl, cap = p.get("floor"), p.get("cap")
    if fl is None:
        return T <= cap
    if cap is None:
        return T >= fl
    return fl <= T <= cap


def settle():
    L = load()
    S = json.load(open(SETTLE)) if os.path.exists(SETTLE) else {}
    n = 0
    for day, d in L["days"].items():
        for p in d.get("picks") or []:
            if "settle" in p:
                continue
            T = S.get(f"{day}|{p['city']}")
            if T is None:
                continue
            yes_won = _contains(p, T)
            won = yes_won if p["side"] == "YES" else not yes_won
            p.update(settle=T, won=won)
            p["pnl_hold"] = (100 if won else 0) - p["price"] - COST
            for m in MARKS:
                if m in p["marks"]:
                    p[f"pnl_sell{m}"] = p["marks"][m] - COST - p["price"] - COST
            n += 1
    save(L)
    print(f"settled {n} positions")


def _clustered(rows):
    n = len(rows)
    if n == 0:
        return None
    m = sum(v for _, v in rows) / n
    by = {}
    for d, v in rows:
        by.setdefault(d, []).append(v)
    D = len(by)
    if D < 2:
        return dict(n=n, days=D, mean=m, lo=None, hi=None)
    se = math.sqrt(D / (D - 1) * sum((sum(v) - len(v) * m) ** 2 for v in by.values())) / n
    return dict(n=n, days=D, mean=m, lo=m - 1.96 * se, hi=m + 1.96 * se)


def report():
    L = load()
    days = sorted(L["days"])
    lines = ["# paper5 daily report", "",
             "PAPER ONLY. No orders. Fixed rule in `paper5.py` (v1, 2026-10-20). "
             "Costs: 2c per contract on every fill. Expected result: about the cost, "
             "because every backtest so far found the market prices these buckets right.", ""]
    if days:
        t = days[-1]
        d = L["days"][t]
        lines += [f"## Picks for {t} (entered {d.get('entered_at', '?')})", "",
                  "| City | Side | Bucket | Entry | My P | Market mid | Edge | 18Z bid | 20Z bid | 22Z bid | Settle | Hold P&L |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for p in d.get("picks") or []:
            mk = [str(p["marks"].get(m, "")) for m in MARKS]
            lines.append(f"| {p['city']} | {p['side']} | {label(p)} | {p['price']}c | {p['p_used']:.2f} | "
                         f"{p['mid']:.0f}c | {p['edge']:+.1f}c | {' | '.join(mk)} | "
                         f"{p.get('settle', '')} | {p.get('pnl_hold', '')} |")
        if not d.get("picks"):
            lines.append("| (no bucket cleared the rule) |||||||||||| ")
        lines.append("")
    graded = [(day, p) for day in days for p in L["days"][day].get("picks") or [] if "won" in p]
    lines += ["## Running results (all graded days)", ""]
    if not graded:
        lines += ["No graded positions yet. Days grade after the official high posts (next night).", ""]
    else:
        wins = sum(p["won"] for _, p in graded)
        lines += [f"{len(graded)} positions over {len({d for d, _ in graded})} days, "
                  f"{wins} won ({100 * wins / len(graded):.0f}%), mean entry "
                  f"{sum(p['price'] for _, p in graded) / len(graded):.0f}c.", "",
                  "| Exit | n | Mean P&L per contract | 95% range (by day) | Total |",
                  "|---|---|---|---|---|"]
        best = None
        for key, lab in [("pnl_hold", "Hold to settlement")] + [(f"pnl_sell{m}", f"Sell at {m}Z bid") for m in MARKS]:
            rows = [(d, p[key]) for d, p in graded if key in p]
            s = _clustered(rows)
            if not s:
                continue
            rng = "n/a" if s["lo"] is None else f"{s['lo']:+.1f} to {s['hi']:+.1f}c"
            lines.append(f"| {lab} | {s['n']} | {s['mean']:+.1f}c | {rng} | {sum(v for _, v in rows):+d}c |")
            if best is None or s["mean"] > best[1]:
                best = (lab, s["mean"], s["lo"])
        lines.append("")
        if best:
            proven = best[2] is not None and best[2] > 0
            lines.append(f"Best exit so far: **{best[0]}** ({best[1]:+.1f}c per contract). " +
                         ("Its 95% lower bound is above zero." if proven else
                          "Its 95% range includes zero or below: **nothing proven.**"))
            lines.append("")
        by_side = {}
        for _, p in graded:
            by_side.setdefault(p["side"], []).append(p["pnl_hold"])
        lines.append("Hold P&L by side: " + ", ".join(
            f"{s} {sum(v) / len(v):+.1f}c (n={len(v)})" for s, v in sorted(by_side.items())))
        lines.append("")
        lines += ["## Recent graded positions", "",
                  "| Day | City | Side | Bucket | Entry | Settle | Won | Hold P&L |", "|---|---|---|---|---|---|---|---|"]
        for d, p in graded[-25:][::-1]:
            lines.append(f"| {d} | {p['city']} | {p['side']} | {label(p)} | {p['price']}c | {p['settle']} | "
                         f"{'yes' if p['won'] else 'no'} | {p['pnl_hold']:+d}c |")
        lines.append("")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("wrote", REPORT)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"enter": enter, "mark": mark, "settle": settle, "report": report}[cmd]()
