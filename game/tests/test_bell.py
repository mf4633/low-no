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
        self.assertIn("country hands came in", said)
        for b in country(s):
            self.assertEqual(b.staffed, 0)
            self.assertEqual(b.idle_reason, "the bell is rung")
        self.assertEqual(s.out_working(), 0)       # and their eyes with them
        self.assertTrue(any(said in e.text for e in g.chronicle.entries))

    def test_nothing_is_made_out_there_while_it_rings(self):
        g, s = new_game()
        g.ring_bell("aldworth")
        g.advance(2)
        self.assertEqual(g.season, "spring")
        for b in country(s):
            self.assertEqual(b.staffed, 0)
            self.assertLessEqual(b.throughput, 0.0)
            # Not "out of season" in spring: the morning's production must
            # not overwrite why the farm is empty.
            self.assertEqual(b.idle_reason, "the bell is rung")

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

    def loot(self, ring):
        g, s = new_game()
        if ring:
            g.ring_bell("aldworth")
        s.units = {}
        stock = sum(s.market.stock.values())
        g._raid_settlement(Army(uid=951, name="raiders", owner="vantry",
                                units={"spearman": 40}, at="aldworth"), s)
        return stock - sum(s.market.stock.values())

    def test_the_granary_is_mostly_spared(self):
        open_fields, rung = self.loot(False), self.loot(True)
        self.assertGreater(open_fields, 0)
        self.assertAlmostEqual(rung / open_fields, C.BELL_LOOT, places=2)

    def herd_lost(self, ring):
        from marchlands.settlement import BuildingInstance, DayReport
        g, s = new_game()
        fold = BuildingInstance(uid=s.next_uid, key="sheep_farm", days_left=0)
        fold.head = 7.0
        s.buildings.append(fold)
        if ring:
            g.ring_bell("aldworth")
        s.raided, s.raid_pressure = True, 1.0
        s._herds(DayReport())
        return 7.0 - fold.head

    def test_most_of_the_beasts_come_in(self):
        open_fields, rung = self.herd_lost(False), self.herd_lost(True)
        self.assertGreater(open_fields, 0)
        self.assertAlmostEqual(rung / open_fields, C.BELL_HERD, places=2)

    def test_a_bell_over_shut_sheds_shelters_nobody(self):
        g, s = new_game()
        for b in country(s):
            b.enabled = False
        g.ring_bell("aldworth")
        self.assertFalse(s.sheltering())
        open_country = self.raid(False)
        g2, s2 = new_game()
        for b in country(s2):
            b.enabled = False
        g2.ring_bell("aldworth")
        s2.units = {}
        pop = s2.population
        g2._raid_settlement(Army(uid=952, name="raiders", owner="vantry",
                                 units={"spearman": 40}, at="aldworth"), s2)
        self.assertAlmostEqual(pop - s2.population, open_country, places=6)

    def test_the_workshops_do_not_take_the_fields_cut(self):
        g, s = new_game()
        g.ring_bell("aldworth")
        s.raid_pressure = 0.667
        rung = s.productivity(g.progress)
        s.bell = 0
        self.assertLess(s.productivity(g.progress), rung)


class TestAWholeRaid(unittest.TestCase):
    """Twelve days of it, not one: RAID_PATIENCE is how long a raid lasts."""

    def run_raid(self, ring):
        g, s = new_game()
        if ring:
            g.ring_bell("aldworth")
        s.units = {}
        start_pop = s.population
        a = Army(uid=953, name="raiders", owner="vantry",
                 units={"spearman": 40}, at="aldworth")
        for _ in range(g.RAID_PATIENCE):
            s.raid_pressure = 0.0
            g._raid_settlement(a, s)
            s.tick(g.season, g.rng, g.progress, g.day)
        return start_pop - s.population, sum(s.market.stock.values())

    def test_ringing_for_the_raid_saves_people_and_stores(self):
        lost_open, stock_open = self.run_raid(False)
        lost_rung, stock_rung = self.run_raid(True)
        self.assertLess(lost_rung, 0.5 * lost_open)
        self.assertGreater(stock_rung, stock_open)


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


class TestTheSteward(unittest.TestCase):
    def test_a_long_ringing_with_short_bread_is_named(self):
        g, s = new_game()
        g.ring_bell("aldworth")
        g.advance(5)
        s.popularity = 20.0
        said = " ".join(Console(g, out=io.StringIO()).hints())
        self.assertIn("The bell has rung at Aldworth for 5 days", said)
        self.assertIn("`bell down aldworth`", said)

    def test_a_rung_town_with_bread_is_still_mentioned(self):
        g, s = new_game()
        s.market.stock["bread"] = s.market.stock.get("bread", 0.0) + 3000.0
        g.ring_bell("aldworth")
        g.advance(1)
        said = Console(g, out=io.StringIO()).hints()
        line = next(h for h in said if "The bell has rung at Aldworth" in h)
        self.assertIn("nothing is made out there", line)

    def test_each_town_is_judged_on_its_own_granary(self):
        g, s = new_game()
        hungry = start("marchlands", seed=3).world.settlements["aldworth"]
        hungry.name = "Greyfell"
        hungry.count = lambda key: 0
        for k in list(hungry.market.stock):
            hungry.market.stock[k] = 0.0
        g.world.settlements["greyfell"] = hungry
        hungry.bell = 4
        said = Console(g, out=io.StringIO()).hints()      # looking at Aldworth
        self.assertIn("The bell has rung at Greyfell", said[0])
        self.assertIn("the granary is what they eat", said[0])

    def test_no_bell_no_word(self):
        g, s = new_game()
        said = " ".join(Console(g, out=io.StringIO()).hints())
        self.assertNotIn("The bell has rung", said)


class TestTheTownOnScreen(unittest.TestCase):
    """Every button on the town's page acts on the town the page shows."""

    def two_towns(self):
        g, s = new_game()
        other = start("marchlands", seed=3).world.settlements["aldworth"]
        other.name = "Greyfell"
        other.count = lambda key: 0          # no keep: Aldworth stays the seat
        g.world.settlements["greyfell"] = other
        con = Console(g, out=io.StringIO())
        con.here = "greyfell"
        return g, s, other, con

    def test_gates(self):
        g, s, other, con = self.two_towns()
        con.do("gates shut")
        self.assertTrue(other.shut)
        self.assertFalse(s.shut)

    def test_shore_and_sally_follow_the_screen_and_take_a_name(self):
        g, s, other, con = self.two_towns()
        con.do("shore on")
        self.assertTrue(other.shoring)
        self.assertFalse(s.shoring)
        con.do("shore on Aldworth")
        self.assertTrue(s.shoring)

    def test_naming_a_town_still_wins(self):
        g, s, other, con = self.two_towns()
        con.do("gates shut aldworth")
        self.assertTrue(s.shut)
        self.assertFalse(other.shut)


if __name__ == "__main__":
    unittest.main()
