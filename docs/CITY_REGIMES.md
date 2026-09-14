# The morning-sky regime, at every Kalshi city

WRITTEN 2026-09-14, BEFORE ANY CITY'S NUMBERS WERE READ. The classifier, the
windows, the threshold, the statistic, the permutation null and the
multiple-comparison rule are all fixed in this file and in `city_regime.py`'s
FROZEN block. This text does not change; corrections are appended with a reason,
like every other correction in this repository.

## THIS IS NOT A HYPOTHESIS AND IT LICENSES NOTHING

H15 separated its weather leg from its market claim and said so in capitals:
"the weather leg is already measured and is NOT the hypothesis." This document
is the weather leg, and only the weather leg, extended from one station to
twenty-four.

    IT ASKS: does a morning-observable sky regime split the daily high at this
    city, once the season is removed?

    IT DOES NOT ASK: is that split in the price?

The second question is the only one that could ever produce an edge, and the
standing answer to it is discouraging: H3 ("real but priced"), the 2026-09-12
price comparison (market Brier 0.0298 against a model's 0.0948, 3.2x better),
and H4a, which reached its information bar and then lost 6.16% anyway. A city
that survives everything below has earned a *measurement*, not a position. Any
trading claim on one is a separate registration with its own 60 units, its own
Wilson LCB bar and its own kill lines.

## THE CLASSIFIER -- FROZEN

Decided from that city's own hourly METAR sky groups. "Stratus" is a BKN or OVC
base below **3000 ft**, read across sky layers 1-3. Windows are in **local**
time:

    dawn         05, 06, 07 local
    mid-morning  09, 10, 11 local
    early pm     12, 13, 14 local

    NO_STRATUS   no stratus at dawn and none mid-morning
    EARLY_BURN   stratus in the morning, gone by the early-pm window
    LATE_BURN    stratus still mid-morning, gone by the early-pm window
    NO_BURN      stratus still present in the early-pm window

A day whose three windows are not all observed is **refused**, not classified.

## THREE DIFFERENCES FROM `lax_regime.py`, EACH A FIX

`lax_regime.py` is frozen and carries H15. It is not touched, imported or
superseded, and this build writes `city_regimes.json` -- never
`lax_regimes.json`.

1. **Local hours, not UTC hours.** LAX's windows are UTC 12-14 / 16-18 / 19-21,
   which *are* 05-07 / 09-11 / 12-14 PDT. Hard-coding the UTC values would aim
   those windows at 08:00 in Boston and 05:00 in Seattle. Verified on 4,000
   randomised observation sets: under PDT this classifier reproduces
   `lax_regime.regime()` exactly, 0 mismatches. Under PST the two differ by an
   hour, which is exactly why H15 keeps its own frozen input file.

2. **Three sky layers, not two.** METAR reports layers ascending by base, so a
   ceiling under 3000 ft is nearly always layer 1 -- but `FEW008 SCT015 OVC025`
   is legal and a 2-layer read scores it NO_STRATUS. Demonstrated on a
   synthetic day: 3-layer says NO_BURN, 2-layer says NO_STRATUS. The
   disagreement is **counted per city and printed**, rather than assumed
   negligible.

3. **Window coverage is required, not inferred.** LAX accepts any day with >=18
   hourly sky obs. That does not guarantee the three decision windows are among
   them, and a missing window reads as "no stratus" -- silently. Silently is how
   the `verdict == "LADDER"` filter hid four August days from the settlement
   quarantine, and how a max-so-far froze into a fake +5.0F SAT bias. Every
   refused day is reported in the coverage column.

## THE STATISTIC, AND THE MULTIPLICITY PROBLEM

The LAX result was one pre-specified test at one station. Asking the same
question at 24 cities is a family, and at alpha=0.05 a family of 24 buys
roughly one false positive by construction. Two guards, both fixed now:

* **Statistic.** CLI highs are demeaned within calendar month, so a regime that
  is merely a seasonal proxy scores zero. `eta^2` is then the share of that
  within-month variance the regime label explains.
* **Null.** Regime labels are permuted **within calendar month**, 2,000 draws,
  so the null is "the regime carries nothing beyond the season" rather than
  "the labels are unrelated to anything".
* **Family.** Holm-Bonferroni across every tested city at alpha = 0.05. A city
  that does not survive Holm is reported as noise, in the same table, with its
  p-value visible.

Calibration was checked before any real data was fetched: 60 synthetic null
datasets gave 5 p-values at or below 0.05 (expected 3, binomial sd 1.7), and an
injected 3F effect returned eta^2 = 0.282 at p = 0.002.

## WHAT WOULD MAKE THIS WRONG

* A city surviving Holm whose surviving regime cell is thin (n < 25 in the
  trading window) is a small-sample artefact, not a result. `city_forecast.py`
  refuses to trust such a cell and widens the seasonal window instead.
* A large 3-vs-2-layer disagreement count at a city means the classifier is
  sensitive to a reporting convention rather than to weather. It is printed for
  exactly this reason.
* If nearly every city survives, the statistic is picking up something
  structural -- cloud cover suppresses daytime heating everywhere, which is
  meteorology, not an inefficiency. The interesting column is then the
  *magnitude* of the variance collapse and the *share* of days in the suppressed
  regimes, not the p-value.

## THE ENTRY-WINDOW PROBLEM, STATED NOW

The frozen gate's entry window is 09:00-13:00 local. The early-pm window closes
at 14:00 local, so **LATE_BURN and NO_BURN are not distinguishable inside the
entry window.** H15's own text says its classifier is knowable "by 10:00 PDT"
while its NO_BURN test reads 19Z-21Z (12:00-14:00 PDT); those two statements
cannot both be true, and this file does not repeat the claim.

`city_regime.morning_call()` is therefore provided: the deterministic 3-way
collapse (`NO_STRATUS`, `EARLY_BURN`, `STRATUS_HOLDING`) that *is* knowable by
11:00 local. It is a function of the same observations, not a second fit. Any
rule that would have to act during the entry window can use only that one.

## THE 1-MINUTE RECORD (`hf1min.py`) -- WHY IT IS SEPARATE

`hf1min.py` ships alongside but tests nothing. It harvests the 1-minute ASOS
maximum per city-day into `docs/settlements_1min.json`, because two known
defects meet there: the CLI expires after seven days (gotcha 11) and our own
`run_max` is quantised to whole degrees C while the CLI settles in whole
degrees F (gotcha 13). The 1-minute record is reported in whole degrees F and
does not expire.

It corrects the local-day error in `sources.asos_1min_max`, which requests a
**UTC** day for a settlement defined on the **local** climate day -- seven hours
late and seven hours early at a Pacific station. Verified on a synthetic feed:
a 99F reading at 21:00 PDT on the previous evening is excluded, an 88F reading
at 22:00 PDT on the day itself is kept.

It writes a parallel file. It does not overwrite `docs/settlements.json`, does
not feed the gate, and grades nothing.
