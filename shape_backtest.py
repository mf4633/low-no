"""Hypothesis 4a -- does climb RATE add information beyond level+hour?

Rule fixed in CANDIDATE.md before this file existed. Rate is measured from
consecutive run_max readings; buckets and bands are as registered. The point of
the banding is that the model ALREADY conditions on hour and on needed climb,
so an effect that survives inside a band is genuinely new information.
"""
import json, glob, os, math, statistics, datetime as dt, zoneinfo
from collections import defaultdict
from lowno.config import CITIES

STALL, CLIMB = 0.2, 1.5
HOUR_BANDS = [("pre<13", lambda h: h < 13),
              ("peak13-16", lambda h: 13 <= h <= 16),
              ("post>16", lambda h: h > 16)]
NEED_BANDS = [("0-2F", 0, 2), ("2-5F", 2, 5), ("5F+", 5, 99)]


def mean_se(v):
    if not v:
        return None, None
    m = sum(v) / len(v)
    if len(v) < 2:
        return m, None
    return m, statistics.pstdev(v) / math.sqrt(len(v))


def main():
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    paths = defaultdict(list)
    for p in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(p)[:-6]
        for line in open(p):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("verdict") != "LADDER":
                continue
            d = r.get("detail") or {}
            c = r.get("city")
            if d.get("world") or c not in CITIES or d.get("run_max") is None:
                continue
            try:
                u = dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
                lt = u.astimezone(zoneinfo.ZoneInfo(CITIES[c]["tz"]))
                h = lt.hour + lt.minute / 60.0
            except Exception:
                continue
            cap = None
            for g in d.get("rungs", []):
                if g.get("fl") is None and g.get("cap") is not None:
                    cap = g["cap"]
                    break
            paths[(day, c)].append((h, d["run_max"], cap))
    for k in paths:
        paths[k].sort()

    obs = []
    for (day, city), v in paths.items():
        s = settles.get((day, city))
        if s is None:
            continue
        for i in range(1, len(v)):
            dh = v[i][0] - v[i - 1][0]
            if not (0.5 <= dh <= 2.5):
                continue
            rate = (v[i][1] - v[i - 1][1]) / dh
            rm = v[i][1]
            remaining = s - rm          # realized climb still to come
            if remaining < -3:          # settle far below observed: bad day, skip
                continue
            obs.append(dict(day=day, city=city, hour=v[i][0], rate=rate,
                            run_max=rm, remaining=remaining, cap=v[i][2]))

    print(f"rate observations with settled outcomes: {len(obs)}")

    def bucket(r):
        return "STALLED" if r <= STALL else ("CLIMBING" if r >= CLIMB else "MID")

    print("\nH4a -- mean REALIZED REMAINING CLIMB (F) by rate bucket, "
          "within hour band")
    print(f"{'band':>12} {'STALLED':>18} {'MID':>18} {'CLIMBING':>18} {'gap':>7}")
    for name, f in HOUR_BANDS:
        g = [o for o in obs if f(o["hour"])]
        cells = {}
        for b in ("STALLED", "MID", "CLIMBING"):
            v = [o["remaining"] for o in g if bucket(o["rate"]) == b]
            cells[b] = (mean_se(v), len(v))
        def fmt(b):
            (m, se), n = cells[b]
            if m is None:
                return f"{'--':>18}"
            s = f"{m:+.2f}+-{se:.2f} n={n}" if se is not None else f"{m:+.2f} n={n}"
            return f"{s:>18}"
        (ms, _), _ = cells["STALLED"]
        (mc, _), _ = cells["CLIMBING"]
        gap = (mc - ms) if (ms is not None and mc is not None) else None
        print(f"{name:>12} {fmt('STALLED')} {fmt('MID')} {fmt('CLIMBING')} "
              f"{(f'{gap:+.2f}' if gap is not None else '--'):>7}")

    print("\nsame, ALSO controlling for needed climb (cap - run_max) -- "
          "the model's other input")
    print(f"{'band':>12} {'need':>7} {'STALLED':>16} {'CLIMBING':>16} {'gap':>7}")
    for name, f in HOUR_BANDS:
        for nname, lo, hi in NEED_BANDS:
            g = [o for o in obs if f(o["hour"]) and o["cap"] is not None
                 and lo <= (o["cap"] - o["run_max"]) < hi]
            vs = [o["remaining"] for o in g if bucket(o["rate"]) == "STALLED"]
            vc = [o["remaining"] for o in g if bucket(o["rate"]) == "CLIMBING"]
            (ms, ses), (mc, sec) = mean_se(vs), mean_se(vc)
            if ms is None or mc is None or len(vs) < 5 or len(vc) < 5:
                continue
            sep = ""
            if ses and sec:
                sep = "  SEPARATED" if abs(mc - ms) >= 0.5 and \
                      (mc - sec) > (ms + ses) else ""
            print(f"{name:>12} {nname:>7} {ms:+.2f}+-{ses:.2f} n={len(vs):<3} "
                  f"{mc:+.2f}+-{sec:.2f} n={len(vc):<3} {mc-ms:>+6.2f}{sep}")


if __name__ == "__main__":
    main()
