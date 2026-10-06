"""Hypothesis 16 -- is the bucket the morning curve-deviation points at UNDERPRICED?

WRITTEN 2026-10-06, FORWARD-ONLY. Only days >= 2026-10-07 count, so no day this
test judges existed when its rules were fixed. Nothing was backtested on the
pre-registration days, on purpose: H4a/H4b already used them, and the
anti-gaming rule forbids reviving a closed avenue by re-slicing the same days.

WHERE IT COMES FROM. Michael's goal, 2026-10-06: find where the market is wrong
EARLY, not concede that it is right once the highs are in. On 2026-10-05 DAL ran
+2.9F over its forecast curve at 10:16 local and settled 86, above the market's
modal bucket (84-85). Hand-picked reads on 10/5-10/6 went 0-for-5, which is why
this is a fixed rule scored on every qualifying city-day instead.

WHY THIS IS NOT H4a OR H4b.
  * H4a asked whether curve SHAPE improves the MODEL's remaining-climb Brier.
    It says nothing about the market's price.
  * H4b asked whether a CHANGE in curve_dev predicts the NEXT cycle's price
    CHANGE on the bottom rung (a lag). It read zero (-0.021).
  * H16 asks whether the market's price, at a FIXED morning hour, on the
    bucket that a full carry of the deviation points at, is too LOW against
    settlement. A market can reprice with the deviation (no lag, H4b) and still
    under-react in LEVEL: move part of the way and stop. H4b cannot see that;
    this can. Different quantity, different rung, different outcome variable
    (settlement, not the next price).

THE RULE (fixed now).
  * Unit: one per (day, city), day >= 2026-10-07.
  * Look: the FIRST logged LADDER cycle whose local time is in [10:00, 12:00).
    Only that cycle. If it does not qualify, the city-day is not a unit; no
    shopping across later cycles.
  * Deviation: temp_now minus the logged forecast curve INTERPOLATED to the
    scan minute (curve[H]*(1-f) + curve[H+1]*f). Not the logged `curve_dev`,
    which compares against the top-of-hour value and reads warm all morning.
  * Qualifies iff |dev| >= 2.0F.
  * Projection: proj = curve_max_f + dev (FULL carry). Bucket = the rung that
    contains round(proj): bottom T<=cap, range fl<=T<=cap, top T>=fl.
  * Entry: buy YES at that rung's logged ask `ya`, 1 <= ya <= 95. No ask, no
    unit.
  * Fees: Kalshi ceil(0.07*C*P*(1-P)) charged on EVERY fill, win or lose.
    That is harsher than shadow.pnl_cents (fee on wins only), deliberately.

THE TEST (fixed now).
  * Data bar: >= 60 units AND >= 20 distinct days (the day leg is H4b's
    correction: one synoptic event must not fill the bar).
  * PASSES iff the 95% lower bound of mean per-unit P&L (cents, after fees) is
    > 0. Read ONCE, at the first nightly that meets the bar; the verdict at
    that n is the verdict (the H4a lesson: a pass at n=69 that later flips is
    the early-peek problem). Later nightlies keep printing numbers, marked
    as post-verdict context.
  * Reported beside it, context only, never a pass: (a) units where the
    projected bucket is NOT the market's modal bucket (the "disagreement"
    slice); (b) a no-carry control, the bucket containing round(curve_max_f)
    at its own ask, same units: does carrying the deviation add anything?
  * Pilot: none. The programme stops 2026-12-31 and the 10/31 cutoff for new
    avenues is respected (registered 10/06). A pass is an information claim.

Paper only. Nothing here places or recommends orders.
"""
import json, glob, os, math, datetime as dt, zoneinfo
from lowno.config import CITIES

START_DAY = "2026-10-07"
MIN_UNITS, MIN_DAYS = 60, 20
DEV_MIN = 2.0
HOUR_LO, HOUR_HI = 10, 12          # local, [lo, hi)
ASK_LO, ASK_HI = 1, 95
SETTLE = "docs/settlements.json"
VERDICT_FILE = "docs/frozen/h16_verdict.json"   # frozen at first read, never rewritten.
# NOT under docs/*.json: push_retry.sh treats that pattern as regenerable on a
# rebase conflict, and a frozen verdict is the one file that must never be.


def fee_cents(p):
    q = p / 100.0
    return math.ceil(0.07 * 100 * q * (1 - q))


def yes_pnl(price, won):
    f = fee_cents(price)
    return (100 - price - f) if won else (-price - f)


def contains(rung, t):
    fl, cap = rung.get("fl"), rung.get("cap")
    if fl is None and cap is None:
        return False
    if fl is None:
        return t <= cap
    if cap is None:
        return t >= fl
    return fl <= t <= cap


def interp_dev(detail, local_t):
    am = detail.get("airmass") or {}
    crv = am.get("curve") or {}
    tnow = detail.get("temp_now")
    if tnow is None or not crv:
        return None
    H, f = local_t.hour, local_t.minute / 60.0
    a = crv.get(str(H), crv.get(H))
    b = crv.get(str(H + 1), crv.get(H + 1))
    if a is None or b is None:
        return None
    return round(tnow - (a * (1 - f) + b * f), 2)


def _ya_ok(r):
    ya = r.get("ya")
    return ya is not None and ASK_LO <= ya <= ASK_HI


def _modal(rungs):
    """The market's modal bucket: highest YES mid (ask when no bid)."""
    best, bp = None, -1
    for r in rungs:
        ya, yb = r.get("ya"), r.get("yb")
        if ya is None or ya >= 100:
            continue
        p = (ya + yb) / 2.0 if (yb is not None and yb > 0) else float(ya)
        if p > bp:
            best, bp = r, p
    return best


def units(log_glob="logs/2*.jsonl", settle_path=SETTLE, start=START_DAY):
    settle = {}
    if os.path.exists(settle_path):
        try:
            settle = json.load(open(settle_path))
        except Exception:
            settle = {}
    out = []
    for path in sorted(glob.glob(log_glob)):
        day = os.path.basename(path)[:-6]
        if day < start:
            continue
        first = {}
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("verdict") != "LADDER":
                continue
            city = r.get("city"); d = r.get("detail") or {}
            if city not in CITIES or d.get("world"):
                continue
            try:
                lt = (dt.datetime.fromisoformat(r["at"].replace("Z", ""))
                      .replace(tzinfo=dt.timezone.utc)
                      .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])))
            except Exception:
                continue
            if not (HOUR_LO <= lt.hour < HOUR_HI):
                continue
            if city not in first or r["at"] < first[city][0]["at"]:
                first[city] = (r, lt)
        for city, (r, lt) in sorted(first.items()):
            d = r["detail"]
            dev = interp_dev(d, lt)
            cmax = (d.get("airmass") or {}).get("curve_max_f")
            if dev is None or cmax is None or abs(dev) < DEV_MIN:
                continue
            rungs = d.get("rungs") or []
            proj = round(cmax + dev)
            pick = next((g for g in rungs if contains(g, proj)), None)
            if pick is None or not _ya_ok(pick):
                continue
            ctl = next((g for g in rungs if contains(g, round(cmax))), None)
            mode = _modal(rungs)
            T = settle.get(f"{day}|{city}")
            u = dict(day=day, city=city, at=r["at"], local=lt.strftime("%H:%M"),
                     dev=dev, curve_max=cmax, proj=proj, ticker=pick.get("t"),
                     price=pick["ya"], is_mode=bool(mode is not None
                                                    and mode.get("t") == pick.get("t")),
                     settle=T)
            if ctl is not None and _ya_ok(ctl):
                u["ctl_ticker"], u["ctl_price"] = ctl.get("t"), ctl["ya"]
            if T is not None:
                u["won"] = contains(pick, T)
                u["pnl"] = yes_pnl(pick["ya"], u["won"])
                if "ctl_price" in u:
                    u["ctl_pnl"] = yes_pnl(ctl["ya"], contains(ctl, T))
            out.append(u)
    return out


def _summ(xs):
    n = len(xs)
    if n == 0:
        return dict(n=0)
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n > 1 else float("inf")
    return dict(n=n, mean_pnl_c=round(m, 2), lcb_c=round(m - 1.96 * se, 2),
                ucb_c=round(m + 1.96 * se, 2))


def verdict(log_glob="logs/2*.jsonl", settle_path=SETTLE,
            verdict_file=VERDICT_FILE, start=START_DAY):
    try:
        U = units(log_glob, settle_path, start)
    except Exception as e:
        return dict(id="H16", ready=False, passed=False, error=str(e)[:120])
    graded = [u for u in U if "won" in u]
    days = {u["day"] for u in graded}
    base = dict(id="H16", units=len(graded), need_units=MIN_UNITS,
                days=len(days), need_days=MIN_DAYS,
                pending=len(U) - len(graded),
                # which population was read: without morning scans only the
                # western stations reach a 10-12 local look
                cities=dict(sorted(__import__("collections").Counter(
                    u["city"] for u in graded).items())))
    if len(graded) < MIN_UNITS or len(days) < MIN_DAYS:
        return dict(base, ready=False, passed=False, reason="data bar not met")
    # Read ONCE. The first nightly at the bar freezes the verdict to disk;
    # every later run reports that frozen verdict plus current context.
    frozen = None
    if verdict_file and os.path.exists(verdict_file):
        try:
            frozen = json.load(open(verdict_file))
        except Exception:
            frozen = None
    s = _summ([u["pnl"] for u in graded])
    hits = sum(1 for u in graded if u["won"])
    ctx = dict(current=s, hit=round(hits / len(graded), 3),
               mean_price=round(sum(u["price"] for u in graded) / len(graded), 1),
               not_mode=_summ([u["pnl"] for u in graded if not u["is_mode"]]),
               control_no_carry=_summ([u["ctl_pnl"] for u in graded if "ctl_pnl" in u]))
    if frozen is None:
        frozen = dict(read_at_units=len(graded), read_at_days=len(days),
                      read_on=dt.date.today().isoformat(),
                      passed=bool(s["lcb_c"] > 0), at_read=s)
        if verdict_file:
            try:
                os.makedirs(os.path.dirname(verdict_file) or ".", exist_ok=True)
                json.dump(frozen, open(verdict_file, "w"), indent=1)
            except Exception:
                pass
    return dict(base, ready=True, passed=frozen["passed"], frozen=frozen,
                context=ctx)


if __name__ == "__main__":
    U = units()
    print(f"H16 units (days >= {START_DAY}): {len(U)}, graded "
          f"{sum(1 for u in U if 'won' in u)}")
    for u in U[-30:]:
        print(" ", u["day"], u["city"], u["local"], f"dev {u['dev']:+.1f}",
              f"proj {u['proj']}", u["ticker"], f"{u['price']}c",
              "mode" if u["is_mode"] else "", "W" if u.get("won") else
              ("L" if u.get("won") is False else "pending"))
    print(json.dumps(verdict(verdict_file=None), indent=1))
