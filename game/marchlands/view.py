"""The town as a plan: the one screen this game was missing.

Everything drawn here is read from the settlement itself -- the fields are the
fields you cleared, and a workshop standing dark is a workshop that had no
hands or no inputs today. It is a picture of the state, not an illustration
of it.

With one deliberate exception, which is worth being plain about: the wall here
is a **schematic** rectangle round the town, not the castle you drew. This
canvas is sixty-eight columns of terminal and the castle is a thirty-yard
square of ground, and squeezing one into the other would produce a picture
that was neither. `castle` draws the real thing at its real shape; this says
how much wall there is and what state it is in. Where the two can disagree --
a workshop your ring does not reach -- the caption under both town screens
says so in a line rather than letting the picture quietly draw it inside.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .buildings import BUILDINGS
from .render import (AMBER, BLOOD, BONE, DEEP, DIM, FAINT, FIELD, FLAME, GOLD,
                     IRON, LEAF, PLUM, RUST, SEA, SLATE, STONE, c, pad)

CANVAS_W = 68
CANVAS_H = 16

# glyph, colour -- one cell each, coloured by what it is rather than what it does
GLYPHS: Dict[str, Tuple[str, int]] = {
    # the castle
    "keep": ("▣", BONE), "palisade": ("╫", RUST), "stone_wall": ("╬", STONE),
    "gatehouse": ("∩", BONE), "wall_tower": ("♦", BONE),
    "barracks": ("x", IRON), "siege_yard": ("X", IRON),
    # works on the wall line
    "moat": ("≈", SEA), "pitch_ditch": ("~", FLAME),
    "kill_pit": ("^", IRON), "oil_pot": ("◓", FLAME),
    # roofs
    "hovel": ("⌂", RUST), "cottage": ("⌂", AMBER), "townhouse": ("⌂", GOLD),
    # the land
    "farm": ("≡", FIELD), "orchard": ("♠", LEAF), "hop_farm": ("╽", LEAF),
    "sheep_farm": ("ᵕ", BONE), "dairy": ("ᴗ", BONE), "saltworks": ("▒", SEA),
    "woodcutter": ("♣", DEEP), "charcoal_burner": ("▲", IRON),
    "quarry": ("△", STONE), "iron_mine": ("◆", RUST), "clay_pit": ("●", RUST),
    # the workshops
    "mill": ("✻", GOLD), "bakery": ("b", AMBER), "brewery": ("a", AMBER),
    "sawmill": ("s", RUST), "smelter": ("S", FLAME), "weaver": ("w", PLUM),
    "kiln": ("k", RUST), "blacksmith": ("h", IRON), "armoury": ("A", IRON),
    "poleturner": ("p", RUST), "fletcher": ("f", DEEP), "armourer": ("P", IRON),
    # civic
    "warehouse": ("▤", RUST), "granary": ("▥", GOLD), "chapel": ("†", BONE),
    "inn": ("∪", AMBER), "market": ("§", GOLD), "trading_post": ("¤", GOLD),
    "stable": ("n", RUST), "guardhouse": ("⌐", IRON), "guildhall": ("¶", PLUM),
    "cathedral": ("╬", BONE), "harbour": ("⚓", SEA), "maypole": ("¡", LEAF),
    "garden": ("❀", LEAF), "stocks": ("†", DIM), "gallows": ("Γ", BLOOD),
}
DEFAULT_GLYPH = ("·", DIM)

# The ground, by season. Sparse on purpose -- ground that is busy argues with
# the buildings standing on it -- and recoloured four times a year, because a
# game about harvests should look different in February.
SEASON_GROUND = {
    "spring": (LEAF, DEEP, ","),
    "summer": (FIELD, DEEP, ","),
    "autumn": (AMBER, RUST, "˛"),
    "winter": (SLATE, SLATE, "˙"),
}


def textures(season: str = "spring") -> Dict[str, List[Tuple[str, int]]]:
    grass, wood, blade = SEASON_GROUND.get(season, SEASON_GROUND["spring"])
    return {
        "field": [(" ", FAINT)] * 7 + [("·", FAINT), (blade, grass)],
        "forest": [(" ", FAINT)] * 4 + [("♠", wood), (" ", FAINT), ("♣", wood),
                                        (" ", FAINT)],
        "hills": [(" ", FAINT)] * 5 + [("▴", SLATE), (" ", FAINT), ("˄", SLATE)],
        "clay": [(" ", FAINT)] * 6 + [("∴", RUST), (" ", FAINT)],
        "water": [("≈", SEA), (" ", SEA), ("~", SEA), (" ", FAINT), ("≈", SEA),
                  (" ", FAINT)],
        "yard": [(" ", FAINT)],
    }


def _scatter(x: int, y: int, n: int) -> int:
    """A stable pseudo-random cell, so the countryside does not shimmer."""
    return (x * 73856093 ^ y * 19349663) % n


class Canvas:
    def __init__(self, w: int = CANVAS_W, h: int = CANVAS_H,
                 season: str = "spring") -> None:
        self.w, self.h = w, h
        self.texture = textures(season)
        self.cells: List[List[Tuple[str, int, bool]]] = [
            [(" ", FAINT, False)] * w for _ in range(h)]

    def put(self, x: int, y: int, glyph: str, colour: int, bold: bool = False) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.cells[y][x] = (glyph, colour, bold)

    def text(self, x: int, y: int, s: str, colour: int, bold: bool = False) -> None:
        for i, ch in enumerate(s):
            self.put(x + i, y, ch, colour, bold)

    def fill(self, x0: int, y0: int, x1: int, y1: int, texture: str) -> None:
        pal = self.texture[texture]
        for y in range(max(0, y0), min(self.h, y1)):
            for x in range(max(0, x0), min(self.w, x1)):
                g, col = pal[_scatter(x, y, len(pal))]
                self.cells[y][x] = (g, col, False)

    def rows(self) -> List[str]:
        out = []
        for row in self.cells:
            line, run, colour, bold = [], [], None, False
            for g, col, bd in row:
                if col != colour or bd != bold:
                    if run:
                        line.append(c("".join(run), colour, bold=bold))
                    run, colour, bold = [], col, bd
                run.append(g)
            if run:
                line.append(c("".join(run), colour, bold=bold))
            out.append("".join(line).rstrip())
        return out


def _activity(b) -> Tuple[bool, int]:
    """How brightly a building should burn: working, idle, or still going up."""
    if not b.complete:
        return False, FAINT
    if not b.enabled:
        return False, FAINT
    spec = b.spec
    if spec.outputs or spec.inputs:
        if b.throughput > 0.6:
            return True, 0
        if b.throughput > 0.05:
            return False, 0
        return False, DIM
    return False, 0


def townscape(settlement, mods=None, season: str = "spring",
              besieged: bool = False) -> List[str]:
    """Draw the settlement: its land, its walls, and everything standing."""
    cv = Canvas(season=season)
    t = settlement.terrain
    urban = [b for b in settlement.buildings if b.spec.terrain == "urban"]

    # --- the walled town, centred -------------------------------------------
    # +1 for the keep's own cell: a plan that silently drops the last workshop
    # is a plan you cannot trust.
    cells = len(urban) + 1
    cols = max(7, min(12, (cells + 2) // 3))
    inner_h = max(3, -(-cells // cols))                  # rows the town needs
    inner_w = cols * 3 - 1
    x0 = (cv.w - inner_w - 3) // 2
    x1 = x0 + inner_w + 2
    y0 = (cv.h - inner_h - 3) // 2
    y1 = y0 + inner_h + 1

    # --- the country round it ------------------------------------------------
    cv.fill(0, 0, cv.w, cv.h, "field")
    if t.get("forest"):
        cv.fill(0, 0, cv.w // 2 - 2, 4, "forest")
    if t.get("hills"):
        cv.fill(cv.w // 2 + 2, 0, cv.w, 4, "hills")
    if t.get("clay"):
        cv.fill(0, cv.h - 3, 18, cv.h, "clay")
    if t.get("coast"):
        cv.fill(cv.w - 26, cv.h - 3, cv.w, cv.h, "water")
    cv.fill(x0 + 1, y0 + 1, x1, y1, "yard")

    # --- the walls -----------------------------------------------------------
    standing = [b for b in settlement.buildings
                if b.spec.terrain == "rampart" and b.complete]
    stone = any(b.key in ("stone_wall", "gatehouse", "wall_tower") for b in standing)
    towers = [b for b in standing if b.key == "wall_tower"]
    gate = any(b.key == "gatehouse" for b in standing)
    keep = any(b.key == "keep" for b in standing)

    if standing:
        top = settlement.wall_max(mods) if mods else settlement.wall_max()
        frac = settlement.wall_hp / max(1.0, top)
        wall_colour = STONE if stone else RUST
        if besieged or frac < 0.5:
            wall_colour = BLOOD if frac < 0.35 else AMBER
        h, v = ("═", "║") if stone else ("─", "│")
        corners = ("╔", "╗", "╚", "╝") if stone else ("┌", "┐", "└", "┘")
        for x in range(x0 + 1, x1):
            cv.put(x, y0, h, wall_colour)
            cv.put(x, y1, h, wall_colour)
        for y in range(y0 + 1, y1):
            cv.put(x0, y, v, wall_colour)
            cv.put(x1, y, v, wall_colour)
        for (cx, cy), ch in zip(((x0, y0), (x1, y0), (x0, y1), (x1, y1)), corners):
            cv.put(cx, cy, ch, wall_colour)
        for i in range(min(4, len(towers))):
            cx, cy = ((x0, y0), (x1, y0), (x0, y1), (x1, y1))[i]
            cv.put(cx, cy, "♦", BONE, bold=True)
        if gate:
            cv.put((x0 + x1) // 2, y1, "∩", BONE, bold=True)

    # --- where things stand --------------------------------------------------
    spots = {
        "fertile": [(2 + (i % 5) * 3, y0 + (i // 5)) for i in range(30)],
        "forest": [(1 + (i % 9) * 3, (i // 9)) for i in range(27)],
        "hills": [(cv.w // 2 + 3 + (i % 6) * 3, (i // 6)) for i in range(24)],
        "clay": [(1 + (i % 5) * 3, cv.h - 3 + (i // 5)) for i in range(10)],
        "coast": [(cv.w - 24 + (i % 7) * 3, cv.h - 3 + (i // 7)) for i in range(14)],
    }
    used = {k: 0 for k in spots}
    inner = [(x0 + 2 + (i % cols) * 3, y0 + 1 + i // cols)
             for i in range(cols * inner_h)]        # never onto the wall itself

    # Sort the town so it reads as a town: the keep and the yard first, then
    # the workshops, then the roofs -- not the order you happened to build in.
    order = {"castle": 0, "civic": 1, "industry": 2}
    urban.sort(key=lambda b: (order.get(b.spec.category, 3),
                              b.key not in ("hovel", "cottage", "townhouse"),
                              b.key, b.uid))
    if keep:
        cv.put(inner[0][0], inner[0][1], "▣", BONE, bold=True)
    used_inner = 1 if keep else 0

    legend: Dict[str, Tuple[str, int]] = {}
    if keep:
        legend["keep"] = ("▣", BONE)
    land = [b for b in settlement.buildings
            if b.spec.terrain not in ("urban", "rampart")]
    for b in urban + land:
        spec = b.spec
        glyph, colour = GLYPHS.get(b.key, DEFAULT_GLYPH)
        bright, override = _activity(b)
        if override:
            colour = override
        if spec.terrain == "urban":
            if used_inner >= len(inner):
                continue
            x, y = inner[used_inner]
            used_inner += 1
        else:
            pool = spots.get(spec.terrain, spots["fertile"])
            if used[spec.terrain] >= len(pool):
                continue
            x, y = pool[used[spec.terrain]]
            used[spec.terrain] += 1
        cv.put(x, y, glyph if b.complete else "▪", colour,
               bold=bright and b.complete)
        legend.setdefault(b.key, (glyph, colour))

    rows = cv.rows()
    while rows and not rows[-1].strip():
        rows.pop()
    rows.append("")
    rows.extend(_legend(legend))
    return rows


def _legend(entries: Dict[str, Tuple[str, int]], per_row: int = 3) -> List[str]:
    items = [f"{c(g, col)} {BUILDINGS[k].name}" for k, (g, col) in
             sorted(entries.items(), key=lambda kv: BUILDINGS[kv[0]].name)]
    lines: List[str] = []
    row: List[str] = []
    for item in items:
        row.append(pad(item, 21))
        if len(row) == per_row:
            lines.append("  " + "".join(row).rstrip())
            row = []
    if row:
        lines.append("  " + "".join(row).rstrip())
    return lines
