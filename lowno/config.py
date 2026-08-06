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
