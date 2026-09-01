"""Sample the KDEN nowcast every 5 minutes until the 09:53 local print.

Michael is watching a possible deceleration. The first read of it may have been
an artefact: the nowcast went +1.8F/hr, then +0.6, then +2.3 within eight
minutes, and each change coincided with the ALIGNMENT WINDOW changing length as
neighbours published. A rate measured over 17 minutes and a rate measured over
27 minutes are not the same estimator, so comparing them across samples is
comparing apples to oranges.

So every row logs the window and the neighbour count alongside the rate. If the
rate moves while the window is stable, that is weather. If it moves whenever the
window moves, it is arithmetic.
"""
import datetime as dt
import json
import os
import time
import zoneinfo

from lowno import hourly_nowcast as hn

STOP = dt.datetime(2026, 9, 1, 15, 58, tzinfo=dt.timezone.utc)   # a little past 09:53L
OUT = "docs/den_0953_samples.jsonl"
TZ = zoneinfo.ZoneInfo("America/Denver")


def main():
    os.makedirs("docs", exist_ok=True)
    print(f"{'local':>7}{'nowcast':>10}{'F/hr':>8}{'win':>6}{'nbrs':>7}"
          f"{'spread':>8}  aligned_to   last print")
    seen = set()
    while dt.datetime.now(dt.timezone.utc) < STOP:
        now = dt.datetime.now(dt.timezone.utc)
        lt = now.astimezone(TZ)
        v, d = hn.estimate("DEN", None)
        if isinstance(d, dict):
            rate = 60 * (d["nowcast_f"] - d["last_print_f"]) / max(d["window_min"], 1)
            row = dict(at=now.isoformat().replace("+00:00", "Z"),
                       local=lt.strftime("%H:%M"), nowcast=d["nowcast_f"],
                       rate=round(rate, 2), window_min=d["window_min"],
                       n=d["n_neighbours"], spread=d["spread_f"],
                       aligned_to=d["aligned_to"], last_print=d["last_print_f"],
                       last_print_at=d["last_print_at"])
            print(f"{lt:%H:%M}L{d['nowcast_f']:>10.2f}{rate:>+8.1f}"
                  f"{d['window_min']:>5}m{d['n_neighbours']:>4}/{d['n_expected']}"
                  f"{d['spread_f']:>8.2f}  {d['aligned_to'][11:16]}Z"
                  f"     {d['last_print_f']}F @{d['last_print_at'][11:16]}Z")
        else:
            row = dict(at=now.isoformat().replace("+00:00", "Z"),
                       local=lt.strftime("%H:%M"), refused=str(d))
            print(f"{lt:%H:%M}L   REFUSED: {d}")
        with open(OUT, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        # note when a NEW host print lands -- that is the thing being predicted
        ts = row.get("last_print_at")
        if ts and ts not in seen:
            seen.add(ts)
            if len(seen) > 1:
                print(f"        ^^ NEW HOST PRINT: {row['last_print']}F @{ts[11:16]}Z")
        time.sleep(300)
    print(f"\nstopped at {STOP:%H:%M}Z; samples in {OUT}")


if __name__ == "__main__":
    main()
