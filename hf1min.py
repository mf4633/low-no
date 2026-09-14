r"""1-minute settlement truth for EVERY Kalshi city.

WHY THIS EXISTS. Two gotchas in CLAUDE.md meet here.

  * Gotcha 11: the CLI product lives for exactly SEVEN DAYS. After that nothing
    can re-derive a settlement, and settlement errors do not decay -- they
    fossilise into station bias, climb tables and every variant downstream.
  * Gotcha 13: our own `run_max` is quantised to whole degrees C while the CLI
    settles in whole degrees F, so `settle - run_max` goes NEGATIVE on 13% of
    settled rows. An impossible value in the outcome variable is a WRONG LABEL,
    not noise, and it sits inside the empirical P(exceed) distribution.

The 1-minute ASOS record fixes both. It is reported in whole degrees F -- the
same unit the CLI settles in -- and the archive does not expire. The project has
already proved CLI == the 1-minute maximum on 260 station-days, but only across
the ELEVEN cities that got per-city offsets on 2026-09-12. This extends that
proof, and that ground truth, to all 23.

WHAT IT WRITES. `docs/settlements_1min.json`, keyed `day|CITY` exactly like
`docs/settlements.json`, holding the 1-minute maximum, the second-highest
minute (so a single-minute spike is visible rather than silently adopted) and
the observation count. It does NOT overwrite `docs/settlements.json`, does not
feed the gate, and decides nothing. It is a parallel, durable record that a
later grading pass can be checked against.

THE LOCAL-DAY TRAP, handled explicitly. The CLI day is the LOCAL midnight-to-
midnight climate day. `sources.asos_1min_max` requests a UTC day, which for a
western city starts seven hours late and ends seven hours early. The daily max
is usually mid-afternoon so it rarely bites -- "rarely bites" being precisely
the profile of every silent error this project has had to dig out afterwards.
This fetches a two-UTC-day span and filters to the city's own local date.

SOURCES. IEM's free 1-minute archive is primary and is the reason this keeps
working after any trial expires. A Synoptic HF-ASOS (network 258) path exists
for the same-day case IEM has not ingested yet; it is OFF unless asked for, and
it refuses any response with fewer than MIN_1MIN_OBS observations rather than
quietly recording an hourly feed as a 1-minute maximum.

Usage:  python hf1min.py                      (all graded days, all cities)
        python hf1min.py --day 2026-09-13
        python hf1min.py --cities SEA,SFO --day 2026-09-13 --synoptic
"""
import argparse
import datetime as dt
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zoneinfo
from collections import defaultdict

from lowno.config import CITIES

OUT = "docs/settlements_1min.json"
SETTLE = "docs/settlements.json"
LOG_DIR = "logs"
MIN_1MIN_OBS = 500      # a real 1-minute day has ~1440; below this, refuse
UA = {"User-Agent": "lowno (contact: github.com/mf4633)"}


# ------------------------------------------------------------------ IEM ------
def _iem_1min(site, day, tz):
    """[(utc_iso, tmpf)] for the city's LOCAL `day`, from IEM's 1-minute archive.

    Fetches [day, day+2) in UTC and filters on the local date, so the local
    climate day is fully covered in every US time zone.
    """
    d0 = dt.date(int(day[:4]), int(day[5:7]), int(day[8:10]))
    d1 = d0 + dt.timedelta(days=2)
    u = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos1min.py"
         f"?station={site}&tz=UTC"
         f"&year1={d0.year}&month1={d0.month}&day1={d0.day}"
         f"&year2={d1.year}&month2={d1.month}&day2={d1.day}"
         "&vars=tmpf&sample=1min&what=download&delim=comma")
    txt = _get(u, timeout=120)
    if txt is None:
        return None
    zone = zoneinfo.ZoneInfo(tz)
    utc = dt.timezone.utc
    hdr, out = None, []
    for line in txt.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = [c.strip() for c in line.split(",")]
        if hdr is None:
            hdr = parts
            continue
        try:
            # IEM has shipped this column as both "valid" and "valid(UTC)"
            ti = next(i for i, c in enumerate(hdr) if c.lower().startswith("valid"))
            vi = hdr.index("tmpf")
        except Exception:
            return None
        try:
            v = float(parts[vi])
        except Exception:
            continue
        s = parts[ti]
        try:
            t = dt.datetime(int(s[0:4]), int(s[5:7]), int(s[8:10]),
                            int(s[11:13]), int(s[14:16]), tzinfo=utc)
        except Exception:
            continue
        if t.astimezone(zone).date().isoformat() != day:
            continue
        out.append((t.isoformat().replace("+00:00", "Z"), v))
    return out


def _get(url, timeout=120, tries=4):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or a == tries - 1:
                print(f"    HTTP {e.code}")
                return None
        except Exception as e:
            if a == tries - 1:
                print(f"    {str(e)[:70]}")
                return None
        time.sleep(min(60, 4 * (2 ** a)))
    return None


# -------------------------------------------------------------- SYNOPTIC ----
def _token():
    t = os.environ.get("SYNOPTIC_API_TOKEN")
    if not t and os.path.exists(".synoptic_token"):
        t = io.open(".synoptic_token").read().strip()
    return t


def _synoptic_1min(station4, day, tz):
    """Same-day fallback while IEM has not ingested the 1-minute file yet.

    DELIBERATELY LOUD. Every Synoptic response is reported with the station id
    and observation count it actually returned, and anything below
    MIN_1MIN_OBS is refused. A 5-minute or hourly stream silently recorded as a
    1-minute maximum would understate the peak by the very 0.5-1F this file
    exists to recover, and it would do it invisibly.
    """
    tok = _token()
    if not tok:
        print("    synoptic: no token (SYNOPTIC_API_TOKEN or ./.synoptic_token)")
        return None
    zone = zoneinfo.ZoneInfo(tz)
    d0 = dt.datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), tzinfo=zone)
    d1 = d0 + dt.timedelta(days=1)
    q = urllib.parse.urlencode(dict(
        token=tok, stid=station4, network="258", vars="air_temp",
        start=d0.astimezone(dt.timezone.utc).strftime("%Y%m%d%H%M"),
        end=d1.astimezone(dt.timezone.utc).strftime("%Y%m%d%H%M"),
        units="temp|F", obtimezone="utc"))
    txt = _get("https://api.synopticdata.com/v2/stations/timeseries?" + q, timeout=120)
    if txt is None:
        return None
    try:
        j = json.loads(txt)
    except Exception:
        print("    synoptic: response was not JSON")
        return None
    stations = j.get("STATION") or []
    if not stations:
        print(f"    synoptic: no STATION rows for {station4} network 258 "
              f"({(j.get('SUMMARY') or {}).get('RESPONSE_MESSAGE')})")
        return None
    out = []
    for stn in stations:
        o = stn.get("OBSERVATIONS") or {}
        rows = list(zip(o.get("date_time") or [], o.get("air_temp_set_1") or []))
        print(f"    synoptic: STID={stn.get('STID')} n={len(rows)}")
        for ts, v in rows:
            if v is None:
                continue
            out.append((ts, float(v)))
    if len(out) < MIN_1MIN_OBS:
        print(f"    synoptic: {len(out)} obs < {MIN_1MIN_OBS} -- REFUSED, "
              f"this is not a 1-minute stream")
        return None
    return out


# ------------------------------------------------------------------ CORE -----
def harvest_day(city, day, use_synoptic=False):
    meta = CITIES[city]
    st4, site, tz = meta["station"], meta["station"][1:].upper(), meta["tz"]
    rows = _iem_1min(site, day, tz)
    src = "iem_1min"
    if not rows or len(rows) < MIN_1MIN_OBS:
        have = 0 if rows is None else len(rows)
        if use_synoptic:
            print(f"    iem gave {have} obs -- trying synoptic HF-ASOS")
            rows, src = _synoptic_1min(st4, day, tz), "synoptic_258"
        else:
            if have:
                print(f"    iem gave {have} obs (< {MIN_1MIN_OBS}) -- not recorded")
            return None
    if not rows or len(rows) < MIN_1MIN_OBS:
        return None
    vals = sorted((v for _, v in rows), reverse=True)
    top = max(rows, key=lambda r: r[1])
    return dict(max_f=vals[0], second_f=vals[1] if len(vals) > 1 else None,
                at=top[0], n_obs=len(rows), src=src)


def logged_run_max():
    """{day|CITY: max run_max we observed} from logs/<day>.jsonl.

    Reads the SAME rows the graders read -- any row with a numeric
    detail.run_max -- rather than filtering on a verdict label. Filtering on
    `verdict == "LADDER"` is what blinded the settlement quarantine to four
    whole days in August (CANDIDATE.md, LAX CLEARED).
    """
    out = {}
    if not os.path.isdir(LOG_DIR):
        return out
    for fn in sorted(os.listdir(LOG_DIR)):
        if not fn.endswith(".jsonl"):
            continue
        day = fn[:-6]
        for line in io.open(os.path.join(LOG_DIR, fn), encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            city = r.get("city")
            d = r.get("detail")
            if city not in CITIES or not isinstance(d, dict):
                continue
            rm = d.get("run_max")
            if not isinstance(rm, (int, float)):
                continue
            k = f"{day}|{city}"
            out[k] = rm if k not in out else max(out[k], rm)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", default=None)
    ap.add_argument("--day", default=None, help="one day; default every graded day")
    ap.add_argument("--since", default=None, help="YYYY-MM-DD lower bound")
    ap.add_argument("--synoptic", action="store_true",
                    help="allow the expiring HF-ASOS network-258 path when IEM is short")
    ap.add_argument("--sleep", type=float, default=0.3)
    a = ap.parse_args()

    cities = ([c.strip().upper() for c in a.cities.split(",")] if a.cities
              else sorted(CITIES))
    bad = [c for c in cities if c not in CITIES]
    if bad:
        raise SystemExit(f"unknown cities: {bad}")

    settled = json.loads(io.open(SETTLE, encoding="utf-8").read()) if os.path.exists(SETTLE) else {}
    if a.day:
        days = [a.day]
    else:
        days = sorted({k.split("|")[0] for k in settled})
    if a.since:
        days = [d for d in days if d >= a.since]
    # never the current ET date: an intraday fetch is a max-SO-FAR, and freezing
    # one is what manufactured the fake +5.0F SAT bias (gotcha 12).
    today_et = dt.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date().isoformat()
    dropped = [d for d in days if d >= today_et]
    days = [d for d in days if d < today_et]
    if dropped:
        print(f"skipping {len(dropped)} day(s) >= today ET ({today_et}): "
              f"an intraday 1-minute max is a max-so-far\n")

    have = json.loads(io.open(OUT, encoding="utf-8").read()) if os.path.exists(OUT) else {}
    print(f"{len(days)} day(s) x {len(cities)} cities; "
          f"{len(have)} already recorded\n")

    added = 0
    for day in days:
        for city in cities:
            k = f"{day}|{city}"
            if k in have:
                continue
            print(f"  {k}", flush=True)
            rec = harvest_day(city, day, use_synoptic=a.synoptic)
            if rec:
                have[k] = rec
                added += 1
                if added % 25 == 0:
                    io.open(OUT, "w", encoding="utf-8").write(json.dumps(have, sort_keys=True, indent=0))
            time.sleep(a.sleep)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(have, sort_keys=True, indent=0))
    print(f"\nwrote {OUT}: {len(have)} city-days (+{added} this run)\n")

    # ------------------------------------------------------------- report ----
    runmax = logged_run_max()
    per = defaultdict(lambda: dict(n=0, exact=0, within1=0, worse=0,
                                   dcli=[], drun=[], spike=0))
    for k, rec in have.items():
        day, city = k.split("|")
        if city not in cities:
            continue
        p = per[city]
        p["n"] += 1
        if rec.get("second_f") is not None and rec["max_f"] - rec["second_f"] >= 3.0:
            p["spike"] += 1
        c = settled.get(k)
        if isinstance(c, (int, float)):
            d = c - rec["max_f"]
            p["dcli"].append(d)
            if abs(d) < 0.5:
                p["exact"] += 1
            elif abs(d) <= 1.0:
                p["within1"] += 1
            else:
                p["worse"] += 1
        rm = runmax.get(k)
        if isinstance(rm, (int, float)):
            p["drun"].append(rec["max_f"] - rm)

    def mean(v):
        return (sum(v) / len(v)) if v else None

    def fmt(x, w, sign=True):
        if x is None:
            return "-".rjust(w)
        return (f"{x:+.2f}" if sign else f"{x:.2f}").rjust(w)

    hdr = (f"{'city':<5}{'n':>5}{'vs CLI':>8}{'exact':>7}{'<=1F':>6}{'>1F':>5}"
           f"{'1min-runmax':>13}{'min':>7}{'max':>7}{'spike':>7}")
    print("1-MINUTE MAX vs the two things it is supposed to correct")
    print(hdr)
    print("-" * len(hdr))
    for city in sorted(per, key=lambda c: -per[c]["n"]):
        p = per[city]
        dr = p["drun"]
        print(f"{city:<5}{p['n']:>5}"
              f"{fmt(mean(p['dcli']), 8)}"
              f"{p['exact']:>7}{p['within1']:>6}{p['worse']:>5}"
              f"{fmt(mean(dr), 13)}"
              f"{fmt(min(dr) if dr else None, 7)}"
              f"{fmt(max(dr) if dr else None, 7)}"
              f"{p['spike']:>7}")
    allc = [d for p in per.values() for d in p["dcli"]]
    allr = [d for p in per.values() for d in p["drun"]]
    if allc:
        print(f"\n  CLI minus 1-minute max over {len(allc)} city-days: "
              f"mean {mean(allc):+.3f}F")
    else:
        print("\n  no CLI overlap yet")
    if allr:
        print(f"  1-minute max minus our run_max over {len(allr)} city-days: "
              f"mean {mean(allr):+.3f}F, range {min(allr):+.2f} to {max(allr):+.2f}")
        print("  gotcha 13 bounds the run_max deficit at 1.8F (a full degC step). "
              "Anything\n  beyond that is something new and belongs in "
              "logaudit.py's CLIMB INTEGRITY.")
    print("\n  'spike' counts days where the top minute stands >=3F above the "
          "second.\n  The CLI is QC'd; a lone spike here is a candidate "
          "disagreement, not a max.")


if __name__ == "__main__":
    main()
