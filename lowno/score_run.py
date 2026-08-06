"""Nightly entry point: grade today's flags against CLI settlements, write REPORT.md."""
import json, glob, datetime as dt
from . import score, sources
from .config import CITIES

WFO = dict(AUS="EWX", CHI="LOT", DEN="BOU", LAX="LOX", MIA="MFL",
           NYC="OKX", PHL="PHI", PHX="PSR", SEA="SEW", SFO="MTR")

def main():
    day = dt.date.today().isoformat()
    flags = []
    for line in open(f"logs/{day}.jsonl"):
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
    import os
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
