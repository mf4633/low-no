"""Hypothesis 19 -- late in the day the market overpays for one more degree.

WRITTEN 2026-10-24, FORWARD-ONLY. Only days >= 2026-10-25 count, so no day this
test judges existed when its rules were fixed.

WHERE IT COMES FROM. Michael asked (10/24) for entry and exit TIMES, not winner
picks. A timing study (session scratchpad timing_bt.py / timing_check.py) used
Kalshi 1-minute bid/ask history for all 7,176 rungs 9/1-10/22, IEM METARs, and
CLI settlements. Buy at ask, sell at bid, fee 7q(1-q) on every fill.
  * EXITS: in hindsight the best round trip was HOLD to settlement on 90% of
    bucket-days. Pooled over every entry, selling after 30/60/120/240 min lost
    5-6.5c per contract against -3.5c for holding: an early exit pays the
    spread and the fee twice. So this rule holds to settlement.
  * ENTRIES: 3,311 state cells (local hour x price band x METAR running max vs
    bucket x 60-min momentum, YES/NO, 5 exits) with >= 10 train days (9/1-10/5);
    31 passed a train LCB > 0, FEWER than the ~83 chance alone gives. Two
    survived the 10/6-10/22 test, one entry per bucket-day, hold:
      A  16-18 local, bucket holds the running max, mid 71-90c, buy YES:
         train +3.5c [-0.9, +7.6] n=254/35d   test +7.7c [+3.5, +11.6] n=111/17d
      B  16-18 local, bucket 1-2F above the running max, mid 11-30c, buy NO:
         train +3.9c [-0.2, +7.7] n=228/35d   test +8.6c [+4.2, +12.6] n=89/17d
    They are one mispricing seen from both sides: late in the day the price of
    "one or two more degrees" is too high. A third survivor (91-98c favourites
    at 10-13 local) failed its test and is NOT part of this rule.
  Selected from many cells and the train CIs touch 0, so this is a lead, not a
  finding. The in-sample numbers are context only; they can never pass H19.

THE RULE (fixed now).
  * Rungs: every rung that appears in that day's scan logs (logs/<day>.jsonl).
  * Quotes: Kalshi 1-min candlesticks, yes_ask / yes_bid close, for the 22 h
    from 10:00Z on the trading day. Quote at time t = the latest candle ending
    at or before t with both sides present, if it is <= 30 min old.
  * Running max rm(t): max METAR tmpf (IEM routine + special) from local
    STANDARD-time midnight up to t, both inclusive; r = Python round(rm).
  * Grid: t = 16:00, 16:15, ..., 19:00 local (13 looks). At each look with a
    quote and 2 <= ask <= 98, mid = (ask + bid)/2:
      A  70 < mid <= 90 and the rung contains r (not dead: cap is None or
         r <= cap) -> BUY YES at the ask.
      B  10 < mid <= 30, rung has a floor fl, r < fl, fl - r <= 2, and the rung
         is not already dead -> BUY NO at 100 - bid.
    The bought price must be 2-98c.
  * One unit per (rung, leg): the FIRST qualifying look only. A rung can give
    one A and one B unit at different looks; both count.
  * Hold to settlement (CLI high). P&L per contract in cents:
    (100 if the bought side wins else 0) - price - fee, fee = Kalshi
    ceil(0.07*100*q*(1-q)) per contract (the 1-contract worst case; the
    backtest used the unrounded 7q(1-q), so this is the stricter fee).
  * Fill assumption: at the quoted ask, no size limit. Stated, not tested.

THE TEST (fixed now).
  * Data bar: >= 60 graded units AND >= 20 distinct days (A and B pooled).
  * PASSES iff the day-clustered 95% lower bound of mean per-unit P&L > 0
    (same deterministic cluster-robust SE as H18).
  * Read ONCE at the first nightly that meets the bar, frozen to
    docs/frozen/h19_verdict.json. Later nightlies print context only.
  * Context, never a pass: A alone, B alone, the unrounded-fee number, hit rate
    vs mean price.

COLLECTION. Graded AFTER the day, from public history, so a late GitHub cron
cannot lose a day. `python h19_late.py collect` writes logs/h19/<day>.json once
per finished day (entries only; outcomes come from docs/settlements.json at
verdict time). A day is written only when every rung's candles AND the METARs
fetched; otherwise the next run retries. Files are never rewritten.
At the backtest rate (~13 units/day) the 20-day bar binds: verdict ~mid-Nov.

Paper only. Nothing here places or recommends orders.
"""
import json, glob, os, sys, math, bisect, time, urllib.request, urllib.error, datetime as dt, zoneinfo

START_DAY = "2026-10-25"
MIN_UNITS, MIN_DAYS = 60, 20
LOOK_FROM, LOOK_TO, STEP = 16, 19, 15            # local hours, inclusive end, minutes
STALE_S = 1800
SETTLE = "docs/settlements.json"
OUT_DIR = "logs/h19"
VERDICT_FILE = "docs/frozen/h19_verdict.json"   # frozen at first read, never rewritten
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"


def fee_ceil(p):
    q = p / 100.0
    return math.ceil(0.07 * 100 * q * (1 - q))


def fee_exact(p):
    q = p / 100.0
    return 7 * q * (1 - q)


def lst_start(day, tzname):
    """UTC epoch of local STANDARD-time midnight (the CLI climate day)."""
    tz = zoneinfo.ZoneInfo(tzname)
    noon = dt.datetime.combine(day, dt.time(12), tz)
    std = noon.utcoffset() - (noon.dst() or dt.timedelta(0))
    return (dt.datetime.combine(day, dt.time(0), dt.timezone.utc) - std).timestamp()


def quote_at(Q, T, t):
    i = bisect.bisect_right(T, t) - 1
    if i < 0 or t - Q[i][0] > STALE_S:
        return None
    return Q[i]


def entries_for_rung(rung, quotes, metars, tzname, day):
    """rung: dict(t, fl, cap). quotes: [[end_ts, ask, bid, vol], ...].
    metars: [(epoch, tmpf), ...] sorted. day: date. Returns 0-2 entry dicts."""
    Q = sorted(q for q in quotes if q[1] is not None and q[2] is not None)
    if not Q:
        return []
    T = [q[0] for q in Q]
    WT = [m[0] for m in metars]
    ls = lst_start(day, tzname)
    tz = zoneinfo.ZoneInfo(tzname)
    fl, cap = rung.get("fl"), rung.get("cap")
    t = dt.datetime.combine(day, dt.time(LOOK_FROM), tz).timestamp()
    t_end = dt.datetime.combine(day, dt.time(LOOK_TO), tz).timestamp()
    got = {}
    while t <= t_end and len(got) < 2:
        q = quote_at(Q, T, t)
        if q and 2 <= q[1] <= 98:
            ask, bid = q[1], q[2]
            mid = (ask + bid) / 2
            a, b = bisect.bisect_left(WT, ls), bisect.bisect_right(WT, t)
            rm = max((metars[i][1] for i in range(a, b)), default=None)
            if rm is not None:
                r = round(rm)
                dead = cap is not None and r >= cap + 1
                inside = (fl is None or r >= fl) and (cap is None or r <= cap)
                local = dt.datetime.fromtimestamp(t, tz).strftime("%H:%M")
                base = dict(ticker=rung["t"], fl=fl, cap=cap, local=local, ask=ask, bid=bid, run_max=rm)
                if "A" not in got and not dead and inside and 70 < mid <= 90 and 2 <= ask <= 98:
                    got["A"] = dict(base, leg="A", side="YES", price=ask)
                if ("B" not in got and not dead and not inside and fl is not None
                        and r < fl and fl - r <= 2 and 10 < mid <= 30 and 2 <= 100 - bid <= 98):
                    got["B"] = dict(base, leg="B", side="NO", price=100 - bid)
        t += STEP * 60
    return list(got.values())


def yes_won(fl, cap, hi):
    return (fl is None or hi >= fl) and (cap is None or hi <= cap)


def grade(e, hi, fee=fee_ceil):
    yw = yes_won(e["fl"], e["cap"], hi)
    won = yw if e["side"] == "YES" else not yw
    return won, (100 if won else 0) - e["price"] - fee(e["price"])


# ---------------------------------------------------------------- collection
def _http(u, tries=8):
    for i in range(tries):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "lowno/1.0"})
            return urllib.request.urlopen(req, timeout=60).read().decode()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            time.sleep(min(60, 3 * 2 ** i))
        except Exception:
            time.sleep(min(60, 3 * 2 ** i))
    raise RuntimeError("fetch failed: " + u[:120])


def day_rungs(day_s):
    from lowno.config import CITIES
    out = {}
    p = f"logs/{day_s}.jsonl"
    if not os.path.exists(p):
        return out
    for line in open(p):
        try:
            r = json.loads(line)
        except Exception:
            continue
        d = r.get("detail")
        if r.get("city") not in CITIES or not isinstance(d, dict) or not d.get("rungs") or d.get("world"):
            continue
        for g in d["rungs"]:
            if g.get("t"):
                out.setdefault(g["t"], dict(t=g["t"], fl=g.get("fl"), cap=g.get("cap"), city=r["city"]))
    return out


def fetch_candles(series, tk, day):
    a = int(dt.datetime.combine(day, dt.time(10), dt.timezone.utc).timestamp())
    txt = _http(f"{KALSHI}/series/{series}/markets/{tk}/candlesticks?start_ts={a}&end_ts={a + 22*3600}&period_interval=1")
    if txt is None:
        return []
    rows = []

    def px(o):
        v = (o or {}).get("close_dollars")
        return round(float(v) * 100) if v not in (None, "") else None
    for c in json.loads(txt).get("candlesticks", []):
        rows.append([c["end_period_ts"], px(c.get("yes_ask")), px(c.get("yes_bid"))])
    return rows


def fetch_metars(stn3, day):
    d0, d1 = day - dt.timedelta(days=1), day + dt.timedelta(days=2)
    txt = _http("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=" + stn3 +
                f"&data=tmpf&year1={d0.year}&month1={d0.month}&day1={d0.day}"
                f"&year2={d1.year}&month2={d1.month}&day2={d1.day}"
                "&tz=Etc/UTC&format=onlycomma&latlon=no&missing=M&report_type=3&report_type=4")
    out = []
    for line in (txt or "").splitlines():
        x = line.strip().split(",")
        if len(x) < 3 or x[2] in ("M", "tmpf"):
            continue
        out.append((dt.datetime.strptime(x[1], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).timestamp(), float(x[2])))
    return sorted(out)


def collect(today=None):
    from lowno.config import CITIES
    os.makedirs(OUT_DIR, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    day = dt.date.fromisoformat(START_DAY)
    last = (now - dt.timedelta(hours=3)).date() - dt.timedelta(days=1) if today is None else today
    wrote = []
    while day <= last:
        ds = day.isoformat(); path = os.path.join(OUT_DIR, ds + ".json")
        if not os.path.exists(path):
            rungs = day_rungs(ds)
            if rungs:
                ents, met = [], {}
                for city in sorted({r["city"] for r in rungs.values()}):
                    met[city] = fetch_metars(CITIES[city]["station"][1:], day)
                for tk, r in sorted(rungs.items()):
                    c = CITIES[r["city"]]
                    q = fetch_candles(c["series"], tk, day)
                    for e in entries_for_rung(r, q, met[r["city"]], c["tz"], day):
                        ents.append(dict(e, day=ds, city=r["city"]))
                    time.sleep(0.3)
                json.dump(dict(day=ds, rungs=len(rungs), written=now.isoformat()[:16] + "Z",
                               entries=ents), open(path, "w"), indent=1)
                wrote.append((ds, len(ents)))
        day += dt.timedelta(days=1)
    for ds, n in wrote:
        print(f"H19 {ds}: {n} entries")
    if not wrote:
        print("H19: nothing new to collect")
    return wrote


# ---------------------------------------------------------------- verdict
def units(out_dir=OUT_DIR, settle_path=SETTLE, start=START_DAY):
    settle = {}
    if os.path.exists(settle_path):
        try:
            settle = json.load(open(settle_path))
        except Exception:
            settle = {}
    out = []
    for p in sorted(glob.glob(os.path.join(out_dir, "2*.json"))):
        try:
            j = json.load(open(p))
        except Exception:
            continue
        if j.get("day", "") < start:
            continue
        for e in j.get("entries", []):
            u = dict(e)
            hi = settle.get(f"{e['day']}|{e['city']}")
            if hi is not None:
                u["settle"] = hi
                u["won"], u["pnl"] = grade(e, hi)
                u["pnl_exact_fee"] = grade(e, hi, fee_exact)[1]
            out.append(u)
    return out


def _clustered(rows):
    n = len(rows)
    if n == 0:
        return dict(n=0)
    m = sum(v for _, v in rows) / n
    by = {}
    for d, v in rows:
        by.setdefault(d, []).append(v)
    D = len(by)
    if D < 2:
        return dict(n=n, days=D, mean_pnl_c=round(m, 2), lcb_c=None, ucb_c=None)
    ss = sum((sum(vs) - len(vs) * m) ** 2 for vs in by.values())
    se = math.sqrt(D / (D - 1) * ss) / n
    return dict(n=n, days=D, mean_pnl_c=round(m, 2), lcb_c=round(m - 1.96 * se, 2), ucb_c=round(m + 1.96 * se, 2))


def verdict(out_dir=OUT_DIR, settle_path=SETTLE, verdict_file=VERDICT_FILE, start=START_DAY):
    try:
        U = units(out_dir, settle_path, start)
    except Exception as e:
        return dict(id="H19", ready=False, passed=False, error=str(e)[:120])
    graded = [u for u in U if "won" in u]
    days = {u["day"] for u in graded}
    base = dict(id="H19", units=len(graded), need_units=MIN_UNITS, days=len(days),
                need_days=MIN_DAYS, pending=len(U) - len(graded))
    if len(graded) < MIN_UNITS or len(days) < MIN_DAYS:
        return dict(base, ready=False, passed=False, reason="data bar not met")
    frozen = None
    if verdict_file and os.path.exists(verdict_file):
        try:
            frozen = json.load(open(verdict_file))
        except Exception:
            frozen = None
    s = _clustered([(u["day"], u["pnl"]) for u in graded])
    ctx = dict(current=s,
               leg_A=_clustered([(u["day"], u["pnl"]) for u in graded if u["leg"] == "A"]),
               leg_B=_clustered([(u["day"], u["pnl"]) for u in graded if u["leg"] == "B"]),
               exact_fee=_clustered([(u["day"], u["pnl_exact_fee"]) for u in graded]),
               hit=round(sum(u["won"] for u in graded) / len(graded), 3),
               mean_price=round(sum(u["price"] for u in graded) / len(graded), 1))
    if frozen is None:
        frozen = dict(read_at_units=len(graded), read_at_days=len(days), read_on=dt.date.today().isoformat(),
                      passed=bool(s["lcb_c"] is not None and s["lcb_c"] > 0), at_read=s)
        if verdict_file:
            try:
                os.makedirs(os.path.dirname(verdict_file) or ".", exist_ok=True)
                json.dump(frozen, open(verdict_file, "w"), indent=1)
            except Exception:
                pass
    return dict(base, ready=True, passed=frozen["passed"], frozen=frozen, context=ctx)


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    if len(sys.argv) > 1 and sys.argv[1] == "collect":
        collect()
    else:
        U = units()
        print(f"H19 units (days >= {START_DAY}): {len(U)}, graded {sum(1 for u in U if 'won' in u)}")
        print(json.dumps(verdict(verdict_file=None), indent=1))
