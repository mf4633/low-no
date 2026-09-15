"""The sickness, and the roads it comes down.

Every other bad thing in this game arrives because somebody sent it. Fire
is an accident, a siege is a lord, a raid is a host -- and all of them come
at you across the map in a way you can watch. This one comes down the roads
*you* built, on the carts you are making your money with, and that is the
whole reason it is worth having: it makes the trade network a liability as
well as an asset, and it does it without a second map or a second economy.

**It travels on traffic, not by distance.** A cart that does business in a
sick market carries it home. A town nobody trades with is a town the
sickness never reaches, however close it is; a hub with six routes into it
is the likeliest place in the march to be ill. Somebody who has spent forty
days building the best trade network on the board has also built the best
road for this.

**The lever is the gate, and it costs exactly what it is worth.** Shutting
it stops the carts, which stops the sickness and stops the income in the
same movement. That is the decision: a fortnight of no trade against a
chance of a season of no people. There is no cure to buy and no building
that makes you safe, because a lever with a price is a decision and a lever
without one is a button.

**It burns out.** A sickness that never ends is a permanent tax, and a
permanent tax is not an event. Each one has a life in it, and when that is
spent the town is poorer and quieter and gets on with things.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

#: How likely a cart that traded in a sick market brings it home, per visit.
#: Low on purpose: this has to be a thing that happens to a busy network
#: over a season rather than a thing that happens to everybody at once.
ON_THE_CART = 0.055

#: And the traffic that is not yours. Your market is a place other people's
#: drovers come to, and the game draws their carts on the march map without
#: ever simulating one -- so without this the sickness could only reach you
#: on a cart of your own, and the trade layer puts those on the best pair of
#: *foreign* markets it can find. Two carts carried it for two hundred and
#: eighty days and delivered it nowhere near their own town.
#:
#: Per day, against the share of the markets abroad that are ill.
VISITORS = 0.075

#: What it does to a town each day, as a share of the people. Over a season
#: that is about a third of them, which is roughly what it was and is a
#: disaster a town can come back from.
#:
#: It was held down at 0.0035 for a while, and not because a third was too
#: much. Below about half its people a town in this game used to stop
#: recovering at all -- the granary emptied, hunger pinned at 1.00, and it
#: starved down to four souls over the following year. That turned out to
#: be the garrison: soldiers come off the working population, a garrison
#: raised for a big town does not shrink when the town does, and past a
#: point it leaves nobody in the fields at all. See
#: `Settlement.GARRISON_SHARE`. With men standing down when there are not
#: the people to keep them under arms, a town that buries two hundred and
#: twenty-four comes back, so the toll can be what it should have been.
TOLL = 0.0075

#: And what it does to everything else while it is there: how much of the
#: workforce is too ill or too busy burying to work, and what it takes off
#: the mood. The idling turns out to matter very little to the outcome --
#: between 0.30 and 0.12 a ruined town ended with six souls or fourteen --
#: which is what pointed at the toll, and then at the cliff under it.
IDLE = 0.18
MOOD = -26.0

#: Days a sickness runs before it has burnt through what it can reach.
#: A season, near enough, and a little either side so two towns are never
#: ill on precisely the same schedule.
LIFE = 62
LIFE_SPREAD = 26

#: A sickness will not take hold in a town that has already had it -- not
#: for this long, anyway. Without this a hub reinfects itself off its own
#: carts for ever and the sickness is a climate rather than an event.
IMMUNE = 200

#: Crowding kills. A town with more people than roofs is the one this runs
#: through, which is the same reading that already drives the mood.
CROWDING = 0.55


@dataclass
class Sickness:
    """What is in a town, and how long it has left in it."""
    since: int = -1           # the day it took hold
    until: int = -1           # and the day it will have burnt out
    dead: float = 0.0         # souls it has taken here
    from_where: str = ""      # the market the cart had been to

    @property
    def here(self) -> bool:
        return self.until > 0

    def to_dict(self) -> dict:
        return {"since": self.since, "until": self.until,
                "dead": round(self.dead, 2), "from_where": self.from_where}

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Sickness":
        d = d or {}
        return cls(since=int(d.get("since", -1)), until=int(d.get("until", -1)),
                   dead=float(d.get("dead", 0.0)),
                   from_where=str(d.get("from_where", "")))


def takes_hold(day: int, rng, from_where: str = "") -> Sickness:
    """A sickness beginning today, with an end already written into it."""
    life = LIFE + rng.randint(-LIFE_SPREAD // 2, LIFE_SPREAD // 2)
    return Sickness(since=day, until=day + max(20, life), from_where=from_where)


def toll(people: float, housing: float) -> float:
    """Souls a day, which is worse where they are packed in."""
    if people <= 0:
        return 0.0
    packed = max(0.0, people / max(housing, 1.0) - 1.0)
    return people * TOLL * (1.0 + CROWDING * min(2.0, packed))


def caught(rng, guards: float = 0.0) -> bool:
    """Whether this visit was the one. `guards` is anything that makes a
    market less likely to pass it on -- nothing does yet, and the argument
    is here so that when something does it goes in one place."""
    return rng.random() < ON_THE_CART * (1.0 - min(0.9, guards))


def words(s: Sickness, day: int) -> str:
    """What the panel says about it."""
    if not s.here:
        return ""
    left = max(0, s.until - day)
    if left > 40:
        return "the sickness is taking hold"
    if left > 14:
        return "the sickness is at its height"
    return "the sickness is going out"
