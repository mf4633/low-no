"""Hypothesis 18 -- a GROWING warm overshoot points at an underpriced bucket.

WRITTEN 2026-10-20, FORWARD-ONLY. Only days >= 2026-10-21 count, so no day this
test judges existed when its rules were fixed.

WHERE IT COMES FROM. Hand picks 10/5-10/20 went 4/23. The one setup with a
positive record was OKC 10/20: the overshoot vs the forecast curve GREW across
consecutive scans (-1.8 -> +2.5 -> +3.3F) and the bucket a full carry pointed at
(76-77, 22c) settled. A backtest of this exact rule, run 2026-10-20 BEFORE this
file was written (scratchpad growing_bt.py, 9/1-10/19), read:
  warm_growing  n=125 / 38 days, hit 49.6% at 43.6c, +4.3c/unit [-3.7, +12.7]
  clean subset (10/9-10/19, after the stale-feed fix) n=33: -5.3c [-20.6, +8.9]
  settle - projection: warm growing -0.64F; COLD growing +2.61F (n=234).
That is not significant, and the clean subset is negative. Expect a fail. The
in-sample numbers are context only; they can never pass H18.

WHY THIS IS NOT H16. H16 takes ONE look (first 10-12 local cycle), needs
|dev| >= 2 at that instant, and trades both signs. H18 conditions on the CHANGE
in dev between two cycles (growth), trades the WARM side only, and looks 9-13
local. The populations overlap (a growing warm dev often also clears H16), so a
pass in both is NOT two independent confirmations; say so if it happens.
Why warm only: the backtest showed cold deviations REVERT (+2.6F) and the market
already prices that (cold_growing YES -4.2c). Mirroring a known-priced effect
would only dilute the claim.

THE RULE (fixed now).
  * Unit: one per (day, city), day >= 2026-10-21.
  * Cycles: logged LADDER rows whose local time is in [09:00, 13:00) and whose
    local date is the trading day.
  * dev: temp_now minus the logged curve INTERPOLATED to the scan minute
    (h16_offcurve.interp_dev). Not the logged curve_dev.
  * Trigger: the FIRST cycle s2 (time order) with PoP <= 20 (or missing) and
    dev2 >= +1.5F, where s1 = the LATEST earlier in-window cycle 45-120 min
    before s2 and dev2 - dev1 >= +1.0F. First trigger only; no shopping.
  * Projection: round(curve_max_f + dev2) (full carry), from s2.
  * Entry: buy YES on the rung containing the projection at s2's logged ask,
    2 <= ya <= 95. No rung or no ask -> the city-day is not a unit (and later
    cycles are NOT tried).
  * Fees: Kalshi ceil(0.07*C*P*(1-P)) on EVERY fill, win or lose.

THE TEST (fixed now).
  * Data bar: >= 60 units AND >= 20 distinct days.
  * PASSES iff the day-clustered 95% lower bound of mean per-unit P&L (cents,
    after fees) is > 0. Cluster-robust SE: se = sqrt(D/(D-1) * sum_d (S_d -
    n_d*m)^2) / N. Deterministic, no bootstrap seed to argue about.
  * Read ONCE at the first nightly that meets the bar, frozen to
    docs/frozen/h18_verdict.json. Later nightlies print context only.
  * Context, never a pass: (a) units where the bucket is adjacent to the
    market's modal bucket and the ask is 15-45c (the hand-pick shape that
    prompted this); (b) settle minus projection; (c) hit rate vs mean ask.
  * Pilot: none. Programme stops 2026-12-31; registered before the 10/31 cutoff.

DEPENDENCY. Needs morning scans. 10/15-10/17 had none (dispatch gap). At the
backtest rate (~2.5 units per day with scans) the bar lands ~mid/late Nov if
morning scans run daily, later if they don't.

Paper only. Nothing here places or recommends orders.
"""
import json, glob, os, math, datetime as dt, zoneinfo
from lowno.config import CITIES
from h16_offcurve import interp_dev, contains, fee_cents, _modal

START_DAY = "2026-10-21"
MIN_UNITS, MIN_DAYS = 60, 20
HOUR_LO, HOUR_HI = 9, 13            # local, [lo, hi)
DEV_MIN, GROW_MIN = 1.5, 1.0
GAP_LO, GAP_HI = 45, 120            # minutes between s1 and s2
POP_MAX = 20
ASK_LO, ASK_HI = 2, 95
SETTLE = "docs/settlements.json"
VERDICT_FILE = "docs/frozen/h18_verdict.json"   # frozen at first read, never rewritten


def yes_pnl(price, won):
    f = fee_cents(price)
    return (100 - price - f) if won else (-price - f)


def _cycles(log_glob, start):
    out = {}
    for path in sorted(glob.glob(log_glob)):
        day = os.path.basename(path)[:-6]
        if day < start:
            continue
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("verdict") != "LADDER" or r.get("city") not in CITIES:
                continue
            d = r.get("detail") or {}
            if d.get("world") or not d.get("rungs"):
                continue
            try:
                u = (dt.datetime.fromisoformat(r["at"].replace("Z", ""))
                     .replace(tzinfo=dt.timezone.utc))
                lt = u.astimezone(zoneinfo.ZoneInfo(CITIES[r["city"]]["tz"]))
            except Exception:
                continue
            if lt.strftime("%Y-%m-%d") != day or not (HOUR_LO <= lt.hour < HOUR_HI):
                continue
            dev = interp_dev(d, lt)
            cmax = (d.get("airmass") or {}).get("curve_max_f")
            if dev is None or cmax is None:
                continue
            out.setdefault((day, r["city"]), []).append(
                dict(u=u, lt=lt, at=r["at"], dev=dev, cmax=cmax,
                     pop=d.get("pop"), rungs=d["rungs"]))
    return out


def units(log_glob="logs/2*.jsonl", settle_path=SETTLE, start=START_DAY):
    settle = {}
    if os.path.exists(settle_path):
        try:
            settle = json.load(open(settle_path))
        except Exception:
            settle = {}
    out = []
    for (day, city), L in sorted(_cycles(log_glob, start).items()):
        L.sort(key=lambda x: x["u"])
        for i, b in enumerate(L):
            if b["pop"] is not None and b["pop"] > POP_MAX:
                continue
            prev = [a for a in L[:i]
                    if GAP_LO <= (b["u"] - a["u"]).total_seconds() / 60 <= GAP_HI]
            if not prev:
                continue
            a = prev[-1]
            if not (b["dev"] >= DEV_MIN and b["dev"] - a["dev"] >= GROW_MIN):
                continue
            # first trigger decides the city-day, unit or not
            proj = round(b["cmax"] + b["dev"])
            rg = next((g for g in b["rungs"] if contains(g, proj)), None)
            if rg is None or rg.get("ya") is None or not (ASK_LO <= rg["ya"] <= ASK_HI):
                break
            mode = _modal(b["rungs"])
            adj = False
            if mode is not None:
                srt = sorted(b["rungs"], key=lambda g: g["fl"] if g.get("fl") is not None else -999)
                try:
                    adj = abs(srt.index(rg) - srt.index(mode)) == 1
                except ValueError:
                    adj = False
            un = dict(day=day, city=city, at=b["at"], local=b["lt"].strftime("%H:%M"),
                      dev1=a["dev"], dev2=b["dev"], curve_max=b["cmax"], proj=proj,
                      ticker=rg.get("t"), price=rg["ya"],
                      adjacent_to_mode=adj)
            T = settle.get(f"{day}|{city}")
            if T is not None:
                un["settle"] = T
                un["won"] = contains(rg, T)
                un["pnl"] = yes_pnl(rg["ya"], un["won"])
            out.append(un)
            break
    return out


def _clustered(rows):
    """rows: [(day, value)]. Mean and day-clustered 95% bounds."""
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
    return dict(n=n, days=D, mean_pnl_c=round(m, 2),
                lcb_c=round(m - 1.96 * se, 2), ucb_c=round(m + 1.96 * se, 2))


def verdict(log_glob="logs/2*.jsonl", settle_path=SETTLE,
            verdict_file=VERDICT_FILE, start=START_DAY):
    try:
        U = units(log_glob, settle_path, start)
    except Exception as e:
        return dict(id="H18", ready=False, passed=False, error=str(e)[:120])
    graded = [u for u in U if "won" in u]
    days = {u["day"] for u in graded}
    base = dict(id="H18", units=len(graded), need_units=MIN_UNITS,
                days=len(days), need_days=MIN_DAYS, pending=len(U) - len(graded))
    if len(graded) < MIN_UNITS or len(days) < MIN_DAYS:
        return dict(base, ready=False, passed=False, reason="data bar not met")
    frozen = None
    if verdict_file and os.path.exists(verdict_file):
        try:
            frozen = json.load(open(verdict_file))
        except Exception:
            frozen = None
    s = _clustered([(u["day"], u["pnl"]) for u in graded])
    adj = [u for u in graded if u["adjacent_to_mode"] and 15 <= u["price"] <= 45]
    ctx = dict(current=s,
               hit=round(sum(u["won"] for u in graded) / len(graded), 3),
               mean_price=round(sum(u["price"] for u in graded) / len(graded), 1),
               settle_minus_proj=round(sum(u["settle"] - u["proj"] for u in graded) / len(graded), 2),
               adjacent_15_45=_clustered([(u["day"], u["pnl"]) for u in adj]))
    if frozen is None:
        frozen = dict(read_at_units=len(graded), read_at_days=len(days),
                      read_on=dt.date.today().isoformat(),
                      passed=bool(s["lcb_c"] is not None and s["lcb_c"] > 0), at_read=s)
        if verdict_file:
            try:
                os.makedirs(os.path.dirname(verdict_file) or ".", exist_ok=True)
                json.dump(frozen, open(verdict_file, "w"), indent=1)
            except Exception:
                pass
    return dict(base, ready=True, passed=frozen["passed"], frozen=frozen, context=ctx)


if __name__ == "__main__":
    U = units()
    print(f"H18 units (days >= {START_DAY}): {len(U)}, graded "
          f"{sum(1 for u in U if 'won' in u)}")
    for u in U[-30:]:
        print(" ", u["day"], u["city"], u["local"], f"dev {u['dev1']:+.1f}->{u['dev2']:+.1f}",
              f"proj {u['proj']}", u["ticker"], f"{u['price']}c",
              "adj" if u["adjacent_to_mode"] else "",
              "W" if u.get("won") else ("L" if u.get("won") is False else "pending"))
    print(json.dumps(verdict(verdict_file=None), indent=1))
