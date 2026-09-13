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

GRASS, FIELD, FOREST, HILL, CLAY, WATER, ROAD, YARD = (
    "grass", "field", "forest", "hill", "clay", "water", "road", "yard")

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


@dataclass
class Plan:
    w: int
    h: int
    tiles: List[List[str]]
    buildings: List[Placed] = field(default_factory=list)
    walls: List[Tuple[int, int, str]] = field(default_factory=list)
    folk: List[Tuple[float, float]] = field(default_factory=list)
    hauls: List[Haul] = field(default_factory=list)
    precinct: Tuple[int, int, int, int] = (0, 0, 0, 0)

    def tile(self, x: int, y: int) -> str:
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.tiles[y][x]
        return GRASS

    def to_dict(self) -> dict:
        x0, y0, x1, y1 = self.precinct
        return {"w": self.w, "h": self.h, "tiles": self.tiles,
                "buildings": [b.to_dict() for b in self.buildings],
                "walls": [{"x": x, "y": y, "kind": k} for x, y, k in self.walls],
                "folk": [{"x": x, "y": y} for x, y in self.folk],
                "hauls": [h.to_dict() for h in self.hauls],
                "precinct": {"x0": x0, "y0": y0, "x1": x1, "y1": y1}}


def _ring(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
    out = [(x, y0) for x in range(x0, x1 + 1)]
    out += [(x1, y) for y in range(y0 + 1, y1 + 1)]
    out += [(x, y1) for x in range(x1 - 1, x0 - 1, -1)]
    out += [(x0, y) for y in range(y1 - 1, y0, -1)]
    return out


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
    urban = [b for b in standing if b.spec.terrain in ("urban", "rampart")
             and b.key != "keep"]
    ramparts = [b for b in standing if b.spec.terrain == "rampart"]
    country = [b for b in standing if b.spec.terrain in
               ("fertile", "forest", "hills", "clay", "coast")]

    # The precinct grows with what has to fit inside it, and the country
    # around it grows with the precinct.
    inner = max(4, int((len(urban) + 2) ** 0.5 + 0.999) + 1)
    side = size or max(16, inner + 12)
    plan = Plan(w=side, h=side, tiles=[[GRASS] * side for _ in range(side)])
    rng = random.Random(hash(settlement.name) & 0xFFFF)

    cx = cy = side // 2
    x0, y0 = cx - inner // 2, cy - inner // 2
    x1, y1 = x0 + inner - 1, y0 + inner - 1
    plan.precinct = (x0, y0, x1, y1)

    # --- the precinct and its streets -------------------------------------
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            plan.tiles[y][x] = YARD
    mid = (x0 + x1) // 2
    for y in range(y0, y1 + 1):
        plan.tiles[y][mid] = ROAD
    for x in range(x0, x1 + 1):
        plan.tiles[(y0 + y1) // 2][x] = ROAD
    # The road out of the gate, south to the rest of the march.
    for y in range(y1 + 1, side):
        plan.tiles[y][mid] = ROAD

    # --- the wall ---------------------------------------------------------
    if ramparts:
        stone = any(b.key in ("stone_wall", "gatehouse", "wall_tower")
                    for b in ramparts if b.complete)
        towers = sum(1 for b in ramparts if b.key == "wall_tower" and b.complete)
        gate = any(b.key == "gatehouse" for b in ramparts if b.complete)
        ring = _ring(x0 - 1, y0 - 1, x1 + 1, y1 + 1)
        corners = {(x0 - 1, y0 - 1), (x1 + 1, y0 - 1),
                   (x1 + 1, y1 + 1), (x0 - 1, y1 + 1)}
        placed_towers = 0
        for (x, y) in ring:
            if (x, y) == (mid, y1 + 1):
                plan.walls.append((x, y, "gate" if gate else "gap"))
                continue
            if (x, y) in corners and placed_towers < towers:
                plan.walls.append((x, y, "tower"))
                placed_towers += 1
                continue
            plan.walls.append((x, y, "stone" if stone else "timber"))
        if any(b.key == "moat" and b.complete for b in ramparts):
            for (x, y) in _ring(x0 - 2, y0 - 2, x1 + 2, y1 + 2):
                if 0 <= x < side and 0 <= y < side and (x, y) != (mid, y1 + 2):
                    plan.tiles[y][x] = WATER

    # --- the country ------------------------------------------------------
    # Each kind of ground gets a quarter of the compass, so a town always has
    # its wood on the same side and you can learn the shape of the place.
    quarters = {FIELD: (0, -1), FOREST: (-1, 0), HILL: (1, 0), CLAY: (0, 1)}
    counts = {FIELD: settlement.terrain.get("fertile", 0),
              FOREST: settlement.terrain.get("forest", 0),
              HILL: settlement.terrain.get("hills", 0),
              CLAY: settlement.terrain.get("clay", 0)}
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
                if plan.tiles[y][x] != GRASS:
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

    keep = next((b for b in standing if b.key == "keep"), None)
    if keep is not None:
        _place(keep, mid, y0)

    plots = [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)
             if plan.tiles[y][x] == YARD and not (x == mid and y == y0)]
    plots.sort(key=lambda p: (abs(p[0] - mid) + abs(p[1] - y0), p[1], p[0]))
    for b, (x, y) in zip(urban, plots):
        _place(b, x, y)

    # Country buildings stand on their own ground, nearest the town first.
    used: set = set()
    for b in country:
        want = GROUND_FOR.get(b.spec.terrain, GRASS)
        best, best_d = None, 1e9
        for y in range(side):
            for x in range(side):
                if (x, y) in used or plan.tiles[y][x] != want:
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
                    if (x, y) not in used and plan.tiles[y][x] == GRASS:
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

    # --- people in the streets --------------------------------------------
    roads = [(x, y) for y in range(side) for x in range(side)
             if plan.tiles[y][x] == ROAD]
    n = int(min(18, max(0, settlement.population) / 18))
    for i in range(n):
        if not roads:
            break
        x, y = roads[(i * 7 + 3) % len(roads)]
        plan.folk.append((x + rng.random() * 0.6 - 0.3,
                          y + rng.random() * 0.6 - 0.3))
    return plan
