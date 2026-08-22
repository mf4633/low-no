# low-no — read this before changing anything

Paper-trading measurement system for Kalshi daily-high temperature markets.
Its purpose is to find out whether an edge exists, not to make money yet.

## THE WIN CONDITION (counterintuitive — get this right)

The gate evaluates a bottom-ladder `<= CAP` bucket. We buy **NO**, so:

    THE POSITION PAYS IF AND ONLY IF THE DAILY MAX **EXCEEDS** THE CAP.
    settle >  ceiling -> WIN
    settle <= ceiling -> LOSS

Despite the name, "low-no" does NOT bet that temperatures stay low. It buys the
NO side of a low bucket, i.e. bets the day runs HOTTER than the cap. This is why
the gate requires G = guide - ceiling >= +4.

This inverted the Claude advisor once (2026-08-16): it reasoned correctly about
marine-layer suppression and then CONCURRED with a position that needed heat.
`lowno/advisor.py` now has a `_direction_guard` that downgrades any CONCUR whose
reasoning argues the day stays capped.

## THE CONSTITUTION

* **Paper only.** No orders. No live capital until promotion criteria are met.
* **The gate is FROZEN.** Do not change `GATE` in `lowno/config.py` for any
  reason. Every new idea goes in as a *scored variant* in `shadow_run.py`, never
  into the gate. A gate that drifts during measurement is unmeasurable.
* **No lottery scanner.** The strategy buys near-certainties at 96-98c. Cheap
  NO at 5-50c is a different (losing) instrument.
* **Hard position cap 5%** (`GATE["max_position_frac"]`), applied in `prob.py`.
  Half-Kelly at 97c prescribes 40%+ — correct arithmetic on an unproven p.

## STATE AS OF 2026-08-22

6 flags, 4W-2L. Real-money equivalent **-9.0%** capped, **-30.7%** flat.
157 shadow units, 21 stations, 16 days. **No band's Wilson LCB clears its fee
breakeven. Nothing is proven.**

Every loss so far has been SFO (marine layer, FORECAST_BUST).

## PROMOTION CRITERIA (see CANDIDATE.md)

* >= 60 independent city-day units passing the candidate rule
* Wilson 95% LCB on hit rate > fee breakeven at mean entry price
* No attribution category exceeding 10% of misses

Earliest ~mid-October. The date is set by flag rate, not by cleverness.

## KILL CRITERIA

* Any 3-loss run at 96-98c
* Station bias drift > 2F between weekly refits

## ARCHITECTURE

| file | role |
|---|---|
| `scan.py` | hourly scan; writes logs/, edge.json, active.json, traps.json |
| `gate.py` | FROZEN decision logic. `running_max_f` takes max across both obs streams |
| `prob.py` | Gaussian model + empirical blend, half-Kelly with LCB shrink and cap |
| `empirical.py` | P(exceed) from observed remaining-climb distribution |
| `adaptive.py` | recency-weighted station bias/sigma, seasonal when earned |
| `advisor.py` | Claude advisory layer (v2: state-injecting). Direction guard. |
| `shadow.py` / `shadow_run.py` | settles EVERY scanned rung; nightly variant scoring |
| `convergence.py` | per-station convergence hour, boundary cases |
| `traps.py` | positive-edge rungs carrying measured trap signals |
| `advection.py` | upstream station + intraday stall telemetry |
| `forecasts.py` / `skill.py` | 6 competing forecasts, scored against CLI |
| `score_run.py` | nightly grade; grades ALL ungraded log days, ET trading date |

## HARD-WON GOTCHAS — do not re-learn these

1. **Kalshi quotes are `*_dollars` strings** ("0.98"), not integer cents. The
   legacy `yes_bid` field is gone. Reading it returned a constant and the gate
   rejected 100% on price for four days while looking healthy.
2. **Kalshi orderbook sides are both resting BIDS.** To buy NO at P you lift a
   YES bid at (100-P). Reading `no_dollars` as asks reports the wrong side.
3. **Three bucket types per ladder**: bottom (`fl` None), range (both), top
   (`cap` None). Each has a different win condition. Grading them all as
   bottoms produced 99-point probability errors.
4. **CLI products are indexed by SITE** (SFO, DEN, NYC), *not* by WFO. `MTR`,
   `BOU`, `OKX` return zero products.
5. **`date.today()` on a UTC runner is tomorrow after 8pm ET.** Always use the
   ET trading date.
6. **`X or default` on numeric fields is a bug** — `yes_bid=0` is a real quote.
7. **Kalshi series tickers are not airport codes**: `KXHIGHTLV` (Las Vegas),
   `KXHIGHTNOLA` (New Orleans), `KXHIGHTSATX` (San Antonio).
8. **A wrong series ticker fails SILENTLY** as an empty ladder, indistinguishable
   from a quiet market. Always verify new stations return rungs > 0.
9. **`|| true` in workflows hides everything.** Removed deliberately.
10. **NOT a bug**: the 5-minute obs and the :53 METARs agree. Measured
    2026-08-22, paired at matched timestamps: -0.17F over 26 pairs. An earlier
    max-over-mismatched-windows comparison suggested -1.74F; that was a sampling
    artifact, not a bias.

## THE METHODOLOGICAL POINT

On 2026-08-22 a careful intraday read of KMSY moved 40% -> 15% -> 20% -> 45%
over two hours while the market sat near 38 the entire time. Separately, a
confident "the 5-minute obs are biased cool" hypothesis — built from one vivid
METAR — died in ten minutes to a proper paired test.

Shadow data says the market wins ~7 of 8 model-market disputes.

Careful reasoning does not protect against this. Structure does: frozen gate,
scored variants, Wilson bounds, and the line that prints at the bottom of every
nightly run —

    "No band's 95% lower bound clears its fee breakeven. Nothing proven."

That sentence is a safety interlock. If it ever disappears without a band
genuinely clearing its bar, something has broken in the scoring.
