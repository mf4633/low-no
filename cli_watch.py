"""CLI issuance watch: what the 1-minute record has ALREADY done today.

WHY. On 2026-09-02 the DEN 89-90 market collapsed at 22:35Z. That was the
minute NWS issued the intraday CLIDEN "valid as of 4 PM" with MAXIMUM 88 at
2:59 PM. I was quoting settlement odds from a nine-day offset table while the
answer sat in a public product; the market read it and I did not. Kalshi
settles on the CLI, the CLI is computed from the 1-minute ASOS data, and the
intraday issuances (typically valid as of 4 PM, 5 PM, 6 PM local, then the
final after midnight) publish that record hours before settlement.

Rule this file enforces: on any day the max is in question, read every CLI
issuance for the trading date BEFORE quoting odds. Predict the future; look
up the past. Buckets the record has already ruled out are printed as such.

WHAT IT DOES
  * Lists every CLI product for the station's SITE (products are indexed by
    site, not WFO -- gotcha #4) whose summary date is the local trading date:
    issuance time, "valid as of" stamp or FINAL, MAXIMUM and its clock time.
  * Compares the CLI max-so-far with the hourly prints from api.weather.gov,
    so the offset (CLI minus hourly max) is visible as it develops.
  * Reads the live Kalshi ladder and marks every bucket whose cap is BELOW the
    CLI max-so-far as impossible (the settle cannot come down), and the bucket
    that already contains it.
  * Appends each run to logs/cli/<CITY>/<day>.jsonl (a subdirectory that
    glob("logs/2*.jsonl") does not match: nothing here reaches a ladder, a
    band, a variant, the gate or any registered test).

Telemetry only. Nothing here changes what the scan writes.

Usage:  python cli_watch.py DEN        python cli_watch.py NYC --no-log
"""
import argparse
import datetime as dt
import json
import os
import re
import zoneinfo

from lowno import sources
from lowno.config import CITIES


def issuances(site, day):
    """Every CLI product for `site` whose summary date is `day`, newest first."""
    try:
        graph = sources._get(f"https://api.weather.gov/products/types/CLI/locations/{site}",
                             timeout=25).get("@graph", [])
    except Exception as e:
        return [], f"product list failed: {str(e)[:60]}"
    out = []
    # Products for `day` are issued on `day` (intraday) and the next UTC day
    # (the final, after local midnight). Filter the listing by issuance date
    # before fetching text: the first version took the 12 newest products,
    # which is ~3 days of issuances, so a backtest saw nothing older.
    nxt = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
    for item in graph:
        it = (item.get("issuanceTime") or "")[:10]
        if it not in (day, nxt):
            continue
        try:
            text = sources._get(item["@id"], timeout=25).get("productText", "") or ""
        except Exception:
            continue
        awips, summary, maxf = sources._parse_cli(text)
        if awips != "CLI" + site or summary != day:
            continue
        valid = re.search(r"VALID (?:TODAY )?AS OF\s+(\d{3,4})\s*([AP]M)", text)
        mx = re.search(r"MAXIMUM\s+(-?\d+)([A-Z])?\s+(\d{1,2}:?\d{2}\s*[AP]M)", text)
        mn = re.search(r"MINIMUM\s+(-?\d+)([A-Z])?\s+(\d{1,2}:?\d{2}\s*[AP]M)", text)
        iss = item.get("issuanceTime") or ""
        out.append(dict(
            issued=iss, final=(iss[:10] > day),
            valid_as_of=(f"{valid.group(1)} {valid.group(2)}" if valid else ("FINAL" if iss[:10] > day else "?")),
            max_f=maxf, max_flag=(mx.group(2) if mx else None), max_at=(mx.group(3) if mx else None),
            min_f=(int(mn.group(1)) if mn else None), min_at=(mn.group(3) if mn else None)))
    out.sort(key=lambda r: r["issued"], reverse=True)
    return out, None


def hourly_prints(station, day, tz):
    """(local HH:MM, temp F) for every METAR print on the local day so far."""
    # Bounded by the local day, not by a count: a limit of 60 was silently
    # dropping half the hourly prints (every other hour was missing on the
    # first run). Duplicate timestamps collapse to one.
    d0 = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(0), tz).astimezone(dt.timezone.utc)
    d1 = d0 + dt.timedelta(days=1)
    try:
        j = sources._get(f"https://api.weather.gov/stations/{station}/observations"
                         f"?start={d0.isoformat().replace('+00:00', 'Z')}"
                         f"&end={d1.isoformat().replace('+00:00', 'Z')}&limit=500", timeout=30)
    except Exception:
        return []
    rows = {}
    for f in j.get("features", []):
        p = f.get("properties") or {}
        v = (p.get("temperature") or {}).get("value")
        t = p.get("timestamp")
        if v is None or not t:
            continue
        lt = dt.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(tz)
        if lt.date().isoformat() == day:
            rows[lt.strftime("%H:%M")] = round(v * 9 / 5 + 32, 1)
    return sorted(rows.items())


def ladder(city, day):
    # Ticker date is the LOCAL trading date, never the UTC date -- after 18:00
    # local the UTC date is tomorrow and this would fetch tomorrow's ladder
    # (gotcha #5). Caught on the first run: 00:28Z showed the Sep 3 board.
    ymd = dt.date.fromisoformat(day).strftime("%y%b%d").upper()
    try:
        rungs = sources.kalshi_ladder(CITIES[city]["series"], ymd, probe_path=None) or []
    except Exception:
        return []
    out = []
    for g in rungs:
        fl, cap = g.get("floor"), g.get("cap")
        lab = (f"<={cap}" if fl is None else (f">={fl}" if cap is None else f"{fl}-{cap}"))
        out.append(dict(label=lab, floor=fl, cap=cap, yes_bid=g.get("yes_bid"),
                        yes_ask=g.get("yes_ask"), vol=g.get("vol")))
    return out


def _stamp_hour(valid):
    """'0400 PM' -> 16, 'FINAL' -> 99, unknown -> None."""
    if valid == "FINAL":
        return 99
    m = re.match(r"(\d{1,2})(\d{2})\s*([AP]M)", valid or "")
    if not m:
        return None
    h = int(m.group(1)) % 12 + (12 if m.group(3) == "PM" else 0)
    return h


def _bucket_of(rungs, value):
    for g in rungs:
        fl, cap = g.get("fl"), g.get("cap")
        if (fl is None or fl <= value) and (cap is None or value <= cap):
            return g
    return None


def _next_up(rungs, g):
    if g is None or g.get("cap") is None:
        return None
    cands = [r for r in rungs if r.get("fl") is not None and r["fl"] > g["cap"]]
    return min(cands, key=lambda r: r["fl"]) if cands else None


def backtest(city, ndays):
    """For each of the last `ndays` local days: every intraday issuance's max vs
    the FINAL, the clock time of the final max, and -- from the scan's own
    logged ladders -- what the market charged for the next bucket UP right
    after the 4 PM issuance, against whether the final actually got there.

    The CLI is fetchable for ~7 days (gotcha #11), so this is bounded by the
    API, not by choice. logs/cli/ grows the record from here on.
    """
    cfg = CITIES[city]
    tz = zoneinfo.ZoneInfo(cfg["tz"])
    site = cfg["station"][1:].upper()
    today = dt.datetime.now(tz).date()
    print(f"{'day':11}{'4PM':>5}{'5PM':>5}{'6PM':>5}{'FINAL':>7}{'final at':>10}   "
          f"{'4PM bucket':>11}{'next-up':>9}{'YES@next':>9}{'scan at':>8}  outcome")
    n = hit = 0
    resid = []
    for i in range(ndays, 0, -1):
        day = (today - dt.timedelta(days=i)).isoformat()
        iss, err = issuances(site, day)
        if not iss:
            print(f"{day:11}  (no CLI products in the API window)")
            continue
        by = {}
        for r in iss:
            h = _stamp_hour(r["valid_as_of"])
            if h is not None and r["max_f"] is not None:
                by[h] = r
        final = by.get(99)
        m4, m5, m6 = (by.get(h, {}).get("max_f") for h in (16, 17, 18))
        fmax = final["max_f"] if final else None
        # market right after the 4 PM issuance, from the scan's logged ladders
        mkt = "--"
        scan_at = "--"
        b4 = nxt = None
        if m4 is not None and by.get(16):
            t4 = by[16]["issued"]
            try:
                for line in open(f"logs/{day}.jsonl"):
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    d = row.get("detail")
                    if row.get("city") != city or not isinstance(d, dict) or not d.get("rungs"):
                        continue
                    if row["at"].replace("+00:00", "Z")[:16] < t4[:16]:
                        continue
                    b4 = _bucket_of(d["rungs"], m4)
                    nxt = _next_up(d["rungs"], b4)
                    if nxt is not None:
                        ya = nxt.get("ya")
                        mkt = f"{ya}" if ya is not None else "--"
                    scan_at = row["at"][11:16] + "Z"
                    break
            except OSError:
                pass
        outcome = "--"
        if fmax is not None and m4 is not None:
            n += 1
            went_up = fmax > m4
            hit += went_up
            outcome = f"final {'ABOVE' if went_up else '=='} 4PM max"
            if mkt != "--" and nxt is not None:
                resid.append((int(mkt), went_up and (nxt["fl"] <= fmax <= (nxt["cap"] or 999))))
        lab = lambda g: ("--" if g is None else (f"<={g['cap']}" if g.get("fl") is None
                         else (f">={g['fl']}" if g.get("cap") is None else f"{g['fl']}-{g['cap']}")))
        fat = (final.get("max_at") if final else None) or "--"
        print(f"{day:11}{str(m4):>5}{str(m5):>5}{str(m6):>5}{str(fmax):>7}"
              f"{fat:>10}   {lab(b4):>11}{lab(nxt):>9}{mkt:>9}{scan_at:>8}  {outcome}")
    if n:
        print(f"\nfinal ABOVE the 4 PM max on {hit}/{n} days")
    if resid:
        print(f"market YES on the next-up bucket after the 4 PM issuance vs whether the final landed there:")
        for price, landed in resid:
            print(f"   priced {price}c -> {'LANDED' if landed else 'did not'}")
        print(f"   mean price {sum(p for p, _ in resid) / len(resid):.1f}c   "
              f"realised {100 * sum(1 for _, l in resid if l) / len(resid):.0f}%   n={len(resid)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("city", nargs="?", default="DEN")
    ap.add_argument("--day", help="local trading date YYYY-MM-DD (default today; tomorrow shows the board with no record yet)")
    ap.add_argument("--backtest", type=int, metavar="NDAYS", help="walk the last NDAYS days instead")
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    cfg = CITIES[a.city]
    tz = zoneinfo.ZoneInfo(cfg["tz"])
    station = cfg["station"]
    site = station[1:].upper()
    if a.backtest:
        backtest(a.city, a.backtest)
        return
    day = a.day or dt.datetime.now(tz).date().isoformat()
    now = dt.datetime.now(dt.timezone.utc)

    iss, err = issuances(site, day)
    prints = hourly_prints(station, day, tz)
    hmax = max((t for _, t in prints), default=None)
    hmax_at = next((h for h, t in prints if t == hmax), None) if hmax is not None else None

    print(f"CLI{site} for {day} ({a.city}), checked {now.strftime('%H:%MZ')}")
    if err:
        print("  " + err)
    if not iss:
        print("  no CLI issuance for today yet (first is usually 'valid as of 4 PM', ~22:30Z at DEN)")
    for r in iss:
        print(f"  {r['issued'][11:16]}Z  {'FINAL' if r['final'] else 'valid as of ' + r['valid_as_of']:>22}  "
              f"MAXIMUM {r['max_f']}{r['max_flag'] or ''} at {r['max_at']}   "
              f"(min {r['min_f']} at {r['min_at']})")

    cli_max = iss[0]["max_f"] if iss else None
    print(f"\nhourly prints today: " + ("  ".join(f"{h} {t:.0f}" for h, t in prints) if prints else "none"))
    if hmax is not None:
        print(f"hourly max {hmax:.0f} at {hmax_at}"
              + (f"   CLI max-so-far {cli_max} (offset {cli_max - round(hmax):+d}) "
                 f"through {iss[0]['valid_as_of']}" if cli_max is not None else ""))

    L = ladder(a.city, day)
    if L and cli_max is not None:
        print(f"\nladder vs the record (settle >= {cli_max} is ALREADY TRUE"
              f"{' and final' if iss[0]['final'] else ' through ' + iss[0]['valid_as_of']}):")
        for g in L:
            cap = g["cap"]
            if cap is not None and cap < cli_max:
                state = "IMPOSSIBLE  (cap below the record)"
            elif (g["floor"] is None or g["floor"] <= cli_max) and (cap is None or cli_max <= cap):
                state = "CONTAINS the record" + ("  <- settles here if nothing higher" if not iss[0]["final"] else "  <- SETTLES HERE")
            else:
                state = "needs a higher minute than any seen so far"
            print(f"  {g['label']:7} YES {str(g['yes_bid']):>4}/{str(g['yes_ask']):<4} {state}")
        if not iss[0]["final"]:
            print("  A later issuance can only RAISE the max. It cannot lower it.")

    if not a.no_log:
        os.makedirs(f"logs/cli/{a.city}", exist_ok=True)
        with open(f"logs/cli/{a.city}/{day}.jsonl", "a") as fh:
            fh.write(json.dumps(dict(at=now.isoformat().replace("+00:00", "Z"), city=a.city, day=day,
                                     issuances=iss, hourly_max=hmax, hourly_max_at=hmax_at,
                                     ladder=L)) + "\n")


if __name__ == "__main__":
    main()
