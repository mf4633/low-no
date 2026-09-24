"""The march as a league: a table, a schedule, and the machinery of parity.

The march always had eight rival lords taking towns off each other. What it
did not have was the one thing that turns a set of rivalries into a
competition you can follow -- a *table*. You could not say who was ahead. You
could not say who was coming for you next. And a season that went badly went
badly for ever, because nothing in the design ever handed anything back to
whoever was losing.

Those three gaps have one well-known answer between them, and it is not a
medieval one. The National Football League is the most deliberately balanced
competition anybody has built: a standings table everyone reads the same way,
a schedule published before a ball is thrown, and a set of levers -- the
draft in reverse order of finish, a ceiling on what anyone may spend -- whose
entire purpose is to stop last year deciding next year. "Any given Sunday" is
a design goal, not a slogan.

That is exactly the hole the fair-play pass measured in this game. Outcomes
ranged five-fold across seeds on an identical map, because income and costs
are both proportional to size, so the surplus is a small difference between
two big numbers and an early stumble never compounds back. A league has faced
precisely that problem and solved it on purpose.

So:

* **The table.** Every lord's season, on one page, by a rule anybody can
  check: towns held, then fields won, then what the country is worth.
* **The schedule.** Lords declare at the turn of the year who they mean to
  move on. It can change -- a muster roll is an intention, not an oath -- but
  you are no longer blindsided by a host that was always coming.
* **The draft.** Each spring a handful of men worth having come looking for a
  lord, and they go in *reverse* order of last year's table. Finish last and
  you choose first. It is the single most effective parity device ever
  designed and it plugs straight into a house that needs a steward.
* **The cap.** Not a hard ceiling -- a rising one. Past what your holdings can
  reasonably keep under arms, every further soldier costs more to feed than
  the last, so a runaway host is possible and dear rather than free.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


PLAYER = "player"

#: What a season is worth in the table, in the order ties are broken.
#: Towns first because towns are the game; fields won next because a lord who
#: keeps winning is coming for you whatever he holds; then the country's worth,
#: which is the tie-break nobody argues with.
#: `muster` rather than `worth` for the tie-break: a player with a whole
#: economy behind them is richer than any lord on the march by an order of
#: magnitude, so worth put them top of a column that meant nothing. What a
#: lord could put in the field is the same measure for everybody.
STANDINGS_KEYS = ("towns", "won", "muster")


@dataclass
class Record:
    """One lord's season."""
    key: str
    name: str = ""
    lord: str = ""
    towns: int = 0
    won: int = 0                 # fields and storms carried
    lost: int = 0
    taken: int = 0               # towns taken this season
    given: int = 0               # ...and lost
    worth: float = 0.0           # what the country is worth, for the tie-break
    muster: float = 0.0

    @property
    def played(self) -> int:
        return self.won + self.lost

    def line(self) -> str:
        return f"{self.won}-{self.lost}"

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Record":
        return cls(**d)


@dataclass
class Fixture:
    """Who a lord means to move on this year.

    An intention rather than a fixture in the strict sense: a lord who is
    beaten, bought off or distracted will not go. Publishing it anyway is the
    whole point -- the difference between a war and an ambush is a fortnight's
    notice.
    """
    who: str
    target: str
    declared: int = 0            # the day it was said out loud
    done: bool = False
    #: Why, in words -- Freeciv tells its allies the reason for a war before
    #: it starts, and a lord who says why is a lord you can answer.
    reason: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Fixture":
        return cls(**d)


# --------------------------------------------------------------------- draft
#: What a man who comes looking for a lord is good at, and how good.
#: Deliberately narrow: a draft that hands out a steward of six would decide
#: the game by itself, which is the opposite of what a draft is for.
DRAFT_SKILLS = ("stewardship", "trade", "tactics", "engineering", "charm")
DRAFT_CLASS = 4                  # men in a year's intake
DRAFT_GRADES = (3, 2, 2, 1)      # what the first, second, third and fourth are
#: The experience a grade is worth, in the house's own units. A drafted man
#: arrives knowing his trade and no further on than a son who has held the
#: post for four years -- a draft that handed out a steward of six would decide
#: the game by itself, which is the opposite of what a draft is for.
STEEP_FOR = {1: 70.0 * 1, 2: 70.0 * 4, 3: 70.0 * 9, 4: 70.0 * 16}


@dataclass
class Prospect:
    """A man worth taking on, and what he is worth."""
    name: str
    skill: str
    grade: int
    story: str = ""
    taken_by: str = ""

    def reads(self) -> str:
        return f"{self.name}, {self.skill} {self.grade} -- {self.story}"

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Prospect":
        return cls(**d)


STORIES = {
    "stewardship": ("kept a bishop's manors for nine years",
                    "reeve of a hundred, and the rolls balanced",
                    "ran his father's hall from the age of fifteen"),
    "trade": ("factor to a Hanse house, and left richer than he came",
              "walked the salt road twice a year for a decade",
              "knows what wool fetches in four countries"),
    "tactics": ("held a gate at Vantry with eleven men",
                "serjeant of horse, and never lost a screen",
                "fought in the east and came home with opinions"),
    "engineering": ("raised the mole at Havnhold",
                    "a mason's son who reads Vitruvius",
                    "took two walls down and put one up"),
    "charm": ("carried letters between lords who would not speak",
              "talked a garrison out of a keep without a blow",
              "a clerk in minor orders with a courtier's tongue"),
}
FIRST = ("Wulfric", "Aldhelm", "Ceolred", "Osgar", "Baldwin", "Rainald",
         "Thurstan", "Everard", "Gilbert", "Roger", "Hamo", "Ivo",
         "Adela", "Sibyl", "Constance", "Juliana", "Isabel", "Cecily")
STYLE = ("of the Weald", "Fitzwarin", "the Fleming", "of Ely", "Longsword",
         "the Clerk", "of Barrow", "Blackhand", "the Younger", "of Thirsk")


def draft_class(rng: random.Random, year: int) -> List[Prospect]:
    """The men who came looking for a lord this spring."""
    out: List[Prospect] = []
    used: set = set()
    for grade in DRAFT_GRADES:
        name = f"{rng.choice(FIRST)} {rng.choice(STYLE)}"
        for _ in range(8):
            if name not in used:
                break
            name = f"{rng.choice(FIRST)} {rng.choice(STYLE)}"
        used.add(name)
        skill = rng.choice(DRAFT_SKILLS)
        out.append(Prospect(name=name, skill=skill, grade=grade,
                            story=rng.choice(STORIES[skill])))
    return out


# ----------------------------------------------------------------- the cap
#: Soldiers you may keep for nothing beyond their wages, per town held.
#: Past it every further man costs more to feed than the last -- the tenth
#: over the cap is dearer than the first.
CAP_PER_TOWN = 60.0
CAP_BASE = 45.0
CAP_BITE = 1.45                  # how fast upkeep climbs past the ceiling


def cap_for(towns: int) -> float:
    return CAP_BASE + CAP_PER_TOWN * max(1, towns)


def overage(soldiers: float, towns: int) -> float:
    """The multiplier on upkeep for a host bigger than its holdings.

    Not a hard ceiling. A hard one is a rule the player fights; a rising cost
    is a decision the player makes, and it still ends runaway musters because
    the last man on the roll eats like three.
    """
    cap = cap_for(towns)
    if soldiers <= cap:
        return 1.0
    return 1.0 + CAP_BITE * ((soldiers - cap) / cap) ** 1.35


@dataclass
class Season:
    """A year of the march, and everything that made it one."""
    year: int = 0
    records: Dict[str, Record] = field(default_factory=dict)
    fixtures: List[Fixture] = field(default_factory=list)
    prospects: List[Prospect] = field(default_factory=list)
    order: List[str] = field(default_factory=list)      # draft order, first first
    picking: int = 0                                     # whose turn it is
    opened: bool = False

    def record(self, key: str) -> Record:
        return self.records.setdefault(key, Record(key=key))

    def table(self) -> List[Record]:
        return sorted(self.records.values(),
                      key=lambda r: tuple(-getattr(r, k) for k in STANDINGS_KEYS))

    def place(self, key: str) -> int:
        for i, r in enumerate(self.table(), 1):
            if r.key == key:
                return i
        return len(self.records)

    def fixture_for(self, key: str) -> Optional[Fixture]:
        for f in self.fixtures:
            if f.who == key and not f.done:
                return f
        return None

    def coming_for(self, key: str) -> List[Fixture]:
        return [f for f in self.fixtures if f.target == key and not f.done]

    def on_the_clock(self) -> str:
        if self.picking >= len(self.order):
            return ""
        return self.order[self.picking]

    def undrafted(self) -> List[Prospect]:
        return [p for p in self.prospects if not p.taken_by]

    def to_dict(self) -> dict:
        return {"year": self.year, "picking": self.picking, "opened": self.opened,
                "order": list(self.order),
                "records": {k: r.to_dict() for k, r in self.records.items()},
                "fixtures": [f.to_dict() for f in self.fixtures],
                "prospects": [p.to_dict() for p in self.prospects]}

    @classmethod
    def from_dict(cls, d: dict) -> "Season":
        return cls(year=d.get("year", 0), picking=d.get("picking", 0),
                   opened=d.get("opened", False),
                   order=list(d.get("order", [])),
                   records={k: Record.from_dict(v)
                            for k, v in d.get("records", {}).items()},
                   fixtures=[Fixture.from_dict(f) for f in d.get("fixtures", [])],
                   prospects=[Prospect.from_dict(p) for p in d.get("prospects", [])])


@dataclass
class League:
    """The march's competition, season by season."""
    season: Season = field(default_factory=Season)
    past: List[dict] = field(default_factory=list)      # finished seasons
    bests: Dict[str, Tuple[float, str, int]] = field(default_factory=dict)
    #: The league rolls its own dice, for the same reason the house does: who
    #: turned up looking for a lord this spring must not decide the weather.
    #: Drawing the draft class and the first spring's running order out of the
    #: world's stream moved every seeded outcome in the game, which looks
    #: exactly like a balance change and is not one.
    seed: int = 0

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed or 7)

    def mark(self, what: str, value: float, who: str, year: int) -> bool:
        """A record that stands until somebody beats it."""
        held = self.bests.get(what)
        if held is None or value > held[0]:
            self.bests[what] = (value, who, year)
            return held is not None
        return False

    def champions(self) -> List[Tuple[int, str]]:
        return [(s["year"], s["first"]) for s in self.past if s.get("first")]

    def to_dict(self) -> dict:
        return {"season": self.season.to_dict(), "past": self.past[-24:],
                "bests": {k: list(v) for k, v in self.bests.items()},
                "seed": self.seed, "rng": list(self.rng.getstate())}

    @classmethod
    def from_dict(cls, d: dict) -> "League":
        out = cls(season=Season.from_dict(d.get("season", {})),
                  past=list(d.get("past", [])), seed=d.get("seed", 0))
        out.bests = {k: (v[0], v[1], int(v[2]))
                     for k, v in d.get("bests", {}).items()}
        raw = d.get("rng")
        if raw:
            out.rng.setstate((raw[0], tuple(raw[1]), raw[2]))
        return out
