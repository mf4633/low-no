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


def _get(url, timeout=600, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = r.read()
    return d if binary else d.decode("utf-8", "replace")


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
            last = int(ln[77:81])
        except Exception:
            continue
        if abs(lat) > 90 or abs(lon) > 180 or lat < -98:
            continue
        out.append(dict(id=sid, lat=lat, lon=lon, elev=elev, name=name, last=last))
    return out


def coverage(active_since=2025):
    """Nearest CURRENTLY-REPORTING sounding site to each Kalshi city."""
    stns = [s for s in station_list() if s["last"] >= active_since]
    print(f"IGRA sites still reporting since {active_since}: {len(stns)}\n")
    hdr = f"{'city':<5}{'station':<6}{'nearest sonde':<26}{'IGRA id':<13}{'km':>7}{'dz_m':>8}"
    print(hdr); print("-" * len(hdr))
    rows = []
    for c in sorted(CITIES):
        m = CITIES[c]
        best = min(stns, key=lambda s: haversine_km(m["lat"], m["lon"], s["lat"], s["lon"]))
        km = haversine_km(m["lat"], m["lon"], best["lat"], best["lon"])
        rows.append((c, best, km))
        print(f"{c:<5}{m['station']:<6}{best['name'][:25]:<26}{best['id']:<13}"
              f"{km:>7.0f}{best['elev']:>8.0f}")
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


def igra_for_city(city, max_km=80.0):
    """The nearest currently-reporting IGRA site, refused beyond `max_km`."""
    m = CITIES[city]
    stns = [s for s in station_list() if s["last"] >= 2025]
    best = min(stns, key=lambda s: haversine_km(m["lat"], m["lon"], s["lat"], s["lon"]))
    km = haversine_km(m["lat"], m["lon"], best["lat"], best["lon"])
    return best, km


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--test", default=None, help="city code, e.g. DEN")
    ap.add_argument("--max-km", type=float, default=80.0)
    a = ap.parse_args()
    if a.coverage:
        coverage()
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
    if not a.coverage and not a.test:
        ap.print_help()


if __name__ == "__main__":
    main()
