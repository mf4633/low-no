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


def sky_today(day):
    """{utc_hour: ceiling_ft or None} for `day`, read from IEM report_type=3.

    SAME SOURCE AS TRAINING -- this is the whole point. lax_regimes.json was
    built from IEM report_type=3, the ROUTINE :5x observation. Reading the live
    sky from api.weather.gov instead produced two separate failures on
    2026-09-12, both silent:

      * KLAX reports every ~5 min there, so a naive out[hour]=... kept the
        OLDEST ob in each hour (the feed is newest-first). Hour 16Z took its
        16:00Z BKN instead of its 16:53Z SCT.
      * and the routine :53 obs carry EMPTY cloudLayers there anyway -- only
        the 5-minute specials have cloud data -- so "nearest :53" then read
        clear when the hour was overcast.

    Either one flips the regime. The first turned EARLY_BURN into LATE_BURN,
    the frozen forecast said 74.8F against a market at 81-82, and the market
    was right: LAX printed 81. A 98-point "discrepancy" manufactured entirely
    by a train/serve mismatch -- the same shape as the 53-minute proxy-align
    lag. H15 is registered on this classifier, so a silent mismatch here would
    score every observation against the wrong cell and look like the hypothesis
    failing.

    IEM also runs AHEAD of api.weather.gov on live obs (measured 2026-09-11 and
    -12: NWS up to an hour behind), so there is no recency cost either.
    """
    import csv
    y, m, d = day[:4], day[5:7], day[8:10]
    nxt = (dt.date(int(y), int(m), int(d)) + dt.timedelta(days=1)).isoformat()
    u = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=LAX"
         "&data=skyc1&data=skyl1&data=skyc2&data=skyl2"
         f"&year1={y}&month1={m}&day1={d}"
         f"&year2={nxt[:4]}&month2={nxt[5:7]}&day2={nxt[8:10]}"
         "&tz=UTC&format=onlycomma&latlon=no&missing=M&trace=T&direct=no"
         "&report_type=3")
    try:
        txt = sources._get_text(u, timeout=45) if hasattr(sources, "_get_text") else None
    except Exception:
        txt = None
    if txt is None:
        import urllib.request
        try:
            txt = urllib.request.urlopen(u, timeout=45).read().decode()
        except Exception as e:
            print(f"  sky fetch failed: {str(e)[:60]}")
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
