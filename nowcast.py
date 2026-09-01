"""Nowcast the next print of an HOURLY settlement station from 5-minute neighbours.

WHY THIS EXISTS. Two of the 23 settlement stations publish hourly -- KNYC and
KDEN -- while the other 21 publish every 4-5 minutes. Measured 2026-08-31 at
17:35Z: KNYC's most recent observation was 16:51Z, 44 minutes stale, while KLGA
(13km east) and KEWR (16km west) were current. The station the market settles on
is the slow one, and its next print is partly knowable before it appears.

MECHANISM, stated before testing. Central Park sits between KLGA on Flushing Bay
to the east and KEWR/KTEB in New Jersey to the west. An onshore easterly cools
LGA first and reaches Manhattan later, leaving the western stations warm. So the
EAST-WEST gradient is a directional front detector, not a spatial average, and
its movement should lead KNYC. Denver has no sea breeze; its single 5-minute
neighbour (KAPA) reflects upslope/downslope flow instead, which is different
physics -- the two stations are reported separately and MUST NOT be pooled.

THE ESTIMATOR HAS NO FITTED PARAMETERS. Predicted next print =
last print + the MEAN change of the neighbours over the same interval. No
weights, no regression, nothing to tune later. If a parameter-free estimator
cannot beat persistence, a fitted one beating it would be a fitting result.

BACKTEST WINDOW. api.weather.gov serves observations for about 7 days, the same
window as CLI. So the backtest is 7 days today. Every run archives what it
fetched under logs/nowcast/, so the window GROWS instead of rolling -- run it
daily and the sample accumulates.

This is an INFORMATION claim only. It measures whether the next print is
predictable. Whether that predictability is tradeable is a separate question
that has to be registered before it is scored -- see CANDIDATE.md.
"""
import argparse
import datetime as dt
import json
import math
import os
import statistics
from collections import defaultdict

from lowno import sources

ARCHIVE = "logs/nowcast"

# Verified 2026-08-31: cadence checked live, only these two settlement stations
# publish hourly. Neighbours are the 5-minute stations around each, tagged with
# the side they sit on so the gradient can be built.
HOURLY = {
    # Neighbour sets are the MEASURED optimum from interp_curve.py, which scores
    # the delta correlation as a function of how many 5-minute stations are
    # averaged, sorted by distance. Two findings drove this:
    #
    #   * Wind-direction weighting made it WORSE at every city and lead
    #     (NYC r 0.728 -> 0.682). Upwind weighting discards neighbours, and
    #     against 1-degree-C quantized predictors the noise reduction lost
    #     exceeds the physical routing gained. Averaging is the mechanism.
    #   * So averaging MORE helps -- but the optimum is per-city, not universal.
    #
    # NYC plateaus by ~38km: r@20m runs 0.531 / 0.626 / 0.680 / 0.705 / 0.710
    # for N=1..5, then FALLS away as 68km+ stations are added. The Atlantic and
    # the urban heat island make distant stations poor proxies.
    #
    # DEN never plateaus in range: r@20m climbs monotonically 0.466 -> 0.731
    # out to KPUB at 174km. Plains airmass is spatially coherent, so every extra
    # station still buys noise reduction.
    #
    # Both shapes are broad, not spikes, which is why an N is picked at all.
    # Re-check as the archive grows -- this is 7 days.
    "NYC": dict(station="KNYC", tz="America/New_York",
                neighbours={"KLGA": "east", "KTEB": "west", "KEWR": "west",
                            "KCDW": "west", "KHPN": "north"}),
    "DEN": dict(station="KDEN", tz="America/Denver",
                neighbours={"KAPA": "south", "KEIK": "north", "KBDU": "northwest",
                            "KLMO": "north", "KGXY": "northeast", "KFNL": "north",
                            "KLIC": "east", "KCOS": "south", "KAKO": "east",
                            "KPUB": "south"}),
}

C2F = lambda c: None if c is None else c * 9 / 5 + 32


def fetch(station, start, end):
    """Observations in [start, end), newest first. Chunked by day: the API caps
    a single response and silently truncates rather than paginating."""
    out = {}
    cur = start
    while cur < end:
        nxt = min(cur + dt.timedelta(days=1), end)
        u = (f"https://api.weather.gov/stations/{station}/observations"
             f"?start={cur.isoformat().replace('+00:00','Z')}"
             f"&end={nxt.isoformat().replace('+00:00','Z')}&limit=500")
        try:
            j = sources._get(u, timeout=45)
        except Exception as e:
            print(f"    {station} {cur:%m-%d}: fetch failed ({str(e)[:40]})")
            cur = nxt
            continue
        for f in j.get("features", []):
            p = f.get("properties") or {}
            t = p.get("timestamp")
            v = (p.get("temperature") or {}).get("value")
            if t and v is not None:
                # Wind, pressure and precipitation ride along so a
                # wind-direction hypothesis can be tested at all. Temperature
                # alone cannot distinguish an upwind neighbour from a downwind
                # one, and that is the first thing worth trying.
                g = lambda k: (p.get(k) or {}).get("value")
                # SKY added 2026-09-01. The cloud question -- does a deck over a
                # neighbour but not the host degrade its delta -- was untestable
                # because only wind/pressure/precip were stored. Kept compact:
                # the most-covering layer and its base, since base height is what
                # mattered at the host (BKN mid/high behaved like clear, only OVC
                # low separated). Older rows have no `sky`; consumers must cope.
                RANK = {"CLR": 0, "SKC": 0, "FEW": 1, "SCT": 2, "BKN": 3, "OVC": 4}
                worst, wbase = None, None
                for lay in (p.get("cloudLayers") or []):
                    amt = lay.get("amount")
                    if amt is None:
                        continue
                    if worst is None or RANK.get(amt, 0) > RANK.get(worst, 0):
                        worst = amt
                        wbase = (lay.get("base") or {}).get("value")
                out[t[:16] + "Z"] = dict(
                    t=round(C2F(v), 2),
                    wd=g("windDirection"),
                    ws=g("windSpeed"),
                    pa=g("barometricPressure"),
                    pr=g("precipitationLastHour"),
                    sky=worst,
                    sky_base_m=wbase)
        cur = nxt
    return out


def temp_of(rec):
    """Archive rows are floats in files written before 2026-08-31 and dicts
    after. One accessor so no caller has to know which."""
    return rec if isinstance(rec, (int, float)) else (rec or {}).get("t")


def field_of(rec, key):
    return None if isinstance(rec, (int, float)) else (rec or {}).get(key)


def archive_path(station, day):
    return os.path.join(ARCHIVE, station, f"{day}.json")


def load_or_fetch(station, days):
    """Archive-first. Only days we have never stored are fetched, so the record
    outlives the API's 7-day window."""
    series = {}
    for day in days:
        p = archive_path(station, day)
        if os.path.exists(p):
            series.update(json.load(open(p)))
            continue
        d0 = dt.datetime.fromisoformat(day + "T00:00:00+00:00")
        got = fetch(station, d0, d0 + dt.timedelta(days=1))
        if got:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            json.dump(got, open(p, "w"), sort_keys=True)
            series.update(got)
            print(f"    archived {station} {day}: {len(got)} obs")
    return series


def at_or_before(series_sorted, ts):
    """Latest observation at or before ts. Returns (timestamp, value) or None."""
    lo, hi, best = 0, len(series_sorted) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if series_sorted[mid][0] <= ts:
            best = series_sorted[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def backtest(city, days, leads=(10, 20, 30, 40, 50)):
    cfg = HOURLY[city]
    print(f"\n{'='*74}\n{city} ({cfg['station']}) -- hourly settlement station")
    host = load_or_fetch(cfg["station"], days)
    nbrs = {st: load_or_fetch(st, days) for st in cfg["neighbours"]}
    hs = [(k, temp_of(v)) for k, v in sorted(host.items()) if temp_of(v) is not None]
    ns = {st: [(k, temp_of(v)) for k, v in sorted(sr.items()) if temp_of(v) is not None]
          for st, sr in nbrs.items()}
    print(f"  host prints: {len(hs)}   neighbours: "
          + ", ".join(f"{st}={len(v)}" for st, v in ns.items()))
    if len(hs) < 10:
        print("  not enough host prints to score")
        return

    rows = defaultdict(list)
    gaps = []
    for i in range(1, len(hs)):
        t0, v0 = hs[i - 1]
        t1, v1 = hs[i]
        d0 = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        d1 = dt.datetime.fromisoformat(t1.replace("Z", "+00:00"))
        gap = (d1 - d0).total_seconds() / 60
        if not (40 <= gap <= 80):
            continue                      # consecutive hourly prints only
        gaps.append(gap)
        for L in leads:
            cut = (d1 - dt.timedelta(minutes=L)).isoformat().replace("+00:00", "Z")[:16] + "Z"
            deltas = []
            for st, s in ns.items():
                a = at_or_before(s, t0)
                b = at_or_before(s, cut)
                if not a or not b or b[0] <= a[0]:
                    continue
                deltas.append(b[1] - a[1])
            if not deltas:
                continue
            rows[L].append((abs(v0 - v1),                       # persistence error
                            abs((v0 + statistics.fmean(deltas)) - v1)))  # nowcast error
    if gaps:
        print(f"  usable transitions: {len(gaps)}  (median gap {statistics.median(gaps):.0f} min)")
    print(f"\n  {'lead':>6}{'n':>6}{'persistence MAE':>18}{'nowcast MAE':>14}"
          f"{'improvement':>13}")
    for L in leads:
        v = rows.get(L) or []
        if len(v) < 10:
            continue
        pm = statistics.fmean(x for x, _ in v)
        nm = statistics.fmean(y for _, y in v)
        # paired difference, so the CI accounts for the shared weather
        diffs = [x - y for x, y in v]
        se = statistics.stdev(diffs) / math.sqrt(len(diffs)) if len(diffs) > 1 else 0
        star = "  significant" if (statistics.fmean(diffs) - 1.96 * se) > 0 else ""
        print(f"  {L:>4}m{len(v):>6}{pm:>17.2f}F{nm:>13.2f}F"
              f"{100*(pm-nm)/pm:>12.0f}%{star}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7,
                    help="how far back to look; the API only serves ~7")
    a = ap.parse_args()
    today = dt.datetime.now(dt.timezone.utc).date()
    days = [(today - dt.timedelta(days=i)).isoformat() for i in range(a.days, 0, -1)]
    print(f"nowcast backtest over {days[0]} .. {days[-1]}")
    print(f"archive: {ARCHIVE}/ (fetched days are stored so the window grows)")
    for city in HOURLY:
        backtest(city, days)
    print("\nInformation claim only. Tradeability is a separate, registered question.")


if __name__ == "__main__":
    main()
