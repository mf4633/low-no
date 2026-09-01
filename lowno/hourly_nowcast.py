"""run_max correction for the two settlement stations that publish hourly.

KNYC and KDEN print once an hour; the other 21 stations print every 4-5 minutes.
So at those two, `run_max` is a max over hourly samples and misses whatever
happened between them. Measured against CLI over 7 days, our max runs about a
degree low: +1.16F at NYC, +1.01F at DEN. Since `needed = cap - run_max` feeds
every p_exceed, that biases the model's probability DOWN at exactly those two
stations -- we have been under-rating NO there for the whole record.

Consulting the neighbours at each scan cuts the error to 0.73F and 0.78F.

GRANULARITY IS THE TRICK. An earlier version reconstructed the between-print
temperature at every neighbour tick -- ~280 a day -- and took the max. A max
over noisy estimates selects the largest error, and it overshot CLI by 3F.
Consulting the nowcast once per scan is ~11 draws a day and behaves.

TELEMETRY ONLY. This writes `run_max_nowcast` alongside `run_max` and changes
NOTHING that makes a decision.

--------------------------------------------------------------------------
HARDENING (2026-09-01). Stations drop out, and the first version handled it
badly in a way that was silently WRONG rather than merely fragile.

Each neighbour's delta was measured from the host's last print to THAT
NEIGHBOUR'S latest observation. Observed live at 15:08Z: KBDU's latest was
13:55Z and KPUB's was 14:50Z, against a host print at 13:53Z -- so KBDU
contributed a 2-MINUTE delta and KPUB a 57-MINUTE delta, and the two were
averaged as though they measured the same thing. Every stale neighbour drags
the estimate toward zero change, which biases the nowcast DOWN exactly when
the day is moving.

Four defences, each with its threshold derived rather than chosen:

  ALIGNED WINDOW   every surviving neighbour is evaluated at one common target
                   time, so all deltas cover the same interval. No exceptions:
                   a neighbour that cannot reach the target is dropped, not
                   included with a shorter window.
  FRESHNESS        a backstop only, and calibrated to observed API LAG rather
                   than to the reporting interval -- see MAX_NEIGHBOUR_AGE_MIN.
  QUORUM           below MIN_NEIGHBOURS the averaging that does the work is
                   gone; the interpolator's whole measured advantage came from
                   averaging (wind weighting made it worse), so a thin
                   ensemble is reported as degraded rather than dressed up.
  HOST SANITY      the host prints hourly; if its last print is over 2 hours
                   old something is broken upstream and extrapolating that far
                   is not a nowcast.

Every return carries `quality` and the numbers behind it, so a consumer can
filter instead of trusting a bare float.

EXTRAPOLATION WAS TESTED AND REJECTED (stale_test.py, 2026-09-01). The obvious
refinement is to project a stale neighbour forward from its own recent rate
rather than dropping it, weighted by how stale it is. Simulated on the archive,
where complete 5-minute data lets staleness be imposed exactly so every
strategy sees identical inputs:

    DEN, 60% of neighbours stale by 30 min
      perfect 1.80   drop 1.82   naive 2.02   extrap 1.93   extrap+conf 1.85

DROPPING COSTS 0.02-0.03F against perfect data even with 60% of the ensemble
gone, so there is almost nothing available to recover -- the neighbours are
near-exchangeable and the survivors already carry the signal. Extrapolation is
a hair better at 15 minutes (inside noise), WORSE at 30, and identical past 45
where no rate history remains to project from. Do not add it.

The same test confirms the alignment fix was worth making: `naive`, the
original behaviour of treating a stale value as current, degrades to 2.02F
where dropping holds 1.82F.
"""
import datetime as dt
import statistics

from . import sources

HOSTS = {
    "NYC": ("KNYC", ["KLGA", "KTEB", "KEWR", "KCDW", "KHPN"]),
    "DEN": ("KDEN", ["KAPA", "KEIK", "KBDU", "KLMO", "KGXY", "KFNL",
                     "KLIC", "KCOS", "KAKO", "KPUB"]),
}
C2F = lambda c: None if c is None else c * 9 / 5 + 32

# Derived from observed API LAG, not from the stations' reporting interval.
# Measured 2026-09-01 15:08Z: neighbours publishing every 4-5 minutes surfaced
# in the API 10-25 minutes behind, and KDEN's own 08:53 print had not appeared
# at 09:08. A 20-minute cut therefore rejected all ten DEN neighbours during
# normal operation -- a false alarm that would have zeroed the station. 45 is
# about twice the observed lag: still catches a station that has genuinely gone
# quiet for nine-plus cycles, without mistaking latency for silence.
#
# This is a backstop, not the main defence. ALIGNMENT is what fixes the bug --
# a laggy neighbour is harmless once every delta spans the same window.
MAX_NEIGHBOUR_AGE_MIN = 45
MIN_NEIGHBOURS = 3             # below this the averaging is gone
MAX_HOST_AGE_MIN = 120         # an hourly station two prints behind is broken
MIN_WINDOW_MIN = 5             # a shorter window is noise, not tendency


def _series(station, limit=60):
    """[(timestamp, degF)] oldest first, or [] on any failure."""
    try:
        j = sources._get(
            f"https://api.weather.gov/stations/{station}/observations?limit={limit}",
            timeout=20)
    except Exception:
        return []
    out = {}
    for f in j.get("features", []):
        p = f.get("properties") or {}
        t = p.get("timestamp")
        v = (p.get("temperature") or {}).get("value")
        if t and v is not None:
            out[t[:16] + "Z"] = round(C2F(v), 2)
    return sorted(out.items())


def _age_min(ts, now):
    return (now - dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds() / 60.0


def _at_or_before(series, ts):
    best = None
    for t, v in series:
        if t <= ts:
            best = (t, v)
        else:
            break
    return best


def estimate(city, run_max, now=None):
    """(run_max_nowcast, detail) or (None, reason-string).

    Never returns a value below run_max or below the host's last print: this can
    only reveal a peak the hourly sampling missed, never erase one it caught.
    """
    if city not in HOSTS:
        return None, "not an hourly station"
    now = now or dt.datetime.now(dt.timezone.utc)
    host, nbrs = HOSTS[city]

    hs = _series(host)
    if not hs:
        return None, "no host observations"
    last_ts, last_v = hs[-1]
    host_age = _age_min(last_ts, now)
    if host_age > MAX_HOST_AGE_MIN:
        return None, f"host print {host_age:.0f}min old (>{MAX_HOST_AGE_MIN})"

    # Gather only neighbours that are FRESH and have moved past the host print.
    fresh, dropped = {}, {}
    for st in nbrs:
        s = _series(st)
        if not s:
            dropped[st] = "no data"
            continue
        age = _age_min(s[-1][0], now)
        if age > MAX_NEIGHBOUR_AGE_MIN:
            dropped[st] = f"stale {age:.0f}min"
            continue
        if s[-1][0] <= last_ts:
            dropped[st] = "no obs after host print"
            continue
        fresh[st] = s

    if len(fresh) < MIN_NEIGHBOURS:
        return None, (f"quorum: {len(fresh)} fresh neighbour(s) < {MIN_NEIGHBOURS} "
                      f"({'; '.join(f'{k}:{v}' for k, v in dropped.items())})")

    # ALIGN: one common target time. Taking the EARLIEST latest-observation
    # keeps every neighbour but lets the laggiest one cap the window for all of
    # them -- measured 2026-09-01 15:24Z, three DEN neighbours sat at 14:55Z
    # while seven were current at 15:10Z, so the target collapsed to a
    # 2-MINUTE window and the whole station was refused.
    #
    # A 2-minute window measures no movement, and dropping neighbours is cheap:
    # stale_test.py puts the cost of losing 60% of the ensemble at 0.02-0.03F.
    # So choose the LATEST target that still satisfies quorum, trading a few
    # laggards for a window long enough to carry a tendency. Parameter-free
    # given MIN_NEIGHBOURS.
    cands = sorted({s[-1][0] for s in fresh.values()}, reverse=True)
    target = None
    for cand in cands:
        keep = sum(1 for s in fresh.values() if s[-1][0] >= cand)
        w = _age_min(last_ts, dt.datetime.fromisoformat(cand.replace("Z", "+00:00")))
        if keep >= MIN_NEIGHBOURS and w >= MIN_WINDOW_MIN:
            target = cand
            break
    if target is None:
        best = _age_min(last_ts, dt.datetime.fromisoformat(cands[0].replace("Z", "+00:00")))
        return None, (f"no target with >={MIN_NEIGHBOURS} neighbours and a "
                      f">={MIN_WINDOW_MIN}min window (best {best:.0f}min)")
    window = _age_min(last_ts, dt.datetime.fromisoformat(target.replace("Z", "+00:00")))
    for st, s in list(fresh.items()):
        if s[-1][0] < target:
            dropped[st] = f"behind target by {_age_min(s[-1][0], dt.datetime.fromisoformat(target.replace('Z','+00:00'))):.0f}min"
            del fresh[st]

    deltas, used = [], []
    for st, s in fresh.items():
        a = _at_or_before(s, last_ts)
        b = _at_or_before(s, target)
        if not a or not b or b[0] <= a[0]:
            dropped[st] = "no aligned pair"
            continue
        deltas.append(b[1] - a[1])
        used.append(st)
    if len(deltas) < MIN_NEIGHBOURS:
        return None, f"quorum after alignment: {len(deltas)} < {MIN_NEIGHBOURS}"

    mean_d = statistics.fmean(deltas)
    nc = round(last_v + mean_d, 2)
    out = max([x for x in (run_max, nc, last_v) if x is not None])
    quality = ("full" if len(deltas) == len(nbrs)
               else "reduced" if len(deltas) >= max(MIN_NEIGHBOURS, len(nbrs) // 2)
               else "degraded")
    return round(out, 2), dict(
        nowcast_f=nc, last_print_f=last_v, last_print_at=last_ts,
        stale_min=round(host_age), n_neighbours=len(deltas),
        n_expected=len(nbrs), quality=quality,
        # The estimate is AS OF the aligned target, which trails real time by
        # the API lag. Reporting it as the current temperature is wrong, and I
        # did exactly that until Michael caught it. Do NOT project it forward:
        # project_test.py shows a linear carry nearly DOUBLES the NYC error at
        # a 50-minute distance (1.07 -> 2.07F) and loses at every lead, because
        # the rate comes from a short variable window and a warming curve
        # decelerates. Flat is the best estimate; only the LABEL needed fixing.
        as_of=target, age_of_estimate_min=round(_age_min(target, now)),
        window_min=round(window), aligned_to=target,
        spread_f=(round(statistics.pstdev(deltas), 2) if len(deltas) > 1 else 0.0),
        dropped=dropped or None)
