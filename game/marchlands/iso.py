"""The holding in perspective.

A plan tells you what you have. This tries for what Stronghold was actually
selling: a place, seen from the corner, with roofs at different heights, smoke
where the ovens are lit, and people in the street when there are people.

The projection is the usual one -- two screen columns and one screen row per
tile step -- and everything is painted back to front, so a keep in the middle
stands in front of the cottages behind it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .render import (AMBER, BLOOD, BONE, DEEP, DIM, FAINT, FIELD, FLAME, GOLD,
                     IRON, LEAF, PARCH, PLUM, RUST, SEA, SKY, SLATE, STONE, c)

Cell = Tuple[str, int, bool]


class IsoCanvas:
    """A screen you can paint sprites onto, back to front."""

    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.cells: List[List[Optional[Cell]]] = [[None] * w for _ in range(h)]

    def put(self, x: int, y: int, glyph: str, colour: int, bold: bool = False) -> None:
        if 0 <= x < self.w and 0 <= y < self.h and glyph != " ":
            self.cells[y][x] = (glyph, colour, bold)

    def wash(self, x: int, y: int, glyph: str, colour: int) -> None:
        """Paint only where nothing has been painted yet (sky, ground)."""
        if 0 <= x < self.w and 0 <= y < self.h and self.cells[y][x] is None:
            self.cells[y][x] = (glyph, colour, False)

    def blit(self, x: int, y: int, rows: Sequence[Tuple[str, int]],
             bold: bool = False) -> None:
        """Draw a sprite with its last row sitting on (x, y)."""
        top = y - len(rows) + 1
        for dy, (line, colour) in enumerate(rows):
            start = x - len(line) // 2
            for dx, ch in enumerate(line):
                self.put(start + dx, top + dy, ch, colour, bold)

    def rows(self) -> List[str]:
        out = []
        for row in self.cells:
            line, run, colour, bold = [], [], None, False
            for cell in row:
                g, col, bd = cell if cell else (" ", FAINT, False)
                if col != colour or bd != bold:
                    if run:
                        line.append(c("".join(run), colour, bold=bold))
                    run, colour, bold = [], col, bd
                run.append(g)
            if run:
                line.append(c("".join(run), colour, bold=bold))
            out.append("".join(line).rstrip())
        return out


# --- sprites ---------------------------------------------------------------
# Two cells wide, so that at a three-column tile pitch there is always a gap of
# daylight between neighbours. Two tones: something that reads as a roof over
# something that reads as a wall. The keep and the cathedral get three, because
# they are meant to dominate.
def _hut(roof: int, wall: int = RUST) -> List[Tuple[str, int]]:
    """A dwelling: pitched roof, one storey."""
    return [("▟▙", roof), ("██", wall)]


def _shed(roof: int, wall: int = RUST, body: str = "▓▓") -> List[Tuple[str, int]]:
    """A workshop: shallow roof, working front."""
    return [("▄▄", roof), (body, wall)]


def _hall(roof: int, wall: int = STONE) -> List[Tuple[str, int]]:
    """Something civic: two storeys and a ridge."""
    return [("▛▜", roof), ("██", wall), ("██", wall)]


def _store(roof: int, wall: int = RUST) -> List[Tuple[str, int]]:
    """A store: flat roof, banded side."""
    return [("▬▬", roof), ("▒▒", wall)]


def _tower(colour: int = BONE) -> List[Tuple[str, int]]:
    return [("▛▜", colour), ("██", SLATE), ("██", SLATE)]


SPRITES: Dict[str, List[Tuple[str, int]]] = {
    # the castle: the tallest things on the skyline
    "keep": [("▄▀▄", BONE), ("███", BONE), ("███", SLATE), ("███", SLATE)],
    "wall_tower": _tower(),
    "palisade": [("▀▀", RUST), ("██", RUST)],
    "stone_wall": [("▀▀", BONE), ("██", STONE)],
    "gatehouse": [("▄▄", BONE), ("∩∩", SLATE)],
    "cathedral": [(" ✝ ", GOLD), ("▟█▙", BONE), ("███", BONE), ("███", BONE)],
    "barracks": _hall(IRON, SLATE),
    "siege_yard": [("╦╦", RUST), ("██", IRON)],

    # roofs
    "hovel": _hut(RUST, DIM),
    "cottage": _hut(AMBER),
    "townhouse": [("▟▙", GOLD), ("██", RUST), ("██", RUST)],

    # workshops: sheds, and the mill stands over all of them
    "mill": [("✻", BONE), ("██", RUST), ("██", RUST)],
    "bakery": _shed(AMBER),
    "brewery": _shed(AMBER, DEEP),
    "sawmill": _shed(RUST, DIM),
    "smelter": _shed(FLAME, IRON),
    "weaver": _shed(PLUM),
    "kiln": _shed(RUST, IRON),
    "blacksmith": _shed(IRON, IRON),
    "armoury": _shed(IRON, SLATE, "██"),
    "armourer": _shed(IRON, SLATE),
    "poleturner": _shed(RUST, DEEP),
    "fletcher": _shed(DEEP, RUST),

    # stores and civic
    "granary": _store(GOLD),
    "warehouse": _store(RUST, DIM),
    "chapel": [(" †", BONE), ("▛▜", BONE), ("██", BONE)],
    "inn": [("▟▙", AMBER), ("∪∪", RUST)],
    "market": [("▄▄", GOLD), ("§§", PARCH)],
    "trading_post": [("▄▄", GOLD), ("¤¤", RUST)],
    "guildhall": _hall(PLUM, BONE),
    "stable": _shed(RUST, DEEP, "██"),
    "guardhouse": _hut(IRON, SLATE),
    "harbour": [("▂▂", RUST), ("⚓≈", SEA)],
    "maypole": [("¡", LEAF), ("│", RUST)],
    "garden": [("❀❀", LEAF), ("▒▒", DEEP)],
    "stocks": [("╥", DIM), ("║", DIM)],
    "gallows": [("┌╖", DIM), ("│║", DIM)],

    # the land: low and wide, so the town stands above it
    "farm": [("≋≋", FIELD)],
    "orchard": [("♠♠", LEAF), ("┃┃", DEEP)],
    "hop_farm": [("╽╽", LEAF)],
    "sheep_farm": [("ᵕᵕ", BONE)],
    "dairy": _hut(BONE, RUST),
    "saltworks": [("▒▒", BONE)],
    "woodcutter": [("♣♣", DEEP), ("┃┃", DEEP)],
    "charcoal_burner": [("▲", IRON), ("▄", DIM)],
    "quarry": [("◣◢", STONE), ("██", SLATE)],
    "iron_mine": [("◣◢", RUST), ("██", IRON)],
    "clay_pit": [("◡◡", RUST)],
}
DEFAULT_SPRITE = [("▪", DIM)]

GROUND = {
    "spring": (("˙", 0), FIELD, LEAF),
    "summer": ((",", 0), FIELD, DEEP),
    "autumn": (("˛", 0), AMBER, RUST),
    "winter": (("˙", 0), SLATE, SLATE),
}
SKY_TONE = {"spring": SKY, "summer": SEA, "autumn": AMBER, "winter": SLATE}


# --- the scene --------------------------------------------------------------
# Three screen columns and one screen row per tile step. Three because the
# sprites are three wide and neighbours on a row must not collide; one because
# a taller pitch turns a town into a scroll.
PX, PY = 3, 1
SKY_ROWS = 3

#: Buildings whose chimneys are worth drawing when they are running.
OVENS = {"bakery", "smelter", "kiln", "brewery", "charcoal_burner", "armourer",
         "blacksmith", "armoury", "inn"}
SMOKE = ("˚", "°", "·", "˙")
FOLK = "îïìí"
SAILS = ("✻", "✼")          # a windmill turning, one frame a day


class Grid:
    """The tile lattice, sized to the town that has to fit on it."""

    def __init__(self, urban: int, land: int) -> None:
        self.side = max(2, min(7, int(max(1, urban) ** 0.5 + 0.999)))
        spread = 2 if land <= 10 else 3
        self.gx = self.side + 2 + spread * 2
        self.gy = self.side + 2 + spread
        self.x0 = (self.gx - self.side) // 2
        self.y0 = (self.gy - self.side) // 2
        self.x1 = self.x0 + self.side - 1
        self.y1 = self.y0 + self.side - 1
        self.ox = (self.gy - 1) * PX + 1
        self.w = (self.gx + self.gy) * PX
        self.h = SKY_ROWS + (self.gx + self.gy) * PY + 2

    def screen(self, tx: int, ty: int) -> Tuple[int, int]:
        return self.ox + (tx - ty) * PX, SKY_ROWS + (tx + ty) * PY


def _land_tiles(g: "Grid") -> Dict[str, List[Tuple[int, int]]]:
    """Where each kind of country sits around the walls."""
    out: Dict[str, List[Tuple[int, int]]] = {
        "fertile": [], "forest": [], "hills": [], "clay": [], "coast": []}
    for ty in range(g.gy):
        for tx in range(g.gx):
            if g.x0 - 1 <= tx <= g.x1 + 1 and g.y0 - 1 <= ty <= g.y1 + 1:
                continue
            if ty < g.y0 - 1 and tx < g.x0:
                out["forest"].append((tx, ty))
            elif ty < g.y0 - 1:
                out["hills"].append((tx, ty))
            elif tx > g.x1 + 1 and ty > g.y0:
                out["coast"].append((tx, ty))
            elif ty > g.y1 + 1 and tx < g.x0:
                out["clay"].append((tx, ty))
            else:
                out["fertile"].append((tx, ty))
    for key in out:
        out[key].sort(key=lambda t: (t[0] + t[1], t[0]))
    return out


def scene(settlement, mods=None, season: str = "spring", day: int = 0,
          besieged: bool = False) -> List[str]:
    """Draw the holding from the corner, back to front."""
    urban = [b for b in settlement.buildings if b.spec.terrain == "urban"]
    outside = [b for b in settlement.buildings
               if b.spec.terrain not in ("urban", "rampart")]
    g = Grid(len(urban) + 1, len(outside))
    cv = IsoCanvas(w=g.w, h=g.h)
    blade, grass, wood = GROUND.get(season, GROUND["spring"])
    terrain = settlement.terrain

    # --- sky ----------------------------------------------------------------
    for y in range(SKY_ROWS - 1):
        for x in range(cv.w):
            cv.wash(x, y, "·" if (x * 7 + y * 13) % 29 == 0 else " ",
                    SKY_TONE.get(season, SKY))
    cv.put(cv.w - 5, 0, "☼" if season in ("summer", "spring") else "☁",
           GOLD if season in ("summer", "spring") else SLATE, bold=True)

    # --- ground -------------------------------------------------------------
    land = _land_tiles(g)
    kind_of = {t: kind for kind, tiles in land.items() for t in tiles}
    for ty in range(g.gy):
        for tx in range(g.gx):
            sx, sy = g.screen(tx, ty)
            kind = kind_of.get((tx, ty), "yard")
            if kind == "coast" and terrain.get("coast"):
                for dx, ch in enumerate("≈~≈"):
                    cv.wash(sx - 1 + dx, sy, ch, SEA)
                continue
            # Inside the wall the ground is trodden, not grown on: streets
            # read as streets instead of scrub showing between the roofs.
            inside = (g.x0 - 1 <= tx <= g.x1 + 1 and g.y0 - 1 <= ty <= g.y1 + 1)
            colour = {"fertile": grass, "forest": wood, "hills": SLATE,
                      "clay": RUST}.get(kind, grass)
            if inside:
                colour, mark, every = DIM, "·", 17
            else:
                mark, every = blade[0], 7
            for dx in (-1, 0, 1):
                seed = ((tx * 73856093) ^ (ty * 19349663) ^ ((dx + 2) * 83492791))
                cv.wash(sx + dx, sy, mark if seed % every == 0 else " ", colour)

    # --- the wall -----------------------------------------------------------
    standing = [b for b in settlement.buildings
                if b.spec.terrain == "rampart" and b.complete]
    stone = any(b.key in ("stone_wall", "gatehouse", "wall_tower") for b in standing)
    towers = sum(1 for b in standing if b.key == "wall_tower")
    gate = any(b.key == "gatehouse" for b in standing)
    keep = any(b.key == "keep" for b in standing)
    if standing:
        top = settlement.wall_max(mods) if mods else settlement.wall_max()
        frac = settlement.wall_hp / max(1.0, top)
        face = STONE if stone else RUST
        cap = BONE if stone else RUST
        if besieged or frac < 0.6:
            face = cap = BLOOD if frac < 0.35 else AMBER
        ring = ([(tx, g.y0 - 1) for tx in range(g.x0 - 1, g.x1 + 2)]
                + [(g.x1 + 1, ty) for ty in range(g.y0, g.y1 + 2)]
                + [(tx, g.y1 + 1) for tx in range(g.x1, g.x0 - 2, -1)]
                + [(g.x0 - 1, ty) for ty in range(g.y1, g.y0 - 1, -1)])
        corners = {(g.x0 - 1, g.y0 - 1), (g.x1 + 1, g.y0 - 1),
                   (g.x1 + 1, g.y1 + 1), (g.x0 - 1, g.y1 + 1)}
        gate_tile = (g.x1 + 1, g.y1) if gate else None
        placed_towers = 0
        for tx, ty in sorted(set(ring), key=lambda t: (t[0] + t[1], t[0])):
            sx, sy = g.screen(tx, ty)
            if (tx, ty) in corners and placed_towers < towers:
                cv.blit(sx, sy, _tower(cap))
                placed_towers += 1
            elif (tx, ty) == gate_tile:
                cv.blit(sx, sy, [("▄▄▄", cap), ("█∩█", face)], bold=True)
            elif ty == g.y1 + 1 or tx == g.x1 + 1:
                # The near walls are drawn low, so you can see over them into
                # your own town -- the oldest trick in isometric drawing.
                cv.blit(sx, sy, [("▀▀", cap), ("██", face)])
            else:
                cv.blit(sx, sy, [("▀▀", cap), ("██", face), ("██", face)])

    # --- everything standing, back to front ---------------------------------
    yard = [(tx, ty) for ty in range(g.y0, g.y1 + 1)
            for tx in range(g.x0, g.x1 + 1)]
    yard.sort(key=lambda t: (t[0] + t[1], t[0]))
    order = {"castle": 0, "civic": 1, "industry": 2}
    urban.sort(key=lambda b: (order.get(b.spec.category, 3), b.key, b.uid))
    if keep:
        urban.insert(0, next(b for b in settlement.buildings if b.key == "keep"))

    placed: List[Tuple[int, int, object]] = []
    for i, b in enumerate(urban[:len(yard)]):
        placed.append((*yard[i], b))
    on_streets = {(t[0], t[1]) for t in placed}
    used = {k: 0 for k in land}
    for b in outside:
        pool = land.get(b.spec.terrain) or land["fertile"]
        if used.get(b.spec.terrain, 0) >= len(pool):
            pool, key = land["fertile"], "fertile"
            if used["fertile"] >= len(pool):
                continue
        else:
            key = b.spec.terrain
        tx, ty = pool[used[key]]
        used[key] += 1
        placed.append((tx, ty, b))

    legend: Dict[str, Tuple[str, int]] = {}
    for tx, ty, b in sorted(placed, key=lambda p: (p[0] + p[1], p[0])):
        sx, sy = g.screen(tx, ty)
        sprite = SPRITES.get(b.key, DEFAULT_SPRITE)
        if not b.complete:
            cv.blit(sx, sy, [("▄▄▄", DIM)])
            continue
        idle = (b.spec.inputs or b.spec.outputs) and b.throughput <= 0.05
        if not b.enabled:
            sprite = [(row, DIM) for row, _ in sprite]
        cv.blit(sx, sy, sprite, bold=not idle and b.enabled)
        if b.key == "mill" and b.enabled and not idle:
            cv.put(sx, sy - len(sprite) + 1, SAILS[(day + tx) % len(SAILS)],
                   BONE, bold=True)
        if b.key in OVENS and b.enabled and not idle:
            cv.put(sx, sy - len(sprite),
                   SMOKE[(day + tx * 3 + ty) % len(SMOKE)],
                   BONE if season == "winter" else DIM)
        legend.setdefault(b.key, (sprite[-1][0][:1], sprite[-1][1]))

    # --- the people ---------------------------------------------------------
    streets = [t for t in yard if t not in on_streets]
    folk = int(min(len(streets), settlement.population / 30.0))
    for i in range(folk):
        tx, ty = streets[(day // 4 + i * 3) % len(streets)] if streets else (0, 0)
        sx, sy = g.screen(tx, ty)
        cv.put(sx + (i % 3) - 1, sy, FOLK[(day + i) % len(FOLK)], PARCH)
    if standing:
        for i in range(min(5, settlement.soldiers // 8)):
            tx = g.x0 + (i * 2) % max(1, g.side)
            sx, sy = g.screen(tx, g.y1 + 1)
            cv.put(sx, sy - 2, "Î", IRON, bold=True)

    rows = cv.rows()
    while rows and not rows[-1].strip():
        rows.pop()
    return rows
