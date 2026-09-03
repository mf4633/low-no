"""The registered nowcast, run on Synoptic observations instead of api.weather.gov.

WHY. The interpolator's binding constraint was never the algorithm, it was the
feed: the 5-minute stations surface in the NWS API 10-25 minutes late, so
every estimate was 15-25 minutes old at scan time and "do not project it
forward" was the rule. Measured 2026-09-03 01:25Z, Synoptic's timeseries had
the same stations +5 to +20 minutes fresher (median +10; the three 20-minute
sites +20). That is roughly half the lag gone -- IF the estimate built on it
is as good. This script measures that instead of assuming it.

HOW. hourly_nowcast.estimate() is NOT modified. Its station reader
(`_series`) is swapped for a Synoptic-backed one for the duration of one call,
so the exact registered algorithm -- same alignment, quorum, window, residual
table -- runs on the fresher obs. Both estimates are printed and logged side
by side with their as-of times, so the comparison is between feeds and
nothing else.

WHAT THIS IS NOT. Not a change to the scan, the registered nowcast, H7's
inputs, or anything that feeds a ladder, band, variant or gate. The log goes
to logs/synoptic_nowcast/<day>.jsonl, a subdirectory the scan globs do not
match. If the Synoptic estimate proves better against the next host print,
that is a registration, not a swap.

TOKEN. Read from SYNOPTIC_API_TOKEN or ./.synoptic_token (gitignored). The
30-day trial serves network 1 (ASOS/AWOS) at 5-minute cadence; KDEN and KNYC
themselves stay hourly on it (the 1-minute stream is network 258, HF-ASOS,
not in the trial), so the HOST print is the same on both feeds -- only the
neighbours are fresher.

Usage:  python synoptic_nowcast.py            (DEN and NYC, log)
        python synoptic_nowcast.py --archive  (also store raw obs per station/day)
"""
import argparse
import datetime as dt
import json
import os
import urllib.parse
import urllib.request

from lowno import hourly_nowcast as HN

C2F = lambda c: None if c is None else round(c * 9 / 5 + 32, 2)


def token():
    t = os.environ.get("SYNOPTIC_API_TOKEN")
    if not t and os.path.exists(".synoptic_token"):
        t = open(".synoptic_token").read().strip()
    if not t:
        raise SystemExit("no SYNOPTIC_API_TOKEN in env and no .synoptic_token file")
    return t


def fetch(stations, minutes=180):
    q = urllib.parse.urlencode(dict(token=token(), stid=",".join(stations), recent=str(minutes),
                                    vars="air_temp", units="temp|C", obtimezone="utc"))
    req = urllib.request.Request("https://api.synopticdata.com/v2/stations/timeseries?" + q,
                                 headers={"User-Agent": "lowno (contact: github.com/mf4633)"})
    j = json.load(urllib.request.urlopen(req, timeout=90))
    out = {}
    for st in j.get("STATION") or []:
        o = st.get("OBSERVATIONS") or {}
        rows = []
        for ts, v in zip(o.get("date_time") or [], o.get("air_temp_set_1") or []):
            if v is None:
                continue
            rows.append((ts[:16] + "Z", C2F(float(v))))
        out[st["STID"]] = sorted(dict(rows).items())
    return out


def run(city, cache, now):
    host, nbrs = HN.HOSTS[city]
    # registered feed
    nws_val, nws_det = HN.estimate(city, 0.0, now)
    # same algorithm, Synoptic feed
    orig = HN._series
    HN._series = lambda station, limit=60: cache.get(station, [])
    try:
        syn_val, syn_det = HN.estimate(city, 0.0, now)
    finally:
        HN._series = orig
    return nws_det, syn_det


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", action="store_true")
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    stations = sorted({s for c in HN.HOSTS for s in [HN.HOSTS[c][0], *HN.HOSTS[c][1]]})
    cache = fetch(stations)
    if a.archive:
        for st, rows in cache.items():
            for ts, v in rows:
                day = ts[:10]
                p = f"logs/synoptic/{st}/{day}.json"
                os.makedirs(os.path.dirname(p), exist_ok=True)
                cur = json.load(open(p)) if os.path.exists(p) else {}
                cur[ts] = v
                json.dump(cur, open(p, "w"), sort_keys=True)
    print(f"{now.strftime('%H:%MZ')}   {'city':5} {'feed':9} {'nowcast':>8} {'as_of':>7} {'age':>5} {'nbrs':>5} {'spread':>7}  print")
    for city in HN.HOSTS:
        nws, syn = run(city, cache, now)
        for label, d in (("nws", nws), ("synoptic", syn)):
            if isinstance(d, dict):
                print(f"          {city:5} {label:9} {d['nowcast_f']:>8.2f} {d['as_of'][11:16]:>7} "
                      f"{d['age_of_estimate_min']:>4}m {d['n_neighbours']:>2}/{d['n_expected']:<2} "
                      f"{d.get('spread_f', 0):>7.2f}  {d['last_print_f']} @{d['last_print_at'][11:16]}Z")
            else:
                print(f"          {city:5} {label:9} refused: {d}")
        if not a.no_log:
            os.makedirs("logs/synoptic_nowcast", exist_ok=True)
            with open(f"logs/synoptic_nowcast/{now.date().isoformat()}.jsonl", "a") as fh:
                fh.write(json.dumps(dict(at=now.isoformat().replace("+00:00", "Z"), city=city,
                                         nws=nws if isinstance(nws, dict) else dict(refused=nws),
                                         synoptic=syn if isinstance(syn, dict) else dict(refused=syn))) + "\n")


if __name__ == "__main__":
    main()
