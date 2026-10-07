"""A path through the game that is yours rather than the scenario's.

Every scenario states one shape of victory -- a net worth, a population, some
towns, inside a number of years -- and that is the whole of what the game has
ever asked of you. It is a good goal and it is the same goal for all five
houses, which means the Hansa and the Ironhand play the identical campaign
with different multipliers.

EU4's answer is a mission tree, and the part worth stealing is not the
branching diagram. It is that the missions are *written for who you are*: a
trading republic is asked to do trading-republic things and paid in
trading-republic coin, so the tree tells you what your nation is for at the
same time as it gives you something to do next.

So each house has a trunk it shares -- the things any lord of the march must
do -- and a branch only it can walk, with rewards only it would want.

Three rules.

**A mission is checked, not claimed.** The condition is read off the same
`Standing` the feats use, gathered once a day from figures the game already
keeps. There is no "claim reward" button to forget to press.

**A reward is a thing, not a number going up.** Coin, a claim on a
neighbour, an institution you did not have to research, a privilege granted
free. Something that changes what you can do next, since that is the only
reason to give somebody a reward in a strategy game.

**The tree admits what it costs.** A mission that asks you to hold five towns
is asking you to fight four wars, and says so. A tree that pretends its
demands are free is a checklist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .feats import Standing

#: What a reward can be. Kept as data rather than a lambda so a mission can
#: be read, printed and tested without running the game.
REWARDS = ("coin", "tech", "claim", "privilege", "prosperity", "opinion",
           "relic_hint", "units")


@dataclass(frozen=True)
class Mission:
    key: str
    house: str                  # "" for the shared trunk
    name: str
    asks: str                   # what to do, in words you could plan toward
    costs: str                  # and what it will cost you to do it
    test: Callable[[Standing], bool]
    gives: Tuple[str, object]   # (kind, value) -- see REWARDS
    after: Tuple[str, ...] = ()  # missions that must be done first

    def reward_words(self) -> str:
        kind, value = self.gives
        if kind == "coin":
            return f"{value:,.0f}c"
        if kind == "tech":
            from .tech import TECHS
            name = TECHS[value].name if value in TECHS else str(value)
            return f"{name}, learned outright"
        if kind == "claim":
            # Which town is nearest depends on the map the scenario drew, so
            # the promise is worded the way it is kept.
            return ("a claim on your nearest neighbour" if value == "nearest"
                    else f"a claim on {value}")
        if kind == "privilege":
            return f"{value} granted, and it costs you nothing"
        if kind == "prosperity":
            return f"your towns prosper (+{value})"
        if kind == "opinion":
            return f"every lord thinks better of you (+{value})"
        if kind == "units":
            from .military import UNITS, plural
            return ", ".join(
                f"{n} {plural(UNITS[k].name) if n != 1 else UNITS[k].name}"
                if k in UNITS else f"{n} {k}"
                for k, n in dict(value).items())
        return str(value)


def _m(key, house, name, asks, costs, test, gives, after=()) -> Mission:
    return Mission(key=key, house=house, name=name, asks=asks, costs=costs,
                   test=test, gives=gives, after=tuple(after))


#: The trunk: what any lord of the march has to do, whoever he is.
TRUNK: List[Mission] = [
    # Not "have a population and a mood", which is the state every game
    # opens in: that made the first mission a 1,200c handout on day one, and
    # the coin was enough to pull a deliberately bankrupt game back from the
    # floor. A mission has to ask for something you do not already have.
    _m("roof", "", "A Roof For Everyone",
       "grow to two hundred souls with the town still content",
       "roofs are cheap and the ground they stand on is not",
       lambda s: s.population >= 200 and s.mood >= 60.0,
       ("coin", 1200)),
    _m("wall", "", "Something To Stand Behind",
       "stand sixty yards of wall",
       "stone, and the hands that could have been in the fields",
       lambda s: s.wall_yards >= 60,
       ("coin", 1800), after=("roof",)),
    _m("letters", "", "A Man Who Can Write",
       "learn the chancery",
       "scholars are fed out of the same granary as everybody else",
       lambda s: s.techs >= 6,
       ("opinion", 8), after=("roof",)),
    _m("neighbour", "", "A Neighbour Sworn",
       "bring one foreign town under your hand",
       "a war, or a marriage and the patience for one",
       lambda s: s.towns >= 1,
       ("claim", "nearest"), after=("wall", "letters")),
    _m("march", "", "Master of the March",
       "hold four foreign towns at once",
       "three more wars than you have fought",
       lambda s: s.towns >= 4,
       ("prosperity", 0.25), after=("neighbour",)),
]

#: And the branch each house walks alone.
BRANCHES: Dict[str, List[Mission]] = {
    "plough": [
        _m("granary", "plough", "The Full Granary",
           "feed six hundred souls at once",
           "every acre under wheat is an acre not under wool",
           lambda s: s.population >= 600,
           ("tech", "three_field"), after=("roof",)),
        _m("bill", "plough", "Every Man A Billman",
           "raise four hundred soldiers off your own land",
           "four hundred pairs of hands out of the fields",
           lambda s: s.soldiers >= 400,
           ("units", {"billman": 40}), after=("granary",)),
    ],
    "hansa": [
        _m("counting", "hansa", "The Counting House",
           "clear thirty thousand in trade profit",
           "carts on roads you do not police",
           lambda s: s.trade_profit >= 30_000,
           ("tech", "coinage"), after=("roof",)),
        _m("staple", "hansa", "The Staple",
           "clear a hundred thousand, and hold two towns",
           "everything a long peace costs you with the knights",
           lambda s: s.trade_profit >= 100_000 and s.towns >= 2,
           ("privilege", "monopoly"), after=("counting",)),
    ],
    "ironhand": [
        _m("forge", "ironhand", "The Forge Never Cools",
           "learn eight institutions and stand a hundred yards of wall",
           "iron, charcoal and the people to work both",
           lambda s: s.techs >= 8 and s.wall_yards >= 100,
           ("tech", "plate_armour"), after=("roof",)),
        _m("hammer", "ironhand", "The Hammer",
           "take three towns by storm",
           "three sieges, and what a siege costs in men",
           lambda s: s.took_by_storm >= 3,
           ("units", {"ironhand_serjeant": 30}), after=("forge",)),
    ],
    "marcher": [
        _m("riders", "marcher", "The Riders",
           "win six battles",
           "horses die faster than the men on them",
           lambda s: s.battles_won >= 6,
           ("units", {"border_horse": 24}), after=("roof",)),
        _m("warden", "marcher", "Warden of the March",
           "hold six towns, and never lose one",
           "five wars, and the coalition all five will raise",
           lambda s: s.towns >= 6 and s.lost_towns == 0,
           ("prosperity", 0.4), after=("riders",)),
    ],
    "abbey": [
        _m("minster", "abbey", "The Minster",
           "keep a town at eighty popularity",
           "a chapter that will want its own court next",
           lambda s: s.mood >= 80.0,
           ("tech", "preaching"), after=("roof",)),
        _m("relics", "abbey", "The Reliquary",
           "gather two relics",
           "pilgrimages, and the lords who want the same bones",
           lambda s: s.relics >= 2,
           ("opinion", 14), after=("minster",)),
    ],
}


def tree(house: str) -> List[Mission]:
    """The trunk plus this house's branch, in the order they unlock."""
    return list(TRUNK) + list(BRANCHES.get(house, ()))


def by_key(house: str) -> Dict[str, Mission]:
    return {m.key: m for m in tree(house)}


class Roll:
    """Which missions are done, and which are open to be tried."""

    def __init__(self) -> None:
        self.done: Dict[str, int] = {}

    def open(self, house: str) -> List[Mission]:
        """Missions whose prerequisites are met and which are not yet done."""
        return [m for m in tree(house)
                if m.key not in self.done
                and all(a in self.done for a in m.after)]

    def check(self, house: str, standing: Standing) -> List[Tuple[Mission, str]]:
        """Any mission finished today, with the words for its reward.

        Only open missions are tested: a tree where the last mission can be
        completed before the first is a list, and the order is the only thing
        a tree adds.
        """
        out: List[Tuple[Mission, str]] = []
        for m in self.open(house):
            try:
                got = bool(m.test(standing))
            except Exception:       # a mission must never break a game day
                got = False
            if got:
                self.done[m.key] = standing.day
                out.append((m, m.reward_words()))
        return out

    def to_dict(self) -> dict:
        return dict(self.done)

    @classmethod
    def from_dict(cls, d: dict) -> "Roll":
        r = cls()
        r.done = {k: int(v) for k, v in (d or {}).items()}
        return r
