"""The small records the game state keeps: the goal, the day's ledger, and the
fight the day is waiting on. Split out of engine.py so each slice of GameState
can name them without importing the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from . import config as C
from .military import Battle


CATHEDRAL_HOLD = 180


@dataclass
class Goals:
    """What this game is played for. A scenario sets its own."""
    net_worth: float = C.GOAL_NET_WORTH
    population: int = C.GOAL_POPULATION
    towns: int = C.GOAL_TOWNS
    relics: int = C.GOAL_RELICS
    relic_days: int = C.RELIC_HOLD_DAYS
    mood: float = 0.0                 # popularity a 'commons' chapter wants
    mood_days: int = 0                # ...held for this long
    days: int = C.GOAL_DAYS
    bankruptcy: float = C.BANKRUPTCY_FLOOR
    wonder: bool = True               # may the cathedral win it?
    paths: Tuple[str, ...] = ("wealth", "dominion", "bells", "reliquary")

    @property
    def years(self) -> int:
        return max(1, round(self.days / C.DAYS_PER_YEAR))

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["paths"] = list(self.paths)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Goals":
        d = dict(d)
        d["paths"] = tuple(d.get("paths",
                                  ("wealth", "dominion", "bells", "reliquary")))
        return cls(**d)


@dataclass
class Ledger:
    taxes: float = 0.0
    trade: float = 0.0
    tribute: float = 0.0
    plunder: float = 0.0
    offerings: float = 0.0
    #: Coin a mission paid. A reward that goes straight into the chest is a
    #: coin the day's accounts cannot explain, and this game has a test that
    #: says every one of them can be.
    reward: float = 0.0
    interest: float = 0.0
    wages: float = 0.0
    upkeep: float = 0.0
    caravans: float = 0.0
    building: float = 0.0
    war: float = 0.0

    @property
    def income(self) -> float:
        return (self.taxes + self.tribute + self.plunder + self.offerings
                + self.interest + self.reward + max(0.0, self.trade))

    @property
    def net(self) -> float:
        # Written as income minus outgoings rather than as its own list of
        # columns. Two hand-written sums of the same ledger is one of them
        # forgetting a column, which is exactly what happened when `reward`
        # was added to `income` and not to this.
        return (self.taxes + self.trade + self.tribute + self.plunder
                + self.offerings + self.interest + self.reward
                - self.wages - self.upkeep - self.caravans - self.building
                - self.war)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _ordinal(n: int) -> str:
    """`3rd of 9`, because `place 3` is not how anybody says it."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


@dataclass
class PendingBattle:
    """A fight the day has stopped on, waiting for somebody to fight it.

    Everything the aftermath needs to finish the day is here by key rather
    than by reference, because this has to survive a save: the army by uid,
    the place by key, the hosts standing inside a sworn town by uid. The
    sides themselves live in the Battle, casualties and all.
    """
    battle: Battle
    kind: str                     # 'wall' -- your own town; 'storm' -- a foreign one
    army: int                     # uid of the host going in
    where: str                    # settlement key, or town key
    side: str                     # which side is yours: 'attacker' or 'defender'
    title: str
    day: int
    stationed: List[int] = field(default_factory=list)
    #: A field battle has hosts on both sides rather than a host and a
    #: wall: `stationed` is the relieving side, `foes` the ring it fights.
    foes: List[int] = field(default_factory=list)
    #: The standing wall, for the picture: the fight itself is at the
    #: breach, with `wall_hp` nought, exactly as `fight` has always had it.
    wall_standing: float = 0.0
    wall_full: float = 0.0
    #: What followed, once it was over -- the sack, the rout, the town
    #: changing hands. Kept on the fight so the screen can say it, because
    #: the engine finishing a battle and the player finishing reading it are
    #: two different moments and the first version conflated them: the day
    #: cleared the fight the instant it ended and the verdict was never seen.
    after: List[str] = field(default_factory=list)

    #: Whether the aftermath has run. A fight can be over and unsettled for
    #: the instant between the last round and `_finish_battle`.
    settled: bool = False
    #: The lord's own part, when he rode at their head: rounds ridden, men
    #: cut down by his hand, steadiness given, and what became of him.
    lord_rode: int = 0
    lord_kills: int = 0
    lord_rally: float = 0.0
    lord_lines: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"battle": self.battle.to_dict(), "kind": self.kind,
                "army": self.army, "where": self.where, "side": self.side,
                "title": self.title, "day": self.day,
                "stationed": list(self.stationed), "foes": list(self.foes),
                "lord_rode": self.lord_rode, "lord_kills": self.lord_kills,
                "lord_rally": self.lord_rally, "lord_lines": list(self.lord_lines),
                "wall_standing": self.wall_standing, "wall_full": self.wall_full,
                "after": list(self.after), "settled": self.settled}

    @classmethod
    def from_dict(cls, d: dict) -> "PendingBattle":
        return cls(battle=Battle.from_dict(d["battle"]), kind=d["kind"],
                   army=d["army"], where=d["where"], side=d["side"],
                   title=d["title"], day=d["day"],
                   stationed=list(d.get("stationed", [])),
                   foes=list(d.get("foes", [])),
                   lord_rode=int(d.get("lord_rode", 0)),
                   lord_kills=int(d.get("lord_kills", 0)),
                   lord_rally=float(d.get("lord_rally", 0.0)),
                   lord_lines=list(d.get("lord_lines", [])),
                   wall_standing=d.get("wall_standing", 0.0),
                   wall_full=d.get("wall_full", 0.0),
                   after=list(d.get("after", [])),
                   settled=bool(d.get("settled", False)))
