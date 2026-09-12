"""LAX book vs the FROZEN regime forecast. Read-only, logs, decides nothing.

WHAT THIS IS NOT. It does not re-fit lax_regime.py or lax_forecast.py, both of
which were frozen 2026-09-12 before any LAX orderbook existed. It does not
produce a trade. H15's verdict is a scored comparison at 20 marine-stratum
days, NOT a series of daily eyeball calls -- looking at a discrepancy and
adjusting the model is precisely how a pre-registration dies, so the model
inputs are imported, never edited here.

WHAT IT IS. A daily record: today's regime, the frozen conditional forecast,
the live ladder, and the per-bucket difference. Appended to logs/lax_book/ so
H15 can be scored later on what was actually believed at the time, rather than
reconstructed.

READ THE OUTPUT AS A MEASUREMENT, NOT A SIGNAL. The 2026-09-12 price comparison
found the market 3.2x better calibrated than our model at KNYC/KDEN, and
trading our disagreements lost 5.8-6.7c per trade at every margin tested. The
prior on any discrepancy shown here is that the market is right.
"""
import argparse, datetime as dt, io, json, os, sys
from collections import defaultdict

from lowno import sources
from lowno.config import CITIES
import lax_regime as LR
import lax_forecast as LF

OUT_DIR = "logs/lax_book"
CITY, STATION = "LAX", "KLAX"


CACHE_DIR = "logs/lax_sky"


def _iem_sky(day):
    """Raw IEM report_type=3 sky CSV for `day`, with backoff and a local cache.

    SAME SOURCE, JUST MORE PATIENT. The temptation when IEM 503s is to fall back
    to another feed. Do not. On 2026-09-12 reading the live sky from
    api.weather.gov instead of IEM flipped EARLY_BURN to LATE_BURN two different
    ways -- its 5-minute obs made a naive hour key take the OLDEST ob, and its
    routine :53 obs carry empty cloudLayers -- and the frozen forecast then said
    74.8F against a market at 81-82 that was right. H15 is registered on this
    classifier; a silent source disagreement scores every observation against
    the wrong cell and looks like the hypothesis failing.

    (HF-ASOS KLAX1M was checked as a fallback and does agree exactly -- oktas
    2/4/6/8 map to FEW/SCT/BKN/OVC with identical bases on all 14 overlapping
    hours of 2026-09-12. It is still not wired in: the trial expires 2026-09-14
    and H15 runs to ~2026-11-20, so it would be a dependency that dies before
    the first marine day, validated on one station on one day.)

    Cached under logs/lax_sky/ once the day is complete, so a later outage
    cannot erase a day already observed.
    """
    import csv, time, random, urllib.request, urllib.error
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, f"{day}.csv")
    if os.path.exists(cache) and os.path.getsize(cache) > 200:
        return io.open(cache, encoding="utf-8").read()
    y, m, d = day[:4], day[5:7], day[8:10]
    nxt = (dt.date(int(y), int(m), int(d)) + dt.timedelta(days=1)).isoformat()
    u = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=LAX"
         "&data=skyc1&data=skyl1&data=skyc2&data=skyl2"
         f"&year1={y}&month1={m}&day1={d}"
         f"&year2={nxt[:4]}&month2={nxt[5:7]}&day2={nxt[8:10]}"
         "&tz=UTC&format=onlycomma&latlon=no&missing=M&trace=T&direct=no"
         "&report_type=3")
    txt = None
    for attempt in range(6):
        try:
            txt = urllib.request.urlopen(u, timeout=60).read().decode()
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 5:
                print(f"  IEM sky fetch failed: HTTP {e.code}")
                return None
            w = min(120, (2 ** attempt) * 5) + random.uniform(0, 3)
            print(f"  IEM {e.code} -- backoff {w:.0f}s (attempt {attempt + 1}/6)")
            time.sleep(w)
        except Exception as e:
            print(f"  IEM sky fetch failed: {str(e)[:60]}")
            return None
    if txt is None or len(txt) < 200:
        return None
    # cache only a COMPLETE day -- a partial day cached mid-afternoon would
    # freeze the regime before the burn-off window has closed
    if day < dt.datetime.now(dt.timezone.utc).date().isoformat():
        io.open(cache, "w", encoding="utf-8").write(txt)
    return txt


def sky_today(day):
    """{utc_hour: ceiling_ft or None} for `day`, from IEM report_type=3.

    Matches the source AND report type lax_regimes.json was built from: the
    routine :5x observation, one per hour. See _iem_sky for why this must not
    silently fall back to another feed.
    """
    import csv
    txt = _iem_sky(day)
    if not txt:
        return {}
    out = {}
    for r in csv.DictReader(io.StringIO(txt)):
        v = r.get("valid", "")
        if v[:10] != day:
            continue
        lo = None
        for c, l in ((r.get("skyc1"), r.get("skyl1")),
                     (r.get("skyc2"), r.get("skyl2"))):
            if c in ("BKN", "OVC") and l not in ("M", "", None):
                try:
                    ft = float(l)
                except Exception:
                    continue
                lo = ft if lo is None else min(lo, ft)
        out[int(v[11:13])] = lo
    return out


def ladder():
    ymd = dt.datetime.now(dt.timezone.utc).strftime("%y%b%d").upper()
    try:
        return sources.kalshi_ladder(CITIES[CITY]["series"], ymd, probe_path=None) or []
    except Exception as e:
        print(f"  ladder fetch failed: {str(e)[:60]}")
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None, help="UTC date, default today")
    a = ap.parse_args()
    day = a.day or dt.datetime.now(dt.timezone.utc).date().isoformat()

    obs = sky_today(day)
    if len(obs) < 6:
        print(f"  only {len(obs)} hourly sky obs for {day} -- too early to classify")
        return
    reg = LR.regime(obs)
    fc = LF.forecast(reg, day)
    hrs = sorted(obs)
    print(f"\nKLAX {day}   regime {reg}   (sky hours {hrs[0]:02d}Z-{hrs[-1]:02d}Z)")
    print(f"  forecast cell: n={fc['n']}  mean {fc['mean']:.1f}  [{fc['source']}]")
    if fc["n"] == 0:
        return

    rows = ladder()
    if not rows:
        print("  no ladder"); return
    print(f"\n  {'ticker':<28}{'floor':>6}{'cap':>5}{'mkt YES':>9}{'model':>8}{'diff':>8}")
    recs = []
    for g in rows:
        fl, cap, ya = g.get("floor"), g.get("cap"), g.get("yes_ask")
        if ya is None:
            continue
        lo = fl if fl is not None else -999
        hi = cap if cap is not None else 999
        pm = sum(p for k, p in fc["dist"].items() if lo <= k <= hi)
        recs.append(dict(ticker=g.get("ticker"), floor=fl, cap=cap,
                         mkt=ya / 100.0, model=round(pm, 4),
                         diff=round(pm - ya / 100.0, 4)))
        print(f"  {str(g.get('ticker')):<28}{str(fl):>6}{str(cap):>5}"
              f"{ya/100.0:>9.2f}{pm:>8.2f}{pm - ya/100.0:>+8.2f}")
    os.makedirs(OUT_DIR, exist_ok=True)
    with io.open(os.path.join(OUT_DIR, f"{day}.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(
            at=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            day=day, city=CITY, regime=reg, marine=reg in LF.MARINE,
            cell_n=fc["n"], cell_mean=round(fc["mean"], 2), cell_src=fc["source"],
            rungs=recs)) + chr(10))
    big = [r for r in recs if abs(r["diff"]) >= 0.15]
    print(f"\n  logged to {OUT_DIR}/{day}.jsonl")
    print(f"  marine stratum: {reg in LF.MARINE}   rungs diverging >=15pts: {len(big)}")
    if big:
        print("  NOTE: a divergence is a measurement, not a signal. The market was")
        print("        3.2x better calibrated than this class of model at KNYC/KDEN.")


if __name__ == "__main__":
    main()
