"""Hypothesis 15 harness -- is the LAX marine-layer regime in the price?

Registration: docs/H15.md (2026-09-12). Classifier lax_regime.py and forecast
lax_forecast.py were FROZEN that day before any LAX book existed; neither is
edited here. This file only decides WHICH rows are scored, at WHAT instant, and
reads the verdict ONCE at the bar.

WRITTEN 2026-10-14, BEFORE ANY H15 SCORE WAS COMPUTED. Nothing below was chosen
after seeing a market-vs-model number for LAX. The only thing looked at first
was a regime COUNT (8 marine days 9/12-10/13, weather data only), which the
registration's own rate projection already called for.

SCORING RULES (fixed now, see the H15.md addendum of the same date).
  * Unit: one LAX trading day d >= 2026-09-12 with a settled CLI high, an
    hourly sky record covering 12Z-18Z, >= 20 poll rows on d's bottom rung
    (the registered unit), and >= 1 of them inside the scoring window.
  * Stratum: the frozen regime. MARINE = stratus (BKN/OVC < 3000 ft) at
    16Z-18Z = LATE_BURN or NO_BURN, which pool into one stratum by
    registration. CONTROL = NO_STRATUS. EARLY_BURN is context only.
  * Instant: poll rows with 19:00Z <= at < 20:00Z (12:00-13:00 PDT), the first
    full hour after the classifier's 16Z-18Z window is fully observed (the
    18:53Z routine ob). Earlier, membership is not knowable; later, the high
    is largely in and every price is trivially right.
  * Model at that instant: the frozen forecast for the regime KNOWABLE BY 18Z.
    That separates NO_STRATUS / EARLY_BURN exactly, but LATE_BURN vs NO_BURN
    is only decided at 19Z-21Z, so a marine day gets the frozen cell built
    from BOTH marine regimes pooled (same windows, same MIN_N, same
    empirical method). Using the LATE_BURN cell alone would be a train/serve
    mismatch: it is forecasting with a fact (no NO_BURN) not yet known.
  * Probabilities, bottom rung (YES = high <= cap): market = YES mid
    (yb+ya)/2, ya alone if no bid; model = P(CLI <= cap) from the cell.
    Day Brier = mean over the window's rows. Stratum Brier = mean over days.
  * Bar: 20 marine days (registered) AND 10 control days (a floor so the
    comparison exists at all; control days run ~70% of the season, so this
    never binds first in practice).
  * PASS iff market Brier(MARINE) - market Brier(CONTROL) >= 0.02 AND
    model Brier(MARINE) < market Brier(MARINE). Both point conditions as
    registered. A day-level bootstrap 95% CI on each difference is reported
    beside it; REFUTED (the registration's retirement) iff the upper bound of
    marine-minus-control market Brier is below 0.
  * Read ONCE: the first nightly at the bar writes docs/frozen/h15_verdict.json
    and every later run reports that file plus current context.

Paper only. An information claim about a price; no pilot can promote from it.
"""
import csv, glob, io, json, math, os, random, re, urllib.request, datetime as dt

import lax_regime as LR
import lax_forecast as LF

START_DAY = "2026-09-12"
MIN_MARINE, MIN_CONTROL = 20, 10
MIN_ROWS = 20
WIN_LO, WIN_HI = 19, 20            # UTC hours, [lo, hi)
CUT_HOUR = 18                      # last sky hour knowable at the instant
DIFF_BAR = 0.02
SETTLE = "docs/settlements.json"
POLL_GLOB = "logs/poll_lax/*.jsonl"
SKY_CACHE = "logs/lax_sky_h15.json"
VERDICT_FILE = "docs/frozen/h15_verdict.json"   # NOT docs/*.json: never regenerable
CONTROL = ("NO_STRATUS",)
_MON = {m: i for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}


def ticker_day(t):
    """KXHIGHLAX-26OCT13-T68 -> 2026-10-13. The poll file date is UTC and the
    evening rows already trade TOMORROW's ladder, so the ticker is the key."""
    m = re.search(r"-(\d\d)([A-Z]{3})(\d\d)-", t or "")
    if not m:
        return None
    return dt.date(2000 + int(m.group(1)), _MON[m.group(2)], int(m.group(3))).isoformat()


def sky(start=START_DAY, end=None, fetch=True, cache=SKY_CACHE):
    """{day: {utc_hour: ceiling_ft|None}} from IEM report_type=3, the source the
    classifier was trained on (see lax_book._iem_sky for why never another).
    Completed days are cached; today is always refetched."""
    out = {}
    if cache and os.path.exists(cache):
        try:
            out = {d: {int(h): v for h, v in o.items()}
                   for d, o in json.load(open(cache)).items()}
        except Exception:
            out = {}
    end = end or dt.datetime.now(dt.timezone.utc).date().isoformat()
    if not fetch:
        return out
    d0 = dt.date.fromisoformat(start)
    have = [d for d in out if d < end]
    if have:
        d0 = max(d0, dt.date.fromisoformat(max(have)) + dt.timedelta(days=1))
    d1 = dt.date.fromisoformat(end) + dt.timedelta(days=1)
    if d0 < d1:
        u = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=LAX"
             "&data=skyc1&data=skyl1&data=skyc2&data=skyl2"
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
                if a < 3:
                    __import__("time").sleep(5 * (a + 1))
        if txt:
            new = {}
            for r in csv.DictReader(io.StringIO(txt)):
                v = r.get("valid", "")
                new.setdefault(v[:10], {})[int(v[11:13])] = LR.ceil_ft(r)
            out.update(new)
            if cache:
                try:
                    keep = {d: o for d, o in out.items() if d < end}
                    json.dump(keep, open(cache, "w"))
                except Exception:
                    pass
    return out


def regime_at_cut(obs, cut=CUT_HOUR):
    """Regime from sky hours <= cut only. Equals the full-day regime for
    NO_STRATUS/EARLY_BURN; every marine day reads LATE_BURN here."""
    return LR.regime({h: v for h, v in obs.items() if h <= cut})


def marine_rows(rows=None):
    """Frozen training rows with the two marine regimes relabeled as one cell."""
    rows = rows if rows is not None else LF._load()
    return [(d, "MARINE" if g in LF.MARINE else g, h) for d, g, h in rows]


def model_cell(obs, day, rows=None):
    g = regime_at_cut(obs)
    if g in LF.MARINE:
        return "MARINE", LF.forecast("MARINE", day, marine_rows(rows))
    return g, LF.forecast(g, day, rows)


def _market_p(rung):
    ya, yb = rung.get("ya"), rung.get("yb")
    if ya is None:
        return None
    return ((yb + ya) / 2 if yb is not None else ya) / 100.0


def units(poll_glob=POLL_GLOB, settle_path=SETTLE, sky_data=None, rows=None,
          start=START_DAY):
    settles = json.load(open(settle_path)) if os.path.exists(settle_path) else {}
    S = sky_data if sky_data is not None else sky(start)
    polls = {}
    for f in sorted(glob.glob(poll_glob)):
        for line in open(f, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            rung = r.get("rung") or {}
            d = ticker_day(rung.get("ticker"))
            if d and d >= start and rung.get("cap") is not None:
                polls.setdefault(d, []).append(r)
    out = []
    for d in sorted(polls):
        P = polls[d]
        obs = S.get(d) or {}
        if len(P) < MIN_ROWS or not all(h in obs for h in range(12, CUT_HOUR + 1)):
            continue
        full = LR.regime(obs) if all(h in obs for h in range(12, 22)) else None
        win = [r for r in P if WIN_LO <= int(r["at"][11:13]) < WIN_HI
               and r["at"][:10] == d and _market_p(r["rung"]) is not None]
        if not win:
            continue
        cell, fc = model_cell(obs, d, rows)
        if not fc["n"]:
            continue
        u = dict(day=d, regime=regime_at_cut(obs), regime_full=full, cell=cell,
                 stratum="MARINE" if cell == "MARINE" else
                         ("CONTROL" if cell in CONTROL else "CONTEXT"),
                 n_rows=len(P), n_win=len(win))
        key = f"{d}|LAX"
        if key in settles and settles[key] is not None:
            s = settles[key]
            bm, bk = [], []
            for r in win:
                cap = r["rung"]["cap"]
                y = 1.0 if s <= cap else 0.0
                bk.append((_market_p(r["rung"]) - y) ** 2)
                bm.append((LF.p_at_or_below(fc["dist"], cap) - y) ** 2)
            u.update(settle=s, brier_mkt=sum(bk) / len(bk), brier_model=sum(bm) / len(bm))
        out.append(u)
    return out


def _boot(a, b, f, n=2000, seed=15):
    """95% CI of f(resampled a, resampled b), resampling DAYS."""
    rnd = random.Random(seed)
    v = []
    for _ in range(n):
        ra = [rnd.choice(a) for _ in a]
        rb = [rnd.choice(b) for _ in b] if b else []
        v.append(f(ra, rb))
    v.sort()
    return round(v[int(0.025 * n)], 4), round(v[int(0.975 * n) - 1], 4)


def _mean(xs):
    return sum(xs) / len(xs)


def score(graded):
    M = [u for u in graded if u["stratum"] == "MARINE"]
    C = [u for u in graded if u["stratum"] == "CONTROL"]
    mk_m, mk_c = _mean([u["brier_mkt"] for u in M]), _mean([u["brier_mkt"] for u in C])
    md_m = _mean([u["brier_model"] for u in M])
    d1 = mk_m - mk_c
    d2 = md_m - mk_m
    ci1 = _boot(M, C, lambda a, b: _mean([u["brier_mkt"] for u in a]) - _mean([u["brier_mkt"] for u in b]))
    ci2 = _boot(M, None, lambda a, b: _mean([u["brier_model"] - u["brier_mkt"] for u in a]))
    return dict(mkt_marine=round(mk_m, 4), mkt_control=round(mk_c, 4),
                model_marine=round(md_m, 4),
                model_control=round(_mean([u["brier_model"] for u in C]), 4),
                mkt_marine_minus_control=round(d1, 4), ci95=ci1,
                model_minus_mkt_marine=round(d2, 4), ci95_model=ci2,
                passed=bool(d1 >= DIFF_BAR and d2 < 0),
                refuted=bool(ci1[1] < 0))


def verdict(poll_glob=POLL_GLOB, settle_path=SETTLE, verdict_file=VERDICT_FILE,
            sky_data=None, rows=None):
    try:
        U = units(poll_glob, settle_path, sky_data, rows)
    except Exception as e:
        return dict(id="H15", ready=False, passed=False, error=str(e)[:120])
    g = [u for u in U if "brier_mkt" in u]
    nm = sum(1 for u in g if u["stratum"] == "MARINE")
    nc = sum(1 for u in g if u["stratum"] == "CONTROL")
    base = dict(id="H15", marine_days=nm, need_marine=MIN_MARINE,
                control_days=nc, need_control=MIN_CONTROL,
                context_days=sum(1 for u in g if u["stratum"] == "CONTEXT"),
                pending=len(U) - len(g))
    if nm < MIN_MARINE or nc < MIN_CONTROL:
        # COUNTS ONLY below the bar -- no Brier leaves this function early.
        return dict(base, ready=False, passed=False, reason="data bar not met")
    frozen = None
    if verdict_file and os.path.exists(verdict_file):
        try:
            frozen = json.load(open(verdict_file))
        except Exception:
            frozen = None
    s = score(g)
    if frozen is None:
        frozen = dict(read_at_marine=nm, read_at_control=nc,
                      read_on=dt.date.today().isoformat(),
                      passed=s["passed"], refuted=s["refuted"], at_read=s)
        if verdict_file:
            try:
                os.makedirs(os.path.dirname(verdict_file) or ".", exist_ok=True)
                json.dump(frozen, open(verdict_file, "w"), indent=1)
            except Exception:
                pass
    return dict(base, ready=True, passed=frozen["passed"], frozen=frozen, context=s)


if __name__ == "__main__":
    U = units()
    for u in U:
        print(" ", u["day"], f"{u['regime']:<11}", f"full={u['regime_full'] or '?':<11}",
              f"{u['stratum']:<8}", f"rows {u['n_rows']:>3} win {u['n_win']:>2}",
              "settled" if "settle" in u else "pending")
    print(json.dumps(verdict(verdict_file=None), indent=1))
