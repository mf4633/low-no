"""Nightly entry point: grade today's flags against CLI settlements, write REPORT.md."""
import json, glob, os, zoneinfo, datetime as dt
from . import score, sources
from .config import CITIES

WFO = dict(AUS="EWX", CHI="LOT", DEN="BOU", LAX="LOX", MIA="MFL",
           NYC="OKX", PHL="PHI", PHX="PSR", SEA="SEW", SFO="MTR")

def _log_days():
    return sorted(os.path.basename(p)[:-6] for p in glob.glob("logs/2*.jsonl"))

def _flags_for(day):
    flags = []
    for line in open(f"logs/{day}.jsonl"):
        r = json.loads(line)
        if r["verdict"] in ("QUALIFIED", "DEAD_SCAVENGE"):
            flags.append(r)
    # one position per city per day: keep the last scan cycle's view
    return list({f["city"]: f for f in flags}.values())

def _grade_day(day):
    flags = _flags_for(day)
    settles, graded = {}, []
    for f in flags:
        city = f["city"]
        if city not in settles:
            try:
                settles[city], _ = sources.cli_max(CITIES[city]["station"], WFO[city], date=day)
            except Exception as e:
                print(f"  {day} {city}: CLI fetch failed ({e})")
                settles[city] = None
        s = settles[city]
        graded.append(dict(date=day, city=city, station=f["station"],
                           verdict=f["verdict"], detail=f["detail"],
                           advisor=f.get("advisor"), settle=s,
                           attribution=score.attribute(f["detail"], s)))
    return graded, flags, settles

def main():
    # Grade every log day that is not yet fully settled, rather than trusting the
    # clock. The old version scored dt.date.today() in ET; when the cron slipped
    # past midnight ET (04:04Z on Aug 10) it graded a day with no log and left
    # Aug 9 -- the only day with flags -- permanently ungraded. This is also
    # self-healing: a PENDING day is retried until CLI settles it.
    os.makedirs("docs", exist_ok=True)
    led = {"days": []}
    if os.path.exists("docs/ledger.json"):
        led = json.load(open("docs/ledger.json"))
    by_date = {d["date"]: d for d in led.get("days", [])}
    days = _log_days()

    # Drop phantom entries: ledger days with no corresponding scan log.
    for ghost in [d for d in by_date if d not in days]:
        print(f"dropping phantom ledger day {ghost} (no scan log)")
        by_date.pop(ghost)

    today_et = dt.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date().isoformat()
    last_graded, last_settles = [], {}
    for day in days:
        entry = by_date.get(day)
        settled = entry is not None and all(f.get("settle") is not None
                                            for f in entry.get("flags", []))
        if settled and entry.get("flags"):
            continue
        if entry is not None and not entry.get("flags") and day != today_et:
            continue  # zero-flag day, already recorded, nothing to settle
        graded, raw, settles = _grade_day(day)
        n_set = sum(1 for g in graded if g["settle"] is not None)
        print(f"graded {day}: {len(graded)} flag(s), {n_set} settled")
        by_date[day] = {"date": day, "flags": graded}
        if graded:
            last_graded, last_settles = raw, settles

    led["days"] = [by_date[d] for d in sorted(by_date)]
    led["generated"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    json.dump(led, open("docs/ledger.json", "w"), indent=1)
    open("REPORT.md", "w").write(score.report(last_graded, last_settles))
    print(open("REPORT.md").read())


if __name__ == "__main__":
    main()
