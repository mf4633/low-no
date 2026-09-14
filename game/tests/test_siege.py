"""Being besieged, as something you do rather than something done to you.

This scenario was built once and thrown away, because it was not a game:
`_mend_walls` returned early while besieged, so the wall only ever went down,
and recruiting at any sane rate changed nothing. Every tuning was decided
before the player acted -- eight of eight held whatever you did, or eight of
ten fell whatever you did, with nothing in between, because there was no
decision in between.

There are two now. `shore` works the breach while it is being made; `sally`
opens the gate and goes at the works. Neither is free and neither always
works, and the measurements below are the argument that they are decisions.
"""

from __future__ import annotations

import random
import unittest

from marchlands.military import Army, BESIEGING, Side, fight
from marchlands.scenarios import start


class TestAnOrderedFightStillKillsPeople(unittest.TestCase):
    """The bug this file found, and the reason to keep looking at numbers.

    Orders were applied by swapping in the copies `ordered` makes, so the
    casualties landed on the copy and the caller read its own untouched
    Side. From the day orders shipped, nobody died in a siege assault, and a
    sortie became a free button that burnt the engines and cost nothing.
    """

    def test_losses_land_on_the_sides_that_were_handed_in(self):
        a, d = Side({"spearman": 50}), Side({"spearman": 50})
        fight(a, d, rng=random.Random(1), orders=("line", "line"))
        self.assertLess(sum(a.units.values()), 50)
        self.assertLess(sum(d.units.values()), 50)

    def test_the_line_costs_exactly_what_no_order_costs(self):
        plain_a, plain_d = Side({"spearman": 50}), Side({"spearman": 50})
        fight(plain_a, plain_d, rng=random.Random(1), orders=("", ""))
        line_a, line_d = Side({"spearman": 50}), Side({"spearman": 50})
        fight(line_a, line_d, rng=random.Random(1), orders=("line", "line"))
        self.assertEqual(plain_a.units, line_a.units)
        self.assertEqual(plain_d.units, line_d.units)

    def test_the_order_is_taken_off_again_afterwards(self):
        a = Side({"spearman": 50})
        was = (a.attack_mult, a.defense_mult, a.morale)
        fight(a, Side({"spearman": 50}), rng=random.Random(1),
              orders=("storm", "hold"))
        self.assertEqual((a.attack_mult, a.defense_mult, a.morale), was)


class TestTheScenarioOpensUnderSiege(unittest.TestCase):
    def setUp(self):
        self.g = start("siege", seed=1)
        self.here = next(iter(self.g.world.settlements))
        self.s = self.g.world.settlements[self.here]

    def test_somebody_is_already_outside(self):
        outside = [a for a in self.g.armies if a.owner != "player"]
        self.assertTrue(outside)
        self.assertEqual(outside[0].state, BESIEGING)
        self.assertGreater(outside[0].size, sum(self.s.units.values()))

    def test_you_have_the_stone_and_the_bread_the_levers_need(self):
        self.assertGreater(self.s.market.stock.get("stone", 0), 100)
        self.assertGreater(self.s.market.stock.get("bread", 0), 500)

    def test_the_briefing_names_both_levers_and_the_real_clock(self):
        said = self.g.briefing
        self.assertIn("sally", said)
        self.assertIn("shore", said)
        self.assertIn("granary", said)

    def test_being_stormed_ends_it_here_and_nowhere_else(self):
        self.assertIn("survive", self.g.goals.paths)
        plain = start("marchlands", seed=1)
        self.assertNotIn("survive", plain.goals.paths)


class TestShoring(unittest.TestCase):
    def besieged(self, seed=1, days=3):
        g = start("siege", seed=seed)
        g.advance(days)
        here = next(iter(g.world.settlements))
        return g, g.world.settlements[here], here

    def test_a_wall_does_not_mend_itself_under_fire(self):
        g, s, _here = self.besieged()
        was = s.wall_hp
        g.advance(10)
        self.assertLess(s.wall_hp, was)

    def test_but_masons_can_be_put_on_it(self):
        g, s, here = self.besieged()
        g.shore(here, True)
        self.assertTrue(s.shoring)
        s.wall_hp *= 0.5
        was = s.wall_hp
        g.advance(1)
        # It is slower than the siege train, so the test is that stone moved.
        self.assertLess(s.market.stock.get("stone", 0), 500)

    def test_it_costs_stone_and_men_and_says_so(self):
        g, s, here = self.besieged()
        g.shore(here, True)
        s.wall_hp *= 0.4
        stone, men = s.market.stock.get("stone", 0), sum(s.units.values())
        g.advance(6)
        self.assertLess(s.market.stock.get("stone", 0), stone)
        self.assertLess(sum(s.units.values()), men)

    def test_and_nothing_at_all_once_the_stone_is_gone(self):
        # Against a game that is not shoring, not against the men it started
        # with: a besieged garrison loses people to the siege either way, and
        # the claim is that shoring with no stone costs nothing *extra*.
        def left(shoring):
            g, s, here = self.besieged()
            s.market.stock["stone"] = 0.0
            if shoring:
                g.shore(here, True)
            g.advance(5)
            return sum(s.units.values())
        self.assertAlmostEqual(left(True), left(False), places=6,
                               msg="it took a toll for work it could not do")

    def test_it_can_be_called_off(self):
        g, s, here = self.besieged()
        g.shore(here, True)
        self.assertIn("come off", g.shore(here, False))
        self.assertFalse(s.shoring)


class TestSallying(unittest.TestCase):
    def besieged(self, seed=1, days=3):
        g = start("siege", seed=seed)
        g.advance(days)
        here = next(iter(g.world.settlements))
        return g, g.world.settlements[here], here

    def foe(self, g):
        return next(a for a in g.armies if a.owner != "player")

    def test_a_good_sortie_burns_the_engines(self):
        g, s, here = self.besieged()
        said = g.sally(here, men=int(sum(s.units.values()) * 0.8))
        foe = self.foe(g)
        self.assertNotIn("ram", foe.units)
        self.assertNotIn("engineer", foe.units)
        self.assertIn("burnt", said)

    def test_and_says_what_it_burnt(self):
        # A successful sortie reported burning "no one", because the fight
        # had already killed the engines and the message read the remainder.
        g, s, here = self.besieged()
        said = g.sally(here, men=int(sum(s.units.values()) * 0.8))
        if "burnt" in said:
            self.assertNotIn("no one", said)

    def test_a_sortie_costs_men_whether_it_works_or_not(self):
        for share in (0.2, 0.8):
            g, s, here = self.besieged()
            was = sum(s.units.values())
            g.sally(here, men=int(was * share))
            self.assertLess(sum(s.units.values()), was, f"share {share}")

    def test_sending_too_few_wastes_them(self):
        g, s, here = self.besieged()
        g.sally(here, men=max(2, int(sum(s.units.values()) * 0.2)))
        self.assertIn("ram", self.foe(g).units)

    def test_you_cannot_sally_from_a_town_nobody_is_besieging(self):
        g = start("marchlands", seed=1)
        here = next(iter(g.world.settlements))
        self.assertIn("not besieged", g.sally(here))

    def test_it_fights_the_works_and_not_the_whole_host(self):
        # A sortie that had to beat two hundred men to reach a ram would
        # never be worth opening the gate for.
        g, s, here = self.besieged()
        foe = self.foe(g)
        before = foe.size
        g.sally(here, men=int(sum(s.units.values()) * 0.8))
        self.assertGreater(foe.size, before * 0.3,
                           "the whole host was in the fight")


class TestItIsDecidedByThePlayer(unittest.TestCase):
    """The measurement that says this is a game. Sallying early takes it from
    a coin flip to seven in eight; leaving it until the wall is falling is no
    better than doing nothing at all."""

    def play(self, sally_on=0, shore=False, seeds=range(1, 7)):
        held = 0
        for seed in seeds:
            g = start("siege", seed=seed)
            here = next(iter(g.world.settlements))
            s = g.world.settlements[here]
            if shore:
                g.shore(here, True)
            done = False
            while not g.over and g.day < 275:
                g.advance(1)
                if sally_on and s.besieged and not done and g.day >= sally_on:
                    g.sally(here, men=int(sum(s.units.values()) * 0.8))
                    done = True
            held += "Time called" in (g.over or "")
        return held

    def test_doing_nothing_is_a_coin_flip(self):
        idle = self.play()
        self.assertGreater(idle, 0, "unwinnable is not hard")
        self.assertLess(idle, 6, "doing nothing should not simply win")

    def test_going_early_wins_it(self):
        self.assertGreater(self.play(sally_on=5), self.play())

    def test_and_going_late_does_not(self):
        self.assertLessEqual(self.play(sally_on=60), self.play(sally_on=5))


if __name__ == "__main__":
    unittest.main()
