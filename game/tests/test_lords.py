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
        # Across a few marches rather than one: whether a given lord's host
        # is big enough on a given day is a roll, and one seed's quiet decade
        # is not the rule being broken.
        taken = 0
        for seed in (5, 1, 3):
            g = new_game(seed=seed)
            g.treasury = 60_000
            for _ in range(C.GOAL_DAYS):
                g.treasury = max(g.treasury, 60_000)
                for m in g.tick():
                    if "has fallen to" in m:
                        taken += 1
                if g.over:
                    break
            if taken:
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

    def test_a_holding_with_no_soldiers_does_not_last(self):
        """Raiders burn the country, and the country is what feeds the town.

        This is the test the vassal one above leans on: an undefended holding
        now dies inside a couple of years, which is why that test has to prop
        the player up to observe anything else.
        """
        g = new_game(seed=5)
        for s in g.world.settlements.values():
            s.units = {}
        for _ in range(C.GOAL_DAYS):
            for s in g.world.settlements.values():
                s.units = {}
            g.tick()
            if g.over:
                break
        self.assertNotEqual(g.over, "", "nobody ever came for an open town")

    def test_a_vassal_you_cannot_overawe_revolts(self):
        """No force anywhere near it, and the oath goes.

        The holding is propped up deliberately. A settlement with no soldiers
        at all now dies inside a year -- raiders burn the country and the town
        with it -- and a dead player stops the clock before the vassal has
        finished making its mind up. What is under test here is the oath, not
        whether an undefended holding survives; it does not, and there is a
        test for that of its own.
        """
        g = new_game(seed=5)
        g.world.towns["dunmere"].owner = "player"
        for s in g.world.settlements.values():
            s.units = {}
        for _ in range(C.GOAL_DAYS):
            for s in g.world.settlements.values():
                s.units = {}                       # still nothing to hold it with
                s.population = max(s.population, 120.0)
                s.popularity = max(s.popularity, 45.0)
            g.treasury = max(g.treasury, 4_000.0)
            g.tick()
            if not g.world.towns["dunmere"].mine:
                break
        self.assertEqual(g.over, "", "the holding died before the vassal decided")
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


class TestEachLordBuildsHisOwnCastle(unittest.TestCase):
    """The thing people remember about Stronghold's villains is not that they
    said different lines. It is that the Rat's castle and the Wolf's castle
    are different problems, and you take them differently.

    This game had the first half and not the second: `works()` read the
    castle off wealth alone, so the Heron -- who does nothing but build --
    and the Boar -- who builds nothing -- had the identical wall at the
    identical prosperity, and every siege was the same siege.
    """

    def town(self, sort_key, base=700.0):
        """A town of a given sort, at a fixed wealth, so only the lord differs."""
        from marchlands.world import ForeignTown
        from marchlands.market import Market
        from marchlands import lords as lordly
        key = next(k for k, v in lordly.CAST.items() if v == sort_key)
        t = ForeignTown(key=key, name=key.title(), x=0.0, y=0.0, market=Market(key))
        t.wall_base, t.prosperity = base, 1.0
        return t

    def test_the_same_money_buys_different_castles(self):
        shapes = {}
        for sort_key in ("boar", "heron", "fox", "ox", "magpie", "wolf"):
            w = self.town(sort_key).works()
            # `naked` counts: it is the flanking coverage, and the single
            # number the escalade code reads to decide whether a ladder goes
            # up unwatched. Two lords with the same tower count and different
            # coverage are two different castles to storm.
            shapes[sort_key] = (w.moat, w.towers, w.naked, w.depth, w.stone,
                                w.pitch + w.pits + w.oil)
        self.assertEqual(len(set(shapes.values())), len(shapes),
                         f"two lords built the same castle: {shapes}")

    def test_the_boar_spends_on_men_and_it_shows_on_his_wall(self):
        boar, heron = self.town("boar").works(), self.town("heron").works()
        self.assertLess(boar.towers, heron.towers)
        self.assertLessEqual(boar.moat, heron.moat)
        self.assertLess(boar.depth, heron.depth)

    def test_a_wall_with_no_towers_is_the_most_naked_thing_there_is(self):
        # The siege reads `1 - naked/8` as how watched a wall is, so writing
        # zero here -- the tempting thing to write -- would have made a castle
        # with nothing on it the hardest in the game to put a ladder against.
        from marchlands.castle import ESCALADE
        bare = self.town("boar", base=260.0).works()
        self.assertEqual(bare.towers, 0)
        self.assertGreaterEqual(bare.naked, 8)
        self.assertNotIn("tower", " ".join(bare.answers(ESCALADE)))

    def test_the_ox_has_no_ditch_to_stop_a_mine(self):
        from marchlands.castle import SAP
        ox = self.town("ox").works()
        self.assertFalse(ox.moat)
        self.assertFalse(any("ditch" in a for a in ox.answers(SAP)))

    def test_the_heron_has_one_and_it_stops_the_mine(self):
        from marchlands.castle import SAP
        heron = self.town("heron", base=1100.0).works()
        self.assertTrue(heron.moat)
        self.assertTrue(any("ditch" in a for a in heron.answers(SAP)))

    def test_the_magpie_buys_what_shows_and_nothing_behind_it(self):
        magpie, wolf = self.town("magpie").works(), self.town("wolf").works()
        self.assertGreaterEqual(magpie.towers, wolf.towers)
        self.assertLess(magpie.depth, wolf.depth)

    def test_every_lord_answers_at_least_one_approach_differently(self):
        from marchlands.castle import PLANS
        seen = {}
        for sort_key in ("boar", "heron", "fox", "ox", "magpie", "wolf"):
            w = self.town(sort_key).works()
            seen[sort_key] = tuple(tuple(w.answers(p)) for p in PLANS)
        self.assertEqual(len(set(seen.values())), len(seen))

    def test_a_poor_lord_still_cannot_build_what_he_would_like(self):
        # The style is how he spends, not free money. A Heron with an abbey's
        # income has an abbey's wall.
        poor = self.town("heron", base=200.0).works()
        rich = self.town("heron", base=1400.0).works()
        self.assertLess(poor.towers, rich.towers)
        self.assertLessEqual(poor.moat, rich.moat)

    def test_what_you_see_is_the_castle_you_last_looked_at(self):
        t = self.town("wolf")
        now = t.works()
        t.prosperity = 3.0                     # he has been building
        self.assertEqual(t.works(1.0), now, "you saw the old wall, not the new")
        self.assertNotEqual(t.works(), now)
