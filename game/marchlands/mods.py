"""Changing the game without editing the game.

Every table in here is a dictionary of frozen dataclasses: buildings, units,
goods, houses, institutions, lords. That is a good shape to read and an
impossible shape to *tune*, because tuning it means editing the source, and
editing the source means your changes and the next commit are the same file.

The thing worth taking from a modding scene is not scripting. It is that
somebody who wants oats in the game, or a cheaper trebuchet, or a seventh
lord, can have them in ten minutes and keep them when the game updates. That
wants exactly one feature: a folder of small files that say what to change.

    mods/cheap_siege.json
    {
      "units": {
        "trebuchet": {"coin": 300, "upkeep": 1.1},
        "ram":       {"coin": 90}
      }
    }

Three rules, and they are all about not lying to the player.

**A mod patches fields; it does not replace tables.** Naming a unit changes
the fields you name and leaves the rest, so a mod written against one version
does not silently delete what a later one added.

**Anything it cannot apply is reported, not swallowed.** A typo in a key is
the single commonest thing to go wrong, and a mod that quietly does nothing
is worse than one that refuses to load.

**Nothing is executed.** These are JSON tables, not scripts. A game that
ships no dependencies should not acquire the ability to run a stranger's
code the week it acquires mods.
"""

from __future__ import annotations

import json
import os
from dataclasses import fields, replace
from typing import Any, Callable, Dict, List, Tuple

#: Which tables a mod may touch, and how to reach each one. Adding a table
#: here is the whole of adding it to the mod format.
def _tables() -> Dict[str, Dict[str, Any]]:
    from . import buildings, goods, lords, military, tech
    return {
        "buildings": buildings.BUILDINGS,
        "units": military.UNITS,
        "goods": goods.GOODS,
        "houses": tech.HOUSES,
        "techs": tech.TECHS,
        "lords": lords.SORTS,
    }


class Mod:
    """One file's worth of changes, and what it could not do."""

    def __init__(self, name: str, data: Dict[str, Any]) -> None:
        self.name = name
        self.data = data
        self.applied: List[str] = []
        self.refused: List[str] = []

    def apply(self) -> "Mod":
        tables = _tables()
        for table, entries in self.data.items():
            if table.startswith("_"):            # notes to the reader
                continue
            if table not in tables:
                self.refused.append(
                    f"no table called {table!r}; there is "
                    + ", ".join(sorted(tables)))
                continue
            if not isinstance(entries, dict):
                self.refused.append(f"{table} should be a table of entries")
                continue
            for key, patch in entries.items():
                self._one(tables[table], table, key, patch)
        return self

    def _one(self, table: Dict[str, Any], name: str, key: str,
             patch: Any) -> None:
        if key not in table:
            near = [k for k in table if k.startswith(key[:3])][:3]
            self.refused.append(
                f"{name}: nothing called {key!r}"
                + (f" -- did you mean {', '.join(near)}?" if near else ""))
            return
        if not isinstance(patch, dict):
            self.refused.append(f"{name}.{key} should be a set of fields")
            return
        was = table[key]
        known = {f.name for f in fields(was)} if hasattr(was, "__dataclass_fields__") else set()
        good: Dict[str, Any] = {}
        for field_name, value in patch.items():
            if field_name not in known:
                self.refused.append(
                    f"{name}.{key}: no field called {field_name!r}"
                    + (f" -- it has " + ", ".join(sorted(known)) if known else ""))
                continue
            good[field_name] = value
        if not good:
            return
        try:
            table[key] = replace(was, **good)
        except Exception as exc:                 # a wrong type, usually
            self.refused.append(f"{name}.{key}: {exc}")
            return
        self.applied.append(
            f"{name}.{key}: " + ", ".join(f"{k}={v!r}" for k, v in good.items()))


def read(path: str) -> Tuple[Dict[str, Any], str]:
    """One mod file, or why it could not be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        return {}, f"could not open it: {exc}"
    except ValueError as exc:
        return {}, f"not valid JSON: {exc}"
    if not isinstance(data, dict):
        return {}, "a mod should be an object of tables"
    return data, ""


def load(folder: str = "mods") -> List[Mod]:
    """Apply every mod in a folder, in name order so it is repeatable.

    Returns what each one did. Nothing here raises: a broken mod is a
    reported mod, because the alternative is a game that will not start and
    does not say why.
    """
    out: List[Mod] = []
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(folder, name)
        data, why = read(path)
        mod = Mod(name, data)
        if why:
            mod.refused.append(why)
            out.append(mod)
            continue
        out.append(mod.apply())
    return out


def report(mods: List[Mod]) -> List[str]:
    """What the folder did, for a player who needs to know it worked."""
    lines: List[str] = []
    for mod in mods:
        lines.append(f"{mod.name}: {len(mod.applied)} change(s)"
                     + (f", {len(mod.refused)} refused" if mod.refused else ""))
        for said in mod.applied:
            lines.append(f"    {said}")
        for said in mod.refused:
            lines.append(f"    refused: {said}")
    return lines
