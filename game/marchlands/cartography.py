"""Drawing a march: real country turned into dials, and dials into a map.

The hand-made march is a good map and it is the only one. Playing it a sixth
time you are no longer reading the country, you are recalling it -- Vantry has
the grain, Caldmoor has the ore, and the best opening run is Dunmere and back.
A map you have memorised is a map that has stopped asking you anything.

So the country can be drawn instead, from two things:

**Dials.** How hilly, how marshy, how wooded, how fertile, how much coast, how
much ore under it, how many neighbours and how far apart. Each is a number
between nothing and everything, and each one changes what the country is *for*
rather than only what it looks like: hills make ore and eat bread, fen makes
nothing at all until somebody drains it, coast makes salt and wants timber.

**Real places.** Not survey data -- this is a game and there is no map server
behind it. What is real is the *characterisation*: the Welsh Marches really are
hills and oak and castles every eight miles; the fens really are peat, eels and
nothing to quarry; the Rhine gorge really is one river, vineyards on the slope
and a toll castle on every bend, which is why it is the one preset where the
neighbours are rich and close and charge you for everything. Each preset is a
set of dials, a naming morphology taken from the real toponymy of that country,
and a line saying what the place is. Anybody who knows the region will
recognise it; nobody should mistake it for a survey.

The marsh is worth a note of its own, because it is the dial that does the most
work. Fen is not "bad farmland" -- it is land that yields *nothing at all* to
anybody who has not drained it, which is why the drainage of the Fens and the
Dutch polders were the great capital projects of the period. So marsh here is a
terrain no building will stand on, and the only way to get anything out of it
is the one that worked in life: dig.
"""

from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple


# ------------------------------------------------------------------ the dials

@dataclass(frozen=True)
class Dials:
    """What the country is made of. Everything 0..1 unless it says otherwise."""
    hills: float = 0.3
    marsh: float = 0.1
    wood: float = 0.4
    fertile: float = 0.6
    coast: float = 0.2
    ore: float = 0.3
    #: How many neighbours, and how far off. Spread is the one dial that
    #: changes the *shape* of the game rather than the country: close
    #: neighbours mean short routes and short wars.
    towns: int = 7
    spread: float = 0.5

    def clamp(self) -> "Dials":
        f = lambda v: max(0.0, min(1.0, float(v)))
        return replace(self, hills=f(self.hills), marsh=f(self.marsh),
                       wood=f(self.wood), fertile=f(self.fertile),
                       coast=f(self.coast), ore=f(self.ore),
                       spread=f(self.spread),
                       towns=max(3, min(12, int(self.towns))))

    def as_dict(self) -> Dict[str, float]:
        return {"hills": self.hills, "marsh": self.marsh, "wood": self.wood,
                "fertile": self.fertile, "coast": self.coast, "ore": self.ore,
                "towns": float(self.towns), "spread": self.spread}


#: The order they are shown and set in.
DIAL_NAMES = ("hills", "marsh", "wood", "fertile", "coast", "ore",
              "towns", "spread")


def parse_dials(text: str, base: Optional[Dials] = None) -> Dials:
    """`hills=0.8,marsh=0.3` -- so a player can say what they want in one go."""
    d = base or Dials()
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition("=")
        name = name.strip().lower()
        if name not in DIAL_NAMES:
            raise KeyError(f"no dial called {name!r}; "
                           f"try {', '.join(DIAL_NAMES)}")
        try:
            num = float(value)
        except ValueError:
            raise KeyError(f"{name} wants a number, not {value!r}")
        d = replace(d, **{name: int(num) if name == "towns" else num})
    return d.clamp()


# ----------------------------------------------------------------- the places

@dataclass(frozen=True)
class Region:
    """A real country, as dials and as the way its places are named."""
    key: str
    name: str
    note: str                    # what the real place is, in one line
    dials: Dials
    heads: Tuple[str, ...]       # first elements of a place name
    tails: Tuple[str, ...]       # and last
    #: Joined with nothing, or with a vowel, depending on the language.
    joiner: str = ""
    lords: Tuple[str, ...] = ()
    #: Given names. Lords were named after their seat often enough in life,
    #: but a whole march of men called after towns reads as a bug rather than
    #: as a custom, so they get christened first and styled `of` second.
    given: Tuple[str, ...] = ()


REGIONS: Dict[str, Region] = {r.key: r for r in [
    Region(
        "marches", "the Welsh Marches",
        "Oak, red sandstone hills and a castle every eight miles, because for "
        "two hundred years the border moved every spring.",
        Dials(hills=0.62, marsh=0.10, wood=0.70, fertile=0.45, coast=0.0,
              ore=0.35, towns=7, spread=0.42),
        heads=("Clun", "Wig", "Lud", "Brom", "Ches", "Knigh", "Pain", "Hay",
               "Ewy", "Cefn", "Mon", "Radn", "Oswes", "Bishop"),
        tails=("bury", "low", "ford", "castle", "ton", "field", "more",
               "cliff", "wardine", "yard"),
        lords=("Reeve", "Warden", "the Marcher", "Castellan", "Steward"),
        given=("Roger", "Maud", "Gwilym", "Hawise", "Payn", "Sybil", "Walter",
               "Nest", "Ralph", "Angharad", "Hugh", "Isolda")),
    Region(
        "fens", "the Fens",
        "Peat, eels and sedge, with islands of gravel a few feet higher than "
        "the rest, and no stone within forty miles of any of it.",
        Dials(hills=0.04, marsh=0.82, wood=0.16, fertile=0.16, coast=0.30,
              ore=0.03, towns=6, spread=0.60),
        heads=("El", "Wis", "March", "Thorn", "Ram", "Chat", "Sut", "Whit",
               "Soh", "Lit", "Dod", "Hol", "Ben", "Quy"),
        tails=("ey", "beach", "ney", "port", "dyke", "fen", "with", "mere",
               "lode", "drove"),
        lords=("Abbot", "Prior", "Bailiff", "the Dykereeve", "Warden"),
        given=("Osbert", "Edith", "Aylwin", "Emma", "Godric", "Alditha",
               "Ivo", "Leofwen", "Baldwin", "Gunnora")),
    Region(
        "rhine", "the Rhine Gorge",
        "One river through a slate gorge, vines on every south slope, and a "
        "toll castle on every bend -- which is the whole economy.",
        Dials(hills=0.74, marsh=0.06, wood=0.46, fertile=0.40, coast=0.0,
              ore=0.30, towns=9, spread=0.26),
        heads=("Bacha", "Kau", "Ober", "Nieder", "Bop", "Loch", "Rhein",
               "Stahl", "Katz", "Mar", "Ass", "Trech", "Bing", "Sankt"),
        tails=("rach", "berg", "burg", "heim", "bach", "fels", "stein",
               "eck", "thal", "hausen"),
        lords=("the Vogt", "Burgrave", "the Elector's man", "Margrave",
               "Toll-master"),
        given=("Konrad", "Irmgard", "Dietrich", "Adelheid", "Werner", "Kunigunde",
               "Gerlach", "Mechtild", "Reinhard", "Hedwig")),
    Region(
        "po", "the Po Valley",
        "Flat, wet, absurdly fertile, and thick with towns close enough to "
        "quarrel with each other before breakfast.",
        Dials(hills=0.10, marsh=0.30, wood=0.20, fertile=0.92, coast=0.12,
              ore=0.08, towns=10, spread=0.22),
        heads=("Borgo", "Castel", "Vill", "Cre", "Mant", "Pav", "Piac",
               "Sabbi", "Guast", "Rever", "Ostigl", "Quing"),
        tails=("ano", "etta", "franco", "nuovo", "oneta", "alla", "ago",
               "ella", "olo", "ino"),
        joiner="",
        lords=("the Podestà", "Captain", "the Consul", "Signore", "the Vicar"),
        given=("Uberto", "Bianca", "Guido", "Imelda", "Rinaldo", "Costanza",
               "Ottone", "Beatrice", "Lanfranco", "Giovanna")),
    Region(
        "pennines", "the Pennines",
        "Gritstone, lead and rain. Long dales with nothing between them but "
        "moor, and villages where the seam is and nowhere else.",
        Dials(hills=0.90, marsh=0.22, wood=0.22, fertile=0.20, coast=0.0,
              ore=0.80, towns=5, spread=0.70),
        heads=("Grass", "Arn", "Sca", "Buck", "Lang", "Rav", "Kel", "Hor",
               "Stan", "Gun", "Litton", "Cray", "Star", "Mal"),
        tails=("thwaite", "dale", "scar", "fell", "gill", "sett", "rigg",
               "beck", "moor", "clough"),
        lords=("Bailiff", "the Moor-reeve", "Warden", "Master of the Mine",
               "the Forester"),
        given=("Thorold", "Ysenda", "Orm", "Sigrid", "Ketel", "Ediva",
               "Gamel", "Asketil", "Ulf", "Ragnhild")),
    Region(
        "baltic", "the Baltic Shore",
        "Sand, pine and amber, with every town of consequence standing at the "
        "mouth of a river and facing out to sea rather than inland.",
        Dials(hills=0.14, marsh=0.34, wood=0.62, fertile=0.34, coast=0.85,
              ore=0.10, towns=7, spread=0.66),
        heads=("Warne", "Trave", "Swine", "Peene", "Wolg", "Greifs", "Stral",
               "Us", "Dar", "Rüg", "Kol", "Stolp", "Leb", "Putt"),
        tails=("münde", "ow", "stad", "wald", "hagen", "sund", "berg",
               "haven", "dorf", "büttel"),
        lords=("the Ratsherr", "Burgomaster", "the Vogt", "Alderman",
               "the Schöffe"),
        given=("Hinrik", "Wendela", "Bertold", "Grete", "Klaus", "Ilsabe",
               "Lubbert", "Alheyd", "Detmar", "Margarethe")),
]}
DEFAULT_REGION = "marches"


# --------------------------------------------------------------- the drawing

@dataclass
class Drawn:
    """A whole country: what to found, who is out there, and what is going on."""
    region: str
    dials: Dials
    seed: int
    home_name: str = ""
    home_terrain: Dict[str, int] = field(default_factory=dict)
    home_deposits: Dict[str, float] = field(default_factory=dict)
    towns: List[dict] = field(default_factory=list)
    sites: List[dict] = field(default_factory=list)
    shrines: List[dict] = field(default_factory=list)
    note: str = ""


#: What each kind of ground is for. A generated town's trade has to fall out
#: of what is under it or the map is scenery with numbers stapled on: a hill
#: town sells ore and buys bread, a fen town sells almost nothing and buys
#: everything, a shore town sells salt and buys timber.
MAKES = {
    "hills": {"stone": 15.0, "iron_ore": 11.0, "charcoal": 5.0},
    "wood": {"wood": 15.0, "charcoal": 6.0, "planks": 4.0},
    "fertile": {"wheat": 20.0, "apples": 12.0, "cheese": 6.0, "wool": 7.0},
    "coast": {"salt": 10.0, "spice": 4.0},
    "marsh": {"clay": 7.0},
}
WANTS = {
    "hills": {"bread": 10.0, "ale": 5.0, "cloth": 4.0, "wheat": 5.0},
    "wood": {"bread": 6.0, "tools": 2.0, "salt": 2.0},
    "fertile": {"tools": 3.0, "pottery": 4.0, "cloth": 3.5, "iron": 2.0},
    "coast": {"wood": 11.0, "wheat": 8.0, "planks": 5.0, "iron": 3.0},
    "marsh": {"bread": 8.0, "wood": 7.0, "stone": 6.0, "tools": 2.0},
}


def _name(rng: random.Random, region: Region, taken: set) -> str:
    for _ in range(60):
        word = rng.choice(region.heads) + region.joiner + rng.choice(region.tails)
        if word not in taken:
            taken.add(word)
            return word
    taken.add(word)
    return word


def _lord(rng: random.Random, region: Region, seat: str) -> str:
    """A title, a christened name, and -- half the time -- his seat.

    Naming every lord with the place generator gave a march of men called
    Painmore and Ludcliff, which is a real medieval custom and still reads as
    a bug when it happens eight times out of eight.
    """
    who = rng.choice(region.given) if region.given else seat
    if rng.random() < 0.45:
        return f"{rng.choice(region.lords)} {who} of {seat}"
    return f"{rng.choice(region.lords)} {who}"


def _key(name: str, taken: set) -> str:
    base = "".join(ch for ch in name.lower() if ch.isalnum()) or "place"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}{n}", n + 1
    taken.add(key)
    return key


def _ground(rng: random.Random, d: Dials, size: float) -> Dict[str, int]:
    """A patch of country, in slots of each kind of ground.

    Marsh is counted like the rest and used by nothing, which is the point:
    undrained fen is land you own and cannot work.
    """
    def roll(dial: float, top: float) -> int:
        return int(round(top * size * dial * (0.62 + 0.76 * rng.random())))
    return {
        "fertile": roll(d.fertile, 11),
        "forest": roll(d.wood, 9),
        "hills": roll(d.hills, 9),
        "clay": roll(0.35 + 0.5 * d.marsh, 5),
        "coast": roll(d.coast, 5),
        "marsh": roll(d.marsh, 10),
        "urban": 30,
        "rampart": 14,
    }


def ground_from_name(key: str) -> Dict[str, int]:
    """A patch of country for a place the map never drew one for.

    The hand-built scenarios predate towns keeping their ground, and two
    things now read it: what a battle there is fought over, and what a host
    standing there can eat. Neither may answer "nothing" merely because the
    scenario is older than the question -- a map where half the towns have
    country and half have none is worse than one where none do, because the
    half with none are free to besiege and impossible to fight in.

    Stable off the name, and stable across processes: `hash` of a str is
    salted per run, so a town would have had different country every time
    the game was started.
    """
    r = random.Random(zlib.crc32(("ground:" + key).encode()))
    marshy = r.random() < 0.13
    return {
        "fertile": r.randint(2, 10),
        "forest": r.randint(1, 9),
        "hills": r.randint(0, 9),
        "clay": r.randint(0, 4),
        "coast": r.randint(0, 3),
        "marsh": r.randint(5, 10) if marshy else r.randint(0, 2),
        "urban": 30,
        "rampart": 14,
    }


def _flows(ground: Dict[str, int], rng: random.Random,
           d: Dials) -> Tuple[Dict[str, float], Dict[str, float]]:
    """What a town with this ground under it sells, and what it has to buy."""
    makes: Dict[str, float] = {}
    wants: Dict[str, float] = {}
    weights = {"hills": ground.get("hills", 0), "wood": ground.get("forest", 0),
               "fertile": ground.get("fertile", 0), "coast": ground.get("coast", 0),
               "marsh": ground.get("marsh", 0)}
    total = sum(weights.values()) or 1
    for kind, n in weights.items():
        if not n:
            continue
        share = n / total
        for good, rate in MAKES[kind].items():
            makes[good] = makes.get(good, 0.0) + rate * share * (0.7 + 0.6 * rng.random())
        for good, rate in WANTS[kind].items():
            wants[good] = wants.get(good, 0.0) + rate * share * (0.7 + 0.6 * rng.random())
    # Nobody grows their own everything. Whatever a place is short of, it buys.
    for good in list(makes):
        if good in wants:
            keep = makes[good] - wants[good]
            if keep >= 0:
                makes[good], wants[good] = keep, 0.0
            else:
                makes[good], wants[good] = 0.0, -keep
    makes = {k: round(v, 2) for k, v in makes.items() if v > 0.4}
    wants = {k: round(v, 2) for k, v in wants.items() if v > 0.4}
    if not makes:                       # a fen with nothing to sell still sells peat
        makes = {"clay": 4.0}
    _ = d
    return makes, wants


def draw(region: str = DEFAULT_REGION, seed: int = 7,
         dials: Optional[Dials] = None) -> Drawn:
    """Draw a whole march: the seat, the neighbours, the land and the bones."""
    reg = REGIONS.get(region, REGIONS[DEFAULT_REGION])
    d = (dials or reg.dials).clamp()
    rng = random.Random(f"{reg.key}:{seed}")
    names: set = set()
    keys: set = set()

    out = Drawn(region=reg.key, dials=d, seed=seed, note=reg.note)

    home_name = _name(rng, reg, names)
    out.home_name = home_name
    # A seat is chosen ground: a little kinder than the country around it,
    # because that is why somebody built a hall there.
    kind = replace(d, fertile=min(1.0, d.fertile * 1.25),
                   marsh=d.marsh * 0.45)
    out.home_terrain = _ground(rng, kind, 1.0)
    out.home_deposits = {
        "stone": round(2500 + 14000 * d.hills * (0.5 + rng.random()), -2),
        "iron_ore": round(600 + 12000 * d.ore * (0.4 + rng.random()), -2),
    }

    # --- the neighbours ----------------------------------------------------
    # Laid round the seat on a ring with the spacing the spread dial asks for,
    # jittered so it never looks like a clock face.
    reach = 55 + 190 * d.spread
    for i in range(d.towns):
        angle = (i + 0.35 * rng.random()) * (2 * math.pi / d.towns)
        far = reach * (0.55 + 0.85 * rng.random())
        x, y = round(math.cos(angle) * far, 1), round(math.sin(angle) * far, 1)
        name = _name(rng, reg, names)
        key = _key(name, keys)
        # Farther out is bigger and richer: a place that far from your gate
        # got that way without you, which is the only reason it is still there.
        weight = 0.55 + 1.1 * (far / max(reach, 1.0))
        ground = _ground(rng, d, 0.5 + 0.5 * weight)
        makes, wants = _flows(ground, rng, d)
        port = ground.get("coast", 0) >= 3
        out.towns.append({
            "key": key, "name": name, "x": x, "y": y,
            "produces": makes, "consumes": wants,
            "appetite": round(0.8 + 0.5 * rng.random(), 2),
            "lawlessness": round(0.004 + 0.016 * rng.random(), 4),
            "tariff": round(0.035 + 0.05 * rng.random(), 3),
            "lord": _lord(rng, reg, name),
            "walls": int(240 + 700 * weight * (0.6 + 0.7 * rng.random())),
            "muster": round(0.45 + 1.2 * weight * (0.6 + 0.6 * rng.random()), 2),
            "wealth": round(0.85 + 0.5 * weight * rng.random(), 2),
            "port": port,
            "ground": ground,
            "blurb": _blurb(ground, port, rng),
        })

    # --- land nobody holds, and bones worth fetching -----------------------
    for i in range(2):
        angle = rng.random() * 2 * math.pi
        far = reach * (0.35 + 0.4 * rng.random())
        name = _name(rng, reg, names)
        ground = _ground(rng, d, 0.55)
        out.sites.append({
            "key": _key(name, keys), "name": name,
            "x": round(math.cos(angle) * far, 1),
            "y": round(math.sin(angle) * far, 1),
            "terrain": ground,
            "coin_cost": int(2400 + 1800 * rng.random()),
            "blurb": _blurb(ground, ground.get("coast", 0) >= 3, rng),
            "deposits": {"stone": round(1500 + 40000 * d.hills * rng.random(), -2),
                         "iron_ore": round(400 + 30000 * d.ore * rng.random(), -2)},
        })
    for i in range(4):
        angle = (i + 0.5) * (math.pi / 2) + rng.random() * 0.7
        far = reach * (0.75 + 0.5 * rng.random())
        saint = _name(rng, reg, names)
        relic = rng.choice(("the arm", "the veil", "a knucklebone",
                            "the staff", "a tooth", "the girdle"))
        out.shrines.append({
            "key": _key("shrine_" + saint, keys),
            "name": f"St {saint}",
            "short": f"St {saint}",
            "relic": f"{relic} of St {saint}",
            "blurb": rng.choice((
                "A chapel on the old road, three days from any wall.",
                "Wayside bones the pilgrims still walk to.",
                "A cell on the hill with a saint under the floor.",
                "Nobody holds it and everybody wants it.")),
            "x": round(math.cos(angle) * far, 1),
            "y": round(math.sin(angle) * far, 1),
        })
    return out


def _blurb(ground: Dict[str, int], port: bool, rng: random.Random) -> str:
    """One line about what the place is, from what is actually under it."""
    bits = []
    order = sorted(("fertile", "forest", "hills", "marsh", "coast"),
                   key=lambda k: -ground.get(k, 0))
    lead = order[0]
    said = {
        "fertile": ["Grain country, and it knows what grain is worth.",
                    "Corn to the horizon and not a quarry in sight.",
                    "Fat land, fat cattle, and a market every Thursday.",
                    "It grows more than it can eat and sells the difference."],
        "forest": ["Oak and charcoal, and a sawpit at the end of every lane.",
                   "Timber, and everything timber is turned into."],
        "hills": ["Stone and ore under the heather. It buys its bread.",
                  "A mining place. Feed it and it pays in ore.",
                  "Lead and gritstone, and a road that goes up all the way.",
                  "Everything here was carried in, and it shows in the price."],
        "marsh": ["Sedge, peat and standing water. It sells almost nothing.",
                  "Fen. Whatever they eat here came in on a boat.",
                  "Eels, reed and turf. Drain it and it would be worth ten "
                  "times what it is.",
                  "Built on the one gravel bank for a day's walk in any "
                  "direction.",
                  "Wet nine months of the year and dust for the other three."],
        "coast": ["Salt pans and a harbour wall.",
                  "It faces the sea and has its back to the march."],
    }[lead]
    bits.append(rng.choice(said))
    second = order[1] if ground.get(order[1], 0) >= 3 else ""
    if second and second != lead:
        bits.append({
            "fertile": "There is corn on the better ground.",
            "forest": "Woodland behind it.",
            "hills": "Rising ground at its back.",
            "marsh": "Half of it is under water until August.",
            "coast": "It can see the water from the wall.",
        }[second])
    if port and lead != "coast":
        bits.append("Ships call.")
    return " ".join(bits)


def describe(d: Dials) -> List[Tuple[str, float, str]]:
    """The dials, in words, for the screen that sets them."""
    words = {
        "hills": ("flat", "rolling", "hill country", "mountainous"),
        "marsh": ("dry", "damp in places", "half fen", "mostly water"),
        "wood": ("cleared", "hedged", "wooded", "forest"),
        "fertile": ("barren", "thin soil", "good land", "absurdly rich"),
        "coast": ("inland", "a river reach", "an estuary", "a sea coast"),
        "ore": ("no metal", "a little ore", "ore worth digging", "a seam under everything"),
        "spread": ("neighbours at the gate", "close neighbours",
                   "a day's ride apart", "a wide empty march"),
    }
    out = []
    for name in DIAL_NAMES:
        value = getattr(d, name)
        if name == "towns":
            out.append((name, float(value), f"{int(value)} neighbours"))
            continue
        band = words[name][min(3, int(value * 4))]
        out.append((name, float(value), band))
    return out
