"""Shadow grading: settle EVERY scanned rung, not just the ones the gate flagged.

The live ledger produces ~1 graded observation per week. The scan log holds ~110
rung-observations per day that were rejected and then forgotten. Settling those
against the same CLI turns the rejections into the dataset -- which is the only
way to learn whether the gate's thresholds are doing work or just being obeyed.

Nothing here places or recommends orders. It scores counterfactuals on logged
prices, and a counterfactual fill at the logged ask is optimistic by construction
(no queue, no slippage, no size). Treat every number below as an upper bound.
"""
import json, glob, os, math, datetime as dt, zoneinfo
from . import sources
from .config import CITIES

# Top-rung floor_strike was parsed as an inclusive floor until 2026-08-31;
# from this date the logs carry the corrected (threshold + 1) value.
FLOOR_FIX_SINCE = "2026-09-01"

FEE_RATE = 0.07  # Kalshi: ceil(0.07 * C * P * (1-P)) cents per contract

# When the bottom-rung cap off-by-one fix (sources.py) deployed. Logs written
# before this carry the raw Kalshi threshold as the bottom cap (1F too high);
# used only as a fallback where ladder-based detection is impossible.
CAP_FIX_UTC = "2026-08-25T17:11"


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
        # Gate rows carry no ladder context, so pre/post cap-fix status falls
        # back to the deploy timestamp (see CAP_FIX_UTC below).
        d["cap_is_raw"] = r["at"] < CAP_FIX_UTC
        rows.append(r)
    for r in ladder:
        d = r["detail"]
        # Pre-fix bottom rungs are SELF-IDENTIFYING: their logged cap equals the
        # first range bucket's floor (the impossible overlap that proved the
        # off-by-one), while post-fix caps sit 1 below it. Detect per record --
        # 2026-08-25's log is MIXED (raw before the ~17:11Z deploy, corrected
        # after), so a date boundary would misgrade that day.
        range_floors = [g.get("fl") for g in d.get("rungs", [])
                        if g.get("fl") is not None and g.get("cap") is not None]
        min_rf = min(range_floors) if range_floors else None
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
            if kind == "bottom" and cap is not None and min_rf is not None:
                cap_is_raw = cap >= min_rf
            else:
                cap_is_raw = r["at"] < CAP_FIX_UTC
            rows.append(dict(city=r["city"], station=r["station"], at=r["at"],
                verdict="LADDER",
                detail=dict(ticker=rung["t"], kind=kind, ceiling=cap, floor=fl,
                    cap_is_raw=cap_is_raw,
                    no_ask=rung["na"] / 100.0, yes_bid=rung.get("yb"),
                    yes_ask=rung.get("ya"),
                    depth=rung.get("depth"),
                    quote_src=rung["src"], guide=d.get("guide"),
                    pop=d.get("pop"), run_max=d.get("run_max"))))
    return rows


CACHE = "docs/settlements.json"
VERIFIED = "docs/settlements_verified.json"   # keys confirmed AFTER the day closed
CLI_WINDOW_DAYS = 7   # measured 2026-08-27: api.weather.gov serves CLI for
                      # exactly 7 days back, then the product is GONE. Any
                      # settlement error not caught inside that window is
                      # permanent, because nothing can ever re-derive it.

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
    verified = set()
    if os.path.exists(VERIFIED):
        try:
            verified = set(json.load(open(VERIFIED)))
        except Exception:
            verified = set()

    fetched = repaired = 0
    # Never fetch the CURRENT ET trading date. A CLI product fetched intraday
    # reports the max SO FAR, not the final max, and non-null cache entries are
    # immutable -- a midday run on 2026-08-25 froze AUS=82/DEN=67/SAT=81 hours
    # before peak heat and graded three phantom YES wins. Today settles tomorrow.
    today_et = dt.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date().isoformat()
    horizon = (dt.date.fromisoformat(today_et)
               - dt.timedelta(days=CLI_WINDOW_DAYS)).isoformat()
    for day in days:
        if day >= today_et:
            continue
        for city, cfg in CITIES.items():
            k = f"{day}|{city}"
            have = cache.get(k) is not None
            # Re-fetch when we have nothing, OR when the value has never been
            # CONFIRMED after the day closed and is still inside the 7-day
            # window. That second case is what repairs the legacy poisoning
            # (2026-08-22 SAT was frozen at 84, an ~09:00 local max-so-far;
            # the true CLI is 103) and it also picks up NWS's own corrected
            # climate reports. Once confirmed, a key is never fetched again.
            if have and (k in verified or day < horizon):
                continue
            try:
                m, _ = sources.cli_max(cfg["station"], None, date=day)
            except Exception:
                m = None
            if m is None:
                continue
            if have and cache[k] != m:
                print(f"  settlement REPAIRED {k}: {cache[k]} -> {m}")
                repaired += 1
            elif not have:
                fetched += 1
            cache[k] = m
            verified.add(k)

    # QUARANTINE the provably impossible. A poisoned entry is a max-SO-FAR, so
    # it is always too LOW -- and our own observations are a valid lower bound
    # on the true max. A settlement below what we watched happen cannot be
    # right, whatever the reason. This is an arithmetic test, not a judgment
    # call, so it works even OUTSIDE the 7-day window where nothing can be
    # re-fetched. Dropping such a day costs one observation; keeping it
    # silently corrupts station bias, grading, and every variant downstream.
    # (1F tolerance absorbs station/rounding differences.)
    dropped = 0
    for day in days:
        try:
            lines = open(f"logs/{day}.jsonl")
        except OSError:
            continue
        seen_max = {}
        for line in lines:
            try:
                r = json.loads(line)
            except Exception:
                continue
            # Row filter must match what the GRADERS read, not a verdict
            # label. It used to require verdict == "LADDER", which the early
            # collector never wrote: 2026-08-06 through 08-09 have 360 rows
            # carrying run_max and ZERO ladder rows, so the one integrity check
            # that protects those days could not see them at all -- while
            # build(), shape_eval and the bias tables all consumed them. That
            # let SFO 2026-08-07 stand at CLI 68 against an observed 72.0.
            # Those days are also the oldest, hence outside the CLI window and
            # unrepairable, so the blind spot was worst exactly where it was
            # permanent. run_max is the station's running max and does not
            # depend on the verdict.
            d = r.get("detail") or {}
            if not isinstance(d, dict) or d.get("world"):
                continue
            rm, c = d.get("run_max"), r.get("city")
            if rm is None or not c:
                continue
            seen_max[c] = max(seen_max.get(c, -999), rm)
        for c, obs in seen_max.items():
            k = f"{day}|{c}"
            v = cache.get(k)
            if v is not None and v < round(obs) - 1:
                print(f"  settlement QUARANTINED {k}: cached {v} but we observed "
                      f"{round(obs)} -- impossible, dropping")
                cache.pop(k, None)
                verified.discard(k)
                dropped += 1

    os.makedirs("docs", exist_ok=True)
    json.dump(cache, open(CACHE, "w"), indent=0, sort_keys=True)
    json.dump(sorted(verified), open(VERIFIED, "w"), indent=0)
    stale = sum(1 for k in cache if k not in verified)
    print(f"settlements: {len(cache)} cached, {fetched} new, {repaired} repaired, "
          f"{dropped} quarantined, {stale} unconfirmable "
          f"(older than the {CLI_WINDOW_DAYS}-day CLI window)")
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
                # NO side stays graded on the LOGGED cap, even for pre-fix rows
                # where that cap is the raw threshold (1F too high). Deliberate:
                # correcting history would silently rewrite every NO band/variant
                # table mid-measurement. Consequence, named: for pre-fix bottom
                # rungs a settle exactly AT the logged cap is graded NO-loss when
                # it was in fact a NO-win, so pre-fix NO figures are pessimistic
                # at the boundary -- one more reason cap_fix_since populations
                # must not be pooled.
                won = s > cap
                # YES side IS cap-corrected: grade against the true inclusive
                # cap (logged - 1 for pre-fix rows). So for pre-fix boundary
                # settles yes_won is NOT simply `not won` -- both read False.
                yes_cap = cap - 1 if d.get("cap_is_raw") else cap
            elif kind == "top":
                if fl is None: continue
                # Rows logged before FLOOR_FIX_SINCE carry the RAW floor_strike,
                # which is a threshold: the contract is "greater than fl", so the
                # inclusive floor is fl + 1. Corrected here rather than left to
                # rot, because unlike the bottom-rung cap this end has never fed
                # a scored population -- there is no band or variant table to
                # rewrite, so there is nothing to protect by leaving it wrong.
                if day < FLOOR_FIX_SINCE:
                    fl = fl + 1
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
            yes_won = (s <= yes_cap) if kind == "bottom" else (not won)
            yes_price = ya if ya is not None else (100 - price)
            yes_price_src = "real_ask" if ya is not None else "derived_ignores_spread"
            yes_spread = (ya - (100 - price)) if ya is not None else None
            obs.append(dict(
                day=day, city=city, at=r["at"], verdict=r["verdict"], kind=kind,
                ceiling=d["ceiling"], cap_is_raw=d.get("cap_is_raw"),
                price=price, yes_bid=yb, yes_ask=ya,
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

    # Local hour and recent climb RATE on every observation. PILOT-A cannot see
    # its universe without them (H4a is a shape claim, and shape is invisible in
    # a running maximum), and they are cheap to derive here rather than being
    # recomputed from raw logs by every consumer.
    by_cd = {}
    for o in obs:
        try:
            u = dt.datetime.fromisoformat(o["at"]).replace(tzinfo=dt.timezone.utc)
            lt = u.astimezone(zoneinfo.ZoneInfo(CITIES[o["city"]]["tz"]))
            o["local_hour"] = lt.hour
            o["_hf"] = lt.hour + lt.minute / 60.0
        except Exception:
            o["local_hour"] = None
            o["_hf"] = None
        by_cd.setdefault((o["day"], o["city"]), []).append(o)
    for k, group in by_cd.items():
        g = [x for x in group if x["_hf"] is not None and x.get("run_max") is not None]
        g.sort(key=lambda x: x["_hf"])
        prev = None
        for o in g:
            if prev is not None:
                dh = o["_hf"] - prev["_hf"]
                if 0.5 <= dh <= 2.5:
                    o["rate"] = round((o["run_max"] - prev["run_max"]) / dh, 3)
            # advance only on a distinct cycle, so multiple rungs sharing one
            # scan do not produce a zero-gap rate
            if prev is None or o["_hf"] > prev["_hf"]:
                prev = o
    for o in obs:
        o.pop("_hf", None)
        o.setdefault("rate", None)
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
