"""Does the nowcast improve run_max -- the number the model actually uses?

p_exceed conditions on (city, hour, run_max), and needed = cap - run_max, so an
error in run_max is an equal and opposite error in the climb the model thinks is
still required. At KNYC and KDEN run_max is built from HOURLY prints, so it
misses whatever happened in between, and CLI reports the true peak. That gap was
measured at +1.16F (NYC) and +1.01F (DEN).

maxfix.py tried to close it and overshot badly, because it took a max over ~280
reconstructed neighbour ticks a day and a max over noisy estimates selects the
largest error. This is the same idea at the granularity the scanner actually
operates: it looks roughly every 55 minutes, so it can consult the nowcast about
11 times a day, not 280. Eleven draws bias the max far less than 280.

Reported against the only ground truth available, CLI.
"""
import datetime as dt
import json
import os
import statistics
import zoneinfo

from interp_wind import load
from nowcast import HOURLY, at_or_before, temp_of

SCAN_MIN = 55           # the main loop's cadence


def main():
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    print(f"{'city':5}{'day':12}{'CLI':>5}{'print max':>11}{'+nowcast':>10}"
          f"{'gap now':>9}{'gap nc':>8}")
    agg = {}
    for city, cfg in HOURLY.items():
        hs = [(k, temp_of(v)) for k, v in sorted(load(cfg["station"]).items())
              if temp_of(v) is not None]
        ns = {st: [(k, temp_of(v)) for k, v in sorted(load(st).items())
                   if temp_of(v) is not None] for st in cfg["neighbours"]}
        tz = zoneinfo.ZoneInfo(cfg["tz"])
        by_day = {}
        for ts, v in hs:
            d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(tz).date().isoformat()
            by_day.setdefault(d, []).append((ts, v))
        rows = []
        for day in sorted(by_day):
            s = settles.get((day, city))
            prints = by_day[day]
            if s is None or len(prints) < 12:
                continue
            pmax = max(v for _, v in prints)
            # Walk the day at the scanner's own cadence. At each look, the
            # nowcast is one extra candidate for the running max.
            t_start = dt.datetime.fromisoformat(prints[0][0].replace("Z", "+00:00"))
            t_end = dt.datetime.fromisoformat(prints[-1][0].replace("Z", "+00:00"))
            best = -999
            t = t_start
            while t <= t_end:
                stamp = t.isoformat().replace("+00:00", "Z")[:16] + "Z"
                lp = at_or_before(prints, stamp)
                if lp:
                    ds = []
                    for st, sr in ns.items():
                        a, b = at_or_before(sr, lp[0]), at_or_before(sr, stamp)
                        if a and b and b[0] > a[0]:
                            ds.append(b[1] - a[1])
                    cand = lp[1] + (statistics.fmean(ds) if ds else 0.0)
                    best = max(best, cand, lp[1])
                t += dt.timedelta(minutes=SCAN_MIN)
            best = max(best, pmax)
            rows.append((day, s, pmax, best))
            print(f"{city:5}{day:12}{s:>5.0f}{pmax:>11.1f}{best:>10.1f}"
                  f"{s-pmax:>+9.2f}{s-best:>+8.2f}")
        if len(rows) >= 3:
            agg[city] = ([s - p for _, s, p, _ in rows],
                         [s - b for _, s, _, b in rows])
    print()
    print(f"{'city':5}{'days':>6}{'mean |gap| now':>17}{'mean |gap| nowcast':>21}"
          f"{'better?':>9}")
    for city, (a, b) in agg.items():
        ma, mb = statistics.fmean(abs(x) for x in a), statistics.fmean(abs(x) for x in b)
        print(f"{city:5}{len(a):>6}{ma:>17.2f}{mb:>21.2f}"
              f"{('YES' if mb < ma else 'no'):>9}")
    print()
    print("run_max feeds needed = cap - run_max, so shrinking |gap| shrinks the")
    print("error in every p_exceed at these two stations. Signed gaps above show")
    print("whether the correction still overshoots.")


if __name__ == "__main__":
    main()
