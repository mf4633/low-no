"""The castle as a shape you drew, rather than a number you bought.

The single most repeated sentence anybody writes about Stronghold is some
version of *"the satisfaction of seeing your vision come to life"*, and it is
never about the popularity dial. It is about a castle somebody laid out
themselves: this wall here, the towers where they can see each other, the gate
on the side the road comes from, and a long thin stretch at the back that they
knew was thin and gambled on.

This game had the *works* -- moat, pitch ditch, killing pits, towers -- and
they are genuinely the right abstraction of what a castle does to a besieger.
They are also entirely invisible. You bought `stone_wall` and a square ring
appeared around whatever the town happened to be; buying a second one did
nothing to the picture at all. Nobody has ever posted a screenshot of an
abstraction.

So the wall is a drawing now. The economy is untouched -- the same buildings at
the same prices buying the same effects -- but each one you buy is a length of
wall **to lay** rather than a ring that appears, and where you lay it decides
four things the siege actually reads:

* **What is inside.** The town fills the ground the wall encloses. Anything
  that does not fit stands outside it, and outside is where the raiders go.
* **How long it is.** A garrison is a number of men and a wall is a number of
  yards, so the thing that matters is men *per yard*. Enclosing the whole
  valley is how you end up with a wall nobody is standing on.
* **What the towers can see.** A tower covers the wall within reach of an
  arrow from it. Wall that no tower covers is where the ladders go up, and the
  besieger picks the longest such stretch, because so would you.
* **How many times they have to do it.** A second ring inside the first is a
  second siege.

None of that is scored or rated. It is read off the drawing by flood fill and
arithmetic, which is the only honest way: a castle should be good because of
where its towers are, not because a rubric gave it four stars for having them.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

Tile = Tuple[int, int]

#: The ground a castle is drawn on. Fixed, and deliberately so: the old layout
#: grew its grid with the town, which meant every coordinate moved whenever
#: somebody built a bakery. A drawing whose coordinates shift under it is not
#: a drawing.
SIDE = 30
CENTRE: Tile = (SIDE // 2, SIDE // 2)

TIMBER = "timber"
STONE = "stone"
TOWER = "tower"
GATE = "gate"
MOAT = "moat"
PITCH = "pitch"
PITS = "pits"

#: What stands *on* the wall line and therefore stops a man walking through.
WALL_KINDS = (TIMBER, STONE, TOWER, GATE)
#: What is dug in front of it. A ditch does not stop anybody; it costs them.
DITCH_KINDS = (MOAT, PITCH, PITS)
KINDS = WALL_KINDS + DITCH_KINDS

#: How far a tower's fire reaches along the wall, in yards. Three is short
#: enough that a corner tower does not cover the whole side, which is the
#: entire reason tower spacing is a decision.
TOWER_REACH = 3

#: What one of each rampart building is worth on the ground. The prices,
#: build times and effects in buildings.py are untouched -- this is only what
#: the same purchase now gets you to *place*. 28 yards closes an 8x8 ring,
#: which is 36 plots of enclosed ground: about what one wall bought before,
#: so a town that never draws anything is neither richer nor poorer for it.
YARDS = {
    "palisade": (TIMBER, 28),
    "stone_wall": (STONE, 28),
    "wall_tower": (TOWER, 1),
    "gatehouse": (GATE, 1),
    "moat": (MOAT, 14),
    "pitch_ditch": (PITCH, 10),
    "kill_pit": (PITS, 8),
}

#: What a yard of each is worth when the wall is reckoned as hit points, so
#: that a wall's strength is the wall you drew and not a flat number per
#: purchase. Scaled from the building effects: a 28-yard stone run comes to
#: the 420 a `stone_wall` was worth, a timber one to 160.
HP = {TIMBER: 160.0 / 28, STONE: 420.0 / 28, TOWER: 220.0, GATE: 260.0}


def _key(t: Tile) -> str:
    return f"{t[0]},{t[1]}"


def _tile(s: str) -> Tile:
    x, _, y = s.partition(",")
    return int(x), int(y)


def on_map(t: Tile) -> bool:
    return 0 <= t[0] < SIDE and 0 <= t[1] < SIDE


def _near(t: Tile) -> Iterable[Tile]:
    x, y = t
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def _touching(t: Tile) -> Iterable[Tile]:
    x, y = t
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                yield (x + dx, y + dy)


def reach(a: Tile, b: Tile) -> int:
    """Chebyshev. An arrow off a tower does not care about street corners."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@dataclass
class Castle:
    """Everything you have drawn, and nothing about how good it is.

    The judgements all live in the reading functions below, so that they can
    be argued with, tested, and shown to the player as the reasons they are
    rather than as a score.
    """
    pieces: Dict[Tile, str] = field(default_factory=dict)
    #: Whether anybody has taken the pen. Separate from having pieces on the
    #: ground, because pulling your whole wall down is a decision and must not
    #: hand the pen back to the steward, who would cheerfully draw the square
    #: you had just spent an evening replacing.
    own: bool = False

    # ------------------------------------------------------------- drawing
    def lay(self, t: Tile, kind: str) -> None:
        if on_map(t) and kind in KINDS:
            self.pieces[t] = kind

    def clear(self, t: Tile) -> Optional[str]:
        return self.pieces.pop(t, None)

    def at(self, t: Tile) -> str:
        return self.pieces.get(t, "")

    def of_kind(self, *kinds: str) -> List[Tile]:
        return sorted(t for t, k in self.pieces.items() if k in kinds)

    @property
    def wall(self) -> List[Tile]:
        return self.of_kind(*WALL_KINDS)

    @property
    def towers(self) -> List[Tile]:
        return self.of_kind(TOWER)

    @property
    def gates(self) -> List[Tile]:
        return self.of_kind(GATE)

    @property
    def yards(self) -> int:
        """How long the wall is, which is the number the garrison is spread
        over. Towers and gatehouses stand in the line and count in it."""
        return len(self.wall)

    @property
    def drawn(self) -> bool:
        return self.own or bool(self.pieces)

    def spent(self) -> Dict[str, int]:
        """Yards laid, by kind. What `castle` reads back to you."""
        out: Dict[str, int] = {}
        for kind in self.pieces.values():
            out[kind] = out.get(kind, 0) + 1
        return out

    def hit_points(self) -> float:
        return sum(HP.get(k, 0.0) for k in self.pieces.values())

    # -------------------------------------------------------------- saving
    def to_dict(self) -> dict:
        out = {_key(t): k for t, k in sorted(self.pieces.items())}
        if self.own:
            out["own"] = "1"
        return out

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Castle":
        c = cls()
        for s, kind in (d or {}).items():
            if s == "own":
                c.own = True
                continue
            try:
                c.lay(_tile(s), kind)
            except ValueError:
                continue
        return c

    def copy(self) -> "Castle":
        return Castle(dict(self.pieces), own=self.own)


# --------------------------------------------------------------- the reading
#
# Everything below is a question a defender would actually ask, answered off
# the drawing. None of it is stored, because a stored judgement is one that
# goes stale the moment somebody lays a stone.

def outside(castle: Castle) -> Set[Tile]:
    """Every tile a man can walk to from off the edge of the map.

    Four-neighbour, because a besieger cannot squeeze diagonally between two
    stones -- which is what makes a diagonal wall a real wall rather than a
    dotted line, and is worth knowing before you draw one.
    """
    block = set(castle.of_kind(*WALL_KINDS))
    seen: Set[Tile] = set()
    queue: deque = deque()
    for i in range(SIDE):
        for t in ((i, 0), (i, SIDE - 1), (0, i), (SIDE - 1, i)):
            if t not in block and t not in seen:
                seen.add(t)
                queue.append(t)
    while queue:
        for n in _near(queue.popleft()):
            if on_map(n) and n not in seen and n not in block:
                seen.add(n)
                queue.append(n)
    return seen


def enclosed(castle: Castle) -> Set[Tile]:
    """The ground the wall actually shuts in. Not the ground you meant to."""
    if not castle.wall:
        return set()
    free = outside(castle)
    block = set(castle.of_kind(*WALL_KINDS))
    return {(x, y) for y in range(SIDE) for x in range(SIDE)
            if (x, y) not in free and (x, y) not in block}


def shut(castle: Castle, t: Tile = CENTRE) -> bool:
    """Is this tile actually behind the wall? The only question that matters
    about a ring, and the one a count of stones cannot answer."""
    return t in enclosed(castle)


def gaps(castle: Castle) -> List[Tile]:
    """Where the ring is open: tiles with wall on two opposite sides and open
    ground either way through. What `castle` points at when it says the east
    side is not finished."""
    wall = set(castle.wall)
    free = outside(castle)
    out = []
    for t in sorted(free):
        if t in wall:
            continue
        x, y = t
        across = (((x - 1, y) in wall and (x + 1, y) in wall)
                  or ((x, y - 1) in wall and (x, y + 1) in wall))
        if across:
            out.append(t)
    return out


def covered(castle: Castle) -> Set[Tile]:
    """Wall within an arrow's reach of a tower standing on it."""
    towers = castle.towers
    if not towers:
        return set()
    return {w for w in castle.wall
            if any(reach(w, t) <= TOWER_REACH for t in towers)}


def naked(castle: Castle) -> List[Tile]:
    """Wall with nothing looking down at it."""
    seen = covered(castle)
    return [w for w in castle.wall if w not in seen]


def stretches(tiles: Iterable[Tile]) -> List[List[Tile]]:
    """Group tiles into runs that touch each other, so that "six yards on the
    east side" is one answer rather than six."""
    left = set(tiles)
    out: List[List[Tile]] = []
    while left:
        start = min(left)
        left.discard(start)
        run, queue = [start], deque([start])
        while queue:
            for n in _touching(queue.popleft()):
                if n in left:
                    left.discard(n)
                    run.append(n)
                    queue.append(n)
        out.append(sorted(run))
    out.sort(key=len, reverse=True)
    return out


def weak(castle: Castle) -> List[Tile]:
    """The stretch a besieger picks: the longest run of wall no tower covers.

    He picks it because you would. If every yard is covered this is empty and
    an escalade has to come in somewhere a tower is shooting at it, which is
    the whole purpose of building towers rather than more wall.
    """
    runs = stretches(naked(castle))
    return runs[0] if runs else []


def compass(t: Tile) -> str:
    """Which side of the castle a tile is on, in words, because "6 yards at
    (11,19)" is not something anybody can act on."""
    dx, dy = t[0] - CENTRE[0], t[1] - CENTRE[1]
    if abs(dx) >= abs(dy) * 2:
        return "east" if dx > 0 else "west"
    if abs(dy) >= abs(dx) * 2:
        return "south" if dy > 0 else "north"
    return ("south" if dy > 0 else "north") + ("-east" if dx > 0 else "-west")


def depth(castle: Castle) -> int:
    """How many walls a man has to get through to reach the middle.

    One is a castle. Two is a castle somebody thought about. It is counted by
    walking in from the edge and adding one every time the path has to go
    through stone, which is exactly what the besieger has to do.
    """
    block = set(castle.of_kind(*WALL_KINDS))
    if not block:
        return 0
    cost: Dict[Tile, int] = {}
    queue: deque = deque()
    for i in range(SIDE):
        for t in ((i, 0), (i, SIDE - 1), (0, i), (SIDE - 1, i)):
            if t not in cost:
                cost[t] = 1 if t in block else 0
                queue.append(t)
    # 0-1 BFS: stepping onto open ground is free, stepping through a wall
    # costs one. The cheapest way in is the one he will take.
    while queue:
        t = queue.popleft()
        for n in _near(t):
            if not on_map(n):
                continue
            step = cost[t] + (1 if n in block else 0)
            if n not in cost or step < cost[n]:
                cost[n] = step
                if n in block:
                    queue.append(n)
                else:
                    queue.appendleft(n)
    return cost.get(CENTRE, 0)


def ditch_at(castle: Castle, tiles: Iterable[Tile]) -> Dict[str, int]:
    """What is dug in front of a given stretch of wall. A moat two hundred
    yards away from where they are digging is scenery."""
    out = {MOAT: 0, PITCH: 0, PITS: 0}
    want = set(tiles)
    for t, kind in castle.pieces.items():
        if kind in DITCH_KINDS and any(reach(t, w) <= 2 for w in want):
            out[kind] += 1
    return out


@dataclass
class Reading:
    """The castle, read. Everything `castle` prints and the siege consults."""
    yards: int = 0
    stone: int = 0
    timber: int = 0
    towers: int = 0
    gates: int = 0
    shut: bool = False
    inside: int = 0
    covered: int = 0
    weak: List[Tile] = field(default_factory=list)
    depth: int = 0
    gaps: int = 0

    @property
    def cover(self) -> float:
        return self.covered / self.yards if self.yards else 0.0

    @property
    def weak_side(self) -> str:
        return compass(self.weak[len(self.weak) // 2]) if self.weak else ""

    def density(self, garrison: float) -> float:
        """Men to the yard. The number a long wall is bought with."""
        return garrison / self.yards if self.yards else 0.0


def read(castle: Castle) -> Reading:
    counts = castle.spent()
    return Reading(
        yards=castle.yards,
        stone=counts.get(STONE, 0), timber=counts.get(TIMBER, 0),
        towers=counts.get(TOWER, 0), gates=counts.get(GATE, 0),
        shut=shut(castle), inside=len(enclosed(castle)),
        covered=len(covered(castle)), weak=weak(castle),
        depth=depth(castle), gaps=len(gaps(castle)))


# ------------------------------------------------------ what you have to lay

def budget(buildings) -> Dict[str, int]:
    """How many yards of each kind the buildings you have paid for allow.

    Only completed ones: a wall that is still being built is not a wall you
    can stand on, and letting it be laid early would make the build time free.
    """
    out: Dict[str, int] = {k: 0 for k in KINDS}
    for b in buildings:
        if not b.complete:
            continue
        kind, n = YARDS.get(b.key, ("", 0))
        if kind:
            out[kind] += n
    return out


def unlaid(buildings, castle: Castle) -> Dict[str, int]:
    """What is in hand and not yet on the ground."""
    have, laid = budget(buildings), castle.spent()
    return {k: have.get(k, 0) - laid.get(k, 0) for k in KINDS}


def over_budget(buildings, castle: Castle) -> Dict[str, int]:
    """Anything drawn that has not been paid for. Nothing should ever be here
    -- the drawing commands check first -- but a save from a version with
    different yardage would be, and silently keeping it would be a wall for
    free."""
    return {k: -v for k, v in unlaid(buildings, castle).items() if v < 0}


#: What a piece falls back to when it has not been paid for. A tower you
#: cannot afford is still a yard of wall somebody built; taking the whole
#: stone out from under it punches a hole in the ring, which is the one
#: thing a budget rule must never do to a castle somebody drew. Measured
#: once and never forgotten: it turned a concentric castle of ninety
#: enclosed plots into sixteen, silently, because two towers were over.
FALLBACK = {TOWER: (STONE, TIMBER), GATE: (STONE, TIMBER), STONE: (TIMBER,)}


def trim(buildings, castle: Castle) -> List[Tile]:
    """Bring the drawing back inside what has been paid for.

    Furthest from the keep first, and *demoted* rather than removed wherever
    there is a humbler thing in hand to stand in its place -- so an unpaid
    tower becomes the stone it is built on, and unpaid stone becomes timber,
    and only what has nothing to fall back on comes down at all.
    """
    gone: List[Tile] = []
    for kind in (TOWER, GATE, STONE, TIMBER, MOAT, PITCH, PITS):
        excess = -unlaid(buildings, castle).get(kind, 0)
        if excess <= 0:
            continue
        standing = sorted(castle.of_kind(kind), key=lambda t: -reach(t, CENTRE))
        for t in standing[:excess]:
            for down in FALLBACK.get(kind, ()):
                if unlaid(buildings, castle).get(down, 0) > 0:
                    castle.lay(t, down)
                    break
            else:
                castle.clear(t)
                gone.append(t)
    return gone


# ---------------------------------------------------------- the default ring

def ring(x0: int, y0: int, x1: int, y1: int) -> List[Tile]:
    out = [(x, y0) for x in range(x0, x1 + 1)]
    out += [(x1, y) for y in range(y0 + 1, y1 + 1)]
    out += [(x, y1) for x in range(x1 - 1, x0 - 1, -1)]
    out += [(x0, y) for y in range(y1 - 1, y0, -1)]
    return out


def default_castle(buildings, want_inside: int = 0) -> Castle:
    """The ring a steward would lay if you never gave him an instruction.

    A square, as big as the yards in hand will close and no bigger than the
    town needs, stone where there is stone, towers at the corners and the gate
    on the south where the road is. This is what every settlement had before
    the wall was a drawing, so a game that never touches the new commands
    looks and plays exactly as it did.
    """
    c = Castle()
    have = budget(buildings)
    line = have[TIMBER] + have[STONE] + have[TOWER] + have[GATE]
    if line < 8:
        return c
    # A square ring of side s costs 4s-4 yards and shuts in (s-2)^2 tiles --
    # of which a cross of streets takes 2(s-2)-1 and the keep takes one, so
    # what is actually left to build on is plots(s) below. Sizing the ring by
    # the raw interior was how a town with thirty-six workshops ended up with
    # twelve of them standing in the field outside its own gate.
    plots = lambda s: (s - 2) ** 2 - (2 * (s - 2) - 1) - 1
    best = 2
    for s in range(3, SIDE - 2):
        if 4 * s - 4 > line:
            break
        best = s
        if want_inside and plots(s) >= want_inside:
            break
    cx, cy = CENTRE
    x0, y0 = cx - best // 2, cy - best // 2
    tiles = ring(x0, y0, x0 + best - 1, y0 + best - 1)
    corners = {(x0, y0), (x0 + best - 1, y0), (x0, y0 + best - 1),
               (x0 + best - 1, y0 + best - 1)}
    gate_at = (cx, y0 + best - 1)
    stone_left, towers_left, gates_left = have[STONE], have[TOWER], have[GATE]
    for t in tiles:
        if t == gate_at and gates_left:
            c.lay(t, GATE)
            gates_left -= 1
        elif t in corners and towers_left:
            c.lay(t, TOWER)
            towers_left -= 1
        elif stone_left:
            c.lay(t, STONE)
            stone_left -= 1
        else:
            c.lay(t, TIMBER)
    # Towers nobody had room for at the corners go on the longest naked run,
    # which is where a steward would put them and where they do most good.
    while towers_left:
        run = weak(c)
        if not run:
            break
        c.lay(run[len(run) // 2], TOWER)
        towers_left -= 1
    # The ditch goes in front of the wall, all the way round as far as it goes.
    outer = ring(x0 - 1, y0 - 1, x0 + best, y0 + best)
    for kind in (MOAT, PITCH, PITS):
        left = have[kind]
        for t in outer:
            if not left:
                break
            if on_map(t) and not c.at(t):
                c.lay(t, kind)
                left -= 1
    return c


# --------------------------------------------------- what the shape is worth
#
# Three numbers the siege reads off the drawing. Each is a thing a defender
# would actually say out loud, and none of them is a score.

#: Men to the yard at which a wall-walk is properly held. Below it there are
#: stretches with nobody on them; above it there are men behind men.
HELD = 2.5


def manning(per_yard: float) -> float:
    """What the wall-walk is worth for how thinly it is held.

    Added to the battlement, so it is in the same units as a tower. This is
    the price of enclosing more ground than you have men for, and the reason
    a small tight castle is a real answer rather than a poor man's one: the
    garrison does not grow when the perimeter does.
    """
    return max(-5.0, min(7.0, 4.0 * math.log2(max(0.25, per_yard) / HELD)))


def exposure(reading: "Reading") -> float:
    """How much easier the ladders are for the stretch nobody covers.

    A besieger does not put his ladders where the towers are. He walks round
    until he finds the longest run of wall with nothing looking down at it,
    and that is where the assault comes -- so a castle is only as covered as
    its worst side, not as covered as its average.
    """
    if not reading.yards:
        return 1.0
    run = len(reading.weak)
    if run <= 1:
        return 0.55                     # nowhere to put a ladder unwatched
    return min(1.0, 0.55 + 0.45 * min(1.0, run / 8.0))


def killing_ground(reading: "Reading") -> float:
    """What a second wall does to a storm that gets over the first.

    Not more hit points -- a yard they have to cross with an inner wall
    shooting into it. It cuts how much of the garrison a storm can reach,
    because most of the garrison is not on the wall they just took.
    """
    return 1.0 / max(1, reading.depth)
