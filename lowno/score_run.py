"""Nightly entry point: grade today's flags against CLI settlements, write REPORT.md."""
import json, glob, os, zoneinfo, datetime as dt
from . import score, sources
from .config import CITIES

WFO = dict(AUS="EWX", CHI="LOT", DEN="BOU", LAX="LOX", MIA="MFL",
           NYC="OKX", PHL="PHI", PHX="PSR", SEA="SEW", SFO="MTR")

def main():
    # The nightly cron fires at 02:05 UTC, which is 10:05 PM ET the PREVIOUS day.
    # dt.date.today() on a UTC runner therefore named tomorrow's log file and
    # graded a day that had not happened yet. Score the ET trading day.
    day = dt.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date().isoformat()
    path = f"logs/{day}.jsonl"
    flags = []
    if not os.path.exists(path):
        print(f"no scan log for {day} -- writing empty day (valid observation)")
    else:
        for line in open(path):
            r = json.loads(line)
            if r["verdict"] in ("QUALIFIED", "DEAD_SCAVENGE"):
                flags.append(r)
    # de-dup to last flag per city
    last = {f["city"]: f for f in flags}
    settles = {}
    for city in last:
        try:
            m, _ = sources.cli_max(CITIES[city]["station"], WFO[city])
            settles[city] = m
        except Exception:
            settles[city] = None
    graded = []
    for f in last.values():
        s = settles.get(f["city"])
        graded.append(dict(date=day, city=f["city"], station=f["station"],
                           verdict=f["verdict"], detail=f["detail"],
                           advisor=f.get("advisor"), settle=s,
                           attribution=score.attribute(f["detail"], s)))
    os.makedirs("docs", exist_ok=True)
    led = {"days": []}
    if os.path.exists("docs/ledger.json"):
        led = json.load(open("docs/ledger.json"))
    led["days"] = [d for d in led["days"] if d["date"] != day] + [{"date": day, "flags": graded}]
    led["generated"] = dt.datetime.utcnow().isoformat() + "Z"
    json.dump(led, open("docs/ledger.json", "w"), indent=1)
    open("REPORT.md", "w").write(score.report(list(last.values()), settles))
    print(open("REPORT.md").read())

if __name__ == "__main__":
    main()
