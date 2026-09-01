"""Does sky cover -- and cloud BASE -- predict the remaining climb?

`sky` has been logged since 2026-08-24 with cover and base height, and is
consumed by nothing. Same position curve_dev was in before H4b.

Michael's Denver observation is the reason to split on base rather than cover
alone: FEW100 BKN150 BKN220 is broken cloud at 15,000 and 22,000 ft, which
attenuates insolation far less than a broken deck at 3,000. Treating "BKN" as
one category would pool a cirrostratus veil with a stratus lid.

Measured against the same target H4a uses -- remaining climb, settle - run_max --
inside the same 13-16 local peak window. Telemetry probe, not a registration:
this reports whether the signal exists, and nothing acts on it.
"""
import datetime as dt
import glob
import json
import os
import statistics
import zoneinfo
from collections import defaultdict

from lowno.config import CITIES

LOW_FT = 8000          # below this a deck shades; above it is mid/high cloud


def main():
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    groups = defaultdict(list)
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d, c = r.get("detail"), r.get("city")
            if not isinstance(d, dict) or d.get("world") or c not in CITIES:
                continue
            s, rm = d.get("sky"), d.get("run_max")
            st = settles.get((day, c))
            if not isinstance(s, dict) or rm is None or st is None:
                continue
            cover, base = s.get("cover"), s.get("base_ft")
            if not cover:
                continue
            try:
                lt = (dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
                      .astimezone(zoneinfo.ZoneInfo(CITIES[c]["tz"])))
            except Exception:
                continue
            if not (13 <= lt.hour <= 16):
                continue
            groups[cover].append(st - rm)
            if cover in ("BKN", "OVC", "SCT"):
                tier = "low" if (base is not None and base < LOW_FT) else "mid/high"
                groups[f"{cover} {tier}"].append(st - rm)
    print("Remaining climb (settle - run_max) in the 13-16 local peak window\n")
    print(f"{'sky':18}{'n':>6}{'mean':>9}{'median':>9}{'sd':>8}")
    order = ["CLR", "FEW", "SCT", "SCT low", "SCT mid/high",
             "BKN", "BKN low", "BKN mid/high", "OVC", "OVC low", "OVC mid/high"]
    for k in order:
        v = groups.get(k) or []
        if len(v) < 8:
            continue
        print(f"{k:18}{len(v):>6}{statistics.fmean(v):>+9.2f}"
              f"{statistics.median(v):>+9.2f}"
              f"{(statistics.stdev(v) if len(v) > 1 else 0):>8.2f}")
    clr = groups.get("CLR") or []
    for k in ("BKN low", "BKN mid/high", "OVC low", "OVC mid/high"):
        v = groups.get(k) or []
        if len(v) >= 8 and clr:
            import math
            diff = statistics.fmean(v) - statistics.fmean(clr)
            se = math.sqrt(statistics.variance(v)/len(v)
                           + statistics.variance(clr)/len(clr))
            print(f"\n  {k} vs CLR: {diff:+.2f}F  "
                  f"[{diff-1.96*se:+.2f}, {diff+1.96*se:+.2f}]"
                  + ("  separated" if abs(diff) > 1.96*se else "  not separated"))


if __name__ == "__main__":
    main()
