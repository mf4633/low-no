"""The Marcher Chronicle: six chapters, one house, one man in the way.

Both parents are remembered for their campaigns rather than their skirmishes,
and for the same reason. A scenario asks *can you do this*; a campaign asks
*what became of you*. The difference is that the second one has a middle --
things you learned in chapter two that you need in chapter five, a name you
first hear spoken with mild contempt and last hear at the foot of his own
wall, and a house that arrives at each chapter carrying whatever the last one
left it.

So: six chapters. Each foregrounds one system, in the order a person can
actually learn them. Each hands the next one your purse, your learning, your
lord and his line, and the chronicle of everything so far. And running under
all of it is the Count of Marchand, who is richer than you at the start and
has no particular reason to notice you at all.
"""

from __future__ import annotations

import json

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import config as C
from .chronicle import Chronicle
from .engine import Goals, GameState
from .scenarios import start as start_scenario

#: The man the campaign is about. He is on the map from the first chapter, but
#: he does not know your name until the fourth.
RIVAL = "marchand"


@dataclass
class Carry:
    """What a house takes with it from one chapter to the next."""
    purse: float = 0.0
    techs: Tuple[str, ...] = ()
    lord_name: str = ""
    heirs: int = 2
    renown: int = 0
    chronicle: Chronicle = field(default_factory=Chronicle)
    outcomes: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"purse": self.purse, "techs": list(self.techs),
                "lord_name": self.lord_name, "heirs": self.heirs,
                "renown": self.renown, "chronicle": self.chronicle.to_dict(),
                "outcomes": list(self.outcomes)}

    @classmethod
    def from_dict(cls, d: dict) -> "Carry":
        return cls(purse=d.get("purse", 0.0),
                   techs=tuple(d.get("techs", ())),
                   lord_name=d.get("lord_name", ""),
                   heirs=d.get("heirs", 2),
                   renown=d.get("renown", 0),
                   chronicle=Chronicle.from_dict(d.get("chronicle", {})),
                   outcomes=tuple(d.get("outcomes", ())))


@dataclass(frozen=True)
class Chapter:
    key: str
    name: str
    teaches: str
    scenario: str
    briefing: str
    dress: Callable[[GameState], None]
    won: str                      # how the ending reads when it goes your way
    lost: str                     # ...and when it does not
    years: float = 2.0

    def start(self, seed: int = 7, house: str = "plough",
              carry: Optional[Carry] = None) -> GameState:
        g = start_scenario(self.scenario, seed=seed, house=house)
        g.chapter = self.key
        carry = carry or Carry()
        # What the house brings with it.
        if carry.purse:
            g.treasury += carry.purse
        for key in carry.techs:
            g.progress.researched.add(key)
        if carry.lord_name:
            g.lord.name = carry.lord_name
            g.lord.heirs = carry.heirs
        if len(carry.chronicle):
            g.chronicle = carry.chronicle
        self.dress(g)
        g.briefing = self.briefing
        return g


# --------------------------------------------------------------- the chapters
def _quiet_march(g: GameState, temper: float = 0.55) -> None:
    """Turn the lords down. Early chapters are not about being invaded."""
    for t in g.world.towns.values():
        t.hostility *= temper
        t.aggression *= temper
        t.ambition *= temper


def _one(g: GameState) -> None:
    _quiet_march(g, 0.40)
    g.goals = Goals(net_worth=22_000.0, population=230, towns=99,
                    days=int(2 * C.DAYS_PER_YEAR), wonder=False,
                    paths=("wealth",))


def _two(g: GameState) -> None:
    _quiet_march(g, 0.55)
    # The levy is the point of the chapter: the coin goes out whatever you do,
    # so the only lever left is whether your people stay content while it does.
    g.treasury = max(600.0, g.treasury * 0.55)
    home = g.world.settlements[next(iter(g.world.settlements))]
    home.tax_level = min(len(C.TAX_LEVELS) - 1, home.tax_level + 2)
    g.goals = Goals(net_worth=1e12, population=10, towns=99,
                    days=int(2 * C.DAYS_PER_YEAR), wonder=False,
                    mood=62.0, mood_days=150, paths=("commons",))


def _three(g: GameState) -> None:
    _quiet_march(g, 0.60)
    g.goals = Goals(net_worth=48_000.0, population=200, towns=99,
                    days=int(2 * C.DAYS_PER_YEAR), wonder=False,
                    paths=("wealth",))


def _four(g: GameState) -> None:
    """Marchand comes. Everything else is scenery."""
    count = g.world.towns[RIVAL]
    count.hostility = C.HOSTILITY_WAR
    count.aggression *= 1.6
    count.temper *= 1.5
    count.muster *= 1.35
    for key, t in g.world.towns.items():
        if key != RIVAL:
            t.hostility *= 0.35
            t.aggression *= 0.5
    g.goals = Goals(net_worth=1e12, population=10, towns=99,
                    days=int(2 * C.DAYS_PER_YEAR), wonder=False,
                    paths=("endure",))


def _five(g: GameState) -> None:
    count = g.world.towns[RIVAL]
    count.hostility = 70.0
    count.ambition = 90.0
    g.SHRINE_RACE_ODDS = 0.03          # he is going for them in earnest
    g.goals = Goals(net_worth=1e12, population=10, towns=99, relics=3,
                    relic_days=90, days=int(2 * C.DAYS_PER_YEAR), wonder=False,
                    paths=("reliquary",))


def _six(g: GameState) -> None:
    count = g.world.towns[RIVAL]
    count.prosperity *= 1.5
    count.muster *= 1.5
    count.wall_base *= 1.2
    count.hostility = C.HOSTILITY_WAR
    g.goals = Goals(net_worth=150_000.0, population=460, towns=1,
                    days=int(3 * C.DAYS_PER_YEAR),
                    paths=("dominion", "wealth", "bells"))


CHAPTERS: List[Chapter] = [
    Chapter(
        "inheritance", "A Small Inheritance", "the market", "marchlands",
        briefing=(
            "Your father held one hill, nine fields and a wood, and owed nobody.\n"
            "He also never once found out what wheat was worth in Vantry.\n"
            "Two years. Learn the roads, and come out of it worth something."),
        dress=_one, years=2,
        won="You are worth noticing. Nobody has noticed yet.",
        lost="The hill is still yours. That is all that can be said for it."),
    Chapter(
        "reeve", "The Reeve's Complaint", "the commons", "marchlands",
        briefing=(
            "The Crown wants its levy and does not care how you raise it.\n"
            "Your taxes are set high and they are staying high.\n"
            "Keep your people content anyway, for a hundred and fifty days\n"
            "together -- bread is not enough; they want ale, and a service,\n"
            "and a reason not to walk to Vantry instead."),
        dress=_two, years=2,
        won="The levy was paid and nobody left. Both halves of that are rare.",
        lost="The levy was paid. The town emptied paying it."),
    Chapter(
        "salt", "The Salt Road", "the sea", "salt_road",
        briefing=(
            "Sealow, on the north shore, and a harbour that has never been used\n"
            "for anything but fish. A cog carries seven carts and fears only the\n"
            "weather. The Count of Marchand has begun buying the coast, and pays\n"
            "above the odds for salt. Sell it to him. Take his money."),
        dress=_three, years=2,
        won="His coin spent as well as anyone's. He will remember the name.",
        lost="The coast stayed his. You are a tenant on it."),
    Chapter(
        "dust", "Dust on the Road", "the castle", "marchlands",
        briefing=(
            "The Count of Marchand has decided what you are: a gap in his map.\n"
            "His host is coming and it is bigger than yours will ever be.\n"
            "Two years. Do not win -- there is no winning this one.\n"
            "Still be here at the end of it."),
        dress=_four, years=2,
        won="You are still here. He did not expect that and neither did you.",
        lost="The keep is down and the march has your measure."),
    Chapter(
        "bones", "The Bones of St Ceolwulf", "the map", "marchlands",
        briefing=(
            "Five shrines, and a Count who has worked out that the pilgrims'\n"
            "offerings pay for soldiers. His parties are already on the roads.\n"
            "Hold three of the march's relics for ninety days together.\n"
            "They are nowhere near your walls. That is the whole problem."),
        dress=_five, years=2,
        won="The pilgrims come to you now, and their coin with them.",
        lost="He has the bones, the offerings, and the argument."),
    Chapter(
        "count", "The Count of Marchand", "everything", "marchlands",
        briefing=(
            "He is richer than you, his walls are better than yours, and he has\n"
            "had thirty years to dig in front of them.\n"
            "Break him, out-earn him, or build something that outlasts them both.\n"
            "Three years. There is no seventh chapter."),
        dress=_six, years=3,
        won="The march is yours, by whichever road you took to it.",
        lost="He outlived you. Most of them do."),
]

BY_KEY: Dict[str, Chapter] = {c.key: c for c in CHAPTERS}


@dataclass
class Run:
    """A campaign in progress: where you are, and what you are carrying."""
    chapter: int = 0
    seed: int = 7
    house: str = "plough"
    carry: Carry = field(default_factory=Carry)

    @property
    def done(self) -> bool:
        return self.chapter >= len(CHAPTERS)

    @property
    def current(self) -> Chapter:
        return chapter_at(self.chapter)

    def begin(self) -> GameState:
        return self.current.start(seed=self.seed + self.chapter * 17,
                                  house=self.house, carry=self.carry)

    def finish(self, g: GameState) -> Tuple[bool, str]:
        """Close the chapter out and move the house on. Returns (won, epilogue)."""
        ch = self.current
        won = won_chapter(g)
        self.carry = carry_from(g, self.carry, won)
        self.chapter += 1
        return won, (ch.won if won else ch.lost)

    def standing(self) -> List[str]:
        out = []
        for i, ch in enumerate(CHAPTERS):
            mark = ("done" if i < self.chapter else
                    "here" if i == self.chapter else "    ")
            outcome = ""
            for rec in self.carry.outcomes:
                key, _, how = rec.partition(":")
                if key == ch.key:
                    outcome = how
            out.append(f"  {mark}  {i + 1}. {ch.name:<26} {ch.teaches:<12} {outcome}")
        return out

    def to_dict(self) -> dict:
        return {"chapter": self.chapter, "seed": self.seed, "house": self.house,
                "carry": self.carry.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> "Run":
        return cls(chapter=d.get("chapter", 0), seed=d.get("seed", 7),
                   house=d.get("house", "plough"),
                   carry=Carry.from_dict(d.get("carry", {})))

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=1)
        return f"campaign saved to {path}"

    @classmethod
    def load(cls, path: str) -> "Run":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


def chapter_at(i: int) -> Chapter:
    return CHAPTERS[max(0, min(len(CHAPTERS) - 1, i))]


def carry_from(g: GameState, carry: Carry, won: bool) -> Carry:
    """What survives a chapter.

    Deliberately generous with learning and mean with coin: a house remembers
    what it worked out, and spends what it earned.
    """
    purse = min(9_000.0, max(0.0, g.treasury) * (0.30 if won else 0.15))
    renown = carry.renown + (3 if won else 1)
    return Carry(
        purse=purse,
        techs=tuple(sorted(set(carry.techs) | set(g.progress.researched))),
        lord_name=g.lord.name,
        heirs=max(0, g.lord.heirs),
        renown=renown,
        chronicle=g.chronicle,
        outcomes=carry.outcomes + (f"{g.chapter}:{'won' if won else 'lost'}",),
    )


def won_chapter(g: GameState) -> bool:
    """Did that chapter go your way? The endings say so in their own words."""
    if not g.over:
        return False
    bad = ("Ruined", "Ended.", "Time called", "IS STORMED")
    return not any(b in g.over for b in bad)
