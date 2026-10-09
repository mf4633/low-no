"""Read-only mispricing table: market vs repo model vs Claude's judgment.

Writes nothing into the repo (Kalshi probe goes to a temp file). Two steps:

  python mispricing_read.py curves NYC EWR ATL
      obs now vs GFS/ECMWF curve INTERPOLATED to the current minute, plus the
      curve highs and the station's guide bias -- the inputs for judging a center.

  python mispricing_read.py table '{"NYC":[62.0,2.0],"ATL":[81.5,2.2]}'
      per rung: P(NO wins) from the market (NO ask), the repo model, and a
      truncated normal at the judged (center, sd), truncated at round(run_max).

sd: measured day-ahead error is ~2.2-2.5F RMSE; mid-morning ~2.0. Tighter sds
manufacture confident mid-rung disagreements.
"""
import sys, json, math, os, tempfile, urllib.request, datetime as dt, zoneinfo
from lowno import sources, gate, prob
from lowno.config import CITIES

ET = zoneinfo.ZoneInfo("America/New_York")
PROBE = os.path.join(tempfile.gettempdir(), "lowno_mispricing_probe.json")


def _get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "lowno/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _day_obs(k, today):
    c = CITIES[k]; tz = zoneinfo.ZoneInfo(c["tz"])
    mid = dt.datetime.combine(today, dt.time(0), tz)
    lst_mid = dt.datetime.combine(today, dt.time(0), dt.timezone(
        mid.utcoffset() - (mid.dst() or dt.timedelta(0))))

    def lst(ts):
        t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(tz)
        return (t - (t.dst() or dt.timedelta(0))).date()
    since = lst_mid - dt.timedelta(hours=1)
    obs = sources.latest_obs(c["station"], since=since)
    try:   # stale-feed fix 2026-10-08: same AWC merge as scan.py
        obs, _ = sources.merge_obs(obs, sources.awc_metars(c["station"], since))
    except Exception:
        pass
    return [o for o in obs if lst(o["ts"]) == today]


def curves(keys):
    now = dt.datetime.now(ET); today = now.date()
    bias = prob.live_bias if hasattr(prob, "live_bias") else None
    print(f"ET {now:%H:%M}")
    for k in keys:
        c = CITIES[k]; tz = zoneinfo.ZoneInfo(c["tz"]); ln = dt.datetime.now(tz)
        j = _get(f"https://api.open-meteo.com/v1/forecast?latitude={c['lat']}&longitude={c['lon']}"
                 f"&hourly=temperature_2m&temperature_unit=fahrenheit&timezone={c['tz']}"
                 f"&start_date={today}&end_date={today}&models=gfs_seamless,ecmwf_ifs025")
        h = j["hourly"]; H, f = ln.hour, ln.minute / 60
        exp, mx = {}, {}
        for m, v in h.items():
            if not m.startswith("temperature"): continue
            name = m.split("_", 2)[-1]
            if H + 1 < len(v) and v[H] is not None and v[H + 1] is not None:
                exp[name] = round(v[H] * (1 - f) + v[H + 1] * f, 1)
            mx[name] = max(x for x in v if x is not None)
        obs = _day_obs(k, today)
        now_f = round(obs[0]["tC"] * 1.8 + 32, 1) if obs and obs[0]["tC"] is not None else None
        guide, short, pop = sources.point_forecast_high(c["lat"], c["lon"])
        b = None
        try: b = bias(k) if bias else None
        except Exception: pass
        print(f"{k}: obs {now_f} run_max {gate.running_max_f(obs)} | curve now {exp} | "
              f"curve max {mx} | guide {guide} ({short}, PoP {pop}) guide-bias {b}")


def table(me):
    Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
    now = dt.datetime.now(ET); today = now.date()
    print(f"ET {now:%H:%M}   P(NO wins) %: market | model | me | me-market")
    for k, (mu, sd) in me.items():
        c = CITIES[k]; tz = zoneinfo.ZoneInfo(c["tz"])
        obs = _day_obs(k, today); rmax = gate.running_max_f(obs)
        guide, short, pop = sources.point_forecast_high(c["lat"], c["lon"])
        rungs = sources.kalshi_ladder(c["series"], today.strftime("%y%b%d").upper(), probe_path=PROBE)
        ev = prob.evaluate_ladder(k, rungs, guide, rmax, pop,
                                  local_hour=dt.datetime.now(tz).hour)["rungs"]
        lo = round(rmax) if rmax is not None else -999
        Z = 1 - Phi((lo - 0.5 - mu) / sd)

        def le(x):
            if x < lo: return 0.0
            return (Phi((x + 0.5 - mu) / sd) - Phi((lo - 0.5 - mu) / sd)) / Z
        print(f"\n{k}  center {mu} sd {sd} | run_max {rmax} | guide {guide} PoP {pop}")
        key = lambda r: (r["ceiling"] if r["ceiling"] is not None else 999, r["floor"] or -1)
        for r in sorted(ev, key=key):
            fl, cap = r["floor"], r["ceiling"]
            if cap is None: p_yes = 1 - le(fl - 1)
            else: p_yes = le(cap) - (le(fl - 1) if fl is not None else 0)
            mine = 100 * (1 - p_yes)
            print(f"  {r['label']:>6}  {r['price']:>3} | {r['p_no']*100:>3.0f} | {mine:>3.0f} | {mine - r['price']:+.0f}")


if __name__ == "__main__":
    if sys.argv[1] == "curves":
        curves(sys.argv[2:])
    else:
        table({k: tuple(v) for k, v in json.loads(sys.argv[2]).items()})
