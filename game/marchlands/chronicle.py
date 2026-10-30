"""The chronicle: what a reign looked like, written down as it happened.

Neither parent game had this and both of them needed it. What people remember
about a long Age of Empires match or a Stronghold estate is not the final
score, it is the shape of the thing -- the year the wolves came, the siege
that nearly went, the season everything was finally paid for. A number at the
end throws all of that away.

So the game keeps a chronicle. Notable things are written down with the date
they happened, in the words a clerk would have used, and at the end you can
read your reign back instead of being handed a total.

Nothing in here changes the rules. It is the part that makes the rules worth
having played.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

ROUTINE = 1        # the ordinary run of a year
NOTABLE = 2        # worth remembering
MOMENTOUS = 3      # worth telling somebody about

MAX_ENTRIES = 400


@dataclass
class Entry:
    day: int
    year: int
    season: str
    text: str
    weight: int = NOTABLE
    chapter: str = ""

    def stamp(self) -> str:
        return f"{self.season} {self.year}"

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Entry":
        return cls(**d)


@dataclass
class Chronicle:
    entries: List[Entry] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.entries)

    def record(self, *, day: int, year: int, season: str, text: str,
               weight: int = NOTABLE, chapter: str = "") -> Optional[Entry]:
        """Write a line, unless the same line was written recently.

        The deduplication matters more than it looks. A siege that runs for a
        fortnight would otherwise fill the chronicle with fourteen identical
        sentences and bury the year it belongs to.
        """
        for old in reversed(self.entries[-12:]):
            if old.text == text and day - old.day < 90:
                return None
        entry = Entry(day=day, year=year, season=season, text=text,
                      weight=weight, chapter=chapter)
        self.entries.append(entry)
        if len(self.entries) > MAX_ENTRIES:
            # Drop the least interesting thing that happened longest ago.
            routine = [i for i, e in enumerate(self.entries)
                       if e.weight <= ROUTINE]
            del self.entries[routine[0] if routine else 0]
        return entry

    def since(self, day: int) -> List[Entry]:
        return [e for e in self.entries if e.day >= day]

    def read(self, least: int = NOTABLE, limit: int = 40,
             chapter: str = "") -> List[Entry]:
        out = [e for e in self.entries
               if e.weight >= least and (not chapter or e.chapter == chapter)]
        return out[-limit:]

    def to_dict(self) -> dict:
        return {"entries": [e.to_dict() for e in self.entries]}

    @classmethod
    def from_dict(cls, d: dict) -> "Chronicle":
        return cls(entries=[Entry.from_dict(e) for e in d.get("entries", [])])
