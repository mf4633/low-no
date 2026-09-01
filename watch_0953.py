"""Wait for KDEN's 09:53 local print, then score the locked prediction.

The prediction was written to docs/locked_predictions.jsonl at 15:33Z, twenty
minutes before the observation existed, so this is a test rather than a fit.

Scores two separate things, which are easy to conflate:

  THE NOWCAST   predicts the next print. Directly testable against 15:53Z, and
                the only claim here that has ever been validated (+0.30F MAE at
                NYC, +0.86F at DEN, both surviving correction).

  ROUTE 1       predicts the DAILY HIGH from the earned climb distribution.
                15:53Z cannot falsify it -- it only re-anchors its input. What
                this reports is how far the route-1 distribution MOVES on one
                new observation, which is a measure of its stability, not of
                its accuracy.
"""
import datetime as dt
import json
import os
import time
import zoneinfo

from lowno import hourly_nowcast as hn, empirical as E

TARGET = "2026-09-01T15:53Z"
DEADLINE_MIN = 55


def latest_target_print():
    for ts, v in reversed(hn._series("KDEN")):
        if ts == TARGET:
            return v
    return None


def main():
    locked = None
    with open("docs/locked_predictions.jsonl") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("target", "").startswith("KDEN 09:53"):
                locked = r
    if not locked:
        print("no locked prediction found")
        return

    start = time.time()
    actual = None
    while (time.time() - start) / 60 < DEADLINE_MIN:
        actual = latest_target_print()
        if actual is not None:
            break
        time.sleep(120)
    if actual is None:
        print(f"{TARGET} still not published after {DEADLINE_MIN} min "
              f"(API lag) -- no score")
        return

    print(f"KDEN {TARGET} actual: {actual}F\n")
    print(f"{'estimator':26}{'predicted':>11}{'error':>9}")
    for k, lab in (("persistence_pred", "persistence (last print)"),
                   ("nowcast_pred_flat", "nowcast, held flat"),
                   ("nowcast_pred_projected", "nowcast, projected")):
        p = locked.get(k)
        if p is not None:
            print(f"{lab:26}{p:>10.2f}F{abs(actual-p):>+9.2f}")
    pe = abs(actual - locked["persistence_pred"])
    ne = abs(actual - locked["nowcast_pred_flat"])
    if pe > 0:
        print(f"\nnowcast cut the error by {100*(1-ne/pe):.0f}%"
              if ne < pe else
              f"\nnowcast was WORSE than persistence by {ne-pe:+.2f}F")

    # route 1 re-anchored on the new observation
    lt = dt.datetime.fromisoformat(TARGET.replace("Z", "+00:00")).astimezone(
        zoneinfo.ZoneInfo("America/Denver"))
    s = sorted(E._raw_climbs().get(("DEN", lt.hour), []))
    if s:
        highs = sorted(round(actual + x) for x in s)
        q = lambda p: highs[min(int(p * len(highs)), len(highs) - 1)]
        print(f"\nroute 1 re-anchored on {actual}F at hour {lt.hour} (n={len(s)}):")
        print(f"  p10 {q(.1)}F  p25 {q(.25)}F  p50 {q(.5)}F  p75 {q(.75)}F  p90 {q(.9)}F")
        print("  (climatology only -- it does not know today's guide of 86F,")
        print("   and analogue methods lost to the guide by 3.53F vs 1.75F MAE)")


if __name__ == "__main__":
    main()
