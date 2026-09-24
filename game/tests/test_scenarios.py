"""Five scenarios, five sets of terms."""

import os
import tempfile
import unittest

from marchlands import config as C
from marchlands.engine import GameState
from marchlands.scenarios import (CAMPAIGN, OUTSIDE_CAMPAIGN, SCENARIOS,
                                  scenario, start)
from marchlands.sim import Bot


class TestRegistry(unittest.TestCase):
    def test_every_scenario_is_placed_exactly_once(self):
        """In the campaign or deliberately outside it -- but placed. The point
        of the test is that adding a scenario cannot orphan it; the point of
        the second list is that leaving one out has to be a decision somebody
        wrote down rather than a line nobody got to."""
        self.assertEqual(sorted(CAMPAIGN + OUTSIDE_CAMPAIGN), sorted(SCENARIOS))
        self.assertFalse(set(CAMPAIGN) & set(OUTSIDE_CAMPAIGN))

    def test_the_campaign_is_an_order_with_an_ending(self):
        """Everything in the sequence has a clock. Freebuild does not, which
        is exactly why it is not in it."""
        for key in CAMPAIGN:
            self.assertLess(SCENARIOS[key].years, 10, key)

    def test_an_unknown_scenario_is_refused(self):
        with self.assertRaises(KeyError):
            scenario("atlantis")

    def test_an_unknown_house_is_refused(self):
        with self.assertRaises(KeyError):
            start("marchlands", house="borgia")


class TestEachScenario(unittest.TestCase):
    def test_all_of_them_start_and_run(self):
        for key in SCENARIOS:
            with self.subTest(scenario=key):
                g = start(key, seed=5)
                self.assertTrue(g.world.settlements, key)
                self.assertGreater(g.population, 20, key)
                self.assertTrue(g.briefing.strip(), key)
                self.assertEqual(g.scenario, key)
                g.advance(60)
                if key == "siege" and g.over.startswith("Stormed"):
                    # The one scenario whose whole subject is a storm: left
                    # alone, the first one goes in near day 48 and carries
                    # the wall about two times in three. Losing it is the
                    # scenario, not a fault -- but not before the ram has
                    # had the weeks it needs.
                    self.assertGreaterEqual(g.day, 40, "stormed too soon")
                    continue
                self.assertEqual(g.over, "", f"{key} ended in its first two months")

    def test_a_seat_is_never_also_unclaimed_land(self):
        """Otherwise you can 'found' your own capital and replace it."""
        for key in SCENARIOS:
            g = start(key, seed=5)
            for settled in g.world.settlements:
                self.assertNotIn(settled, g.world.sites, key)

    def test_the_terms_differ(self):
        salt = start("salt_road")
        iron = start("iron_marches")
        march = start("marchlands")
        self.assertEqual(salt.goals.paths, ("wealth",))
        self.assertIn("dominion", iron.goals.paths)
        self.assertFalse(iron.goals.wonder)
        self.assertEqual(set(march.goals.paths),
                         {"wealth", "dominion", "bells", "reliquary"})
        self.assertLess(salt.goals.days, march.goals.days)

    def test_the_salt_road_opens_on_the_water(self):
        g = start("salt_road")
        home = next(iter(g.world.settlements.values()))
        self.assertTrue(home.effect("port"))
        self.assertTrue(g.world.is_port("sealow"))

    def test_the_iron_marches_opens_on_the_ore(self):
        g = start("iron_marches")
        home = next(iter(g.world.settlements.values()))
        self.assertGreater(home.deposits["iron_ore"], 10_000)
        self.assertTrue(home.count("keep"))
        self.assertGreater(sum(t.hostility for t in g.world.towns.values()),
                           sum(t.hostility for t in start("salt_road").world.towns.values()))

    def test_the_winter_crown_opens_in_the_snow(self):
        g = start("winter_crown")
        self.assertEqual(g.season, "winter")
        self.assertLess(g.goals.days, 3 * C.DAYS_PER_YEAR)

    def test_a_scenario_survives_a_save(self):
        g = start("salt_road", seed=3)
        g.advance(20)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            g.save(path)
            h = GameState.load(path)
        self.assertEqual(h.scenario, "salt_road")
        self.assertEqual(h.goals.paths, g.goals.paths)
        self.assertEqual(h.goals.net_worth, g.goals.net_worth)
        self.assertEqual(h.briefing, g.briefing)
        self.assertEqual(h.start_month, g.start_month)


class TestGoals(unittest.TestCase):
    def test_a_path_that_is_not_offered_cannot_be_taken(self):
        g = start("salt_road")
        for key in list(g.world.towns)[:3]:
            g.world.towns[key].owner = "player"
        g.tick()
        self.assertEqual(g.over, "")        # dominion is not on the table here

    def test_wealth_still_ends_it(self):
        g = start("salt_road")
        g.treasury = g.goals.net_worth * 1.2
        next(iter(g.world.settlements.values())).population = g.goals.population + 10
        g.tick()
        self.assertIn("Triumph", g.over)


class TestBalance(unittest.TestCase):
    """Guards, not correctness: every scenario must be survivable and none
    of them a walkover for a policy that never reads a price."""

    #: The bot is an economy: it climbs, builds, trades and holds a garrison
    #: proportional to the threat. The siege is none of those things -- one
    #: hill, no expansion, and a closed ring that makes trading impossible by
    #: design. The bot lives through the ring perfectly well (see
    #: `test_the_bot_lives_through_the_ring`) and then spends the rest of the
    #: clock paying sixty-five soldiers out of a town of forty, which is a
    #: fact about the bot rather than about the scenario. Guard the siege with
    #: the assertion that means something there instead.
    NOT_FOR_THE_BOT = {"siege"}

    def test_the_bot_lasts_the_distance_everywhere(self):
        for key in SCENARIOS:
            if key in self.NOT_FOR_THE_BOT:
                continue
            with self.subTest(scenario=key):
                g = start(key, seed=5)
                Bot(g).run(g.goals.days)
                self.assertNotIn("Ruined", g.over, key)
                self.assertNotIn("Ended", g.over, key)

    def test_the_bot_usually_lives_through_the_ring(self):
        """What the siege actually promises: a plain defensive policy is
        enough to hold the town more often than not.

        It used to say *always*, and that was only ever true because the
        sortie at the middle of the scenario always worked. Now that it is a
        bet on getting out of the gate unseen -- see `military.sortie_odds`
        -- a policy that makes the bet correctly still loses it about one
        game in four, and a test demanding five wins from five seeds is a
        test demanding the gamble be taken out again.

        So: most, and a number, and it fails if the number moves. Five of
        eight would catch the regressions that matter -- a scenario nobody
        can hold, or one the bot walks through -- without asserting away the
        thing the last two commits were for.
        """
        held, endings = 0, []
        for seed in range(1, 9):
            g = start("siege", seed=seed)
            bot = Bot(g)
            town = next(iter(g.world.settlements.values()))
            # The host has to arrive first. Waiting for the ring before
            # looping on it matters: written the other way round the loop
            # never ran a single day and the test passed in three
            # milliseconds without playing anything.
            while not g.over and not town.besieged and g.day < g.goals.days:
                bot.step()
                g.tick()
            self.assertTrue(town.besieged, f"the ring never closed (seed {seed})")
            days = 0
            while not g.over and town.besieged and g.day < g.goals.days:
                bot.step()
                g.tick()
                days += 1
            self.assertGreater(days, 10, "the ring lifted before it was a siege")
            # Read the ending, not `besieged`: a town that falls stops being
            # besieged, so "besieged and over" is the one state a storming
            # does not leave behind, and that test passed whatever happened.
            lost = any(w in (g.over or "") for w in ("Stormed", "Ruined", "Ended"))
            held += not lost
            endings.append(g.over or "held")
        self.assertGreaterEqual(held, 5, f"the siege is unholdable: {endings}")

    def test_none_of_them_is_a_walkover(self):
        won = []
        for key in SCENARIOS:
            if key in self.NOT_FOR_THE_BOT:
                continue
            g = start(key, seed=5)
            Bot(g).run(g.goals.days)
            if any(w in g.over for w in ("Triumph", "Dominion", "cathedral")):
                won.append(key)
        self.assertLessEqual(len(won), 2, f"too easy: {won}")


if __name__ == "__main__":
    unittest.main()
