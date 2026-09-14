r"""Morning-sky regime classifier for EVERY US Kalshi city.

WHAT THIS IS. `lax_regime.py` established that a morning-observable sky regime
splits the LAX daily high hard enough to collapse its spread from 7.05F to
2.7-3.0F. That machinery ran at exactly one station. This file applies ONE
classifier, unchanged, to all 23 US cities in `config.CITIES`, and measures per
city whether the split is real. It does not touch `lax_regime.py`,
`lax_forecast.py` or `lax_book.py`, all frozen 2026-09-12 and carrying H15.

NO PRICE DATA IS IN THE LOOP. The inputs are IEM hourly METAR sky groups and
NWS CLI highs, both free and both historical. Nothing here can have been tuned
against a market, for the same reason H15 was built that way.

THREE DELIBERATE DIFFERENCES FROM lax_regime.py, each a fix, each stated so
nobody later mistakes this file's output for that one's:

  1. LOCAL hours, not UTC hours. LAX's windows are UTC 12-14 / 16-18 / 19-21,
     which are 05-07 / 09-11 / 12-14 PDT -- dawn, mid-morning, early afternoon.
     Hard-coding the UTC hours would point those windows at the wrong part of
     the day in every other time zone (12Z is 08:00 in Boston and 05:00 in
     Seattle), so the windows here are LOCAL and the LAX values are reproduced
     exactly during PDT. Under PST they land one hour earlier than LAX's frozen
     file, which is why this writes `city_regimes.json` and NEVER overwrites
     `lax_regimes.json`. H15 keeps its own frozen input.

  2. THREE sky layers, not two. METAR reports layers ascending by base, so a
     ceiling under 3000 ft is nearly always layer 1 -- but FEW008 SCT015 OVC025
     is legal and LAX's 2-layer read scores it NO_STRATUS. The disagreement is
     COUNTED at LAX and printed, rather than assumed negligible.

  3. WINDOW COVERAGE IS REQUIRED, not inferred from a day-total. LAX accepts a
     day with >=18 hourly sky obs. That does not guarantee the three decision
     windows are among them, and a missing window reads as "no stratus" --
     silently, which is the failure mode this project keeps re-learning. A day
     here is classified only if every window has at least one observation.

THE MULTIPLICITY PROBLEM, HANDLED UP FRONT. Asking 23 cities "does the regime
split the high?" at alpha=0.05 buys roughly one false positive by construction.
The LAX result was a single pre-specified test; this is a family. So each city
gets a permutation p-value (regime labels shuffled WITHIN calendar month, so
the null preserves seasonality) and the family gets Holm-Bonferroni. A city
that survives Holm is a candidate; a city that does not is noise and is
reported as noise.

Usage:  python city_regime.py              (all cities, build city_regimes.json)
        python city_regime.py --cities SEA,SFO,SAN
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import random
import statistics as st
import time
import urllib.error
import urllib.request
import zoneinfo
from collections import Counter, defaultdict

from lowno.config import CITIES

# ---------------------------------------------------------------- FROZEN ----
# Set here, before any city's numbers have been looked at. Changing any of them
# after seeing a result is refitting, and is recorded with a reason if it ever
# happens -- like every other correction in this repository.
STRATUS_FT = 3000.0              # a BKN/OVC base below this is "stratus"
WIN_DAWN = (5, 6, 7)             # local hours
WIN_MIDMORN = (9, 10, 11)
WIN_EARLYPM = (12, 13, 14)
YEARS = (2022, 2023, 2024, 2025, 2026)     # same 5 years lax_regime.py used
TRADING_WINDOW = ((8, 15), (10, 5))        # Aug 15 - Oct 5, the season traded
N_PERM = 2000                    # permutation draws per city
ALPHA = 0.05                     # family-wise, Holm-corrected
REGIMES = ("NO_STRATUS", "EARLY_BURN", "LATE_BURN", "NO_BURN")

CACHE_DIR = "cache"
OUT_JSON = "city_regimes.json"
OUT_SUMMARY = "docs/city_regimes_summary.json"


# ------------------------------------------------------------------ IO ------
def cached(name, fn, min_bytes=200):
    """Disk-cached fetch with backoff. IEM 503s under load; it is the only
    source here on purpose (see lax_book._iem_sky for what happened the one
    time a 'equivalent' feed was substituted)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    p = os.path.join(CACHE_DIR, name)
    if os.path.exists(p) and os.path.getsize(p) > min_bytes:
        return io.open(p, encoding="utf-8").read()
    last = None
    for attempt in range(6):
        try:
            d = fn()
            if d is not None and len(d) > min_bytes:
                io.open(p, "w", encoding="utf-8").write(d)
                return d
            last = f"short response ({0 if d is None else len(d)} bytes)"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as e:
            last = str(e)[:80]
        if attempt < 5:
            time.sleep(min(90, 5 * (2 ** attempt)))
    raise RuntimeError(f"{name}: {last}")


def fetch_sky(site):
    """Hourly routine (:5x) sky groups, all YEARS, one request."""
    y0, y1 = YEARS[0], YEARS[-1] + 1
    u = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
         f"?station={site}"
         "&data=skyc1&data=skyl1&data=skyc2&data=skyl2&data=skyc3&data=skyl3"
         f"&year1={y0}&month1=1&day1=1&year2={y1}&month2=1&day2=1"
         "&tz=UTC&format=onlycomma&latlon=no&missing=M&trace=T&direct=no"
         "&report_type=3")
    return cached(f"sky_{site}.csv",
                  lambda: urllib.request.urlopen(u, timeout=900).read().decode())


def fetch_cli(station4):
    """{local_date: high_f} from the NWS CLI product -- the settlement quantity."""
    out = {}
    for y in YEARS:
        u = f"https://mesonet.agron.iastate.edu/json/cli.py?station={station4}&year={y}"
        try:
            d = json.loads(cached(f"cli_{station4}_{y}.json",
                                  lambda: urllib.request.urlopen(u, timeout=180).read().decode(),
                                  min_bytes=20))
        except Exception as e:
            # A station-year with no CLI is a fact about the station, not an
            # error to retry forever. It is reported in the coverage column.
            print(f"    CLI {station4} {y}: {str(e)[:60]}")
            continue
        for r in d.get("results") or []:
            h = r.get("high")
            if h in (None, "", "M"):
                continue
            try:
                out[r["valid"][:10]] = float(h)
            except Exception:
                pass
        time.sleep(0.4)
    return out


# ------------------------------------------------------------ CLASSIFY ------
def ceiling_ft(row, layers=3):
    """Lowest BKN/OVC base in ft, or None. `layers=2` reproduces lax_regime.py."""
    lo = None
    for i in range(1, layers + 1):
        c, l = row.get(f"skyc{i}"), row.get(f"skyl{i}")
        if c in ("BKN", "OVC") and l not in ("M", "", None):
            try:
                v = float(l)
            except Exception:
                continue
            lo = v if lo is None else min(lo, v)
    return lo


def regime(obs):
    """obs: {local_hour: ceiling_ft or None} for observed hours only.

    Returns a regime name, or None when a decision window was not observed.
    Structure is lax_regime.regime() unchanged; only the window hours are local
    and the missing-window case is refused instead of defaulting to clear.
    """
    def seen(win):
        return any(h in obs for h in win)

    def stratus(win):
        return any(obs.get(h) is not None and obs[h] < STRATUS_FT for h in win)

    if not (seen(WIN_DAWN) and seen(WIN_MIDMORN) and seen(WIN_EARLYPM)):
        return None
    early, mid, pm = stratus(WIN_DAWN), stratus(WIN_MIDMORN), stratus(WIN_EARLYPM)
    if not early and not mid:
        return "NO_STRATUS"
    if pm:
        return "NO_BURN"
    if mid:
        return "LATE_BURN"
    return "EARLY_BURN"


def morning_call(reg):
    """The part of the regime knowable by 11:00 local, i.e. inside the 09:00-13:00
    entry window. LATE_BURN and NO_BURN are indistinguishable until the early
    afternoon window closes, so a rule that had to act during the entry window
    can only use this 3-way collapse. Deterministic function of `regime`, not a
    second fit."""
    if reg is None:
        return None
    return "STRATUS_HOLDING" if reg in ("LATE_BURN", "NO_BURN") else reg


def day_regimes(csv_text, tz):
    """{local_date: (regime3, regime2)} -- the 3-layer read and the 2-layer read."""
    utc = dt.timezone.utc
    zone = zoneinfo.ZoneInfo(tz)
    by_day3, by_day2 = defaultdict(dict), defaultdict(dict)
    for r in csv.DictReader(io.StringIO(csv_text)):
        v = r.get("valid") or ""
        if len(v) < 16:
            continue
        try:
            t = dt.datetime(int(v[0:4]), int(v[5:7]), int(v[8:10]),
                            int(v[11:13]), int(v[14:16]), tzinfo=utc).astimezone(zone)
        except Exception:
            continue
        d, h = t.date().isoformat(), t.hour
        # Keep the FIRST observation of each local hour. IEM report_type=3 is
        # one routine ob per hour, but a corrected re-issue can duplicate it,
        # and taking whichever arrives last is how lax_book's api.weather.gov
        # experiment flipped a regime.
        if h not in by_day3[d]:
            by_day3[d][h] = ceiling_ft(r, layers=3)
            by_day2[d][h] = ceiling_ft(r, layers=2)
    out = {}
    for d in by_day3:
        out[d] = (regime(by_day3[d]), regime(by_day2[d]))
    return out


# ------------------------------------------------------------ STATISTICS ----
def demean_by_month(rows):
    """[(day, regime, high)] -> [(regime, high - that month's mean high)].

    Month removed, so a regime that is merely a season proxy scores zero. Same
    construction as the H15 weather-leg table.
    """
    by_m = defaultdict(list)
    for d, g, h in rows:
        by_m[d[5:7]].append(h)
    mu = {m: sum(v) / len(v) for m, v in by_m.items()}
    return [(d[5:7], g, h - mu[d[5:7]]) for d, g, h in rows]


def eta_sq(pairs):
    """Share of within-month variance explained by the regime label."""
    vals = [x for _, _, x in pairs]
    if len(vals) < 8:
        return 0.0
    gm = sum(vals) / len(vals)
    sst = sum((x - gm) ** 2 for x in vals)
    if sst <= 0:
        return 0.0
    ssw = 0.0
    for g in set(p[1] for p in pairs):
        v = [x for _, gg, x in pairs if gg == g]
        m = sum(v) / len(v)
        ssw += sum((x - m) ** 2 for x in v)
    return max(0.0, 1.0 - ssw / sst)


def perm_p(pairs, n=N_PERM, seed=20260914):
    """P(eta^2 >= observed) with regime labels shuffled WITHIN calendar month.

    Shuffling within month is what makes the null 'the regime carries nothing
    beyond the season'. A global shuffle would break the seasonal balance of the
    labels and hand back a p-value for a question nobody asked.
    """
    obs = eta_sq(pairs)
    rng = random.Random(seed)
    idx = defaultdict(list)
    for i, (m, _, _) in enumerate(pairs):
        idx[m].append(i)
    labels = [g for _, g, _ in pairs]
    work = list(pairs)
    hits = 0
    for _ in range(n):
        shuffled = labels[:]
        for m, ii in idx.items():
            pool = [labels[i] for i in ii]
            rng.shuffle(pool)
            for i, g in zip(ii, pool):
                shuffled[i] = g
        for i, g in enumerate(shuffled):
            work[i] = (pairs[i][0], g, pairs[i][2])
        if eta_sq(work) >= obs:
            hits += 1
    return obs, (hits + 1) / (n + 1)


def holm(pvals, alpha=ALPHA):
    """Holm-Bonferroni. Returns {key: bool survived}."""
    order = sorted(pvals, key=lambda k: pvals[k])
    m = len(order)
    out, still = {}, True
    for i, k in enumerate(order):
        thresh = alpha / (m - i)
        if still and pvals[k] <= thresh:
            out[k] = True
        else:
            still = False
            out[k] = False
    return out


def in_trading_window(day):
    (m0, d0), (m1, d1) = TRADING_WINDOW
    mm, dd = int(day[5:7]), int(day[8:10])
    return (mm, dd) >= (m0, d0) and (mm, dd) <= (m1, d1)


# ------------------------------------------------------------------ MAIN ----
def build(cities):
    out, disagree = {}, Counter()
    for city in cities:
        meta = CITIES[city]
        st4, site, tz = meta["station"], meta["station"][1:].upper(), meta["tz"]
        print(f"  {city} ({st4})...", flush=True)
        try:
            sky = fetch_sky(site)
        except Exception as e:
            print(f"    sky fetch FAILED: {str(e)[:80]} -- city skipped")
            continue
        regs = day_regimes(sky, tz)
        cli = fetch_cli(st4)
        rows, rows2, n_nocli, n_noreg = [], [], 0, 0
        for d, (g3, g2) in sorted(regs.items()):
            if g3 is None:
                n_noreg += 1
                continue
            if d not in cli:
                n_nocli += 1
                continue
            rows.append((d, g3, cli[d]))
            rows2.append((d, g2, cli[d]))
            if g2 != g3:
                disagree[city] += 1
        # rows2 is a DIAGNOSTIC, not an input: only its disagreement count is
        # kept, so the committed file holds one series and cannot be read as
        # offering a choice of classifier.
        out[city] = dict(station=st4, tz=tz, rows=rows,
                         n_unclassified=n_noreg, n_no_cli=n_nocli)
        print(f"    {len(rows)} classified days  "
              f"({n_noreg} windows incomplete, {n_nocli} no CLI, "
              f"{disagree[city]} 3-vs-2-layer disagreements)")
    return out, disagree


def report(built):
    """Per-city tables + the family-wise test. Returns the summary dict."""
    stats, pvals = {}, {}
    for city, blob in sorted(built.items()):
        rows = [tuple(r) for r in blob["rows"]]
        if len(rows) < 60:
            stats[city] = dict(n=len(rows), skipped="fewer than 60 classified days")
            continue
        pairs = demean_by_month(rows)
        e2, p = perm_p(pairs)
        pvals[city] = p
        allv = [h for _, _, h in rows]
        per = {}
        for g in REGIMES:
            v = [h for _, gg, h in rows if gg == g]
            dv = [x for _, gg, x in pairs if gg == g]
            if not v:
                per[g] = dict(n=0)
                continue
            per[g] = dict(n=len(v), mean=round(sum(v) / len(v), 2),
                          sd=round(st.pstdev(v), 2) if len(v) > 1 else None,
                          vs_month=round(sum(dv) / len(dv), 2))
        tw = [(d, g, h) for d, g, h in rows if in_trading_window(d)]
        tw_per = {}
        for g in REGIMES:
            v = [h for _, gg, h in tw if gg == g]
            tw_per[g] = dict(n=len(v),
                             mean=round(sum(v) / len(v), 2) if v else None,
                             sd=round(st.pstdev(v), 2) if len(v) > 1 else None)
        stats[city] = dict(n=len(rows), eta_sq=round(e2, 4), p_perm=round(p, 4),
                           sd_pooled=round(st.pstdev(allv), 2),
                           sd_within_month=round(st.pstdev([x for _, _, x in pairs]), 2),
                           by_regime=per, trading_window=tw_per,
                           n_trading_window=len(tw),
                           n_2layer_disagree=blob.get("n_2layer_disagree"))
    surv = holm(pvals) if pvals else {}
    for c, s in stats.items():
        s["holm_survives"] = bool(surv.get(c, False))
    return stats, surv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", default=None, help="comma list, default all US cities")
    a = ap.parse_args()
    cities = ([c.strip().upper() for c in a.cities.split(",")] if a.cities
              else sorted(CITIES))
    bad = [c for c in cities if c not in CITIES]
    if bad:
        raise SystemExit(f"unknown cities: {bad}")

    print(f"building morning-sky regimes for {len(cities)} cities, "
          f"{YEARS[0]}-{YEARS[-1]}\n")
    built, disagree = build(cities)
    for c in built:
        built[c]["n_2layer_disagree"] = disagree.get(c, 0)
    io.open(OUT_JSON, "w", encoding="utf-8").write(json.dumps(built))
    print(f"\nwrote {OUT_JSON} "
          f"({sum(len(b['rows']) for b in built.values())} city-days)\n")

    stats, surv = report(built)

    print("PER-CITY REGIME SPLIT, month removed. eta^2 is the share of "
          "within-month\nvariance the regime explains; p is a within-month "
          "label permutation.\n")
    hdr = (f"{'city':<5}{'n':>6}{'sd_mo':>7}{'eta2':>7}{'p':>8}{'holm':>6}"
           f"{'NO_STRATUS':>13}{'EARLY_BURN':>13}{'LATE_BURN':>13}{'NO_BURN':>13}")
    print(hdr)
    print("-" * len(hdr))
    for c in sorted(stats, key=lambda k: -(stats[k].get("eta_sq") or -1)):
        s = stats[c]
        if s.get("skipped"):
            print(f"{c:<5}{s['n']:>6}   {s['skipped']}")
            continue
        g = s["by_regime"]
        cell = lambda k: (f"{g[k]['vs_month']:+.1f}/{g[k]['n']}" if g[k]["n"] else "-")
        print(f"{c:<5}{s['n']:>6}{s['sd_within_month']:>7.2f}{s['eta_sq']:>7.3f}"
              f"{s['p_perm']:>8.4f}{('YES' if s['holm_survives'] else 'no'):>6}"
              f"{cell('NO_STRATUS'):>13}{cell('EARLY_BURN'):>13}"
              f"{cell('LATE_BURN'):>13}{cell('NO_BURN'):>13}")
    print("\n  cells are (mean deviation from that month's mean, F) / (n days)")

    n_sig = sum(1 for c in stats if stats[c].get("holm_survives"))
    n_tested = sum(1 for c in stats if stats[c].get("p_perm") is not None)
    print(f"\n  {n_sig} of {n_tested} tested cities survive Holm-Bonferroni "
          f"at alpha={ALPHA}.")

    print("\n3-LAYER vs 2-LAYER ceiling read (lax_regime.py uses 2):")
    for c in sorted(built, key=lambda k: -built[k]["n_2layer_disagree"]):
        n = built[c]["n_2layer_disagree"]
        if n:
            print(f"  {c:<5}{n:>5} of {len(built[c]['rows']):>5} days reclassified")

    os.makedirs(os.path.dirname(OUT_SUMMARY), exist_ok=True)
    io.open(OUT_SUMMARY, "w", encoding="utf-8").write(json.dumps(dict(
        built_at=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        years=list(YEARS), stratus_ft=STRATUS_FT,
        windows=dict(dawn=list(WIN_DAWN), midmorn=list(WIN_MIDMORN),
                     earlypm=list(WIN_EARLYPM)),
        n_perm=N_PERM, alpha=ALPHA, cities=stats), indent=1))
    print(f"\nwrote {OUT_SUMMARY}")
    print("\n  A city surviving Holm is a WEATHER result -- the regime splits the "
          "high.\n  It is NOT an edge. H15's whole point is that a real weather "
          "signal can be\n  entirely inside the price, and the market was 3.2x "
          "better calibrated than\n  this class of model at KNYC/KDEN.")


if __name__ == "__main__":
    main()
