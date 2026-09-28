"""The joints between the four parents, tested as joints.

A system that only changes its own screen is a wing on the house; these are
the places where one thing a player does has to move two books at once. One
test per weld, and the one number a lord's ill-will comes to. If a later
patch makes any of these false, it has added a wing and taken away a joint.

  * the court's number is one number, made of the reasons it lists;
  * the road is the diplomatic map: a gift moves a toll the same day, and
    the steward can say what that is worth in coin and in days;
  * the host is a payroll: raising it empties sheds, its dead leave the
    town, and standing it down puts the hands back;
  * succession is the campaign: the chapter opens on the person;
  * coverage and the letter are one pressure, ranked as one.
"""

import unittest

from marchlands import chancery as court
from marchlands import config as C
from marchlands.scenario import new_game


def chartered(g):
    g.progress.researched |= {"coinage", "assize_of_bread", "chancery"}
    return g


class TestOneNumber(unittest.TestCase):
    """What a lord feels about you is one figure, and it is its reasons."""

    def setUp(self):
        self.g = chartered(new_game(seed=5))
        self.t = self.g.world.towns["ostmark"]
        self.t.hostility = 40.0

    def test_the_reasons_add_up_to_the_number(self):
        g = self.g
        g.court.write("ostmark", "took_town", -30.0, g.day)
        g.court.write("ostmark", "gift", 12.0, g.day)
        rows = g.court.reasons("ostmark", g.day, restless=self.t.hostility)
        self.assertIn(court.RESTLESS, [r[0] for r in rows])
        self.assertAlmostEqual(-sum(v for _l, v, _d in rows),
                               g.court.ill_will("ostmark", g.day, self.t.hostility))

    def test_a_gift_is_counted_once(self):
        g = self.g
        before = g.court.ill_will("ostmark", g.day, self.t.hostility)
        g.gift("ostmark", 1000)
        # Into the book -- not off the timer as well.
        self.assertEqual(self.t.hostility, 40.0)
        self.assertAlmostEqual(before - self.t.ill_will, 1000 * C.GIFT_PER_COIN)

    def test_the_war_gate_reads_the_whole_number(self):
        """A grievance in the book brings a lord to war as surely as time does."""
        g = self.g
        self.t.hostility = C.HOSTILITY_WAR - 20.0
        g.court.write("ostmark", "took_town", -40.0, g.day)
        g.tick()
        self.assertGreater(self.t.gathering + len(
            [a for a in g.armies if a.owner == "ostmark"]), 0,
            "a lord over the line on reasons alone never reckoned a war")

    def test_a_truce_holds_the_whole_number_back(self):
        g = self.g
        self.t.truce_days = 30
        self.t.hostility = C.HOSTILITY_WAR
        g.court.write("ostmark", "took_town", -60.0, g.day)
        for _ in range(10):
            g.tick()
        self.assertFalse([a for a in g.armies if a.owner == "ostmark"])

    def test_the_court_screen_shows_it(self):
        from marchlands.cli import Console
        import io
        import re
        out = io.StringIO()
        con = Console(self.g, out=out)
        con.do("court ostmark")
        text = re.sub(r"\x1b\[[0-9;]*m", "", out.getvalue())
        self.assertIn("his ill-will toward you", text)
        self.assertIn(court.RESTLESS, text)
        self.assertIn("rises until he marches", text)


if __name__ == "__main__":
    unittest.main()
