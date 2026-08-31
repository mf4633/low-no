"""Hypothesis 7 -- shape on TEMPERATURE tendency, not on the maximum.

WRITTEN 2026-08-31, BEFORE ANY QUALIFYING DAY. Same discipline as shape_eval,
curve_lag and band_eval: not to be tuned once data arrives.

H4A IS NOT TOUCHED. shape_eval.py keeps scoring on run_max and stays exactly as
registered. This is a separate harness with a separate verdict.

THE ONE CHANGE. Everything is identical to H4a -- peak window 13-16 local, the
same rate_bucket thresholds, the same MIN_N_RATE, the same held-out Brier on a
date-parity split, the same level (run_max) and the same sample (settle -
run_max). Only the CONDITIONING VARIABLE differs: the rate comes from `temp_now`
rather than from `run_max`.

Why: run_max is a maximum, so it moves only when a new high is set. 47% of
peak-window intervals have delta(run_max) = 0 and are all labelled STALLED,
while their actual tendency runs p10 -3.18 to p90 +1.77 F/hr. Re-bucketed on
temp_now they are 79% stalled / 3% mid / 18% CLIMBING -- one in five is
mislabelled, and cooling is indistinguishable from flat-at-peak although the two
mean opposite things.

STRATIFIED, AND THAT IS THE POINT. Two effects are in play and they must not be
pooled:

    effect A   temp_now instead of run_max          -- all 23 stations
    effect B   nowcast instead of a stale temp_now  -- KNYC and KDEN only

The 21 five-minute stations already have a fresh temp_now, so effect B is zero
there BY CONSTRUCTION. That makes them a clean control: the hourly pair gets
A + B, the control gets A alone, and the difference isolates B. A result that
looks the same in both strata means the nowcast contributed nothing and only
monotonicity mattered -- which is a real answer, not a failure.
"""
import datetime as dt
import glob
import json
import os
import zoneinfo
from collections import defaultdict

from lowno import empirical as E
from lowno.config import CITIES

HOURLY_STATIONS = {"NYC", "DEN"}
NOWCAST_SINCE = "2026-09-01"      # when run_max_nowcast starts being logged
MIN_SCORED = 50                   # same bar as H4a


def _rows():
    """(day, city) -> [(hour_float, hour, run_max, tendency_source)] sorted."""
    out = defaultdict(list)
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d, city = r.get("detail"), r.get("city")
            if not isinstance(d, dict) or d.get("world") or city not in CITIES:
                continue
            rm, tn = d.get("run_max"), d.get("temp_now")
            if rm is None or tn is None:
                continue
            # At the two hourly stations, from the date the field exists, the
            # nowcast replaces the stale print as the tendency source. Nowhere
            # else -- the other 21 are the control and must stay untouched.
            src = tn
            if city in HOURLY_STATIONS and day >= NOWCAST_SINCE:
                nd = d.get("nowcast_detail")
                if isinstance(nd, dict) and nd.get("nowcast_f") is not None:
                    src = nd["nowcast_f"]
            try:
                lt = (dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
                      .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])))
            except Exception:
                continue
            out[(day, city)].append((lt.hour + lt.minute / 60.0, lt.hour, rm, src))
    for k in out:
        out[k].sort(key=lambda x: x[0])
    return out


def _settles():
    return {tuple(k.split("|")): v
            for k, v in json.load(open("docs/settlements.json")).items()}


def build(days_keep):
    """(unconditioned, tendency-conditioned) sample tables from `days_keep`."""
    settles, rows = _settles(), _rows()
    S, R = defaultdict(list), defaultdict(list)
    for (day, city), v in rows.items():
        if day not in days_keep:
            continue
        s = settles.get((day, city))
        if s is None:
            continue
        for i, (hf, h, rm, src) in enumerate(v):
            S[(city, h)].append(s - rm)
            if i == 0:
                continue
            dh = hf - v[i - 1][0]
            if not (0.5 <= dh <= 2.5):
                continue
            b = E.rate_bucket((src - v[i - 1][3]) / dh)   # <- the one change
            if b is not None:
                R[(city, h, b)].append(s - rm)
    return S, R


def cycles(days_keep):
    settles, rows = _settles(), _rows()
    out = []
    for (day, city), v in rows.items():
        if day not in days_keep:
            continue
        s = settles.get((day, city))
        if s is None:
            continue
        for i in range(1, len(v)):
            hf, h, rm, src = v[i]
            if not (E.PEAK_WINDOW[0] <= h <= E.PEAK_WINDOW[1]):
                continue
            dh = hf - v[i - 1][0]
            if not (0.5 <= dh <= 2.5):
                continue
            out.append(dict(city=city, hour=h, run_max=rm, settle=s,
                            rate=(src - v[i - 1][3]) / dh,
                            stratum=("hourly" if city in HOURLY_STATIONS
                                     else "control")))
    return out


def evaluate(stratum=None):
    days = sorted(os.path.basename(p)[:-6] for p in glob.glob("logs/2*.jsonl"))
    train = {d for d in days if int(d[-1]) % 2 == 0}
    test = {d for d in days if int(d[-1]) % 2 == 1}
    S, R = build(train)
    base, shape, n = [], [], 0
    for c in cycles(test):
        if stratum and c["stratum"] != stratum:
            continue
        for off in (1, 2, 3):
            cap = c["run_max"] + off
            a = E.p_exceed(c["city"], c["hour"], c["run_max"], cap, samples=S)
            b = E.p_exceed(c["city"], c["hour"], c["run_max"], cap, samples=S,
                           rate=c["rate"], rated_samples=R)
            if a is None or b is None or not b.get("source", "").startswith("shape"):
                continue
            y = 1.0 if c["settle"] > cap else 0.0
            base.append((a["p"] - y) ** 2)
            shape.append((b["p"] - y) ** 2)
            n += 1
    if not n:
        return dict(n=0, base=None, shape=None)
    return dict(n=n, base=sum(base) / n, shape=sum(shape) / n)


def verdict():
    """PASSES only on a strict held-out Brier improvement over >= MIN_SCORED,
    reported per stratum. Pooled is shown but is NOT the verdict -- the whole
    design is that the hourly pair and the control are answered separately."""
    try:
        strata = {k: evaluate(k) for k in ("hourly", "control")}
        pooled = evaluate(None)
    except Exception as e:
        return dict(id="H7", ready=False, passed=False, error=str(e)[:120])
    out = dict(id="H7", pooled_n=pooled["n"])
    for k, r in strata.items():
        out[k] = dict(n=r["n"],
                      brier_base=(round(r["base"], 4) if r["base"] else None),
                      brier_shape=(round(r["shape"], 4) if r["shape"] else None),
                      improved=(bool(r["shape"] < r["base"]) if r["n"] else None))
    ready = all(strata[k]["n"] >= MIN_SCORED for k in strata)
    out["ready"] = ready
    out["passed"] = bool(ready and strata["hourly"]["shape"] < strata["hourly"]["base"]
                         and strata["control"]["shape"] < strata["control"]["base"])
    if not ready:
        out["reason"] = (f"need {MIN_SCORED} scored decisions per stratum; have "
                         f"hourly={strata['hourly']['n']}, "
                         f"control={strata['control']['n']}")
    return out


def main():
    print("H7 -- shape on temperature tendency, stratified")
    print(f"  hourly stratum: {sorted(HOURLY_STATIONS)} (nowcast substituted "
          f"from {NOWCAST_SINCE})")
    print("  control stratum: the other 21, fresh temp_now, no substitution\n")
    v = verdict()
    print(json.dumps(v, indent=1))
    if not v.get("ready"):
        print(f"\n{v.get('reason')}")
        print("Registered behaviour, not a failure.")
        return
    h, c = v["hourly"], v["control"]
    dh = h["brier_base"] - h["brier_shape"]
    dc = c["brier_base"] - c["brier_shape"]
    print(f"\n  hourly  Brier {h['brier_base']} -> {h['brier_shape']}  gain {dh:+.4f}")
    print(f"  control Brier {c['brier_base']} -> {c['brier_shape']}  gain {dc:+.4f}")
    print(f"  difference-in-differences (isolates the nowcast): {dh - dc:+.4f}")
    if dh - dc <= 0:
        print("  -> the nowcast added nothing beyond the temp_now change itself.")


if __name__ == "__main__":
    main()
