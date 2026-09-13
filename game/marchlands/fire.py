"""Fire.

Stronghold's towns were made of timber and thatch and they burned, and the
burning was not a cutscene: it started somewhere, it spread to whatever stood
near it, and it stopped when enough people ran at it with buckets. A besieger
who could get fire into a town did not need to get anything else in.

Three rules, and everything else follows from them:

    what is made of wood catches; what is made of stone mostly does not
    fire spreads to what stands next to it, and a packed town is all next to
        each other
    the only thing that puts it out is hands, and hands are the thing you
        never have enough of

So a fire is a bill presented in the one currency the town is always short
of, at the worst possible moment -- which is the whole idea.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

#: How fast a thing burns, by what it was built out of. A building's timber
#: share sets both how easily it catches and how fast it goes.
TIMBER = ("wood", "planks")
STONE = ("stone", "clay", "iron")

CATCH_BASE = 0.16          # chance a neighbour catches on a given day
BURN_RATE = 0.22           # of the building, per day, unattended
QUENCH_PER_HAND = 0.040    # how much one pair of hands takes off a fire
HANDS_PER_BLAZE = 12.0     # how many it takes to fight one properly. This
                           # must buy more quench than a *summer* fire eats,
                           # or every fire in July is unstoppable however few
                           # there are, which is not a fire system but a
                           # seasonal demolition service.
LOST_AT = 1.0              # ruin, at which point the building is gone
MAX_QUENCH_STEP = 0.22     # you cannot unburn a roof in an afternoon
SCARRED_AT = 0.25          # ruin above which a saved building needs work
SEASON_TINDER = {"spring": 1.0, "summer": 1.45, "autumn": 1.0, "winter": 0.55}


def timber_share(cost: Dict[str, float]) -> float:
    """How much of what this was built from will burn."""
    wood = sum(v for k, v in cost.items() if k in TIMBER)
    stone = sum(v for k, v in cost.items() if k in STONE)
    if wood + stone <= 0:
        return 0.45                     # a shed of nothing much
    return wood / (wood + stone)


@dataclass
class Blaze:
    """One building on fire, and how far gone it is."""
    uid: int
    ruin: float = 0.30                  # it has been burning a while before
                                        # anyone notices; 1 is lost
    days: int = 0
    peak: float = 0.30                  # the worst it got, for the repair bill

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Blaze":
        return cls(**d)


@dataclass
class Fires:
    """Everything burning in one settlement."""
    blazes: Dict[int, Blaze] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.blazes)

    def burning(self, uid: int) -> bool:
        return uid in self.blazes

    def light(self, uid: int) -> bool:
        if uid in self.blazes:
            return False
        self.blazes[uid] = Blaze(uid=uid)
        return True

    def worst(self) -> float:
        return max((b.ruin for b in self.blazes.values()), default=0.0)

    def to_dict(self) -> dict:
        return {"blazes": [b.to_dict() for b in self.blazes.values()]}

    @classmethod
    def from_dict(cls, d: dict) -> "Fires":
        out = cls()
        for raw in d.get("blazes", []):
            b = Blaze.from_dict(raw)
            out.blazes[b.uid] = b
        return out


def hands_wanted(blazes: int) -> float:
    return HANDS_PER_BLAZE * blazes


def burn(fires: Fires, standing: List[Tuple[int, Dict[str, float], bool]],
         *, hands: float, season: str, rng: random.Random
         ) -> Tuple[List[int], Dict[int, float], List[str]]:
    """Advance every fire a day. Returns the uids lost, and the story.

    `standing` is (uid, build cost, is it complete) for everything in the town;
    `hands` is the labour actually thrown at it, which is labour doing nothing
    else -- the fire is a bill whether or not you save the building.

    Returns the uids lost, the uids saved but wanting repair (mapped to how
    much of their building time they need back), and the story.
    """
    lines: List[str] = []
    if not fires.blazes:
        return [], {}, lines
    costs = {uid: cost for uid, cost, _done in standing}
    quench = QUENCH_PER_HAND * hands / max(1, len(fires.blazes))
    tinder = SEASON_TINDER.get(season, 1.0)

    lost: List[int] = []
    scarred: Dict[int, float] = {}
    for uid, blaze in list(fires.blazes.items()):
        share = timber_share(costs.get(uid, {}))
        blaze.days += 1
        eaten = BURN_RATE * (0.45 + 0.85 * share) * tinder
        # Clamped, so a fire always takes a few days one way or the other.
        # Without this the arithmetic is all-or-nothing on the first morning:
        # either quench beats burn and it is out by dawn, or it is not and the
        # whole town goes. There is no interesting fire in between.
        blaze.ruin += max(-MAX_QUENCH_STEP, eaten - quench)
        blaze.peak = max(blaze.peak, blaze.ruin)
        if blaze.ruin <= 0.0:
            del fires.blazes[uid]
            lines.append("a fire is beaten out")
            if blaze.peak >= SCARRED_AT:
                scarred[uid] = min(0.9, blaze.peak)
            continue
        if blaze.ruin >= LOST_AT:
            del fires.blazes[uid]
            lost.append(uid)

    # Each fire reaches for one roof, not for the whole town. That matters:
    # rolling every building against every blaze makes the spread quadratic,
    # and a quadratic fire has exactly two outcomes -- out by morning, or the
    # whole town -- with nothing in between worth playing.
    alight = set(fires.blazes)
    catchable = [(uid, cost) for uid, cost, done in standing
                 if done and uid not in alight]
    if catchable:
        for blaze in list(fires.blazes.values()):
            odds = CATCH_BASE * tinder * min(1.0, 0.35 + blaze.ruin)
            if rng.random() >= odds:
                continue
            uid, cost = catchable[rng.randrange(len(catchable))]
            if rng.random() < timber_share(cost) and fires.light(uid):
                lines.append("the fire jumps to the next roof")
    return lost, scarred, lines
