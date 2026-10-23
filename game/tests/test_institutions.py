"""A tech tree with a logical relationship to the economics and the politics.

A tech tree is usually a list of multipliers with a picture on each one. It
can be the other thing: every node an *institution* that the economics or the
politics layer already models, where researching it is what gives you the
lever rather than a percentage.

The prerequisites are then the real ones. You cannot debase a coinage you do
not strike. You cannot fix the price of bread without a guild to enforce it and
a court to hear the complaints. You cannot keep an embassy without a chancery
to write the letters, nor offer a safe-conduct without an embassy to be
trusted by. An exchequer is what a counting house becomes when it is the
crown's.

These are tests that the branch is load-bearing: that the gates shut, that the
chains are the real ones, and that the four institutions whose effect is a
mechanic rather than a number actually change the mechanic.
"""

import json
import unittest

from marchlands import config as C
from marchlands.economics import MONEY_BASE
from marchlands.engine import GameState
from marchlands.scenario import drawn_game, new_game
from marchlands.tech import TECHS


def charter(g, *keys):
    g.progress.researched |= set(keys)
    return g


class TestTheInstitutionsAreGates(unittest.TestCase):
    """A tree that only multiplies what you were already doing describes your
    town. One that decides what you may do in it is a tree."""

    def setUp(self):
        self.g = new_game(seed=5)
        self.g.treasury = 80_000

    def test_you_cannot_debase_a_coinage_you_do_not_strike(self):
        said = self.g.mint(C.MINT_LIMIT)
        self.assertIn("no coinage of your own", said)
        self.assertAlmostEqual(self.g.economy.money, MONEY_BASE)

    def test_and_can_once_you_do(self):
        charter(self.g, "coinage")
        self.g.mint(200)
        self.assertGreater(self.g.economy.money, MONEY_BASE)

    def test_you_cannot_fix_a_price_with_no_court_to_hear_it(self):
        said = self.g.decree("bread", 1.0)
        self.assertIn("no assize here", said)
        self.assertEqual(self.g.economy.assize, {})

    def test_and_can_once_there_is_one(self):
        charter(self.g, "assize_of_bread")
        self.g.decree("bread", 1.0)
        self.assertIn("bread", self.g.economy.assize)

    def test_nobody_swears_to_a_house_that_cannot_write(self):
        self.g.court.write("dunmere", "marriage", 90.0, 0)
        said = self.g.ally("dunmere")
        self.assertIn("no chancery", said)
        self.assertEqual(self.g.court.allies, [])

    def test_and_will_once_it_can(self):
        charter(self.g, "chancery")
        self.g.court.write("dunmere", "marriage", 90.0, 0)
        self.g.ally("dunmere")
        self.assertIn("dunmere", self.g.court.allies)

    def test_every_gate_names_the_institution_that_opens_it(self):
        for lever, (want, why) in GameState.OPENS.items():
            self.assertIn(want, TECHS, lever)
            self.assertIn(want, why, f"{lever} does not say what to research")

    def test_and_says_it_rather_than_failing_silently(self):
        for lever in GameState.OPENS:
            self.assertTrue(self.g.opened(lever), lever)
            self.assertGreater(len(self.g.opened(lever)), 40, lever)


class TestTheChainsAreTheRealOnes(unittest.TestCase):
    def test_an_assize_needs_a_guild_to_enforce_it(self):
        self.assertEqual(TECHS["assize_of_bread"].prereq, "guild_charter")

    def test_a_safe_conduct_needs_somebody_to_be_trusted_by(self):
        self.assertEqual(TECHS["safe_conduct"].prereq, "chancery")
        self.assertEqual(TECHS["heralds"].prereq, "chancery")

    def test_an_exchequer_is_what_a_counting_house_becomes(self):
        self.assertEqual(TECHS["exchequer"].prereq, "counting_house")
        self.assertEqual(TECHS["staple_right"].prereq, "counting_house")
        self.assertEqual(TECHS["counting_house"].prereq, "letters_of_credit")

    def test_no_institution_can_be_had_before_its_prerequisite(self):
        g = new_game(seed=5)
        g.progress.age = 4
        offered = {t.key for t in g.progress.available()}
        for key in ("safe_conduct", "heralds", "staple_right", "exchequer",
                    "assize_of_bread"):
            self.assertNotIn(key, offered, key)

    def test_every_institution_says_what_it_is_for(self):
        for key in ("coinage", "assize_of_bread", "chancery", "staple_right",
                    "safe_conduct", "heralds", "drainage", "exchequer"):
            self.assertGreater(len(TECHS[key].blurb), 50, key)


class TestTheOnesThatChangeAMechanic(unittest.TestCase):
    """Four of them do something no multiplier could."""

    def test_a_safe_conduct_takes_the_worst_off_a_hostile_gate(self):
        g = new_game(seed=5)
        g.court.write("dunmere", "took_town", -80.0, 0)
        g.tick()
        bad = g.world.tariff_for("dunmere", None)
        charter(g, "safe_conduct")
        g.tick()
        self.assertLess(g.world.tariff_for("dunmere", None), bad)

    def test_and_nothing_off_a_friendly_one(self):
        """Which is what a safe-conduct was: protection against being
        stopped, not a discount."""
        g = charter(new_game(seed=5), "chancery")
        g.court.write("vantry", "marriage", 90.0, 0)
        g.ally("vantry")
        g.tick()
        good = g.world.tariff_for("vantry", None)
        charter(g, "safe_conduct")
        g.tick()
        self.assertAlmostEqual(g.world.tariff_for("vantry", None), good)

    def test_heralds_make_a_grievance_you_can_name_last_longer(self):
        g = new_game(seed=5)
        g.court.give_ground("dunmere", "raided", 0)
        spec = g.court.ground_for("dunmere", 0)
        self.assertIsNotNone(spec)
        stale = spec.days + 10
        self.assertIsNone(g.court.ground_for("dunmere", stale))
        charter(g, "heralds")
        g.tick()
        self.assertIsNotNone(g.court.ground_for("dunmere", stale))

    def test_drainage_turns_land_you_cannot_work_into_land_you_can(self):
        g = drawn_game("fens", seed=5)
        s = g.home()
        fen = s.terrain.get("marsh", 0)
        self.assertGreater(fen, 0)
        charter(g, "drainage")
        for _ in range(g.DRAIN_DAYS * (fen + 1)):
            g.tick()
        self.assertEqual(s.terrain.get("marsh", 0), 0)
        self.assertGreater(s.terrain.get("fertile", 0), 0)

    def test_but_slowly_enough_that_a_fen_is_still_a_bad_start(self):
        """Draining the Fens took generations and the capital of whole
        cities. A tech that converted a marsh overnight would make the
        wettest map the best one to open on."""
        self.assertGreaterEqual(GameState.DRAIN_DAYS, 60)

    def test_and_nothing_happens_without_it(self):
        g = drawn_game("fens", seed=5)
        fen = g.home().terrain.get("marsh", 0)
        for _ in range(g.DRAIN_DAYS * 3):
            g.tick()
        self.assertEqual(g.home().terrain.get("marsh", 0), fen)

    def test_the_staple_is_worth_what_it_says(self):
        self.assertLess(TECHS["staple_right"].effects["tariff"], 1.0)

    def test_it_all_survives_a_save(self):
        g = charter(new_game(seed=5), "safe_conduct", "heralds")
        g.tick()
        back = GameState.from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertTrue(back.world.safe_conduct)
        self.assertTrue(back.court.long_memory)


class TestTheTreeStillPlays(unittest.TestCase):
    def test_the_institutions_can_actually_be_reached(self):
        g = new_game(seed=5)
        g.progress.age = 2
        offered = {t.key for t in g.progress.available()}
        self.assertIn("coinage", offered)
        self.assertIn("chancery", offered)

    def test_and_are_priced_like_the_rest_of_their_age(self):
        for key in ("coinage", "assize_of_bread", "chancery"):
            t = TECHS[key]
            self.assertEqual(t.age, 2)
            self.assertGreater(t.cost["coin"], 300)
            self.assertLess(t.cost["coin"], 1200)

    def test_nothing_in_the_tree_needs_something_that_is_not_in_it(self):
        for t in TECHS.values():
            if t.prereq:
                self.assertIn(t.prereq, TECHS, t.key)

    def test_and_nothing_needs_something_from_a_later_age(self):
        for t in TECHS.values():
            if t.prereq:
                self.assertLessEqual(TECHS[t.prereq].age, t.age, t.key)
