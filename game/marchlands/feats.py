"""Things worth having done, which is not the same as things worth doing.

Every scenario in this game has one shape of victory: a net worth, a
population, some towns, some relics, inside a number of years. That is a
goal, and a goal tells you what the game is *for*. It does not tell you what
the game is *capable of*, and a player who has met it twice has no third
thing to aim at.

EU4's answer is achievements, and the good ones share a property worth
copying: they are not "play for a hundred hours", they are a *different way
to play* stated as a condition. "Take the whole march without ever raising a
host" is a strategy pitch disguised as a trophy.

So each of these is a sentence you could plan toward, and every one of them
is checked against figures the game was already keeping. Nothing here is
instrumented specially, which is the only reason the list can be this long
and still be trustworthy: if a feat could be earned by a bug, the bug is in
the thing it counts, not in the counting.

They are also honest about difficulty. `Impossible` in a hundred-year
scenario is not a challenge, it is a lie, so anything time-bound says the
years it needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

#: Keys of every figure a feat may read, so a feat cannot quietly start
#: depending on something that is not kept between saves.
@dataclass
class Standing:
    """Everything a feat is allowed to look at, gathered once a day."""
    day: int = 0
    year: float = 0.0
    net_worth: float = 0.0
    treasury: float = 0.0
    population: int = 0
    towns: int = 0                 # foreign towns sworn to you
    relics: int = 0
    age: int = 0
    techs: int = 0
    battles_won: int = 0
    hosts_raised: int = 0
    coin_minted: float = 0.0
    allies: int = 0
    coalition: int = 0
    marriages: int = 0
    wall_yards: int = 0
    enclosed: int = 0
    soldiers: int = 0
    trade_profit: float = 0.0
    idioms_seen: int = 0
    estates_loyal: int = 0         # how many of the three are above sixty
    privileges: int = 0
    worst_estate: float = 100.0
    mood: float = 0.0
    took_by_storm: int = 0
    lost_towns: int = 0


@dataclass(frozen=True)
class Feat:
    key: str
    name: str
    blurb: str                     # what to do, as a thing you could plan
    test: Callable[[Standing], bool]
    hard: int = 1                  # 1 plain, 2 stiff, 3 the long ones


FEATS: Dict[str, Feat] = {f.key: f for f in [
    # --- the trader's way ------------------------------------------------
    Feat("peaceable", "The Peaceable Kingdom",
         "reach 60,000 in net worth without ever raising a host",
         lambda s: s.net_worth >= 60_000 and s.hosts_raised == 0, hard=3),
    Feat("factor", "Factor of the March",
         "clear 40,000 coin in trade profit alone",
         lambda s: s.trade_profit >= 40_000, hard=2),
    Feat("sound_money", "Sound Money",
         "pass 80,000 in net worth having never struck a penny",
         lambda s: s.net_worth >= 80_000 and s.coin_minted <= 0, hard=2),

    # --- the builder's way -----------------------------------------------
    Feat("enceinte", "The Great Enceinte",
         "enclose 120 plots inside one wall",
         lambda s: s.enclosed >= 120, hard=2),
    Feat("longwall", "Two Hundred Yards",
         "stand 200 yards of wall at once",
         lambda s: s.wall_yards >= 200, hard=2),
    Feat("thousand", "A Thousand Souls",
         "keep a thousand people fed at once",
         lambda s: s.population >= 1000, hard=2),
    Feat("content", "Well Governed",
         "hold a town at 85 popularity",
         lambda s: s.mood >= 85.0),

    # --- the soldier's way -----------------------------------------------
    Feat("stormed", "By Storm",
         "take three towns by storm",
         lambda s: s.took_by_storm >= 3, hard=2),
    Feat("march_whole", "Lord of the Whole March",
         "hold every foreign town on the map",
         lambda s: s.towns >= 8, hard=3),
    Feat("unbeaten", "Not One Yard",
         "win twelve battles without losing a town",
         lambda s: s.battles_won >= 12 and s.lost_towns == 0, hard=3),

    # --- the politician's way --------------------------------------------
    Feat("coalition", "Everyone's Problem",
         "have five lords sign the letter against you at once",
         lambda s: s.coalition >= 5, hard=2),
    Feat("web", "The Web",
         "hold three alliances and three marriages at the same time",
         lambda s: s.allies >= 3 and s.marriages >= 3, hard=2),
    Feat("wellheld", "Three Estates Content",
         "keep all three estates above sixty at once",
         lambda s: s.estates_loyal >= 3, hard=2),
    Feat("unbought", "Nothing Given Away",
         "reach the Age of Faith having granted no privilege",
         lambda s: s.age >= 3 and s.privileges == 0, hard=2),

    # --- the scholar's way -----------------------------------------------
    Feat("learned", "The Whole Book",
         "learn twenty institutions",
         lambda s: s.techs >= 20, hard=3),
    Feat("imperial", "The Last Age",
         "reach the last age the tech tree has",
         lambda s: s.age >= 5, hard=3),
    Feat("cosmopolitan", "Five Idioms",
         "hold towns built in all five architectures",
         lambda s: s.idioms_seen >= 5, hard=3),
]}


class Book:
    """What has been done, and on which day it was done."""

    def __init__(self) -> None:
        self.done: Dict[str, int] = {}

    def check(self, standing: Standing) -> List[str]:
        """Any feat earned today, announced once and never again."""
        said: List[str] = []
        for key, feat in FEATS.items():
            if key in self.done:
                continue
            try:
                got = bool(feat.test(standing))
            except Exception:          # a feat must never break a game day
                got = False
            if got:
                self.done[key] = standing.day
                said.append(f"*** {feat.name} -- {feat.blurb} ***")
        return said

    def earned(self) -> List[Feat]:
        return [FEATS[k] for k in self.done if k in FEATS]

    def to_dict(self) -> dict:
        return dict(self.done)

    @classmethod
    def from_dict(cls, d: dict) -> "Book":
        b = cls()
        b.done = {k: int(v) for k, v in (d or {}).items() if k in FEATS}
        return b
