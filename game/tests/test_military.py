"""Soldiers, the counter triangle, walls, sieges and conquest."""

import random
import unittest

from marchlands import config as C
from marchlands.military import (UNITS, Side, describe, fight, host_speed,
                                 host_strength, host_upkeep, siege_day)
from marchlands.scenario import new_game


def rng():
    return random.Random(11)


class TestUnits(unittest.TestCase):
    def test_every_soldier_is_armed_from_a_good_you_can_make(self):
        from marchlands.buildings import producers_of
        from marchlands.goods import GOODS
        for u in UNITS.values():
            for g in u.equipment:
                self.assertIn(g, GOODS, u.key)
                self.assertTrue(producers_of(g) or GOODS[g].foreign_only, g)

    def test_a_host_marches_at_the_pace_of_its_slowest(self):
        self.assertEqual(host_speed({"knight": 5, "trebuchet": 1}),
                         UNITS["trebuchet"].speed)

    def test_upkeep_and_strength_scale_with_numbers(self):
        self.assertAlmostEqual(host_upkeep({"archer": 10}),
                               10 * UNITS["archer"].upkeep, places=6)
        self.assertGreater(host_strength({"knight": 10}), host_strength({"militia": 10}))

    def test_describe_reads_like_a_muster_roll(self):
        self.assertIn("Knight", describe({"knight": 3}))
        self.assertEqual(describe({}), "no one")


class TestTheTriangle(unittest.TestCase):
    """Spears break horse, horse rides down bows, bows cut up foot."""

    def duel(self, a, b, rounds=3):
        wins = 0
        for seed in range(rounds):
            atk, dfn = Side(dict(a)), Side(dict(b))
            res = fight(atk, dfn, rng=random.Random(seed))
            wins += res.winner == "attacker"
        return wins

    def test_spears_beat_horse(self):
        self.assertEqual(self.duel({"spearman": 60}, {"knight": 20}), 3)

    def test_horse_beats_bows(self):
        self.assertEqual(self.duel({"knight": 20}, {"archer": 60}), 3)

    def test_armoured_foot_beats_bows(self):
        self.assertGreaterEqual(self.duel({"man_at_arms": 40}, {"archer": 60}), 2)

    def test_numbers_still_matter(self):
        self.assertEqual(self.duel({"man_at_arms": 60}, {"man_at_arms": 10}), 3)

    def test_a_battle_ends_and_costs_both_sides(self):
        a, d = Side({"man_at_arms": 40}), Side({"man_at_arms": 40})
        res = fight(a, d, rng=rng())
        self.assertGreater(res.rounds, 1)
        self.assertTrue(res.attacker_losses)
        self.assertTrue(res.defender_losses)
        self.assertTrue(res.log)


class TestWalls(unittest.TestCase):
    def test_foot_cannot_storm_a_standing_wall(self):
        a, d = Side({"man_at_arms": 80}), Side({"archer": 10}, battlement=12)
        res = fight(a, d, wall_hp=800, rng=rng(), place="the keep")
        self.assertEqual(res.winner, "defender")
        self.assertEqual(res.wall_damage, 0.0)

    def test_engines_bring_a_wall_down(self):
        bes = Side({"ram": 4, "engineer": 8, "man_at_arms": 40})
        dfn = Side({"archer": 20}, battlement=10)
        wall, days = 900.0, 0
        while wall > 0 and days < 60:
            days += 1
            wall, _a, _d, _lines = siege_day(bes, dfn, wall, rng(), wall_max=900.0)
        self.assertGreater(wall, -1)
        self.assertLessEqual(wall, 0)
        self.assertLess(days, 40)

    def test_a_high_wall_shelters_its_garrison(self):
        losses = {}
        for intact in (1.0, 0.05):
            bes = Side({"archer": 60})
            dfn = Side({"spearman": 40}, battlement=8)
            before = dfn.alive()
            siege_day(bes, dfn, 900.0 * intact, random.Random(2), wall_max=900.0)
            losses[intact] = before - dfn.alive()
        self.assertLess(losses[1.0], losses[0.05])

    def test_a_siege_without_engines_makes_no_progress(self):
        bes = Side({"man_at_arms": 50})
        dfn = Side({"archer": 20}, battlement=10)
        wall, _a, _d, lines = siege_day(bes, dfn, 500.0, rng(), wall_max=500.0)
        self.assertEqual(wall, 500.0)
        self.assertIn("nothing to break stone", lines[0])


class TestRecruiting(unittest.TestCase):
    def setUp(self):
        self.g = new_game(seed=6)
        self.home = self.g.world.settlements["aldworth"]
        self.g.treasury = 20000

    def test_a_barracks_is_required(self):
        for b in list(self.home.buildings):
            if b.key == "barracks":
                self.home.demolish(b.uid)
        self.assertIn("no barracks", self.g.recruit("aldworth", "spearman", 1))

    def test_soldiers_need_arms_from_your_own_stores(self):
        self.home.market.stock["spears"] = 0.0
        self.assertIn("Spears", self.g.recruit("aldworth", "spearman", 2))

    def test_recruiting_spends_coin_arms_and_hands(self):
        g, home = self.g, self.home
        home.market.add("spears", 50)
        before_coin = g.treasury
        before_spears = home.market.stock["spears"]
        before_work = home.workforce
        self.assertIn("muster", g.recruit("aldworth", "spearman", 5))
        self.assertLess(g.treasury, before_coin)
        self.assertAlmostEqual(home.market.stock["spears"], before_spears - 5, places=4)
        self.assertEqual(home.workforce, before_work - 5)

    def test_later_soldiers_wait_on_the_age(self):
        self.home.market.add("weapons", 20)
        self.home.market.add("armour", 20)
        self.assertIn("age", self.g.recruit("aldworth", "man_at_arms", 1))

    def test_some_soldiers_wait_on_a_technology(self):
        g = self.g
        g.progress.age = 3
        self.home.market.add("bows", 20)
        self.home.market.add("armour", 20)
        self.assertIn("Crossbow", g.recruit("aldworth", "crossbowman", 1))
        g.progress.researched.add("crossbow")
        self.assertIn("muster", g.recruit("aldworth", "crossbowman", 1))

    def test_a_house_soldier_needs_that_house(self):
        g = new_game(seed=6, house="marcher")
        g.treasury = 20000
        home = g.world.settlements["aldworth"]
        home.market.add("spears", 30)
        home.market.add("armour", 30)
        g.progress.age = 2
        self.assertIn("muster", g.recruit("aldworth", "border_horse", 2))
        other = new_game(seed=6, house="abbey")
        other.treasury = 20000
        other.progress.age = 2
        other.world.settlements["aldworth"].market.add("spears", 30)
        other.world.settlements["aldworth"].market.add("armour", 30)
        self.assertIn("Border Horse needs", other.recruit("aldworth", "border_horse", 2))

    def test_a_town_cannot_arm_more_men_than_it_has(self):
        g, home = self.g, self.home
        g.treasury = 10_000_000
        home.market.add("spears", 9999)
        self.assertIn("spare hands", g.recruit("aldworth", "spearman", 10_000))


class TestCampaign(unittest.TestCase):
    def setUp(self):
        self.g = new_game(seed=6, house="marcher")
        self.g.treasury = 60000
        self.g.progress.age = 3
        home = self.g.world.settlements["aldworth"]
        home.population = 900
        for k, q in (("spears", 300), ("bows", 200), ("armour", 200),
                     ("weapons", 200), ("planks", 400), ("iron", 200), ("tools", 80)):
            home.market.add(k, q)

    def army_of(self, **units):
        for k, n in units.items():
            self.g.recruit("aldworth", k, n)
        a, why = self.g.raise_host("aldworth", units)
        self.assertIsNotNone(a, why)
        return a

    def test_raising_a_host_takes_men_out_of_the_garrison(self):
        self.g.recruit("aldworth", "spearman", 10)
        before = self.g.world.settlements["aldworth"].units["spearman"]
        a, why = self.g.raise_host("aldworth", {"spearman": 6})
        self.assertEqual(a.size, 6)
        self.assertEqual(self.g.world.settlements["aldworth"].units["spearman"],
                         before - 6)

    def test_you_cannot_march_men_you_do_not_have(self):
        a, why = self.g.raise_host("aldworth", {"knight": 40})
        self.assertIsNone(a)
        self.assertIn("only", why)

    def test_a_host_marches_besieges_and_takes_a_town(self):
        g = self.g
        a = self.army_of(spearman=20, archer=16, man_at_arms=14, engineer=6, ram=4)
        self.assertIn("marches", g.march(a.uid, "dunmere"))
        for _ in range(60):
            g.tick()
            if g.world.towns["dunmere"].mine or g.over:
                break
        self.assertTrue(g.world.towns["dunmere"].mine)
        self.assertEqual(g.world.tariff_for("dunmere", None), 0.0)
        g.tick()                       # tribute is collected from the next day
        self.assertGreater(g.ledger.tribute, 0.0)

    def test_taking_a_town_angers_the_rest(self):
        """Every other lord on the march takes note the day one bends the knee."""
        g = self.g
        others = [k for k in g.world.towns if k != "dunmere"]
        a = self.army_of(spearman=20, archer=16, man_at_arms=14, engineer=6, ram=4)
        g.march(a.uid, "dunmere")
        for _ in range(60):
            before = {k: g.world.towns[k].hostility for k in others}
            g.tick()
            if g.world.towns["dunmere"].mine:
                break
        after = {k: g.world.towns[k].hostility for k in others}
        jumps = [after[k] - before[k] for k in others]
        self.assertGreater(max(jumps), 15.0)

    def test_a_host_with_no_engines_gives_up(self):
        g = self.g
        a = self.army_of(spearman=30)
        g.march(a.uid, "ostmark")
        for _ in range(90):
            g.tick()
            if a.state in ("marching", "garrison") and a.at != "ostmark":
                break
        self.assertFalse(g.world.towns["ostmark"].mine)

    def test_dominion_ends_the_game(self):
        g = self.g
        for key in list(g.world.towns)[:C.GOAL_TOWNS]:
            g.world.towns[key].owner = "player"
        g.tick()
        self.assertIn("Dominion", g.over)


class TestDefence(unittest.TestCase):
    def test_a_storming_costs_the_keep_but_not_the_game(self):
        from marchlands.military import Army
        g = new_game(seed=8)
        home = g.world.settlements["aldworth"]
        home.wall_hp = 0.0
        home.units = {}
        host = Army(uid=99, name="Test host", owner="dunmere",
                    units={"man_at_arms": 60, "ram": 3, "engineer": 6},
                    at="aldworth", home="dunmere", state="besieging")
        g.armies.append(host)
        for _ in range(20):
            g.tick()
            if not any(b.key == "keep" for b in home.buildings):
                break
        self.assertFalse(any(b.key == "keep" for b in home.buildings))
        self.assertEqual(g.over, "")          # gutted, not finished

    def test_lords_grow_bolder_as_you_grow_richer(self):
        """Wealth is what brings a host over the hill, not the calendar."""
        wars = {}
        for label, purse in (("lean", 4_000), ("fat", 200_000)):
            g = new_game(seed=8)
            count = 0
            for _ in range(400):
                g.treasury = purse
                count += sum(m.startswith("WAR:") for m in g.tick())
            wars[label] = count
        self.assertGreater(wars["fat"], wars["lean"])


if __name__ == "__main__":
    unittest.main()
