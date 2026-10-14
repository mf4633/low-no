"""Holdout check: fade my 30+ point disagreements by buying the market's 51-80c side.

FROZEN 2026-10-14. NOT a registered hypothesis and NOT in the ledger. Michael's
call: decide the "invert our losing bets" question by analysis on data we have,
then confirm on days the search never touched.

DISCOVERY (9/4-10/13, every logged scan at 14/16/18/20Z, 12,753 mirrored bets,
85 slices searched, kept only if positive in both day-halves): the one cluster
that survived is "when my center (below) disagrees with a side's ask by >= 30
points, buy the MIRROR side at its ask if that ask is 51-80c". It made +3.6c per
contract after fees, n=431, 95% CI [-2.5, +9.6], halves +6.1 / +1.2. That is not
significant, and it was the best of a search. This file decides it on new days.

THE RULE (fixed now, identical to the discovery code).
  * Scans: first LADDER row per city in each of the 14Z, 16Z, 18Z, 20Z cycles.
    City local hour >= 9.
  * My center = mean of: guide minus its mean (guide - CLI) error over the 3
    prior days (first logged guide of each day); curve_max_f + 0.5*curve_dev;
    temp_now + (yesterday's CLI - yesterday's temp_now at the same scan hour).
    Missing predictors are dropped. Normal, sd 2.0, truncated below at
    round(run_max) - 0.5.
  * For every rung and side with ask 1-97: edge = my P - ask/100. If edge >=
    0.30 and the opposite side's ask is 51-80c, buy the opposite side at its
    ask. Fee ceil(0.07*100*q*(1-q)) on every fill. Settled from shadow.json.

THE CALL (fixed now). Holdout = days >= 2026-10-14 (no discovery day). Day-
clustered bootstrap (2000 resamples, seed 30) on mean P&L per contract:
  CONFIRMED  95% lower bound > 0
  ALIVE      mean > 0 but lower bound <= 0: keep watching, do not act on it
  DEAD       mean <= 0
Run: python fade30_check.py [start] [end]   (defaults: holdout, through yesterday)
"""
import json, math, os, random, sys, statistics as st, collections, zoneinfo, datetime as dt
from lowno.config import CITIES

HOURS = ("14", "16", "18", "20")
EDGE, BUY_LO, BUY_HI, SD = 0.30, 51, 80, 2.0
HOLDOUT_START = "2026-10-14"


def fee(p):
    q = p / 100
    return math.ceil(0.07 * 100 * q * (1 - q))


def Phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bucket_p(lo, hi, mu, sd, floor):
    lo_ = -1e9 if lo is None else lo - 0.5
    hi_ = 1e9 if hi is None else hi + 0.5
    lo_ = max(lo_, floor)
    if hi_ <= lo_:
        return 0.0
    Z = 1 - Phi((floor - mu) / sd)
    return (Phi((hi_ - mu) / sd) - Phi((lo_ - mu) / sd)) / Z


def rung_bounds(g):
    if g["cap"] is not None and g["fl"] is not None:
        return g["fl"], g["cap"]
    if g["cap"] is not None:
        return None, g["cap"]
    return g["fl"], None


def _rows(day):
    p = os.path.join("logs", f"{day}.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def settles():
    S = collections.defaultdict(dict)
    for r in json.load(open("docs/shadow.json")):
        if r.get("settle") is not None:
            S[r["day"]][r["city"]] = r["settle"]
    return S


def bets(start, end):
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    days = [(d0 + dt.timedelta(n)).isoformat() for n in range(-3, (d1 - d0).days + 1)]
    SET = settles()
    rows = {d: _rows(d) for d in days}
    G = {}
    for d in days:
        g = {}
        for r in rows[d]:
            if r.get("verdict") == "LADDER":
                g.setdefault(r["city"], r["detail"]["guide"])
        G[d] = g
    out = []
    for H in HOURS:
        S = {}
        for d in days:
            s = {}
            for r in rows[d]:
                if r.get("verdict") == "LADDER" and r["at"][11:13] == H:
                    s.setdefault(r["city"], r)
            S[d] = s
        for i, d in enumerate(days[3:], 3):
            if not S[d] or not S[days[i - 1]]:
                continue
            for c, r in S[d].items():
                det = r["detail"]
                if det.get("guide") is None or not det.get("rungs"):
                    continue
                settle = SET[d].get(c)
                if settle is None:
                    continue
                tz = zoneinfo.ZoneInfo(CITIES[c]["tz"])
                lh = dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc).astimezone(tz).hour
                if lh < 9:
                    continue
                errs = [G[p][c] - SET[p][c] for p in days[i - 3:i]
                        if G[p].get(c) is not None and c in SET[p]]
                g_c = det["guide"] - (st.mean(errs) if errs else 0)
                hc = det["airmass"]["curve_max_f"] + 0.5 * (det.get("curve_dev") or 0) if det.get("airmass") else g_c
                y = S[days[i - 1]].get(c); an = None
                if (y and c in SET[days[i - 1]] and det.get("temp_now") is not None
                        and y["detail"].get("temp_now") is not None):
                    an = det["temp_now"] + (SET[days[i - 1]][c] - y["detail"]["temp_now"])
                preds = [x for x in (g_c, hc, an) if x is not None]
                mu = st.mean(preds)
                floor = round(det["run_max"]) - 0.5 if det.get("run_max") else -1e9
                for g in det["rungs"]:
                    if g.get("ya") is None or g.get("na") is None:
                        continue
                    lo, hi = rung_bounds(g)
                    p = bucket_p(lo, hi, mu, SD, floor)
                    win = (lo is None or settle >= lo) and (hi is None or settle <= hi)
                    for side, myp, ask, opp in (("YES", p, g["ya"], g["na"]), ("NO", 1 - p, g["na"], g["ya"])):
                        if not 1 <= ask <= 97 or myp - ask / 100 < EDGE or not BUY_LO <= opp <= BUY_HI:
                            continue
                        won = (not win) if side == "YES" else win   # we hold the OPPOSITE side
                        out.append(dict(day=d, hour=H, city=c, lo=lo, hi=hi,
                                        bought="NO" if side == "YES" else "YES", ask=opp,
                                        won=won, pnl=(100 - opp if won else -opp) - fee(opp)))
    return [b for b in out if start <= b["day"] <= end]


def call(B):
    if not B:
        return dict(n=0, call="NO DATA")
    by = {}
    for b in B:
        by.setdefault(b["day"], []).append(b["pnl"])
    ks = sorted(by); R = random.Random(30); bs = []
    for _ in range(2000):
        v = [x for d in (R.choice(ks) for _ in ks) for x in by[d]]
        bs.append(sum(v) / len(v))
    bs.sort()
    m = sum(b["pnl"] for b in B) / len(B)
    lo, hi = bs[50], bs[1949]
    verdict = "CONFIRMED" if lo > 0 else ("ALIVE" if m > 0 else "DEAD")
    return dict(n=len(B), days=len(by), hit=round(sum(b["won"] for b in B) / len(B), 3),
                mean_ask=round(sum(b["ask"] for b in B) / len(B), 1),
                mean_pnl_c=round(m, 2), ci95=[round(lo, 2), round(hi, 2)], call=verdict)


if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else HOLDOUT_START
    end = sys.argv[2] if len(sys.argv) > 2 else (dt.date.today() - dt.timedelta(days=1)).isoformat()
    B = bets(start, end)
    print(f"fade30 {start}..{end}")
    print(json.dumps(call(B), indent=1))
