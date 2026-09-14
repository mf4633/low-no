# dawn12 -- the pre-dawn 12-hour-advance prediction

REGISTERED 2026-09-14. The ensemble membership, the issuance hour and the
distribution method are fixed in `dawn12.py`'s FROZEN block and in this file.
Corrections are appended with a reason.

## WHAT "12 HOURS" MEANS HERE, MEASURED

Over 681 city-days in this log the observed daily peak sits at **p10 12.8,
median 15.7, p90 17.6 local**. Issuance at 04:00 local is therefore **11.7
hours before the median peak**. That is the lead this file is named for, and it
is measured rather than assumed.

It is also, unavoidably, **before every sky window `city_regime.py` uses** --
the earliest is 05-07 local. So none of the regime machinery is available at
issuance and none is used. At 04:00 the inputs are numerical guidance and
nothing else: no observed climb, no morning sky, no book.

## THE ENSEMBLE -- FROZEN

    om_gfs      GFS       (NOAA global, via Open-Meteo)
    om_icon     ICON      (DWD)
    om_metno    MET Norway
    nbm_guide   NWS       (api.weather.gov /forecast, first daytime period)

Equal weight, each member bias-corrected by its own pooled mean error. Three
candidates are excluded for measured reasons:

| excluded | why |
|---|---|
| `om_best` | Open-Meteo `best_match` resolves to GFS in the US: identical to `om_gfs` on 5,222 of 5,226 logged rows (99.92%). Including both double-weights GFS. |
| `nws_grid` | The SAME NWS forecaster product as `nbm_guide` read through a different endpoint (`/forecastGridData` vs `/forecast`), not an independent model. Of the two readings the period temperature is better at this hour: solo MAE 1.89 vs 2.55, residual sd 2.60 vs 3.43. |
| `om_ecmwf` | Solo MAE 3.19, residual sd 4.29 -- roughly double every other member, in every lead bucket in the record. |

So the frozen set is three independent NWP chains plus one human-adjusted NWS
forecast, which is as decorrelated as this input set gets.

**`om_best` contaminates `docs/skill.json` too.** Its pooled `mean` and
`median` rows are computed over a source list containing both `om_best` and
`om_gfs`, so they are GFS-tilted. Not fixed here; recorded so it is not
rediscovered.

## MEASURED SKILL -- leave-one-DAY-out, 413 pre-dawn city-days, 16 days, 23 cities

| configuration | MAE | sd | within 2F |
|---|---|---|---|
| best bias-corrected single (`nbm_guide`) | 1.890 | 2.60 | 64.2% |
| ENS4, `nws_grid` in and guide out | 1.651 | 2.26 | 71.4% |
| ENS5, both NWS readings in | 1.598 | 2.21 | 72.6% |
| **ENS4b -- FROZEN** | **1.503** | **2.08** | **75.5%** |

**1.503 IS AN IN-SELECTION NUMBER.** Five configurations were compared on the
same 16 days, so the member set is chosen on the data it is scored against and
the honest forward expectation is worse. Every locked prediction therefore also
records the three alternatives, and `dawn12.py --score` reports the forward
number on locked predictions only. **That number, not this table, is the
result.** It does not exist yet.

## THE DISTRIBUTION

P(CLI high = k) from the **empirical** residual distribution of the frozen
ensemble, discretised to integer degrees F -- not a Gaussian. Same reason
`lax_forecast.py` is empirical: these highs are not normal, and a measured tail
beats an assumed one. `p_exceeds(dist, cap)` gives P(high > cap), which is what
a bottom-rung NO position pays on (CLAUDE.md, THE WIN CONDITION).

## WHAT IS DELIBERATELY NOT DONE, each because it was measured to not pay

* **No per-station bias.** Measured to HURT: 1.652 -> 1.684 MAE. Per-city
  residual counts here are 5 to 40; a per-city term fits noise. H4a's lesson.
* **No marine/continental split.** Marine residual sd 2.49 vs continental 2.12,
  a ratio of 1.17 -- not enough to pay for the cell.
* **No inverse-variance weighting.** 1.749 vs 1.744 for the plain mean.
* **No regime conditioning.** Not available at this hour.

## THE UNIT, AND WHY IT CANNOT BE INFLATED

One prediction per **city-day**. The issuance window is +/-1h because GitHub
drops scheduled fires and this project has already lost a day of peak coverage
to a single-slot assumption -- but a wide window with hourly crons would lock
the same city two or three times and silently triple its weight in every later
score. `dawn12.already_locked()` enforces one per city-day.

## THE BOOK IS CAPTURED, AND CAPTURED ONLY

Each locked record carries the Kalshi ladder as quoted AT ISSUANCE, in a `book`
field that feeds nothing and is read by nothing. It exists because it cannot be
captured later: "is this prediction already inside the price?" is a separate
registration, and it would be unanswerable in sixty days if the pre-dawn book
were not recorded now. A missing book degrades to `null` and never costs a
prediction.

Recording it is not the same as testing it. Nothing in this file compares the
two, and doing so is a new registration with its own units.

## THIS IS A FORECAST, NOT A SIGNAL

Nothing here claims the number is outside the price, and the standing evidence
says it is inside: the market was 3.2x better calibrated than a model of this
class at KNYC/KDEN (Brier 0.0298 vs 0.0948), and trading the disagreements lost
5.8-6.7c per trade at every margin tested. A trading claim on this is a
separate registration with its own 60 units, its own Wilson LCB bar and its own
kill lines.

## KILL CRITERIA FOR THE FROZEN ENSEMBLE

* Forward MAE (from `--score`) exceeding the best bias-corrected single member
  over 60+ locked city-days -> the ensemble is not earning its complexity and
  collapses to that single member.
* Any member's bias drifting more than 2F between weekly recalibrations -> that
  member's feed has changed and the frozen set is re-opened with a reason.
