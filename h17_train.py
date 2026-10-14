"""Build h17_train.json -- the FROZEN training set for H17 (2026-10-14).

One row per KLAX day, 2022-01-01..2025-12-31 ONLY (no 2026 day: 8/10-9/11 were
looked at for the H15 backtest the same day, and everything after is H15/H17's
forward data). Same source and report type the H15 classifier was built on:
IEM asos.py report_type=3, the routine hourly ob, keyed by UTC hour.

Row: [day, cell, t18, max_to18, cli]
  cell     h15_lax.model_cell's label at the 18Z cut: NO_STRATUS / EARLY_BURN /
           MARINE (LATE_BURN+NO_BURN pooled -- NO_BURN is not knowable at 18Z)
  t18      tmpf of the 18Z-hour routine ob (~18:53Z)
  max_to18 max tmpf over that UTC day's routine obs through hour 18 (13Z-18Z;
           earlier hours are the previous local evening and are excluded)
  cli      the CLI high (IEM cli.py), the settled quantity
Run once; the output is committed and never regenerated.
"""
import csv, io, json, time, urllib.request
import lax_regime as LR
import h15_lax as H


def get(u):
    for a in range(6):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "lowno/1.0"})
            return urllib.request.urlopen(req, timeout=600).read().decode()
        except Exception:
            if a == 5:
                raise
            time.sleep(8 * (a + 1))


rows = []
for y in (2022, 2023, 2024, 2025):
    cli = {}
    for r in json.loads(get(f"https://mesonet.agron.iastate.edu/json/cli.py?station=KLAX&year={y}")).get("results") or []:
        h = r.get("high")
        try:
            cli[r["valid"][:10]] = float(h)
        except Exception:
            pass
    txt = get("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=LAX"
              "&data=tmpf&data=skyc1&data=skyl1&data=skyc2&data=skyl2"
              f"&year1={y}&month1=1&day1=1&year2={y + 1}&month2=1&day2=1"
              "&tz=UTC&format=onlycomma&latlon=no&missing=M&trace=T&direct=no&report_type=3")
    sky, tmp = {}, {}
    for r in csv.DictReader(io.StringIO(txt)):
        v = r["valid"]; d, h = v[:10], int(v[11:13])
        sky.setdefault(d, {})[h] = LR.ceil_ft(r)
        try:
            tmp.setdefault(d, {})[h] = float(r["tmpf"])
        except Exception:
            pass
    n0 = len(rows)
    for d in sorted(sky):
        o, t = sky[d], tmp.get(d, {})
        if d not in cli or not all(h in o for h in range(12, 19)) or 18 not in t:
            continue
        g = H.regime_at_cut(o)
        cell = "MARINE" if g in ("LATE_BURN", "NO_BURN") else g
        mx = max(v for h, v in t.items() if 13 <= h <= 18)
        rows.append([d, cell, t[18], mx, cli[d]])
    print(y, len(rows) - n0, "days")

json.dump(rows, open("h17_train.json", "w"))
print("total", len(rows))
