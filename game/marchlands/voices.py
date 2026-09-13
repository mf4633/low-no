"""What the town would say, if you asked it.

The single most quoted thing about Stronghold is not a mechanic. It is a
peasant saying *"Double rations? Oh, thank you, Sire!"* when you move the
ration dial, and *"No taxes is good taxes, that's my motto!"* when you move
the other one. People who have not played it in twenty years can still quote
those lines, and when a sequel dropped them the complaint was that the game
had gone "more bland" -- which is exactly right, and is a complaint about
*information*, not about charm. A dial that answers you is a dial you
understand.

This game had a mood breakdown that was perfectly honest and entirely
inhuman: `taxes -3.5, crowding -2.6, ale +11`. That is the same information,
and it is not the same thing at all, because a number cannot be indignant.

So: `ask`, and somebody answers. Every line is keyed to something actually
true today -- what they are eating, what you are taking, whether they were
paid, whether there is a queue at the bakery, whether the roof they sleep
under exists. They are ordered by how much it matters, so the loudest thing
in the town is the thing you hear about, which makes this a diagnostic that
happens to have a person in it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple




@dataclass(frozen=True)
class Voice:
    """One thing somebody might say, and when they would say it."""
    key: str
    weight: float                       # how loudly this drowns out the rest
    when: Callable[["Mood"], bool]
    lines: Tuple[str, ...]


@dataclass
class Mood:
    """Everything about a town that anybody in it would have an opinion on."""
    name: str = ""
    popularity: float = 50.0
    rations: int = 2
    tax: int = 2
    unpaid: bool = False
    hunger: float = 0.0
    crowded: bool = False
    idle: bool = False
    besieged: bool = False
    raided: bool = False
    fires: int = 0
    queue: float = 0.0                  # the assize biting, 0-1
    relief: float = 0.0                 # ...or paying off
    ale: float = 0.0
    faith: float = 0.0
    lord_home: bool = False
    lord_gone: bool = False
    minted: float = 0.0
    variety: int = 1


def _q(name: str, weight: float, when, *lines: str) -> Voice:
    return Voice(key=name, weight=weight, when=when, lines=lines)


#: Ordered by weight when they fire. A town with a host at the gate does not
#: want to talk about the beer.
VOICES: Tuple[Voice, ...] = (
    _q("siege", 100, lambda m: m.besieged,
       "There are men at the gate, my lord. Ours are on the wall. "
       "That is all anybody is thinking about.",
       "I have carried stones up to the parapet since dawn. Ask me about "
       "the harvest another week."),
    _q("fire", 95, lambda m: m.fires,
       "The bakery is alight and the wind is wrong. Buckets, my lord, "
       "not questions.",
       "Half the row is burning and the other half is watching it burn."),
    _q("raided", 90, lambda m: m.raided,
       "There are riders in the fields. Whatever we sowed is theirs now.",
       "They have had the corn and they have had the byre. We are stood here "
       "with nothing to reap."),
    _q("starving", 88, lambda m: m.hunger > 0.15,
       "There is nothing in the granary, my lord. Nothing. We have eaten the "
       "seed corn and I will not say what else.",
       "My children have not eaten since the day before yesterday. I am past "
       "being polite about it."),
    _q("queue", 80, lambda m: m.queue > 0.35,
       "Bread is fourpence by your proclamation and there is no bread. "
       "I have stood in that line since first light for nothing.",
       "Cheap bread, they said. Cheap bread and an empty shelf, and the baker "
       "selling out the back door at the old price."),
    _q("unpaid", 78, lambda m: m.unpaid,
       "No wages on Friday. I worked the week and I am told to be patient. "
       "Patience does not grind flour.",
       "Six days' work and an apology. I have had better offers from Vantry."),
    _q("debased", 70, lambda m: m.minted > 5000,
       "The new pennies are lighter, my lord. We are not so simple that we "
       "cannot feel the weight of a coin.",
       "Your penny buys what a halfpenny bought. Somebody has been at the "
       "dies and it was not me."),
    _q("relief", 66, lambda m: m.relief > 0.25,
       "Bread at your price, my lord, and there is still some on the shelf. "
       "God keep you while it lasts.",
       "The assize is a kindness and I will say so to anybody who asks."),
    _q("cruel tax", 64, lambda m: m.tax >= 4,
       "You have had two pence in every three. I am not sure what you imagine "
       "is left.",
       "There is a word for what you are taking and it is not tax."),
    _q("heavy tax", 55, lambda m: m.tax == 3,
       "The reeve came twice this month. Twice, my lord.",
       "Heavy, my lord. Not ruinous. Heavy."),
    _q("crowded", 52, lambda m: m.crowded,
       "There are four of us to a bed and one of them is my brother's goat.",
       "No roof going spare, so we sleep where we can. Build, my lord, or we "
       "will walk to somewhere that has."),
    _q("idle", 50, lambda m: m.idle,
       "There is no work. I stand in the square and I am hungry in the "
       "evening exactly as if I had done something.",
       "Half of us have nothing to do and all of us have to eat."),
    _q("no lord", 48, lambda m: m.lord_gone,
       "The hall is empty. A town with nobody in the hall is a town waiting "
       "to be somebody else's.",
       "Who do I take it to, my lord? There is no my lord."),
    _q("thin rations", 45, lambda m: m.rations <= 1,
       "Half rations. I can work on half rations. I cannot work on half "
       "rations and be cheerful about it.",
       "Thin, my lord. We are none of us starving and none of us glad."),
    _q("full rations", 30, lambda m: m.rations >= 3,
       "Double rations, my lord! God bless you, and my wife says the same.",
       "There is meat in it this week. I have not said that since spring."),
    _q("light tax", 28, lambda m: m.tax <= 0,
       "No taxes is good taxes. That has always been my motto and I have "
       "never had cause to change it.",
       "You take nothing and I keep it. I do not know what else to tell you, "
       "my lord -- I am content."),
    _q("ale", 26, lambda m: m.ale > 0.6,
       "There is beer in the inn and enough of it to go round, which is more "
       "than my father could say.",
       "A pot after work. It is not much and it is everything."),
    _q("faith", 24, lambda m: m.faith > 0.6,
       "The bell goes at the right hours and the chapel is full. It settles a "
       "place, that.",
       "Father Aldwin says you are a godly lord. I would not know, but the "
       "roof is mended."),
    _q("lord home", 22, lambda m: m.lord_home,
       "You are in the hall, my lord, and everybody knows it. That is worth "
       "something on a dark evening.",
       "We see you on the wall of a morning. It helps."),
    _q("variety", 20, lambda m: m.variety >= 3,
       "Bread and cheese and an apple. Three things, my lord! My mother never "
       "had three things.",
       "It is not all one thing any more. You would be surprised what that "
       "is worth."),
    _q("content", 10, lambda m: m.popularity >= 70,
       "No complaints, my lord. I am aware that is unusual.",
       "It is a good town. I have been in worse and I do not mean to leave."),
    _q("grumbling", 8, lambda m: m.popularity < 40,
       "It is not what it was. I could not tell you one thing that is wrong "
       "and I could tell you nine.",
       "Somebody said Bruille is better. I have not been, but somebody said "
       "it."),
    _q("nothing", 1, lambda m: True,
       "Nothing to report, my lord. The day is the day.",
       "Middling, my lord. Which is most days."),
)

WHO = ("A woman at the well", "A carter", "One of the reeve's men",
       "A girl with a basket", "The baker's boy", "An old man on the step",
       "A woman with a child on her hip", "A thatcher", "One of the wall guard",
       "A widow from the row", "A lad from the mill", "A fishwife")


def read(settlement, game=None) -> Mood:
    """Take the town's own reading of itself, in things people notice."""
    s = settlement
    rep = s.report
    m = Mood(name=s.name, popularity=s.popularity,
             rations=s.ration_level, tax=s.tax_level,
             unpaid=bool(rep.unpaid), hunger=float(rep.hunger),
             besieged=bool(s.besieged), raided=bool(s.raided),
             fires=len(s.fires.blazes),
             ale=s.coverage("ale_reach", needs_running=True),
             faith=s.coverage("faith_reach"),
             lord_home=bool(s.lord_home), lord_gone=bool(s.lord_lost),
             variety=int(rep.variety or 1))
    if s.assize_mood > 0:
        m.relief = min(1.0, s.assize_mood / 12.0)
    elif s.assize_mood < 0:
        m.queue = min(1.0, -s.assize_mood / 14.0)
    if s.workforce:
        m.idle = (s.workforce - s.employed) / s.workforce > 0.35
    if game is not None:
        m.crowded = s.housing(game.progress) < s.population
        m.minted = game.economy.minted
    else:
        m.crowded = s.housing() < s.population
    return m


def street_rng(settlement, game=None) -> random.Random:
    """The dice the street is spoken with.

    Display code must not draw from the world's stream -- a browser polling
    once a second would re-roll the campaign, and `ask` typed twice would be
    two different afternoons. Seeded on the day and the place instead: stable
    while you look at it, different tomorrow, and it costs the game nothing.
    """
    day = getattr(game, "day", 0)
    seed = getattr(game, "seed", 0)
    # Seeded on a string rather than hash() of a tuple: hash() of a str is
    # salted per process, so that would be a different street every time
    # the program started, which is not what "stable" means.
    return random.Random(f'{seed}:{day}:{getattr(settlement, "key", "")}')


def speak(settlement, game=None, rng: Optional[random.Random] = None,
          how_many: int = 1) -> List[Tuple[str, str]]:
    """Who says what, loudest thing first. Returns (who, what) pairs."""
    rng = rng or random
    mood = read(settlement, game)
    live = [v for v in VOICES if v.when(mood)]
    live.sort(key=lambda v: -v.weight)
    out: List[Tuple[str, str]] = []
    for v in live[:max(1, how_many)]:
        out.append((rng.choice(list(WHO)), rng.choice(list(v.lines))))
    return out


def one(settlement, game=None, rng: Optional[random.Random] = None) -> str:
    """A single line, for a roof somebody clicked on."""
    said = speak(settlement, game, rng, 1)
    return f"{said[0][0]}: “{said[0][1]}”" if said else ""


def loudest(settlement, game=None) -> str:
    """Which voice is currently top, for anything that wants the key."""
    mood = read(settlement, game)
    for v in sorted(VOICES, key=lambda v: -v.weight):
        if v.when(mood):
            return v.key
    return "nothing"


