# -*- coding: utf-8 -*-
"""Search the whole board for an edge, then price the search.

Every instrument (NO and YES, bottom/range/top), every price band, every
conditioner we have. An unconstrained sweep like this manufactures positives by
construction -- at 95% nominal, 1 in 20 empty slices comes back "significant" --
so the only number that means anything is the one corrected for how many slices
were actually tested.

Reports both, side by side, so the gap between them is visible.
"""
import json
import math
import statistics
from collections import defaultdict

from lowno import shadow

FEE = lambda pc: math.ceil(0.07 * 100 * (pc / 100) * (1 - pc / 100))
MIN_N = 20                    # below this a Wilson bound says nothing useful
NORM = statistics.NormalDist()


def wilson_lcb(k, n, z):
    if not n:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - m


def load():
    """Grade every rung with shadow's own rules, no network."""
    cache = json.load(open("docs/settlements.json"))
    shadow.settle_map = lambda days=None: {
        (d, c): v for k, v in cache.items() for d, c in [k.split("|")]}
    return shadow.build()


def band_of(p):
    for lo, hi in ((1, 10), (11, 20), (21, 30), (31, 40), (41, 50), (51, 60),
                   (61, 70), (71, 80), (81, 90), (91, 95), (96, 98)):
        if lo <= p <= hi:
            return f"{lo}-{hi}"
    return None


def hour_bucket(h):
    if h is None:
        return None
    return "morning" if h < 11 else "midday" if h < 13 else "peak" if h <= 16 else "late"


def rate_bucket(r):
    if r is None:
        return None
    return "stalled" if r <= 0.2 else "climbing" if r >= 1.5 else "mid"


MARINE = {"SFO", "LAX", "SAN"}


def conditioners(o):
    """Every way we can slice a single observation. One at a time, so the
    search space stays enumerable and the correction stays honest."""
    yield ("none", "all")
    hb = hour_bucket(o.get("local_hour"))
    if hb:
        yield ("hour", hb)
    rb = rate_bucket(o.get("rate"))
    if rb:
        yield ("rate", rb)
    yield ("coast", "marine" if o["city"] in MARINE else "inland")
    pop = o.get("pop")
    if pop is not None:
        yield ("pop", "wet" if pop >= 30 else "dry")
    g = o.get("G")
    if g is not None:
        yield ("G", "G>=4" if g >= 4 else "G<4")


def main():
    obs = load()
    print(f"graded observations: {len(obs)}")

    # (side, kind, band, cond_name, cond_value) -> one unit per city-day
    cells = defaultdict(dict)
    for o in obs:
        kind = o.get("kind", "bottom")
        for side in ("NO", "YES"):
            if side == "NO":
                px, won = o.get("price"), o.get("won")
            else:
                # real logged asks only: the derived 100-no_ask ignores the
                # spread and flatters the YES buyer into a fake edge.
                if o.get("yes_price_src") != "real_ask":
                    continue
                px, won = o.get("yes_price"), o.get("yes_won")
            if px is None or won is None or not (1 <= px <= 98):
                continue
            b = band_of(px)
            if b is None:
                continue
            for cname, cval in conditioners(o):
                key = (side, kind, b, cname, cval)
                cells[key].setdefault((o["day"], o["city"]), (px, won))

    tested = {k: v for k, v in cells.items() if len(v) >= MIN_N}
    N = len(tested)
    z_nom = NORM.inv_cdf(0.95)                 # one-sided 95%
    z_cor = NORM.inv_cdf(1 - 0.05 / max(N, 1))  # Bonferroni over the slices run
    print(f"slices with n >= {MIN_N}: {N}")
    print(f"  nominal one-sided 95%      -> z = {z_nom:.2f}")
    print(f"  Bonferroni 0.05/{N:<4}       -> z = {z_cor:.2f}")

    hits_nom, hits_cor = [], []
    for key, units in tested.items():
        n = len(units)
        k = sum(1 for _, w in units.values() if w)
        mp = sum(p for p, _ in units.values()) / n
        be = (mp + FEE(mp)) / 100.0
        rec = dict(key=key, n=n, k=k, hit=k / n, be=be,
                   lcb_nom=wilson_lcb(k, n, z_nom),
                   lcb_cor=wilson_lcb(k, n, z_cor))
        if rec["lcb_nom"] > be:
            hits_nom.append(rec)
        if rec["lcb_cor"] > be:
            hits_cor.append(rec)

    print(f"\nslices clearing breakeven at NOMINAL 95%:      {len(hits_nom)}")
    print(f"  expected by chance alone if nothing is real: ~{0.05*N:.0f}")
    print(f"slices clearing breakeven AFTER correction:    {len(hits_cor)}")

    if hits_nom:
        print(f"\n{'side':5}{'kind':7}{'band':8}{'slice':22}{'n':>5}{'hit':>7}"
              f"{'be':>7}{'LCB95':>8}{'LCBcor':>8}")
        for r in sorted(hits_nom, key=lambda x: -(x["lcb_cor"] - x["be"])):
            s, kd, b, cn, cv = r["key"]
            print(f"{s:5}{kd:7}{b:8}{cn+'='+cv:22}{r['n']:>5}{100*r['hit']:>6.1f}%"
                  f"{100*r['be']:>6.1f}%{100*r['lcb_nom']:>7.1f}%{100*r['lcb_cor']:>7.1f}%"
                  + ("   <= SURVIVES" if r in hits_cor else ""))
    if not hits_cor:
        print("\nNothing survives the correction.")


if __name__ == "__main__":
    main()
