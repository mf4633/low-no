"""FROZEN 2026-09-12. The regime-conditioned CLI forecast for KLAX.

Frozen the same night as lax_regime.py and BEFORE any LAX orderbook exists
(logs/poll_lax/ held 1 row when this was written). H15's second leg is "a
regime-conditioned model beats the market on marine strata" -- a model fitted
after watching books would be fitted to the prices it is meant to be tested
against, and that leg would be worthless. So the conditioning is set here and
DOES NOT MOVE.

METHOD, deliberately simple. The H4a failure says fine cells cost more Brier
than they pay, so this does not split further than it must:

  1. regime from lax_regime.regime(), decided by 17Z from KLAX sky groups only
  2. historical days matching that regime AND within +/-21 days of the same
     day-of-year, any year -- a seasonal window, not a month, so there is no
     month-boundary artifact
  3. the EMPIRICAL distribution of their CLI highs, not a fitted Gaussian:
     LAX highs are not normal, which is why the frozen gate excludes marine
     stations from the trading rule in the first place
  4. no further conditioning. Not on morning temperature, not on SST, not on
     inversion strength. Each would be defensible and each is a cell split.

WHAT IT RETURNS. P(CLI high = k) for integer k. The CLI IS the quantity the
market settles, so no separate settlement offset is applied -- the historical
values here are already CLI highs, not METAR maxima.
"""
import io, json, os, datetime as dt
from collections import Counter

# Progressive widening, NOT a year-round fallback. A thin seasonal cell used to
# drop to the all-year pool, which put January days into a September forecast:
# NO_BURN pooled year-round is 66.2F while its September value is 71.7F, so the
# broken fallback forecast 5F cold on exactly the regime H15 tests. Widening the
# seasonal window keeps the season; pooling the year does not.
WINDOWS = (21, 35, 50, 75)   # +/- day-of-year, tried in order. FROZEN.
WINDOW_DAYS = WINDOWS[0]     # kept for the header line
MIN_N = 25                # below this the regime cell is not trusted. FROZEN.
REGIMES = ("NO_STRATUS", "EARLY_BURN", "LATE_BURN", "NO_BURN")
MARINE = ("LATE_BURN", "NO_BURN")     # H15's test strata. FROZEN.


def _load(path="lax_regimes.json"):
    """[(day, regime, cli_high), ...] built by lax_regime.py."""
    if not os.path.exists(path):
        raise SystemExit(f"{path} missing -- run lax_regime.py first")
    return json.loads(io.open(path, encoding="utf-8").read())


def _doy(d):
    return dt.date(int(d[:4]), int(d[5:7]), int(d[8:10])).timetuple().tm_yday


def _near(a, b, span=366):
    """Circular day-of-year distance."""
    return min(abs(a - b), span - abs(a - b))


def forecast(regime, day, rows=None):
    """Empirical P(CLI high = k) for `regime` on calendar date `day`.

    Returns dict(n=, dist={k: p}, mean=, source=) or n=0 if the cell is thin.
    """
    rows = rows if rows is not None else _load()
    d0 = _doy(day)
    sel, src = [], None
    for w in WINDOWS:
        sel = [h for dd, g, h in rows
               if g == regime and _near(_doy(dd), d0) <= w]
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


if __name__ == "__main__":
    rows = _load()
    today = dt.date.today().isoformat()
    print(f"frozen LAX forecast, cells for {today} (+/-{WINDOW_DAYS}d):\n")
    print(f"{'regime':<12}{'n':>5}{'mean':>8}{'p10':>7}{'p50':>7}{'p90':>7}   source")
    for g in REGIMES:
        f = forecast(g, today, rows)
        if not f["n"]:
            print(f"{g:<12}{0:>5}   empty")
            continue
        ks = sorted(f["dist"])
        cum, q = 0.0, {}
        for k in ks:
            cum += f["dist"][k]
            for t in (0.10, 0.50, 0.90):
                if t not in q and cum >= t:
                    q[t] = k
        print(f"{g:<12}{f['n']:>5}{f['mean']:>8.1f}"
              f"{q.get(0.10,'-'):>7}{q.get(0.50,'-'):>7}{q.get(0.90,'-'):>7}   {f['source']}")
    print(f"\n  MARINE strata (H15's test set): {', '.join(MARINE)}")
