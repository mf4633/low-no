"""THE GATE. Pure logic, no I/O -- testable, and deliberately incapable of
scanning for lottery tickets: there is no code path in this repo that flags a
cheap YES. That absence is a feature requested by the operator on Aug 6, 2026."""
from .config import GATE

def c_to_f(c):
    return None if c is None else c * 9 / 5 + 32

def running_max_f(obs_today):
    vals = []
    for o in obs_today:
        if o.get("tC") is not None: vals.append(c_to_f(o["tC"]))
        if o.get("max24C") is not None: vals.append(c_to_f(o["max24C"]))
    return max(vals) if vals else None

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
    ceil_f, price = b["cap"], (b.get("no_ask") or 100) / 100.0
    d = dict(ticker=b["ticker"], ceiling=ceil_f, no_ask=price,
             run_max=run_max, guide=guide_high, pop=pop)

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
    # Known residual loss mode (Denver Aug 4): guidance intact but the tape is
    # stalled far below it. The gate does NOT hard-fail this -- the backtest
    # shows coastal winners (LAX Aug 3) share the signature -- but it must be
    # shown to the human in red, not hidden.
    if run_max is not None and (guide_high - run_max) >= 12:
        out["WARN"] = (f"pace deficit {guide_high - run_max:.0f}F at entry -- "
                       "Denver-Aug4 profile; verify slope/mechanism before executing")
    return "QUALIFIED", out
