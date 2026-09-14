r"""Invariants for city_regime.py / city_forecast.py / hf1min.py.

These are the checks that were run BEFORE the first real fetch, kept so they
cannot quietly stop being true. Three of them exist because the thing they test
is exactly the kind of silent error this project keeps having to dig out
afterwards:

  * the generalised classifier must reproduce the FROZEN lax_regime.regime()
    under PDT, or H15 and this build are measuring different objects while
    using the same vocabulary;
  * an unobserved decision window must be REFUSED, not read as "clear";
  * the 1-minute harvest must cut the LOCAL climate day, not the UTC day.

Stdlib only, no network. Run: python test_city_regime.py
"""
import datetime as dt
import random
import sys

import city_regime as CR
import city_forecast as CF
import lax_regime as LR

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILS.append(name)


# ------------------------------------------------------- classifier parity ---
def test_parity_with_frozen_lax():
    """LAX's windows are UTC 12-14/16-18/19-21, which ARE 05-07/09-11/12-14 PDT.
    Under PDT the two classifiers must agree on every input, or the local-hour
    generalisation changed the definition instead of relocating it."""
    rng = random.Random(7)
    mism = []
    for _ in range(4000):
        obs_utc = {h: rng.choice([None, None, 800.0, 1500.0, 2500.0, 4000.0, 9000.0])
                   for h in range(24)}
        obs_local = {(h - 7) % 24: v for h, v in obs_utc.items()}
        a, b = LR.regime(obs_utc), CR.regime(obs_local)
        if a != b:
            mism.append((obs_utc, a, b))
    check("regime() == lax_regime.regime() under PDT (4000 draws)",
          not mism, f"{len(mism)} mismatches, first {mism[:1]}")


def test_refuses_unobserved_window():
    full = {h: None for h in range(24)}
    check("full coverage, no cloud -> NO_STRATUS", CR.regime(full) == "NO_STRATUS")
    for win, label in ((CR.WIN_DAWN, "dawn"), (CR.WIN_MIDMORN, "mid-morning"),
                       (CR.WIN_EARLYPM, "early-pm")):
        partial = {h: None for h in range(24) if h not in win}
        check(f"{label} window unobserved -> refused (None)",
              CR.regime(partial) is None, f"got {CR.regime(partial)}")


def test_regime_ladder():
    base = {h: None for h in range(24)}
    cases = {
        "NO_STRATUS": {},
        "EARLY_BURN": {5: 900.0},
        "LATE_BURN": {5: 900.0, 10: 900.0},
        "NO_BURN": {5: 900.0, 10: 900.0, 13: 900.0},
    }
    for want, extra in cases.items():
        got = CR.regime({**base, **extra})
        check(f"regime ladder -> {want}", got == want, f"got {got}")
    check("morning_call collapses the two indistinguishable strata",
          CR.morning_call("LATE_BURN") == CR.morning_call("NO_BURN") == "STRATUS_HOLDING")
    check("morning_call passes the decidable strata through",
          CR.morning_call("NO_STRATUS") == "NO_STRATUS"
          and CR.morning_call("EARLY_BURN") == "EARLY_BURN")


def test_third_layer_is_not_cosmetic():
    """FEW008 SCT015 OVC025 is a legal ceiling under 3000 ft that a 2-layer read
    misses. If this ever stops differing, the extra layer can be dropped."""
    hdr = "station,valid,skyc1,skyl1,skyc2,skyl2,skyc3,skyl3"
    rows = [hdr] + [f"BOS,2024-08-15 {h:02d}:54,FEW,800,SCT,1500,OVC,2500"
                    for h in range(24)]
    got = CR.day_regimes("\n".join(rows), "America/New_York").get("2024-08-15")
    check("3-layer read sees a ceiling the 2-layer read does not",
          got == ("NO_BURN", "NO_STRATUS"), f"got {got}")


def test_day_regimes_uses_local_date():
    hdr = "station,valid,skyc1,skyl1,skyc2,skyl2,skyc3,skyl3"
    rows = [hdr]
    # OVC900 through 15Z = through 11:00 EDT; clear after -> LATE_BURN
    for h in range(24):
        c, l = ("OVC", "900") if h <= 15 else ("CLR", "M")
        rows.append(f"BOS,2024-08-15 {h:02d}:54,{c},{l},M,M,M,M")
    got = CR.day_regimes("\n".join(rows), "America/New_York")
    check("hourly CSV -> local-day regime", got.get("2024-08-15") == ("LATE_BURN",) * 2,
          f"got {got.get('2024-08-15')}")


# ------------------------------------------------------------- statistics ----
def test_permutation_is_calibrated():
    """Under the null the p-value must not be optimistic. 40 synthetic datasets
    with regime drawn independently of the high; p<=0.05 should happen about
    twice, and a run far above that means the within-month shuffle is broken."""
    rng = random.Random(11)
    months = [f"{m:02d}" for m in range(1, 13)]
    below, N = 0, 40
    for k in range(N):
        rows = []
        for _ in range(400):
            m = rng.choice(months)
            seas = 60 + 25 * (1 - abs(int(m) - 7) / 6)
            rows.append((f"2024-{m}-15", rng.choice(CR.REGIMES), seas + rng.gauss(0, 5)))
        _, p = CR.perm_p(CR.demean_by_month(rows), n=200, seed=1000 + k)
        below += p <= 0.05
    check(f"null: {below}/{N} runs at p<=0.05 (expect ~2, allow <=7)", below <= 7)


def test_permutation_has_power():
    rng = random.Random(3)
    months = [f"{m:02d}" for m in range(1, 13)]
    shift = dict(NO_STRATUS=3.0, EARLY_BURN=0.0, LATE_BURN=-3.0, NO_BURN=-6.0)
    rows = []
    for _ in range(400):
        m = rng.choice(months)
        g = rng.choice(CR.REGIMES)
        seas = 60 + 25 * (1 - abs(int(m) - 7) / 6)
        rows.append((f"2024-{m}-15", g, seas + shift[g] + rng.gauss(0, 5)))
    e2, p = CR.perm_p(CR.demean_by_month(rows), n=300, seed=5)
    check(f"3F effect detected (eta2={e2:.3f}, p={p:.4f})", e2 > 0.05 and p < 0.01)


def test_demean_removes_the_season():
    """A regime that is purely seasonal must score ~0, or the statistic is a
    season detector wearing a regime's name."""
    rows = []
    for m in range(1, 13):
        g = "NO_BURN" if m in (1, 2, 12) else "NO_STRATUS"
        for _ in range(40):
            rows.append((f"2024-{m:02d}-15", g, 40.0 + 4 * m))
    check("pure season -> eta^2 ~ 0", CR.eta_sq(CR.demean_by_month(rows)) < 1e-9)


def test_holm():
    got = CR.holm(dict(A=0.001, B=0.02, C=0.04, D=0.30, E=0.9))
    check("Holm: only A survives a family of 5", got == dict(A=True, B=False, C=False,
                                                            D=False, E=False), got)
    check("Holm: a family of 1 is plain alpha", CR.holm(dict(A=0.04)) == dict(A=True))


# -------------------------------------------------------------- forecast -----
def _synthetic_blob():
    rng = random.Random(3)
    shift = dict(NO_STRATUS=3, EARLY_BURN=-1, LATE_BURN=-3, NO_BURN=-6)
    rows = []
    for y in (2022, 2023, 2024, 2025, 2026):
        for i in range(365):
            d = (dt.date(y, 1, 1) + dt.timedelta(days=i))
            g = rng.choice(CF.REGIMES)
            base = 60 + 22 * (1 - abs(d.timetuple().tm_yday - 196) / 196)
            rows.append([d.isoformat(), g, round(base + shift[g] + rng.gauss(0, 4))])
    return {"TST": dict(station="KTST", tz="America/New_York", rows=rows)}


def test_forecast_is_a_distribution():
    b = _synthetic_blob()
    f = CF.forecast("TST", "NO_BURN", "2026-09-14", b)
    check("forecast cell is non-empty", f["n"] > 0)
    check("distribution sums to 1", abs(sum(f["dist"].values()) - 1.0) < 1e-9)
    check("unknown city returns n=0 rather than raising",
          CF.forecast("ZZZ", "NO_BURN", "2026-09-14", b)["n"] == 0)


def test_win_condition_partition():
    """THE WIN CONDITION (CLAUDE.md): a bottom-rung NO pays iff the day EXCEEDS
    the cap. p_exceeds and p_at_or_below must partition the mass exactly -- an
    off-by-one here is the error that has already inverted this project once."""
    b = _synthetic_blob()
    f = CF.forecast("TST", "NO_STRATUS", "2026-09-14", b)
    for cap in range(50, 100):
        tot = CF.p_exceeds(f["dist"], cap) + CF.p_at_or_below(f["dist"], cap)
        if abs(tot - 1.0) > 1e-9:
            check(f"p_exceeds + p_at_or_below == 1 at cap {cap}", False, tot)
            return
    check("p_exceeds + p_at_or_below == 1 at every cap 50-99", True)


# ----------------------------------------------------------------- hf1min ----
def test_hf1min_cuts_the_local_day():
    """sources.asos_1min_max requests a UTC day for a settlement defined on the
    LOCAL climate day. At a Pacific station that starts 7h late and ends 7h
    early, so the previous evening leaks in and the day's own evening is lost."""
    sys.argv = ["hf1min.py"]
    import hf1min as H

    def fake_get(url, timeout=120, tries=4):
        lines = ["station,valid(UTC),tmpf"]
        base = dt.datetime(2026, 9, 10, 0, 0)
        for i in range(2 * 1440):
            t = base + dt.timedelta(minutes=i)
            v = 70.0
            if t == dt.datetime(2026, 9, 10, 21, 0):
                v = 95.0        # 14:00 PDT on the day itself -- the real max
            if t == dt.datetime(2026, 9, 10, 4, 0):
                v = 99.0        # 21:00 PDT the PREVIOUS evening -- must not leak
            if t == dt.datetime(2026, 9, 11, 5, 0):
                v = 88.0        # 22:00 PDT on the day itself -- must be kept
            lines.append(f"SFO,{t.strftime('%Y-%m-%d %H:%M')},{v}")
        return chr(10).join(lines)

    orig, H._get = H._get, fake_get
    try:
        rows = H._iem_1min("SFO", "2026-09-10", "America/Los_Angeles")
        vals = sorted((v for _, v in rows), reverse=True)
        check("local day is exactly 1440 minutes", len(rows) == 1440, len(rows))
        check("previous local evening does not leak in", 99.0 not in vals)
        check("this local evening is kept", 88.0 in vals[:3])
        check("max is the day's own peak", vals[0] == 95.0, vals[:3])
        rec = H.harvest_day("SFO", "2026-09-10")
        check("harvest_day reports max, runner-up and count",
              rec["max_f"] == 95.0 and rec["second_f"] == 88.0 and rec["n_obs"] == 1440, rec)
    finally:
        H._get = orig


def test_hf1min_refuses_a_short_stream():
    sys.argv = ["hf1min.py"]
    import hf1min as H

    def short_get(url, timeout=120, tries=4):
        lines = ["station,valid(UTC),tmpf"]
        for i in range(24):      # hourly, not 1-minute
            lines.append(f"SFO,2026-09-10 {i:02d}:00,70.0")
        return chr(10).join(lines)

    orig, H._get = H._get, short_get
    try:
        check("an hourly stream is refused, not recorded as a 1-minute max",
              H.harvest_day("SFO", "2026-09-10") is None)
    finally:
        H._get = orig


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        print(f"\n{fn.__name__}")
        fn()
    print(f"\n{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILURES: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)
