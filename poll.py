"""Dense price poller for H6 -- the two hourly settlement stations only.

WHY A SEPARATE POLLER. H6 claims the market prices off a stale print at KNYC and
KDEN. The effect lives inside a 40-minute window, and the main scan samples every
~55 minutes -- we would be sampling the market at the frequency of the thing we
claim is mispriced. This polls those two cities every few minutes instead.

WHY IT DOES NOT TOUCH THE SCAN. Cadence is load-bearing for H4a, whose pairing
band is 0.5-2.5h; compressing the main scan zeroes the day exactly as 2026-08-26
did. So this writes to logs/poll/<day>.jsonl -- a SUBDIRECTORY, which
glob("logs/2*.jsonl") does not match, so shape_eval, curve_lag and shadow.build
cannot see these rows even by accident. Nothing here feeds a ladder, a band, a
variant or the gate.

WHAT EACH ROW CAPTURES. Enough to answer H6 and nothing more: when we looked,
how stale the host print was, what the nowcast said, and both sides of the
bottom rung at that instant. The analysis then asks whether the price move
ACROSS a print correlates with (nowcast - last print) measured before it.
"""
import argparse
import datetime as dt
import json
import os
import statistics
from collections import Counter

from lowno import sources
from lowno.config import CITIES
from nowcast import HOURLY, C2F, at_or_before

OUT_DIR = "logs/poll"

# --- ISOLATED CITIES -- must NOT reach H6 -----------------------------------
# h6_eval.py globs logs/poll/*.jsonl with NO city filter, and H6 is registered
# as a POOLED verdict over exactly two cities: "both cities are hourly, that is
# why they are the only two polled", and "at ~1 print per city-hour over TWO
# CITIES the events leg is not binding; the 20 distinct days is". Dropping a
# third city into logs/poll/ would change a pre-declared population at 10/20
# distinct days and accelerate the events leg the bar was reasoned around.
#
# So these write to logs/poll_lax/, which glob("logs/poll/*.jsonl") does not
# match -- the same isolation poll.py already uses to stay invisible to
# glob("logs/2*.jsonl"). Nothing registered reads this directory. If H6 ever
# resolves and a successor wants three cities, that is a NEW registration.
#
# Defined HERE rather than in nowcast.HOURLY on purpose: HOURLY is imported by
# interp_curve, interp_wind and others, and adding LAX there would silently
# widen their populations too.
#
# LAX neighbours measured 2026-09-12 exactly as NYC's and DEN's were
# (interp_curve.py's method): r(host delta, mean-of-N neighbour delta) at
# 20-min lead, 14 days, n~2000. The whole curve, not a chosen N:
#     N=1 KHHR  0.302 | N=2 KSMO 0.379 | N=3 KLGB 0.378 | N=4 KBUR 0.395
#     N=5 KVNY  0.400 | N=6 KFUL 0.398 | N=7 KSNA 0.395 | N=10 KCMA 0.375
# A FLAT plateau N=4..7, peak 0.400. NYC reaches 0.710 on the same metric.
# LAX sits on a marine boundary its neighbours are on the wrong side of at
# different times, so nowcast_f here is MUCH weaker evidence than at NYC/DEN
# and must not be pooled with them.
ISOLATED = {
    "LAX": dict(station="KLAX", tz="America/Los_Angeles", out="logs/poll_lax",
                neighbours={"KHHR": "east", "KSMO": "north", "KLGB": "southeast",
                            "KBUR": "north", "KVNY": "north"}),
}


def recent(station, hours=6):
    """Latest observations for a station, newest first, as sorted (ts, degF)."""
    try:
        j = sources._get(
            f"https://api.weather.gov/stations/{station}/observations?limit=120",
            timeout=25)
    except Exception:
        return []
    out = {}
    cutoff = (dt.datetime.now(dt.timezone.utc)
              - dt.timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
    for f in j.get("features", []):
        p = f.get("properties") or {}
        t, v = p.get("timestamp"), (p.get("temperature") or {}).get("value")
        if t and v is not None and t[:16] + "Z" >= cutoff[:16] + "Z":
            out[t[:16] + "Z"] = round(C2F(v), 2)
    return sorted(out.items())


def print_minute(station):
    """Which minute past the hour this station publishes on, learned from the
    archive rather than hardcoded -- KNYC prints at :51, and assuming :00 would
    put every lead time 9 minutes out."""
    d = os.path.join("logs/nowcast", station)
    if not os.path.isdir(d):
        return None
    mins = Counter()
    for f in sorted(os.listdir(d))[-5:]:
        for ts in json.load(open(os.path.join(d, f))):
            mins[int(ts[14:16])] += 1
    return mins.most_common(1)[0][0] if mins else None


def bottom_rung(city):
    """The bottom rung of today's ladder, with both sides."""
    import datetime as _dt
    ymd = _dt.datetime.now(_dt.timezone.utc).strftime("%y%b%d").upper()
    try:
        rungs = sources.kalshi_ladder(CITIES[city]["series"], ymd,
                                      probe_path=None)
    except Exception as e:
        print(f"    {city}: ladder fetch failed ({str(e)[:50]})")
        return None
    for g in rungs or []:
        if g.get("floor") is None and g.get("cap") is not None:
            return dict(ticker=g.get("ticker"), cap=g.get("cap"),
                        na=g.get("no_ask"), nb=g.get("no_bid"),
                        ya=g.get("yes_ask"), yb=g.get("yes_bid"),
                        oi=g.get("oi"), vol=g.get("vol"))
    return None


def one_pass():
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    merged = [(c, cfg, OUT_DIR) for c, cfg in HOURLY.items()]
    merged += [(c, cfg, cfg["out"]) for c, cfg in ISOLATED.items()]
    for city, cfg, out_dir in merged:
        host = recent(cfg["station"])
        if not host:
            continue
        last_ts, last_v = host[-1]
        deltas = []
        for st in cfg["neighbours"]:
            s = recent(st)
            if not s:
                continue
            a = at_or_before(s, last_ts)
            b = s[-1]
            if a and b and b[0] > a[0]:
                deltas.append(b[1] - a[1])
        nc = round(last_v + statistics.fmean(deltas), 2) if deltas else None
        pm = print_minute(cfg["station"])
        # minutes until the next expected print, from the learned print minute
        lead = None
        if pm is not None:
            nxt = now.replace(minute=pm, second=0, microsecond=0)
            if nxt <= now:
                nxt += dt.timedelta(hours=1)
            lead = round((nxt - now).total_seconds() / 60)
        stale = round((now - dt.datetime.fromisoformat(
            last_ts.replace("Z", "+00:00"))).total_seconds() / 60)
        rows.append(dict(
            at=now.isoformat().replace("+00:00", "Z"), city=city,
            station=cfg["station"], last_print_at=last_ts, last_print_f=last_v,
            stale_min=stale, nowcast_f=nc,
            nowcast_minus_print=(round(nc - last_v, 2) if nc is not None else None),
            n_neighbours=len(deltas), lead_min=lead,
            rung=bottom_rung(city), _out=out_dir))
    return rows


def append(rows):
    """Route each row to its own directory and strip the routing tag.

    `_out` is popped before writing, so the on-disk schema is byte-identical to
    what logs/poll/ carried before ISOLATED existed -- h6_eval and anything else
    reading those rows sees no new field.
    """
    if not rows:
        return 0
    day = dt.datetime.now(dt.timezone.utc).date().isoformat()
    by_dir = {}
    for r in rows:
        by_dir.setdefault(r.pop("_out", OUT_DIR), []).append(r)
    for d, rs in by_dir.items():
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{day}.jsonl"), "a") as fh:
            for r in rs:
                fh.write(json.dumps(r) + chr(10))
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    rows = one_pass()
    n = append(rows)
    for r in rows:
        rung = r.get("rung") or {}
        # None-safe: a city with no neighbour archive yet (no logs/nowcast/<stn>)
        # has lead_min None, and a city whose neighbours all fail has nowcast
        # None. Neither is a reason to lose the row or crash the loop.
        d = r.get("nowcast_minus_print")
        print(f"  {r['city']}: print {r['last_print_f']}F @{r['last_print_at'][11:16]}Z "
              f"({r['stale_min']}m stale)  nowcast {r['nowcast_f']}F "
              f"(delta {('%+.2f' % d) if d is not None else '--'}) "
              f"lead {r['lead_min'] if r['lead_min'] is not None else '--'}m  "
              f"rung {rung.get('cap')} no {rung.get('nb')}/{rung.get('na')}")
    dirs = sorted({OUT_DIR} | {c["out"] for c in ISOLATED.values()})
    print(f"  wrote {n} row(s) to {', '.join(d + '/' for d in dirs)}")


if __name__ == "__main__":
    main()
