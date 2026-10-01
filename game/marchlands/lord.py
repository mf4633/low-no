"""The lord: a person, not a flag.

Stronghold's most-copied idea is the popularity dial, but its most *particular*
one is that your lord is a man standing in the courtyard with a sword. He can
be killed, and when he is, the castle is lost -- not because a counter hit
zero, but because the man the whole arrangement was about is dead.

Here he is deliberately not a trapdoor, because the game already holds that a
storming is a catastrophe you carry on from. What he is instead is a decision:
he is worth real numbers wherever he stands, so keeping him safe at home and
getting the good of him in the field are the same coin, seen from two sides.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, List, Optional

#: What a lord is worth to the men who can see him.
HOME_MOOD = 4.0             # a lord in residence, in his own hall
HOME_DEFENCE = 9.0          # and on his own wall
FIELD_ATTACK = 0.16         # a host he rides with hits this much harder
FIELD_MORALE = 0.15         # and breaks that much later

FALL_ODDS = 0.30            # chance he falls when the host he rode with breaks
CAPTURE_ODDS = 0.45         # given he did not fall, that he is taken instead
SUCCESSION_DAYS = 21        # how long the hall is empty before an heir is raised
MOURNING = 22.0             # mood the whole holding loses when he dies

#: Riding at their head. The lord is one man in the line and the line is
#: hundreds, so what he can do with his own hand is bounded on purpose: an
#: order's worth, never a battle's. The knife-edge is that fine -- at even
#: strength the attacker wins one fight in fifty and at ten per cent up
#: nearly every one -- and a free sword would be a lever that decided
#: battles. What he does cost is himself.
RIDE_KILL_CAP = 6           # men he can cut down in one round, at most
RIDE_KILL_SHARE = 0.02      # and never more than this share of those facing him
RIDE_RALLY = 0.02           # steadiness his own line gains, seeing him in front
RIDE_RALLY_CAP = 0.08       # over the whole fight
RIDE_HITS_DOWN = 3          # blows in one fight that bear him down
RIDE_DEATH = 0.12           # each blow past that: the chance it is the last
WOUND_DAYS = (18, 40)       # abed, no bonuses, not to be sent anywhere
VALOUR_PER_RIDE = 6.0       # what a round at their head teaches

FIRST = ("Aldred", "Osric", "Godwin", "Hereward", "Edric", "Wulfstan",
         "Leofric", "Cuthbert", "Morcar", "Siward")
STYLE = ("the Younger", "the Elder", "the Lame", "the Red", "One-Hand",
         "the Quiet", "the Grim", "Longshanks", "the Fair", "the Black")


def name_for(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(STYLE)}"


@dataclass
class Lord:
    """Your lord, wherever he happens to be standing."""
    name: str = "Aldred the Younger"
    alive: bool = True
    seat: str = ""              # the settlement he keeps his hall in
    riding: int = 0             # uid of the host he is with, 0 if at home
    captured: bool = False
    ransom: float = 0.0         # what they want for him back
    heir_days: int = 0          # days until an heir is raised
    heirs: int = 2              # how many are left after this one
    wounded: int = 0            # days abed still to go, 0 if whole
    hits: int = 0               # blows taken in the fight going on now

    @property
    def at_home(self) -> bool:
        return self.alive and not self.captured and not self.riding

    @property
    def in_the_field(self) -> bool:
        return self.alive and not self.captured and bool(self.riding)

    @property
    def gone(self) -> bool:
        """No lord to be had today, for whatever reason."""
        return not self.alive or self.captured

    def standing(self, name_of: Optional[Callable[[str], str]] = None) -> str:
        name = name_of or (lambda k: k)
        if self.captured:
            return f"held for ransom at {self.ransom:,.0f}c"
        if not self.alive:
            if self.heirs <= 0:
                return "dead, and the line with him"
            return f"dead -- an heir is raised in {self.heir_days} days"
        if self.riding:
            return f"riding with host {self.riding}"
        return f"in his hall at {name(self.seat) if self.seat else 'home'}"

    # ------------------------------------------------------------- the day
    def day(self) -> List[str]:
        """Succession, if there is anyone left to succeed; and a wound healing."""
        if self.wounded > 0 and self.alive:
            self.wounded -= 1
            if self.wounded == 0:
                return [f"{self.name} is on his feet again"]
        if self.alive or self.heirs <= 0:
            return []
        self.heir_days -= 1
        if self.heir_days > 0:
            return []
        self.heirs -= 1
        self.alive = True
        self.captured = False
        self.riding = 0
        # A new man: his father's wound and his father's blows are buried
        # with his father.
        self.wounded = 0
        self.hits = 0
        return [f"*** {self.name} is raised in his father's place. ***"]

    def cannot_ride(self) -> str:
        """Why he is not to be sent at anybody's head today, or ''."""
        if not self.alive:
            return "there is no lord to ride"
        if self.captured:
            return f"{self.name} is held for ransom"
        if self.wounded > 0:
            return f"{self.name} is abed with his wound, {self.wounded} days yet"
        return ""

    def borne_down(self, rng: random.Random, heir_name: str) -> List[str]:
        """Too many blows at their head. Wounded, or dead where he stood."""
        past = max(0, self.hits - RIDE_HITS_DOWN)
        if any(rng.random() < RIDE_DEATH for _ in range(past + 1)):
            self.alive = False
            self.riding = 0
            self.hits = 0
            if self.heirs > 0:
                self.heir_days = SUCCESSION_DAYS
                dead, self.name = self.name, heir_name
                return [f"*** {dead} is cut down at the head of his men. The hall "
                        f"is empty for {SUCCESSION_DAYS} days. ***"]
            return [f"*** {self.name} is cut down at the head of his men, and "
                    f"there is no one left to raise. ***"]
        self.wounded = rng.randint(*WOUND_DAYS)
        self.hits = 0
        return [f"*** {self.name} is borne back wounded -- abed for "
                f"{self.wounded} days. ***"]

    def falls(self, rng: random.Random, heir_name: str) -> List[str]:
        """His host has broken around him. Work out what became of him."""
        roll = rng.random()
        if roll < FALL_ODDS:
            self.alive = False
            self.riding = 0
            if self.heirs > 0:
                self.heir_days = SUCCESSION_DAYS
                dead, self.name = self.name, heir_name
                return [f"*** {dead} is dead on the field. The hall is empty "
                        f"for {SUCCESSION_DAYS} days. ***"]
            return [f"*** {self.name} is dead on the field, and there is no "
                    f"one left to raise. ***"]
        if roll < FALL_ODDS + CAPTURE_ODDS:
            self.captured = True
            self.riding = 0
            return [f"*** {self.name} is taken alive. They will want "
                    f"{self.ransom:,.0f}c for him. ***"]
        self.riding = 0
        return [f"{self.name} is cut out of the rout and rides home alone"]

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Lord":
        return cls(**d)


def attack_bonus(lord: Optional[Lord], uid: int) -> float:
    """A lord abed in the baggage is no lord at the head of the line."""
    if lord and lord.riding == uid and lord.wounded <= 0:
        return 1.0 + FIELD_ATTACK
    return 1.0
