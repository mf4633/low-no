"""H19 fill-reality logger -- CONTEXT ONLY, never an input to the H19 verdict.

Why (2026-10-24): H19's paper P&L assumes a fill at the quoted ask with no size
limit. Before any real money the question is what 10 / 50 / 100 / 250 contracts
actually cost. Order books are ephemeral and cannot be rebuilt afterwards, so
they must be logged live.

Each run (every 30 min, 20:00Z-02:30Z via h19-depth.yml): for every city whose
local time is in [16:00, 19:00], read the open ladder for the city's local date
and the METAR running max since local-standard midnight (IEM). Any rung meeting
an H19 leg right now (same tests as h19_late.entries_for_rung, on the live
quote) gets its order book read. Logged per rung: top-of-book price, contracts
at the best price, and for each size the volume-weighted fill price and its
excess over the best price (cents). Rows -> logs/h19_depth/<UTC date>.jsonl.

Buying YES at P lifts resting NO bids at 100-P; buying NO at P lifts resting
YES bids at 100-P (Kalshi books publish bids only -- CLAUDE.md gotcha 2).
Paper only. Nothing here places or recommends orders.
"""
import json, os, sys, datetime as dt, zoneinfo, urllib.request
sys.path.insert(0, os.getcwd())
from lowno.config import CITIES
from lowno import sources
import h19_late as H

SIZES = (10, 50, 100, 250)
OUT = "logs/h19_depth"


def book(ticker):
    req = urllib.request.Request(f"{H.KALSHI}/markets/{ticker}/orderbook", headers={"User-Agent": "lowno/1.0"})
    j = json.loads(urllib.request.urlopen(req, timeout=20).read())
    ob = j.get("orderbook_fp") or j.get("orderbook") or {}
    yes_bids = sources._ob_levels(ob.get("yes_dollars") or ob.get("yes"))
    no_bids = sources._ob_levels(ob.get("no_dollars") or ob.get("no"))
    yes_asks = sorted((100 - p, s) for p, s in no_bids if 0 < p < 100)   # what a YES buyer lifts
    no_asks = sorted((100 - p, s) for p, s in yes_bids if 0 < p < 100)   # what a NO buyer lifts
    return yes_asks, no_asks


def fills(levels):
    out = {}
    best = levels[0][0] if levels else None
    for n in SIZES:
        left, cost = n, 0
        for p, s in levels:
            take = min(left, s); cost += take * p; left -= take
            if left == 0:
                break
        out[str(n)] = None if left else dict(vwap=round(cost / n, 2), excess_c=round(cost / n - best, 2))
    return best, out


def run():
    now = dt.datetime.now(dt.timezone.utc)
    rows, checked = [], []
    for city, c in sorted(CITIES.items()):
        tz = zoneinfo.ZoneInfo(c["tz"]); lt = now.astimezone(tz)
        if not (16 <= lt.hour < 19 or (lt.hour == 19 and lt.minute == 0)) and not os.environ.get("H19_DEPTH_ANYTIME"):
            continue
        day = lt.date()
        try:
            met = [m for m in H.fetch_metars(c["station"][1:], day) if m[0] <= now.timestamp()]
            ls = H.lst_start(day, c["tz"])
            obs = [v for t, v in met if t >= ls]
            rungs = sources.kalshi_ladder(c["series"], day.strftime("%y%b%d").upper(), probe_path=None)
        except Exception as e:
            rows.append(dict(at=now.isoformat()[:16] + "Z", city=city, error=str(e)[:100])); continue
        if not obs or not rungs:
            continue
        rm = max(obs); r = round(rm)
        checked.append(f"{city}@{lt.strftime('%H:%M')}:{len(rungs)}")
        for g in rungs:
            ya, yb, fl, cap = g.get("yes_ask"), g.get("yes_bid"), g.get("floor"), g.get("cap")
            if ya is None or yb is None or not (2 <= ya <= 98):
                continue
            mid = (ya + yb) / 2
            dead = cap is not None and r >= cap + 1
            inside = (fl is None or r >= fl) and (cap is None or r <= cap)
            leg = None
            if not dead and inside and 70 < mid <= 90:
                leg, side, quoted = "A", "YES", ya
            elif (not dead and not inside and fl is not None and r < fl and fl - r <= 2
                  and 10 < mid <= 30 and 2 <= 100 - yb <= 98):
                leg, side, quoted = "B", "NO", 100 - yb
            if not leg:
                continue
            try:
                yes_asks, no_asks = book(g["ticker"])
            except Exception as e:
                rows.append(dict(at=now.isoformat()[:16] + "Z", city=city, ticker=g["ticker"], error=str(e)[:100])); continue
            lv = yes_asks if side == "YES" else no_asks
            best, f = fills(lv)
            rows.append(dict(at=now.isoformat()[:16] + "Z", local=lt.strftime("%H:%M"), city=city,
                             ticker=g["ticker"], leg=leg, side=side, quoted=quoted, mid=mid, run_max=rm,
                             book_best=best, at_best=sum(s for p, s in lv if p == best) if best is not None else 0,
                             within_2c=sum(s for p, s in lv if best is not None and p <= best + 2),
                             fills=f, levels=lv[:10]))
    # heartbeat: proves the run looked, so an empty sample is not mistaken for a broken one
    rows.append(dict(at=now.isoformat()[:16] + "Z", heartbeat=True, cities_checked=checked,
                     hits=sum(1 for x in rows if "leg" in x)))
    if checked or len(rows) > 1:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, now.date().isoformat() + ".jsonl"), "a") as fh:
            for x in rows:
                fh.write(json.dumps(x) + "\n")
    print(f"h19_depth {now.isoformat()[:16]}Z: {len(rows)} rows")
    for x in rows[:20]:
        if x.get("heartbeat"):
            print("  checked", x["cities_checked"]); continue
        if "error" in x:
            print("  ERR", x); continue
        print(f"  {x['city']:4} {x['leg']} {x['side']:3} quoted {x['quoted']} best {x['book_best']} at_best {x['at_best']} "
              + " ".join(f"{k}:{(v or {}).get('excess_c')}" for k, v in x["fills"].items()))


def window_end(now=None):
    """Epoch of the next 02:05Z: today's if before 12Z, else tomorrow's."""
    now = now or dt.datetime.now(dt.timezone.utc)
    d = now.date() if now.hour < 12 else now.date() + dt.timedelta(days=1)
    return int(dt.datetime.combine(d, dt.time(2, 5), dt.timezone.utc).timestamp())


if __name__ == "__main__":
    run()
