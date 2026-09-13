"""Tunable constants. One place, so balance is a diff and not an archaeology dig."""

from __future__ import annotations

# --- calendar ---------------------------------------------------------------
DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR
START_YEAR = 1247
START_MONTH = 3            # you take the seat in spring, not in a snowdrift

SEASON_OF_MONTH = {
    1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn",
    11: "autumn", 12: "winter",
}
# Field yield by season. Winter is the whole reason granaries exist.
FIELD_YIELD = {"winter": 0.35, "spring": 0.90, "summer": 1.40, "autumn": 1.15}
# Orchards are a harvest, not a flow.
ORCHARD_YIELD = {"winter": 0.00, "spring": 0.20, "summer": 1.10, "autumn": 2.30}

# --- labour and money -------------------------------------------------------
WAGE = 2.5                  # coins per employed worker per day
# Note: every base price in goods.py was set against this number. Move it and
# you move the margin on every trade in the game at once.
WORKING_FRACTION = 0.55     # share of population available for jobs
# Tax is deliberately thin. A population is labour, not a revenue farm: it
# costs more to feed than it ever pays in coin, and the profit has to come off
# the back of a cart. Fatten these and the game turns into a tax-slider idler.
TAX_LEVELS = {              # coins per head per day, and the mood it costs
    -2: (-0.80, +6.0),      # largesse: you pay them
    -1: (-0.35, +3.0),
    0: (0.00, +0.5),
    1: (0.45, -1.0),
    2: (0.85, -3.5),
    3: (1.35, -7.0),
    4: (2.10, -13.0),
}
TAX_LABELS = {-2: "largesse", -1: "gifts", 0: "none", 1: "light",
              2: "normal", 3: "heavy", 4: "cruel"}

# --- population -------------------------------------------------------------
RATION_LEVELS = {           # food units per head per day, and the mood it buys
    0: (0.00, -18.0),       # none
    1: (0.10, -6.0),        # half
    2: (0.20, +0.0),        # normal
    3: (0.28, +6.0),        # generous
    4: (0.36, +10.0),       # double
}
RATION_LABELS = {0: "none", 1: "half", 2: "normal", 3: "generous", 4: "double"}
FOOD_VARIETY_BONUS = 3.0    # mood per distinct ration good eaten beyond the first
COMFORT_RATE = 0.020        # comfort goods per head per day when available
COMFORT_BONUS = 4.0         # mood per comfort good supplied in full
LUXURY_RATE = 0.004         # luxuries per head per day
LUXURY_BONUS = 5.0
CROWDING_PENALTY = 25.0     # mood lost when housing is exactly at capacity+
UNPAID_WAGE_PENALTY = 20.0  # mood lost on a day wages could not be met

POPULARITY_START = 55.0
POPULARITY_INERTIA = 0.25   # how fast mood tracks conditions (per day)
MIGRATION_RATE = 0.010      # share of headroom that moves per day at full swing
UNREST_THRESHOLD = 18.0     # below this, work all but stops
UNREST_PRODUCTIVITY = 0.15  # a riot is not quite a vacuum -- recovery stays possible
BASE_HOUSING = 25.0         # the old village core, roof included

# Productivity as a function of popularity: 0.60 at 0, 1.00 at 50, 1.40 at 100.
PRODUCTIVITY_FLOOR = 0.60
PRODUCTIVITY_SLOPE = 0.008

# --- markets ----------------------------------------------------------------
PRICE_ADJUST = 0.20         # posted price convergence toward fundamentals per day
PRICE_FLOOR_MULT = 0.25     # price cannot fall below this multiple of base
PRICE_CEIL_MULT = 6.00
SPREAD = 0.10               # round-trip cost of dealing, halved on each side
MARKET_LOT = 3.0            # trades walk the curve in lots this size
STOCK_REVERSION = 0.06      # foreign stock drifts back toward target per day
BASE_STORAGE = 600.0        # units a settlement can hold before spillage
SPILL_RATE = 0.10           # share of the overflow lost each day

# --- trade ------------------------------------------------------------------
CARAVAN_BASE_CAPACITY = 150.0   # cart units
CARAVAN_BASE_SPEED = 32.0       # leagues per day
CARAVAN_COST = 300.0            # coins to outfit
CARAVAN_UPKEEP = 4.0            # coins per day, whether it moves or not
GUARD_COST = 3.0                # coins per guard per day
GUARD_PROTECTION = 0.22         # share of banditry removed per guard
SHIP_COST = 900.0               # coins to build and rig a cog
SHIP_CAPACITY = 420.0           # a hull holds what four carts hold
SHIP_SPEED = 60.0               # sea leagues per day
SHIP_UPKEEP = 11.0              # coins per day, crew and caulking
SEA_DIRECTNESS = 0.80           # sea miles against land miles between two ports
STORM_RISK = 0.018              # per sailing day in fair season
STORM_WINTER = 3.0              # and how much worse the winter sea is
BASE_TARIFF = 0.06              # foreign toll on both sides of a deal
TRADING_POST_TARIFF_RELIEF = 0.45

# --- military ---------------------------------------------------------------
LETHALITY = 1.15                # how bloody one round of a battle is
SIEGE_ATTRITION = 0.16          # share of a round's fire that lands during a siege
SIEGE_HUNGER = 0.55             # what a besieged town still manages to produce
RAID_BASE_CHANCE = 0.004        # per settlement per day, scaled by year
RAID_LOOT_FRACTION = 0.18
HOSTILITY_DRIFT = 0.30          # per day, per town; scales with how rich you look
HOSTILITY_WAR = 100.0           # at this, a lord marches
AMBITION_DRIFT = 0.30           # per day, per town, toward its neighbours
REVOLT_CHANCE = 0.006           # per day, for a vassal you cannot overawe
GIFT_PER_COIN = 0.012           # hostility a coin of tribute buys off
TRUCE_RATE = 9.0                # coins per day of bought peace, per muster
TRIBUTE_BASE = 22.0             # coins per day from a town that has bent the knee
TRIBUTE_PER_WEALTH = 14.0

# --- victory ----------------------------------------------------------------
GOAL_NET_WORTH = 120000.0
GOAL_POPULATION = 450
GOAL_DAYS = 3 * DAYS_PER_YEAR
GOAL_TOWNS = 3              # towns sworn to you for a dominion victory
BANKRUPTCY_FLOOR = -3000.0
