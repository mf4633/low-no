"""Rivers: what the water does to the road, and what a bridge is worth.

The map had roads and it had a sea. Between two inland towns it had nothing
at all -- a cart went the straight-line distance at the straight-line speed,
in March exactly as in August. That is the one piece of medieval geography a
trading game cannot afford to leave out, because for most of the year the
question "can I get there" was really the question "is the water down".

So: a handful of real rivers, drawn as lines on the same map the towns stand
on. A road from A to B crosses a river when the segment between them crosses
it -- no lookup table, no per-pair data, just the geometry, which means a
scenario that places its own towns gets its own crossings for nothing.

## How high the water is

Not rolled. Rivers are the one thing on this map with a memory: it rains
today and the ford is out on Thursday, and it is still out on Friday when
the sky is clear. So the stage is a *hydrograph* -- today's height is the
last fortnight of weather, each day's rain weighted by how long ago it fell,
decaying as a catchment drains:

    stage = base(season) + CATCHMENT * sum( rain(day-i) * exp(-i/RECESSION) )

That is a unit hydrograph with an exponential recession limb, which is
overkill for a game and cost nothing, because `military.sky_on` is already
a pure function of the day. Nothing is stored, nothing is rolled, and two
people asking about Thursday's ford get the same answer -- the panel that
warns you before you commit a cart and the cart itself, which is the same
reason the weather is drawn the way it is.

The seasonal base is the part players plan around. Spring is highest (the
melt), summer lowest, and a hard frost in low water is not an obstacle at
all: a frozen river is a road, and winter is when campaigns crossed.

## What it costs

A ford in low water costs nothing. A ford in high water costs time and
risks the load. A ford under a flood is simply not there, and the honest
answer is the medieval one -- you ride upstream until you find a bridge,
which is days.

## Bridges

Which is what makes a bridge worth its price. A bridge is a point on a
river, and a road uses it if it meets the water near it, so *where* you
build is the decision: a bridge on the reach your own carts cross is worth
several on a reach nobody uses. It makes the crossing free at any stage,
for ever, for everyone -- and everyone who is not you pays a toll for it.

A toll on a bridge nobody else crosses is nothing, so the toll is scaled by
the trade of the country either side of it. That is not a fudge: the world
already models a foreign town's business with everybody-who-is-not-you as
a pull toward equilibrium, and a bridge between two busy markets sits on
exactly that traffic. It is the whole economy of the Rhine gorge.

And a bridge can be thrown down. That is the war half, and it is a real
decision rather than a free one, because the crossing you deny the host
marching on you is the crossing your own carts were using.
"""

from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config as C
from .military import sky_on, FAIR, RAIN, MUD, FROST, HEAT

# --------------------------------------------------------------- the stage
#
# How much water each kind of day puts into the catchment. Mud is not rain,
# it is the day after rain, so it still counts -- the ground is already
# full and what falls runs straight off. Frost holds it as snow (and the
# melt is in the spring base, below) and heat takes it away.
RAINFALL = {RAIN: 1.00, MUD: 0.50, FAIR: 0.0, FROST: -0.30, HEAT: -0.28}

MEMORY = 14          # days of weather a river still remembers
RECESSION = 4.5      # days for a flood peak to fall by 1/e
CATCHMENT = 0.34     # how hard this country answers its rain

#: Where the water sits with no weather at all. Spring is the melt; the
#: summer figure is why every campaign in the game wants to be a summer one.
BASE = {"spring": 0.95, "summer": 0.30, "autumn": 0.62, "winter": 0.58}

#: Below this, with a hard frost on, the river is ice and carries carts.
FREEZES_AT = 0.80

LOW, FORD, HIGH, SHUT, ICE, BRIDGED = "low", "ford", "high", "shut", "ice", "bridged"

#: How far over its ford a river runs before it stops being crossable at all.
#: Measured rather than chosen: the stage distribution this weather produces
#: is narrow, and at the 0.55 this started as the big river flooded on two
#: days of the spring in a hundred -- a state the player would never see.
#: At 0.30 it is shut on a fifth of spring days and a sixteenth of the year,
#: which is a river you plan around.
IN_SPATE = 0.30

#: Days a crossing costs, by what the water is doing.
DELAY = {LOW: 0.0, FORD: 0.4, HIGH: 1.5, SHUT: 3.2, ICE: 0.0, BRIDGED: 0.0}

#: Chance per crossing of losing part of a load in the water. Only the two
#: states where a sensible drover would have turned back and did not.
SPILL = {HIGH: 0.10, SHUT: 0.22}

WORDS = {
    LOW: "low water",
    FORD: "fordable",
    HIGH: "running high",
    SHUT: "in flood",
    ICE: "frozen hard",
    BRIDGED: "bridged",
}


@dataclass(frozen=True)
class River:
    """A line on the map, and the height at which its ford goes under.

    `ford_limit` is the whole of a river's character. A beck with a gravel
    bottom is crossable in nearly anything; the big one in the middle of the
    map is out for most of the spring, and that is the one worth a bridge.
    """
    key: str
    name: str
    x1: float
    y1: float
    x2: float
    y2: float
    ford_limit: float

    @property
    def size(self) -> str:
        if self.ford_limit <= 1.65:
            return "a real river"
        if self.ford_limit <= 2.05:
            return "a wide stream"
        return "a beck"

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "River":
        return cls(**{k: d[k] for k in
                      ("key", "name", "x1", "y1", "x2", "y2", "ford_limit")})


@dataclass
class Bridge:
    """Stone over water, at a point, owned by somebody."""
    uid: int
    river: str
    x: float
    y: float
    owner: str = "player"
    name: str = ""
    built_day: int = 0
    #: Days of work left before it carries anything. A bridge is not a
    #: purchase, it is a season's masonry, and the season is the cost that
    #: makes breaking one hurt.
    days_left: int = 0
    broken: bool = False

    @property
    def standing(self) -> bool:
        return not self.broken and self.days_left <= 0

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Bridge":
        return cls(**d)


#: How far from a crossing a bridge still serves it, in leagues. A day's
#: ride up the bank and back: far enough that one bridge covers a reach,
#: near enough that where you put it is a decision.
REACH = 20.0

#: What a bridge costs to build, and how long the masons take.
BRIDGE_COST = 1400.0
BRIDGE_DAYS = 45
#: What it costs to put a broken one back up. Cheaper than new -- the piers
#: survive; it is the deck that goes -- which is also why breaking one is a
#: delay to an enemy rather than a permanent denial.
REBUILD_SHARE = 0.45
REBUILD_DAYS = 22

#: Water worth 1400c of masonry. A beck that is out for five days of the
#: spring is a beck you walk your oxen through.
WORTH_BRIDGING = 1.70

#: Coin a day a standing bridge takes off other people's traffic, per unit
#: of the trade either side of it. See the module note: this is the world's
#: own business with everybody-who-is-not-you, walking over your deck.
#:
#: Set by measurement rather than by taste. Across the sites reachable from
#: a starting seat the traffic figure runs about 1.2 to 2.8, so this rate
#: puts a good crossing near 7c a day and a poor one near 3 -- a bridge that
#: pays for itself in seven months where the roads actually are and in
#: sixteen where they are not. That gap is the decision; the saved days on
#: your own carts are on top of it, and they are the real reason.
TOLL_RATE = 0.050
TOLL_CAP = 26.0


# --------------------------------------------------------------- hydrology
def stage(day: int, seed: int = 0, start_month: int = C.START_MONTH) -> float:
    """How high the water is today, over the whole country.

    One number for the map. A catchment this size would have a dozen, but
    the player has one sky to look at and the honest simplification is to
    give him one river-stage to go with it; the rivers differ in what
    height puts their ford out, not in what the rain did.
    """
    total = 0.0
    for back in range(MEMORY):
        d = day - back
        if d < 0:
            break
        sky = sky_on(_season_on(d, start_month), d, seed)
        total += RAINFALL.get(sky, 0.0) * math.exp(-back / RECESSION)
    return max(0.0, BASE[_season_on(day, start_month)] + CATCHMENT * total)


def _season_on(day: int, start_month: int = C.START_MONTH) -> str:
    cal = day + (start_month - 1) * C.DAYS_PER_MONTH
    month = (cal % C.DAYS_PER_YEAR) // C.DAYS_PER_MONTH + 1
    return C.SEASON_OF_MONTH[month]


def state_of(river: River, level: float, sky: str = FAIR,
             bridged: bool = False) -> str:
    """What this river is doing to travellers, in one word."""
    if bridged:
        return BRIDGED
    if sky == FROST and level <= FREEZES_AT:
        return ICE
    limit = river.ford_limit
    if level <= limit - 0.35:
        return LOW
    if level <= limit:
        return FORD
    if level <= limit + IN_SPATE:
        return HIGH
    return SHUT


def forecast(season: str) -> str:
    """What this season does to the water, for a player deciding to wait."""
    base = BASE.get(season, 1.0)
    if base >= 1.0:
        return "the melt is on -- every ford in the march is doubtful"
    if base >= 0.75:
        return "the rivers are up more often than not"
    if base >= 0.6:
        return "the fords hold except after rain"
    return "low water; the fords are a formality"


# ---------------------------------------------------------------- geometry
def _hits(ax: float, ay: float, bx: float, by: float,
          r: River) -> Optional[Tuple[float, float]]:
    """Where the road A-B meets this river, if it does.

    Plain segment intersection. Roads in this game are straight lines
    because distances are, and a river that a road pretended to miss would
    be a river the player could not reason about.
    """
    rx, ry = r.x2 - r.x1, r.y2 - r.y1
    sx, sy = bx - ax, by - ay
    denom = rx * sy - ry * sx
    if abs(denom) < 1e-9:
        return None                      # parallel: the road runs the valley
    t = ((ax - r.x1) * sy - (ay - r.y1) * sx) / denom
    u = ((ax - r.x1) * ry - (ay - r.y1) * rx) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (r.x1 + t * rx, r.y1 + t * ry)
    return None


def crossings(rivers: List[River], ax: float, ay: float,
              bx: float, by: float) -> List[Tuple[River, float, float]]:
    """Every river the road from A to B has to get over, and where."""
    out = []
    for r in rivers:
        hit = _hits(ax, ay, bx, by, r)
        if hit is not None:
            out.append((r, hit[0], hit[1]))
    return out


def served_by(bridges: List[Bridge], river_key: str,
              x: float, y: float) -> Optional[Bridge]:
    """The nearest standing bridge that covers this crossing, if any."""
    best, best_d = None, REACH
    for b in bridges:
        if b.river != river_key or not b.standing:
            continue
        d = math.hypot(b.x - x, b.y - y)
        if d <= best_d:
            best, best_d = b, d
    return best


# ------------------------------------------------------------------- names
_HEADS = ("Dun", "Aln", "Wharf", "Tarn", "Lugg", "Corve", "Onny", "Teme",
          "Clun", "Rea", "Perry", "Bourne", "Hafren", "Wye", "Eden", "Dever")
#: A river's name says how big it is, because in England it always did.
#: Nothing called a brook is a real river, and "the Edenbrook is in flood
#: and your host is going round" is a sentence that fights itself.
_TAILS = {
    "a real river": ("", "", "", "water"),
    "a wide stream": ("", "water", "brook"),
    "a beck": ("brook", "beck", "burn", "lake"),
}


def _river_name(rng: random.Random, taken: set, size: str) -> str:
    tails = _TAILS.get(size, ("",))
    for _ in range(40):
        name = rng.choice(_HEADS) + rng.choice(tails)
        if name not in taken:
            taken.add(name)
            return name
    return f"the {len(taken) + 1}th water"


def draw(coords: Dict[str, Tuple[float, float]], seed: int = 0) -> List[River]:
    """Put rivers on a map that already has its towns.

    Drawn from the towns rather than under them, which is backwards from how
    a country grows and right for how this one is built: the scenarios place
    their towns first and hand-built ones place them by name. What matters
    is that the same map always gets the same rivers -- so this is seeded off
    the node keys, not off anybody's RNG stream. Drawing even one number out
    of the world's would move every seeded outcome behind it, which is a bug
    this codebase has now paid for four times.
    """
    if len(coords) < 3:
        return []
    xs = [p[0] for p in coords.values()]
    ys = [p[1] for p in coords.values()]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0

    stamp = "|".join(sorted(coords)) + f"|{seed}"
    rng = random.Random(zlib.crc32(stamp.encode()))

    # One that matters and two that are mostly a nuisance: a map where every
    # river is a real river is a map where the bridge decision has no shape.
    limits = [1.50, 1.90, 2.25]
    taken: set = set()
    out: List[River] = []
    # Spread the three across the compass rather than drawing each freely.
    # Three free angles put two of them down the same valley often enough to
    # notice, and two rivers a road crosses within ten leagues of each other
    # are one river charged for twice.
    first = rng.uniform(0, math.pi)
    for i, limit in enumerate(limits):
        ang = (first + i * math.pi / 3.0 + rng.uniform(-0.28, 0.28)) % math.pi
        # Offset perpendicular to the river's own run, so the three of them
        # do not all pile through the middle of the map.
        off = rng.uniform(-0.30, 0.30) * span
        px, py = -math.sin(ang), math.cos(ang)
        half = rng.uniform(0.55, 0.80) * span
        mx, my = cx + px * off, cy + py * off
        dx, dy = math.cos(ang) * half, math.sin(ang) * half
        name = _river_name(rng, taken, River("", "", 0, 0, 0, 0, limit).size)
        out.append(River(key=f"r{i}", name=name,
                         x1=mx - dx, y1=my - dy, x2=mx + dx, y2=my + dy,
                         ford_limit=limit))
    return out
