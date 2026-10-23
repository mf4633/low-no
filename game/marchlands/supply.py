"""What a host eats, and what happens on the day it does not.

Until this, an army in the field was a payroll line and nothing else. It
cost coin every morning and it never once ate, which meant a host could sit
in front of a wall for a year at no cost but wages, and marching to the far
end of the map was exactly as cheap as standing in your own gate. That is
the wrong shape for a game about a march: for most of the period the thing
that ended a campaign was not a battle and not money, it was October.

Three numbers, and the interesting one is the third.

**What it eats.** A soldier eats more than a townsman and is counted in the
same rations, so the bread chain that feeds your people is the one that
feeds your army.

**What it carries.** A fortnight, near enough, and no more -- a host that
could carry a season's food would make the rest of this pointless.

**What it can take where it stands.** This is the mechanic. Foraging pays
off the country: fertile ground feeds a host, a fen does not, and the same
field in October yields what it will not in March. And it is *exhaustible*.
A host sitting still eats out the country round it a little more each day.
That is what makes a siege a race rather than a wait: a besieger far from
his own granaries is running down a clock of his own while he runs down
yours, which is the reason real sieges were lifted far more often than they
were stormed. Near home he is not, and that is the difference between being
besieged by your neighbour and by somebody who had to cross a kingdom.

The grazing is kept on the world rather than on the army, because a country
is eaten out by whoever has been in it. Two hosts in one place are
competing for the same fields, and a lord who has just marched through is
somewhere you should not follow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

#: Rations a soldier eats a day. The commons eat 0.20 at a normal ration --
#: see config.RATION_LEVELS -- and a man who marches twenty miles in armour
#: eats more than a man who does not.
MARCH_RATION = 0.30

#: Days of its own food a host carries. Enough to cross the map and open a
#: siege; not enough to sit through one.
CARRY_DAYS = 14.0

#: Rations a slot of fertile ground yields in a day, before the season and
#: before anyone has been at it.
FORAGE_PER_SLOT = 2.6

#: What the country round a place will give, by season. Autumn is the
#: harvest and it is why campaigns were fought in it; winter is the answer
#: to "why did everybody go home".
SEASON_YIELD = {"spring": 0.70, "summer": 1.10, "autumn": 1.40, "winter": 0.30}

#: How fast a host eats a country out, as a share of the country's own daily
#: yield taken permanently per day of foraging, and how fast it comes back.
#: A month in one place takes a place most of the way down; a season away
#: brings it most of the way back.
GRAZE_RATE = 0.055
GRAZE_HEAL = 0.014

#: However long a host sits there, the country is never picked to nothing --
#: there is always a little put by, a late field, a pig nobody declared.
#: Without this the grazing reaches a cliff and stays on it, and a siege
#: stops being a race and becomes a countdown with a fixed answer.
GRAZE_FLOOR = 0.16

#: Of the men a starving host loses in a day, at the worst. They are not
#: killed -- they go home, which is what actually happened and is also the
#: reason a starved host can be beaten without a battle.
DESERT_RATE = 0.085


#: How far a friendly granary can keep a host fed, in leagues, and how
#: sharply it falls off. This is the supply line, and it is the reason a
#: siege in the next valley is a different proposition from a siege at the
#: far end of the map -- which is the shape the real thing had. Towns sit
#: 70 to 180 leagues apart on a drawn map, so a host in your own country is
#: largely fed and a host across it is largely not.
CONVOY_REACH = 120.0

#: And how much further it reaches once a host has stopped moving. A siege
#: is not a march that has paused -- it is a camp, with a road behind it that
#: somebody is running carts down, which is most of what sitting down in
#: front of a wall consists of.
#:
#: Without this, supply quietly disarmed every siege in the game that was
#: not next door. A lord's second host would arrive at your gate with its
#: baggage eaten on the road and come apart in a week, so a player was safe
#: from anyone more than a few days' march away -- which is not a harder
#: game, it is a smaller one.
SETTLED_REACH = 2.6


def convoy_share(distance: float, settled: bool = False) -> float:
    """What share of a host's need can be carted out to it from home.

    `settled` is a host that has stopped -- besieging, or holding a place.
    A host on the march is the one that lives out of its own baggage,
    because the carts cannot catch a moving army.
    """
    reach = CONVOY_REACH * (SETTLED_REACH if settled else 1.0)
    if distance <= 0.0:
        return 1.0
    if distance >= reach:
        return 0.0
    return max(0.0, 1.0 - (distance / reach) ** 1.5)


@dataclass
class Ration:
    """One host's day of eating, as something that can be reported."""
    need: float = 0.0
    foraged: float = 0.0
    carted: float = 0.0
    from_stores: float = 0.0
    short: float = 0.0
    deserted: float = 0.0

    @property
    def fed(self) -> bool:
        return self.short <= 1e-9

    def words(self) -> str:
        if self.fed:
            if self.foraged >= self.need - 1e-9:
                return "living off the country"
            if self.foraged <= 1e-9:
                return "eating what it carries"
            return "foraging, and eating the rest"
        if self.deserted >= 1:
            return f"short of food -- {self.deserted:.0f} away in the night"
        return "short of food"


def fields_of(ground: Dict[str, int]) -> float:
    """How much of a place is worth foraging.

    Fertile ground first, and a little off the woods and the coast, because
    a host in a forest is not eating bark -- it is eating pannage, game, and
    whatever the villages under the trees had put by.
    """
    return (ground.get("fertile", 0)
            + 0.35 * ground.get("forest", 0)
            + 0.30 * ground.get("coast", 0))


def yield_at(ground: Dict[str, int], season: str, grazed: float = 0.0) -> float:
    """Rations a day the country round a place will give up today."""
    base = fields_of(ground) * FORAGE_PER_SLOT
    base *= SEASON_YIELD.get(season, 1.0)
    left = 1.0 - min(1.0, max(0.0, grazed))
    return max(0.0, base * (GRAZE_FLOOR + (1.0 - GRAZE_FLOOR) * left))


def eat(men: float, stores: float, *, ground: Dict[str, int], season: str,
        grazed: float = 0.0, forage: bool = True,
        carts: float = 0.0) -> Tuple[Ration, float, float]:
    """One host's day. Returns (what happened, stores left, grazing left).

    Forage first, then what came up the road, then the packs, which is the
    order an army actually does it in: what you carry is what gets you
    through the country that has nothing, so you do not spend it in the
    country that has something.

    `carts` is rations delivered from a friendly granary -- the caller works
    out how much got through and takes it out of the town's own stores,
    because this module does not know where anybody's towns are.
    """
    r = Ration(need=men * MARCH_RATION)
    if r.need <= 0:
        return r, stores, grazed
    give = yield_at(ground, season, grazed) if forage else 0.0
    r.foraged = min(r.need, give)
    if give > 0 and r.foraged > 0:
        # Eaten out in proportion to how hard it was worked, so a small host
        # in a rich country can sit a long time and a big one cannot.
        whole = max(give, 1e-9)
        grazed = min(1.0, grazed + GRAZE_RATE * (r.foraged / whole))
    want = r.need - r.foraged
    r.carted = min(want, max(0.0, carts))
    want -= r.carted
    r.from_stores = min(stores, want)
    stores -= r.from_stores
    r.short = max(0.0, want - r.from_stores)
    if r.short > 0:
        # Proportional to how hungry, so one thin day is not a rout and a
        # week of nothing is.
        bite = min(1.0, r.short / r.need)
        r.deserted = men * DESERT_RATE * bite
    return r, stores, grazed


def recover(grazed: float) -> float:
    """A day of nobody eating it."""
    return max(0.0, grazed - GRAZE_HEAL)


def capacity(men: float) -> float:
    """The most a host of this size can carry, in rations."""
    return men * MARCH_RATION * CARRY_DAYS


def days_left(men: float, stores: float) -> float:
    if men <= 0:
        return 0.0
    return stores / (men * MARCH_RATION)


def note(men: float, stores: float, ground: Dict[str, int], season: str,
         grazed: float = 0.0) -> dict:
    """What the panel says before you march, rather than after you starve."""
    give = yield_at(ground, season, grazed)
    need = men * MARCH_RATION
    return {
        "days": round(days_left(men, stores), 1),
        "carry": round(capacity(men), 1),
        "stores": round(stores, 1),
        "need": round(need, 2),
        "forage": round(give, 2),
        "feeds": int(give / MARCH_RATION) if MARCH_RATION else 0,
        "grazed": round(min(1.0, grazed), 3),
        "enough": give >= need,
    }
