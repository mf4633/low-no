"""THE GATE. Pure logic, no I/O -- testable, and deliberately incapable of
scanning for lottery tickets: there is no code path in this repo that flags a
cheap YES. That absence is a feature requested by the operator on Aug 6, 2026."""
from .config import GATE

def c_to_f(c):
    return None if c is None else c * 9 / 5 + 32

def running_max_f(obs_today, return_detail=False):
    """Max temperature so far today, across BOTH observation streams.

    2026-08-22: api.weather.gov interleaves 5-minute automated obs (converted
    from whole degrees C -- odd Fahrenheit values only) with the :53 METARs
    (reported to 1F, and the basis for CLI settlement). Taking whichever is
    most recent, or only the 5-minute stream, understates the day by up to 1F.
    KMSY read 94F on the METAR while every neighbouring 5-minute ob read 93F.

    That bias lands directly on boundary rungs and contaminates the empirical
    remaining-climb distributions. Take the max across both, and report which
    stream produced it so the bias is measurable.
    """
    best, best_src, n_metar = None, None, 0
    for o in obs_today:
        t = o.get("tC")
        if t is None:
            continue
        f = c_to_f(t)
        src = "metar" if o.get("raw") else "fivemin"
        if src == "metar":
            n_metar += 1
        if best is None or f > best:
            best, best_src = f, src
    if return_detail:
        return dict(run_max=best, source=best_src, n_metar=n_metar,
                    n_obs=len(obs_today))
    return best

def bottom_rung(rungs):
    """The rung with no floor (e.g. '<=75'). Its cap is the ceiling to beat."""
    floorless = [r for r in rungs if r.get("floor") in (None, "")]
    if not floorless:
        return None
    return min(floorless, key=lambda r: r.get("cap") or 999)

def evaluate(city, rungs, run_max, guide_high, pop, local_hm, wx_text=""):
    """Returns (verdict, detail). Verdicts:
       DEAD_SCAVENGE  running max already > ceiling; NO is settled arithmetic
       QUALIFIED      all gates pass; forecast-class entry in window
       PASS           with the failed gate named (the reason is the product)"""
    b = bottom_rung(rungs)
    if b is None or b.get("cap") is None:
        return "PASS", "no bottom rung / no ladder"
    ceil_f = b["cap"]
    raw = b.get("no_ask")
    d = dict(ticker=b["ticker"], ceiling=ceil_f, no_ask=None if raw is None else raw / 100.0,
             quote_src=b.get("quote_src"), yes_bid=b.get("yes_bid"),
             run_max=run_max, guide=guide_high, pop=pop)
    # An absent quote is NOT a 100c quote. Conflating them (the pre-Aug-7 bug)
    # made a parser failure look like a market with no offer -- an unfalsifiable
    # PASS that logged as if the gate were working.
    if raw is None:
        return "PASS", {**d, "why": "no NO offer on book -- quote absent, not priced"}
    price = raw / 100.0

    if run_max is not None and run_max > ceil_f:
        if price <= GATE["max_price"]:
            return "DEAD_SCAVENGE", d
        return "PASS", {**d, "why": "dead rung fully priced (no offer <= 98)"}

    if price > GATE["max_price"]:
        return "PASS", {**d, "why": f"price {price:.2f} > {GATE['max_price']}"}
    if guide_high is None:
        return "PASS", {**d, "why": "no verified guidance -- unverified = no trade"}
    g = guide_high - ceil_f
    if g < GATE["min_g_deg"]:
        return "PASS", {**d, "why": f"G={g:.1f} < {GATE['min_g_deg']} (boundary territory)"}
    if pop is not None and pop > GATE["max_pop_pct"]:
        return "PASS", {**d, "why": f"PoP {pop}% -- precip mechanism live"}
    if any(k in (wx_text or "").lower() for k in ("thunder", "rain", "drizzle")):
        return "PASS", {**d, "why": f"active wx on tape: {wx_text}"}
    hm = local_hm[0] * 60 + local_hm[1]
    lo = GATE["entry_local"][0] * 60 + GATE["entry_local"][1]
    hi = GATE["entry_close"][0] * 60 + GATE["entry_close"][1]
    if hm < lo:
        return "PASS", {**d, "why": "before entry window (screen only; 7-9am is the worst hour -- backtested)"}
    if hm > hi:
        return "PASS", {**d, "why": "after entry window; scavenge-only hours"}
    gross = (1 - price) * 100
    fee = -(-7 * price * (1 - price) // 1) / 100 * 100  # ceil to cent, in cents
    if gross - fee < GATE["min_net_cents"]:
        return "PASS", {**d, "why": f"net {gross - fee:.2f}c under floor"}
    out = {**d, "G": g, "net_cents": round(gross - fee, 2)}

    # ---- HARD SIZE CAP -------------------------------------------------------
    # Half-Kelly at a 97c near-certainty prescribes 40%+ of bankroll. That is
    # correct arithmetic on a WRONG p: at these prices a 2-point error in pWin
    # swings size by tens of percent, and Kelly with a mis-estimated p does not
    # underperform -- it ruins. CANDIDATE.md named a 5% cap in prose; prose does
    # not execute. It is a number here, computed and logged on every flag, so the
    # size that would have been taken is part of the record from day one.
    # The gate has no model probability -- deliberately; it is pure logic with no
    # I/O. Sizing off the market-implied p (1 - price) is degenerate: it returns
    # Kelly = 0 by construction, since the market's own p carries no edge. So the
    # gate records the CEILING and the inputs; the model-driven half-Kelly lives
    # in prob.evaluate_ladder(), and the cap below is applied to whichever
    # estimate is used. Either way no position may exceed max_position_frac.
    out["size"] = {"cap": GATE["max_position_frac"],
                   "max_position_frac": GATE["max_position_frac"],
                   "kelly_source": "prob.evaluate_ladder (model p); gate does not estimate p",
                   "note": ("PAPER ONLY. Cap is unconditional and binds on every flag while "
                            "no band's Wilson LCB clears its fee breakeven.")}
    # Known residual loss mode (Denver Aug 4): guidance intact but the tape is
    # stalled far below it. The gate does NOT hard-fail this -- the backtest
    # shows coastal winners (LAX Aug 3) share the signature -- but it must be
    # shown to the human in red, not hidden.
    if run_max is not None and (guide_high - run_max) >= 12:
        out["WARN"] = (f"pace deficit {guide_high - run_max:.0f}F at entry -- "
                       "Denver-Aug4 profile; verify slope/mechanism before executing")
    return "QUALIFIED", out
