"""What you are, as distinct from who you are.

The house changes your bonuses. It has never changed your *situation*: every
game opened with one hill, a full treasury and nobody's permission needed,
and the only question was how you spent three years. A role is a different
place to be standing on the same map, built out of what the game already
does -- a role that needed a new mechanic would be one I could not test.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from marchlands import roles
from marchlands.military import host_upkeep
from marchlands.scenarios import start


def played(role, seed=7, days=0, scenario="marchlands"):
    g = start(scenario, seed=seed, role=role)
    if days:
        g.advance(days)
    return g


class TestEachRoleIsADifferentPosition(unittest.TestCase):
    def test_every_role_says_what_it_is_and_what_its_problem_is(self):
        for r in roles.ROLES.values():
            self.assertTrue(r.blurb, r.key)
            self.assertTrue(r.problem, r.key)
            self.assertTrue(r.paths, r.key)

    def test_a_lord_is_the_game_as_it_always_opened(self):
        plain = start("marchlands", seed=7)
        lord = played("lord")
        self.assertEqual(plain.treasury, lord.treasury)
        self.assertEqual(sum(plain.home().units.values()),
                         sum(lord.home().units.values()))

    def test_a_merchant_has_the_carts_and_not_the_spears(self):
        lord, merchant = played("lord"), played("merchant")
        self.assertGreater(len(merchant.caravans), len(lord.caravans))
        self.assertLess(sum(merchant.home().units.values()),
                        sum(lord.home().units.values()))
        self.assertGreater(merchant.treasury, lord.treasury)

    def test_a_merchant_earns_his_carts_rather_than_being_given_the_rule(self):
        # The limit on trains is bought by building for it. Bending the rule
        # for the role would have been a rule that applies to everybody but
        # the player.
        merchant = played("merchant")
        self.assertGreaterEqual(merchant.caravan_limit, len(merchant.caravans))
        self.assertGreater(merchant.home().count("trading_post"), 0)

    def test_a_captain_has_the_company_and_not_the_coin(self):
        lord, captain = played("lord"), played("mercenary")
        self.assertGreater(sum(captain.home().units.values()),
                           sum(lord.home().units.values()) * 3)
        self.assertLess(captain.treasury, lord.treasury)

    def test_a_captains_company_does_not_bankrupt_him_for_existing(self):
        # It did: a hundred and ten men cost 106 a day against 60 in tax, on
        # thirteen days of runway. That is not a hard opening, it is a
        # decided one, and raiding does not close a gap that size.
        captain = played("mercenary")
        seat = captain.home()
        self.assertLess(host_upkeep(seat.units), seat._taxes(),
                        "the company eats more than the village makes")

    def test_and_he_survives_doing_nothing_long_enough_to_do_something(self):
        for seed in (3, 7, 11):
            g = played("mercenary", seed=seed, days=300)
            self.assertNotIn("Ruined", g.over or "", f"seed {seed}")

    def test_a_vassal_starts_under_somebody(self):
        vassal = played("vassal")
        self.assertTrue(vassal.liege)
        liege = vassal.world.towns[vassal.liege]
        self.assertGreater(liege.truce_days, 0)
        self.assertEqual(liege.hostility, 0.0)
        self.assertIn(vassal.world.node_name(vassal.liege), vassal.briefing)

    def test_a_king_starts_with_more_and_is_resented_for_it(self):
        lord, king = played("lord"), played("king")
        self.assertGreater(sum(1 for t in king.world.towns.values() if t.mine),
                           sum(1 for t in lord.world.towns.values() if t.mine))
        hate = lambda g: sum(t.hostility for t in g.world.towns.values()
                             if not t.mine)
        self.assertGreater(hate(king), hate(lord))

    def test_a_merchant_is_not_asked_to_conquer(self):
        self.assertEqual(played("merchant").goals.paths, ("wealth",))

    def test_the_briefing_says_what_your_problem_is(self):
        for key in roles.ROLES:
            g = played(key)
            self.assertGreater(len(g.briefing), 80, key)


class TestARoleTravels(unittest.TestCase):
    def test_it_survives_a_save(self):
        g = played("vassal", days=30)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "g.save")
            g.save(path)
            back = type(g).load(path)
        self.assertEqual(back.role, "vassal")
        self.assertEqual(back.liege, g.liege)

    def test_an_old_save_without_one_is_a_lord(self):
        g = start("marchlands", seed=7)
        self.assertEqual(g.role, "lord")

    def test_a_role_that_does_not_exist_is_refused_at_the_door(self):
        with self.assertRaises(KeyError):
            start("marchlands", role="nonesuch")

    def test_every_role_plays_on_every_scenario_that_takes_one(self):
        from marchlands.scenarios import SCENARIOS
        for key in roles.ROLES:
            for scenario in ("marchlands", "salt_road"):
                g = start(scenario, seed=5, role=key)
                g.advance(20)
                self.assertTrue(g.day >= 20, f"{key} on {scenario}")


if __name__ == "__main__":
    unittest.main()
