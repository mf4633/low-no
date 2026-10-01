"""What every part of the console draws with: rules, titles, sparklines,
wrapping, and reading a command line. Split out of cli.py so each part
can name them without importing the console itself.
"""

from __future__ import annotations

import shlex
from typing import Dict, List, Sequence

from .goods import resolve as resolve_good
from . import render as ink
from .trade import Order, Stop


BARS = " ▁▂▃▄▅▆▇█"
RULE = ink.rule()


def title(text: str, right: str = "", colour: int = ink.GOLD) -> str:
    return ink.head(text, right, colour)


def _fmt(x: float, width: int = 8, dp: int = 0) -> str:
    return f"{x:>{width},.{dp}f}"


def sparkline(values: Sequence[float], width: int = 48) -> str:
    vals = list(values)[-width:]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return BARS[4] * len(vals)
    return "".join(BARS[1 + int(7.99 * (v - lo) / (hi - lo))] for v in vals)


def _words(line: str) -> list:
    r"""A command line split the way a shell splits it, less the escapes.

    Quotes still hold a name with a space in it together. A backslash is
    only a backslash, because the game ships as a Windows exe and to a
    POSIX splitter `save C:\Users\me\march.json` is `C:Usersmemarch.json`,
    written quietly to wherever the game was started from.
    """
    lex = shlex.shlex(line, posix=True)
    lex.whitespace_split = True
    lex.commenters = ""
    lex.escape = ""
    return list(lex)


def _node_colour(game, key: str) -> int:
    if game.world.is_mine(key):
        return ink.GOLD
    town = game.world.towns.get(key)
    if town is None:
        return ink.INK
    if town.mine:
        return ink.LEAF
    if game.world.is_port(key):
        return ink.SEA
    return ink.BLOOD if town.ill_will > 70 else ink.INK


def _wrap(text: str, n: int) -> List[str]:
    """Break a sentence at a space, because a person speaking does not wrap
    mid-word at column sixty-eight."""
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > n:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


def _short(text: str, n: int) -> str:
    """A name that will not fit, cut where a reader can still place it."""
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _level(text: str, labels: Dict[int, str]) -> int:
    t = text.lower()
    for k, v in labels.items():
        if v == t:
            return k
    # A word that is not one of the labels is the likeliest thing a player
    # types here -- `ration full` rather than `ration double` -- and it used
    # to answer with `invalid literal for int() with base 10: 'full'`, which
    # is Python talking to a player. Say what the dial takes instead.
    try:
        n = int(text)
    except ValueError:
        raise ValueError(f"no setting called {text!r}; "
                         f"try {', '.join(labels.values())}") from None
    if n not in labels:
        raise ValueError(f"level must be one of {sorted(labels)} or "
                         f"{', '.join(labels.values())}")
    return n


def _parse_stop(world, tokens: List[str]) -> Stop:
    """`<town> buy wheat 120@3.2 sell ale all` -> a Stop."""
    if not tokens:
        raise ValueError("which town?")
    stop = Stop(node=world.resolve(tokens[0]))
    i = 1
    while i < len(tokens):
        verb = tokens[i].lower()
        if verb not in ("buy", "sell"):
            raise ValueError(f"expected buy/sell, got {tokens[i]!r}")
        if i + 2 >= len(tokens):
            raise ValueError(f"{verb} needs a good and a quantity")
        gkey = resolve_good(tokens[i + 1])
        qty_text = tokens[i + 2]
        limit = 0.0
        if "@" in qty_text:
            qty_text, price_text = qty_text.split("@", 1)
            limit = float(price_text)
        qty = -1.0 if qty_text.lower() in ("all", "max", "*") else float(qty_text)
        order = Order(good=gkey, quantity=qty, limit_price=limit)
        (stop.sell if verb == "sell" else stop.buy).append(order)
        i += 3
    return stop
