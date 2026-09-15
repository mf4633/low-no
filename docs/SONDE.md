# Does the 12Z sounding predict how WRONG the day will be?

WRITTEN 2026-09-15, BEFORE ANY RESULT WAS READ. The metric, the height, the
statistic, the null, the direction, the distance limit and the power floor are
fixed here and in `sonde.py`'s FROZEN block. Corrections are appended with a
reason.

## THE CLAIM IS ABOUT VARIANCE, NOT THE MEAN

The obvious test -- "does a sounding improve the forecast centre?" -- is the one
most likely to fail, and it is not this one. `dawn12.py` already reaches MAE
1.50F at 12h lead, and every NWP chain in that ensemble assimilates these same
soundings, so a better centre is not on offer.

What the project does NOT have is any per-day estimate of SPREAD:

* `prob.py` takes one `sigma` per **city** from `adaptive.bias_sigma()`, not per
  day, and hard-codes `MARINE = {SFO, LAX, SAN}` as `"marine/unfit"` -- a
  permanent blacklist, not a measurement.
* `dawn12.py` applies ONE pooled empirical residual distribution to all 23
  cities on every day. Per-city and marine splits were tested and did not pay.

    CLAIM: the 12Z profile measures how RESISTANT today's boundary layer is,
    and resistance predicts the MAGNITUDE of the day's departure from its
    seasonal expectation.

## WHY A SOUNDING AND NOTHING ELSE

The daily max at a mixing-limited station is a closure, not a regression: the
mixed layer warms dry-adiabatically until the heat absorbed equals the area
between the observed profile and the surface adiabat. So the sensitivity dT/dQ
goes as 1/h, inversely with the depth being mixed. A deep adiabatic profile
barely moves when the forcing is wrong. A strong low inversion makes the surface
climb fast, then STALL at the cap, then JUMP if it breaks. **That step-and-jump
is the bimodality**, and the profile measures where it sits.

Nothing else in this stack can see it:

| source | why it cannot |
|---|---|
| 1-min / 5-min obs, METAR | cannot see above the surface at all |
| model `t850` / `z500` | the model's own guess, at two levels; an area integral needs more than two points, and it is not independent of that model's surface forecast |
| `city_regime.py` BKN/OVC < 3000 ft | a PROXY -- fires only when the cap is deep and moist enough to condense a deck. A shallow or dry cap reads NO_STRATUS while the inversion is still there. This is a blind spot in that classifier. |

## THE PRIMARY METRIC -- FROZEN

    Q2000 = the sensible heat per unit area (MJ/m^2) required to mix the
    boundary layer to 2000 m AGL by encroachment from the 12Z profile:

        Q(z) = integral_0^z rho(z') c_p [theta(z) - theta(z')] dz'

One number, the actual physical resistance rather than a proxy for it, and no
tuning constant. 2000 m AGL is a fixed height, not a fitted one. Verified
offline before any data was fetched: a perfectly dry-adiabatic profile returns
**0.0000 MJ/m^2**, and a 10 K cap in the lowest 400 m returns **2.379 MJ/m^2**,
which is the hand-calculated value.

## THE TEST -- FROZEN

* **Statistic**: Spearman rank correlation between Q2000 and `|CLI high - that
  month's mean CLI high|`, the same month-removed construction `city_regime.py`
  uses, so a seasonal cycle in cap strength cannot manufacture the result.
* **Direction**: pre-specified **POSITIVE** -- more cap, larger miss. A negative
  correlation of any size falsifies it; it does not become a two-sided test
  afterwards.
* **Null**: the deviation is permuted WITHIN calendar month, 2,000 draws, so the
  null is "resistance carries nothing beyond the season". Calibration checked on
  synthetic nulls before any real data: 2 of 40 runs at p <= 0.05 against an
  expected 2, and an injected relation returned rho +0.433 at p = 0.002.
* **Power floor**: n >= 200 matched days. Below that the result prints as
  UNDER-POWERED and is read as indicative only.

## THE DISTANCE LIMIT -- FROZEN AT 80 km

A sounding is representative only if it samples the same boundary layer.
Coastal gradients run over tens of km, so a distant site is the station-mismatch
problem in another costume -- the same error as grading KHOU against KIAH.
`sonde.py` REFUSES any city whose nearest currently-reporting IGRA site is more
than 80 km away, rather than quietly using it.

This is expected to exclude most of the 23 cities, and **probably the marine
trio SFO/LAX/SAN, which is where every loss in the ledger lives**. If it does,
that is the finding: the instrument that would help most cannot reach the
stations that need it. The coverage table is computed from IGRA's own station
list, not from recollection.

## SECONDARY, PRE-SPECIFIED AND EXPECTED TO BE UNDER-POWERED

The left tail: `P(deviation <= -5F)` in the lowest versus highest Q2000
quartile. This is the operationally interesting number -- a bottom-rung NO at
96-98c is selling exactly this tail -- and with a handful of cool busts per
quartile it will not reach significance. It is reported as description, not as
a test, and the primary stands or falls on its own.

## WHAT A PASS WOULD AND WOULD NOT LICENSE

A pass says resistance predicts spread. It does NOT say the market has missed
it: soundings are assimilated into every NWP run and into the NBM the market
anchors on, so the standing prior is H3, H4a and the 3.2x Brier gap. Turning
this into a per-day sigma inside `prob.py` would be a change to a scored path
and needs its own registration; turning it into a position needs 60 units and a
Wilson bar. **Nothing here grades anything, feeds the gate, or writes a file any
scorer reads.**

## WHAT IT CANNOT DO, IN ANY VERSION

A sounding gives theta(z) at launch, not Q. Cloud evolution after launch is the
other half of the heat budget and is invisible to it, as is advection that
reshapes the profile. **It tells you the day's RESISTANCE and never its
FORCING.** A pass would therefore explain part of the spread, never all of it.
