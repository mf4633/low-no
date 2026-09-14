"""The lords of the march, as people you learn rather than numbers you read.

Ask anybody what they remember about Stronghold and you will not get the
popularity dial. You will get the Rat, the Snake, the Wolf and the Pig --
characters people still have favourites among twenty-four years later, who
are remembered because each one *plays differently and says so out loud*. The
Rat throws men away in dribs and drabs. The Snake will not fight you himself
and pays somebody who will. The Wolf comes for you properly and does not
surrender when his own wall comes down.

This game had eight lords with excellent names and no character whatever.
`Reeve Halden` and `Abbot Gervase` behaved identically: same aggression, same
ambition, same everything, differing only in how much wall and muster the map
handed them. A rival you cannot tell apart from another rival is a number with
a name on it.

So each of them is now a *sort* of lord, and the sort does three things:

* **It changes how he plays.** The Boar arms early and spends it; the Heron
  builds wall and sits behind it; the Magpie would always rather pay than
  fight and grows fat doing it. These are multipliers on the war engine's own
  dials, so the behaviour is real rather than described.
* **It changes what he says.** He has a voice when he declares for you, when
  he takes a town, when he is beaten, and when he wants something. You learn
  a lord by being insulted by him.
* **It is learnable and plannable.** Trade with a man and you find out what
  sort he is. Then you know whether a gift will hold him off, whether a truce
  is worth buying, and whether he is coming at your wall or your fields.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Sort:
    """A kind of lord: how he plays, and how he talks about it."""
    key: str
    name: str                    # "the Boar"
    blurb: str                   # what a merchant would tell you about him
    aggression: float = 1.0      # how fast ambition builds toward a war
    temper: float = 1.0          # how quickly he takes offence at you
    muster: float = 1.0          # how big a host he puts in the field
    thrift: float = 1.0          # how fast his country grows rich in peace
    raids: float = 0.0           # preference for burning country over walls
    bought: float = 1.0          # how cheaply a truce or a gift buys him off
    holds: float = 1.0           # how hard he is to shift once he holds a town
    # --- how he builds -------------------------------------------------
    #
    # Every lord used to raise the identical castle, because `works()` read
    # it off wealth alone: the Heron who does nothing but build and the Boar
    # who builds nothing had the same wall at the same prosperity. These are
    # shares of the same purse, not extra money, so a man who spends on stone
    # has less for towers -- and each way of spending it has a different
    # thing that cracks it.
    stone: float = 1.0           # curtain: raises the bar for a breach
    towers: float = 1.0          # flanking fire: what punishes an escalade
    water: float = 1.0           # a moat, which stops a mine dead
    traps: float = 1.0           # pitch, pits and oil at the gate
    layers: float = 1.0          # depth: rings between the gate and the hall
    cover: float = 1.0           # how well the towers actually cover the line
    declares: Tuple[str, ...] = ()     # when he means to move on you
    takes: Tuple[str, ...] = ()        # when he takes a town
    beaten: Tuple[str, ...] = ()       # when you break his host
    paid: Tuple[str, ...] = ()         # when you buy him off


SORTS: Dict[str, Sort] = {s.key: s for s in [
    Sort("boar", "the Boar",
         "arms first and thinks afterwards; comes early and comes often",
         aggression=1.75, temper=1.5, muster=1.15, thrift=0.75, bought=0.6,
         # Spends on men, not masonry. Thin, unflanked, and climbable.
         stone=0.7, towers=0.45, water=0.2, traps=0.8, layers=0.5, cover=0.5,
         declares=("I am coming. Do not trouble to write back.",
                   "Your gate is wood and my patience is thinner."),
         takes=("Another. I shall want another after that.",),
         beaten=("You have cost me men I could spare. I will bring more.",),
         paid=("Coin now. Steel later, when the coin runs out.",)),
    Sort("heron", "the Heron",
         "builds wall and stands behind it; will not come unless you make him",
         aggression=0.45, temper=0.7, muster=0.85, thrift=1.25, holds=1.5,
         bought=1.3,
         # Wall first and wall always: water, depth, and towers that cover.
         # Nothing cheap gets in. He still has to eat.
         stone=1.35, towers=1.3, water=1.8, traps=1.1, layers=1.7, cover=1.4,
         declares=("I had hoped to be left alone. You have seen to that.",),
         takes=("It is mine now, and it will stay mine.",),
         beaten=("I shall be behind my own wall before you have formed up.",),
         paid=("A sensible arrangement. I dislike being disturbed.",)),
    Sort("fox", "the Fox",
         "burns your fields rather than face your wall, and treats when losing",
         aggression=1.15, temper=1.2, muster=0.9, thrift=1.1, raids=0.75,
         bought=0.55,
         # Wide, cheap and nasty: everything in traps, nothing in stone. The
         # gate is the way in, and he has made the gate expensive.
         stone=0.6, towers=0.7, water=0.5, traps=1.9, layers=0.8, cover=0.7,
         declares=("I have no quarrel with your walls. Your harvest is another "
                   "matter.",),
         takes=("Taken cheaply, which is the only way worth taking anything.",),
         beaten=("A misunderstanding. Let us call it that.",),
         paid=("Now we understand one another. Until we do not.",)),
    Sort("ox", "the Ox",
         "slow, steady and hard to shift; what he takes he keeps",
         aggression=0.85, temper=0.85, muster=1.25, thrift=1.0, holds=1.6,
         bought=1.1,
         # Thick stone, one gate, and no ditch worth the name. Batter it and
         # you will be there a month; dig under it and it is a week.
         stone=1.7, towers=0.6, water=0.25, traps=0.9, layers=1.1, cover=0.6,
         declares=("I have written it in the roll. I shall come when I come.",),
         takes=("Held. That is the whole of it.",),
         beaten=("You have moved me. Few have.",),
         paid=("Very well. I keep my word; see that you keep yours.",)),
    Sort("magpie", "the Magpie",
         "would always rather pay than fight, and grows fat doing it",
         aggression=0.55, temper=0.6, muster=0.7, thrift=1.5, bought=0.4,
         # Buys what shows: towers and oil, and no depth at all behind them.
         # Get through the front of it and there is nothing else.
         stone=0.9, towers=1.6, water=0.7, traps=1.5, layers=0.4, cover=1.2,
         declares=("Reluctantly. My factors assure me it is the cheaper course.",),
         takes=("A good acquisition, all things considered.",),
         beaten=("An expensive morning. I shall make it back by Michaelmas.",),
         paid=("Sensible. Everything is for sale; only fools fight over price.",)),
    Sort("wolf", "the Wolf",
         "good at everything and in no hurry; the one you plan around",
         aggression=1.25, temper=1.0, muster=1.45, thrift=1.3, holds=1.4,
         bought=1.6,
         # Everything, properly, and the towers actually cover each other.
         # There is no cheap way into the Wolf's seat.
         stone=1.3, towers=1.3, water=1.2, traps=1.2, layers=1.4, cover=1.5,
         declares=("I know what you are worth to within a hundred coins. "
                   "I am coming for it.",),
         takes=("As expected.",),
         beaten=("Once. You will not manage it twice.",),
         paid=("I take your coin. I take it as tribute, whatever you call it.",)),
]}

#: Who is what on the default march. Set here rather than in the scenario so
#: that a lord keeps his character wherever a map puts him, and so that the
#: whole cast can be read at a glance and balanced against itself.
CAST: Dict[str, str] = {
    "dunmere": "boar",         # small, poor, and always the first to try you
    "vantry": "magpie",        # the breadbasket would rather sell than fight
    "bruille": "heron",        # an abbot with a wall and no ambition
    "ostmark": "ox",           # armourers, and they use what they make
    "caldmoor": "boar",        # a mining camp with a temper
    "havnhold": "magpie",      # a port: everything is for sale
    "marchand": "wolf",        # the Count, who is the campaign
    "caer_ithel": "fox",       # out of reach by road, and plays like it
}
DEFAULT = "ox"


def sort_of(key: str) -> Sort:
    return SORTS.get(CAST.get(key, DEFAULT), SORTS[DEFAULT])


def says(key: str, when: str, rng: Optional[random.Random] = None) -> str:
    """What this lord says at a moment like this, if he says anything."""
    lines = getattr(sort_of(key), when, ())
    if not lines:
        return ""
    return (rng or random).choice(list(lines))


def reputation(key: str, seen: bool) -> str:
    """What a merchant would tell you about him -- if you have been there.

    A lord you have never sent a cart to is a lord you are guessing about,
    which is the same rule the rest of the fog follows. Character is
    intelligence, and intelligence is the thing the trade layer buys.
    """
    if not seen:
        return "nobody of yours has been near enough to say"
    return sort_of(key).blurb
