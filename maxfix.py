"""Does the nowcast recover the peaks an hourly station hides?

THE CLAIM THIS TESTS. A NO position wins when the settled max EXCEEDS the cap,
so what matters is the running max, not the current temperature. At KNYC and
KDEN the host publishes hourly, so our running max is a max over hourly prints
and misses anything that happened between them. CLI reports the station's true
daily max. If that is the story, CLI - our observed max should be biggest at
exactly these two stations, and reconstructing the between-print temperature
from 5-minute neighbours should close the gap.

If it does, the advantage at NYC and DEN is NOT primarily about entry timing.
It is that our probability of winning is biased LOW at those two stations, and
correcting it is an information claim testable with no market data at all.

Baselines, in order of ambition:
  hourly max        max of the host's own prints             (what we do now)
  + nowcast         max of (last print + mean neighbour delta) at every
                    neighbour timestamp between prints        (parameter-free)
"""
import datetime as dt
import json
import os
import statistics
from collections import defaultdict

from nowcast import HOURLY, ARCHIVE, at_or_before


def load(station):
    d = os.path.join(ARCHIVE, station)
    out = {}
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            out.update(json.load(open(os.path.join(d, f))))
    return out


def local_day(ts, tzname):
    import zoneinfo
    return (dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            .astimezone(zoneinfo.ZoneInfo(tzname)).date().isoformat())


def main():
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    print(f"{'city':5}{'day':12}{'CLI':>6}{'hourly max':>12}{'+nowcast':>10}"
          f"{'gap now':>9}{'gap fixed':>11}")
    agg = defaultdict(lambda: ([], []))
    for city, cfg in HOURLY.items():
        host = sorted(load(cfg["station"]).items())
        nbrs = {st: sorted(load(st).items()) for st in cfg["neighbours"]}
        nbrs = {k: v for k, v in nbrs.items() if v}
        by_day = defaultdict(list)
        for ts, v in host:
            by_day[local_day(ts, cfg["tz"])].append((ts, v))
        for day in sorted(by_day):
            s = settles.get((day, city))
            if s is None or len(by_day[day]) < 12:
                continue
            prints = by_day[day]
            hourly_max = max(v for _, v in prints)
            # Reconstruct between-print temperature at every neighbour tick.
            # Average ACROSS neighbours at each tick, then take the max over
            # time. Doing it the other way round -- max over every neighbour's
            # own reconstruction -- picks the single largest noise excursion out
            # of ~1400 draws and overshot CLI by 6-7F. A max over noisy
            # estimates is biased upward by construction; averaging first cuts
            # the per-tick noise by sqrt(n) before the max is taken.
            best = hourly_max
            for i, (t0, v0) in enumerate(prints):
                t_end = prints[i + 1][0] if i + 1 < len(prints) else None
                base = {}
                ticks = set()
                for st, sr in nbrs.items():
                    a = at_or_before(sr, t0)
                    if a:
                        base[st] = a[1]
                        ticks.update(tb for tb, _ in sr
                                     if tb > t0 and (not t_end or tb < t_end))
                for tb in sorted(ticks):
                    ds = []
                    for st, sr in nbrs.items():
                        if st not in base:
                            continue
                        b = at_or_before(sr, tb)
                        if b and b[0] > t0:
                            ds.append(b[1] - base[st])
                    if ds:
                        best = max(best, v0 + statistics.fmean(ds))
            g_now, g_fix = s - hourly_max, s - best
            agg[city][0].append(g_now)
            agg[city][1].append(g_fix)
            print(f"{city:5}{day:12}{s:>6.0f}{hourly_max:>12.1f}{best:>10.1f}"
                  f"{g_now:>+9.2f}{g_fix:>+11.2f}")
    print()
    print(f"{'city':5}{'days':>6}{'mean gap now':>15}{'mean gap fixed':>17}{'closed':>9}")
    for city, (a, b) in agg.items():
        if len(a) < 3:
            continue
        ma, mb = statistics.fmean(a), statistics.fmean(b)
        print(f"{city:5}{len(a):>6}{ma:>+15.2f}{mb:>+17.2f}"
              f"{100*(ma-mb)/ma if ma else 0:>8.0f}%")
    print()
    print("A positive gap means the settled max was HIGHER than we observed, so")
    print("our p_exceed was too low and NO positions looked worse than they were.")
    print("Closing it is an information claim -- no market data involved.")


if __name__ == "__main__":
    main()
