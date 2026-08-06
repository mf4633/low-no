"""Hourly scan: evaluate every city, append flags to logs/YYYY-MM-DD.jsonl.
FLAGS ONLY -- this module has no order-placement code and must never grow any.
The human (or nothing) executes. Run: python -m lowno.scan"""
import datetime as dt, json, os, zoneinfo
from .config import CITIES
from . import sources, gate, advisor

def scan_once():
    today = dt.date.today()
    results = []
    for key, c in CITIES.items():
        try:
            tz = zoneinfo.ZoneInfo(c["tz"])
            now_l = dt.datetime.now(tz)
            obs = sources.latest_obs(c["station"])
            obs_today = [o for o in obs if o["ts"][:10] == now_l.date().isoformat()]
            rmax = gate.running_max_f(obs_today)
            wx = obs_today[0]["wx"] if obs_today else ""
            try:
                guide, short, pop = sources.point_forecast_high(c["lat"], c["lon"])
            except Exception:
                guide, short, pop = None, None, None  # unverified -> gate PASSes by design
            rungs = sources.kalshi_ladder(c["series"], today.strftime("%y%b%d").upper())
            verdict, detail = gate.evaluate(key, rungs, rmax, guide, pop,
                                            (now_l.hour, now_l.minute), wx)
            row = dict(city=key, station=c["station"], verdict=verdict,
                       detail=detail, at=dt.datetime.utcnow().isoformat())
            if verdict in ("QUALIFIED", "DEAD_SCAVENGE"):
                row["advisor"] = advisor.advise(detail, obs_today, rungs)
            results.append(row)
        except Exception as e:
            results.append(dict(city=key, station=c["station"], verdict="ERROR",
                                detail={"why": str(e)[:200]}, at=dt.datetime.utcnow().isoformat()))
    os.makedirs("logs", exist_ok=True)
    path = f"logs/{today.isoformat()}.jsonl"
    with open(path, "a") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    hits = [r for r in results if r["verdict"] in ("QUALIFIED", "DEAD_SCAVENGE")]
    print(f"{dt.datetime.utcnow():%H:%MZ} scanned {len(results)} :: "
          f"{len(hits)} actionable :: " + ", ".join(f"{r['city']}={r['verdict']}" for r in hits) if hits
          else f"{dt.datetime.utcnow():%H:%MZ} scanned {len(results)} :: nothing qualified (fine)")
    return results

if __name__ == "__main__":
    scan_once()
