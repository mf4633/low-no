"""Time that runs on its own.

The game was turn-based because a console has no other option. A drawn view
does, and taking it changes what the game is: a siege you watched arrive is a
different thing from a siege that was in the report when you pressed next.

These tests are about the three things that make a running clock usable
rather than merely running -- it stops itself when something happens, it
never loses a day's news to a slow poll, and it is the same writer as the
rest of the server rather than a second one racing it.
"""

from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.request
from io import StringIO

from marchlands.clock import Clock, PACE, watch


class FakeGame:
    """A game that only knows how to have a day happen."""

    def __init__(self, lines=None, over_after=None):
        self.day = 0
        self.over = False
        self.lines = lines or []
        self.over_after = over_after
        self.saved = 0

    def advance(self, n=1):
        self.day += n
        if self.over_after is not None and self.day >= self.over_after:
            self.over = True
        return list(self.lines)


class FakeConsole:
    def __init__(self, game):
        self.game = game
        self.autosaves = 0

    def _autosave(self):
        self.autosaves += 1


def clock(lines=None, over_after=None):
    console = FakeConsole(FakeGame(lines, over_after))
    return Clock(console, threading.Lock()), console


class TestWhatStopsTheClock(unittest.TestCase):
    """A clock that runs while your castle burns is unreadable. A clock that
    stops at every harvest is one nobody leaves running, and then the game is
    turn-based again with extra steps.

    This began as patterns matched against the day's messages, and five
    minutes of playing it showed why that cannot work: `***` marks
    *momentous* in this codebase rather than *dangerous*, so the clock halted
    on day one of every game for "the season opens" -- twenty-three stops in
    twelve hundred days, not one of them an emergency -- and a rule for fire
    matched "Vantry is rebuilding after fire", a trade opportunity in
    somebody else's town, sixteen times more. It reads the state now.
    """

    def march(self, seed=11, days=0):
        from marchlands.scenarios import start
        g = start("marchlands", seed=seed)
        if days:
            g.advance(days)
        return g

    def test_a_quiet_march_is_worth_nothing_to_stop_for(self):
        g = self.march()
        for words in watch(g).values():
            self.assertNotIn("season", words.lower())
            self.assertNotIn("age", words.lower())

    def test_a_siege_is(self):
        g = self.march()
        next(iter(g.world.settlements.values())).besieged = True
        self.assertTrue(any("besieged" in w for w in watch(g).values()))

    def test_so_is_hunger_and_so_is_a_town_near_revolt(self):
        g = self.march()
        s = next(iter(g.world.settlements.values()))
        s.report.hunger = 0.5
        s.popularity = 10.0
        said = " ".join(watch(g).values())
        self.assertIn("hungry", said)
        self.assertIn("revolt", said)

    def test_it_stops_on_the_day_a_thing_becomes_true_and_not_after(self):
        # A siege that stops the clock once is a warning. A siege that stops
        # it every morning is a reason to stop using the clock.
        c, console = clock(["a quiet day"])
        seat = type("S", (), {})()
        c.speed = 3
        c.step()                         # first step only learns the world
        stops = []

        def pretend(_game, state={"n": 0}):
            state["n"] += 1
            return {"siege:Aldworth": "Aldworth is besieged"} if state["n"] > 1 else {}

        import marchlands.clock as clockmod
        was = clockmod.watch
        clockmod.watch = pretend
        try:
            c.speed = 3
            c.step()                     # nothing yet
            stops.append(c.speed)
            c.speed = 3
            c.step()                     # the siege begins: stop
            stops.append(c.speed)
            c.speed = 3
            c.step()                     # still besieged: do not stop again
            stops.append(c.speed)
        finally:
            clockmod.watch = was
        self.assertEqual(stops, [3, 0, 3], "it stopped for the same siege twice")

    def test_a_game_that_opens_besieged_is_not_interrupted_to_be_told_so(self):
        c, console = clock(["a day"])
        self.assertIsNone(c._was)
        c.speed = 2
        c.step()
        self.assertEqual(c.speed, 2, "the first step should only look")

    def test_a_real_siege_stops_a_running_clock(self):
        # Driven through the engine rather than by setting the flag: the day
        # clears `besieged` at the top of the tick and sets it again from the
        # armies standing outside, so a flag poked in from a test is gone
        # before `watch` ever sees it.
        from marchlands.military import Army, BESIEGING
        g = self.march()
        console = FakeConsole(g)
        c = Clock(console, threading.Lock())
        c.speed = 3
        c.step()                                   # learn the quiet world
        seat = next(iter(g.world.settlements))
        foe = next(k for k, t in g.world.towns.items() if not t.mine)
        g.armies.append(Army(uid=9001, name="host", owner=foe, at=seat,
                             state=BESIEGING, home=foe,
                             units={"spearman": 40, "ram": 1}))
        c.speed = 3
        c.step()
        self.assertEqual(c.speed, 0, "a host at the gate did not stop time")
        self.assertIn("besieged", c.stopped_for)

    def test_the_end_of_the_game_stops_it(self):
        c, console = clock(["a quiet day"], over_after=1)
        c.speed = 3
        c.step()
        self.assertEqual(c.speed, 0)
        self.assertEqual(c.stopped_for, "the game is over")
        c.step()
        self.assertEqual(console.game.day, 1, "a finished game went on running")


class TestNoDayIsLost(unittest.TestCase):
    """The browser polls. A poll that lands after three days have passed must
    be given three days, not the last one with the other two dropped."""

    def test_what_was_said_is_handed_out_from_where_you_had_got_to(self):
        # Distinct lines: a day that says the same thing as yesterday is
        # collapsed on purpose, and this test is about the cursor.
        c, console = clock(["day happened"])
        for n in range(3):
            console.game.lines = [["a birth", "a fire", "a wedding"][n]]
            c.step()
        self.assertEqual(len(c.since(0)), 3)
        self.assertEqual(len(c.since(1)), 2)
        self.assertEqual(c.since(c.seq), [])

    def test_the_sequence_only_ever_goes_up(self):
        c, console = clock(["one", "two"])
        seen = []
        for n in range(4):
            console.game.lines = ["abcd"[n] + " happened",
                                  "wxyz"[n] + " happened too"]
            c.step()
            seen.append(c.seq)
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(len(set(seen)), len(seen))

    def test_blank_lines_are_not_news(self):
        c, _console = clock(["", "   ", "something"])
        c.step()
        self.assertEqual(len(c.since(0)), 1)

    def test_it_does_not_remember_forever(self):
        from marchlands.clock import KEEP
        c, _console = clock(["a line"])
        for _ in range(KEEP + 40):
            c.step()
        self.assertLessEqual(len(c.said), KEEP)


class TestItIsTheSameWriterAsTheServer(unittest.TestCase):
    """Two writers of one game with two locks is not locking."""

    def test_it_waits_for_whoever_is_holding_the_lock(self):
        lock = threading.Lock()
        console = FakeConsole(FakeGame(["a day"]))
        c = Clock(console, lock)
        with lock:
            t = threading.Thread(target=c.step, daemon=True)
            t.start()
            time.sleep(0.15)
            self.assertEqual(console.game.day, 0, "it stepped during a command")
        t.join(timeout=2.0)
        self.assertEqual(console.game.day, 1)

    def test_it_autosaves_the_way_a_typed_day_does(self):
        c, console = clock(["a day"])
        c.step()
        self.assertEqual(console.autosaves, 1)

    def test_a_paused_clock_does_not_move(self):
        c, console = clock(["a day"])
        c.set_speed(0)
        c.start()
        time.sleep(0.5)
        c.close()
        self.assertEqual(console.game.day, 0)

    def test_running_it_actually_advances_days(self):
        c, console = clock(["a day"])
        c.set_speed(3)
        time.sleep(PACE[3] * 3 + 0.4)
        c.close()
        self.assertGreaterEqual(console.game.day, 2)


class TestTheDialOverHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from marchlands import web
        from marchlands.cli import Console
        from marchlands.scenarios import start
        cls.web = web
        cls.server, cls.url = web.serve(Console(start("marchlands", seed=5),
                                                out=StringIO()),
                                        port=0, open_browser=False)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        if cls.web.CLOCK:
            cls.web.CLOCK.close()
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.url.rstrip("/") + path) as r:
            return json.loads(r.read())

    def post(self, path, body):
        req = urllib.request.Request(self.url.rstrip("/") + path,
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def test_the_game_starts_stopped(self):
        self.assertEqual(self.get("/clock")["speed"], 0)

    def test_setting_a_speed_makes_the_days_pass(self):
        was = self.get("/state")["day"]
        self.post("/speed", {"speed": 3})
        try:
            time.sleep(PACE[3] * 3 + 0.5)
            self.assertGreater(self.get("/state")["day"], was)
        finally:
            self.post("/speed", {"speed": 0})

    def test_a_nonsense_speed_is_a_stopped_clock_not_a_crash(self):
        self.assertEqual(self.post("/speed", {"speed": 99})["speed"], 0)

    def test_the_state_carries_the_clock_and_the_news(self):
        self.post("/speed", {"speed": 3})
        try:
            time.sleep(PACE[3] * 2 + 0.5)
        finally:
            self.post("/speed", {"speed": 0})
        out = self.get("/state?since=0")
        self.assertIn("clock", out)
        self.assertIn("said", out)
        self.assertGreater(out["clock"]["seq"], 0)
        # and asking from the head gives nothing twice
        self.assertEqual(self.get(f"/state?since={out['clock']['seq']}")["said"], [])




class TestTheLogIsNewsAndNotWeather(unittest.TestCase):
    """Found by playing it. Somebody else's cart on somebody else's road was
    one line in a day you asked for; with time running on its own it is seven
    a day, and thirty days of play buried three pieces of news under sixty of
    other people's trade."""

    def test_the_world_marks_its_own_chatter(self):
        from marchlands.events import FLAVOUR
        from marchlands.scenarios import start
        g = start("marchlands", seed=11)
        said = g.advance(8)
        marked = [l for l in said if l.startswith(FLAVOUR)]
        self.assertTrue(marked, "no chatter to filter; the test is not testing")
        for line in marked:
            self.assertIn("is running", line)

    def test_the_browser_stream_leaves_it_out(self):
        from marchlands.scenarios import start
        console = FakeConsole(start("marchlands", seed=11))
        c = Clock(console, threading.Lock())
        for _ in range(12):
            c.step()
        for line in c.since(0):
            self.assertNotIn("is running", line)

    def test_and_the_news_is_still_there(self):
        from marchlands.scenarios import start
        console = FakeConsole(start("marchlands", seed=11))
        c = Clock(console, threading.Lock())
        for _ in range(12):
            c.step()
        self.assertTrue(c.since(0), "the stream was filtered down to nothing")

    def test_a_standing_complaint_is_said_once(self):
        # A town whose stores are overflowing says so every single day with a
        # different number: six lines of "stores overflowing, 75 / 70 / 65 /
        # 60 units past capacity" in one screenful. That is a condition, not
        # news, and a log that runs on its own has to show what changed.
        c, _console = clock(["Greyfell: stores overflowing, 75 units past capacity"])
        for n in (70, 65, 60, 54):
            c.console.game.lines = [
                f"Greyfell: stores overflowing, {n} units past capacity"]
            c.step()
        c.step()
        self.assertEqual(len(c.since(0)), 1, c.since(0))

    def test_but_two_different_complaints_are_two_lines(self):
        c, _console = clock(["Greyfell: stores overflowing, 75 units past capacity"])
        c.step()
        c.console.game.lines = ["Greyfell: the granary is empty"]
        c.step()
        self.assertEqual(len(c.since(0)), 2)

    def test_the_engine_still_produces_it(self):
        # Filtered out of the browser's stream, not out of the game: the
        # chatter is what makes a foreign market feel like somewhere other
        # people trade, and `log` still has it.
        from marchlands.events import FLAVOUR
        from marchlands.scenarios import start
        g = start("marchlands", seed=11)
        said = g.advance(8)
        self.assertTrue(any("is running" in l for l in said))
        self.assertTrue(all(l.startswith(FLAVOUR)
                            for l in said if "is running" in l),
                        "chatter reached the day unmarked")



if __name__ == "__main__":
    unittest.main()


class TestTheAlarmSaysWhatHappened(unittest.TestCase):
    """Naming the category is not the same as naming the event. These used to
    drive a fake game whose messages contained the words to match; the clock
    reads the state now, so they drive a real one."""

    def besieged(self):
        from marchlands.military import Army, BESIEGING
        from marchlands.scenarios import start
        g = start("marchlands", seed=11)
        console = FakeConsole(g)
        c = Clock(console, threading.Lock())
        c.speed = 3
        c.step()                                  # learn the quiet world
        seat = next(iter(g.world.settlements))
        foe = next(k for k, t in g.world.towns.items() if not t.mine)
        g.armies.append(Army(uid=9002, name="host", owner=foe, at=seat,
                             state=BESIEGING, home=foe,
                             units={"spearman": 40, "ram": 1}))
        c.speed = 3
        c.step()
        return c, g

    def test_it_names_the_place_rather_than_the_kind_of_thing(self):
        c, g = self.besieged()
        seat = next(iter(g.world.settlements.values()))
        self.assertIn(seat.name, c.stopped_for)
        self.assertIn("besieged", c.stopped_for)

    def test_it_quotes_the_day_only_when_the_day_named_that_place(self):
        # It used to match the reason's first two words against the day's
        # lines, and the second word of "Aldworth is besieged" is `is`, which
        # appears in almost everything the game prints -- so the banner
        # announced that time had stopped because the Vellani House was
        # running bread to Caer Ithel. Empty is a fine answer; wrong is not.
        from marchlands.events import FLAVOUR
        c, g = self.besieged()
        seat = next(iter(g.world.settlements.values()))
        if c.stopped_at:
            self.assertIn(seat.name, c.stopped_at)
            self.assertFalse(c.stopped_at.startswith(FLAVOUR))
        self.assertTrue(c.stopped_for, "the reason itself is never empty")

    def test_the_reason_is_a_sentence_and_not_a_category(self):
        c, g = self.besieged()
        seat = next(iter(g.world.settlements.values()))
        self.assertIn(seat.name, c.stopped_for)

    def test_starting_the_clock_again_clears_both(self):
        c, _g = self.besieged()
        self.assertTrue(c.stopped_for)
        c.set_speed(1)
        try:
            self.assertEqual(c.stopped_at, "")
            self.assertEqual(c.stopped_for, "")
        finally:
            c.close()

    def test_the_end_of_the_game_has_no_line_to_quote(self):
        c, _console = clock(["a quiet day"], over_after=1)
        c.speed = 2
        c.step()
        self.assertEqual(c.stopped_for, "the game is over")
        self.assertEqual(c.stopped_at, "")

    def test_the_state_carries_both(self):
        c, _g = self.besieged()
        st = c.state()
        self.assertIn("stopped_for", st)
        self.assertIn("stopped_at", st)
        self.assertIn("besieged", st["stopped_for"])


if __name__ == "__main__":
    unittest.main()
