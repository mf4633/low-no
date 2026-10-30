"""What a place is built out of, and why it looks like that.

Age of Empires II is remembered for a lot of things, and one of them is that
you can tell whose town you are looking at from the roofline. Not from a
banner or a label -- from the fact that a Frankish castle and a Japanese one
are different objects. Five architecture sets did more for that game's sense
of place than any amount of unique-unit design.

This game had one idiom. Every settlement anybody founded, on chalk or on
granite, in the fen or on the border, came out as timber frame and thatch,
because the renderer had one table of styles and no reason to have two.

So a place has a **culture** now, and the culture is a property of the ground
rather than of the player. A hold on the chalk builds long and low in cob and
lime because that is what is under it; a port builds tall and narrow in brick
because land inside the wall is dear and there is no good building stone for
fifty miles; an abbey builds in ashlar because it can afford to and because
the point of an abbey is to look like one. Found a second settlement in a
different quarter of the march and it will not look like your first.

Three rules kept this from being a reskin:

* **It is the same building.** A Hansa granary holds what a March granary
  holds. Architecture is how a thing looks, and a bonus attached to a roof
  shape would be a bonus pretending to be a culture.
* **It is legible from the picture alone.** Each idiom differs in wall
  material, roof material, roof *form* and palette -- four channels, not a
  colour swap -- so you can tell them apart at a glance and from behind.
* **It is the ground's, and the ground does not move.** A culture is assigned
  by where the place is, and taking a town does not re-roof it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Culture:
    key: str
    name: str
    blurb: str
    #: What the walls are made of, in the renderer's own vocabulary. The map
    #: is from the building's default material to this culture's answer.
    walls: Dict[str, str] = field(default_factory=dict)
    #: ...and the roofs. A culture with no good reed swaps thatch for tile.
    roofs: Dict[str, str] = field(default_factory=dict)
    #: How steep. A wet country roofs steeply because it must.
    pitch: float = 1.0
    #: Gable treatment: 'plain', 'stepped' (crow steps), 'hipped' (four
    #: slopes, no gable at all), 'jettied' (the upper floor oversails).
    gable: str = "plain"
    #: A multiplier on the building's own colour, and a tint pulled toward
    #: this. Together they are what makes a street read as one place.
    tone: float = 1.0
    tint: str = ""
    tint_by: float = 0.0
    #: Roof colour, where the culture has a strong one of its own.
    roof_tint: str = ""
    roof_by: float = 0.0
    #: Taller than wide, or lower than long.
    stretch: float = 1.0


CULTURES: Dict[str, Culture] = {c.key: c for c in [
    Culture(
        "march", "the March",
        "Timber frame on a stone plinth, steep thatch, deep eaves. Built by "
        "people who expect weather and raiders in roughly equal measure.",
        walls={"daub": "timber", "plank": "timber"},
        pitch=1.22, gable="jettied", tone=1.0,
        roof_tint="#8a6a3e", roof_by=0.14),
    Culture(
        "hansa", "the Hansa",
        "Brick gables stepped like a stair, tile, and everything tall because "
        "the ground inside a port's wall is the dearest land on the march.",
        walls={"timber": "brick", "daub": "brick", "plank": "brick"},
        roofs={"thatch": "tile"},
        pitch=1.05, gable="stepped", stretch=1.28,
        tint="#8e4b3a", tint_by=0.42,
        roof_tint="#6f7a6a", roof_by=0.30),
    Culture(
        "abbey", "the Abbey",
        "Ashlar and slate, arcaded, and pale enough to see from the next "
        "valley. An abbey is a building that is trying to be seen.",
        walls={"timber": "stone", "daub": "stone", "plank": "stone",
               "clay": "stone"},
        roofs={"thatch": "tile"},
        pitch=1.15, gable="plain", stretch=1.12,
        tint="#b9b6ad", tint_by=0.46,
        roof_tint="#59616b", roof_by=0.44),
    Culture(
        "vale", "the Vale",
        "Cob and lime under long hipped thatch, sitting low out of the wind. "
        "Chalk country: no stone worth quarrying and no need of it.",
        walls={"timber": "daub", "plank": "daub", "stone": "daub"},
        roofs={"tile": "thatch"},
        pitch=0.86, gable="hipped", stretch=0.82,
        tint="#e0d6bc", tint_by=0.40,
        roof_tint="#b49a5c", roof_by=0.22),
    Culture(
        "ironhand", "the Ironhand",
        "Drystone and slate, squat and heavy, with the smoke of something "
        "always going. Upland building: what the hill gives you, mortared "
        "with nothing.",
        walls={"timber": "stone", "daub": "stone", "plank": "stone"},
        roofs={"thatch": "tile"},
        pitch=0.94, gable="plain", stretch=0.88,
        tint="#736f66", tint_by=0.38,
        roof_tint="#4c5048", roof_by=0.40),
]}
DEFAULT = "march"


def culture(key: str) -> Culture:
    return CULTURES.get(key or DEFAULT, CULTURES[DEFAULT])


#: Which idiom a house builds in when it founds a place of its own. A house
#: carries its masons with it -- but only to the first hold; see `for_ground`.
OF_HOUSE: Dict[str, str] = {
    "marcher": "march", "hansa": "hansa", "abbey": "abbey",
    "plough": "vale", "ironhand": "ironhand",
}

#: And which idiom the ground itself suggests, read off what is under it.
#: Ordered: the first rule that fits wins, so a coast is a port before it is
#: anything else and a hill is upland before it is farmland.
def for_ground(terrain: Dict[str, int], house: str = "",
               first: bool = False) -> str:
    """The idiom a place built here would come out in.

    The ground decides, not the builder -- with one exception, and the
    exception has to be checked *first* or it is not an exception at all: a
    house's opening hold is raised by masons who travelled with it, and every
    hold it founds afterwards is raised by men hired locally, which is how
    building has always worked. Testing the ground before the house made all
    five houses open on the same chalk in the same idiom, which is the one
    outcome that makes the whole feature pointless.
    """
    if first and house in OF_HOUSE:
        return OF_HOUSE[house]
    if terrain.get("coast", 0) >= 2:
        return "hansa"
    hills = terrain.get("hills", 0)
    fertile = terrain.get("fertile", 0)
    if hills >= 4 and hills > fertile:
        return "ironhand"
    if fertile >= 6 and hills <= 2:
        return "vale"
    if terrain.get("forest", 0) >= 5:
        return "march"
    return OF_HOUSE.get(house, DEFAULT)


#: The march's own towns, so that the map has more than one skyline on it.
#: Set here rather than derived, for the same reason the lords are: a place
#: should look like itself wherever a scenario puts it.
OF_TOWN: Dict[str, str] = {
    "dunmere": "march", "vantry": "vale", "bruille": "abbey",
    "ostmark": "ironhand", "caldmoor": "ironhand", "havnhold": "hansa",
    "marchand": "abbey", "caer_ithel": "march",
}


def of_town(key: str) -> str:
    return OF_TOWN.get(key, DEFAULT)


def roster() -> List[Tuple[str, str, str]]:
    """Every idiom, for the screen that lists them."""
    return [(c.key, c.name, c.blurb) for c in CULTURES.values()]
