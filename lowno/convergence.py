"""Per-station convergence: when does the day stop being uncertain?

Two questions the ledger could not previously answer:

  1. INFORMATION HOUR -- how fast does each station's outcome become knowable?
     Denver's high can print at 5 PM off downslope flow; SFO's fate is usually
     sealed by the 11 AM burn-off verdict. A flag taken at 10:00 local means
     something different at those two stations, and the entry window is currently
     one-size-fits-all.

  2. BOUNDARY RESOLUTION -- when settlement lands within 1F of a ceiling, the
     tenths decide. Hourly METAR undersamples the true peak; the 1-minute ASOS
     max is the tiebreaker. This module pairs them so the BOUNDARY attribution
     stops being a shrug.

Pure analysis over logged data. No gate input, no trading effect.
"""
import json, glob, os, datetime as dt, zoneinfo
from collections import defaultdict
from .config import CITIES


def _settles():
    out = {}
    try:
        for k, v in json.load(open("docs/settlements.json")).items():
            d, c = k.split("|")
            out[(d, c)] = v
    except Exception:
        pass
    return out


def build(min_n=8):
    """Per (city, local hour): how close the running max already is to the final
    settle, and how often the remaining climb still spans a typical ceiling gap."""
    settles = _settles()
    cells = defaultdict(list)
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
            rm = d.get("run_max")
            city = r.get("city")
            s = settles.get((day, city))
            if rm is None or s is None or city not in CITIES:
                continue
            lh = (dt.datetime.fromisoformat(r["at"])
                    .replace(tzinfo=dt.timezone.utc)
                    .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])).hour)
            cells[(city, lh)].append(round(s - rm, 1))

    out = {}
    for (city, lh), v in cells.items():
        v = sorted(v)
        n = len(v)
        q = lambda f: v[min(n - 1, int(f * n))]
        resolved = sum(1 for x in v if x <= 1.0) / n     # within 1F of final
        out[f"{city}|{lh:02d}"] = dict(
            n=n, remaining_q10=q(.10), remaining_q50=q(.50), remaining_q90=q(.90),
            frac_resolved_1F=round(resolved, 3), ready=bool(n >= min_n))

    # Convergence hour = earliest local hour where the median remaining climb is
    # <= 1F on a ready cell. None until a station has earned it.
    conv = {}
    for city in CITIES:
        hrs = sorted(int(k.split("|")[1]) for k in out if k.startswith(city + "|"))
        found = None
        for h in hrs:
            c = out[f"{city}|{h:02d}"]
            if c["ready"] and c["remaining_q50"] <= 1.0:
                found = h
                break
        conv[city] = found
    return dict(cells=out, convergence_hour_local=conv,
                note="convergence_hour = first local hour whose median remaining "
                     "climb is <=1F on a cell with n>=min_n; None = not yet earned")


def boundary_report():
    """Flags that settled within 1F of their ceiling, with the 1-min ASOS max
    beside the CLI value -- the cases where rounding decided the trade."""
    try:
        led = json.load(open("docs/ledger.json"))
    except Exception:
        return []
    rows = []
    for day in led.get("days", []):
        for f in day.get("flags", []):
            s, cap = f.get("settle"), (f.get("detail") or {}).get("ceiling")
            if s is None or cap is None:
                continue
            if abs(s - cap) <= 1:
                rows.append(dict(date=day["date"], city=f.get("city"), ceiling=cap,
                                 cli=s, margin=s - cap,
                                 attribution=f.get("attribution")))
    return rows
