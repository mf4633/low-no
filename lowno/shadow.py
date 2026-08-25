"""Shadow grading: settle EVERY scanned rung, not just the ones the gate flagged.

The live ledger produces ~1 graded observation per week. The scan log holds ~110
rung-observations per day that were rejected and then forgotten. Settling those
against the same CLI turns the rejections into the dataset -- which is the only
way to learn whether the gate's thresholds are doing work or just being obeyed.

Nothing here places or recommends orders. It scores counterfactuals on logged
prices, and a counterfactual fill at the logged ask is optimistic by construction
(no queue, no slippage, no size). Treat every number below as an upper bound.
"""
import json, glob, os, math, datetime as dt
from . import sources
from .config import CITIES

FEE_RATE = 0.07  # Kalshi: ceil(0.07 * C * P * (1-P)) cents per contract


def fee_cents(price_cents):
    p = price_cents / 100.0
    return math.ceil(FEE_RATE * 100 * p * (1 - p))


def pnl_cents(price_cents, won):
    """Buy NO at price_cents. Win -> collect 100, pay fee. Lose -> lose stake."""
    if won:
        return (100 - price_cents) - fee_cents(price_cents)
    return -price_cents


def load_day(day):
    """Yield one pseudo-record per rung. LADDER rows (full ladder, post Aug-10)
    expand to one record per rung; on cycles where a LADDER row exists, the
    gate's bottom-rung row is skipped to avoid double counting."""
    gate_rows, ladder = [], []
    for line in open(f"logs/{day}.jsonl"):
        r = json.loads(line)
        if r.get("verdict") == "LADDER":
            ladder.append(r)
        else:
            gate_rows.append(r)
    ladder_cycles = {(r["city"], r["at"][:15]) for r in ladder}
    rows = []
    for r in gate_rows:
        d = r.get("detail") or {}
        if not isinstance(d, dict) or d.get("no_ask") is None:
            continue
        if d.get("quote_src") in (None, "absent"):
            continue
        if (r["city"], r["at"][:15]) in ladder_cycles:
            continue
        rows.append(r)
    for r in ladder:
        d = r["detail"]
        for rung in d.get("rungs", []):
            if rung.get("na") is None or rung.get("src") in (None, "absent"):
                continue
            fl, cap = rung.get("fl"), rung.get("cap")
            # Three instruments per ladder (2026-08-10 audit finding):
            #   bottom  T-cap,  fl None : YES iff T <= cap          NO wins: T > cap
            #   range   B-x.5, fl & cap: YES iff fl <= T <= cap     NO wins: T outside
            #   top     T-fl,  cap None: YES iff T >= fl            NO wins: T < fl
            # Boundary settles count for YES (conservative for the NO buyer).
            kind = "bottom" if fl is None else ("top" if cap is None else "range")
            rows.append(dict(city=r["city"], station=r["station"], at=r["at"],
                verdict="LADDER",
                detail=dict(ticker=rung["t"], kind=kind, ceiling=cap, floor=fl,
                    no_ask=rung["na"] / 100.0, yes_bid=rung.get("yb"),
                    yes_ask=rung.get("ya"),
                    depth=rung.get("depth"),
                    quote_src=rung["src"], guide=d.get("guide"),
                    pop=d.get("pop"), run_max=d.get("run_max"))))
    return rows


CACHE = "docs/settlements.json"

def settle_map(days):
    """(day, city) -> CLI max, persisted to disk.

    Without a cache this refetches every city for every historical day on every
    nightly run -- O(days x cities) against api.weather.gov and growing forever.
    Settled values are immutable once the CLI is final, so only misses are
    fetched. Nulls are NOT cached: an unsettled day retries tomorrow.
    """
    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE))
        except Exception:
            cache = {}
    fetched = 0
    for day in days:
        for city, cfg in CITIES.items():
            k = f"{day}|{city}"
            if cache.get(k) is not None:
                continue
            try:
                m, _ = sources.cli_max(cfg["station"], None, date=day)
            except Exception:
                m = None
            if m is not None:
                cache[k] = m
                fetched += 1
    os.makedirs("docs", exist_ok=True)
    json.dump(cache, open(CACHE, "w"), indent=0, sort_keys=True)
    print(f"settlements: {len(cache)} cached, {fetched} newly fetched")
    return {(d, c): v for k, v in cache.items() for d, c in [k.split("|")]}


def build(days=None):
    days = days or sorted(os.path.basename(p)[:-6] for p in glob.glob("logs/2*.jsonl"))
    settles = settle_map(days)
    obs = []
    for day in days:
        for r in load_day(day):
            d, city = r["detail"], r["city"]
            s = settles.get((day, city))
            if s is None:
                continue
            kind = d.get("kind", "bottom")      # gate rows are bottom rungs
            fl, cap = d.get("floor"), d.get("ceiling")
            if kind == "bottom":
                if cap is None: continue
                won = s > cap
            elif kind == "top":
                if fl is None: continue
                won = s < fl
            else:                               # range: NO wins strictly outside
                if fl is None or cap is None: continue
                won = (s < fl) or (s > cap)
            price = int(round(d["no_ask"] * 100))
            guide, yb = d.get("guide"), d.get("yes_bid")
            ya = d.get("yes_ask")
            # YES side of the same rung. When no real yes_ask was logged, the
            # derived price 100 - no_ask IGNORES THE SPREAD and therefore FAVOURS
            # the YES buyer (a real ask sits at or above it). Any band that
            # survives only on the derived price is an artifact, not an edge --
            # yes_price_src marks which population each observation belongs to.
            yes_won = not won
            yes_price = ya if ya is not None else (100 - price)
            yes_price_src = "real_ask" if ya is not None else "derived_ignores_spread"
            yes_spread = (ya - (100 - price)) if ya is not None else None
            obs.append(dict(
                day=day, city=city, at=r["at"], verdict=r["verdict"], kind=kind,
                ceiling=d["ceiling"], price=price, yes_bid=yb, yes_ask=ya,
                guide=guide, pop=d.get("pop"), run_max=d.get("run_max"),
                G=(guide - cap) if (guide is not None and cap is not None) else None,
                settle=s, won=won, pnl=pnl_cents(price, won),
                yes_won=yes_won, yes_price=yes_price, yes_price_src=yes_price_src,
                yes_spread=yes_spread, yes_pnl=pnl_cents(yes_price, yes_won),
                # market-implied P(NO wins) = 1 - P(YES); yes_bid is in cents
                mkt_no=(100 - yb) if yb is not None else None,
                depth=d.get("depth"),
                guide_err=(guide - s) if guide is not None else None,
            ))
    return obs


def grid(obs, g_thresholds=(2, 3, 4, 5, 6), floors=(0, 50, 80, 90, 95)):
    """Score parameter variants on the same observations. One entry per
    city-day (first qualifying cycle), so variants are compared on position
    count, not on how many times a scanner happened to look."""
    out = []
    for g in g_thresholds:
        for fl in floors:
            taken, seen = [], set()
            for o in sorted(obs, key=lambda x: x["at"]):
                if o["G"] is None or o["G"] < g or o["price"] < fl or o["price"] > 98:
                    continue
                k = (o["day"], o["city"])
                if k in seen:
                    continue
                seen.add(k)
                taken.append(o)
            n = len(taken)
            wins = sum(1 for t in taken if t["won"])
            pnl = sum(t["pnl"] for t in taken)
            out.append(dict(G=g, floor=fl, n=n, wins=wins,
                            hit=(wins / n if n else None),
                            pnl=pnl, per=(pnl / n if n else None)))
    return out
