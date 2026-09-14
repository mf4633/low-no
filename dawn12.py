r"""Pre-dawn 12-hour-advance daily-high prediction, locked so it can be scored.

ISSUED AT 04:00 LOCAL. Measured over 681 city-days in this log, the observed
peak sits at a median 15.7 local, so 04:00 is **11.7 hours before the median
peak** -- the "12 hour advance" this file is named for. It is also before every
sky window `city_regime.py` uses (the earliest is 05-07 local), so NO REGIME
INFORMATION IS AVAILABLE HERE and none is used. At this hour the only inputs
are numerical guidance and climatology: no observed climb, no morning sky, no
book-derived anything.

WHAT IT PRODUCES. For each city, a full distribution over the integer CLI high
-- P(high = k) -- plus P(high > cap) for any ladder rung, which is the quantity
a bottom-rung NO position actually pays on. Locked to logs/dawn12/<day>.jsonl
with its issuance time and every input, so the prediction can be graded later
against what was believed AT THE TIME rather than reconstructed.

THE ENSEMBLE -- FROZEN, AND WHY THESE FOUR

    om_gfs      GFS       (NOAA global, via Open-Meteo)
    om_icon     ICON      (DWD)
    om_metno    MET Norway
    nbm_guide   NWS       (api.weather.gov /forecast, first daytime period)

One member per genuinely distinct modelling chain. Three are excluded, each for
a measured reason rather than a taste:

  * `om_best` is Open-Meteo's best_match, which resolves to GFS in the US:
    identical to om_gfs on 5,222 of 5,226 logged rows (99.92%). Including both
    silently double-weights GFS. THIS ALSO AFFECTS docs/skill.json, whose
    pooled `mean` and `median` rows are computed over a source list containing
    both and are therefore GFS-tilted.
  * `nws_grid` is the SAME NWS forecaster product as nbm_guide read through a
    different endpoint -- /forecastGridData maxTemperature against /forecast
    period temperature -- not an independent model. Keeping both repeats the
    om_best mistake in a subtler form. Of the two readings, the period
    temperature is the better one at this hour (solo MAE 1.89 against 2.55,
    residual sd 2.60 against 3.43; the gridded read looks stale pre-dawn).
    Dropping it moved the ensemble from 1.651 to 1.503 MAE.
  * `om_ecmwf` carries solo MAE 3.19 and residual sd 4.29, roughly double every
    other member, across every lead bucket in the record.

So the frozen set is THREE independent NWP chains plus one NWS human-adjusted
forecast, which is as close to decorrelated as this input set gets.

MEASURED SKILL, leave-one-DAY-out on 413 pre-dawn city-days over 16 days:

    bias-corrected single, best (nbm_guide)   MAE 1.890   sd 2.60   64.2% <=2F
    ENS4 with nws_grid, no guide              MAE 1.651   sd 2.26   71.4%
    ENS5 with both                            MAE 1.598   sd 2.21   72.6%
    ENS4b  <- FROZEN                          MAE 1.503   sd 2.08   75.5%

READ 1.503 AS AN IN-SELECTION NUMBER, NOT A FORWARD ONE. Five configurations
were compared on the same 16 days, so the member set is chosen on the data it
is scored against and the honest forward expectation is worse. That is what
`--score` is for: every locked prediction also records the three alternatives
above, so the comparison keeps running out-of-sample and the forward number
replaces this one.

WHAT IS DELIBERATELY NOT DONE

  * No per-station bias correction. Measured to HURT: 1.652 -> 1.684 MAE. The
    per-city residual counts here are 5 to 40, so a per-city term is fitting
    noise, which is H4a's lesson restated.
  * No marine/continental split. Marine residual sd is 2.49 against 2.12
    continental -- a ratio of 1.17, not enough to pay for the cell split.
  * No inverse-variance weighting. Measured at 1.749 against 1.744 for the
    plain mean: the fine weights do not pay.
  * No regime conditioning. Not available at this hour, as above.

THIS IS A FORECAST, NOT A SIGNAL. It says nothing about whether the number is
in the price, and the standing evidence says it will be: the market was 3.2x
better calibrated than a model of this class at KNYC/KDEN, and trading the
disagreements lost 5.8-6.7c per trade at every margin tested. Any trading claim
is a separate registration with its own units and its own Wilson bar.

Usage:  python dawn12.py --calibrate      rebuild docs/dawn12_calib.json from logs
        python dawn12.py                  predict for cities now at ~04:00 local
        python dawn12.py --cities DEN,PHX --force
        python dawn12.py --score          grade every locked prediction
"""
import argparse
import datetime as dt
import io
import json
import os
import statistics as st
import zoneinfo
from collections import defaultdict

from lowno import forecasts, sources
from lowno.config import CITIES

# ---------------------------------------------------------------- FROZEN ----
MEMBERS = ("om_gfs", "om_icon", "om_metno", "nbm_guide")
ALTERNATIVES = {                       # scored alongside, NEVER primary
    "ens4_nws": ("nws_grid", "om_gfs", "om_icon", "om_metno"),
    "ens5_both": ("nws_grid", "om_gfs", "om_icon", "om_metno", "nbm_guide"),
    "single_nbm": ("nbm_guide",),
}
ISSUE_LOCAL_HOUR = 4
ISSUE_TOLERANCE_H = 1.0                # accept 03:00-05:00 local
CALIB_HOURS = (3, 6)                   # local-hour window the calibration reads
MIN_RESID = 120                        # below this, fall back to a Gaussian
LOG_DIR = "logs/dawn12"
CALIB = "docs/dawn12_calib.json"
SETTLE = "docs/settlements.json"


# ------------------------------------------------------------ LOG READING ---
def _pre_dawn_cells():
    """[(day, city, {forecaster: value}, settle)] for the calibration window.

    One row per (day, city, rounded local hour) -- the scan fires several times
    an hour and weighting an hour by how often it happened to run is not a
    property of the forecast.
    """
    settle = json.loads(io.open(SETTLE, encoding="utf-8").read())
    best = {}
    for fn in sorted(os.listdir("logs")):
        if not fn.endswith(".jsonl"):
            continue
        day = fn[:-6]
        for line in io.open(os.path.join("logs", fn), encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            c, d = r.get("city"), r.get("detail")
            if c not in CITIES or not isinstance(d, dict):
                continue
            f = d.get("forecasts")
            if not isinstance(f, dict) or "om_gfs" not in f:
                continue
            at = r.get("at")
            if not at:
                continue
            try:
                t = dt.datetime.fromisoformat(at.replace("Z", "+00:00"))
            except Exception:
                continue
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
            loc = t.astimezone(zoneinfo.ZoneInfo(CITIES[c]["tz"]))
            lh = loc.hour + loc.minute / 60.0
            b = int(round(lh))
            if not (CALIB_HOURS[0] <= b <= CALIB_HOURS[1]):
                continue
            merged = dict(f)
            g = d.get("guide")
            if isinstance(g, (int, float)):
                merged["nbm_guide"] = float(g)
            k = (day, c, b)
            err = abs(lh - b)
            if k not in best or err < best[k][0]:
                best[k] = (err, merged)
    out = []
    for (day, c, _b), (_e, f) in best.items():
        s = settle.get(f"{day}|{c}")
        if not isinstance(s, (int, float)):
            continue
        out.append((day, c, f, float(s)))
    return out


def _members_present(f, members):
    return all(isinstance(f.get(k), (int, float)) for k in members)


def _point(f, members, bias):
    return sum(float(f[k]) - bias[k] for k in members) / len(members)


# ------------------------------------------------------------ CALIBRATION ---
def calibrate(verbose=True):
    cells = _pre_dawn_cells()
    need = set(MEMBERS) | {m for v in ALTERNATIVES.values() for m in v}
    full = [x for x in cells if _members_present(x[2], need)]
    if len(full) < 50:
        raise SystemExit(f"only {len(full)} complete pre-dawn cells -- refusing to calibrate")
    days = sorted({d for d, _, _, _ in full})

    bias = {k: st.mean([f[k] - s for _, _, f, s in full]) for k in need}
    resid = sorted(_point(f, MEMBERS, bias) - s for _, _, f, s in full)

    # leave-one-DAY-out skill for the frozen set and every alternative
    def lodo(members):
        errs = []
        for day in days:
            tr = [x for x in full if x[0] != day]
            te = [x for x in full if x[0] == day]
            if not tr or not te:
                continue
            b = {k: st.mean([f[k] - s for _, _, f, s in tr]) for k in members}
            errs += [_point(f, members, b) - s for _, _, f, s in te]
        return dict(n=len(errs), mae=round(sum(abs(e) for e in errs) / len(errs), 3),
                    sd=round(st.pstdev(errs), 3), bias=round(st.mean(errs), 3),
                    within_2f=round(sum(1 for e in errs if abs(e) <= 2) / len(errs), 4))

    skill = {"FROZEN_ens4b": lodo(MEMBERS)}
    for name, mem in ALTERNATIVES.items():
        skill[name] = lodo(mem)

    blob = dict(
        built_at=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        members=list(MEMBERS), calib_hours=list(CALIB_HOURS),
        n_cells=len(full), n_days=len(days),
        cities=sorted({c for _, c, _, _ in full}),
        bias={k: round(v, 4) for k, v in bias.items()},
        residuals=[round(r, 3) for r in resid],
        resid_sd=round(st.pstdev(resid), 4),
        lodo_skill=skill)
    os.makedirs(os.path.dirname(CALIB), exist_ok=True)
    io.open(CALIB, "w", encoding="utf-8").write(json.dumps(blob, indent=1))
    if verbose:
        print(f"calibrated on {len(full)} pre-dawn city-days over {len(days)} days, "
              f"{len(blob['cities'])} cities")
        print(f"  per-forecaster bias (forecast minus settle):")
        for k in sorted(bias):
            print(f"    {k:<12}{bias[k]:+.2f}")
        print(f"  ensemble residual sd {blob['resid_sd']:.2f}\n")
        print(f"  {'configuration':<22}{'MAE':>7}{'sd':>7}{'<=2F':>8}")
        for name in ["FROZEN_ens4b"] + sorted(ALTERNATIVES):
            s = skill[name]
            print(f"  {name:<22}{s['mae']:>7.3f}{s['sd']:>7.3f}{s['within_2f']:>8.1%}")
        print(f"\n  wrote {CALIB}")
        print("  NOTE: these are leave-one-day-out over the SAME 16 days the member")
        print("        set was chosen on. The forward number comes from --score.")
    return blob


def load_calib():
    if not os.path.exists(CALIB):
        raise SystemExit(f"{CALIB} missing -- run: python dawn12.py --calibrate")
    return json.loads(io.open(CALIB, encoding="utf-8").read())


# ------------------------------------------------------------ PREDICTION ----
def distribution(point, calib):
    """P(CLI high = k) from the EMPIRICAL residual distribution.

    residual r = prediction - settle, so settle = point - r. The mass on
    integer k is the share of the residual sample landing in the half-degree
    bin around (point - k). Empirical rather than Gaussian for the same reason
    lax_forecast.py is: these highs are not normal, and a Gaussian tail is an
    assumption where a measured tail is available.
    """
    R = calib.get("residuals") or []
    lo, hi = int(round(point - 12)), int(round(point + 12))
    if len(R) >= MIN_RESID:
        n = len(R)
        dist = {}
        for k in range(lo, hi + 1):
            c = sum(1 for r in R if point - k - 0.5 <= r < point - k + 0.5)
            if c:
                dist[k] = c / n
        src = f"empirical residuals (n={n})"
    else:
        import math
        sd = calib.get("resid_sd") or 2.2
        cdf = lambda x: 0.5 * (1 + math.erf(x / (sd * math.sqrt(2))))
        dist = {}
        for k in range(lo, hi + 1):
            p = cdf(point - k + 0.5) - cdf(point - k - 0.5)
            if p > 1e-6:
                dist[k] = p
        src = f"Gaussian fallback (sd={sd:.2f}, only {len(R)} residuals)"
    tot = sum(dist.values()) or 1.0
    return {k: v / tot for k, v in sorted(dist.items())}, src


def p_exceeds(dist, cap):
    """P(daily high > cap) -- what a bottom-rung NO position pays on.

    THE WIN CONDITION (CLAUDE.md): buying NO on a `<= cap` bucket wins when the
    day runs HOTTER than cap. This is the place that inverted the advisor once.
    """
    return sum(p for k, p in dist.items() if k > cap)


def quantiles(dist, ts=(0.10, 0.50, 0.90)):
    cum, q = 0.0, {}
    for k in sorted(dist):
        cum += dist[k]
        for t in ts:
            if t not in q and cum >= t:
                q[t] = k
    return q


def already_locked(day):
    """{city} already holding a prediction for `day`.

    THE UNIT IS ONE PREDICTION PER CITY-DAY. The issuance tolerance is +/-1h
    (not tighter) because GitHub drops scheduled fires and this project has
    already lost a full day of peak coverage to a single-slot assumption -- but
    a wide window plus hourly crons would otherwise lock the same city two or
    three times and quietly triple its weight in every later score.
    """
    p = os.path.join(LOG_DIR, f"{day}.jsonl")
    if not os.path.exists(p):
        return set()
    out = set()
    for line in io.open(p, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("city") and not r.get("refused"):
            out.add(r["city"])
    return out


def predict(cities, calib, force=False, day=None, skip=()):
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for city in cities:
        meta = CITIES[city]
        z = zoneinfo.ZoneInfo(meta["tz"])
        loc = now.astimezone(z)
        lh = loc.hour + loc.minute / 60.0
        if not force and abs(lh - ISSUE_LOCAL_HOUR) > ISSUE_TOLERANCE_H:
            continue
        local_date = day or loc.date().isoformat()
        if city in skip:
            print(f"  {city}: already locked for {local_date} -- skipped")
            continue
        f = forecasts.collect(meta, local_date)
        # `nbm_guide` is not one of forecasts.FORECASTERS -- scan.py fetches it
        # separately and stores it as detail["guide"]. The calibration reads it
        # from there, so the live path must fetch the SAME object or the frozen
        # bias term is applied to a different quantity.
        try:
            g, _short, _pop = sources.point_forecast_high(meta["lat"], meta["lon"])
            if isinstance(g, (int, float)):
                f["nbm_guide"] = float(g)
        except Exception as e:
            print(f"  {city}: nbm_guide fetch failed ({str(e)[:50]})")
        missing = [k for k in MEMBERS if not isinstance(f.get(k), (int, float))]
        if missing:
            print(f"  {city}: members missing {missing} -- NO PREDICTION")
            out.append(dict(city=city, day=local_date, refused=f"missing {missing}"))
            continue
        point = _point(f, MEMBERS, calib["bias"])
        dist, src = distribution(point, calib)
        alts = {}
        for name, mem in ALTERNATIVES.items():
            if _members_present(f, mem):
                alts[name] = round(_point(f, mem, calib["bias"]), 2)
        q = quantiles(dist)
        rec = dict(
            issued_at=now.isoformat().replace("+00:00", "Z"),
            local_time=loc.isoformat(), city=city, day=local_date,
            lead_h_to_median_peak=round(15.7 - lh, 1),
            members={k: f.get(k) for k in MEMBERS},
            inputs_all={k: v for k, v in f.items() if isinstance(v, (int, float))},
            point=round(point, 2), dist={str(k): round(v, 5) for k, v in dist.items()},
            dist_src=src, p10=q.get(0.10), p50=q.get(0.50), p90=q.get(0.90),
            alternatives=alts)
        out.append(rec)
        print(f"  {city:<5}{loc.strftime('%H:%M')} local  point {point:>6.1f}  "
              f"p10/50/90 {q.get(0.10)}/{q.get(0.50)}/{q.get(0.90)}  "
              f"lead {rec['lead_h_to_median_peak']}h")
    return out


# --------------------------------------------------------------- SCORING ----
def score():
    """Grade every locked prediction. This is the FORWARD number."""
    settle = json.loads(io.open(SETTLE, encoding="utf-8").read())
    if not os.path.isdir(LOG_DIR):
        print(f"no {LOG_DIR} yet -- nothing locked")
        return
    per = defaultdict(list)
    n = 0
    for fn in sorted(os.listdir(LOG_DIR)):
        if not fn.endswith(".jsonl"):
            continue
        for line in io.open(os.path.join(LOG_DIR, fn), encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("refused") or r.get("point") is None:
                continue
            s = settle.get(f"{r['day']}|{r['city']}")
            if not isinstance(s, (int, float)):
                continue
            n += 1
            per["FROZEN_ens4b"].append(r["point"] - s)
            for name, v in (r.get("alternatives") or {}).items():
                per[name].append(v - s)
    if not n:
        print("no locked prediction has settled yet")
        return
    print(f"FORWARD skill on {n} locked pre-dawn predictions\n")
    print(f"  {'configuration':<22}{'n':>5}{'MAE':>8}{'sd':>8}{'bias':>8}{'<=2F':>8}")
    for name in ["FROZEN_ens4b"] + sorted(k for k in per if k != "FROZEN_ens4b"):
        e = per[name]
        if not e:
            continue
        print(f"  {name:<22}{len(e):>5}{sum(abs(x) for x in e)/len(e):>8.3f}"
              f"{st.pstdev(e) if len(e) > 1 else 0:>8.3f}{st.mean(e):>+8.3f}"
              f"{sum(1 for x in e if abs(x) <= 2)/len(e):>8.1%}")
    print("\n  This is the number that matters. The calibration table's 1.503 was")
    print("  measured on the days the member set was chosen on; this one is not.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--cities", default=None)
    ap.add_argument("--day", default=None)
    ap.add_argument("--force", action="store_true",
                    help="predict regardless of the local hour (testing)")
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()

    if a.calibrate:
        calibrate()
        return
    if a.score:
        score()
        return

    calib = load_calib()
    cities = ([c.strip().upper() for c in a.cities.split(",")] if a.cities
              else sorted(CITIES))
    bad = [c for c in cities if c not in CITIES]
    if bad:
        raise SystemExit(f"unknown cities: {bad}")
    print(f"pre-dawn 12h predictions, issuance {ISSUE_LOCAL_HOUR:02d}:00 local "
          f"+/-{ISSUE_TOLERANCE_H}h\n")
    probe = a.day or dt.datetime.now(dt.timezone.utc).date().isoformat()
    skip = set() if a.force else already_locked(probe)
    recs = predict(cities, calib, force=a.force, day=a.day, skip=skip)
    if not recs:
        print("  no city is at its issuance hour right now (use --force to override)")
        return
    if a.no_log:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    day = recs[0].get("day") or dt.date.today().isoformat()
    with io.open(os.path.join(LOG_DIR, f"{day}.jsonl"), "a", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + chr(10))
    print(f"\n  locked {len(recs)} prediction(s) to {LOG_DIR}/{day}.jsonl")
    print("  A forecast, not a signal. See the module docstring.")


if __name__ == "__main__":
    main()
