"""Hourly scan: evaluate every city, append flags to logs/YYYY-MM-DD.jsonl.
FLAGS ONLY -- this module has no order-placement code and must never grow any.
The human (or nothing) executes. Run: python -m lowno.scan"""
import datetime as dt, json, os, zoneinfo
from .config import CITIES
from . import sources, gate, advisor, prob

def scan_once():
    today = dt.date.today()
    results = []
    for key, c in CITIES.items():
        try:
            tz = zoneinfo.ZoneInfo(c["tz"])
            now_l = dt.datetime.now(tz)
            obs = sources.latest_obs(c["station"])
            # api.weather.gov timestamps are UTC. The old filter compared the UTC
            # date prefix to the LOCAL date string, so 00:00-07:00Z obs (= prior
            # local evening on the West Coast, incl. yesterday's ~17:00 near-peak)
            # matched "today". Convert to station-local time and pin to the
            # MARKET day (the ticker date), not the wall clock.
            def _obs_local_date(ts):
                return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))                          .astimezone(tz).date().isoformat()
            obs_today = [o for o in obs if _obs_local_date(o["ts"]) == today.isoformat()]
            rmax = gate.running_max_f(obs_today)
            wx = obs_today[0]["wx"] if obs_today else ""
            try:
                guide, short, pop = sources.point_forecast_high(c["lat"], c["lon"])
            except Exception:
                guide, short, pop = None, None, None  # unverified -> gate PASSes by design
            rungs = sources.kalshi_ladder(c["series"], today.strftime("%y%b%d").upper())
            verdict, detail = gate.evaluate(key, rungs, rmax, guide, pop,
                                            (now_l.hour, now_l.minute), wx)
            # Full-ladder record: every rung's quotes, not just the bottom one
            # the gate evaluates. The gate stays frozen -- this is telemetry.
            # ~6x the settled observations per day at zero marginal fetch cost.
            results.append(dict(city=key, station=c["station"], verdict="LADDER",
                detail=dict(guide=guide, pop=pop, run_max=rmax,
                    rungs=[dict(t=r["ticker"], cap=r.get("cap"), fl=r.get("floor"),
                                na=r.get("no_ask"), yb=r.get("yes_bid"),
                                ya=r.get("yes_ask"), nb=r.get("no_bid"),
                                src=r.get("quote_src")) for r in rungs]),
                at=dt.datetime.utcnow().isoformat()))
            row = dict(city=key, station=c["station"], verdict=verdict,
                       detail=detail, at=dt.datetime.utcnow().isoformat())
            if verdict in ("QUALIFIED", "DEAD_SCAVENGE"):
                row["advisor"] = advisor.advise(detail, obs_today, rungs)
            results.append(row)
        except Exception as e:
            results.append(dict(city=key, station=c["station"], verdict="ERROR",
                                detail={"why": str(e)[:200]}, at=dt.datetime.utcnow().isoformat()))
    # Live edge board for the site: per-rung probability/edge/half-Kelly.
    try:
        board = []
        for r in results:
            if r["verdict"] != "LADDER": continue
            d = r["detail"]
            rungs = [dict(cap=x.get("cap"), floor=x.get("fl"), no_ask=x.get("na"),
                          yes_bid=x.get("yb"), ticker=x.get("t")) for x in d["rungs"]]
            board.append(prob.evaluate_ladder(r["city"], rungs, d.get("guide"),
                                              d.get("run_max"), d.get("pop")))
        os.makedirs("docs", exist_ok=True)
        json.dump(dict(at=dt.datetime.utcnow().isoformat()+"Z", cities=board),
                  open("docs/edge.json", "w"), indent=1)
    except Exception as e:
        print("edge board failed:", e)

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
