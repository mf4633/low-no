"""Nightly shadow grading: settle every scanned rung, roll up band statistics.

Writes docs/shadow.json (row-level) and docs/shadow_summary.json (band rollup
with Wilson bounds vs. fee breakeven). Deduplicates to one entry per
city-day-band so n reflects independent observations, not scan cycles.
"""
import json, math, os, datetime as dt, zoneinfo
from collections import defaultdict
from lowno import shadow, adaptive, convergence, spend, skill, paper_pilot
from lowno.config import CITIES

MARINE_CITIES = {"SFO", "LAX", "SAN"}   # keep in sync with lowno.prob.MARINE

BANDS = [(1,10),(11,20),(21,30),(31,40),(41,50),(51,60),(61,70),(71,80),(81,90),(91,95),(96,98)]

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 1.0)
    p = k/n; d = 1 + z*z/n; c = (p + z*z/(2*n))/d
    m = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return (max(0.0, c-m), min(1.0, c+m))

def band_of(p):
    for lo, hi in BANDS:
        if lo <= p <= hi: return f"{lo}-{hi}"
    return None

def main():
    obs = shadow.build()
    json.dump(obs, open("docs/shadow.json", "w"), indent=1)

    bottom = [o for o in obs if o.get("kind", "bottom") == "bottom"]
    units = {}
    for o in sorted(bottom, key=lambda x: x["at"]):
        if o["price"] > 98: continue
        b = band_of(o["price"])
        if b is None: continue
        units.setdefault((o["day"], o["city"], b), o)   # first cycle in band

    roll = []
    for b in [f"{lo}-{hi}" for lo, hi in BANDS]:
        g = [v for k, v in units.items() if k[2] == b]
        n = len(g); k = sum(1 for x in g if x["won"])
        if n == 0:
            roll.append(dict(band=b, n=0)); continue
        mp = sum(x["price"] for x in g)/n
        fee = math.ceil(0.07*100*(mp/100)*(1-mp/100))
        need = mp/(100-fee)
        lo_, hi_ = wilson(k, n)
        # RETIREMENT IS JUDGED ON CAP-CORRECTED OUTCOMES, on purpose.
        #
        # NO-side grading deliberately stays on the LOGGED cap so that history
        # is not rewritten mid-measurement (see shadow.build). For pre-fix rows
        # that cap is the raw threshold, so a settle exactly AT it reads as a
        # NO-loss when it was truly a NO-win -- pessimistic at the boundary, by
        # design, and 18 of 26 days in this record are pre-fix.
        #
        # Pessimism is harmless for "not proven": it can only delay a promotion.
        # It is NOT harmless for "refuted", which is permanent and one-way.
        # Judging futility on a knowingly pessimistic number retires bands that
        # are merely unproven. Measured 2026-08-31: on the as-graded numbers
        # 8 of 11 bands retired; on cap-corrected outcomes only 96-98c does.
        # That is the difference between "the strategy is dead" and "the strategy
        # is dead at the top of the book", and the second one is what is true.
        kc = sum(1 for x in g
                 if x["settle"] > ((x["ceiling"] - 1) if x.get("cap_is_raw")
                                   else x["ceiling"]))
        _, hi_corr = wilson(kc, n)
        roll.append(dict(band=b, n=n, wins=k, hit=k/n, mean_price=round(mp,1),
                         breakeven=round(need,4), lcb=round(lo_,4), ucb=round(hi_,4),
                         mean_pnl_c=round(sum(x["pnl"] for x in g)/n,2),
                         proven=bool(lo_ > need),
                         # Futility is promotion inverted, same interval, other
                         # end: the 95% UPPER bound below breakeven means the
                         # data has ruled OUT any true rate that could profit.
                         # See "WHEN THIS PROJECT STOPS" in CANDIDATE.md.
                         # NB this retires the band traded UNCONDITIONALLY. It
                         # says nothing about a conditional rule inside it --
                         # which is the only reason H4a/H4b/H5 are still alive.
                         wins_capfix=kc, ucb_capfix=round(hi_corr, 4),
                         retired=bool(hi_corr < need)))
    # YES side of the same bottom rungs: same bands, same one-entry-per-
    # city-day-band dedup, same fee model and Wilson bounds. CAUTION: where no
    # real yes_ask was logged, yes_price is derived as 100 - no_ask, which
    # IGNORES THE SPREAD and therefore FAVOURS the YES buyer (a real ask sits at
    # or above the derived price). Any band that survives only on derived prices
    # is an artifact -- n_real_ask records how much of each band is real quotes.
    yunits = {}
    for o in sorted(bottom, key=lambda x: x["at"]):
        yp = o.get("yes_price")
        if yp is None: continue
        b = band_of(yp)
        if b is None: continue
        yunits.setdefault((o["day"], o["city"], b), o)   # first cycle in band

    yroll = []
    for b in [f"{lo}-{hi}" for lo, hi in BANDS]:
        g = [v for k, v in yunits.items() if k[2] == b]
        n = len(g); k = sum(1 for x in g if x["yes_won"])
        if n == 0:
            yroll.append(dict(band=b, n=0)); continue
        mp = sum(x["yes_price"] for x in g)/n
        fee = math.ceil(0.07*100*(mp/100)*(1-mp/100))
        need = mp/(100-fee)
        lo_, hi_ = wilson(k, n)
        yroll.append(dict(band=b, n=n, wins=k, hit=k/n, mean_price=round(mp,1),
                          breakeven=round(need,4), lcb=round(lo_,4), ucb=round(hi_,4),
                          mean_pnl_c=round(sum(x["yes_pnl"] for x in g)/n,2),
                          n_real_ask=sum(1 for x in g
                                         if x.get("yes_price_src") == "real_ask"),
                          proven=bool(lo_ > need)))
    yspreads = [o["yes_spread"] for o in obs if o.get("yes_spread") is not None]

    # SCAN COVERAGE: how many distinct hourly cycles each day actually got.
    # GitHub's scheduled cron is best-effort and drops fires under load
    # (2026-08-26: 5 of 11 hours). This matters to interpretation, not just
    # ops -- the pilot and the prereg variant both take a city's FIRST
    # qualifying cycle, so a sparse day samples a different, later price than
    # a full day. Any cross-day comparison should check this first.
    import glob as _glob
    coverage = {}
    for _f in sorted(_glob.glob("logs/2*.jsonl")):
        _day = _f.replace("\\", "/").split("/")[-1][:-6]
        # An hour counts if a scan cycle HAPPENED in it -- either it wrote a
        # ladder row or it recorded a station's running max. Ladder-only was
        # wrong in both directions: the early collector never wrote that label,
        # so 2026-08-06..08-09 reported 0 cycles against 11 real ones and cried
        # wolf permanently; and an hour whose scan errored before producing an
        # observation still wrote ladder rows, so 2026-08-30 counted 15 hours
        # against 12 that yielded data.
        #
        # This stays a count of ATTEMPTS on purpose. Whether the attempts
        # produced anything the tests can eat is a different question, and it
        # now has its own alarm in lowno.health -- see the 2026-08-30 entry in
        # CANDIDATE.md for why conflating the two hid a whole lost day.
        _hrs = set()
        try:
            for _line in open(_f):
                _r = json.loads(_line)
                _at = _r.get("at")
                if not _at:
                    continue
                _d = _r.get("detail")
                if _r.get("verdict") == "LADDER" or (
                        isinstance(_d, dict) and not _d.get("world")
                        and _d.get("run_max") is not None):
                    _hrs.add(_at[11:13])
        except Exception:
            continue
        coverage[_day] = len(_hrs)

    # Per-station guide bias from settled days: mean(guide - CLI). This is the
    # transfer-function candidate (same shape as the EWR-3.5 KNYC correction).
    bias_acc = defaultdict(list)
    seen_cd = set()
    for o in obs:   # bias uses ALL kinds: guide_err is per city-day, kind-independent
        cd = (o["day"], o["city"])
        if o.get("guide_err") is not None and cd not in seen_cd:
            seen_cd.add(cd); bias_acc[o["city"]].append(o["guide_err"])
    bias = {c: round(sum(v)/len(v), 2) for c, v in bias_acc.items()}

    # EARNED station profiles: the QUIRKS table in config is hand-calibrated
    # for 7 of 23 stations and must not be extended by guesswork. This is the
    # data-derived counterpart for EVERY station, refreshed nightly from
    # settled days, with n attached so nobody mistakes 3 days for a climate.
    # Written to docs/quirks_observed.json; promote a line into QUIRKS only
    # when the behavior has enough days behind it to deserve prose.
    profiles = {}
    for c in {o["city"] for o in obs}:
        days_map = {}
        for o in obs:
            if o["city"] == c:
                days_map.setdefault(o["day"], o)
        ge = [d.get("guide_err") for d in days_map.values()
              if d.get("guide_err") is not None]
        n = len(ge)
        if n == 0:
            profiles[c] = dict(n_days=0)
            continue
        mu = sum(ge) / n
        sd = (sum((x - mu) ** 2 for x in ge) / n) ** 0.5 if n > 1 else None
        bset = {o["day"] for o in obs
                if o["city"] == c and o.get("kind") == "bottom"
                and o.get("ceiling") is not None and o.get("settle") is not None
                and abs(o["settle"] - o["ceiling"]) <= 1}
        profiles[c] = dict(
            n_days=n, bias=round(mu, 2),
            sd=(round(sd, 2) if sd is not None else None),
            hot_bust_days=sum(1 for x in ge if x >= 3),
            cool_bust_days=sum(1 for x in ge if x <= -3),
            boundary_days=len(bset))
    json.dump(dict(generated=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                   note="guide_err = guide - CLI per settled city-day; "
                        "hot/cool bust = |err| >= 3F; boundary = bottom-rung "
                        "settle within 1F of ceiling. Earned data, not calibration.",
                   profiles=profiles),
              open("docs/quirks_observed.json", "w"), indent=1)

    # Candidate rules scored on the SAME deduped city-day units, one entry each.
    # frozen: the live gate's shape (G>=4, price<=98, no floor)
    # corrected: G computed from bias-corrected guide
    # corrected+floor: adds the 90c floor the band data motivates
    def score_rule(name, keep):
        taken, seen = [], set()
        for o in sorted(bottom, key=lambda x: x["at"]):
            if o["price"] > 98 or o["G"] is None: continue
            cd = (o["day"], o["city"])
            if cd in seen or not keep(o): continue
            seen.add(cd); taken.append(o)
        n = len(taken); k = sum(1 for t in taken if t["won"])
        lo_, _ = wilson(k, n)
        return dict(rule=name, n=n, wins=k, hit=(k/n if n else None),
                    lcb=round(lo_, 3), pnl_c=sum(t["pnl"] for t in taken),
                    mean_pnl_c=(round(sum(t["pnl"] for t in taken)/n, 2) if n else None))
    abias = {c: adaptive.bias_sigma(c)[0] for c in bias} or \
            {c: adaptive.bias_sigma(c)[0] for c in {o["city"] for o in obs}}
    def gcorr(o): return o["G"] - abias.get(o["city"], 0.0)
    # Per-station entry windows from MEASURED convergence hours. The frozen gate
    # uses one 10:30-13:30 window for all ten stations; the convergence data says
    # LAX resolves by 12:00 while DEN has not resolved by any earned hour. This
    # variant enters only at/after a station's convergence hour (when the median
    # remaining climb is <=1F), i.e. when the day is effectively decided.
    conv = (convergence.build() or {}).get("convergence_hour_local", {})

    def _local_hour(o):
        try:
            u = dt.datetime.fromisoformat(o["at"]).replace(tzinfo=dt.timezone.utc)
            return u.astimezone(zoneinfo.ZoneInfo(CITIES[o["city"]]["tz"])).hour
        except Exception:
            return None

    def in_conv_window(o):
        h, ch = _local_hour(o), conv.get(o["city"])
        if h is None or ch is None:
            return False          # station has not earned a convergence hour yet
        return ch <= h <= ch + 3

    # Minimum depth: is the 96-98c band actually INVESTABLE? Every P&L figure
    # assumes a fill at the logged ask; DEN showed 3 contracts resting there.
    # Depth logging began 2026-08-13, so this variant's n starts from that date.
    def has_depth(o, need=25):
        d = o.get("depth") or {}
        return (d.get("depth_le_max") or 0) >= need

    # Is there a MARKET here, or only an ask? Every P&L figure assumes a fill at
    # the logged ask, and depth25 tests the ask side. Nothing tested whether a
    # bid exists at all. Measured 2026-08-31 on the 96-98c bottom rungs: the
    # median NO spread is 1c, but 18% of rungs sit at 79-93c -- an ask of 97
    # against a bid of 4 is not a two-sided market, and a unit priced off one is
    # a fill that does not exist. (The mean spread of 15.7c is that tail, not a
    # typical condition; it briefly looked like an execution opportunity worth
    # more than the whole 5.34c shortfall, which is why the median is the number
    # that matters.)
    #
    # `yes_spread` IS the NO spread: price == 100 - yes_bid and
    # yes_spread == yes_ask - yes_bid, verified on every bottom obs.
    #
    # The threshold is DERIVED, not chosen: require the spread to be no wider
    # than the position's own upside (100 - price). Wider than that and you can
    # never exit at the bid for less than you stood to win, which is the
    # definition of an untradeable quote. No free parameter to drift.
    def two_sided(o):
        sp = o.get("yes_spread")
        return sp is not None and o.get("price") is not None and sp <= (100 - o["price"])

    variants = [
        score_rule("frozen_G4",            lambda o: o["G"] >= 4),
        # Marine-layer stations are bimodal (burn-off vs. cap); a Gaussian cannot
        # price them and prob.py already zeroes their size. As of 2026-08-19 every
        # loss in the ledger is SFO. Scored, not enforced -- SFO is also half the
        # flag supply, so exclusion trades accuracy for sample rate.
        score_rule("exclude_marine",       lambda o: o["G"] >= 4 and o["city"] not in MARINE_CITIES),
        score_rule("floor96_ex_marine",    lambda o: 96 <= o["price"] <= 98 and o["city"] not in MARINE_CITIES),
        score_rule("conv_window_96_98",    lambda o: 96 <= o["price"] <= 98 and in_conv_window(o)),
        score_rule("floor96_depth25",      lambda o: 96 <= o["price"] <= 98 and has_depth(o)),
        score_rule("corrected_G4",         lambda o: gcorr(o) >= 4),
        score_rule("corrected_G4_floor90", lambda o: gcorr(o) >= 4 and o["price"] >= 90),
        score_rule("floor96_only",         lambda o: 96 <= o["price"] <= 98),
        # Same populations, restricted to rungs that actually have two sides.
        # Scored, never enforced: the point is to measure how much of the
        # existing P&L rests on quotes nobody could have traded against.
        score_rule("floor96_twosided",     lambda o: 96 <= o["price"] <= 98 and two_sided(o)),
        score_rule("frozen_G4_twosided",   lambda o: o["G"] >= 4 and two_sided(o)),
    ]

    # PRE-REGISTERED 2026-08-25, before any qualifying data existed -- so this
    # variant cannot be a product of scanning the yes_bands table it grew out of.
    # Rule: buy YES <= 10c on bottom rungs at stations whose measured guide bias
    # runs hotter than +3F. Mechanism: a hot-biased guide drags the market toward
    # heat; when the guide busts, the cheap "stays capped" side pays. Constraints:
    #   * days >= 2026-08-26 ONLY (first full day of cap-corrected scans; earlier
    #     yes_won grades used the raw threshold cap, which favours YES at the
    #     exact boundary this bet lives on)
    #   * real logged yes_ask ONLY -- the derived 100 - no_ask ignores the spread
    #     and flatters the YES buyer
    # Known hedge: station bias is evaluated at scoring time, not trade time, so
    # early units lean on bias measured partly after the fact. Promotion bar is
    # the same as everything else: >= 60 units, Wilson LCB > fee breakeven.
    def score_yes_rule(name, keep):
        taken, seen = [], set()
        for o in sorted(bottom, key=lambda x: x["at"]):
            if o.get("yes_price") is None or o["day"] < "2026-08-26": continue
            cd = (o["day"], o["city"])
            if cd in seen or not keep(o): continue
            seen.add(cd); taken.append(o)
        n = len(taken); k = sum(1 for t in taken if t["yes_won"])
        lo_, _ = wilson(k, n)
        return dict(rule=name, n=n, wins=k, hit=(k/n if n else None),
                    lcb=round(lo_, 3), pnl_c=sum(t["yes_pnl"] for t in taken),
                    mean_pnl_c=(round(sum(t["yes_pnl"] for t in taken)/n, 2) if n else None),
                    mean_price=(round(sum(t["yes_price"] for t in taken)/n, 1) if n else None),
                    n_real_ask=sum(1 for t in taken
                                   if t.get("yes_price_src") == "real_ask"))
    variants.append(score_yes_rule("PREREG_yes10_hotbias3",
        lambda o: 1 <= o["yes_price"] <= 10
                  and o.get("yes_price_src") == "real_ask"
                  and abias.get(o["city"], 0.0) > 3.0))

    # Registered 2026-08-26 (LATER than the rule above -- stated plainly so it
    # is never mistaken for the pre-registered number). Same rule plus a
    # liveness filter: skip rungs whose day is already decided against YES
    # (running max, rounded as settlement rounds, already above the cap).
    # Motivation was a defect, not a backtest: the original rule would buy an
    # arithmetically-settled loss because a 1c price implies a large Kelly
    # stake under a fixed hypothesis rate. On history the filter removes 6 of
    # 181 cheap units, all losers, moving 7.2% -> 7.4% -- inside noise, which
    # is exactly why it is a correctness fix and not an edge claim. Both
    # variants are scored side by side from here.
    def _alive(o):
        return not (o.get("run_max") is not None and o.get("ceiling") is not None
                    and round(o["run_max"]) > o["ceiling"])
    variants.append(score_yes_rule("yes10_hotbias3_live",
        lambda o: 1 <= o["yes_price"] <= 10
                  and o.get("yes_price_src") == "real_ask"
                  and abias.get(o["city"], 0.0) > 3.0
                  and _alive(o)))

    out = dict(generated=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z"),
               n_rung_obs=len(obs), n_bottom_obs=len(bottom), n_units=len(units),
               days=sorted({o["day"] for o in obs}), bands=roll, yes_bands=yroll,
               yes_spread=dict(n=len(yspreads),
                               mean=(round(sum(yspreads)/len(yspreads), 2)
                                     if yspreads else None),
                               max=(max(yspreads) if yspreads else None)),
               station_guide_bias=bias,
               adaptive={c: dict(zip(("bias","sigma","n_eff","mode"),
                                     adaptive.bias_sigma(c)))
                         for c in {o["city"] for o in obs}},
               diurnal=adaptive.diurnal_climb({k: v["tz"] for k, v in CITIES.items()}),
               station_profiles=profiles, scan_coverage=coverage,
               convergence=convergence.build(),
               boundary_cases=convergence.boundary_report(),
               variants=variants, brier=_brier())
    json.dump(out, open("docs/shadow_summary.json", "w"), indent=1)
    try:
        skill.write()
    except Exception as e:
        print('skill: skipped -', str(e)[:100])
    try:
        spend.write()
    except Exception as e:
        print("spend: skipped -", str(e)[:100])

    print(f"rung-obs {len(obs)} -> {len(units)} independent units over {len(out['days'])} days")
    print(f"{'band':>6} {'n':>3} {'w':>3} {'hit':>6} {'need':>6} {'LCB':>6} {'UCBfix':>6} "
          f"{'pnl':>7} {'verdict':>9}")
    for r in roll:
        if not r["n"]: continue
        verdict = ("PROVEN" if r["proven"] else "RETIRED" if r.get("retired") else "open")
        print(f"{r['band']:>6} {r['n']:>3} {r['wins']:>3} {r['hit']:>6.0%} "
              f"{r['breakeven']:>6.1%} {r['lcb']:>6.0%} {r.get('ucb_capfix', 0):>6.0%} "
              f"{r['mean_pnl_c']:>7.1f} {verdict:>9}")
    _dead = [r["band"] for r in roll if r.get("retired")]
    if _dead:
        print(f"  RETIRED at 95% ({len(_dead)} of {sum(1 for r in roll if r['n'])} bands): "
              f"{', '.join(_dead)}")
        print("  Retirement applies to the band traded UNCONDITIONALLY. Conditional "
              "rules inside a retired band are NOT retired by it.")
    # YES-side sweep. Reminder: derived prices (100 - no_ask) ignore the spread
    # and flatter the YES buyer -- read the real_ask column before believing a band.
    print(f"\nYES bands (real_ask = units priced from a logged yes_ask; the rest "
          f"are 100 - no_ask, spread-blind and optimistic)")
    print(f"{'band':>6} {'n':>3} {'w':>3} {'hit':>6} {'need':>6} {'LCB':>6} {'pnl':>7} {'real_ask':>8} {'proven':>7}")
    for r in yroll:
        if not r["n"]: continue
        print(f"{r['band']:>6} {r['n']:>3} {r['wins']:>3} {r['hit']:>6.0%} "
              f"{r['breakeven']:>6.1%} {r['lcb']:>6.0%} {r['mean_pnl_c']:>7.1f} "
              f"{r['n_real_ask']:>8} {str(r['proven']):>7}")
    if yspreads:
        print(f"yes_spread over {len(yspreads)} real-ask obs: "
              f"mean {sum(yspreads)/len(yspreads):.2f}c, max {max(yspreads)}c")
    else:
        print("yes_spread: no real-ask observations yet")

    print("\nstation guide bias (guide - CLI):", dict(sorted(bias.items(), key=lambda kv: -abs(kv[1]))))
    print(f"\n{'rule':>22} {'n':>3} {'w':>3} {'hit':>6} {'LCB':>5} {'meanP&L':>8}")
    for v in variants:
        h = f"{v['hit']:.0%}" if v['hit'] is not None else "--"
        m = v['mean_pnl_c'] if v['mean_pnl_c'] is not None else "--"
        print(f"{v['rule']:>22} {v['n']:>3} {v['wins']:>3} {h:>6} {v['lcb']:>5.0%} {m:>8}")
    # Self-announcing promotion review for the pre-registered YES pilot.
    # The quit lines and promotion criteria live in CANDIDATE.md ("YES Pilot
    # v1"), pre-committed 2026-08-25 with $0 at risk and n=0. This print exists
    # so the review date is set by the data, not by anyone remembering to look.
    _short = {d: n for d, n in coverage.items() if n < 8}
    if _short:
        print(f"\nscan coverage BELOW 8 cycles on {len(_short)} day(s): "
              f"{dict(sorted(_short.items())[-5:])} (of 11 scheduled) -- "
              f"first-qualifying-cycle entries on these days sample later prices")

    pr = next((v for v in variants if v["rule"] == "PREREG_yes10_hotbias3"), None)
    if pr is not None:
        if pr["n"] < 60:
            print(f"\nPREREG_yes10_hotbias3: {pr['n']}/60 units toward promotion "
                  f"review (criteria + quit lines: CANDIDATE.md, YES Pilot v1)")
        else:
            mp = pr["mean_price"]
            fee = math.ceil(0.07 * 100 * (mp / 100) * (1 - mp / 100))
            be = mp / (100 - fee)
            ra = pr["n_real_ask"] / pr["n"]
            met = pr["lcb"] > be and ra >= 0.90
            print(f"\nPREREG_yes10_hotbias3: n={pr['n']} hit={pr['hit']:.1%} "
                  f"LCB={pr['lcb']:.1%} vs breakeven={be:.1%} real_ask={ra:.0%} -> "
                  + ("PROMOTION CRITERIA 1-3 MET: re-probe liquidity (criterion 4), "
                     "then review CANDIDATE.md YES Pilot v1 before ANY seed"
                     if met else "not proven; keep accruing"))

    # PAPER $100 pilot: deterministic nightly replay of the YES Pilot v1 rules
    # (CANDIDATE.md) against the fixed 6.8% hypothesis. Paper only, no orders.
    pp = {}     # defined up front so status.json is still written if this fails
    try:
        pp = paper_pilot.run(obs)
        pp["generated"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        json.dump(pp, open("docs/paper_pilot.json", "w"), indent=1)
        c = pp["config"]
        print(f"\nPAPER PILOT ${c['bankroll0']:.0f} @ {c['start_day']} "
              f"(p_hyp {c['p_hyp']:.1%}, half-Kelly, cap {c['cap_frac']:.0%}): "
              f"${pp['bankroll']:.2f} after {pp['n_trades']} trades "
              f"({pp['wins']} wins, {pp['n_skipped']} skipped), status {pp['status']}; "
              f"quit lines ${c['quit_down']:.0f} / ${c['quit_up']:.0f}")
        if pp["status"] != "ACTIVE":
            print(f"PAPER PILOT HALTED: {pp['status']} -- see CANDIDATE.md YES Pilot v1")
        rf = pp.get("refuted")
        if rf:
            print(f"  HYPOTHESIS REFUTED {rf['on']}: {rf['reason']}. Measured rate "
                  f"{rf['measured_rate']:.1%} vs breakeven {rf['breakeven']:.1%} "
                  f"(LCB {rf['lcb']:.1%}). No station clears the bias gate, so the "
                  f"pilot correctly trades nothing. NO SEED. See CANDIDATE.md.")
    except Exception as e:
        print("paper pilot: skipped -", str(e)[:100])

    # HYPOTHESIS PROGRESS. Every open hypothesis has a registered data bar; the
    # point of this block is that checking on the project means reading one
    # line, not asking someone to interpret a directory. Counts only, no
    # results -- a progress meter must never leak an outcome.
    try:
        prog = _hypothesis_progress(obs)
        json.dump(prog, open("docs/hypotheses.json", "w"), indent=1)
        try:
            st = _status(obs, roll, yroll, units, coverage, profiles, pp, prog)
            json.dump(st, open("docs/status.json", "w"), indent=1)
            print(f"  status.json written ({st['schema']}): "
                  f"{st['data']['logged_days']} days, "
                  f"{len(st['blocking'])} hypothesis bar(s) still short")
        except Exception as _se:
            print("  status.json: skipped -", str(_se)[:90])
        print("\nHYPOTHESIS PROGRESS (data bars, not results)")
        for h in prog["hypotheses"]:
            legs = [h] + ([h["also"]] if h.get("also") else [])
            bar = min((l["have"] / l["need"] if l["need"] else 1.0) for l in legs)
            blocks = int(min(1.0, bar) * 20)
            print(f"  {h['id']:5} {h['name']:26} [{'#'*blocks}{'.'*(20-blocks)}] "
                  f"{h['have']}/{h['need']} {h['unit']}"
                  + (f"  +{h['note']}" if h.get("note") else ""))
    except Exception as e:
        print("hypothesis progress: skipped -", str(e)[:100])

    # AUTONOMOUS PILOT ACTIVATION (CANDIDATE.md, registered 2026-08-27).
    # Run each registered test whose data bar is met, record the verdict, and
    # activate the matching pilot ONLY on a pass. Both branches are automatic.
    try:
        from lowno import pilots
        gates = {}
        # H5 has no pilot; it is listed so its refusal is visible next to the
        # ones that can activate, rather than silently absent.
        for mod, hid in (("shape_eval", "H4a"), ("curve_lag", "H4b"),
                         ("band_eval", "H5"), ("h6_eval", "H6"),
                         ("shape_temp_eval", "H7")):
            try:
                m = __import__(mod)
                gates[hid] = m.verdict()
            except Exception as e:
                gates[hid] = dict(id=hid, ready=False, passed=False,
                                  error=str(e)[:120])
        gates["generated"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        json.dump(gates, open("docs/gates.json", "w"), indent=1)

        ev = None
        try:
            import curve_lag as _cl
            ev = _cl._events(_cl.series())
        except Exception:
            ev = None
        res = pilots.run_all(obs, gates, events=ev)
        json.dump(dict(generated=gates["generated"], pilots=res),
                  open("docs/pilots.json", "w"), indent=1)
        print("\nAUTONOMOUS PILOTS (activate on a PASSED test, not a met bar)")
        for r in res:
            g = r["gate"]
            state = ("ACTIVE" if r["active"] else
                     ("ready, FAILED test" if g["ready"] else "dormant"))
            line = (f"  {r['id']} <- {r['hypothesis']}  {state:22} "
                    f"${r.get('bankroll', 0):.2f} {r.get('n_trades', 0)} trades")
            if not r["active"] and g.get("reason"):
                line += f"  ({g['reason'][:52]})"
            print(line)
    except Exception as e:
        print("autonomous pilots: skipped -", str(e)[:110])

    if not any(r.get("proven") for r in roll):
        print("\nNo band's 95% lower bound clears its fee breakeven. Nothing proven.")



# H5 was registered 2026-08-31; only later days count as evidence for it.
H5_SINCE = "2026-09-01"

STATUS_SCHEMA = "lowno.status/1"


def _status(obs, roll, yroll, units, coverage, profiles, pilot, prog):
    """Consolidated MACHINE-READABLE project state -> docs/status.json.

    One document, stable keys, versioned schema, so a script or an agent can
    answer "where is this project" without parsing prose out of a README or a
    terminal dump. Everything here is a fact or a count; interpretation stays
    in CANDIDATE.md.
    """
    try:
        cache = json.load(open("docs/settlements.json"))
    except Exception:
        cache = {}
    try:
        verified = set(json.load(open("docs/settlements_verified.json")))
    except Exception:
        verified = set()
    try:
        world = json.load(open("docs/world.json"))
    except Exception:
        world = {}

    days = sorted({o["day"] for o in obs})
    proven_no = [b["band"] for b in roll if b.get("proven")]
    proven_yes = [b["band"] for b in (yroll or []) if b.get("proven")]

    hyp = []
    for h in prog["hypotheses"]:
        closed = not h["need"]
        hyp.append(dict(
            id=h["id"], name=h["name"],
            status="closed" if closed else "open",
            bar=None if closed else dict(
                have=h["have"], need=h["need"], unit=h["unit"],
                # A bar may have more than one constraint (H4b: events AND
                # days). `ready` comes from the progress record when it says so,
                # because `blocking` is contracted to mean "a test can run".
                ready=bool(h.get("ready", h["have"] >= h["need"])),
                **({"also": h["also"]} if h.get("also") else {})),
            note=h.get("note")))

    return dict(
        schema=STATUS_SCHEMA,
        generated=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        repo="mf4633/low-no",
        constitution=dict(
            paper_only=True, gate_frozen=True, live_capital_usd=0.0,
            orders_placed=0,
            seed_preconditions_met=False,
            interlock_line_printed=not any(b.get("proven") for b in roll)),
        data=dict(
            logged_days=len(days), first_day=(days[0] if days else None),
            last_day=(days[-1] if days else None),
            rung_observations=len(obs), independent_units=len(units),
            stations_us=len(CITIES),
            stations_world_listed=world.get("n_series"),
            stations_world_live=len(world.get("live") or []),
            scan_coverage=coverage),
        integrity=dict(
            cli_window_days=shadow.CLI_WINDOW_DAYS,
            settlements_cached=len(cache),
            settlements_verified=len(verified),
            settlements_unconfirmable=sum(1 for k in cache if k not in verified),
            note="unconfirmable = older than the CLI window; cannot be re-derived"),
        results=dict(
            no_bands_proven=proven_no, yes_bands_proven_nominal=proven_yes,
            no_bands_retired=[b["band"] for b in roll if b.get("retired")],
            nothing_proven=not proven_no),
        hypotheses=hyp,
        pilot=dict(
            status=pilot.get("status"), bankroll_usd=pilot.get("bankroll"),
            trades=pilot.get("n_trades"), wins=pilot.get("wins"),
            refuted=pilot.get("refuted")),
        blocking=[h for h in hyp if h["status"] == "open"
                  and not (h["bar"] or {}).get("ready")],
    )


def _hypothesis_progress(obs):
    """Data accumulated toward each open hypothesis's REGISTERED bar.

    Counts only. This must never report whether anything is working -- that is
    what the tests are for, and a progress meter that leaks an outcome invites
    exactly the peeking the registrations exist to prevent.
    """
    import glob as _g
    days = sorted(os.path.basename(p)[:-6] for p in _g.glob("logs/2*.jsonl")) \
        if False else sorted({o["day"] for o in obs})

    # H4a: out-of-sample shape validation needs a half-split where each half
    # earns cells at n>=12 per (city, hour, bucket); measured to need ~28 days.
    #
    # THE DAY COUNT IS NOT THE OPERATIVE GATE, and left alone it lies. The
    # registered bar is 28 logged days and it stays 28 -- but activation gates
    # on shape_eval.verdict() reaching MIN_SCORED held-out decisions, and the
    # day count reaches 28 first. Without an explicit `ready`, _status falls
    # back to have >= need, drops H4a out of `blocking`, and status.json
    # reports "a test is ready" while gates.json still says n=0/50. That is the
    # H4b meter bug of 414df64 with the hypotheses swapped. So: `ready` comes
    # from the test, and the real blocker rides along as a second leg. The
    # registered 28-day bar is UNCHANGED; MIN_SCORED was registered 2026-08-27
    # in the same breath, so surfacing it adds no requirement.
    #
    # COUNTS ONLY. `ready` and `n` are taken from the verdict; `passed` and the
    # Brier values are deliberately never read here.
    n_days = len(days)
    h4a_scored, h4a_ready, h4a_need = 0, False, 50
    try:
        import shape_eval as _se
        _v = _se.verdict()
        h4a_scored = int(_v.get("n") or 0)
        h4a_ready = bool(_v.get("ready"))
        h4a_need = int(_v.get("need") or _se.MIN_SCORED)
    except Exception:
        h4a_ready = False       # unknown counts as not-there, never as progress

    # H7: shape on temperature tendency. STRATIFIED -- the verdict needs
    # MIN_SCORED in EACH stratum, so the bar fills to its shortest leg. The
    # hourly pair (2 stations, nowcast from 2026-09-01) is the binding one.
    h7_ctl, h7_hr, h7_ready, h7_need = 0, 0, False, 50
    try:
        import shape_temp_eval as _st
        _v7 = _st.verdict()
        h7_ctl = int((_v7.get("control") or {}).get("n") or 0)
        h7_hr = int((_v7.get("hourly") or {}).get("n") or 0)
        h7_ready = bool(_v7.get("ready"))
        h7_need = int(_st.MIN_SCORED)
    except Exception:
        h7_ready = False

    # H6: does the market price off the stale print. Delegated to the test for
    # the same reason H4b is -- a meter that counts poll rows rather than
    # usable print transitions would read full on an unmet bar.
    h6_ev, h6_days, h6_ready, h6_need_ev, h6_need_d = 0, 0, False, 200, 20
    try:
        import h6_eval as _h6
        _e6 = _h6._events(_h6.series())
        h6_ev, h6_days = len(_e6), len({e["day"] for e in _e6})
        h6_need_ev, h6_need_d = _h6.MIN_EVENTS, _h6.MIN_DAYS
        h6_ready = bool(h6_ev >= h6_need_ev and h6_days >= h6_need_d)
    except Exception:
        h6_ready = False

    # H4b: EVENTS as curve_lag defines them -- a material |d(curve_dev)| on a
    # valid cycle gap with a real bottom-rung price -- not "cycles that logged
    # a curve_dev". Counting raw telemetry rows here read 984/200 while the
    # gate read 52/200, so the meter showed a full bar on an unmet bar. A
    # progress number that disagrees with its own test is worse than none.
    # Delegating to the test keeps them from drifting apart again.
    ev_need, day_need = 200, 20
    try:
        import curve_lag as _cl
        _ev = _cl._events(_cl.series())
        ev, ev_days = len(_ev), {e["day"] for e in _ev}
        ev_need, day_need = _cl.MIN_EVENTS, _cl.MIN_DAYS
    except Exception:
        # Unknown counts as not-there. Never let a failed count read as progress.
        ev, ev_days = 0, set()

    # H5: SUPPLY of the contested-band instrument on post-registration days.
    # Counts city-days carrying a real 81-95c bottom-rung ask inside the peak
    # window -- the universe the registered rule draws from, not the units it
    # would take, because the entry condition needs validated shape cells and
    # H4a has not passed. Same filter the eventual test uses, as far as it can
    # go without the cells: a meter that reads a different slice than its test
    # is the mistake this file has now made three times.
    h5_units, h5_days = set(), 0
    for path in sorted(_g.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        if day < H5_SINCE:
            continue
        h5_days += 1
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = r.get("detail")
            city = r.get("city")
            if not isinstance(d, dict) or d.get("world") or city not in CITIES:
                continue
            try:
                lt = (dt.datetime.fromisoformat(r["at"])
                      .replace(tzinfo=dt.timezone.utc)
                      .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])))
            except Exception:
                continue
            if not (13 <= lt.hour <= 16):
                continue
            for g in (d.get("rungs") or []):
                if g.get("fl") is not None or g.get("cap") is None:
                    continue
                na = g.get("na")
                if na is not None and 81 <= na <= 95:
                    h5_units.add((day, city))

    # PREREG_yes10_hotbias3 stays listed so its refutation is visible next to
    # the live ones rather than quietly dropped.
    return dict(
        generated=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        hypotheses=[
            dict(id="H4a", name="shape validation (held-out)",
                 have=n_days, need=28, unit="logged days",
                 also=dict(have=h4a_scored, need=h4a_need,
                           unit="held-out scored decisions"),
                 ready=h4a_ready,
                 note="days is not the gate -- cells must reach n>=12 inside "
                      "the peak window before a decision scores"),
            dict(id="H4b", name="market lag on curve_dev",
                 have=ev, need=ev_need, unit="events",
                 also=dict(have=len(ev_days), need=day_need,
                           unit="distinct days"),
                 ready=bool(ev >= ev_need and len(ev_days) >= day_need),
                 note=f"{len(ev_days)}/{day_need} distinct days"),
            dict(id="H5", name="contested band 81-95c (blocked on H4a)",
                 have=len(h5_units), need=60, unit="city-day units",
                 also=dict(have=0, need=1, unit="H4a passed"),
                 ready=False,
                 note=f"supply only; scoring waits on H4a ({h5_days} days since "
                      f"{H5_SINCE})"),
            dict(id="H6", name="market prices off the stale print",
                 have=h6_ev, need=h6_need_ev, unit="print transitions",
                 also=dict(have=h6_days, need=h6_need_d,
                           unit="distinct days"),
                 ready=h6_ready,
                 note=f"{h6_days}/{h6_need_d} distinct days; poll data starts "
                      "2026-08-31, NYC/DEN only"),
            dict(id="H7", name="shape on temperature (stratified)",
                 have=h7_ctl, need=h7_need, unit="scored (control)",
                 also=dict(have=h7_hr, need=h7_need, unit="scored (hourly)"),
                 ready=h7_ready,
                 note="the hourly pair is the binding leg; a verdict needs "
                      "both strata, pooled is context"),
            dict(id="H1", name="hot-bias (REFUTED 2026-08-27)",
                 have=0, need=0, unit="closed", note="do not revive"),
            dict(id="H2", name="early exit (REFUTED 2026-08-27)",
                 have=0, need=0, unit="closed", note="expectancy set at entry"),
            dict(id="H3", name="settlement gap (NOT SUPPORTED)",
                 have=0, need=0, unit="closed", note="real but priced"),
        ])


def _brier():
    """Score the forecasters against settlement. A verdict cannot be calibrated;
    a probability can. Both the model's p and the advisor's p_exceed are graded
    on every settled flag, so 'does the LLM add signal over the model' becomes a
    measured question rather than an opinion."""
    try:
        led = json.load(open("docs/ledger.json"))
    except Exception:
        return None
    rows = []
    for day in led.get("days", []):
        for f in day.get("flags", []):
            s, d = f.get("settle"), (f.get("detail") or {})
            cap = d.get("ceiling")
            if s is None or cap is None:
                continue
            y = 1.0 if s > cap else 0.0
            adv = f.get("advisor") or {}
            rows.append(dict(date=day["date"], city=f.get("city"), outcome=y,
                             p_model=(d.get("model") or {}).get("p_exceed_cap"),
                             p_advisor=adv.get("p_exceed")))
    def score(key):
        v = [(r[key], r["outcome"]) for r in rows if isinstance(r.get(key), (int, float))]
        if not v:
            return dict(n=0, brier=None)
        return dict(n=len(v), brier=round(sum((p - y) ** 2 for p, y in v) / len(v), 4))
    return dict(n_settled=len(rows), model=score("p_model"),
                advisor=score("p_advisor"), rows=rows[-20:],
                note="Brier: lower is better. 0.25 = always saying 50%. "
                     "Needs ~30+ settled flags before the comparison means anything.")


if __name__ == "__main__":
    main()
