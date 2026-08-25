"""Hourly scan: evaluate every city, append flags to logs/YYYY-MM-DD.jsonl.
FLAGS ONLY -- this module has no order-placement code and must never grow any.
The human (or nothing) executes. Run: python -m lowno.scan"""
import datetime as dt, json, os, zoneinfo
from .config import CITIES, GATE
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
            # Depth on the rung the gate actually evaluates. One call per city
            # per cycle. Every P&L figure assumes a fill AT the logged ask; this
            # measures whether the contracts to fill it actually exist.
            br = gate.bottom_rung(rungs)
            depth = None
            if br is not None:
                depth = sources.orderbook_depth(
                    br["ticker"], max_price=int(GATE["max_price"] * 100),
                    probe_path=("logs/_ob_probe.json" if key == "DEN" else None))

            verdict, detail = gate.evaluate(key, rungs, rmax, guide, pop,
                                            (now_l.hour, now_l.minute), wx)
            # Upstream advection + stall telemetry. NOT gate inputs -- new,
            # unvalidated features logged so they can be scored as variants.
            # Both come from the 2026-08-22 MSY call, which was resolved by an
            # upstream station read and an intraday stall the scanner cannot see.
            try:
                from . import advection
                detail["upstream"] = advection.upstream(key)
                detail["stall"] = advection.stall(
                    key, [r for r in results
                          if r.get("city") == key and r.get("verdict") != "LADDER"])
            except Exception as _ae:
                print("advection: skipped -", str(_ae)[:100])
            # Sky condition and run_max provenance. BKN/OVC at peak heating is a
            # real differentiator (MSY under BKN250 vs BTR CLR, 2026-08-22) and
            # was not captured anywhere. run_max_detail records which observation
            # stream produced the max so the 5-minute cool bias is measurable.
            try:
                detail["sky"] = sources.sky_from_obs(obs_today[0]) if obs_today else None
                detail["run_max_detail"] = gate.running_max_f(obs_today, return_detail=True)
            except Exception as _se:
                print("sky/run_max_detail: skipped -", str(_se)[:100])
            # Competing forecasts for the same station-day. Recorded so their
            # skill can be scored against CLI -- the ledger previously held only
            # NBM `guide`, making "which forecaster is best" unanswerable.
            try:
                from . import forecasts
                detail["forecasts"] = forecasts.collect(c, today.isoformat())
            except Exception as _fe:
                print("forecasts: skipped -", str(_fe)[:100])
            if depth is not None and isinstance(detail, dict):
                detail["depth"] = depth
            # Persist the EVIDENCE PACK on every flag. Without it the advisor can
            # never be backtested: the 2026-08-16 replay found the ledger stores
            # only the gate's summary, so historical flags have no obs trace or
            # ladder to re-read and every replay ABSTAINs on missing data.
            if isinstance(detail, dict) and verdict in ("QUALIFIED", "DEAD_SCAVENGE"):
                detail["evidence"] = {
                    "obs_tail": [{"ts": o.get("ts"), "tC": o.get("tC")}
                                 for o in obs_today[:10]],
                    "ladder": [{"ticker": r.get("ticker"), "cap": r.get("cap"),
                                "floor": r.get("floor"), "no_ask": r.get("no_ask"),
                                "yes_bid": r.get("yes_bid")} for r in rungs],
                    "wx": (wx or "")[:600]}
                # Snapshot the model's own probability ON the flag. Without this
                # the nightly Brier has nothing to grade: edge.json is overwritten
                # every cycle, so a flag's forecast is gone by settlement time.
                try:
                    _lh2 = dt.datetime.now(dt.timezone.utc).astimezone(
                        zoneinfo.ZoneInfo(CITIES[key]["tz"])).hour
                    _bd = prob.evaluate_ladder(key, rungs, guide, rmax, pop,
                                               local_hour=_lh2)
                    for _r in _bd.get("rungs", []):
                        if _r.get("ceiling") == detail.get("ceiling") and _r.get("kind") == "bottom":
                            detail["model"] = {"p_exceed_cap": _r.get("p_no"),
                                               "p_source": _r.get("p_source"),
                                               "p_empirical": _r.get("p_empirical"),
                                               "emp_n": _r.get("emp_n"),
                                               "sigma": _r.get("sigma"),
                                               "size_frac": _r.get("size_frac")}
                            break
                except Exception as _e:
                    detail["model"] = {"error": str(_e)[:80]}
            # Also attach to the LADDER record's bottom rung: shadow dedup prefers
            # LADDER rows for any cycle that has one, so depth stored only on the
            # gate row never reaches the observations (found 2026-08-16, n=0 on
            # the depth variant). Store it where the analysis actually reads.
            if depth is not None and br is not None:
                for _lr in results:
                    if _lr.get("verdict") == "LADDER" and _lr.get("city") == key:
                        for _rg in _lr["detail"].get("rungs", []):
                            if _rg.get("t") == br["ticker"]:
                                _rg["depth"] = depth
            # Full-ladder record: every rung's quotes, not just the bottom one
            # the gate evaluates. The gate stays frozen -- this is telemetry.
            # ~6x the settled observations per day at zero marginal fetch cost.
            # oi/vol were fetched per rung and then dropped here since Aug 7;
            # sky was computed and kept only on the gate row. Both are ephemeral
            # (unreconstructable later) and cheap (no extra fetches): oi/vol
            # feed future fill/activity models, sky feeds YES-win attribution
            # (marine layer / frontal bust vs. clear-day miss).
            results.append(dict(city=key, station=c["station"], verdict="LADDER",
                detail=dict(guide=guide, pop=pop, run_max=rmax,
                    sky=(detail.get("sky") if isinstance(detail, dict) else None),
                    rungs=[dict(t=r["ticker"], cap=r.get("cap"), fl=r.get("floor"),
                                na=r.get("no_ask"), yb=r.get("yes_bid"),
                                ya=r.get("yes_ask"), nb=r.get("no_bid"),
                                oi=r.get("oi"), vol=r.get("vol"),
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
        try:
            from . import empirical as _emp
            _samples = _emp._raw_climbs()
        except Exception:
            _samples = None
        for r in results:
            if r["verdict"] != "LADDER": continue
            d = r["detail"]
            rungs = [dict(cap=x.get("cap"), floor=x.get("fl"), no_ask=x.get("na"),
                          yes_bid=x.get("yb"), ticker=x.get("t")) for x in d["rungs"]]
            _lh = dt.datetime.now(dt.timezone.utc).astimezone(
                zoneinfo.ZoneInfo(CITIES[r["city"]]["tz"])).hour
            board.append(prob.evaluate_ladder(r["city"], rungs, d.get("guide"),
                                              d.get("run_max"), d.get("pop"),
                                              local_hour=_lh, emp_samples=_samples))
        os.makedirs("docs", exist_ok=True)
        json.dump(dict(at=dt.datetime.utcnow().isoformat()+"Z", cities=board),
                  open("docs/edge.json", "w"), indent=1)
        # Classify positive-edge rungs that carry measured trap signals. The
        # board sorts by edge and the biggest edges are usually the worst bets.
        try:
            from . import traps
            traps.write()
        except Exception as _te:
            print("traps: skipped -", str(_te)[:100])
    except Exception as e:
        print("edge board failed:", e)

    # Notify on qualifying flags. Best-effort: a notification failure must never
    # break a scan or lose data, so this is wrapped and logged, not raised.
    try:
        from . import notify
        for _r in results:
            if _r.get("verdict") in ("QUALIFIED", "DEAD_SCAVENGE"):
                notify.notify_flag(_r.get("city"), _r["verdict"],
                                   _r.get("detail") or {}, _r.get("advisor"))
    except Exception as _e:
        print("notify: skipped -", str(_e)[:120])

    # Live intraday tracker for anything flagged or near-flagging today.
    try:
        from . import live
        _conv = {}
        try:
            _cv = json.load(open("docs/shadow_summary.json"))
            _conv = (_cv.get("convergence") or {}).get("convergence_hour_local", {})
        except Exception:
            pass
        live.write(results, emp_samples=_samples if "_samples" in dir() else None,
                   conv_hours=_conv)
    except Exception as _e:
        print("live tracker: skipped -", str(_e)[:120])

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
