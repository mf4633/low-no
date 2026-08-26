"""low-no: station + market registry and THE GATE (constitution values).

The gate parameters are law. They were set on a calm day (Aug 6, 2026)
from a backtest of 130 settled city-days. Changing them mid-session,
after a loss, or to 'catch' a marginal ticket defeats the system.
"""

GATE = {
    "max_price": 0.98,        # never lift above this; rest bids below
    "min_g_deg": 4.0,         # guidance_high - bottom_ceiling must be >= this
    "max_pop_pct": 20,        # forecast precip prob during heating window
    "entry_local": (10, 30),  # earliest local entry (h, m) - post-slope-confirmation
    "entry_close": (13, 30),  # after this, scavenge-only (dead rungs)
    "min_net_cents": 1.5,     # skip if fee leaves less than this per contract
    # Hard ceiling on any single position, independent of Kelly. Half-Kelly at a
    # 97c near-certainty prescribes 40%+ of bankroll -- correct arithmetic on an
    # UNPROVEN p. No band's Wilson LCB clears its fee breakeven yet, so the cap
    # binds on every flag by design. Raise it only when a band is PROVEN.
    "max_position_frac": 0.05,
}

# Kalshi series tickers verified against live markets Aug 2026.
CITIES = {
    "AUS": dict(name="Austin",        station="KAUS", tz="America/Chicago",    series="KXHIGHAUS", lat=30.1945, lon=-97.6699),
    "CHI": dict(name="Chicago",       station="KMDW", tz="America/Chicago",    series="KXHIGHCHI", lat=41.786, lon=-87.7524),
    "DEN": dict(name="Denver",        station="KDEN", tz="America/Denver",     series="KXHIGHDEN", lat=39.8617, lon=-104.6731),
    "LAX": dict(name="Los Angeles",   station="KLAX", tz="America/Los_Angeles",series="KXHIGHLAX", lat=33.9425, lon=-118.4081),
    "MIA": dict(name="Miami",         station="KMIA", tz="America/New_York",   series="KXHIGHMIA", lat=25.7959, lon=-80.287),
    "NYC": dict(name="New York",      station="KNYC", tz="America/New_York",   series="KXHIGHNY", lat=40.7789, lon=-73.9692),
    "PHL": dict(name="Philadelphia",  station="KPHL", tz="America/New_York",   series="KXHIGHPHIL", lat=39.8729, lon=-75.2437),
    "PHX": dict(name="Phoenix",       station="KPHX", tz="America/Phoenix",    series="KXHIGHTPHX", lat=33.4342, lon=-112.0116),
    "SEA": dict(name="Seattle",       station="KSEA", tz="America/Los_Angeles",series="KXHIGHTSEA", lat=47.4502, lon=-122.3088),
    "SFO": dict(name="San Francisco", station="KSFO", tz="America/Los_Angeles",series="KXHIGHTSFO", lat=37.6213, lon=-122.379),
    # --- added 2026-08-22: station expansion -------------------------------
    # Flag supply was the binding constraint: 6 flags in 15 days across 10
    # stations, and 3 of those came from SFO (which produced BOTH losses).
    # Every series below was verified live on Kalshi AND confirmed to have NWS
    # CLI products, so settlement can actually resolve. A station without CLI
    # accumulates PENDING flags forever -- see the MTR/BOU/OKX failure.
    "ATL": dict(name="Atlanta",       station="KATL", tz="America/New_York",    series="KXHIGHTATL",  lat=33.6301, lon=-84.4418),
    "BOS": dict(name="Boston",        station="KBOS", tz="America/New_York",    series="KXHIGHTBOS",  lat=42.3606, lon=-71.0097),
    "DAL": dict(name="Dallas",        station="KDFW", tz="America/Chicago",     series="KXHIGHTDAL",  lat=32.8975, lon=-97.0381),
    "DC":  dict(name="Washington DC", station="KDCA", tz="America/New_York",    series="KXHIGHTDC",   lat=38.8483, lon=-77.0342),
    # HOU settles on HOBBY, not Intercontinental: Kalshi rules_primary names
    # CLIHOU, the NWS climate product for KHOU (verified via API 2026-08-26).
    # This dict previously held DUPLICATE keys -- an earlier KIAH entry was
    # silently overridden by a later KHOU line, which happened to be correct.
    # Deduplicated 2026-08-26; do not "restore" KIAH.
    "HOU": dict(name="Houston Hobby", station="KHOU", tz="America/Chicago",     series="KXHIGHTHOU",  lat=29.6372, lon=-95.2820),
    "LAS": dict(name="Las Vegas",     station="KLAS", tz="America/Los_Angeles", series="KXHIGHTLV",   lat=36.0719, lon=-115.1634),
    "MSP": dict(name="Minneapolis",   station="KMSP", tz="America/Chicago",     series="KXHIGHTMIN",  lat=44.8831, lon=-93.2289),
    "MSY": dict(name="New Orleans",   station="KMSY", tz="America/Chicago",     series="KXHIGHTNOLA", lat=29.9934, lon=-90.2581),
    "OKC": dict(name="Oklahoma City", station="KOKC", tz="America/Chicago",     series="KXHIGHTOKC",  lat=35.3889, lon=-97.6008),
    # SAN is marine-influenced (coastal stratus). Added to prob.MARINE so the
    # edge board refuses to size it -- SFO's bimodal burn-off has produced every
    # loss in this ledger and San Diego shares the mechanism.
    "SAN": dict(name="San Diego",     station="KSAN", tz="America/Los_Angeles", series="KXHIGHTSAN",  lat=32.7336, lon=-117.1831),
    "SAT": dict(name="San Antonio",   station="KSAT", tz="America/Chicago",     series="KXHIGHTSATX", lat=29.5337, lon=-98.4698),
    # --- added 2026-08-26: full-coverage audit against Kalshi's series list --
    # Both were live with daily markets and unmonitored. Verified: markets open
    # today AND NWS CLI settles them (EWR 81 / TTN 77 on 8/25).
    "EWR": dict(name="Newark",        station="KEWR", tz="America/New_York",    series="KXHIGHTEWR",  lat=40.6925, lon=-74.1687),
    "TTN": dict(name="Trenton",       station="KTTN", tz="America/New_York",    series="KXHIGHTTTN",  lat=40.2767, lon=-74.8135),
}

# International daily-high series (ICAO-coded tickers), enumerated from
# Kalshi's Climate and Weather category 2026-08-26. ALL dormant at audit time
# -- London traded through 26AUG19 then stopped -- so there is nothing to
# grade yet. The scanner probes each for open markets and logs full ladders
# from the day any of them returns (first-day books are ephemeral). Obs and
# settlement plumbing (non-NWS: international METAR / The Weather Company per
# Kalshi's stated settlement source) gets built when a market is actually
# live. There is also a full KXLOWT* daily-LOW product line, US and world,
# deliberately not tracked yet.
WORLD = {
    "LON": dict(name="London",      icao="EGLL", tz="Europe/London",       series="KXHIGHTEGLL"),
    "PAR": dict(name="Paris",       icao="LFPG", tz="Europe/Paris",        series="KXHIGHTLFPG"),
    "BER": dict(name="Berlin",      icao="EDDB", tz="Europe/Berlin",       series="KXHIGHTEDDB"),
    "FRA": dict(name="Frankfurt",   icao="EDDF", tz="Europe/Berlin",       series="KXHIGHTEDDF"),
    "AMS": dict(name="Amsterdam",   icao="EHAM", tz="Europe/Amsterdam",    series="KXHIGHTEHAM"),
    "BRU": dict(name="Brussels",    icao="EBBR", tz="Europe/Brussels",     series="KXHIGHTEBBR"),
    "GVA": dict(name="Geneva",      icao="LSGG", tz="Europe/Zurich",       series="KXHIGHTLSGG"),
    "IST": dict(name="Istanbul",    icao="LTFM", tz="Europe/Istanbul",     series="KXHIGHTLTFM"),
    "TYO": dict(name="Tokyo",       icao="RJTT", tz="Asia/Tokyo",          series="KXHIGHTRJTT"),
    "SEL": dict(name="Seoul",       icao="RKSI", tz="Asia/Seoul",          series="KXHIGHTRKSI"),
    "PEK": dict(name="Beijing",     icao="ZBAA", tz="Asia/Shanghai",       series="KXHIGHTZBAA"),
    "SHA": dict(name="Shanghai",    icao="ZSPD", tz="Asia/Shanghai",       series="KXHIGHTZSPD"),
    "HKG": dict(name="Hong Kong",   icao="VHHH", tz="Asia/Hong_Kong",      series="KXHIGHTVHHH"),
    "SIN": dict(name="Singapore",   icao="WSSS", tz="Asia/Singapore",      series="KXHIGHTWSSS"),
    "BOM": dict(name="Mumbai",      icao="VABB", tz="Asia/Kolkata",        series="KXHIGHTVABB"),
    "DXB": dict(name="Dubai",       icao="OMDB", tz="Asia/Dubai",          series="KXHIGHTOMDB"),
    "SYD": dict(name="Sydney",      icao="YSSY", tz="Australia/Sydney",    series="KXHIGHTYSSY"),
    "YYZ": dict(name="Toronto",     icao="CYYZ", tz="America/Toronto",     series="KXHIGHTCYYZ"),
    "MEX": dict(name="Mexico City", icao="MMMX", tz="America/Mexico_City", series="KXHIGHTMMMX"),
    "GRU": dict(name="Sao Paulo",   icao="SBGR", tz="America/Sao_Paulo",   series="KXHIGHTSBGR"),
}

# Static regime classification, all 23 stations (2026-08-26). GEOGRAPHY, not
# calibration: these are verifiable facts (what water is nearby, how high, which
# mechanistic bust modes the geography permits) for attribution slicing and
# future variants. They are deliberately separate from QUIRKS below, which are
# EARNED from observed behavior -- do not promote a regime hypothesis into
# QUIRKS without data. Feeds nothing today; prob.MARINE is intentionally NOT
# expanded from this (changing it mid-measurement would redefine the
# exclude_marine variant population).
#   regime: primary label   water_km: nearest significant water (approx)
#   elev_ft: station elevation (approx)   bust_modes: mechanisms to watch
REGIME = {
    "AUS": dict(regime="continental",    water_km=250, elev_ft=540,  bust_modes=["frontal", "outflow"]),
    "CHI": dict(regime="lake_breeze",    water_km=15,  elev_ft=620,  bust_modes=["lake_breeze_cap"]),
    "DEN": dict(regime="high_plains",    water_km=999, elev_ft=5430, bust_modes=["outflow", "downslope_warm"]),
    "LAX": dict(regime="marine_stratus", water_km=5,   elev_ft=125,  bust_modes=["stratus", "sea_breeze_cap"]),
    "MIA": dict(regime="sea_breeze",     water_km=15,  elev_ft=10,   bust_modes=["sea_breeze_cap", "convective"]),
    "NYC": dict(regime="urban_park",     water_km=8,   elev_ft=130,  bust_modes=["sea_breeze_cap", "park_cool"]),
    "PHL": dict(regime="riverine",       water_km=80,  elev_ft=35,   bust_modes=["frontal"]),
    "PHX": dict(regime="desert",         water_km=999, elev_ft=1110, bust_modes=["monsoon", "outflow"]),
    "SEA": dict(regime="marine_mod",     water_km=3,   elev_ft=430,  bust_modes=["marine_push", "onshore_switch"]),
    "SFO": dict(regime="marine_stratus", water_km=1,   elev_ft=10,   bust_modes=["stratus", "gap_reversal"]),
    "ATL": dict(regime="continental",    water_km=350, elev_ft=1000, bust_modes=["convective", "frontal"]),
    "BOS": dict(regime="sea_breeze",     water_km=1,   elev_ft=20,   bust_modes=["sea_breeze_cap", "backdoor_front"]),
    "DAL": dict(regime="continental",    water_km=400, elev_ft=600,  bust_modes=["frontal", "outflow"]),
    "DC":  dict(regime="riverine",       water_km=50,  elev_ft=15,   bust_modes=["frontal", "convective"]),
    "HOU": dict(regime="gulf_breeze",    water_km=8,   elev_ft=45,   bust_modes=["sea_breeze_cap", "convective"]),
    "LAS": dict(regime="desert",         water_km=999, elev_ft=2180, bust_modes=["monsoon", "outflow"]),
    "MSP": dict(regime="continental",    water_km=999, elev_ft=840,  bust_modes=["frontal"]),
    "MSY": dict(regime="gulf_lake",      water_km=5,   elev_ft=5,    bust_modes=["lake_breeze_cap", "convective"]),
    "OKC": dict(regime="plains",         water_km=999, elev_ft=1290, bust_modes=["frontal", "outflow"]),
    "SAN": dict(regime="marine_stratus", water_km=2,   elev_ft=15,   bust_modes=["stratus", "sea_breeze_cap"]),
    "SAT": dict(regime="continental",    water_km=200, elev_ft=810,  bust_modes=["frontal", "convective"]),
    "EWR": dict(regime="harbor_urban",   water_km=3,   elev_ft=10,   bust_modes=["sea_breeze_cap", "frontal"]),
    "TTN": dict(regime="riverine",       water_km=80,  elev_ft=210,  bust_modes=["frontal"]),
}

# Station quirk library, calibrated Jul 29-Aug 4 2026. Used by the scorer's
# attribution step, and as entry cautions in scan output.
QUIRKS = {
    "KDEN": "max register premium +1/+2F over hourlies; min -1/-3. Outflow guillotines. KCFO twin-check -1.5F.",
    "KLAX": "sea-breeze pin; surge onset W>=12kt sustained. deg-C quantized feed. Offshore days rare (terrain).",
    "KNYC": "park bowl: Td throttle, -3.5F vs EWR clear days, -2 cloudy. EWR leads by 2-3h; LGA = marine sentinel.",
    "KSEA": "boundary-case city; ramp narratives run ~1 day ahead of airmass. Check dawn Td (>=58 = arrived).",
    "KPHX": "most inert station; monsoon debris only bust mode. Td 60s+ raises min floor.",
    "KMDW": "lake cap ONLY on E/NE flow days; W/SW = clean. Boundary maxes common -> tenths decode.",
    "KSFO": "gap station: flips offshore a day before LAX. Weak NE drainage collapses to W reversal - timing city.",
}
