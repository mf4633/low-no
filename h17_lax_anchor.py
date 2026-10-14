"""Hypothesis 17 -- LAX: today's temperature + the marine-layer regime beats the price.

WRITTEN 2026-10-14, FORWARD-ONLY: days >= 2026-10-15. n = 0 at registration.
Full text: CANDIDATE.md "HYPOTHESIS 17". Training set h17_train.json (2022-2025
only), built by h17_train.py and committed with this file; neither changes.

WHERE IT COMES FROM. H15's frozen forecast is regime x season climatology with
no information about TODAY. The out-of-sample backtest on 2026-08-10..09-11 (run
2026-10-14, before this was written) found it 2.2-4.4F COLD on all 6 marine days
and losing -3c/unit on marine trades. The market knew 2026 was running warm;
climatology could not. The regime idea was never tested with a level anchor.
Conditioned on the 11 AM PDT temperature, the rest-of-day rise in 2022-2025
(Aug 15-Nov 30) has sd 1.34F on marine days, 1.57 early-burn, 1.99 clear.

THE MODEL (fixed now).
  * At 19Z, from IEM report_type=3 (the source the classifier and the training
    rows share): cell = h15_lax.regime_at_cut on <= 18Z sky, marine regimes
    pooled; t18 = 18Z-hour tmpf; mx = max tmpf over 13Z-18Z.
  * Residuals r = cli - t18 from training rows with the same cell and day-of-
    year within +/-21d, widening 35/50/75 until >= 25 rows (lax_forecast's
    frozen windows).
  * P(CLI = k) = share of rows with round(t18 + r) == k, keeping only k >=
    round(mx) and renormalizing (the CLI was never below the 13-18Z max in
    1,454 training days).

THE RULE (fixed now).
  * Look: the first LAX LADDER row in the hourly scan with 19:00Z <= at <
    20:00Z. If the scan missed that hour, the lax_book.py record for the day
    (CI, 19:05Z). Nothing later; no shopping across cycles.
  * Trade: on every rung, each side, buy 1 at the ask (1-97c) when model P -
    ask >= 0.15. Kalshi fee ceil(0.07*100*q*(1-q)) on EVERY fill.

THE TEST (fixed now).
  * Bar: >= 60 trades AND >= 20 distinct days.
  * PASS iff the 95% lower bound of mean P&L per trade (cents, after fees),
    from a DAY-clustered bootstrap (4000 resamples, seed 17), is > 0. Read
    ONCE to docs/frozen/h17_verdict.json.
  * Context only, never a pass: full-ladder Brier model vs market (YES mid),
    and the MARINE slice's P&L.
  * RETRO GATE, declared before it was run: the same rule, once, on
    2026-08-10..09-11 (days the model never trained on). If retro mean P&L < 0
    AND model Brier >= market Brier, H17 is KILLED before forward collection.
    Anything else and it collects forward. The retro run can never PASS H17.
  * No pilot. Programme stops 2026-12-31; registered inside the 10/31 cutoff.

Paper only. Nothing here places or recommends orders.
"""
import csv, glob, io, json, math, os, random, time, urllib.request, datetime as dt
import h15_lax as H15
import lax_regime as LR

START_DAY = "2026-10-15"
RETRO = ("2026-08-10", "2026-09-11")
EDGE = 0.15
ASK_LO, ASK_HI = 1, 97
MIN_UNITS, MIN_DAYS = 60, 20
WINDOWS, MIN_N = (21, 35, 50, 75), 25
TRAIN = "h17_train.json"
SETTLE = "docs/settlements.json"
OBS_CACHE = "logs/lax_obs_h17.json"
VERDICT_FILE = "docs/frozen/h17_verdict.json"
RETRO_FILE = "docs/frozen/h17_retro.json"
_MON = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


def fee_cents(p):
    q = p / 100.0
    return math.ceil(0.07 * 100 * q * (1 - q))


def _doy(d):
    return dt.date.fromisoformat(d).timetuple().tm_yday


def _near(a, b):
    return min(abs(a - b), 366 - abs(a - b))


def forecast(cell, day, t18, mx, rows=None):
    rows = rows if rows is not None else json.load(open(TRAIN))
    d0 = _doy(day)
    for w in WINDOWS:
        sel = [r[4] - r[2] for r in rows if r[1] == cell and _near(_doy(r[0]), d0) <= w]
        if len(sel) >= MIN_N:
            break
    if not sel:
        return {}
    floor = round(mx)
    ks = [round(t18 + r) for r in sel]
    ks = [k for k in ks if k >= floor]
    if not ks:
        return {floor: 1.0}
    return {k: ks.count(k) / len(ks) for k in sorted(set(ks))}


def obs(start, end, fetch=True, cache=OBS_CACHE):
    """{day: {"sky": {h: ceil}, "tmp": {h: tmpf}}} from IEM report_type=3."""
    out = {}
    if cache and os.path.exists(cache):
        try:
            out = json.load(open(cache))
        except Exception:
            out = {}
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    need = [d for d in _days(start, end) if d not in out or d >= today]
    if fetch and need:
        d0, d1 = dt.date.fromisoformat(need[0]), dt.date.fromisoformat(need[-1]) + dt.timedelta(days=1)
        u = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=LAX"
             "&data=tmpf&data=skyc1&data=skyl1&data=skyc2&data=skyl2"
             f"&year1={d0.year}&month1={d0.month}&day1={d0.day}"
             f"&year2={d1.year}&month2={d1.month}&day2={d1.day}"
             "&tz=UTC&format=onlycomma&latlon=no&missing=M&trace=T&direct=no&report_type=3")
        txt = None
        for a in range(4):
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "lowno/1.0"})
                txt = urllib.request.urlopen(req, timeout=120).read().decode()
                break
            except Exception:
                time.sleep(5 * (a + 1))
        if txt:
            new = {}
            for r in csv.DictReader(io.StringIO(txt)):
                v = r["valid"]; d, h = v[:10], str(int(v[11:13]))
                o = new.setdefault(d, {"sky": {}, "tmp": {}})
                o["sky"][h] = LR.ceil_ft(r)
                try:
                    o["tmp"][h] = float(r["tmpf"])
                except Exception:
                    pass
            out.update(new)
            if cache:
                try:
                    json.dump({d: o for d, o in out.items() if d < today}, open(cache, "w"))
                except Exception:
                    pass
    return out


def _days(a, b):
    d, e = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    while d <= e:
        yield d.isoformat(); d += dt.timedelta(days=1)


def inputs(o):
    """(cell, t18, mx) knowable at 19Z, or None."""
    sky = {int(h): v for h, v in (o or {}).get("sky", {}).items()}
    tmp = {int(h): v for h, v in (o or {}).get("tmp", {}).items()}
    if not all(h in sky for h in range(12, 19)) or 18 not in tmp:
        return None
    g = H15.regime_at_cut(sky)
    cell = "MARINE" if g in ("LATE_BURN", "NO_BURN") else g
    return cell, tmp[18], max(v for h, v in tmp.items() if 13 <= h <= 18)


def _fix_bounds(rungs, day):
    """Pre-2026-08-31 logs carry two known raw-threshold off-by-ones."""
    if day >= "2026-08-31":
        return [(g.get("fl"), g.get("cap"), g) for g in rungs]
    fls = [g["fl"] for g in rungs if g.get("fl") is not None and g.get("cap") is not None]
    caps = [g["cap"] for g in rungs if g.get("fl") is not None and g.get("cap") is not None]
    out = []
    for g in rungs:
        lo, hi = g.get("fl"), g.get("cap")
        if lo is None and hi is not None and fls and hi == min(fls): hi -= 1
        if hi is None and lo is not None and caps and lo == max(caps): lo += 1
        out.append((lo, hi, g))
    return out


def ladder(day, log_dir="logs", book_dir="logs/lax_book"):
    """[(lo, hi, ya, yb, na)] at the 19Z look, scan first, lax_book fallback."""
    f = os.path.join(log_dir, f"{day}.jsonl")
    if os.path.exists(f):
        for line in open(f, encoding="utf-8"):
            if '"LAX"' not in line or '"LADDER"' not in line:
                continue
            r = json.loads(line)
            if r.get("city") == "LAX" and r["at"][:10] == day and r["at"][11:13] == "19":
                return [(lo, hi, g.get("ya"), g.get("yb"), g.get("na"))
                        for lo, hi, g in _fix_bounds(r["detail"]["rungs"], day)], "scan"
    f = os.path.join(book_dir, f"{day}.jsonl")
    if os.path.exists(f):
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            if r["at"][11:13] == "19" and r["rungs"] and "na" in r["rungs"][0]:
                return [(g["floor"], g["cap"], g["ya"], g.get("yb"), g["na"]) for g in r["rungs"]], "lax_book"
    return None, None


def day_record(day, o, settles, rows=None, log_dir="logs", book_dir="logs/lax_book"):
    inp = inputs(o)
    lad, src = ladder(day, log_dir, book_dir)
    if not inp or not lad:
        return None
    cell, t18, mx = inp
    dist = forecast(cell, day, t18, mx, rows)
    if not dist:
        return None
    s = settles.get(f"{day}|LAX")
    rec = dict(day=day, cell=cell, t18=t18, mx=mx, src=src, trades=[], brier=None)
    bm, bk = [], []
    for lo, hi, ya, yb, na in lad:
        if ya is None:
            continue
        L = -999 if lo is None else lo; U = 999 if hi is None else hi
        pm = sum(p for k, p in dist.items() if L <= k <= U)
        win = (L <= s <= U) if s is not None else None
        if win is not None:
            mid = ((yb if yb is not None else ya) + ya) / 200
            bk.append((mid - win) ** 2); bm.append((pm - win) ** 2)
        for side, p, ask in (("YES", pm, ya), ("NO", 1 - pm, na)):
            if ask is None or not ASK_LO <= ask <= ASK_HI or p - ask / 100 < EDGE:
                continue
            t = dict(side=side, lo=lo, hi=hi, ask=ask, p=round(p, 3))
            if win is not None:
                won = win if side == "YES" else not win
                t.update(won=won, pnl=(100 - ask if won else -ask) - fee_cents(ask))
            rec["trades"].append(t)
    if s is not None:
        rec.update(settle=s, brier=(sum(bm) / len(bm), sum(bk) / len(bk)))
    return rec


def records(start, end, settle_path=SETTLE, obs_data=None, rows=None, **kw):
    settles = json.load(open(settle_path)) if os.path.exists(settle_path) else {}
    O = obs_data if obs_data is not None else obs(start, end)
    out = []
    for d in _days(start, end):
        r = day_record(d, O.get(d), settles, rows, **kw)
        if r:
            out.append(r)
    return out


def summarize(R):
    T = [(r["day"], t) for r in R for t in r["trades"] if "pnl" in t]
    if not T:
        return dict(n=0)
    by = {}
    for d, t in T:
        by.setdefault(d, []).append(t["pnl"])
    m = sum(t["pnl"] for _, t in T) / len(T)
    ks = sorted(by); rnd = random.Random(17); bs = []
    for _ in range(4000):
        p = [x for d in (rnd.choice(ks) for _ in ks) for x in by[d]]
        bs.append(sum(p) / len(p))
    bs.sort()
    B = [r["brier"] for r in R if r["brier"]]
    M = [t["pnl"] for r in R if r["cell"] == "MARINE" for t in r["trades"] if "pnl" in t]
    return dict(n=len(T), days=len(by), hit=round(sum(t["won"] for _, t in T) / len(T), 3),
                mean_ask=round(sum(t["ask"] for _, t in T) / len(T), 1),
                mean_pnl_c=round(m, 2), lcb_c=round(bs[100], 2), ucb_c=round(bs[3899], 2),
                brier_model=round(sum(b[0] for b in B) / len(B), 4) if B else None,
                brier_mkt=round(sum(b[1] for b in B) / len(B), 4) if B else None,
                marine_n=len(M), marine_mean_pnl_c=round(sum(M) / len(M), 2) if M else None)


def retro(write=RETRO_FILE, **kw):
    """The pre-declared retro gate. Writes once; later calls return the file."""
    if write and os.path.exists(write):
        return json.load(open(write))
    s = summarize(records(*RETRO, **kw))
    killed = bool(s.get("n") and s["mean_pnl_c"] < 0 and s["brier_model"] >= s["brier_mkt"])
    out = dict(window=RETRO, run_on=dt.date.today().isoformat(), killed=killed, summary=s)
    if write:
        os.makedirs(os.path.dirname(write), exist_ok=True)
        json.dump(out, open(write, "w"), indent=1)
    return out


def verdict(verdict_file=VERDICT_FILE, retro_file=RETRO_FILE, end=None, **kw):
    end = end or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()
    try:
        rg = json.load(open(retro_file)) if retro_file and os.path.exists(retro_file) else None
        if rg and rg.get("killed"):
            return dict(id="H17", ready=False, passed=False, reason="KILLED by retro gate")
        R = records(START_DAY, end, **kw) if end >= START_DAY else []
    except Exception as e:
        return dict(id="H17", ready=False, passed=False, error=str(e)[:120])
    G = [t for r in R for t in r["trades"] if "pnl" in t]
    days = len({r["day"] for r in R if any("pnl" in t for t in r["trades"])})
    base = dict(id="H17", units=len(G), need_units=MIN_UNITS, days=days, need_days=MIN_DAYS)
    if len(G) < MIN_UNITS or days < MIN_DAYS:
        return dict(base, ready=False, passed=False, reason="data bar not met")
    frozen = json.load(open(verdict_file)) if verdict_file and os.path.exists(verdict_file) else None
    s = summarize(R)
    if frozen is None:
        frozen = dict(read_at_units=len(G), read_at_days=days, read_on=dt.date.today().isoformat(),
                      passed=bool(s["lcb_c"] > 0), at_read=s)
        if verdict_file:
            os.makedirs(os.path.dirname(verdict_file), exist_ok=True)
            json.dump(frozen, open(verdict_file, "w"), indent=1)
    return dict(base, ready=True, passed=frozen["passed"], frozen=frozen, context=s)


if __name__ == "__main__":
    print(json.dumps(verdict(verdict_file=None), indent=1))
