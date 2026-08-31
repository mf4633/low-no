"""Upwind weighting, done properly this time.

The first attempt (interp_wind.py) used max(0, cos(theta)), which ZEROES every
downwind station instead of tilting toward the upwind one, took wind direction
from each neighbour rather than the flow reaching the host, and applied at all
speeds including calm. Michael's point stands: that is not the hypothesis, it is
a crude caricature of it. So:

  * SOFT TILT, w = 1 + k*cos(theta), swept over k. k=0 is the equal-weight mean,
    so the baseline is nested inside the sweep and the whole curve is reported.
    If the best k is 0, that is the answer rather than an omission.
  * CONSENSUS FLOW from the vector mean of the neighbours' winds. KNYC reports a
    direction only 50% of the time and reads 5.4 km/h median with 33% calm --
    Central Park's anemometer is sheltered and cannot define the regional flow.
  * SPEED GATE. Upwind means nothing at 3 km/h; below the gate the tilt is off.
  * TRANSIT MATCH, the strongest form of the argument and untested until now: a
    station matters if the air over it NOW reaches the host within the horizon.
    Weight by a Gaussian on (distance/speed - lead), so stations whose air
    arrives on time are favoured over ones that merely lie upwind.

Read the transit times before the results. They decide the outcome.
"""
import datetime as dt
import json
import math
import os
import statistics

from interp_wind import coords, load, pearson, bearing
from interp_more import haversine
from nowcast import HOURLY, at_or_before, temp_of, field_of


def rows(city, lead):
    cfg = HOURLY[city]
    hs = [(k, temp_of(v)) for k, v in sorted(load(cfg["station"]).items())
          if temp_of(v) is not None]
    raw = {st: sorted(load(st).items()) for st in cfg["neighbours"]}
    out = []
    for i in range(1, len(hs)):
        t0, v0 = hs[i - 1]
        t1, v1 = hs[i]
        d0 = dt.datetime.fromisoformat(t0.replace("Z", "+00:00"))
        d1 = dt.datetime.fromisoformat(t1.replace("Z", "+00:00"))
        if not (40 <= (d1 - d0).total_seconds() / 60 <= 80):
            continue
        cut = (d1 - dt.timedelta(minutes=lead)).isoformat().replace("+00:00", "Z")[:16] + "Z"
        per = {}
        for st, s in raw.items():
            ser = [(k, temp_of(v)) for k, v in s if temp_of(v) is not None]
            a, b = at_or_before(ser, t0), at_or_before(ser, cut)
            if not a or not b or b[0] <= a[0]:
                continue
            wd = ws = None
            for ts, rr in reversed(s):
                if ts <= cut:
                    wd, ws = field_of(rr, "wd"), field_of(rr, "ws")
                    break
            per[st] = dict(d=b[1] - a[1], wd=wd, ws=ws)
        if len(per) == len(raw):
            out.append((v1 - v0, per))
    return out


def consensus(per):
    """Vector-mean wind over the neighbours: (from_direction_deg, speed_kmh)."""
    xs = ys = n = 0.0
    sp = []
    for v in per.values():
        if v["wd"] is None or v["ws"] is None:
            continue
        r = math.radians(v["wd"])
        xs += math.sin(r); ys += math.cos(r); n += 1
        sp.append(v["ws"])
    if not n:
        return None, None
    return (math.degrees(math.atan2(xs / n, ys / n)) + 360) % 360, statistics.fmean(sp)


def main():
    C = coords()
    for city, cfg in HOURLY.items():
        host = C[cfg["station"]]
        brg = {st: bearing(host[0], host[1], *C[st]) for st in cfg["neighbours"] if st in C}
        km = {st: haversine(host, C[st]) for st in cfg["neighbours"] if st in C}
        print(f"\n{'='*72}\n{city}: transit time of each neighbour's air, at its median wind")
        for st in sorted(km, key=km.get):
            print(f"   {st}  {km[st]:>6.1f} km  bearing {brg[st]:>5.0f}")

        for lead in (10, 20, 30):
            R = rows(city, lead)
            if len(R) < 40:
                continue
            act = [r[0] for r in R]
            print(f"\n  lead {lead}m, n={len(R)}")
            print(f"  {'scheme':26}{'r':>9}{'applied':>10}")
            for gate in (0, 8):
                for k in (0.0, 0.25, 0.5, 0.75, 1.0):
                    pred, applied = [], 0
                    for a, per in R:
                        wdir, spd = consensus(per)
                        use_k = k if (wdir is not None and spd is not None
                                      and spd >= gate) else 0.0
                        if use_k:
                            applied += 1
                        tot = num = 0.0
                        for st, v in per.items():
                            w = 1.0
                            if use_k and st in brg:
                                w = max(0.05, 1 + use_k * math.cos(
                                    math.radians(brg[st] - wdir)))
                            num += v["d"] * w; tot += w
                        pred.append(num / tot)
                    if k == 0.0 and gate:
                        continue
                    lbl = ("equal (k=0)" if k == 0 else
                           f"tilt k={k} gate>={gate}km/h")
                    print(f"  {lbl:26}{pearson(pred, act):>9.3f}"
                          f"{100*applied/len(R):>9.0f}%")

            # transit-time matching
            for sigma in (15, 30):
                pred = []
                for a, per in R:
                    tot = num = 0.0
                    for st, v in per.items():
                        w = 1.0
                        if v["ws"] and v["ws"] > 1 and st in km:
                            tt = 60.0 * km[st] / v["ws"]        # minutes
                            w = math.exp(-((tt - lead) ** 2) / (2.0 * sigma ** 2))
                            w = max(0.05, w)
                        num += v["d"] * w; tot += w
                    pred.append(num / tot)
                print(f"  {'transit match sd=' + str(sigma) + 'm':26}"
                      f"{pearson(pred, act):>9.3f}{'':>10}")


if __name__ == "__main__":
    main()
