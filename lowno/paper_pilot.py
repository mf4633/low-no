"""PAPER pilot: what happens to $100 run through the YES Pilot v1 rules.

PAPER ONLY. No orders, no order code, ever -- this module consumes the same
settled shadow observations as everything else and simulates a bankroll.

What it tests: the HYPOTHESIS that the post-hoc 1-10c YES hit rate (~6.8%,
optimistic, unproven -- see CANDIDATE.md) is real. Sizing uses that fixed
hypothesis rate, NOT the accruing live estimate, so the simulation is a clean
bet on one stated number: if ~6.8% is real the bankroll grinds up ~2% per
unit; if the true rate is at or below breakeven (~2.6%), the curve bleeds to
the $40 quit line and that IS the result. Both outcomes are the experiment.

Design constraints, deliberate:
* Deterministic replay from logs every night -- no mutable state file. A
  bankroll number that cannot be recomputed from raw logs is a bug
  (weatherbot phantom-ledger lesson: grade from the log, never from a
  running balance).
* The station bias gate is evaluated POINT-IN-TIME: a unit on day D uses
  only settlements from days < D. The PREREG_yes10_hotbias3 variant uses
  scoring-time bias (a known hedge); a daily-followed bankroll cannot,
  because tonight's bias refit must never rewrite yesterday's trajectory.
* Fills are assumed full at the logged real yes_ask -- no queue, no
  slippage. Optimistic by construction; the FILL REALITY quit line in
  CANDIDATE.md exists to test exactly this if the pilot ever goes live.
"""
import math

CONFIG = dict(
    start_day="2026-08-26",       # first day of cap-corrected scans
    bankroll0=100.0,
    p_hyp=0.068,                  # hypothesis under test: post-hoc 1-10c hit rate
    kelly_mult=0.5,               # half-Kelly
    cap_frac=0.05,                # hard cap per unit, same seatbelt as the gate
    max_price_c=10,               # YES <= 10c
    bias_gate_f=3.0,              # station guide bias must exceed +3F...
    bias_min_days=3,              # ...measured over at least 3 prior settled days
    quit_up=5000.0,
    quit_down=40.0,
)


def _fee(price_c):
    return math.ceil(0.07 * 100 * (price_c / 100) * (1 - price_c / 100))


def _bias_asof(obs_sorted, day):
    """Per-city mean(guide - CLI) using ONLY city-days settled before `day`."""
    acc, seen = {}, set()
    for o in obs_sorted:
        if o["day"] >= day:
            break
        cd = (o["day"], o["city"])
        if cd in seen or o.get("guide_err") is None:
            continue
        seen.add(cd)
        acc.setdefault(o["city"], []).append(o["guide_err"])
    return {c: (sum(v) / len(v), len(v)) for c, v in acc.items()}


def run(obs):
    """Replay the paper pilot over settled shadow observations. Returns the
    full trajectory; caller persists/prints. Never raises on empty data."""
    cfg = CONFIG
    obs_sorted = sorted(obs, key=lambda o: (o["day"], o["at"]))
    # one unit per city-day, first qualifying cycle, same dedup as the variant
    units, seen = [], set()
    bias_cache = {}
    for o in obs_sorted:
        if o.get("kind", "bottom") != "bottom":
            continue
        if o["day"] < cfg["start_day"]:
            continue
        yp = o.get("yes_price")
        if yp is None or not (1 <= yp <= cfg["max_price_c"]):
            continue
        if o.get("yes_price_src") != "real_ask":
            continue
        cd = (o["day"], o["city"])
        if cd in seen:
            continue
        if o["day"] not in bias_cache:
            bias_cache[o["day"]] = _bias_asof(obs_sorted, o["day"])
        b, nd = bias_cache[o["day"]].get(o["city"], (0.0, 0))
        if nd < cfg["bias_min_days"] or b <= cfg["bias_gate_f"]:
            continue
        seen.add(cd)
        units.append(o)

    bankroll, rows, status = cfg["bankroll0"], [], "ACTIVE"
    for o in units:
        P = o["yes_price"]
        fee = _fee(P)
        b_odds = (100 - P - fee) / P
        f_star = cfg["p_hyp"] - (1 - cfg["p_hyp"]) / b_odds
        if f_star <= 0:
            # Kelly refuses the price: at p_hyp=6.8% anything >= ~6c is a
            # negative-edge bet even under the optimistic hypothesis.
            rows.append(dict(day=o["day"], city=o["city"], price=P,
                             action="skip_kelly", bankroll=round(bankroll, 2)))
            continue
        f = min(cfg["kelly_mult"] * f_star, cfg["cap_frac"])
        contracts = int(bankroll * f * 100 // P)
        if contracts < 1:
            rows.append(dict(day=o["day"], city=o["city"], price=P,
                             action="skip_size", bankroll=round(bankroll, 2)))
            continue
        stake = contracts * P / 100.0
        won = bool(o["yes_won"])
        pnl = contracts * (100 - P - fee) / 100.0 if won else -stake
        bankroll += pnl
        rows.append(dict(day=o["day"], city=o["city"], price=P,
                         action="trade", contracts=contracts,
                         stake=round(stake, 2), won=won, pnl=round(pnl, 2),
                         bankroll=round(bankroll, 2)))
        if bankroll <= cfg["quit_down"]:
            status = "QUIT_DOWN"
            break
        if bankroll >= cfg["quit_up"]:
            status = "QUIT_UP"
            break

    trades = [r for r in rows if r["action"] == "trade"]
    return dict(config=cfg, status=status,
                bankroll=round(bankroll, 2),
                n_trades=len(trades),
                wins=sum(1 for r in trades if r["won"]),
                n_skipped=len(rows) - len(trades),
                last_settled_day=(units[-1]["day"] if units else None),
                rows=rows)
