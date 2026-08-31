"""run_max correction for the two settlement stations that publish hourly.

KNYC and KDEN print once an hour; the other 21 stations print every 4-5 minutes.
So at those two, `run_max` is a max over hourly samples and misses whatever
happened between them. Measured against CLI over 7 days, our max runs about a
degree low: +1.16F at NYC, +1.01F at DEN. Since `needed = cap - run_max` feeds
every p_exceed, that biases the model's probability DOWN at exactly those two
stations -- we have been under-rating NO there for the whole record.

Consulting the neighbours at each scan cuts the error to 0.73F and 0.78F, a 37%
and 23% reduction, without swapping the bias for an overshoot (2 of 12 days go
negative, both by less than a degree).

GRANULARITY IS THE WHOLE TRICK. An earlier version reconstructed the
between-print temperature at every neighbour tick -- ~280 a day -- and took the
max. A max over noisy estimates selects the largest error, and it overshot CLI
by 3F. Consulting the nowcast once per scan is ~11 draws a day and behaves.

TELEMETRY ONLY. This writes `run_max_nowcast` alongside `run_max` and changes
NOTHING that makes a decision. Applying it to p_exceed would rewrite every
historical NYC/DEN probability mid-measurement, which is the thing shadow.build
refuses to do for the cap fix, and n=5 and n=7 days is far too thin to justify
it. When the archive is large enough it gets a dated cutoff like cap_fix_since,
and history is left alone.
"""
import datetime as dt
import statistics

from . import sources

# The hourly hosts and the 5-minute neighbours found best by interp_curve.py.
# NYC plateaus by ~38km; DEN keeps improving out to 174km. Kept in step with
# nowcast.py -- if that file's HOURLY changes, change this.
HOSTS = {
    "NYC": ("KNYC", ["KLGA", "KTEB", "KEWR", "KCDW", "KHPN"]),
    "DEN": ("KDEN", ["KAPA", "KEIK", "KBDU", "KLMO", "KGXY", "KFNL",
                     "KLIC", "KCOS", "KAKO", "KPUB"]),
}
C2F = lambda c: None if c is None else c * 9 / 5 + 32


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


def estimate(city, run_max):
    """(run_max_nowcast, detail) or (None, reason) when it cannot be computed.

    Never returns a value BELOW run_max: this can only reveal a peak the hourly
    sampling missed, never erase one it caught.
    """
    if city not in HOSTS:
        return None, "not an hourly station"
    host, nbrs = HOSTS[city]
    hs = _series(host)
    if not hs:
        return None, "no host observations"
    last_ts, last_v = hs[-1]
    stale = (dt.datetime.now(dt.timezone.utc)
             - dt.datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
             ).total_seconds() / 60.0
    deltas = []
    for st in nbrs:
        s = _series(st)
        if not s:
            continue
        base = None
        for ts, v in s:
            if ts <= last_ts:
                base = v
        if base is not None and s[-1][0] > last_ts:
            deltas.append(s[-1][1] - base)
    if not deltas:
        return None, "no neighbour deltas"
    nc = round(last_v + statistics.fmean(deltas), 2)
    # Floor at BOTH the incoming run_max and the last print. The nowcast can
    # only ever reveal a peak the hourly sampling missed; it must never pull the
    # running max down, and a neighbour set that happens to have cooled would do
    # exactly that if last_v were not in the max.
    out = max([x for x in (run_max, nc, last_v) if x is not None])
    return round(out, 2), dict(nowcast_f=nc, last_print_f=last_v,
                               last_print_at=last_ts, stale_min=round(stale),
                               n_neighbours=len(deltas))
