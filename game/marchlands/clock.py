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

from .events import FLAVOUR

#: Real seconds per game day at each speed. Speed 0 is paused. These are the
#: numbers that decide whether the game feels like a map or a spreadsheet:
#: slow enough at 1 that a day is a beat you can think in, fast enough at 3
#: that a quiet winter does not have to be sat through.
PACE: Dict[int, float] = {1: 2.2, 2: 1.0, 3: 0.4}
SPEEDS: Tuple[int, ...] = (0, 1, 2, 3)

#: How many recent lines to check a new one against before deciding it is
#: the same complaint again. Long enough to catch a daily repeat, short
#: enough that a thing which stops and starts is reported twice.
ECHO = 14

_DIGITS = re.compile(r"[\d.,]+")


def _shape(line: str) -> str:
    """A line with its numbers taken out, which is what makes two days of
    the same standing complaint the same line."""
    return _DIGITS.sub("#", line.strip())


#: How many days of messages to keep. A player who leaves the tab and comes
#: back gets the recent past, not the whole chronicle -- `chronicle` is for
#: the whole chronicle.
KEEP = 400

#: What stops the clock -- read off the game rather than out of its prose.
#:
#: This began as a list of patterns matched against the day's messages, and
#: playing it for five minutes showed why that cannot work. `***` marks
#: *momentous* in this codebase, not *dangerous*, so the clock halted on day
#: one of every game for "the season opens", and on every feat earned and
#: every age begun: twenty-three stops in twelve hundred days, none of them
#: an emergency. Worse, a rule for fire matched "Vantry is rebuilding after
#: fire" -- a trade opportunity in somebody else's town -- sixteen more times.
#:
#: A fact about your own holdings is not open to that kind of mistake. Each
#: of these reads the state directly and returns the words for it, and the
#: clock stops on the *rising edge*: the day a thing becomes true, not every
#: day it goes on being true. A siege that stopped the clock once is a
#: warning; a siege that stops it every morning is a reason to stop using
#: the clock.
def watch(game) -> Dict[str, str]:
    """The handful of facts worth interrupting a player for.

    Never raises. This runs inside the clock's own thread, where an
    exception is not an error message, it is time silently stopping.
    """
    out: Dict[str, str] = {}
    # A fight the day is waiting on comes first, because it is the one thing
    # here that time cannot simply run past: `advance` will not move the day
    # until it is fought, so a clock left running would print the same line
    # every beat for ever.
    pending = getattr(game, "pending", None)
    if pending is not None and not getattr(pending.battle, "over", True):
        out["battle"] = f"the storm is going in at {pending.title}"
    world = getattr(game, "world", None)
    if world is None:
        # Not every caller has a world -- the clock's own tests drive it with
        # a game that only knows how to have a day happen, and an exception
        # raised in here would kill the thread rather than the request.
        return out
    for s in world.settlements.values():
        name = s.name
        if getattr(s, "besieged", False):
            out[f"siege:{name}"] = f"{name} is besieged"
        if getattr(s, "raided", False):
            out[f"raid:{name}"] = f"the country around {name} is being raided"
        if getattr(s, "blockaded", False):
            out[f"blockade:{name}"] = f"{name} is blockaded"
        if getattr(getattr(s, "fires", None), "blazes", None):
            out[f"fire:{name}"] = f"fire in {name}"
        if getattr(s.report, "hunger", 0.0) > 0.01:
            out[f"hunger:{name}"] = f"{name} is going hungry"
        if getattr(s.report, "unpaid", None):
            out[f"unpaid:{name}"] = f"{name} has not been paid"
        if s.popularity < 25.0:
            out[f"unrest:{name}"] = f"{name} is close to revolt"
    court = getattr(game, "court", None)
    if court is not None:
        for key in getattr(court, "declared", {}):
            out[f"war:{key}"] = f"{game.world.node_name(key)} has declared war"
        if len(getattr(court, "coalition", ())) >= 3:
            out["coalition"] = (f"{len(court.coalition)} lords have signed the "
                                f"letter against you")
        if getattr(court, "called", None):
            out["called"] = "an ally has called you to a war"
    for key, t in getattr(world, "towns", {}).items():
        if t.mine:
            out[f"held:{key}"] = f"{t.name} is yours"
    return out


class Clock:
    """A thread that lets the days pass, and knows when to stop."""

    def __init__(self, console, lock: threading.Lock) -> None:
        self.console = console
        self.lock = lock                      # the server's, not a second one
        self.speed = 0
        self.seq = 0
        self.said: List[Tuple[int, str]] = []
        self.stopped_for = ""                 # why it paused itself, if it did
        self.stopped_at = ""                  # and the line that did it
        #: What was true of the march yesterday, so that only a *change* can
        #: stop the clock. Filled on the first step rather than at
        #: construction, because a game that opens besieged should not be
        #: interrupted to be told so.
        self._was: Optional[Dict[str, str]] = None
        #: The shape of the last few lines, so a standing complaint is said
        #: once rather than every morning.
        self._recent: List[str] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------- the dial
    def set_speed(self, speed: int) -> dict:
        self.speed = speed if speed in SPEEDS else 0
        if self.speed:
            self.stopped_for = self.stopped_at = ""
            self.start()
        return self.state()

    def state(self) -> dict:
        return {"speed": self.speed, "seq": self.seq,
                "pace": PACE.get(self.speed, 0.0),
                "stopped_for": self.stopped_for,
                "stopped_at": self.stopped_at}

    # --------------------------------------------------------- what was said
    def since(self, seq: int) -> List[str]:
        """Everything said after `seq`, in order. A poll that missed three
        days gets three days, not the last one."""
        return [line for n, line in self.said if n > seq]

    def _remember(self, text: str) -> None:
        """Keep a day's news. Not a day's weather.

        Somebody else's cart on somebody else's road was one line in a day
        you asked for. Time runs on its own now, and seven of them a day
        buried the news in a log nobody could read -- so the lines the world
        marks as flavour do not go into the stream the browser reads. They
        are still said in the terminal, where a day is something you asked
        for and the chatter is the point.
        """
        for line in str(text).splitlines():
            if not line.strip() or line.startswith(FLAVOUR):
                continue
            # And not the same complaint again. A town whose stores are
            # overflowing says so every single day, with a different number
            # each time -- six lines of "stores overflowing, 75 / 70 / 65 /
            # 60 units past capacity" in one screenful, which is a standing
            # condition rather than news. A log that runs on its own has to
            # show what changed.
            shape = _shape(line)
            if shape in self._recent:
                continue
            self._recent.append(shape)
            del self._recent[:-ECHO]
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
        try:
            now = watch(game)
        except Exception:               # time must not stop because a
            now = self._was or {}       # readout did

        fresh = [] if self._was is None else [
            (key, words) for key, words in now.items() if key not in self._was]
        self._was = now
        if over:
            self.speed, self.stopped_for = 0, "the game is over"
            self.stopped_at = ""
        elif fresh:
            key, words = fresh[0]
            self.speed = 0
            self.stopped_for = words
            # And the day's own words for it, if the day said anything about
            # that place. Matched on the name, which is distinctive, and not
            # on the first words of the reason -- the reason begins "Aldworth
            # is besieged", and matching its second word meant `is`, which
            # appears in almost every line the game prints. The banner duly
            # announced that time had stopped because the Vellani House was
            # running bread to Caer Ithel.
            where = key.split(":", 1)[-1] if ":" in key else ""
            self.stopped_at = next(
                (l.strip() for l in said
                 if where and where in l and not l.startswith(FLAVOUR)),
                "")
            self._remember(
                f"*** the clock stops: {'; '.join(w for _k, w in fresh[:3])} ***")
