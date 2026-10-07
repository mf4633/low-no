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

    def test_the_workshops_take_the_same_cut(self):
        # Rung or not, horsemen round the town cost the workshops the same:
        # what ringing gives up is the fields, and only the fields.
        g, s = new_game()
        calm = s.productivity(g.progress)
        g.ring_bell("aldworth")
        s.raid_pressure = 0.667
        rung = s.productivity(g.progress)
        s.bell = 0
        self.assertEqual(s.productivity(g.progress), rung)
        self.assertLess(rung, calm)

    def test_asking_whether_it_shelters_changes_nothing(self):
        from marchlands.settlement import BuildingInstance
        g, s = new_game()
        for b in country(s):
            b.enabled = False
        burner = BuildingInstance(uid=s.next_uid, key="charcoal_burner",
                                  days_left=0)
        burner.dry_days = 2
        s.buildings.append(burner)
        s.market.stock["wood"] = 50.0
        g.ring_bell("aldworth")
        s.sheltering()
        s.raid_pressure = 1.0
        s.productivity(g.progress)
        self.assertEqual(burner.dry_days, 2)

    def test_a_shed_that_could_not_work_shelters_nobody(self):
        from marchlands.settlement import BuildingInstance
        g, s = new_game()
        for b in country(s):
            b.enabled = False
        fold = BuildingInstance(uid=s.next_uid, key="sheep_farm", days_left=0)
        fold.head = 0.0                                   # no beasts
        s.buildings.append(fold)
        g.ring_bell("aldworth")
        self.assertFalse(s.sheltering())
        fold.head = 7.0
        self.assertTrue(s.sheltering())

    def test_a_winter_orchard_shelters_nobody(self):
        from marchlands.settlement import BuildingInstance
        g, s = new_game()
        for b in country(s):
            b.enabled = False
        s.buildings.append(BuildingInstance(uid=s.next_uid, key="orchard",
                                            days_left=0))
        g.ring_bell("aldworth")
        s._season_now = "winter"
        self.assertFalse(s.sheltering())
        s._season_now = "summer"
        self.assertTrue(s.sheltering())


class TestAWholeRaid(unittest.TestCase):
    """Twelve days of it through `advance`, the host really RAIDING: the
    order the game runs a day in (produce, eat, mood, then the raid) is part
    of what is being tested."""

    def run_raid(self, ring, workshops=False, spears=40, winter=False):
        from marchlands.goods import good
        from marchlands.military import RAIDING
        from marchlands.settlement import BuildingInstance
        g, s = new_game()
        if winter:
            g.day = 270
        if workshops:
            for key in ("mill", "bakery"):
                s.buildings.append(BuildingInstance(uid=s.next_uid, key=key,
                                                    days_left=0))
                s.next_uid += 1
            s.market.stock["wheat"] = s.market.stock.get("wheat", 0) + 2500
            s.market.stock["wood"] = s.market.stock.get("wood", 0) + 400
        s.units = {}
        if ring:
            g.ring_bell("aldworth")
        pop = s.population
        g.armies.append(Army(uid=953, name="raiders", owner="vantry",
                             units={"spearman": spears}, at="aldworth",
                             state=RAIDING))
        made = 0.0
        for _ in range(g.RAID_PATIENCE):
            g.advance(1)
            made += sum(q * good(k).base_price
                        for k, q in s.report.produced.items())
        stock = sum(q * good(k).base_price for k, q in s.market.stock.items())
        return pop - s.population, stock, made

    def test_ringing_for_the_raid_saves_people_and_stores(self):
        lost_open, stock_open, _ = self.run_raid(False)
        lost_rung, stock_rung, _ = self.run_raid(True)
        self.assertLess(lost_rung, lost_open)
        self.assertGreater(stock_rung, stock_open)

    def test_a_rung_town_still_makes_less_than_one_working_its_fields(self):
        # The workshops keep part of the raid's cut: ringing trades output
        # for people and stores, it does not win on every count.
        # On the raid it was tuned on, a bigger one, and in winter: the
        # cases where relief for the workshops let ringing win on output.
        for spears, winter in ((40, False), (80, False), (50, True)):
            with self.subTest(spears=spears, winter=winter):
                lost_open, stock_open, made_open = self.run_raid(
                    False, workshops=True, spears=spears, winter=winter)
                lost_rung, stock_rung, made_rung = self.run_raid(
                    True, workshops=True, spears=spears, winter=winter)
                self.assertLess(made_rung, made_open)
                self.assertLess(lost_rung, lost_open)
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
        line = next(h for h in said if "The bell is ringing at Aldworth" in h)
        self.assertIn("nothing is made out there", line)
        self.assertIn("`bell down aldworth`", line)
        self.assertNotIn("<town>", line)

    def test_fed_but_sour_is_not_told_the_granary_is_empty(self):
        g, s = new_game()
        s.market.stock["bread"] = s.market.stock.get("bread", 0.0) + 3000.0
        g.ring_bell("aldworth")
        g.advance(1)
        s.popularity = 25.0
        line = next(h for h in Console(g, out=io.StringIO()).hints()
                    if "The bell has rung at Aldworth" in h)
        self.assertNotIn("granary", line)
        self.assertIn("mood 25", line)

    def test_an_empty_granary_outranks_a_quiet_bell_and_the_towers(self):
        from marchlands.military import MARCHING
        g, s = new_game()
        for k in list(s.market.stock):
            s.market.stock[k] = 0.0
        fed = start("marchlands", seed=3).world.settlements["aldworth"]
        fed.name = "Greyfell"
        fed.count = lambda k: 0
        fed.market.stock["bread"] = 3000.0
        fed.bell = 3
        g.world.settlements["greyfell"] = fed
        g.armies.append(Army(uid=960, name="the Margrave's host",
                             owner="vantry", units={"spearman": 30},
                             at="vantry", bound_for="aldworth",
                             state=MARCHING, days_left=3, leg_days=4))
        said = Console(g, out=io.StringIO()).hints()
        self.assertTrue(any("of food" in h for h in said), said)

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

    def test_two_fed_bells_do_not_hide_an_empty_granary(self):
        g, s = new_game()
        for k in list(s.market.stock):
            s.market.stock[k] = 0.0                  # Aldworth: no food at all
        for key, name in (("greyfell", "Greyfell"), ("brack", "Brack")):
            fed = start("marchlands", seed=3).world.settlements["aldworth"]
            fed.name = name
            fed.count = lambda k: 0
            fed.market.stock["bread"] = 3000.0
            fed.bell = 3
            g.world.settlements[key] = fed
        said = Console(g, out=io.StringIO()).hints()
        self.assertEqual(sum("The bell is ringing at" in h for h in said), 1)
        self.assertTrue(any("days of food" in h or "day of food" in h
                            for h in said), said)

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

    def test_a_name_in_two_words(self):
        g, s, other, con = self.two_towns()
        other.name = "Caer Ithel"
        con.here = "aldworth"
        con.do("bell ring caer ithel")
        self.assertEqual(other.bell, 1)
        self.assertEqual(s.bell, 0)
        con.do("sally 5 caer ithel")
        self.assertIn("Caer Ithel", con.out.getvalue())

    def test_shore_takes_off_wherever_it_is_said(self):
        g, s, other, con = self.two_towns()
        s.shoring = True
        con.do("shore aldworth off")
        self.assertFalse(s.shoring)

    def test_a_verb_word_inside_a_name_stays_in_the_name(self):
        g, s, other, con = self.two_towns()
        other.name = "North Stand"
        con.here = "aldworth"
        g.ring_bell("aldworth")
        con.do("bell ring north stand")
        self.assertEqual(other.bell, 1)
        self.assertEqual(s.bell, 1)               # Aldworth's still up

    def test_naming_a_town_still_wins(self):
        g, s, other, con = self.two_towns()
        con.do("gates shut aldworth")
        self.assertTrue(s.shut)
        self.assertFalse(other.shut)


if __name__ == "__main__":
    unittest.main()
