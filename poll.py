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
    for city, cfg in HOURLY.items():
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
            rung=bottom_rung(city)))
    return rows


def append(rows):
    if not rows:
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    day = dt.datetime.now(dt.timezone.utc).date().isoformat()
    with open(os.path.join(OUT_DIR, f"{day}.jsonl"), "a") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    rows = one_pass()
    n = append(rows)
    for r in rows:
        rung = r.get("rung") or {}
        print(f"  {r['city']}: print {r['last_print_f']}F @{r['last_print_at'][11:16]}Z "
              f"({r['stale_min']}m stale)  nowcast {r['nowcast_f']}F "
              f"(delta {r['nowcast_minus_print']:+}) lead {r['lead_min']}m  "
              f"rung {rung.get('cap')} no {rung.get('nb')}/{rung.get('na')}")
    print(f"  wrote {n} row(s) to {OUT_DIR}/")


if __name__ == "__main__":
    main()
