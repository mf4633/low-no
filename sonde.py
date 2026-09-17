r"""Does the 12Z sounding predict how WRONG the day will be?

THE CLAIM IS ABOUT VARIANCE, NOT THE MEAN. `dawn12.py` already gets the mean to
MAE 1.50F and NBM assimilates soundings anyway, so a better centre is not on
offer. What the project does NOT have is any per-day estimate of SPREAD:
`prob.py` takes one sigma per CITY from `adaptive.bias_sigma()` and hard-codes
`MARINE = {SFO, LAX, SAN}` as "Gaussian unfit" -- a permanent blacklist, not a
measurement -- and `dawn12.py` applies ONE pooled residual distribution to all
23 cities on every day.

WHY A SOUNDING AND NOTHING ELSE. The daily max at a mixing-limited station is a
closure, not a regression: the mixed layer warms dry-adiabatically until the
heat absorbed equals the area between the observed profile and the surface
adiabat. So theta_ML(Q) is set by the observed profile, and the SENSITIVITY
dT/dQ goes as 1/h -- inversely with the depth being mixed. A deep adiabatic
profile barely moves when Q is wrong; a strong low inversion makes T climb fast,
then STALL at the cap, then JUMP if it breaks. That step-and-jump IS the
bimodality, and its location is measured by the profile.

Nothing else here can see it. Surface obs (1-min, 5-min, METAR) cannot see
aloft. Model t850/z500 is the model's own guess at two levels -- an area
integral needs more than two points, and it is not independent of the model's
own surface forecast. `city_regime.py`'s BKN/OVC-below-3000ft test is a PROXY
that only fires when the cap is deep and moist enough to condense a deck; a
shallow or dry cap reads NO_STRATUS while the inversion is still there.

THE PRIMARY METRIC, FROZEN BEFORE ANY RESULT WAS READ

    Q2000 -- the sensible heat per unit area (MJ/m^2) needed to mix the
    boundary layer to 2000 m AGL by encroachment from the 12Z profile:

        Q(z) = integral_0^z  rho(z') c_p [theta(z) - theta(z')] dz'

    High Q2000 = strongly resistant, a threshold day. Q2000 ~ 0 = already well
    mixed, so the day's max should track its forcing smoothly.

Chosen because it is one number, it is the actual physical resistance rather
than a proxy for it, and it needs no tuning constant. 2000 m AGL is a fixed
height, not a fitted one.

WHAT THIS IS NOT. Not a trading claim, not a gate input, not a variant. It
grades nothing and writes nothing any scorer reads. A sounding tells you the
day's RESISTANCE and never its FORCING -- cloud evolution after launch is the
other half of the heat budget and is invisible here.

Usage:  python sonde.py --coverage        nearest sounding site to every city
        python sonde.py --test DEN
"""
import argparse
import datetime as dt
import io
import json
import math
import os
import random
import statistics as st
import time
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict

from lowno.config import CITIES

# ---------------------------------------------------------------- FROZEN ----
MIX_TOP_M = 2000.0        # AGL, fixed not fitted
YEARS = (2022, 2023, 2024, 2025, 2026)
SONDE_HOUR = 12           # the morning sounding
MIN_LEVELS = 12           # below this the profile cannot support an integral
MIN_N = 200               # below this the test reports as UNDER-POWERED
N_PERM = 2000
CP = 1004.0               # J/(kg K)
RD = 287.05
P0 = 100000.0             # Pa

IGRA = "https://www.ncei.noaa.gov/pub/data/igra/data/data-por"
STATION_LIST = "https://www.ncei.noaa.gov/pub/data/igra/igra2-station-list.txt"
CACHE = "cache"
UA = {"User-Agent": "lowno (contact: github.com/mf4633)"}


def _get(url, timeout=600, binary=False, tries=8):
    """Fetch with backoff. NCEI returns 503 routinely under load, and the first
    run of this file died outright on a single one -- every downstream step with
    it -- because there was no retry at all. city_regime.cached() already had
    this and sonde.py shipped without it."""
    last = None
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = r.read()
            return d if binary else d.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except Exception as e:
            last = str(e)[:80]
        if a < tries - 1:
            w = min(120, 5 * (2 ** a))
            print(f"    {url.rsplit('/', 1)[-1]}: {last} -- backoff {w}s "
                  f"(attempt {a + 1}/{tries})", flush=True)
            time.sleep(w)
    raise RuntimeError(f"{url}: {last} after {tries} attempts")


def haversine_km(a, b, c, d):
    R = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


# ------------------------------------------------------------- COVERAGE -----
def station_list():
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, "igra2-station-list.txt")
    if not (os.path.exists(p) and os.path.getsize(p) > 10000):
        io.open(p, "w", encoding="utf-8").write(_get(STATION_LIST, timeout=180))
    out = []
    for ln in io.open(p, encoding="utf-8"):
        if len(ln) < 82:
            continue
        try:
            sid = ln[0:11].strip()
            lat, lon = float(ln[12:20]), float(ln[21:30])
            elev = float(ln[31:37])
            name = ln[41:71].strip()
            first = int(ln[72:76])
            last = int(ln[77:81])
        except Exception:
            continue
        if abs(lat) > 90 or abs(lon) > 180 or lat < -98:
            continue
        out.append(dict(id=sid, lat=lat, lon=lon, elev=elev, name=name,
                        first=first, last=last))
    return out


def coverage(active_since=2025):
    """Nearest CURRENTLY-REPORTING sounding site to each Kalshi city."""
    stns = [s for s in station_list() if s["last"] >= active_since]
    print(f"IGRA sites still reporting since {active_since}: {len(stns)}\n")
    hdr = (f"{'city':<5} {'stn':<6} {'nearest sonde':<26} {'IGRA id':<13}"
           f"{'km':>6}{'site_m':>8}  within 80km")
    print(hdr); print("-" * len(hdr))
    rows = []
    for c in sorted(CITIES):
        m = CITIES[c]
        best = min(stns, key=lambda s: haversine_km(m["lat"], m["lon"], s["lat"], s["lon"]))
        km = haversine_km(m["lat"], m["lon"], best["lat"], best["lon"])
        rows.append((c, best, km))
        # IGRA writes -999.9 for a missing elevation; printing it as -1000 m
        # would read as a real value below sea level.
        ev = "  --" if best["elev"] < -900 else f"{best['elev']:.0f}"
        print(f"{c:<5} {m['station']:<6} {best['name'][:25]:<26} {best['id']:<13}"
              f"{km:>6.0f}{ev:>8}  {'YES' if km <= 80 else ''}")
    print("\n  A sounding is representative of the city's boundary layer only if it")
    print("  samples the same airmass. Coastal gradients run over tens of km, so a")
    print("  distant site is the station-mismatch problem in another costume.")
    return rows


# ------------------------------------------------------------- SOUNDINGS ----
def fetch_soundings(igra_id):
    """{YYYY-MM-DD: [(press_pa, gph_m, temp_k), ...]} for SONDE_HOUR, YEARS.

    IGRA v2 fixed-width. Parsed by column and then VALIDATED (pressure
    decreasing, temperature physical) -- a format drift that silently produced
    plausible-looking garbage is exactly the failure this project keeps finding.
    """
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{igra_id}-data.txt.zip")
    if not (os.path.exists(p) and os.path.getsize(p) > 100000):
        print(f"  downloading {igra_id} period-of-record ...", flush=True)
        io.open(p, "wb").write(_get(f"{IGRA}/{igra_id}-data.txt.zip", binary=True))
    print(f"  {os.path.getsize(p)/1e6:.1f} MB on disk; parsing {YEARS[0]}-{YEARS[-1]} "
          f"{SONDE_HOUR:02d}Z", flush=True)

    out, keep, day, nhdr = {}, False, None, 0
    with zipfile.ZipFile(p) as z:
        name = z.namelist()[0]
        with z.open(name) as fh:
            for raw in io.TextIOWrapper(fh, encoding="utf-8", errors="replace"):
                if raw.startswith("#"):
                    nhdr += 1
                    try:
                        y, mo, d, hh = (int(raw[13:17]), int(raw[18:20]),
                                        int(raw[21:23]), int(raw[24:26]))
                    except Exception:
                        keep = False
                        continue
                    keep = (y in YEARS and hh == SONDE_HOUR)
                    day = f"{y:04d}-{mo:02d}-{d:02d}" if keep else None
                    if keep:
                        out.setdefault(day, [])
                    continue
                if not keep or day is None:
                    continue
                try:
                    press = int(raw[9:15])
                    gph = int(raw[16:21])
                    temp = int(raw[22:27])
                except Exception:
                    continue
                if press in (-9999, -8888) or gph in (-9999, -8888) or temp in (-9999, -8888):
                    continue
                if not (1000 <= press <= 110000) or not (-1000 <= gph <= 40000):
                    continue
                tk = temp / 10.0 + 273.15
                if not (150.0 < tk < 340.0):
                    continue
                out[day].append((float(press), float(gph), tk))
    good = {d: v for d, v in out.items() if len(v) >= MIN_LEVELS}
    print(f"  {nhdr} headers scanned -> {len(out)} {SONDE_HOUR:02d}Z days, "
          f"{len(good)} with >= {MIN_LEVELS} valid levels")
    if good:
        k = sorted(good)[len(good) // 2]
        s = sorted(good[k], key=lambda r: -r[0])[:4]
        print(f"  sample {k}: " + "  ".join(f"{p0/100:.0f}hPa/{z0:.0f}m/{t-273.15:+.1f}C"
                                            for p0, z0, t in s))
    return good


def theta(press_pa, temp_k):
    return temp_k * (P0 / press_pa) ** (RD / CP)


def q_to_mix(levels, top_m):
    """Sensible heat (MJ/m^2) to mix to `top_m` AGL by encroachment. None if unusable."""
    lv = sorted(levels, key=lambda r: -r[0])            # surface first
    if len(lv) < MIN_LEVELS:
        return None
    z0 = lv[0][1]
    prof = [(p, z - z0, theta(p, t)) for p, z, t in lv if z - z0 >= 0]
    if len(prof) < MIN_LEVELS or prof[0][1] > 50:       # surface level must be near ground
        return None
    inside = [r for r in prof if r[1] <= top_m]
    if len(inside) < 4 or inside[-1][1] < top_m * 0.6:  # need the layer actually sampled
        return None
    th_top = inside[-1][2]
    j = 0.0
    for i in range(len(inside) - 1):
        p_a, z_a, th_a = inside[i]
        p_b, z_b, th_b = inside[i + 1]
        dz = z_b - z_a
        if dz <= 0:
            continue
        # rho from the layer mean, deficit from the layer mean
        p_m = 0.5 * (p_a + p_b)
        th_m = 0.5 * (th_a + th_b)
        t_m = th_m * (p_m / P0) ** (RD / CP)
        rho = p_m / (RD * t_m)
        j += rho * CP * max(0.0, th_top - th_m) * dz
    return j / 1e6


# ---------------------------------------------------------------- TEST ------
def spearman(x, y):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(x), rank(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def perm_p(x, y, months, n=N_PERM, seed=20260915):
    """Permute y WITHIN calendar month, so the null is 'no relation beyond season'."""
    obs = spearman(x, y)
    rng = random.Random(seed)
    idx = defaultdict(list)
    for i, m in enumerate(months):
        idx[m].append(i)
    hits = 0
    work = list(y)
    for _ in range(n):
        for _m, ii in idx.items():
            pool = [y[i] for i in ii]
            rng.shuffle(pool)
            for i, v in zip(ii, pool):
                work[i] = v
        if spearman(x, work) >= obs:
            hits += 1
    return obs, (hits + 1) / (n + 1)


def nearest_dump(city, n=10):
    """The n nearest IGRA sites INCLUDING inactive ones, with their record span.

    Exists because the first coverage run gave DEN its nearest site as GRAND
    JUNCTION at 341 km, across the Continental Divide, when Denver has had an
    upper-air site for decades. Either that site stopped reporting or the
    `last >= 2025` filter is reading the wrong column, and guessing which would
    be exactly the kind of assumption this project keeps having to undo.
    """
    m = CITIES[city]
    stns = station_list()
    ranked = sorted(stns, key=lambda s: haversine_km(m["lat"], m["lon"], s["lat"], s["lon"]))
    print(f"\n{city} ({m['station']}) at {m['lat']:.3f},{m['lon']:.3f} -- "
          f"{n} nearest IGRA sites, ACTIVE OR NOT\n")
    hdr = f"{'IGRA id':<13}{'name':<30}{'km':>6}{'elev':>7}{'first':>7}{'last':>6}"
    print(hdr); print("-" * len(hdr))
    for s_ in ranked[:n]:
        km = haversine_km(m["lat"], m["lon"], s_["lat"], s_["lon"])
        ev = "  --" if s_["elev"] < -900 else f"{s_['elev']:.0f}"
        print(f"{s_['id']:<13}{s_['name'][:29]:<30}{km:>6.0f}{ev:>7}"
              f"{s_['first']:>7}{s_['last']:>6}")


# RESOLVED SITES, pinned from the committed coverage run (sonde_coverage.txt /
# docs/sonde_result.json, 2026-09-15). Generated from those files, not retyped.
#
# WHY PIN THEM. Three consecutive runs died because the 1 MB IGRA station list
# 503'd, and the station list is METADATA -- site coordinates -- not the data
# under test. Resolving a site that a committed run already resolved should not
# require a network call that can take the whole measurement down with it. The
# sounding archives still come from NCEI, so the primary test and its effect
# size continue to read the SAME slice; only the lookup is pinned.
#
# It also makes the choice of site reproducible: a later change to IGRA's
# station list cannot silently move a city onto a different sounding.
RESOLVED = {
    "ATL": ("USM00072215", 32.6),
    "DAL": ("USM00072249", 25.3),
    "DC": ("USM00072403", 37.7),
    "LAS": ("USM00072388", 3.4),
    "MIA": ("USM00072202", 10.9),
    "MSP": ("USM00072649", 26.7),
    "MSY": ("USM00072233", 56.5),
    "OKC": ("USM00072357", 27.5),
    "PHX": ("USM00074626", 6.0),
    "SAN": ("USM00072293", 12.7),
    "SFO": ("USM00072493", 19.3),
}


def igra_for_city(city, max_km=80.0):
    """The nearest currently-reporting IGRA site, refused beyond `max_km`.

    Uses the pinned RESOLVED table when the city is in it, and only falls back
    to downloading the station list otherwise.
    """
    if city in RESOLVED:
        sid, km = RESOLVED[city]
        return dict(id=sid, name=f"{sid} (pinned)", elev=float("nan"),
                    lat=None, lon=None, first=0, last=9999), km
    m = CITIES[city]
    stns = [s for s in station_list() if s["last"] >= 2025]
    best = min(stns, key=lambda s: haversine_km(m["lat"], m["lon"], s["lat"], s["lon"]))
    km = haversine_km(m["lat"], m["lon"], best["lat"], best["lon"])
    return best, km


def dev_rows(city, max_km=80.0, quiet=False):
    """[(day, Q2000, CLI high - that month's mean)] or None.

    THE SINGLE SOURCE for both the primary test and the effect size. They must
    read the same slice: a statistic and its illustration computed on different
    data is the H4b-meter error, and the first sonde run shipped a quartile
    table cut on RAW Q2000 while the p-value was computed within month.
    """
    blob = json.loads(io.open("city_regimes.json", encoding="utf-8").read())
    if city not in blob:
        raise SystemExit(f"{city} not in city_regimes.json -- run city_regime.py")
    cli = {d: h for d, g, h in blob[city]["rows"]}
    stn, km = igra_for_city(city)
    if not quiet:
        print(f"\n{city} ({CITIES[city]['station']}) -> {stn['name']} [{stn['id']}], "
              f"{km:.0f} km away\n")
    if km > max_km:
        if not quiet:
            print(f"  REFUSED: {km:.0f} km exceeds the {max_km:.0f} km limit. A sounding")
            print("  that far off samples a different boundary layer.")
        return None, stn, km
    snd = fetch_soundings(stn["id"]) if not quiet else fetch_soundings(stn["id"])
    rows = []
    for d, lv in sorted(snd.items()):
        if d not in cli:
            continue
        q = q_to_mix(lv, MIX_TOP_M)
        if q is None:
            continue
        rows.append((d, q, cli[d]))
    if not quiet:
        print(f"  matched {len(rows)} days with BOTH a usable 12Z profile and a CLI high")
    if len(rows) < 30:
        if not quiet:
            print("  too few to test.")
        return None, stn, km
    bym = defaultdict(list)
    for d, q, h in rows:
        bym[d[5:7]].append(h)
    mu = {m: sum(v) / len(v) for m, v in bym.items()}
    return [(d, q, h - mu[d[5:7]]) for d, q, h in rows], stn, km


def within_month_quartiles(dev):
    """Assign each day a Q2000 quartile computed WITHIN its own calendar month.

    Cutting quartiles on raw Q2000 across all months puts winter in the top
    quartile, and winter is wider for reasons that have nothing to do with the
    cap. That confound is the whole reason this function exists.
    """
    bym = defaultdict(list)
    for r in dev:
        bym[r[0][5:7]].append(r)
    out = []
    for m, rows in bym.items():
        rows = sorted(rows, key=lambda r: r[1])
        n = len(rows)
        if n < 8:
            continue
        for i, r in enumerate(rows):
            out.append((min(3, (4 * i) // n), r))
    return out


def _quartile_stats(tagged):
    st_ = {}
    for qi in range(4):
        v = [r[2] for t, r in tagged if t == qi]
        if len(v) < 5:
            continue
        st_[qi] = dict(n=len(v), mean=st.mean(v), absmean=st.mean([abs(z) for z in v]),
                       sd=st.pstdev(v), tail=sum(1 for z in v if z <= -5) / len(v))
    return st_


def effect_size(city, max_km=80.0, n_boot=2000, seed=20260916):
    """Within-month Q2000 quartiles, and the sd ratio Q4/Q1 with a bootstrap CI."""
    dev, stn, km = dev_rows(city, max_km=max_km)
    if not dev:
        return None
    tagged = within_month_quartiles(dev)
    stats = _quartile_stats(tagged)
    if 0 not in stats or 3 not in stats:
        print("  quartiles too thin"); return None
    print(f"\n  WITHIN-MONTH Q2000 quartile (season removed from the CUT, not just "
          f"the outcome)")
    hdr = (f"  {'quartile':<10}{'n':>6}{'mean dev':>10}{'|dev|':>8}{'sd':>8}"
           f"{'P(dev<=-5F)':>13}")
    print(hdr); print("  " + "-" * (len(hdr) - 2))
    for qi in range(4):
        if qi not in stats:
            continue
        v = stats[qi]
        print(f"  Q{qi+1:<9}{v['n']:>6}{v['mean']:>+10.2f}{v['absmean']:>8.2f}"
              f"{v['sd']:>8.2f}{v['tail']:>12.1%}")
    ratio = stats[3]["sd"] / stats[0]["sd"]
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        samp = [dev[rng.randrange(len(dev))] for _ in range(len(dev))]
        t = _quartile_stats(within_month_quartiles(samp))
        if 0 in t and 3 in t and t[0]["sd"] > 0:
            boots.append(t[3]["sd"] / t[0]["sd"])
    boots.sort()
    lo = boots[int(0.025 * len(boots))] if boots else float("nan")
    hi = boots[int(0.975 * len(boots))] if boots else float("nan")
    print(f"\n  sd ratio Q4/Q1 = {ratio:.3f}   bootstrap 95% CI [{lo:.3f}, {hi:.3f}]"
          f"   ({len(boots)} draws)")
    print(f"  tail ratio  Q4/Q1 = {stats[3]['tail']/max(stats[0]['tail'],1e-9):.2f}"
          f"  ({stats[3]['tail']:.1%} vs {stats[0]['tail']:.1%})")
    return dict(city=city, station=stn["id"], km=round(km, 1), n=len(dev),
                sd_q1=round(stats[0]["sd"], 3), sd_q4=round(stats[3]["sd"], 3),
                sd_ratio=round(ratio, 3), ci_lo=round(lo, 3), ci_hi=round(hi, 3),
                tail_q1=round(stats[0]["tail"], 4), tail_q4=round(stats[3]["tail"], 4))


def run_test(city, max_km=80.0):
    blob = json.loads(io.open("city_regimes.json", encoding="utf-8").read())
    if city not in blob:
        raise SystemExit(f"{city} not in city_regimes.json -- run city_regime.py")
    cli = {d: h for d, g, h in blob[city]["rows"]}

    stn, km = igra_for_city(city)
    print(f"\n{city} ({CITIES[city]['station']}) -> {stn['name']} [{stn['id']}], "
          f"{km:.0f} km away\n")
    if km > max_km:
        print(f"  REFUSED: {km:.0f} km exceeds the {max_km:.0f} km limit. A sounding")
        print("  that far off samples a different boundary layer.")
        return None

    snd = fetch_soundings(stn["id"])
    rows = []
    for d, lv in sorted(snd.items()):
        if d not in cli:
            continue
        q = q_to_mix(lv, MIX_TOP_M)
        if q is None:
            continue
        rows.append((d, q, cli[d]))
    print(f"  matched {len(rows)} days with BOTH a usable 12Z profile and a CLI high")
    if len(rows) < 30:
        print("  too few to test."); return None

    # deviation from that month's own mean -- season removed, as in city_regime
    bym = defaultdict(list)
    for d, q, h in rows:
        bym[d[5:7]].append(h)
    mu = {m: sum(v) / len(v) for m, v in bym.items()}
    dev = [(d, q, h - mu[d[5:7]]) for d, q, h in rows]

    x = [q for _, q, _ in dev]
    absdev = [abs(v) for _, _, v in dev]
    months = [d[5:7] for d, _, _ in dev]

    print(f"\n  Q2000 (MJ/m^2): min {min(x):.2f}  median {sorted(x)[len(x)//2]:.2f}  "
          f"max {max(x):.2f}")
    print(f"  |deviation| (F): mean {st.mean(absdev):.2f}  sd {st.pstdev(absdev):.2f}")

    rho, p = perm_p(x, absdev, months)
    powered = len(dev) >= MIN_N
    print(f"\n  PRIMARY  Spearman(Q2000, |deviation|) = {rho:+.4f}   "
          f"p = {p:.4f}   n = {len(dev)}")
    print(f"           pre-specified direction: POSITIVE (more cap -> larger miss)")
    if not powered:
        print(f"           UNDER-POWERED: n < {MIN_N}, read as indicative only")

    # quartile table -- descriptive, shows the shape the correlation compresses
    q4 = sorted(dev, key=lambda r: r[1])
    cut = len(q4) // 4
    print(f"\n  {'Q2000 quartile':<16}{'n':>5}{'mean dev':>10}{'|dev|':>8}{'sd':>8}"
          f"{'P(dev<=-5F)':>13}")
    for i in range(4):
        part = q4[i * cut: (i + 1) * cut] if i < 3 else q4[3 * cut:]
        v = [r[2] for r in part]
        lo, hi = part[0][1], part[-1][1]
        print(f"  {f'{lo:.1f}-{hi:.1f}':<16}{len(v):>5}{st.mean(v):>+10.2f}"
              f"{st.mean([abs(z) for z in v]):>8.2f}{st.pstdev(v):>8.2f}"
              f"{sum(1 for z in v if z <= -5)/len(v):>12.1%}")

    # SECONDARY, pre-specified and expected to be under-powered: the left tail
    lo_q = [r for r in q4[:cut]]
    hi_q = [r for r in q4[3 * cut:]]
    pl = lambda part: sum(1 for r in part if r[2] <= -5) / len(part)
    print(f"\n  SECONDARY left tail  P(dev <= -5F): "
          f"lowest quartile {pl(lo_q):.1%}  vs highest {pl(hi_q):.1%}")
    print("  A variance claim is not an edge, and an edge is not a position.")
    return dict(city=city, station=stn["id"], km=round(km, 1), n=len(dev),
                spearman=round(rho, 4), p_perm=round(p, 4), powered=powered)


def holm(pvals, alpha=0.05):
    order = sorted(pvals, key=lambda k: pvals[k])
    m, out, still = len(order), {}, True
    for i, k in enumerate(order):
        if still and pvals[k] <= alpha / (m - i):
            out[k] = True
        else:
            still = False
            out[k] = False
    return out


def test_all(max_km=80.0):
    """Every city inside the distance limit, corrected as ONE family.

    Run as a family rather than a chosen station. DEN was named in the
    pre-specification as the first station and the frozen 80 km limit refuses
    it, so SOMETHING had to change -- and picking the next station by hand,
    after seeing which ones have instruments, is how a family of tests gets
    reported as a single one. Selecting on instrument AVAILABILITY is legitimate
    (no outcome has been seen); selecting on RESULT is not, and running all of
    them removes the question.
    """
    elig = [c for c in sorted(RESOLVED) if RESOLVED[c][1] <= max_km]
    if not elig:
        stns = [x for x in station_list() if x["last"] >= 2025]
        for c in sorted(CITIES):
            m = CITIES[c]
            best = min(stns, key=lambda s: haversine_km(m["lat"], m["lon"],
                                                        s["lat"], s["lon"]))
            if haversine_km(m["lat"], m["lon"], best["lat"], best["lon"]) <= max_km:
                elig.append(c)
    print(f"cities within {max_km:.0f} km of a reporting sounding: "
          f"{len(elig)} -- {', '.join(elig)}\n")
    res = {}
    for c in elig:
        try:
            r = run_test(c, max_km=max_km)
        except Exception as e:
            print(f"  {c}: FAILED {str(e)[:90]}")
            continue
        if r:
            res[c] = r
    if not res:
        print("\nno city produced a testable sample")
        return res
    pv = {c: r["p_perm"] for c, r in res.items()}
    surv = holm(pv)
    print("\n\nFAMILY RESULT -- Holm-Bonferroni across every tested city, alpha=0.05\n")
    hdr = f"{'city':<5}{'sonde':<13}{'km':>5}{'n':>6}{'rho':>9}{'p':>8}{'holm':>6}{'powered':>9}"
    print(hdr); print("-" * len(hdr))
    for c in sorted(res, key=lambda k: -res[k]["spearman"]):
        r = res[c]
        r["holm_survives"] = bool(surv.get(c))
        print(f"{c:<5}{r['station']:<13}{r['km']:>5.0f}{r['n']:>6}{r['spearman']:>+9.4f}"
              f"{r['p_perm']:>8.4f}{('YES' if surv.get(c) else 'no'):>6}"
              f"{('yes' if r['powered'] else 'NO'):>9}")
    n_sig = sum(1 for c in res if res[c]["holm_survives"])
    print(f"\n  {n_sig} of {len(res)} survive Holm. Direction was pre-specified "
          f"POSITIVE;\n  a negative rho is a falsification, not a two-sided result.")
    return res


def effect_all(cities, max_km=80.0):
    """Effect size at EVERY tested city, not only the survivors.

    An effect size measured only where the test passed is upward-biased by
    selection -- the winner's curse. Printing the non-survivors alongside is how
    a reader sees how much of DAL's and OKC's magnitude is selection and how
    much is signal. This is DESCRIPTION computed after the primary test, not a
    second test, and it carries no p-value of its own.
    """
    out = {}
    for c in cities:
        try:
            r = effect_size(c, max_km=max_km)
        except Exception as e:
            print(f"  {c}: FAILED {str(e)[:90]}")
            continue
        if r:
            out[c] = r
    if not out:
        return out
    surv = {"DAL", "OKC"}
    print("\n\nWITHIN-MONTH EFFECT SIZE -- every tested city, survivors marked\n")
    hdr = (f"{'city':<5}{'n':>6}{'sd Q1':>8}{'sd Q4':>8}{'ratio':>8}"
           f"{'95% CI':>16}{'tail Q1':>9}{'tail Q4':>9}  Holm")
    print(hdr); print("-" * len(hdr))
    for c in sorted(out, key=lambda k: -out[k]["sd_ratio"]):
        r = out[c]
        ci = f"[{r['ci_lo']:.2f}, {r['ci_hi']:.2f}]"
        tag = "SURVIVOR" if c in surv else ""
        print(f"{c:<5}{r['n']:>6}{r['sd_q1']:>8.2f}{r['sd_q4']:>8.2f}"
              f"{r['sd_ratio']:>8.3f}{ci:>16}"
              f"{r['tail_q1']:>8.1%}{r['tail_q4']:>9.1%}  {tag}")
    print("\n  ratio > 1 means high-cap days are WIDER within the same month.")
    print("  A CI containing 1.00 is a magnitude consistent with no effect.")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--test", default=None, help="city code, e.g. DEN")
    ap.add_argument("--test-all", action="store_true",
                    help="every city inside --max-km, Holm-corrected as a family")
    ap.add_argument("--nearest", default=None, help="diagnostic: n nearest sites")
    ap.add_argument("--effect", default=None,
                    help="within-month effect size; comma list or 'tested'")
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--max-km", type=float, default=80.0)
    a = ap.parse_args()
    if a.nearest:
        nearest_dump(a.nearest.upper(), a.n)
    if a.coverage:
        coverage()
    if a.effect:
        if a.effect.strip().lower() == "tested":
            prev = json.loads(io.open("docs/sonde_result.json", encoding="utf-8").read())
            cl = sorted(prev.get("cities", {}))
        else:
            cl = [x.strip().upper() for x in a.effect.split(",")]
        rs = effect_all(cl, max_km=a.max_km)
        if rs:
            p_ = "docs/sonde_effect.json"
            io.open(p_, "w", encoding="utf-8").write(json.dumps(
                dict(at=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                     note="within-month Q2000 quartiles; description, not a test",
                     cities=rs), indent=1))
            print(f"\n  wrote {p_}")
    if a.test_all:
        rs = test_all(max_km=a.max_km)
        if rs:
            os.makedirs("docs", exist_ok=True)
            io.open("docs/sonde_result.json", "w", encoding="utf-8").write(json.dumps(
                dict(at=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                     metric=f"Q{int(MIX_TOP_M)} MJ/m2", years=list(YEARS),
                     max_km=a.max_km, cities=rs), indent=1))
            print("\n  wrote docs/sonde_result.json")
    if a.test:
        r = run_test(a.test.upper(), max_km=a.max_km)
        if r:
            os.makedirs("docs", exist_ok=True)
            p = "docs/sonde_result.json"
            cur = json.loads(io.open(p, encoding="utf-8").read()) if os.path.exists(p) else {}
            cur[r["city"]] = dict(r, at=dt.datetime.now(dt.timezone.utc)
                                  .isoformat().replace("+00:00", "Z"),
                                  metric=f"Q{int(MIX_TOP_M)} MJ/m2", years=list(YEARS))
            io.open(p, "w", encoding="utf-8").write(json.dumps(cur, indent=1))
            print(f"\n  wrote {p}")
    if not (a.coverage or a.test or a.test_all or a.nearest or a.effect):
        ap.print_help()


if __name__ == "__main__":
    main()
