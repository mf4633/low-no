"""Score competing forecasters against CLI settlement.

Metrics, per forecaster and per station:
  n       settled station-days with a forecast present
  bias    mean(forecast - actual). Positive = runs hot. This is the number the
          adaptive layer would correct with.
  mae     mean absolute error
  rmse    root mean square error -- penalises the big misses that produce
          FORECAST_BUST attributions
  p_within_2F  fraction landing within 2F, the practical accuracy that matters
          when a rung sits 1-2F from the guide

Only forecasts recorded at the SAME scan cycle are compared, so no forecaster
gets an unfair look at a later, easier update.
"""
import json, glob, os, math
from collections import defaultdict

# Keys that live in the forecasts dict but are NOT temperature forecasts. The
# 2026-08-22 interim collector wrote a consensus block whose `n` (member count)
# and `spread` (degrees F) are numeric, and scoring every numeric value as a
# forecast graded them against CLI: they appear in the nightly table with a
# -84F bias. Nothing consumes those rows, but the table is read every night.
NOT_A_FORECAST = {"n", "spread", "sources"}

# A forecaster must span this many distinct settled DAYS before it can be
# ranked. Observation count alone is not enough: `mean` and `median` carry 42
# observations from a SINGLE day (2026-08-22) and were ranking first and second
# by RMSE, above nbm_guide's 2,000+ observations across the whole record. One
# calm day is not a skill result.
MIN_DAYS_TO_RANK = 5


def _settlements():
    try:
        return {tuple(k.split("|")): v
                for k, v in json.load(open("docs/settlements.json")).items()}
    except Exception:
        return {}


def build(min_n=3):
    settles = _settlements()
    # (forecaster, city) -> [errors]; also pooled per forecaster
    err = defaultdict(list)
    pooled = defaultdict(list)
    days_seen = defaultdict(set)
    seen = set()

    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = r.get("detail")
            if not isinstance(d, dict):
                continue
            fc = d.get("forecasts")
            city = r.get("city")
            if not fc or not city:
                continue
            actual = settles.get((day, city))
            if actual is None:
                continue
            # one observation per city-day-cycle-forecaster
            key = (day, city, r.get("at", "")[:16])
            if key in seen:
                continue
            seen.add(key)
            for name, val in list(fc.items()) + [("nbm_guide", d.get("guide"))]:
                if name in NOT_A_FORECAST:
                    continue
                # not just None-guarding: rows logged 2026-08-22 by the interim
                # collector carry a nested dict under this key, and one such row
                # would TypeError the whole build once that day settles
                if not isinstance(val, (int, float)):
                    continue
                e = val - actual
                err[(name, city)].append(e)
                pooled[name].append(e)
                days_seen[name].add(day)
    return err, pooled, days_seen


def _stats(errs):
    n = len(errs)
    if not n:
        return None
    bias = sum(errs) / n
    mae = sum(abs(e) for e in errs) / n
    rmse = math.sqrt(sum(e * e for e in errs) / n)
    within2 = sum(1 for e in errs if abs(e) <= 2) / n
    return dict(n=n, bias=round(bias, 2), mae=round(mae, 2),
                rmse=round(rmse, 2), p_within_2F=round(within2, 3))


def report(min_n=3):
    err, pooled, days_seen = build()
    out = {"pooled": {}, "by_station": {}, "min_n": min_n,
           "min_days_to_rank": MIN_DAYS_TO_RANK}
    for name, e in pooled.items():
        st = _stats(e)
        if st:
            st["days"] = len(days_seen[name])
            out["pooled"][name] = st
    for (name, city), e in err.items():
        if len(e) >= min_n:
            out["by_station"].setdefault(city, {})[name] = _stats(e)
    # Rank only forecasters with enough DAYS. The others still appear in
    # `pooled` -- hiding them would be its own kind of lie -- but they cannot
    # top a ranking on one day's weather.
    rankable = {k: v for k, v in out["pooled"].items()
                if v["days"] >= MIN_DAYS_TO_RANK and v["n"] >= min_n}
    out["ranking_by_rmse"] = [k for k, _ in
                              sorted(rankable.items(), key=lambda kv: kv[1]["rmse"])]
    out["unranked"] = sorted(set(out["pooled"]) - set(rankable))
    out["note"] = ("Started 2026-08-22. Earlier history has only NBM guide -- "
                   "competing forecasts were never archived and cannot be "
                   "reconstructed. Needs ~3 weeks before a ranking means anything.")
    return out


def write(path="docs/skill.json"):
    import datetime as dt
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = report()
    out["generated"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    json.dump(out, open(path, "w"), indent=1)
    if out["pooled"]:
        print(f"{'forecaster':12} {'n':>5} {'days':>5} {'bias':>6} {'mae':>5} "
              f"{'rmse':>5} {'<=2F':>6}")
        for name in out["ranking_by_rmse"]:
            st = out["pooled"][name]
            print(f"{name:12} {st['n']:>5} {st['days']:>5} {st['bias']:>+6.2f} "
                  f"{st['mae']:>5.2f} {st['rmse']:>5.2f} {100*st['p_within_2F']:>5.0f}%")
        for name in out.get("unranked", []):
            st = out["pooled"][name]
            print(f"{name:12} {st['n']:>5} {st['days']:>5} {st['bias']:>+6.2f} "
                  f"{st['mae']:>5.2f} {st['rmse']:>5.2f} {100*st['p_within_2F']:>5.0f}%"
                  f"   unranked (<{MIN_DAYS_TO_RANK} days)")
    else:
        print("skill: no settled forecasts yet (expected until tomorrow's grade)")
    return out


if __name__ == "__main__":
    write()
