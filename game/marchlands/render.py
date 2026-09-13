"""Ink: colour, framing and the small typography of a terminal.

Nothing in here knows the rules. It knows that a besieged wall should read as
red, that a granary running down should not read the same as one that is full,
and that a box drawn with box-drawing characters looks like a box.

Colour switches itself off when the output is not a terminal, when NO_COLOR is
set, or when TERM says dumb -- so a piped transcript and a test's StringIO both
come out as plain text.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional, Sequence

# --- the palette ------------------------------------------------------------
# 256-colour indices, chosen to sit together: parchment and ink, with field
# green, stone grey, iron rust and a banner red.
INK = 250
DIM = 244
FAINT = 240
PARCH = 223
GOLD = 178
AMBER = 214
FIELD = 107
LEAF = 71
DEEP = 65
STONE = 145
SLATE = 103
RUST = 137
IRON = 66
BLOOD = 160
FLAME = 202
SEA = 74
SKY = 111
PLUM = 139
BONE = 187

SEASON_TINT = {"spring": LEAF, "summer": FIELD, "autumn": AMBER, "winter": SKY}


def _enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("MARCHLANDS_COLOR") == "1":
        return True
    if os.environ.get("TERM", "") in ("", "dumb"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:                       # pragma: no cover - odd streams
        return False


COLOUR = _enabled()


def set_colour(on: bool) -> None:
    """Force colour on or off (the console does this per output stream)."""
    global COLOUR
    COLOUR = on


def c(text: str, colour: Optional[int] = None, *, bold: bool = False,
      dim: bool = False) -> str:
    if not COLOUR or (colour is None and not bold and not dim):
        return text
    parts = []
    if bold:
        parts.append("1")
    if dim:
        parts.append("2")
    if colour is not None:
        parts.append(f"38;5;{colour}")
    return f"\033[{';'.join(parts)}m{text}\033[0m"


def width(text: str) -> int:
    """Printable width, ignoring escape codes."""
    out, i = 0, 0
    while i < len(text):
        if text[i] == "\033":
            while i < len(text) and text[i] != "m":
                i += 1
        else:
            out += 1
        i += 1
    return out


def pad(text: str, n: int, align: str = "<") -> str:
    gap = max(0, n - width(text))
    if align == ">":
        return " " * gap + text
    if align == "^":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


# --- framing ----------------------------------------------------------------
W = 72


def rule(char: str = "─", n: int = W, colour: int = FAINT) -> str:
    return c(char * n, colour)


def head(title: str, right: str = "", colour: int = GOLD, n: int = W) -> str:
    """A titled rule: ── TITLE ─────────────────────────── right ──"""
    left = f"── {title} "
    tail = f" {right} ──" if right else "──"
    fill = max(2, n - width(left) - width(tail))
    return (c("── ", FAINT) + c(title, colour, bold=True) + c(" " + "─" * fill, FAINT)
            + (c(f" {right} ", DIM) + c("──", FAINT) if right else c("──", FAINT)))


def box(lines: Sequence[str], title: str = "", n: int = W,
        colour: int = FAINT) -> List[str]:
    top = "┌" + (f"┤ {title} ├" if title else "") + "─" * max(
        0, n - 2 - (width(title) + 4 if title else 0)) + "┐"
    out = [c(top, colour)]
    for ln in lines:
        out.append(c("│", colour) + " " + pad(ln, n - 3) + c("│", colour))
    out.append(c("└" + "─" * (n - 2) + "┘", colour))
    return out


# --- small pieces -----------------------------------------------------------
BLOCKS = " ▁▂▃▄▅▆▇█"
BAR_FULL = "█"
BAR_HALF = "▌"


def bar(value: float, top: float, n: int = 20, good_high: bool = True) -> str:
    """A filled bar that goes red when it should worry you."""
    frac = 0.0 if top <= 0 else max(0.0, min(1.0, value / top))
    filled = int(round(frac * n))
    shade = frac if good_high else 1.0 - frac
    colour = BLOOD if shade < 0.25 else (AMBER if shade < 0.55 else LEAF)
    return c(BAR_FULL * filled, colour) + c("·" * (n - filled), FAINT)


def coin(value: float, width_: int = 8, plus: bool = False) -> str:
    text = f"{value:+,.0f}" if plus else f"{value:,.0f}"
    text = pad(text, width_, ">")
    if abs(value) < 0.5:
        return c(text, FAINT)
    return c(text, LEAF if value > 0 else BLOOD)


def spark(values: Sequence[float], n: int = 48, colour: int = GOLD) -> str:
    vals = list(values)[-n:]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return c(BLOCKS[4] * len(vals), colour)
    return c("".join(BLOCKS[1 + int(7.99 * (v - lo) / (hi - lo))] for v in vals),
             colour)


def tone(ratio: float) -> int:
    """Colour for a price against its base: cheap is green, dear is red."""
    if ratio < 0.8:
        return LEAF
    if ratio > 1.3:
        return BLOOD
    if ratio > 1.1:
        return AMBER
    return INK
