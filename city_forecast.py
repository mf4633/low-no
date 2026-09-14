r"""Regime-conditioned empirical CLI-high forecast for every US Kalshi city.

`lax_forecast.py` is the single-station original and is FROZEN -- it carries
H15 and this file does not import, modify or supersede it. This is the same
method keyed by city, reading `city_regimes.json` (built by `city_regime.py`).

METHOD, deliberately identical to lax_forecast.py so the two are comparable and
so no new tuning knob enters by the back door:

  1. regime from city_regime.regime(), morning-and-early-afternoon sky only
  2. historical days of the SAME city matching that regime AND within a
     seasonal day-of-year window -- widened progressively only when the cell is
     thin, never pooled across the year (pooling January into September is what
     made an early LAX build forecast 5F cold on exactly the regime under test)
  3. the EMPIRICAL distribution of their CLI highs, not a fitted Gaussian
  4. no further conditioning. Not on morning temperature, not on the guide, not
     on the airmass. Each would be defensible and each is a cell split, and
     H4a's failure is the standing evidence that fine cells cost more Brier
     than they pay.

WHAT IT RETURNS. P(CLI high = k) for integer k. The CLI IS the settled
quantity, so no settlement offset is applied -- the historical values are
already CLI highs, not METAR maxima. (This is also why the degC-quantisation
artefact of gotcha 13 does not enter here: `run_max` is not in this path.)

WHAT IT IS NOT. Not a signal, not a gate input, not a variant. A conditional
distribution is a measurement. The market was 3.2x better calibrated than this
class of model at KNYC/KDEN, and trading its disagreements lost 5.8-6.7c per
trade at every margin tested. Anything that turns this into a position is a
separate registration with its own units and its own Wilson bar.

Usage:  python city_forecast.py                 (today's cells, all cities)
        python city_forecast.py --city SEA --day 2026-09-20
"""
import argparse
import datetime as dt
import io
import json
import os
from collections import Counter

# FROZEN, copied from lax_forecast.py rather than imported, so that a later
# change to H15's frozen file cannot silently move this one (or the reverse).
WINDOWS = (21, 35, 50, 75)    # +/- day-of-year, tried in order
WINDOW_DAYS = WINDOWS[0]
MIN_N = 25                    # below this the regime cell is not trusted
REGIMES = ("NO_STRATUS", "EARLY_BURN", "LATE_BURN", "NO_BURN")
MARINE = ("LATE_BURN", "NO_BURN")   # the strata where stratus survived the morning

DEFAULT_PATH = "city_regimes.json"


def load(path=DEFAULT_PATH):
    if not os.path.exists(path):
        raise SystemExit(f"{path} missing -- run city_regime.py first")
    return json.loads(io.open(path, encoding="utf-8").read())


def _doy(d):
    return dt.date(int(d[:4]), int(d[5:7]), int(d[8:10])).timetuple().tm_yday


def _near(a, b, span=366):
    """Circular day-of-year distance."""
    return min(abs(a - b), span - abs(a - b))


def forecast(city, regime, day, blob=None):
    """Empirical P(CLI high = k) for `city` in `regime` on calendar date `day`.

    Returns dict(n=, dist={k: p}, mean=, source=), n=0 when the city is absent.
    """
    blob = blob if blob is not None else load()
    if city not in blob:
        return dict(n=0, dist={}, mean=None, source="city not built")
    rows = [tuple(r) for r in blob[city]["rows"]]
    d0 = _doy(day)
    sel, src = [], None
    for w in WINDOWS:
        sel = [h for dd, g, h in rows if g == regime and _near(_doy(dd), d0) <= w]
        src = f"regime x +/-{w}d"
        if len(sel) >= MIN_N:
            break
    else:
        src += " (STILL THIN -- widest window)"
    if not sel:
        return dict(n=0, dist={}, mean=None, source="empty")
    c = Counter(int(round(h)) for h in sel)
    n = len(sel)
    return dict(n=n, dist={k: v / n for k, v in sorted(c.items())},
                mean=sum(sel) / n, source=src)


def p_at_or_above(dist, k):
    return sum(p for kk, p in dist.items() if kk >= k)


def p_at_or_below(dist, k):
    return sum(p for kk, p in dist.items() if kk <= k)


def p_exceeds(dist, cap):
    """P(daily high > cap) -- the quantity a bottom-rung NO position pays on.

    Spelled out because this is the exact place the project has inverted itself
    before (CLAUDE.md, THE WIN CONDITION): buying NO on a `<= cap` bucket wins
    when the day runs HOTTER than cap, not cooler.
    """
    return sum(p for k, p in dist.items() if k > cap)


def quantiles(dist, ts=(0.10, 0.50, 0.90)):
    cum, q = 0.0, {}
    for k in sorted(dist):
        cum += dist[k]
        for t in ts:
            if t not in q and cum >= t:
                q[t] = k
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=None, help="one city, default all")
    ap.add_argument("--day", default=None, help="YYYY-MM-DD, default today")
    ap.add_argument("--path", default=DEFAULT_PATH)
    a = ap.parse_args()
    blob = load(a.path)
    day = a.day or dt.date.today().isoformat()
    cities = [a.city.upper()] if a.city else sorted(blob)

    print(f"regime-conditioned CLI-high cells for {day} "
          f"(seasonal window +/-{WINDOW_DAYS}d, widened when thin)\n")
    hdr = f"{'city':<6}{'regime':<12}{'n':>5}{'mean':>8}{'p10':>6}{'p50':>6}{'p90':>6}   source"
    print(hdr)
    print("-" * len(hdr))
    for city in cities:
        for g in REGIMES:
            f = forecast(city, g, day, blob)
            if not f["n"]:
                print(f"{city:<6}{g:<12}{0:>5}   {f['source']}")
                continue
            q = quantiles(f["dist"])
            print(f"{city:<6}{g:<12}{f['n']:>5}{f['mean']:>8.1f}"
                  f"{q.get(0.10,'-'):>6}{q.get(0.50,'-'):>6}{q.get(0.90,'-'):>6}"
                  f"   {f['source']}")
        print()
    print("  A cell is a measurement, not a signal. See the module docstring.")


if __name__ == "__main__":
    main()
