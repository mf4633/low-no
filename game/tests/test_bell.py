"""The bell: the warning is worth nothing unless there is something to do.

Rung, every hand out in the country comes in behind the wall. A raid finds
empty fields -- fewer people driven off, most of the beasts brought in --
and the town pays for it in everything the country would have made, in the
woodcutters' eyes, and in a crowded, sour town.
"""
import io
import random
import unittest

from marchlands import config as C
from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.military import Army
from marchlands.scenarios import start


def new_game():
    g = start("marchlands", seed=3)
    g.advance(3)
    return g, g.world.settlements["aldworth"]


def country(s):
    return [b for b in s.buildings if b.spec.terrain in s.COUNTRY and b.complete]


class TestRinging(unittest.TestCase):
    def test_the_country_comes_in(self):
        g, s = new_game()
        self.assertTrue(any(b.staffed for b in country(s)))
        said = g.ring_bell("aldworth")
        self.assertIn("The bell rang at Aldworth", said)
        self.assertIn("woodcutters", said)
        for b in country(s):
            self.assertEqual(b.staffed, 0)
            self.assertEqual(b.idle_reason, "the bell is rung")
        self.assertEqual(s.rangers(), [])          # and their eyes with them
        self.assertTrue(any(said in e.text for e in g.chronicle.entries))

    def test_nothing_is_made_out_there_while_it_rings(self):
        g, s = new_game()
        g.ring_bell("aldworth")
        g.advance(2)
        for b in country(s):
            self.assertEqual(b.staffed, 0)
            self.assertLessEqual(b.throughput, 0.0)

    def test_a_pin_does_not_outrank_it(self):
        g, s = new_game()
        wood = next(b for b in s.buildings if b.key == "woodcutter")
        s.pin_hands(wood.uid, 2)
        g.ring_bell("aldworth")
        g.advance(1)
        self.assertEqual(wood.staffed, 0)

    def test_it_sours_the_town(self):
        g, s = new_game()
        g.ring_bell("aldworth")
        self.assertEqual(dict(s.mood_factors(g.progress)).get(
            "the bell has the country in"), C.BELL_MOOD)

    def test_standing_down_sends_them_back(self):
        g, s = new_game()
        g.ring_bell("aldworth")
        g.advance(4)
        said = g.ring_bell("aldworth", False)
        self.assertIn("after 4 days", said)
        self.assertEqual(s.bell, 0)
        self.assertTrue(any(b.staffed for b in country(s)))

    def test_twice_is_said_not_done(self):
        g, s = new_game()
        g.ring_bell("aldworth")
        before = len(g.chronicle.entries)
        self.assertIn("already", g.ring_bell("aldworth"))
        self.assertEqual(len(g.chronicle.entries), before)

    def test_it_is_saved(self):
        g, s = new_game()
        g.ring_bell("aldworth")
        g.advance(2)
        back = GameState.from_dict(g.to_dict())
        self.assertEqual(back.world.settlements["aldworth"].bell, s.bell)


class TestTheRaid(unittest.TestCase):
    def raid(self, ring):
        g, s = new_game()
        if ring:
            g.ring_bell("aldworth")
        s.units = {}
        g.rng = random.Random(7)
        a = Army(uid=950, name="raiders", owner="vantry",
                 units={"spearman": 40}, at="aldworth")
        pop = s.population
        g._raid_settlement(a, s)
        return pop - s.population

    def test_fewer_are_driven_off(self):
        open_fields, rung = self.raid(False), self.raid(True)
        self.assertGreater(open_fields, 0)
        self.assertAlmostEqual(rung / open_fields, C.BELL_FLIGHT, places=2)


class TestTheVerb(unittest.TestCase):
    def test_bell_rings_and_bell_down_stands_it_down(self):
        g, s = new_game()
        out = io.StringIO()
        con = Console(g, out=out)
        con.do("bell ring")
        self.assertEqual(s.bell, 1)
        con.do("bell")
        self.assertIn("bell down", out.getvalue())
        con.do("bell down")
        self.assertEqual(s.bell, 0)

    def test_it_rings_the_town_you_are_looking_at(self):
        g, s = new_game()
        other = start("marchlands", seed=3).world.settlements["aldworth"]
        other.name = "Greyfell"
        g.world.settlements["greyfell"] = other
        con = Console(g, out=io.StringIO())
        con.here = "greyfell"
        con.do("bell ring")
        self.assertEqual(other.bell, 1)
        self.assertEqual(s.bell, 0)


if __name__ == "__main__":
    unittest.main()
