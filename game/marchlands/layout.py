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
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

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
SOULS_PER_FIGURE = 14
MEN_PER_FIGURE = 6


@dataclass
class Walker:
    """One person, standing for fourteen of them, going somewhere real."""
    x: float
    y: float
    kind: str                       # 'worker', 'idle', 'watch'
    path: List[Tuple[float, float]] = field(default_factory=list)
    at: str = ""                    # what they are doing, for the tooltip

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "kind": self.kind, "at": self.at,
                "path": [{"x": x, "y": y} for x, y in self.path]}


@dataclass
class Plan:
    w: int
    h: int
    tiles: List[List[str]]
    buildings: List[Placed] = field(default_factory=list)
    walls: List[Tuple[int, int, str]] = field(default_factory=list)
    folk: List[Walker] = field(default_factory=list)
    hauls: List[Haul] = field(default_factory=list)
    precinct: Tuple[int, int, int, int] = (0, 0, 0, 0)
    #: Every tile the wall actually shuts in, which for anything but a square
    #: is not the same as the precinct's bounding box.
    inside: List[Tuple[int, int]] = field(default_factory=list)

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
                "per_figure": SOULS_PER_FIGURE,
                "per_watch": MEN_PER_FIGURE,
                "hauls": [h.to_dict() for h in self.hauls],
                "precinct": {"x0": x0, "y0": y0, "x1": x1, "y1": y1}}


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


def plan_for(settlement, *, size: int = 0) -> Plan:
    """Lay a settlement out on a square of ground.

    Deterministic: the same town always comes out the same way, so the picture
    does not rearrange itself every time you look at it.
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
    rng = random.Random(hash(settlement.name) & 0xFFFF)
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
            running=b.complete and b.enabled and b.throughput > 0.05,
            idle=b.complete and (not b.enabled or b.throughput <= 0.05),
            burning=settlement.fires.burning(b.uid), name=b.spec.name))

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
    roads = [(x, y) for y in range(side) for x in range(side)
             if plan.tiles[y][x] == ROAD]
    want = int(min(20, max(0.0, settlement.population) / SOULS_PER_FIGURE))
    # What share of the figures are going somewhere is the share of the
    # *workforce* that has a job, not the share of the population -- most of
    # a town is children and the old, and dividing by the whole of it put two
    # people on the road in a town with every shed running.
    busy = settlement.employed / max(1.0, float(settlement.workforce))
    at_work = int(round(want * max(0.0, min(1.0, busy))))
    for i in range(want):
        if i < at_work and roofs and working:
            home_roof = roofs[(i * 5 + 1) % len(roofs)]
            shed = working[(i * 3) % len(working)]
            route = _walk(plan, home_roof, shed)
            plan.folk.append(Walker(x=route[0][0], y=route[0][1], kind="worker",
                                    path=route, at=shed.name))
        elif roads:
            x, y = roads[(i * 7 + 3) % len(roads)]
            plan.folk.append(Walker(
                x=x + rng.random() * 0.6 - 0.3, y=y + rng.random() * 0.6 - 0.3,
                kind="idle", at="nothing to do"))

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
                                    at="on the wall"))
    return plan
