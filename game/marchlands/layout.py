"""Where everything actually stands, so a renderer can draw a place.

The terminal view fits the town to whatever grid the console can spare. A
picture wants the opposite: a real plan, laid out once and consistently, with
streets that go somewhere, fields outside the wall, woods on the wood side and
the river where the river is.

This module is that plan, and it lives in Python rather than in the drawing
code for one reason: layout is a decision and decisions should be testable.
The renderer's only job is to make it look like something.
"""

from __future__ import annotations

import random
import zlib
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config as C
from .buildings import BUILDINGS
from . import keep as keeps

GRASS, FIELD, FOREST, HILL, CLAY, WATER, ROAD, YARD, MARSH = (
    "grass", "field", "forest", "hill", "clay", "water", "road", "yard",
    "marsh")

#: Which ground a building of each terrain wants under it.
GROUND_FOR = {"fertile": FIELD, "forest": FOREST, "hills": HILL,
              "clay": CLAY, "coast": WATER, "urban": YARD, "rampart": YARD}


@dataclass
class Placed:
    uid: int
    key: str
    x: int
    y: int
    category: str
    terrain: str
    complete: bool
    running: bool
    idle: bool
    burning: bool
    name: str
    #: Head of livestock standing in this yard, for the yards that keep any.
    #: Carried onto the drawing so the flock you can see is the flock the
    #: books are paying you for -- see settlement.BuildingInstance.head.
    head: float = -1.0
    #: Whether it is open for business at all. `idle` covers both a shed
    #: short of hands and a shed you have shut, and those are not the same
    #: thing to anybody deciding where to send people: one wants hands and
    #: the other refuses them.
    enabled: bool = True

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Haul:
    """One load going from where it was made to where it is wanted.

    This is the thing people actually describe when they describe Stronghold:
    not the popularity dial, the little man carrying wheat to the mill. It is
    read off the real production graph -- a haul exists only where a building
    that is running wants something a building that is running makes -- so
    what you watch crossing the street is what the ledger is doing.
    """
    frm: int
    to: int
    good: str
    #: The way round, not the way through. A carrier who walks the straight
    #: line between two buildings spends the journey inside other people's
    #: roofs, which is both wrong and invisible.
    path: List[Tuple[float, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"frm": self.frm, "to": self.to, "good": self.good,
                "path": [{"x": x, "y": y} for x, y in self.path]}


#: How many souls one drawn figure stands for, and how many men one figure on
#: the wall stands for.
#:
#: This is the honest answer to a real tension. The simulation runs on
#: aggregates -- a population is a float, a garrison is a dictionary of counts
#: -- and the picture draws people. Draw one figure per soul and a town of two
#: hundred is an unreadable crowd and a dead framerate; draw an arbitrary
#: handful of decorative dots and the picture is telling you something that is
#: not true.
#:
#: So a figure is a *sample*, at a ratio the interface states out loud, doing
#: something the aggregate is actually doing: a worker walks between the roof
#: he sleeps under and the shed he is staffed at today, and a spearman stands
#: on a yard of wall that is really being held. Thin the garrison and the wall
#: visibly empties. The picture is then a readout rather than an illustration,
#: which is the same rule the rest of this codebase follows.
#: Which beast each yard keeps. How MANY is not written here: that is the
#: yard's own head, kept on the building and paid out by the economy -- see
#: config.HERD_FULL and settlement.BuildingInstance.head.
#:
#: A sheep pasture with no sheep in it is a shed with a label on, and the
#: same is true of a dairy and a stable. They are drawn for the same reason
#: the people are: you should be able to tell what a yard is for by looking
#: at it, and a flock is the most legible thing in a medieval landscape.
#:
#: What makes them worth the pixels rather than decoration is that the
#: flock you can see is the flock you are being paid for. A raid drives
#: them off and the wool stops with them; the field empties on screen
#: because the yard's head fell, not because a renderer was told a raid
#: looks like an empty field. The picture cannot flatter the books.
HERDS = {
    "sheep_farm": "sheep",
    "dairy": "cow",
    "stable": "horse",
}


#: What a figure at each kind of shed is actually doing, as a posture the
#: renderer can draw and a phrase the tooltip can say.
#:
#: The postures are deliberately few. Seven silhouettes that read at this
#: scale beat thirty that all look like a smudge with an arm: an overhead
#: swing, a low sweep, a strike on an anvil, a lean over a vessel, a walk
#: with a load, a man talking with his hands, and a man standing with a
#: spear. What makes a blacksmith read as a blacksmith is that he is at the
#: blacksmith's, hammering, while the man in the next yard is bent over a
#: furrow -- not that his hammer has a detailed head.
TRADES = {
    "woodcutter": ("swing", "felling timber"),
    "charcoal_burner": ("tend", "watching the burn"),
    "farm": ("reap", "in the wheat"),
    "hop_farm": ("reap", "on the hop poles"),
    "orchard": ("reap", "among the trees"),
    "sheep_farm": ("herd", "with the sheep"),
    "dairy": ("herd", "at the milking"),
    "quarry": ("swing", "at the stone face"),
    "iron_mine": ("swing", "down the adit"),
    "clay_pit": ("swing", "cutting clay"),
    "blacksmith": ("strike", "at the anvil"),
    "armourer": ("strike", "beating plate"),
    "armoury": ("strike", "at the bench"),
    "fletcher": ("strike", "fitting arrows"),
    "poleturner": ("strike", "at the lathe"),
    "siege_yard": ("strike", "framing an engine"),
    "sawmill": ("strike", "on the saw"),
    "bakery": ("tend", "at the oven"),
    "brewery": ("tend", "over the mash"),
    "kiln": ("tend", "at the kiln"),
    "smelter": ("tend", "at the furnace"),
    "saltworks": ("tend", "at the pans"),
    "mill": ("tend", "at the millstones"),
    "weaver": ("tend", "at the loom"),
    "granary": ("carry", "shifting sacks"),
    "warehouse": ("carry", "shifting bales"),
    "harbour": ("carry", "on the quay"),
    "market": ("talk", "keeping the stall"),
    "trading_post": ("talk", "at the counter"),
    "guildhall": ("talk", "in the hall"),
    "inn": ("talk", "serving"),
    "cathedral": ("pray", "at the altar"),
    "barracks": ("guard", "at drill"),
    "stable": ("herd", "with the horses"),
}

#: The posture for a shed nobody wrote a line for. A new building should look
#: like somebody is at it rather than like nobody is.
DEFAULT_TRADE = ("tend", "at work")

#: How many souls one figure in the picture stands for.
#:
#: Was fourteen, which is honest and was too coarse to look at: a town of two
#: hundred showed fourteen figures over fifty buildings, most of them on a
#: road rather than at a shed, and the first thing anybody said about the
#: picture was that there were no people in it. At eight a town of two
#: hundred has two dozen, which is enough that the yards look worked.
#:
#: The number is stated on screen, so it can move without the picture
#: becoming a lie -- that is the whole reason it is stated.
SOULS_PER_FIGURE = 8

#: And the most that are ever drawn, however big the town gets. Past this the
#: precinct is a crowd rather than a place and the frame rate is paying for
#: people nobody can pick out.
MOST_FIGURES = 30
MEN_PER_FIGURE = 6


@dataclass
class Beast:
    """One animal in a yard. Not a sample of anything -- a sheep is a sheep."""
    x: float
    y: float
    kind: str                       # 'sheep', 'cow', 'horse'
    at: int = -1                    # uid of the yard it belongs to
    #: A number of its own, so the renderer can give it its own grazing
    #: rhythm without every beast in the fold nodding in time.
    seed: int = 0

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "kind": self.kind,
                "at": self.at, "seed": self.seed}


@dataclass
class Walker:
    """One person, standing for fourteen of them, going somewhere real.

    The identity fields are here so that clicking a figure can answer a
    question rather than invent one. A worker already knows the roof he
    sleeps under and the shed he is walking to -- that is how his path was
    drawn -- and it was simply being thrown away.
    """
    x: float
    y: float
    kind: str                       # 'worker', 'idle', 'watch', 'kin'
    path: List[Tuple[float, float]] = field(default_factory=list)
    at: str = ""                    # what they are doing, for the tooltip
    home: int = -1                  # uid of the roof they sleep under
    work: int = -1                  # uid of the shed they are walking to
    souls: int = 0                  # how many of them this one figure is
    who: str = ""                   # a name, for the few who have one
    post: str = ""                  # and the job they hold, if any
    #: The posture this figure is drawn in -- see TRADES. A worker standing
    #: at a shed doing that shed's own work is the whole of what makes a
    #: town look worked rather than populated.
    trade: str = ""

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "kind": self.kind, "at": self.at,
                "home": self.home, "work": self.work, "souls": self.souls,
                "who": self.who, "post": self.post, "trade": self.trade,
                "path": [{"x": x, "y": y} for x, y in self.path]}


@dataclass
class Plan:
    w: int
    h: int
    tiles: List[List[str]]
    buildings: List[Placed] = field(default_factory=list)
    walls: List[Tuple[int, int, str]] = field(default_factory=list)
    folk: List[Walker] = field(default_factory=list)
    beasts: List[Beast] = field(default_factory=list)
    hauls: List[Haul] = field(default_factory=list)
    precinct: Tuple[int, int, int, int] = (0, 0, 0, 0)
    #: Every tile the wall actually shuts in, which for anything but a square
    #: is not the same as the precinct's bounding box.
    inside: List[Tuple[int, int]] = field(default_factory=list)
    #: Where the road leaves the wall: the gate you built, or, in a wall with
    #: none, the stretch the road runs through -- the way people get in and
    #: out. The picture's pathfinder walks them through it.
    door: Optional[Tuple[int, int]] = None

    def tile(self, x: int, y: int) -> str:
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.tiles[y][x]
        return GRASS

    def to_dict(self) -> dict:
        x0, y0, x1, y1 = self.precinct
        return {"w": self.w, "h": self.h, "tiles": self.tiles,
                "inside": [{"x": x, "y": y} for x, y in self.inside],
                "buildings": [b.to_dict() for b in self.buildings],
                "walls": [{"x": x, "y": y, "kind": k} for x, y, k in self.walls],
                "folk": [f.to_dict() for f in self.folk],
                "beasts": [b.to_dict() for b in self.beasts],
                "per_figure": SOULS_PER_FIGURE,
                "per_watch": MEN_PER_FIGURE,
                "hauls": [h.to_dict() for h in self.hauls],
                "precinct": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                "door": ({"x": self.door[0], "y": self.door[1]}
                         if self.door else None)}


def _walk(plan: Plan, a: "Placed", b: "Placed") -> List[Tuple[float, float]]:
    """A route from one door to another that keeps to the street.

    Not a pathfinder -- the streets are a cross through the middle of the
    precinct and a road out of the gate, so the way round is: step to the
    nearest lane, follow it, step off at the other end. That is enough to make
    a carrier read as somebody going somewhere rather than a dot sliding
    through a roof.
    """
    roads = [(x, y) for y in range(plan.h) for x in range(plan.w)
             if plan.tiles[y][x] == ROAD]
    if not roads:
        return [(a.x, a.y), (b.x, b.y)]
    near = lambda p: min(roads, key=lambda r: abs(r[0] - p.x) + abs(r[1] - p.y))
    r1, r2 = near(a), near(b)
    if r1 == r2:
        return [(a.x, a.y), (float(r1[0]), float(r1[1])), (b.x, b.y)]
    # Along the lane in two straight runs, which is how a grid of streets is
    # actually walked.
    corner = (r1[0], r2[1]) if plan.tile(r1[0], r2[1]) == ROAD else (r2[0], r1[1])
    return [(a.x, a.y), (float(r1[0]), float(r1[1])),
            (float(corner[0]), float(corner[1])),
            (float(r2[0]), float(r2[1])), (b.x, b.y)]


#: Where one of yours stands when they hold a post here. First roof of the
#: first kind that is standing; a post whose building has not been raised yet
#: waits at the hall, because they are still in the town doing the job.
POST_WHERE = {
    "steward": ("keep", "guildhall", "market"),
    "factor": ("trading_post", "market", "warehouse", "harbour"),
    "master": ("siege_yard", "quarry", "sawmill", "kiln"),
    "captain": ("barracks", "gatehouse", "keep"),
}
#: The envoy is not on this list on purpose: "sits with the other lords" means
#: away. A figure of him in your own square would be a lie about where he is.


def plan_for(settlement, *, size: int = 0, officers=None) -> Plan:
    """Lay a settlement out on a square of ground.

    Deterministic: the same town always comes out the same way, so the picture
    does not rearrange itself every time you look at it.

    `officers` are the few people in the town who are somebody rather than a
    sample of fourteen: pass a list of `{"name", "post"}` and each is placed
    at the building their post attaches to. The caller resolves who holds
    what, so this module still knows nothing about houses and marriages.
    """
    standing = [b for b in settlement.buildings]
    urban = [b for b in standing if b.spec.terrain == "urban"]
    # A wall building is not a shed on a plot any more: it is the length of
    # wall it paid for, and it stands on it. Placing them in the precinct as
    # well was how a killing pit came to be reported as a workshop somebody
    # had left outside the gate.
    ramparts = [b for b in standing
                if b.spec.terrain == "rampart" and b.key != "keep"]
    country = [b for b in standing if b.spec.terrain in
               ("fertile", "forest", "hills", "clay", "coast")]

    # The ground is a fixed square. It used to grow with the town, which was
    # fine while nothing had a permanent address -- but a wall you drew at
    # (12,9) cannot have the map move out from under it because somebody
    # raised a bakery. See keep.SIDE.
    side = size or keeps.SIDE
    plan = Plan(w=side, h=side, tiles=[[GRASS] * side for _ in range(side)])
    # crc32 rather than hash(): hash() of a str is salted per process, so the
    # idle folk this seeds would stand in slightly different places every time
    # the program started -- and the docstring above promises they do not.
    rng = random.Random(zlib.crc32(settlement.name.encode("utf-8")))
    cx = cy = side // 2

    # --- the castle, as drawn ---------------------------------------------
    castle = settlement.plan() if hasattr(settlement, "plan") else keeps.Castle()
    inside = sorted(keeps.enclosed(castle))
    for t, kind in sorted(castle.pieces.items()):
        x, y = t
        if not (0 <= x < side and 0 <= y < side):
            continue
        if kind in keeps.DITCH_KINDS:
            plan.tiles[y][x] = WATER if kind == keeps.MOAT else CLAY
            continue
        plan.walls.append((x, y, "stone" if kind == keeps.STONE else kind))

    if inside:
        x0 = min(t[0] for t in inside)
        y0 = min(t[1] for t in inside)
        x1 = max(t[0] for t in inside)
        y1 = max(t[1] for t in inside)
    else:
        # No wall yet, so the precinct is only as big as what has to stand in
        # it -- an open town, which is what an unwalled holding is.
        inner = max(4, int((len(urban) + 2) ** 0.5 + 0.999) + 1)
        x0, y0 = cx - inner // 2, cy - inner // 2
        x1, y1 = x0 + inner - 1, y0 + inner - 1
        inside = [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    plan.precinct = (x0, y0, x1, y1)
    plan.inside = list(inside)

    # --- the precinct and its streets -------------------------------------
    yard = set(inside)
    for (x, y) in inside:
        plan.tiles[y][x] = YARD
    mid = (x0 + x1) // 2
    for (x, y) in inside:
        if x == mid or y == (y0 + y1) // 2:
            plan.tiles[y][x] = ROAD
    # The road out of the gate, to the rest of the march. It leaves by the
    # gate you put there rather than by the south side on principle.
    gates = [g for g in castle.gates if 0 <= g[0] < side and 0 <= g[1] < side]
    door = min(gates, key=lambda g: (-g[1], abs(g[0] - mid))) if gates \
        else (mid, y1 + 1)
    gx, gy = door
    plan.door = (gx, gy)
    step = (0, 1) if gy >= cy else (0, -1)
    if abs(gx - cx) > abs(gy - cy):
        step = (1, 0) if gx >= cx else (-1, 0)
    x, y = gx + step[0], gy + step[1]
    while 0 <= x < side and 0 <= y < side:
        if (x, y) not in castle.pieces:
            plan.tiles[y][x] = ROAD
        x, y = x + step[0], y + step[1]
    # And a lane from the gate to the cross inside, so the way in goes
    # somewhere.
    for i in range(1, 6):
        t = (gx - step[0] * i, gy - step[1] * i)
        if t in yard:
            plan.tiles[t[1]][t[0]] = ROAD

    # --- the country ------------------------------------------------------
    # Each kind of ground gets a quarter of the compass, so a town always has
    # its wood on the same side and you can learn the shape of the place.
    # Marsh gets the low corner, because water goes downhill and because a
    # fen you can see is the only way the dial means anything. Nothing will
    # stand on it: see cartography.py on why undrained fen is land you own
    # and cannot work.
    quarters = {FIELD: (0, -1), FOREST: (-1, 0), HILL: (1, 0), CLAY: (0, 1),
                MARSH: (-1, 1)}
    counts = {FIELD: settlement.terrain.get("fertile", 0),
              FOREST: settlement.terrain.get("forest", 0),
              HILL: settlement.terrain.get("hills", 0),
              CLAY: settlement.terrain.get("clay", 0),
              MARSH: settlement.terrain.get("marsh", 0)}
    for kind, (dx, dy) in quarters.items():
        want = max(0, counts.get(kind, 0)) * 3
        laid = 0
        for step in range(2, side):
            for spread in range(-step, step + 1):
                if laid >= want:
                    break
                x = cx + dx * step + (spread if dx == 0 else 0)
                y = cy + dy * step + (spread if dy == 0 else 0)
                if not (0 <= x < side and 0 <= y < side):
                    continue
                if plan.tiles[y][x] != GRASS or (x, y) in castle.pieces:
                    continue      # the precinct, its roads and its ditch are laid
                plan.tiles[y][x] = kind
                laid += 1
            if laid >= want:
                break
    if settlement.terrain.get("coast", 0):
        for y in range(side):
            for x in range(side - 3, side):
                plan.tiles[y][x] = WATER

    # --- what stands where ------------------------------------------------
    def _place(b, x: int, y: int) -> None:
        plan.buildings.append(Placed(
            uid=b.uid, key=b.key, x=x, y=y, category=b.spec.category,
            terrain=b.spec.terrain, complete=b.complete,
            running=b.worked, idle=b.complete and not b.worked,
            enabled=b.enabled,
            burning=settlement.fires.burning(b.uid), name=b.spec.name,
            head=b.head))

    # The keep stands deepest in: the tile a besieger has to cross the most
    # wall to reach, and the furthest from the gate among those. A hall on
    # the gate side of its own castle is a hall somebody walks into.
    hall = next((b for b in standing if b.key == "keep"), None)
    taken: set = set()
    if hall is not None:
        seat = max(plan.inside,
                   key=lambda t: (abs(t[0] - door[0]) + abs(t[1] - door[1]),
                                  -t[1], -t[0])) if plan.inside else (mid, y0)
        _place(hall, seat[0], seat[1])
        taken = {seat}
    plots = [(x, y) for (x, y) in plan.inside
             if plan.tiles[y][x] == YARD and (x, y) not in taken]
    plots.sort(key=lambda p: (abs(p[0] - mid) + abs(p[1] - y0), p[1], p[0]))
    # And what will not fit stands outside the wall, because a town does not
    # stop growing when the wall stops. This is the whole cost of drawing a
    # small castle, and it is a real one: see `raid` -- what is outside is
    # what gets burned.
    spill = [(x, y) for y in range(side) for x in range(side)
             if plan.tiles[y][x] in (GRASS, YARD) and (x, y) not in set(plan.inside)
             and (x, y) not in castle.pieces]
    spill.sort(key=lambda p: (abs(p[0] - cx) + abs(p[1] - cy), p[1], p[0]))
    for b, (x, y) in zip(urban, plots + spill):
        _place(b, x, y)

    # Each wall building on a yard of the kind it bought, spread along it, so
    # that clicking a length of wall reaches the thing that paid for it.
    for kind in (keeps.STONE, keeps.TIMBER, keeps.TOWER, keeps.GATE,
                 keeps.MOAT, keeps.PITCH, keeps.PITS):
        want = [b for b in ramparts if keeps.YARDS.get(b.key, ("",))[0] == kind]
        line = castle.of_kind(kind)
        if not want:
            continue
        if not line:
            # Paid for and nowhere laid. It stands by the gate waiting for
            # somebody to say where it goes -- never dropped from the picture.
            line = [door]
        for i, b in enumerate(want):
            t = line[(i * max(1, len(line) // max(1, len(want)))) % len(line)]
            _place(b, t[0], t[1])

    # Country buildings stand on their own ground, nearest the town first.
    used: set = set()
    for b in country:
        want = GROUND_FOR.get(b.spec.terrain, GRASS)
        best, best_d = None, 1e9
        for y in range(side):
            for x in range(side):
                if (x, y) in used or (x, y) in castle.pieces:
                    continue
                if plan.tiles[y][x] != want:
                    continue
                d = abs(x - cx) + abs(y - cy)
                if d < best_d:
                    best, best_d = (x, y), d
        if best is None:
            # Its ground is not on this map -- a quarry on a hill the town does
            # not have. Stand it on open country rather than dropping it, so
            # the picture never quietly loses a building the town really has.
            for y in range(side):
                for x in range(side):
                    if ((x, y) not in used and plan.tiles[y][x] == GRASS
                            and (x, y) not in castle.pieces):
                        best = (x, y)
                        break
                if best:
                    break
        if best is not None:
            used.add(best)
            _place(b, best[0], best[1])

    # --- what is being carried, and where from -----------------------------
    # A load only exists where something running wants what something running
    # makes. Nothing decorative crosses this street.
    placed = {b.uid: b for b in plan.buildings}
    makers: Dict[str, List[int]] = {}
    for b in standing:
        if not (b.complete and b.enabled) or b.uid not in placed:
            continue
        for good_key in b.spec.outputs:
            makers.setdefault(good_key, []).append(b.uid)
    seen_pairs = set()
    for b in standing:
        if not (b.complete and b.enabled and b.throughput > 0.05):
            continue
        if b.uid not in placed:
            continue
        for good_key in b.spec.inputs:
            for src in makers.get(good_key, []):
                if src == b.uid or (src, b.uid, good_key) in seen_pairs:
                    continue
                seen_pairs.add((src, b.uid, good_key))
                plan.hauls.append(Haul(frm=src, to=b.uid, good=good_key,
                                       path=_walk(plan, placed[src], placed[b.uid])))
                break
    # A town with forty chains running is a town you cannot see. Keep the
    # nearest loads, which are the ones that read as a street rather than a
    # diagram.
    plan.hauls.sort(key=lambda h: abs(placed[h.frm].x - placed[h.to].x)
                    + abs(placed[h.frm].y - placed[h.to].y))
    del plan.hauls[14:]

    # --- people, each standing for fourteen of them ------------------------
    #
    # Not dots on a road. Every figure is a sample of the real population at
    # SOULS_PER_FIGURE to one, and every one of them is doing what the town is
    # actually doing today: walking from a roof to the shed that is staffed,
    # or standing in the street because nothing is. A town with half its sheds
    # idle has half its people in the square, without anybody drawing that as
    # a special case.
    roofs = [b for b in plan.buildings
             if b.key in ("cottage", "hovel", "townhouse")]
    working = [b for b in plan.buildings if b.running
               and BUILDINGS.get(b.key) and BUILDINGS[b.key].jobs]
    # The sheds you put hands at by name come first, so the man you sent is
    # the man you see. A small town has few figures to go round, and the
    # one place they must not be missing from is the shed you just pointed at.
    pins = getattr(settlement, "pins", {}) or {}
    working.sort(key=lambda b: 0 if b.uid in pins else 1)
    roads = [(x, y) for y in range(side) for x in range(side)
             if plan.tiles[y][x] == ROAD]
    want = int(min(MOST_FIGURES,
                   max(0.0, settlement.population) / SOULS_PER_FIGURE))
    # What share of the figures are going somewhere is the share of the
    # *workforce* that has a job, not the share of the population -- most of
    # a town is children and the old, and dividing by the whole of it put two
    # people on the road in a town with every shed running.
    busy = settlement.employed / max(1.0, float(settlement.workforce))
    at_work = int(round(want * max(0.0, min(1.0, busy))))

    # One figure to a working shed, standing at it, doing its work.
    #
    # They used to be given a route from a roof to a shed and left to walk it
    # back and forth for ever, which is a dot sliding along a road: at any
    # moment almost nobody was *at* the thing they worked. A town reads as
    # worked when the yards have somebody in them -- the man is at the anvil
    # and the woman is in the wheat, and you can tell which is which from
    # across the precinct by what their arms are doing.
    #
    # Sheds first, in the order they were laid out, so the same shed keeps
    # the same figure from frame to frame and clicking one twice asks about
    # the same person.
    for i in range(min(at_work, len(working))):
        shed = working[i]
        posture, doing = TRADES.get(shed.key, DEFAULT_TRADE)
        roof = roofs[(i * 5 + 1) % len(roofs)] if roofs else None
        # Beside the door rather than on the roof, and on a side that
        # depends on the shed, so a row of them is not a row of clones.
        off = ((i % 3) - 1) * 0.42, 0.62 + (i % 2) * 0.18
        plan.folk.append(Walker(
            x=shed.x + off[0], y=shed.y + off[1], kind="worker",
            at=doing, trade=posture, work=shed.uid,
            home=roof.uid if roof else -1, souls=SOULS_PER_FIGURE))

    # And the rest on the road between a roof and a shed, because a town
    # where nobody is ever going anywhere is a diorama.
    walking = max(0, at_work - len(working))
    for i in range(walking):
        if not (roofs and working):
            break
        home_roof = roofs[(i * 5 + 1) % len(roofs)]
        shed = working[(i * 3) % len(working)]
        route = _walk(plan, home_roof, shed)
        posture, doing = TRADES.get(shed.key, DEFAULT_TRADE)
        plan.folk.append(Walker(x=route[0][0], y=route[0][1], kind="worker",
                                path=route, at=f"on the way -- {doing}",
                                trade="walk", home=home_roof.uid,
                                work=shed.uid, souls=SOULS_PER_FIGURE))

    # --- the idle, gathered where a town gathers ---------------------------
    #
    # Stronghold's answer to "where are my spare hands" is that they are all
    # in one place. Its peasants stand round the campfire until a building
    # takes one, so the crowd by the fire *is* the readout -- there is no
    # idle-villager button in that game because there is nothing to hunt
    # for. Scattering them along the roads, which is what this did, made
    # the same fact invisible: a town with sixty spare hands looked like a
    # town with a slightly busier street.
    #
    # The market square is this game's campfire. Failing one, the chapel or
    # the inn -- somewhere people would actually stand about -- and failing
    # all three they are back on the roads, because a town with none of
    # those has nowhere to gather and that is the honest picture of it.
    gather = next((b for b in plan.buildings
                   if b.key == "market" and b.complete), None)
    for fallback in ("chapel", "inn"):
        if gather is None:
            gather = next((b for b in plan.buildings
                           if b.key == fallback and b.complete), None)
    idle_folk = max(0, want - at_work)
    for i in range(idle_folk):
        roof = roofs[(i * 5 + 1) % len(roofs)] if roofs else None
        if gather is not None:
            # A crowd, not a queue: the golden angle keeps them from
            # falling into rings you can count, and the ring grows as the
            # square fills, so sixty idle hands look like sixty.
            # In front of it, never on it and never round the back: a
            # fan that widens as the square fills, so sixty idle hands
            # look like sixty rather than like a ring you can count.
            ring = 1 + i // 7
            frac = ((i * 0.6180339887) % 1.0)
            ang = math.pi * (0.13 + 0.74 * frac)
            rad = 0.62 + 0.5 * ring
            x = gather.x + math.cos(ang) * rad
            y = gather.y + 0.62 + math.sin(ang) * rad * 0.7
            where = f"waiting at the {gather.name} for somebody to want them"
        elif roads:
            x, y = roads[(i * 7 + 3) % len(roads)]
            where = "nothing to do"
        else:
            break
        # Idle folk sleep somewhere too, and being able to say where is
        # half of what makes them people rather than filler.
        plan.folk.append(Walker(
            x=x + rng.random() * 0.34 - 0.17, y=y + rng.random() * 0.34 - 0.17,
            kind="idle", at=where, trade="idle",
            souls=SOULS_PER_FIGURE, home=roof.uid if roof else -1))

    # --- the beasts in the yards -------------------------------------------
    #
    # Put down after the people, so a herder already exists to put them near:
    # a flock scattered over its field reads as a flock, but a flock drawn
    # round the shepherd reads as a flock being *kept*, which is the thing
    # worth seeing. An idle pasture gets neither -- no herder and a thin
    # scatter -- and a raided one gets nothing at all.
    herders = {f.work: f for f in plan.folk if f.trade == "herd"}
    # Every tile a roof is standing on. A beast may stand in its own yard
    # but not in anybody else's, which is checked per yard below.
    taken = {(b.x, b.y) for b in plan.buildings}
    for shed in plan.buildings:
        kind = HERDS.get(shed.key)
        if kind is None or not shed.complete:
            continue
        # The real head, rounded to whole animals, because half a sheep is
        # not a thing you can draw. A yard with a tenth of a flock left
        # shows one beast standing in an empty field, which is the picture
        # a raid ought to leave behind it.
        head = int(round(max(0.0, shed.head))) if shed.head >= 0 \
            else C.HERD_FULL.get(shed.key, 0)
        if head <= 0:
            continue
        keeper = herders.get(shed.uid)
        # The ground a beast may stand on: near its own yard, and not under
        # anybody's roof. A pasture is one tile in a town this dense, so the
        # flock lives in the gardens and alleys round it -- which is what a
        # town flock did. Nearest first, so a small herd is tight to the
        # fold and a big one spills down the lane.
        near = []
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                gx, gy = shed.x + dx, shed.y + dy
                if not (0 <= gx < side and 0 <= gy < side):
                    continue
                if (gx, gy) in taken and (gx, gy) != (shed.x, shed.y):
                    continue
                if plan.tiles[gy][gx] in (WATER, ROAD):
                    continue            # they are not standing in the beck
                near.append((abs(dx) + abs(dy), gx, gy))
        near.sort()
        if not near:
            near = [(0, shed.x, shed.y)]
        # Round the herder where there is one: a flock drawn round its
        # shepherd reads as a flock being *kept*, and one scattered over the
        # same ground reads as one nobody is watching. That difference is
        # the whole reason they are worth drawing.
        if keeper is not None:
            near.sort(key=lambda t: abs(t[1] - keeper.x) + abs(t[2] - keeper.y))
        for n in range(head):
            _d, gx, gy = near[n % len(near)]
            wobble = 0.30 if keeper else 0.44
            plan.beasts.append(Beast(
                x=gx + (rng.random() - 0.5) * 2 * wobble,
                y=gy + (rng.random() - 0.5) * 2 * wobble,
                kind=kind, at=shed.uid, seed=(shed.uid * 31 + n * 7) % 97))

    # --- and the watch, standing on the wall they are actually holding -----
    #
    # The other half of the same idea, and the one that pays for itself: the
    # garrison is drawn along the castle you drew, so a wall you enclosed more
    # ground with than you have men for *looks* thinly held. There is no
    # separate warning, no icon and no number: you can see it.
    line = castle.of_kind(keeps.TOWER, keeps.GATE) + castle.of_kind(
        keeps.STONE, keeps.TIMBER)
    garrison = sum(settlement.units.values())
    watch = int(min(len(line), garrison / MEN_PER_FIGURE))
    if watch and line:
        step = max(1, len(line) // watch)
        for i in range(watch):
            wx, wy = line[(i * step) % len(line)]
            plan.folk.append(Walker(x=float(wx), y=float(wy), kind="watch",
                                    at="on the wall", trade="guard",
                                    souls=MEN_PER_FIGURE))

    # --- and the handful who are somebody ---------------------------------
    #
    # Everyone above is a sample. These are not: they have a name, an age, a
    # skill that is going up, and a job you gave them. Standing them at the
    # building their post attaches to means the picture shows where you sent
    # them, and an empty works is an empty works.
    by_key: Dict[str, "Placed"] = {}
    for b in plan.buildings:
        by_key.setdefault(b.key, b)
    for off in (officers or []):
        where = None
        for key in POST_WHERE.get(off.get("post", ""), ()):  # first that stands
            if key in by_key:
                where = by_key[key]
                break
        if where is None:
            continue
        # In front of the door, not behind it. The scene is painted back to
        # front on x+y, so a figure placed at a lower y than its building is
        # a figure the building paints over -- recorded as a click target and
        # invisible, which is the worst of both.
        plan.folk.append(Walker(x=float(where.x), y=float(where.y) + 0.62,
                                kind="kin", at=where.name, work=where.uid,
                                souls=1, who=off.get("name", ""),
                                trade="talk", post=off.get("post", "")))
    return plan
