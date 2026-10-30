"""What a host eats, and what happens on the day it does not.

An army in the field used to be a payroll line and nothing else. It cost
coin every morning and it never once ate, so a host could sit in front of a
wall for a year at no cost but wages, and marching to the far end of the map
was exactly as cheap as standing in your own gate. For most of the period
the thing that ended a campaign was not a battle and not money, it was
October.
"""

from __future__ import annotations

import unittest

from marchlands import supply
from marchlands.scenarios import start
from marchlands.scenario import drawn_game


RICH = {"fertile": 9, "forest": 5, "coast": 0}
FEN = {"fertile": 1, "forest": 1, "marsh": 9}


class TestWhatTheCountryGives(unittest.TestCase):
    def test_a_fen_does_not_feed_an_army(self):
        self.assertGreater(supply.yield_at(RICH, "summer"),
                           5 * supply.yield_at(FEN, "summer"))

    def test_october_is_the_campaigning_season_and_january_is_not(self):
        best = supply.yield_at(RICH, "autumn")
        worst = supply.yield_at(RICH, "winter")
        self.assertGreater(best, 3 * worst)

    def test_a_country_is_eaten_out_by_sitting_in_it(self):
        grazed = 0.0
        first = supply.yield_at(RICH, "summer", grazed)
        for _ in range(30):
            _r, _s, grazed = supply.eat(120, 1e6, ground=RICH, season="summer",
                                        grazed=grazed)
        self.assertLess(supply.yield_at(RICH, "summer", grazed), first * 0.5)

    def test_but_never_to_nothing(self):
        """A cliff at zero turns a siege from a race into a countdown with a
        fixed answer, and there is always a late field somewhere."""
        self.assertGreater(supply.yield_at(RICH, "summer", 1.0), 0.0)
        self.assertGreater(supply.yield_at(RICH, "summer", 99.0), 0.0)

    def test_and_it_comes_back_when_nobody_is_eating_it(self):
        grazed = 0.9
        for _ in range(40):
            grazed = supply.recover(grazed)
        self.assertLess(grazed, 0.4)

    def test_a_small_host_can_sit_where_a_big_one_cannot(self):
        def stands(men, days=45):
            stores, grazed, left = supply.capacity(men), 0.0, float(men)
            for _ in range(days):
                r, stores, grazed = supply.eat(left, stores, ground=RICH,
                                               season="summer", grazed=grazed)
                left -= r.deserted
            return left / men
        self.assertGreater(stands(40), stands(240))


class TestTheRoadHome(unittest.TestCase):
    def test_carts_cannot_catch_a_moving_army(self):
        self.assertGreater(supply.convoy_share(90, settled=True),
                           supply.convoy_share(90, settled=False))

    def test_a_camp_can_be_supplied_much_further_than_a_march(self):
        """Supply disarmed every siege in the game that was not next door
        until this: a lord's second host arrived with its baggage eaten on
        the road and came apart outside the wall."""
        self.assertEqual(supply.convoy_share(200), 0.0)
        self.assertGreater(supply.convoy_share(200, settled=True), 0.25)

    def test_standing_in_the_gate_is_fully_supplied(self):
        self.assertEqual(supply.convoy_share(0.0), 1.0)


class TestAHostInThePlay(unittest.TestCase):
    def raise_one(self, g, men=90):
        home = next(iter(g.world.settlements))
        s = g.world.settlements[home]
        s.units = {"spearman": men * 2 // 3, "archer": men // 3}
        a, why = g.raise_host(home, dict(s.units))
        self.assertIsNotNone(a, why)
        return home, a

    def test_a_host_marches_out_of_the_granary_it_was_raised_in(self):
        g = start("marchlands", seed=3)
        home, a = self.raise_one(g)
        self.assertGreater(supply.days_left(a.size, a.stores), 5)

    def test_and_the_town_paid_for_it(self):
        g = start("marchlands", seed=3)
        home = next(iter(g.world.settlements))
        s = g.world.settlements[home]
        from marchlands.goods import RATION_GOODS, good
        before = sum(s.market.stock.get(k, 0.0) * good(k).nourish
                     for k in RATION_GOODS)
        self.raise_one(g)
        after = sum(s.market.stock.get(k, 0.0) * good(k).nourish
                    for k in RATION_GOODS)
        self.assertLess(after, before, "the baggage came out of nowhere")

    def test_but_it_does_not_empty_the_larder(self):
        """A host that ate the town on its way through the gate would be a
        tax on raising one at all."""
        g = start("marchlands", seed=3)
        home = next(iter(g.world.settlements))
        s = g.world.settlements[home]
        for _ in range(3):
            s.units = {"spearman": 60, "archer": 30}
            g.raise_host(home, dict(s.units))
        from marchlands.goods import RATION_GOODS, good
        left = sum(s.market.stock.get(k, 0.0) * good(k).nourish
                   for k in RATION_GOODS)
        self.assertGreater(left, 0.20 * s.population * 4)

    def test_their_hosts_march_out_loaded_too(self):
        """An AI that starves itself is not an opponent. Every lord in the
        game set out with an empty baggage train until this."""
        g = start("marchlands", seed=3)
        for _ in range(400):
            g.advance(1)
            theirs = [a for a in g.armies if a.owner != "player" and a.size > 20]
            if theirs:
                self.assertGreater(max(a.stores for a in theirs), 0.0)
                return
        self.skipTest("no lord raised a host to look at")

    def test_a_garrison_at_home_is_not_charged_twice(self):
        """The town already feeds its soldiers -- they are counted in the
        population that eats."""
        g = start("marchlands", seed=3)
        home, a = self.raise_one(g)
        before = a.stores
        for _ in range(20):
            g.advance(1)
        self.assertEqual(a.at, home)
        self.assertEqual(a.stores, before)
        self.assertEqual(a.fed, "in quarters")

    def test_marching_across_the_map_costs_you_the_host(self):
        g = start("marchlands", seed=3)
        home, a = self.raise_one(g)
        far = max(g.world.towns, key=lambda k: g.world.distance(home, k))
        started = a.size
        g.march(a.uid, far)
        for _ in range(60):
            g.advance(1)
            if a not in g.armies:
                break
        self.assertLess(a.size, started * 0.8,
                        "a host crossed the map and never missed a meal")

    def test_and_the_country_it_crossed_remembers(self):
        g = start("marchlands", seed=3)
        home, a = self.raise_one(g)
        far = max(g.world.towns, key=lambda k: g.world.distance(home, k))
        g.march(a.uid, far)
        for _ in range(40):
            g.advance(1)
        self.assertTrue(any(v > 0.1 for v in g.world.grazed.values()),
                        "a host ate its way across the map and left it untouched")

    def test_the_grazing_survives_a_save(self):
        from marchlands.engine import GameState
        g = drawn_game(seed=5)
        g.world.grazed["somewhere"] = 0.42
        again = GameState.from_dict(g.to_dict())
        self.assertAlmostEqual(again.world.grazed["somewhere"], 0.42)

    def test_and_so_does_the_baggage(self):
        from marchlands.engine import GameState
        g = start("marchlands", seed=3)
        _home, a = self.raise_one(g)
        again = GameState.from_dict(g.to_dict())
        self.assertAlmostEqual(again.army(a.uid).stores, a.stores)


class TestSomewhereToReadIt(unittest.TestCase):
    def test_the_panel_says_it_before_you_starve_rather_than_after(self):
        g = start("marchlands", seed=3)
        home = next(iter(g.world.settlements))
        s = g.world.settlements[home]
        s.units = {"spearman": 60, "archer": 30}
        a, _ = g.raise_host(home, dict(s.units))
        far = max(g.world.towns, key=lambda k: g.world.distance(home, k))
        g.march(a.uid, far)
        g.advance(3)
        from marchlands.web import march
        view = march(g, home)["hosts"][0]["supply"]
        for key in ("days", "feeds", "forage", "need", "larder", "from_home"):
            self.assertIn(key, view)
        self.assertGreater(view["days"], 0)


if __name__ == "__main__":
    unittest.main()
