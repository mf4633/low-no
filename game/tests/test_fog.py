"""Fire, friars and fog: the three that were still missing.

Stronghold's towns burned, Age of Empires' monks stole men off a wall, and
neither game let you see what you had not gone and looked at.
"""

import io
import json
import random
import unittest

from marchlands import config as C
from marchlands.cli import Console
from marchlands.fire import Fires, burn, hands_wanted, timber_share
from marchlands.military import Side, convert
from marchlands.scenarios import start
from marchlands.settlement import BuildingInstance
from marchlands.sim import Bot


def game(seed=5):
    return start("marchlands", seed=seed)


def grown(seed=3, days=600):
    g = start("marchlands", seed=seed)
    Bot(g).run(days)
    return g, g.world.settlements["aldworth"]


# ------------------------------------------------------------------ the fire
class TestWhatBurns(unittest.TestCase):
    def test_timber_catches_and_stone_mostly_does_not(self):
        self.assertGreater(timber_share({"wood": 40}), timber_share({"stone": 40}))
        self.assertEqual(timber_share({"stone": 40}), 0.0)
        self.assertEqual(timber_share({"wood": 30}), 1.0)

    def test_a_shed_of_nothing_much_still_burns(self):
        self.assertGreater(timber_share({"coin": 90}), 0.0)

    def test_unattended_a_building_is_lost(self):
        fires = Fires()
        fires.light(1)
        standing = [(1, {"wood": 40}, True)]
        lost = []
        for _ in range(20):
            gone, _sc, _l = burn(fires, standing, hands=0.0, season="summer",
                                 rng=random.Random(2))
            lost += gone
            if not fires:
                break
        self.assertEqual(lost, [1])

    def test_enough_hands_beat_it_out(self):
        fires = Fires()
        fires.light(1)
        standing = [(1, {"wood": 40}, True)]
        for _ in range(8):
            lost, _sc, _l = burn(fires, standing, hands=40.0, season="spring",
                                 rng=random.Random(2))
            self.assertEqual(lost, [])
            if not fires:
                break
        self.assertFalse(fires)

    def test_summer_is_the_dangerous_season(self):
        def ruin_after(season):
            fires = Fires()
            fires.light(1)
            burn(fires, [(1, {"wood": 40}, True)], hands=0.0, season=season,
                 rng=random.Random(2))
            return fires.blazes[1].ruin
        self.assertGreater(ruin_after("summer"), ruin_after("winter"))

    def test_a_fire_reaches_for_one_roof_not_the_whole_town(self):
        """Quadratic spread has two outcomes and nothing in between."""
        fires = Fires()
        fires.light(1)
        standing = [(1, {"wood": 40}, True)]
        standing += [(i, {"wood": 40}, True) for i in range(2, 40)]
        burn(fires, standing, hands=0.0, season="summer", rng=random.Random(5))
        self.assertLessEqual(len(fires.blazes), 2)

    def test_a_saved_building_still_wants_work(self):
        """A fire has taken hold before anyone gets there, so nothing is free."""
        fires = Fires()
        fires.light(1)
        standing = [(1, {"wood": 40}, True)]
        scarred = {}
        for _ in range(10):
            _lost, sc, _l = burn(fires, standing, hands=12.0, season="summer",
                                 rng=random.Random(2))
            scarred.update(sc)
            if not fires:
                break
        self.assertTrue(scarred, "a building burned for days and came out untouched")
        self.assertGreater(scarred[1], 0.0)

    def test_a_town_can_beat_a_fire_in_any_season(self):
        """The bucket chain must out-quench a *summer* fire, not a spring one.

        It did not, once: a single blaze in July was unstoppable however few
        there were, because quench per fire was fixed and summer burned faster
        than it. That is not a fire system, it is a seasonal demolition
        service, and it cost the naive bot a fifth of its net worth.
        """
        from marchlands.fire import (BURN_RATE, HANDS_PER_BLAZE,
                                     QUENCH_PER_HAND, SEASON_TINDER)
        quench = QUENCH_PER_HAND * HANDS_PER_BLAZE
        worst = BURN_RATE * 1.3 * max(SEASON_TINDER.values())
        self.assertGreater(quench, worst,
                           "one properly fought fire must still be losing")

    def test_one_fire_is_contained_but_never_free(self):
        g, s = grown()
        s.kindle(random.Random(3), 1)
        for _ in range(12):
            g.tick()
            if not s.fires:
                break
        self.assertFalse(s.fires, "one fire burned for a fortnight")
        self.assertTrue(any(not b.complete for b in s.buildings),
                        "the fire cost nothing at all")

    def test_the_response_scales_with_the_blaze(self):
        self.assertGreater(hands_wanted(6), hands_wanted(2))

    def test_fires_survive_a_save(self):
        f = Fires()
        f.light(4)
        f.blazes[4].ruin = 0.4
        back = Fires.from_dict(json.loads(json.dumps(f.to_dict())))
        self.assertTrue(back.burning(4))
        self.assertAlmostEqual(back.blazes[4].ruin, 0.4)

    def test_lighting_the_same_roof_twice_does_nothing(self):
        f = Fires()
        self.assertTrue(f.light(1))
        self.assertFalse(f.light(1))


class TestATownOnFire(unittest.TestCase):
    def test_a_burning_workshop_does_not_work(self):
        g, s = grown()
        target = next(b for b in s.buildings
                      if b.complete and b.enabled and b.spec.jobs and b.spec.outputs)
        s.set_band(target.key, "first")
        s.fires.light(target.uid)
        g.tick()
        self.assertEqual(target.throughput, 0.0)
        self.assertEqual(target.idle_reason, "on fire")

    def test_fighting_it_costs_a_day_s_work(self):
        g, s = grown()
        s.kindle(random.Random(3), 3)
        g.tick()
        self.assertGreater(s.fire_labour, 0.0)

    def test_but_it_can_never_stop_the_town_entirely(self):
        """A town that stops working never recovers, so the bite is bounded."""
        g, s = grown()
        s.kindle(random.Random(3), 40)
        g.tick()
        self.assertLessEqual(s.fire_labour, 0.41 * s.workforce)

    def test_a_burning_town_is_a_frightened_town(self):
        g, s = grown()
        s.kindle(random.Random(3), 2)
        self.assertIn("the town is burning", dict(s.mood_factors()))

    def test_a_settlement_with_no_fires_pays_nothing(self):
        g, s = grown()
        g.tick()
        self.assertEqual(s.fire_labour, 0.0)

    def test_an_ordinary_game_does_not_burn_down(self):
        """Accidents must be memorable, not routine."""
        for seed in (3, 7, 11):
            g = start("marchlands", seed=seed)
            Bot(g).run(500)
            self.assertEqual(g.over, "", f"seed {seed} did not survive: {g.over}")

    def test_raiders_carry_torches(self):
        from marchlands.military import Army
        g = start("marchlands", seed=6)
        Bot(g).run(300)
        s = g.world.settlements["aldworth"]
        s.units = {"spearman": 3}
        raiders = Army(uid=90, name="Reivers", owner="dunmere",
                       units={"knight": 80}, at="aldworth", home="dunmere",
                       state="raiding")
        # With a baggage train, because hosts eat now and one built by hand
        # here does not go through the engine's own outfitting. Without it
        # these eighty knights spent the fortnight starving instead of
        # burning, and the test read that as "a raid never set light to
        # anything" -- which was true, and not for the reason it meant.
        from marchlands import supply
        raiders.stores = supply.capacity(raiders.size)
        g.armies.append(raiders)
        lit = 0
        for _ in range(40):
            lit += sum(1 for m in g.tick() if "alight" in m)
            if lit:
                break
        self.assertGreater(lit, 0, "a raid never set light to anything")

    def test_a_wall_that_burns_stops_being_a_wall(self):
        g, s = grown()
        s.buildings.append(BuildingInstance(uid=7777, key="palisade", days_left=0))
        s.wall_hp = s.wall_max()
        before = s.wall_hp
        # Enough alight at once that the bucket chain cannot save any of it.
        s.kindle(random.Random(3), 30)
        s.fires.light(7777)
        s.fires.blazes[7777].ruin = 0.95
        for _ in range(6):
            g.tick()
            if s.find(7777) is None:
                break
        self.assertIsNone(s.find(7777))
        self.assertLess(s.wall_hp, before)


# ---------------------------------------------------------------- the friars
class TestConversion(unittest.TestCase):
    def test_friars_bring_men_over(self):
        host, town = Side({"friar": 10}), Side({"spearman": 200})
        won, lines = convert(host, town, faith=0.0, rng=random.Random(4))
        self.assertTrue(won)
        self.assertLess(town.alive(), 200)
        self.assertGreater(host.units.get("spearman", 0), 0)
        self.assertTrue(lines)

    def test_a_church_of_their_own_is_the_answer(self):
        def swayed(faith):
            host, town = Side({"friar": 10}), Side({"spearman": 200})
            convert(host, town, faith=faith, rng=random.Random(4))
            return 200 - town.alive()
        self.assertGreater(swayed(0.0), swayed(0.6))
        self.assertEqual(swayed(1.0), 0.0)

    def test_a_host_with_no_friars_converts_nobody(self):
        host, town = Side({"man_at_arms": 90}), Side({"spearman": 200})
        won, _l = convert(host, town, faith=0.0, rng=random.Random(4))
        self.assertEqual(won, {})

    def test_no_garrison_is_talked_away_in_a_day(self):
        host, town = Side({"friar": 400}), Side({"spearman": 100})
        convert(host, town, faith=0.0, rng=random.Random(4))
        self.assertGreater(town.alive(), 100 * (1 - C.CONVERT_CEILING) - 1)

    def test_men_are_not_created_only_moved(self):
        host, town = Side({"friar": 12}), Side({"spearman": 150, "archer": 50})
        before = host.alive() + town.alive()
        convert(host, town, faith=0.0, rng=random.Random(4))
        self.assertAlmostEqual(host.alive() + town.alive(), before, places=6)

    def test_a_great_seat_is_deaf_to_preaching(self):
        g = game()
        towns = g.world.towns
        great = max(towns.values(), key=lambda t: t.wealth)
        small = min(towns.values(), key=lambda t: t.wealth)
        self.assertGreater(great.faith(), small.faith())

    def test_the_friar_has_to_be_learned_first(self):
        from marchlands.military import can_recruit
        g = game()
        ok, why = can_recruit("friar", g.progress)
        self.assertFalse(ok)
        self.assertTrue(why)


# ------------------------------------------------------------------ the fog
class TestFog(unittest.TestCase):
    def test_you_begin_knowing_nothing(self):
        g = game()
        for key in g.world.towns:
            _seen, age = g.known(key)
            self.assertEqual(age, -1, key)

    def test_a_cart_that_calls_somewhere_looks_around(self):
        g = game()
        Bot(g).run(200)
        fresh = [k for k in g.world.towns if g.known(k)[1] >= 0]
        self.assertTrue(fresh, "trading everywhere taught you nothing")

    def test_what_you_never_visit_stays_unknown(self):
        g = game(seed=3)
        Bot(g).run(300)
        unknown = [k for k in g.world.towns if g.known(k)[1] < 0]
        self.assertTrue(unknown, "you somehow saw the whole march without going")
        for key in unknown:
            self.assertEqual(g.believed_host(key), {})

    def test_old_word_understates_a_growing_lord(self):
        """Towns grow while you are not looking, so stale news is optimistic."""
        from marchlands.military import host_strength
        g = game(seed=3)
        t = g.world.towns["marchand"]
        t.observe(g.day)
        believed_then = host_strength(g.believed_host("marchand"))
        truth_then = host_strength(g.likely_host("marchand"))
        # A season of peace, which is what a lord does with one. Your report
        # does not improve while he does.
        t.prosperity *= 1.6
        t.muster *= 1.4
        self.assertEqual(host_strength(g.believed_host("marchand")), believed_then)
        self.assertGreater(host_strength(g.likely_host("marchand")), truth_then)
        self.assertLess(host_strength(g.believed_host("marchand")),
                        host_strength(g.likely_host("marchand")))

    def test_a_host_of_yours_standing_there_sees_it(self):
        from marchlands.military import Army
        g = game()
        self.assertEqual(g.known("dunmere")[1], -1)
        g.armies.append(Army(uid=90, name="Host", owner="player",
                             units={"knight": 10}, at="dunmere", home="aldworth"))
        g.tick()
        self.assertEqual(g.known("dunmere")[1], 0)

    def test_a_town_sworn_to_you_reports_every_day(self):
        g = game()
        g.world.towns["dunmere"].owner = "player"
        g.tick()
        self.assertEqual(g.known("dunmere")[1], 0)

    def test_the_castle_you_are_told_about_is_the_one_you_saw(self):
        g = game()
        t = g.world.towns["marchand"]
        t.observe(0)
        poor = t.works(t.seen["prosperity"])
        t.prosperity = 2.2
        self.assertGreaterEqual(t.works().towers, poor.towers)

    def test_what_you_know_survives_a_save(self):
        g = game()
        g.world.towns["dunmere"].observe(12)
        back = type(g).from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual(back.world.towns["dunmere"].seen_day, 12)
        self.assertTrue(back.world.towns["dunmere"].seen)


class TestConsole(unittest.TestCase):
    def speak(self, *cmds, seed=5, days=0):
        g = start("marchlands", seed=seed)
        if days:
            Bot(g).run(days)
        out = io.StringIO()
        c = Console(g, out=out)
        for cmd in cmds:
            c.do(cmd)
        return g, out.getvalue()

    def test_war_admits_what_it_does_not_know(self):
        _g, text = self.speak("war")
        self.assertIn("never sent anyone", text)

    def test_war_dates_what_it_does_know(self):
        _g, text = self.speak("war", days=200)
        self.assertTrue("today" in text or "d ago" in text)

    def test_plans_refuses_a_town_you_have_not_looked_at(self):
        _g, text = self.speak("plans havnhold")
        self.assertIn("never had eyes", text)

    def test_none_of_it_emits_escapes_when_piped(self):
        _g, text = self.speak("war", "plans dunmere", days=120)
        self.assertNotIn("\033", text)


if __name__ == "__main__":
    unittest.main()
