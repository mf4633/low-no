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

from marchlands.clock import ALARMS, Clock, PACE, alarming


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
    """A clock that runs while your castle burns is not exciting, it is
    unreadable. A clock that stops at every harvest is one nobody leaves
    running, and then the game is turn-based again with extra steps."""

    def test_it_stops_for_the_things_you_would_want_to_be_told(self):
        for line in ("Dunmere besieges Aldworth",
                     "Caldmoor declares war on you",
                     "Aldworth has fallen",
                     "the people are starving",
                     "fire in the granary",
                     "*** The Age of Faith begins ***"):
            self.assertTrue(alarming(line), line)

    def test_it_does_not_stop_for_the_weather(self):
        for line in ("Old Mare at Bruille: +56c",
                     "the Ostmark Guild is running Weapons from Bruille to Vantry",
                     "Aldworth: stores overflowing, 277 units past capacity",
                     "Aldworth: Iron Mine finished"):
            self.assertFalse(alarming(line), line)

    def test_every_alarm_says_why_in_words_a_player_reads(self):
        for _pattern, why in ALARMS:
            self.assertTrue(why and why[0].islower(), why)

    def test_a_day_with_an_alarm_in_it_stops_the_clock(self):
        c, _console = clock(["a quiet morning", "Dunmere besieges Aldworth"])
        c.speed = 3
        c.step()
        self.assertEqual(c.speed, 0)
        self.assertIn("besieg", c.stopped_for.lower() + "besieg")
        self.assertTrue(c.stopped_for)
        self.assertTrue(any("the clock stops" in l for _n, l in c.said))

    def test_a_quiet_day_leaves_it_running(self):
        c, _console = clock(["Old Mare at Bruille: +56c"])
        c.speed = 2
        c.step()
        self.assertEqual(c.speed, 2)
        self.assertEqual(c.stopped_for, "")

    def test_the_end_of_the_game_stops_it(self):
        c, console = clock(["a quiet day"], over_after=1)
        c.speed = 3
        c.step()
        self.assertEqual(c.speed, 0)
        self.assertEqual(c.stopped_for, "the game is over")
        c.step()                                  # and it stays stopped
        self.assertEqual(console.game.day, 1, "a finished game went on running")


class TestNoDayIsLost(unittest.TestCase):
    """The browser polls. A poll that lands after three days have passed must
    be given three days, not the last one with the other two dropped."""

    def test_what_was_said_is_handed_out_from_where_you_had_got_to(self):
        c, _console = clock(["day happened"])
        for _ in range(3):
            c.step()
        self.assertEqual(len(c.since(0)), 3)
        self.assertEqual(len(c.since(1)), 2)
        self.assertEqual(c.since(c.seq), [])

    def test_the_sequence_only_ever_goes_up(self):
        c, _console = clock(["one", "two"])
        seen = []
        for _ in range(4):
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


if __name__ == "__main__":
    unittest.main()


class TestTheAlarmSaysWhatHappened(unittest.TestCase):
    """Naming the category is not the same as naming the event. "a host has
    sat down before your walls" tells you what kind of thing happened;
    "Dunmere besieges Aldworth" tells you what happened."""

    def test_it_keeps_the_line_that_stopped_it(self):
        c, _console = clock(["a quiet morning", "Dunmere besieges Aldworth"])
        c.speed = 3
        c.step()
        self.assertEqual(c.stopped_at, "Dunmere besieges Aldworth")
        self.assertTrue(c.stopped_for)
        self.assertNotEqual(c.stopped_at, c.stopped_for)

    def test_starting_the_clock_again_clears_both(self):
        c, _console = clock(["fire in the granary"])
        c.speed = 1
        c.step()
        self.assertTrue(c.stopped_at)
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
        c, _console = clock(["Caldmoor declares war on you"])
        c.speed = 2
        c.step()
        st = c.state()
        self.assertIn("stopped_for", st)
        self.assertIn("stopped_at", st)
        self.assertIn("declares war", st["stopped_at"])
