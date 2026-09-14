"""A path through the game that is yours rather than the scenario's.

Every scenario states one shape of victory and it is the same for all five
houses, which means the Hansa and the Ironhand have been playing the
identical campaign with different multipliers. The part of a mission tree
worth stealing is not the branching diagram; it is that the missions are
written for who you are, so the tree says what your house is *for* at the
same time as it gives you something to do next.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from marchlands import missions as mi
from marchlands.feats import Standing
from marchlands.missions import Roll, tree
from marchlands.scenarios import start
from marchlands.sim import Bot
from marchlands.tech import HOUSES, TECHS


class TestTheTreeItself(unittest.TestCase):
    def test_every_house_has_a_branch_of_its_own(self):
        for house in HOUSES:
            branch = [m for m in tree(house) if m.house]
            self.assertTrue(branch, f"{house} plays the trunk and nothing else")

    def test_the_trunk_is_the_same_for_everybody(self):
        trunks = {house: tuple(m.key for m in tree(house) if not m.house)
                  for house in HOUSES}
        self.assertEqual(len(set(trunks.values())), 1)

    def test_no_two_houses_share_a_branch(self):
        for a in HOUSES:
            for b in HOUSES:
                if a == b:
                    continue
                ka = {m.key for m in tree(a) if m.house}
                kb = {m.key for m in tree(b) if m.house}
                self.assertFalse(ka & kb, f"{a} and {b} share {ka & kb}")

    def test_every_mission_says_what_it_costs(self):
        # A tree that pretends its demands are free is a checklist.
        for house in HOUSES:
            for m in tree(house):
                self.assertTrue(m.asks, m.key)
                self.assertTrue(m.costs, m.key)

    def test_every_prerequisite_is_a_mission_that_exists(self):
        for house in HOUSES:
            keys = {m.key for m in tree(house)}
            for m in tree(house):
                for need in m.after:
                    self.assertIn(need, keys, f"{m.key} waits on {need}")

    def test_every_reward_names_something_the_game_has(self):
        from marchlands.estates import PRIVILEGES
        from marchlands.military import UNITS
        for house in HOUSES:
            for m in tree(house):
                kind, value = m.gives
                self.assertIn(kind, mi.REWARDS, m.key)
                if kind == "tech":
                    self.assertIn(value, TECHS, m.key)
                if kind == "privilege":
                    self.assertIn(value, PRIVILEGES, m.key)
                if kind == "units":
                    for unit in dict(value):
                        self.assertIn(unit, UNITS, m.key)

    def test_a_reward_reads_as_words_rather_than_a_key(self):
        for house in HOUSES:
            for m in tree(house):
                said = m.reward_words()
                self.assertTrue(said)
                self.assertNotIn("_", said, f"{m.key} shows a raw key: {said}")


class TestTheOrderIsTheWholePoint(unittest.TestCase):
    def test_only_what_is_open_can_be_finished(self):
        # A tree where the last mission can be done before the first is a
        # list, and the order is the only thing a tree adds.
        r = Roll()
        everything = Standing(day=1, population=900, mood=99.0, towns=8,
                              wall_yards=500, techs=40, trade_profit=500_000,
                              soldiers=900, battles_won=50, took_by_storm=9,
                              relics=5)
        r.check("plough", everything)
        self.assertIn("roof", r.to_dict())
        self.assertNotIn("march", r.to_dict(), "the last one went first")

    def test_it_walks_the_tree_a_step_at_a_time(self):
        r = Roll()
        everything = Standing(day=1, population=900, mood=99.0, towns=8,
                              wall_yards=500, techs=40, trade_profit=500_000,
                              soldiers=900, battles_won=50, took_by_storm=9,
                              relics=5)
        for day in range(8):
            everything.day = day
            r.check("plough", everything)
        self.assertIn("march", r.to_dict())

    def test_a_mission_is_finished_once(self):
        r = Roll()
        s = Standing(day=1, population=400, mood=90.0)
        self.assertTrue(r.check("plough", s))
        self.assertEqual(r.check("plough", Standing(day=2, population=400,
                                                    mood=90.0)), [])

    def test_a_mission_that_throws_does_not_break_the_day(self):
        boom = mi.Mission(key="boom", house="", name="Boom", asks="x",
                          costs="y", test=lambda s: 1 / 0 > 0,
                          gives=("coin", 1))
        mi.TRUNK.append(boom)
        try:
            self.assertNotIn("boom", dict(Roll().check("plough",
                                                       Standing(day=1))))
        finally:
            mi.TRUNK.remove(boom)


class TestTheRewardIsActuallyPaid(unittest.TestCase):
    """A reward that is a line of text is a reward nobody notices was never
    given."""

    def game(self, house="hansa", days=600, seed=3):
        g = start("marchlands", seed=seed, house=house)
        Bot(g).run(days)
        return g

    def test_coin_reaches_the_chest(self):
        g = self.game(days=60)
        was = g.treasury
        m = next(m for m in tree(g.house) if m.gives[0] == "coin")
        said = g._pay(m)
        self.assertGreater(g.treasury, was)
        self.assertIn("chest", said)

    def test_an_institution_is_known_without_the_scholars(self):
        g = self.game()
        m = next(m for m in tree("hansa") if m.gives[0] == "tech")
        g.progress.researched.discard(m.gives[1])
        g._pay(m)
        self.assertIn(m.gives[1], g.progress.researched)

    def test_a_claim_lands_on_a_town_the_map_actually_has(self):
        g = self.game()
        m = next(m for m in tree("hansa") if m.gives[0] == "claim")
        said = g._pay(m)
        self.assertTrue(g.court.claims, said)
        for key in g.court.claims:
            self.assertIn(key, g.world.towns)

    def test_men_muster_where_you_live(self):
        g = self.game(house="marcher")
        m = next(m for m in tree("marcher") if m.gives[0] == "units")
        want = dict(m.gives[1])
        seat = g.home()
        was = {k: seat.units.get(k, 0.0) for k in want}
        g._pay(m)
        for k, n in want.items():
            self.assertEqual(seat.units.get(k, 0.0), was[k] + n)

    def test_a_privilege_is_granted_and_costs_nothing(self):
        g = self.game()
        m = next(m for m in tree("hansa") if m.gives[0] == "privilege")
        g._pay(m)
        self.assertTrue(g.estates.granted(m.gives[1]))

    def test_it_is_paid_by_playing_rather_than_by_claiming(self):
        # There is no button to press: a day passing is what pays it.
        g = self.game()
        key = next(k for k, t in g.world.towns.items() if not t.mine)
        g.world.towns[key].owner = "player"
        self.assertNotIn("neighbour", g.missions.to_dict())
        g.advance(1)
        self.assertIn("neighbour", g.missions.to_dict())
        self.assertTrue(g.court.claims)


class TestTwoHousesPlayTwoGames(unittest.TestCase):
    def test_the_same_seed_opens_different_missions(self):
        seen = {}
        for house in ("plough", "hansa"):
            g = start("marchlands", seed=3, house=house)
            Bot(g).run(700)
            seen[house] = {m.key for m in g.missions.open(house) if m.house}
        self.assertNotEqual(seen["plough"], seen["hansa"])

    def test_the_roll_survives_a_save(self):
        g = start("marchlands", seed=3, house="abbey")
        Bot(g).run(400)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "g.save")
            g.save(path)
            back = type(g).load(path)
        self.assertEqual(back.missions.to_dict(), g.missions.to_dict())


if __name__ == "__main__":
    unittest.main()


class TestNoMissionPaysForTheStartingPosition(unittest.TestCase):
    """The first mission asked for "a population and a mood", which is the
    state every game opens in -- so it paid 1,200c on day one of every game,
    and the coin was enough to pull a deliberately bankrupt game back off the
    floor. A mission has to ask for something you do not already have."""

    def test_nothing_is_finished_on_the_first_day(self):
        from marchlands.scenario import new_game
        for house in HOUSES:
            g = new_game(house=house)
            self.assertEqual(g.missions.check(house, g._standing()), [],
                             f"{house} was paid for turning up")

    def test_coin_rewards_go_through_the_ledger(self):
        # A reward added straight to the treasury is a coin the day's
        # accounts cannot explain.
        from marchlands.scenario import new_game
        g = new_game()
        led = type(g.ledger)()
        m = next(m for m in tree(g.house) if m.gives[0] == "coin")
        was = g.treasury
        g._pay(m, led)
        self.assertEqual(g.treasury - was, led.reward)
        self.assertAlmostEqual(led.net, led.reward, places=6)
