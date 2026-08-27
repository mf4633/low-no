"""Autonomous paper pilots. PAPER ONLY -- no orders, ever.

Registered in CANDIDATE.md ("AUTONOMOUS PILOT ACTIVATION") on 2026-08-27,
before either underlying test had produced a number.

Activation policy, deliberate: a data bar being met means a test can RUN.
A pilot activates only when that test PASSES. Starting a trader on an
unvalidated premise is the H1 failure, and no amount of "it's only paper"
makes the resulting data less misleading. Both branches are automatic; neither
needs a human.

Each pilot keeps a SEPARATE bankroll. They test different hypotheses and must
never be pooled, including when both are live.
"""
import json, math, os

GATES = "docs/gates.json"
BANKROLL0 = 100.0
KELLY_MULT, CAP_FRAC = 0.5, 0.05
QUIT_DOWN, QUIT_UP = 40.0, 5000.0
FEE_RATE = 0.07


def _fee(p):
    return math.ceil(FEE_RATE * 100 * (p / 100) * (1 - p / 100))


def read_gates():
    try:
        return json.load(open(GATES))
    except Exception:
        return {}


def _size(bankroll, price, p_win):
    """Half-Kelly on the stated win probability, hard 5% cap, whole contracts."""
    fee = _fee(price)
    b = (100 - price - fee) / price
    f_star = p_win - (1 - p_win) / b
    if f_star <= 0:
        return 0, 0.0
    f = min(KELLY_MULT * f_star, CAP_FRAC)
    n = int(bankroll * f * 100 // price)
    return n, n * price / 100.0


def _replay(units, p_win_of):
    """Day-cohort replay: every unit on a day is sized off that day's OPENING
    bankroll and all its P&L applied at the close (a position opened at 14:06
    cannot be sized off a 14:05 position's settlement -- both are open, and
    neither settles until that night). Quit lines evaluate at day boundaries.
    """
    by_day = {}
    for u in units:
        by_day.setdefault(u["day"], []).append(u)
    bankroll, rows, status = BANKROLL0, [], "ACTIVE"
    for day in sorted(by_day):
        start, pnl_day = bankroll, 0.0
        for u in by_day[day]:
            price = u["price"]
            n, stake = _size(start, price, p_win_of(u))
            if n < 1:
                rows.append(dict(day=day, city=u["city"], price=price,
                                 action="skip_size"))
                continue
            won = bool(u["won"])
            pnl = n * (100 - price - _fee(price)) / 100.0 if won else -stake
            pnl_day += pnl
            rows.append(dict(day=day, city=u["city"], price=price, contracts=n,
                             stake=round(stake, 2), won=won, pnl=round(pnl, 2),
                             action="trade", bankroll=round(start + pnl_day, 2)))
        bankroll = start + pnl_day
        if bankroll <= QUIT_DOWN:
            status = "QUIT_DOWN"
            break
        if bankroll >= QUIT_UP:
            status = "QUIT_UP"
            break
    trades = [r for r in rows if r["action"] == "trade"]
    return dict(bankroll=round(bankroll, 2), status=status,
                n_trades=len(trades),
                wins=sum(1 for r in trades if r["won"]),
                rows=rows[-60:])


def pilot_a(obs, rated_samples=None):
    """PILOT-A -- trades model-vs-market using the shape-validated model.

    Universe: bottom rungs, PEAK WINDOW ONLY (the H4a effect inverts outside
    it), real ask 1-98c, shape cell earned. Enter NO when the shape model
    exceeds the market-implied probability by >= 0.10.
    """
    from . import empirical as E
    R = rated_samples if rated_samples is not None else E._raw_climbs_rated()
    units, seen = [], set()
    for o in sorted(obs, key=lambda x: x["at"]):
        if o.get("kind", "bottom") != "bottom":
            continue
        price = o.get("price")
        rate, hour = o.get("rate"), o.get("local_hour")
        if price is None or not (1 <= price <= 98) or rate is None or hour is None:
            continue
        if not (E.PEAK_WINDOW[0] <= hour <= E.PEAK_WINDOW[1]):
            continue
        pe = E.p_exceed(o["city"], hour, o.get("run_max"), o.get("ceiling"),
                        rate=rate, rated_samples=R)
        if not pe or not str(pe.get("source", "")).startswith("shape"):
            continue
        if pe["p"] - price / 100.0 < 0.10:
            continue
        k = (o["day"], o["city"])
        if k in seen:
            continue
        seen.add(k)
        units.append(dict(day=o["day"], city=o["city"], price=price,
                          won=bool(o.get("won")), p=pe["p"]))
    return _replay(units, lambda u: u["p"])


def pilot_b(obs, events=None):
    """PILOT-B -- trades the lag: enter NO when the day turns hotter than its
    own forecast curve (d(curve_dev) >= +1.0F), at that cycle's ask.
    Sizing uses the REALIZED event hit rate, never a re-tuned constant.
    """
    if not events:
        return _replay([], lambda u: 0.5)
    hits = [e for e in events if e.get("won") is not None]
    p_hat = (sum(1 for e in hits if e["won"]) / len(hits)) if hits else 0.0
    units, seen = [], set()
    for e in sorted(events, key=lambda x: (x["day"], x.get("hour") or 0)):
        if e.get("ddev", 0) < 1.0 or e.get("price") is None or e.get("won") is None:
            continue
        if not (1 <= e["price"] <= 98):
            continue
        k = (e["day"], e["city"])
        if k in seen:
            continue
        seen.add(k)
        units.append(dict(day=e["day"], city=e["city"], price=e["price"],
                          won=bool(e["won"])))
    return _replay(units, lambda u: p_hat)


def run_all(obs, gates, events=None):
    """Every registered pilot, with its activation state. Dormant pilots are
    reported too -- an autonomous start must never be a silent one."""
    out = []
    spec = [("PILOT-A", "H4a", "shape model vs market (peak window)",
             lambda: pilot_a(obs)),
            ("PILOT-B", "H4b", "curve-deviation lag",
             lambda: pilot_b(obs, events))]
    for pid, hyp, name, fn in spec:
        g = gates.get(hyp) or {}
        active = bool(g.get("passed"))
        rec = dict(id=pid, hypothesis=hyp, name=name, active=active,
                   gate=dict(ready=bool(g.get("ready")),
                             passed=bool(g.get("passed")),
                             reason=g.get("reason") or g.get("error")))
        if active:
            try:
                rec.update(fn())
            except Exception as e:
                rec.update(dict(status="ERROR", error=str(e)[:140]))
        else:
            rec.update(dict(status="DORMANT", bankroll=BANKROLL0,
                            n_trades=0, wins=0, rows=[]))
        out.append(rec)
    return out
