"""The whole machine: ticks, money, endings, and saves."""

import json
import math
import os
import tempfile
import unittest

from marchlands import config as C
from marchlands.engine import GameState
from marchlands.goods import ALL_KEYS
from marchlands.scenario import new_game
from marchlands.sim import Bot


class TestCalendar(unittest.TestCase):
    def test_the_game_opens_in_spring(self):
        g = new_game()
        self.assertEqual(g.month, C.START_MONTH)
        self.assertEqual(g.season, C.SEASON_OF_MONTH[C.START_MONTH])

    def test_a_year_comes_round(self):
        g = new_game()
        g.advance(C.DAYS_PER_YEAR)
        self.assertEqual(g.month, C.START_MONTH)
        self.assertEqual(g.year, C.START_YEAR + 1)


class TestLedger(unittest.TestCase):
    def test_the_ledger_explains_the_treasury(self):
        g = new_game(seed=2)
        for _ in range(30):
            before = g.treasury
            g.tick()
            self.assertAlmostEqual(g.treasury - before, g.ledger.net, places=6,
                                   msg=f"day {g.day} unaccounted for")

    def test_building_costs_coin_and_land(self):
        g = new_game()
        before = g.treasury
        msg = g.build("aldworth", "mill")
        self.assertIn("begun", msg)
        self.assertLess(g.treasury, before)

    def test_you_cannot_build_what_you_cannot_pay_for(self):
        g = new_game()
        g.treasury = 5.0
        self.assertIn("costs", g.build("aldworth", "armoury"))

    def test_caravans_are_limited_and_cost_coin(self):
        g = new_game()
        while True:
            c, why = g.new_caravan("aldworth")
            if c is None:
                break
            self.assertLess(len(g.caravans), 40)
        self.assertIn("caravans", why)
        self.assertEqual(len(g.caravans), g.caravan_limit)


class TestSettling(unittest.TestCase):
    def test_founding_takes_the_site_and_the_coin(self):
        g = new_game()
        g.treasury = 20000.0
        before = len(g.world.settlements)
        msg = g.found("sealow")
        self.assertIn("founded", msg)
        self.assertEqual(len(g.world.settlements), before + 1)
        self.assertNotIn("sealow", g.world.sites)
        self.assertIn("sealow", g.world.coords)

    def test_a_colony_can_be_reached(self):
        g = new_game()
        g.treasury = 20000.0
        g.found("greyfell")
        self.assertGreater(g.world.distance("aldworth", "greyfell"), 0)


class TestEndings(unittest.TestCase):
    def test_debt_ends_it(self):
        g = new_game()
        g.treasury = C.BANKRUPTCY_FLOOR - 500   # past saving by a day's takings
        g.tick()
        self.assertIn("Ruined", g.over)

    def test_the_goal_ends_it(self):
        g = new_game()
        g.treasury = C.GOAL_NET_WORTH * 2
        g.world.settlements["aldworth"].population = C.GOAL_POPULATION + 50
        g.tick()
        self.assertIn("Triumph", g.over)

    def test_the_clock_ends_it(self):
        g = new_game()
        g.day = C.GOAL_DAYS - 1
        g.tick()
        self.assertIn("Time called", g.over)


class TestSaves(unittest.TestCase):
    def test_round_trip_preserves_the_world(self):
        g = new_game(seed=3)
        Bot(g).run(60)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            g.save(path)
            h = GameState.load(path)
        self.assertEqual(h.day, g.day)
        self.assertAlmostEqual(h.treasury, g.treasury, places=6)
        self.assertAlmostEqual(h.net_worth(), g.net_worth(), places=4)
        self.assertEqual(sorted(h.world.settlements), sorted(g.world.settlements))
        for key, s in g.world.settlements.items():
            t = h.world.settlements[key]
            self.assertAlmostEqual(t.population, s.population, places=6)
            self.assertEqual(len(t.buildings), len(s.buildings))
            for k in ALL_KEYS:
                self.assertAlmostEqual(t.market.stock[k], s.market.stock[k], places=6)
        self.assertEqual(len(h.caravans), len(g.caravans))
        for a, b in zip(g.caravans, h.caravans):
            self.assertEqual(a.cargo, b.cargo)
            self.assertEqual(len(a.route), len(b.route))

    def test_a_save_is_plain_json(self):
        g = new_game()
        g.advance(5)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            g.save(path)
            with open(path) as fh:
                data = json.load(fh)
        self.assertEqual(data["version"], 1)


class TestLongRun(unittest.TestCase):
    def test_three_years_stay_finite_and_sane(self):
        g = new_game(seed=11)
        bot = Bot(g)
        bot.run(C.GOAL_DAYS)
        self.assertTrue(math.isfinite(g.treasury))
        self.assertTrue(math.isfinite(g.net_worth()))
        for s in g.world.settlements.values():
            self.assertGreaterEqual(s.population, 0.0)
            self.assertTrue(0.0 <= s.popularity <= 100.0)
            for k in ALL_KEYS:
                self.assertGreaterEqual(s.market.stock[k], -1e-9)
                self.assertTrue(math.isfinite(s.market.price(k)))
        for t in g.world.towns.values():
            for k in ALL_KEYS:
                self.assertGreaterEqual(t.market.stock[k], -1e-9)
                self.assertTrue(math.isfinite(t.market.price(k)))

    def test_the_naive_bot_survives_most_starts(self):
        """Balance guard: a plain policy should usually last the distance."""
        survived = 0
        for seed in (3, 7, 11, 19, 23):
            g = new_game(seed=seed)
            Bot(g).run(C.GOAL_DAYS)
            survived += "Ruined" not in g.over
        self.assertGreaterEqual(survived, 3, "the opening is too punishing")

    def test_the_naive_bot_does_not_walk_the_goal(self):
        """Balance guard: greed without judgement should not be enough."""
        won = 0
        for seed in (3, 7, 11):
            g = new_game(seed=seed)
            Bot(g).run(C.GOAL_DAYS)
            won += "Triumph" in g.over
        self.assertLessEqual(won, 1, "the goal is too easy")


if __name__ == "__main__":
    unittest.main()
