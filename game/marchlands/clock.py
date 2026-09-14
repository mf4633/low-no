"""Time that runs on its own.

The game was turn-based because a console has no other option: nothing
happens until somebody types. A drawn view in a browser does have another
option, and the games this one keeps borrowing from all take it -- Stronghold
and the Bannerlord campaign map both run the clock and let you interrupt it,
and that changes what the game *is*. A siege you watched arrive is a
different thing from a siege that was in the report when you pressed next.

Three decisions worth writing down.

**The clock advances the day through the engine's own `advance`**, which is
the identical call `next` makes, under the same lock, and it autosaves after
it the same way. What it does not do is print the console's status block,
because that is a *console* answer to "what happened" and the browser already
has a better one: it reads the state. Running `next` verbatim buried seven
days of events under a hundred and fifty lines of banner.

**It pauses itself when something happens.** This is the whole difference
between real time being tense and real time being a way to miss things. A
host at your gate, a war declared, a town lost, a fire in the granary: the
clock stops and the message is on the screen. An RTS that keeps running while
your castle burns is not being exciting, it is being unreadable.

**Messages are buffered with a sequence number.** The browser polls; a poll
that arrives after three days have passed must not silently drop two of them,
so what the days said is kept in order and handed out from wherever the
browser has got to.
"""

from __future__ import annotations

import re
import threading
from typing import Dict, List, Optional, Tuple

#: Real seconds per game day at each speed. Speed 0 is paused. These are the
#: numbers that decide whether the game feels like a map or a spreadsheet:
#: slow enough at 1 that a day is a beat you can think in, fast enough at 3
#: that a quiet winter does not have to be sat through.
PACE: Dict[int, float] = {1: 2.2, 2: 1.0, 3: 0.4}
SPEEDS: Tuple[int, ...] = (0, 1, 2, 3)

#: How many days of messages to keep. A player who leaves the tab and comes
#: back gets the recent past, not the whole chronicle -- `chronicle` is for
#: the whole chronicle.
KEEP = 400

#: What stops the clock. Deliberately about things that need a decision or
#: that you would be upset to read about afterwards, not about everything
#: notable -- a clock that stops at every harvest is a clock nobody leaves
#: running, and then the game is turn-based again with extra steps.
ALARMS = (
    (re.compile(r"\bbesieg", re.I), "a host has sat down before your walls"),
    (re.compile(r"\bstorms? the|\bassault", re.I), "the wall is being stormed"),
    (re.compile(r"\bdeclares war|\bdeclared war", re.I), "war has been declared"),
    (re.compile(r"\bhas fallen|\bis taken|\brevolts?\b", re.I), "a town has changed hands"),
    (re.compile(r"\bstarv|\bfamine", re.I), "people are starving"),
    (re.compile(r"\bfire\b|\bburn(s|ing)\b", re.I), "something is burning"),
    (re.compile(r"\braid(s|ing|ed)\b", re.I), "the country is being raided"),
    (re.compile(r"\*\*\*", re.I), "something worth stopping for"),
)


def alarming(line: str) -> str:
    """Why this line should stop the clock, or "" if it should not."""
    for pattern, why in ALARMS:
        if pattern.search(line):
            return why
    return ""


class Clock:
    """A thread that lets the days pass, and knows when to stop."""

    def __init__(self, console, lock: threading.Lock) -> None:
        self.console = console
        self.lock = lock                      # the server's, not a second one
        self.speed = 0
        self.seq = 0
        self.said: List[Tuple[int, str]] = []
        self.stopped_for = ""                 # why it paused itself, if it did
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------- the dial
    def set_speed(self, speed: int) -> dict:
        self.speed = speed if speed in SPEEDS else 0
        if self.speed:
            self.stopped_for = ""
            self.start()
        return self.state()

    def state(self) -> dict:
        return {"speed": self.speed, "seq": self.seq,
                "pace": PACE.get(self.speed, 0.0),
                "stopped_for": self.stopped_for}

    # --------------------------------------------------------- what was said
    def since(self, seq: int) -> List[str]:
        """Everything said after `seq`, in order. A poll that missed three
        days gets three days, not the last one."""
        return [line for n, line in self.said if n > seq]

    def _remember(self, text: str) -> None:
        for line in str(text).splitlines():
            if line.strip():
                self.seq += 1
                self.said.append((self.seq, line))
        del self.said[:-KEEP]

    # ------------------------------------------------------------ the thread
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            pace = PACE.get(self.speed, 0.0)
            if not pace:
                if self._stop.wait(0.2):
                    return
                continue
            if self._stop.wait(pace):
                return
            if not self.speed:                # paused while we waited
                continue
            self.step()

    def step(self) -> None:
        """One day, by the same call `next` makes."""
        with self.lock:
            game = getattr(self.console, "game", None)
            if game is None or getattr(game, "over", False):
                self.speed = 0
                self.stopped_for = "the game is over"
                return
            said = game.advance(1)
            autosave = getattr(self.console, "_autosave", None)
            if autosave:
                autosave()
            over = bool(getattr(game, "over", False))
        for line in said:
            self._remember(line)
        why = next((alarming(l) for l in said if alarming(l)), "")
        if over:
            self.speed, self.stopped_for = 0, "the game is over"
        elif why:
            self.speed = 0
            self.stopped_for = why
            self._remember(f"*** the clock stops: {why} ***")
