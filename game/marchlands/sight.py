"""What of the march you have seen, and what you can see today.

The map used to be drawn whole from the first morning -- every town, every
road, every price -- and the fog covered only how many men stood behind a
wall. That is a map somebody handed you. This is the map you made: country
nobody of yours has been near is blank parchment, and it fills in round your
towns, your carts and your hosts as they go.

Two things are kept, the way every game with a shroud keeps them:

* ``explored`` -- ground somebody of yours has had in sight at some time.
  It never un-happens, and it is saved.
* ``visible`` -- ground somebody of yours has in sight *today*. Worked out
  again every morning from where they stand, and never saved.

Both are sets of cells on a coarse grid over the map's own coordinates,
rather than sets of towns, so a host marching between two towns clears the
country it crosses and not just the places at either end.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Set, Tuple

#: One cell of the shroud, in map units. The towns stand thirty to ninety
#: apart, so five is fine enough that a circle looks like a circle.
CELL = 5.0

#: How far each kind of eye reaches, in map units. A town sees the country
#: round its walls -- enough to know its neighbours are there, not enough to
#: see the whole march. A host has scouts out ahead and on the flanks. A cart
#: sees the road it is on and a little either side.
TOWN_SIGHT = 58.0
HOST_SIGHT = 46.0
CART_SIGHT = 30.0

Cell = Tuple[int, int]


def cell_of(x: float, y: float) -> Cell:
    return (math.floor(x / CELL), math.floor(y / CELL))


def disc(x: float, y: float, r: float) -> Iterable[Cell]:
    """Every cell whose middle lies within ``r`` of (x, y)."""
    i0, i1 = math.floor((x - r) / CELL), math.floor((x + r) / CELL)
    j0, j1 = math.floor((y - r) / CELL), math.floor((y + r) / CELL)
    r2 = r * r
    for i in range(i0, i1 + 1):
        cx = (i + 0.5) * CELL - x
        for j in range(j0, j1 + 1):
            cy = (j + 0.5) * CELL - y
            if cx * cx + cy * cy <= r2:
                yield (i, j)


@dataclass
class Shroud:
    explored: Set[Cell] = field(default_factory=set)
    visible: Set[Cell] = field(default_factory=set)
    #: A save from before there was a shroud. Its player has been looking at
    #: the whole map for as long as they have played it; taking it away on
    #: load would be a punishment for updating.
    everything: bool = False

    def morning(self) -> None:
        """Forget what was in sight yesterday; keep what was explored."""
        self.visible = set()

    def look(self, x: float, y: float, r: float) -> None:
        for c in disc(x, y, r):
            self.visible.add(c)
            self.explored.add(c)

    def trail(self, a: Tuple[float, float], b: Tuple[float, float],
              r: float) -> None:
        """Explore all along a stretch of road, not just its two ends -- a
        host that covered forty leagues since yesterday saw the whole forty.
        Explored only: what is in sight *now* is round where it stands."""
        steps = max(1, int(math.ceil(math.dist(a, b) / CELL)))
        for k in range(steps + 1):
            t = k / steps
            self.explored.update(disc(a[0] + (b[0] - a[0]) * t,
                                      a[1] + (b[1] - a[1]) * t, r))

    def known(self, x: float, y: float) -> bool:
        return self.everything or cell_of(x, y) in self.explored

    def sees(self, x: float, y: float) -> bool:
        return cell_of(x, y) in self.visible

    # ------------------------------------------------------------- the save
    def to_dict(self) -> dict:
        # Packed as one flat list of i, j pairs: a few hundred cells, and a
        # save is read far more often by a program than by a person.
        flat: List[int] = []
        for i, j in sorted(self.explored):
            flat += (i, j)
        return {"cell": CELL, "explored": flat, "everything": self.everything}

    @classmethod
    def from_dict(cls, d) -> "Shroud":
        if not d:
            return cls(everything=True)
        flat = list(d.get("explored", []))
        s = cls(everything=bool(d.get("everything", False)))
        if float(d.get("cell", CELL)) == CELL:
            s.explored = {(flat[k], flat[k + 1]) for k in range(0, len(flat) - 1, 2)}
        else:
            s.everything = True     # a grid we no longer read: show it all
        return s
