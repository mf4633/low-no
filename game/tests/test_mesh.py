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


class TestTheHostIsAPayroll(unittest.TestCase):
    """Every man in the field is a hand missing from a shed at home."""

    def setUp(self):
        self.g = new_game(seed=5)
        self.key = next(iter(self.g.world.settlements))
        self.s = self.g.world.settlements[self.key]
        self.s.population = max(self.s.population, 400.0)
        self.s.units = {"spearman": 60.0}
        self.g.tick()                     # a day, so the roll has been called

    def test_raising_a_levy_keeps_its_men_off_the_sheds(self):
        s = self.s
        worked = s.workforce
        a, _why = self.g.raise_host(self.key, {"spearman": 50})
        # Out of the garrison and into the field: still not at a shed.
        self.assertEqual(s.workforce, worked)
        self.assertEqual(s.afield, 50)
        self.g.tick()
        self.assertEqual(s.afield, 50, "the host was forgotten overnight")

    def test_recruiting_empties_jobs_the_same_morning(self):
        s = self.s
        s.market.add("spears", 200)
        self.g.treasury = 50_000
        employed = s.employed
        self.g.recruit(self.key, "spearman", 40)
        self.assertLess(s.employed, employed + 1)
        self.assertLessEqual(s.employed, s.workforce)

    def test_standing_down_to_the_square_gives_the_hands_back(self):
        s = self.s
        a, _ = self.g.raise_host(self.key, {"spearman": 50})
        before = s.workforce
        said = self.g.disband_host(a.uid, to_square=True)
        self.assertIn("square", said)
        self.assertEqual(s.workforce, before + 50)
        self.assertEqual(s.units.get("spearman", 0.0), 10.0,
                         "they went to the garrison")

    def test_the_dead_are_missed_at_home(self):
        g, s = self.g, self.s
        a, _ = g.raise_host(self.key, {"spearman": 50})
        pop = s.population
        a.units["spearman"] -= 20.0       # a bad day somewhere
        said = g.tick()
        self.assertAlmostEqual(s.population, pop - 20.0, delta=3.0)
        self.assertTrue(any("buries" in m for m in said))

    def test_a_host_that_stands_down_is_not_mourned(self):
        g, s = self.g, self.s
        a, _ = g.raise_host(self.key, {"spearman": 50})
        g.tick()
        pop = s.population
        g.disband_host(a.uid)
        said = g.tick()
        self.assertGreater(s.population, pop - 3.0)
        self.assertFalse(any("buries" in m for m in said))

    def test_a_sliver_is_not_a_man(self):
        """A siege's arrows take a hundredth of a man a day. Rounding the
        roll to whole men buried a whole man the day 60.0 became 59.99."""
        g, s = self.g, self.s
        s.units = {"spearman": 60.0}
        g._roll = g._under_arms()
        pop = s.population
        s.units["spearman"] = 59.99
        g._count_the_fallen({})
        self.assertAlmostEqual(s.population, pop - 0.01, places=3)

    def test_a_starving_garrison_is_not_buried_twice(self):
        """Men who thin with a hungry town leave by the town's own road;
        the roll does not bury them again as killed at the wall."""
        g, s = self.g, self.s
        g._roll = g._under_arms()
        pop = s.population
        s.units["spearman"] -= 6.0
        g._roll_moved(self.key, -6.0)
        g._count_the_fallen({})
        self.assertAlmostEqual(s.population, pop, places=6)

    def test_a_parked_captain_learns_nothing(self):
        g = self.g
        a, _ = g.raise_host(self.key, {"spearman": 50})
        kid = next(p for p in g.kin.living() if p.uid != g.kin.head)
        kid.post, kid.target = "captain", str(a.uid)
        before = kid.xp.get("tactics", 0.0)
        for _ in range(20):
            g.tick()
        self.assertEqual(kid.xp.get("tactics", 0.0), before,
                         "two hundred men kept for later taught the heir war")
        self.assertIn(kid.uid, g.kin.idle)
        a.state = "marching"
        g.kin.day(g.day, head_doing="hall", afield={str(a.uid)})
        self.assertGreater(kid.xp.get("tactics", 0.0), before)


class TestSuccessionIsTheCampaign(unittest.TestCase):
    """The person is the save file: a chapter opens on who sits the hall."""

    def test_the_next_chapter_opens_on_the_heir_and_what_she_learned(self):
        from marchlands.campaign import Carry, carry_from, chapter_at
        g = chapter_at(3).start(seed=7)
        lord = g.kin.lord
        kid = next(p for p in g.kin.living()
                   if p.uid != g.kin.head and not p.inlaw
                   and lord.uid in (p.father, p.mother))
        kid.born = min(kid.born, g.day - 20 * int(C.DAYS_PER_YEAR))
        kid.post, kid.target = "factor", ""
        kid.xp["trade"] = 4000.0
        kid.xp["tactics"] = 0.0
        # The lord dies in chapter four. That is not the end of anything.
        g.kin.bury(lord, g.day)
        g.lord.alive = False              # as the fight that killed him does
        g.over = "Time called."
        carry = carry_from(g, Carry(seated=g.seated), won=False)
        nxt = chapter_at(4).start(seed=7, carry=carry)
        self.assertEqual(nxt.kin.lord.uid, kid.uid)
        opening = nxt.briefing.split("\n\n")[0]
        self.assertIn(f"{lord.name} is dead", opening)
        self.assertIn(f"{kid.name} sits the hall", opening)
        self.assertIn("trade", opening)
        self.assertIn("no tactics", opening)


class TestTheLetterIsAHoleInTheRing(unittest.TestCase):
    """A town grown past its inn and a march grown past what it will bear
    are the same pressure, and the steward ranks them the same."""

    def setUp(self):
        self.g = chartered(new_game(seed=5))
        home = next(iter(self.g.world.settlements))
        self.g.world.settlements[home].units = {"spearman": 200.0}
        self.a, _ = self.g.raise_host(home, {"spearman": 100})

    def test_the_second_town_warns_before_the_letter_is_written(self):
        from marchlands.cli import Console
        import io
        g = self.g
        g._take_town(g.world.towns["dunmere"], self.a)
        g.tick()
        self.assertFalse(g.court.coalition)
        tips = g.coalition_after_next()
        self.assertGreaterEqual(len(tips), court.COALITION_NAMES)
        con = Console(g, out=io.StringIO())
        ranked = dict((text[:40], rank) for rank, text in con._court_hints())
        self.assertIn(74.0, ranked.values(),
                      "the letter did not rank with a hole in the ring")
        # ...and it was right: the next town writes it.
        g._take_town(g.world.towns["vantry"], self.a)
        for _ in range(3):
            g.tick()
        self.assertGreaterEqual(len(g.court.coalition), court.COALITION_NAMES)


class TestTheRoadIsTheDiplomaticMap(unittest.TestCase):
    """Opinion is a customs rate, and a letter is an embargo."""

    def setUp(self):
        self.g = chartered(new_game(seed=5))
        self.t = self.g.world.towns["ostmark"]

    def test_a_gift_moves_the_toll_the_same_day_and_says_its_payback(self):
        g, t = self.g, self.t
        t.tolls_paid = 40.0               # a road your carts do use
        before = g.world.tariff_for("ostmark", None)
        said = g.gift("ostmark", 800)
        self.assertLess(g.world.tariff_for("ostmark", None), before)
        self.assertIn("c/day", said)
        self.assertRegex(said, r"pays back in \d+ days|never pays back")

    def test_a_gift_on_a_road_nobody_uses_is_goodwill(self):
        said = self.g.gift("ostmark", 800)
        self.assertIn("goodwill, not coin", said)

    def test_the_payback_arithmetic(self):
        days = self.g._days_to_repay(100.0, 2.0, 200.0)
        # 2c a day falling to nothing over 200 days is 200c in all; half of
        # it is back when 2t - t*t/200 = 100, at t = 58.6.
        self.assertAlmostEqual(days, 58.58, places=1)
        self.assertIsNone(self.g._days_to_repay(500.0, 2.0, 200.0))

    def test_a_signed_lord_stops_named_goods(self):
        from marchlands.advisor import scan
        g, t = self.g, self.t
        home = next(iter(g.world.settlements))

        def through_him():
            out = set()
            for o in scan(g.world, home, day=g.day, seed=g.seed, top=30,
                          budget=10_000):
                for leg in (o.out, o.back):
                    if leg is not None and "ostmark" in (o.frm, o.to):
                        out |= set(leg.cargo)
            return out
        was = through_him()
        g.court.coalition = ["ostmark", "dunmere", "vantry"]
        g._chancery_day()
        self.assertTrue(t.refuses, "a signatory refused nothing")
        stopped = t.refuses[0]
        self.assertIn(stopped, was, "nothing to stop: the test proves nothing")
        self.assertTrue(g.world.refuses("ostmark", stopped))
        self.assertNotIn(stopped, through_him(),
                         "the route-finder still sends it through his post")

    def test_pilgrims_buy_at_your_market_into_offerings(self):
        g = self.g
        sh = next(iter(g.world.shrines.values()))
        sh.holder = "player"
        seat = g.home()
        seat.market.add("bread", 300)
        seat.market.add("ale", 300)
        bread = seat.market.stock["bread"]
        g.tick()
        self.assertLess(seat.market.stock.get("bread", 0.0), bread)
        self.assertGreater(g.ledger.offerings, g.relic_income())


class TestTheLastThreeChaptersUseAllThree(unittest.TestCase):
    """The Count, the heir and the letter, in the same year -- chapters four
    to six are about all three, and before the Count wrote his letters the
    letter only came if you went conquering, which they never ask."""

    def test_the_count_writes_the_letter_in_the_first_year(self):
        from marchlands.campaign import RIVAL, chapter_at
        for idx in (3, 4, 5):
            g = chapter_at(idx).start(seed=7)
            for _ in range(7):
                g.tick()
            self.assertIn(RIVAL, g.court.coalition, f"chapter {idx + 1}")
            self.assertGreaterEqual(len(g.court.coalition),
                                    court.COALITION_NAMES)

    def test_and_it_lapses_if_nobody_proves_him_right(self):
        from marchlands.campaign import chapter_at
        g = chapter_at(3).start(seed=7)
        g.tick()
        spec = court.WHYS["slandered"]
        days = (55.0 - court.COALITION_LAPSE) / spec.decay
        self.assertLess(days, 360, "the Count's word outlives the year")


if __name__ == "__main__":
    unittest.main()
