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
    rows = []
    for line in open(f"logs/{day}.jsonl"):
        r = json.loads(line)
        d = r.get("detail") or {}
        if not isinstance(d, dict) or d.get("no_ask") is None:
            continue
        if d.get("quote_src") in (None, "absent"):
            continue  # pre-fix corrupt records and empty books
        rows.append(r)
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
            if s is None or d.get("ceiling") is None:
                continue
            price = int(round(d["no_ask"] * 100))
            won = s > d["ceiling"]              # NO pays iff high exceeds ceiling
            guide, yb = d.get("guide"), d.get("yes_bid")
            obs.append(dict(
                day=day, city=city, at=r["at"], verdict=r["verdict"],
                ceiling=d["ceiling"], price=price, yes_bid=yb,
                guide=guide, pop=d.get("pop"), run_max=d.get("run_max"),
                G=(guide - d["ceiling"]) if guide is not None else None,
                settle=s, won=won, pnl=pnl_cents(price, won),
                # market-implied P(NO wins) = 1 - P(YES); yes_bid is in cents
                mkt_no=(100 - yb) if yb is not None else None,
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
