"""The other lords: growth, ambition, diplomacy and oaths kept or broken."""

import random
import unittest

from marchlands import config as C
from marchlands.military import Army, host_strength
from marchlands.scenario import new_game


class TestGrowth(unittest.TestCase):
    def test_a_town_left_alone_becomes_a_harder_problem(self):
        g = new_game(seed=5)
        t = g.world.towns["ostmark"]
        before = (t.prosperity, t.wall_max, sum(t.garrison.values()),
                  host_strength(g.likely_host("ostmark")))
        rng = random.Random(1)
        for _ in range(C.DAYS_PER_YEAR * 2):
            t.grow(rng)
        after = (t.prosperity, t.wall_max, sum(t.garrison.values()),
                 host_strength(g.likely_host("ostmark")))
        for i, label in enumerate(("prosperity", "walls", "garrison", "muster")):
            self.assertGreater(after[i], before[i], label)

    def test_a_besieged_town_goes_backwards(self):
        g = new_game(seed=5)
        t = g.world.towns["ostmark"]
        rng = random.Random(1)
        for _ in range(200):
            t.grow(rng, besieged=True)
        self.assertLess(t.prosperity, 1.0)

    def test_prosperity_is_bounded(self):
        g = new_game(seed=5)
        t = g.world.towns["dunmere"]
        rng = random.Random(1)
        for _ in range(20_000):
            t.grow(rng)
        self.assertLessEqual(t.prosperity, 2.3)


class TestRivalWars(unittest.TestCase):
    def test_lords_march_on_each_other(self):
        """Left to itself the march rearranges: somebody swallows a neighbour."""
        g = new_game(seed=5)
        g.treasury = 60_000
        taken = 0
        for _ in range(C.GOAL_DAYS):
            g.treasury = max(g.treasury, 60_000)
            for m in g.tick():
                if "has fallen to" in m:
                    taken += 1
            if g.over:
                break
        self.assertGreater(taken, 0, "no lord ever moved against another")
        self.assertTrue(any(t.owner not in ("", "player") for t in g.world.towns.values()))

    def test_rival_wars_are_capped(self):
        g = new_game(seed=5)
        g.treasury = 60_000
        worst = 0
        for _ in range(600):
            g.treasury = max(g.treasury, 60_000)
            g.tick()
            rival = sum(1 for a in g.armies
                        if a.owner != "player" and a.bound_for in g.world.towns)
            worst = max(worst, rival)
        self.assertLessEqual(worst, g.MAX_RIVAL_WARS)

    def test_a_beaten_host_thickens_the_garrison_it_came_from(self):
        g = new_game(seed=5)
        town = g.world.towns["dunmere"]
        before = sum(town.garrison.values())
        host = Army(uid=99, name="probe", owner="dunmere", units={"spearman": 10},
                    at="dunmere", home="dunmere", state="marching",
                    bound_for="dunmere", days_left=1)
        g.armies.append(host)
        g.tick()
        self.assertGreaterEqual(sum(town.garrison.values()), before + 9)
        self.assertNotIn(host, g.armies)


class TestDiplomacy(unittest.TestCase):
    def setUp(self):
        self.g = new_game(seed=5)
        self.g.treasury = 40_000
        self.town = self.g.world.towns["ostmark"]
        self.town.hostility = 90.0

    def test_a_gift_cools_a_temper_and_costs_coin(self):
        before_coin = self.g.treasury
        msg = self.g.gift("ostmark", 2000)
        self.assertIn("cools", msg)
        self.assertLess(self.town.hostility, 90.0)
        self.assertAlmostEqual(self.g.treasury, before_coin - 2000, places=4)

    def test_you_cannot_gift_what_you_do_not_have(self):
        self.g.treasury = 10
        self.assertIn("you have", self.g.gift("ostmark", 5000))

    def test_a_truce_holds_the_lord_off(self):
        self.g.truce("ostmark", 200)
        self.assertGreater(self.town.truce_days, 0)
        before = self.town.hostility
        for _ in range(60):
            self.g.tick()
        self.assertLessEqual(self.town.hostility, before + 1e-6)

    def test_a_truce_costs_more_from_a_greater_lord(self):
        g = self.g
        self.assertGreater(g.truce_cost("marchand", 100), g.truce_cost("dunmere", 100))

    def test_a_demand_needs_a_bigger_stick(self):
        g = self.g
        self.assertIn("laughs", g.demand("dunmere"))
        g.world.settlements["aldworth"].units = {"knight": 80, "man_at_arms": 80}
        before = g.treasury
        self.assertIn("pays", g.demand("dunmere"))
        self.assertGreater(g.treasury, before)

    def test_a_demand_is_remembered(self):
        g = self.g
        g.world.settlements["aldworth"].units = {"knight": 80, "man_at_arms": 80}
        before = g.world.towns["dunmere"].hostility
        g.demand("dunmere")
        self.assertGreater(g.world.towns["dunmere"].hostility, before)


class TestOaths(unittest.TestCase):
    def test_a_captured_town_keeps_a_garrison_behind(self):
        g = new_game(seed=6)
        g.treasury = 60_000
        g.progress.age = 3
        home = g.world.settlements["aldworth"]
        home.population = 900
        for k, q in (("spears", 300), ("bows", 200), ("armour", 200),
                     ("weapons", 200), ("planks", 400), ("iron", 200)):
            home.market.add(k, q)
        for k, n in (("spearman", 30), ("archer", 20), ("man_at_arms", 16),
                     ("engineer", 6), ("ram", 4)):
            g.recruit("aldworth", k, n)
        a, why = g.raise_host("aldworth", {"spearman": 30, "archer": 20,
                                           "man_at_arms": 16, "engineer": 6, "ram": 4})
        self.assertIsNotNone(a, why)
        g.march(a.uid, "dunmere")
        for _ in range(60):
            g.tick()
            if g.world.towns["dunmere"].mine:
                break
        town = g.world.towns["dunmere"]
        self.assertTrue(town.mine)
        self.assertGreater(sum(town.garrison.values()), 0,
                           "a town taken and walked away from is not held")
        self.assertGreater(town.wall_hp, 0)

    def test_a_vassal_you_cannot_overawe_revolts(self):
        g = new_game(seed=5)
        g.world.towns["dunmere"].owner = "player"
        for s in g.world.settlements.values():
            s.units = {}
        for _ in range(C.GOAL_DAYS):
            g.tick()
            if not g.world.towns["dunmere"].mine:
                break
        self.assertFalse(g.world.towns["dunmere"].mine)

    def test_a_garrison_holds_a_vassal(self):
        g = new_game(seed=5)
        g.world.towns["dunmere"].owner = "player"
        g.world.settlements["aldworth"].units = {"knight": 60, "man_at_arms": 60}
        for _ in range(400):
            g.tick()
            g.world.settlements["aldworth"].units = {"knight": 60, "man_at_arms": 60}
        self.assertTrue(g.world.towns["dunmere"].mine)


if __name__ == "__main__":
    unittest.main()
