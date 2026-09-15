"""Where a battle is fought, and what the sky is doing while it is.

Before this, `fight` took a `place` and used it only to write the log, and
the word "season" appeared nowhere in military.py. A January battle in a fen
came out exactly like a June one on a dry plain -- in a game whose whole map
is country and whose whole calendar is seasons.

The cartographer had been deciding this all along and throwing it away: it
rolls a patch of ground for every town, picks the roofline off it, and drops
it. Its own note on `_ground` said marsh was "counted like the rest and used
by nothing". It is used by this.
"""

from __future__ import annotations

import random
import unittest

from marchlands import cartography as carto
from marchlands.military import (CLOSE, FROST, HEAVY, HORSE, MUD, OPEN, RANGED,
                                 Field, Side, field_note, fight, going_of,
                                 season_odds, sky_on)
from marchlands.scenario import drawn_game
from marchlands.scenarios import start


class TestTheMapDecidesTheGround(unittest.TestCase):
    def test_a_town_keeps_the_country_it_was_drawn_in(self):
        g = drawn_game("fens", seed=5)
        for t in g.world.towns.values():
            self.assertTrue(t.ground, f"{t.key} was drawn with no country")

    def test_each_region_fights_like_itself(self):
        """The dials that draw a region decide how war works in it, which is
        the whole argument for drawing regions rather than maps."""
        want = {"fens": HEAVY, "po": OPEN, "pennines": "broken",
                "marches": CLOSE}
        for region, going in want.items():
            g = drawn_game(region, seed=5)
            grounds = [g.field_at(k).going for k in g.world.towns]
            self.assertTrue(grounds, region)
            common = max(set(grounds), key=grounds.count)
            self.assertEqual(common, going, f"{region} came out {grounds}")

    def test_a_place_with_no_country_recorded_still_has_some(self):
        """The hand-built scenarios predate this. A map where half the towns
        have ground and half have none would be worse than none having it."""
        seen = set()
        for key in ("aldworth", "dunmere", "vantry", "bruille", "ostmark"):
            seen.add(going_of({}, key))
        self.assertGreater(len(seen), 1, "every name came out the same country")

    def test_the_ground_survives_a_save(self):
        g = drawn_game("fens", seed=5)
        key = next(iter(g.world.towns))
        before = dict(g.world.towns[key].ground)
        again = type(g).from_dict(g.to_dict())
        self.assertEqual(again.world.towns[key].ground, before)
        self.assertEqual(again.field_at(key).going, g.field_at(key).going)


class TestTheSky(unittest.TestCase):
    def test_the_same_day_gives_the_same_answer_twice(self):
        """The panel that tells you before you commit and the battle that
        happens afterwards are two askers of the same question. Weather that
        re-rolled between them would be a lie rather than a forecast."""
        for day in range(0, 400, 37):
            a = sky_on("winter", day, seed=11)
            self.assertEqual(a, sky_on("winter", day, seed=11))

    def test_two_games_do_not_get_the_same_weather(self):
        one = [sky_on("autumn", d, seed=1) for d in range(60)]
        two = [sky_on("autumn", d, seed=2) for d in range(60)]
        self.assertNotEqual(one, two)

    def test_winter_is_not_summer(self):
        winter = [sky_on("winter", d, seed=3) for d in range(300)]
        summer = [sky_on("summer", d, seed=3) for d in range(300)]
        self.assertGreater(winter.count(FROST), 60, winter.count(FROST))
        self.assertEqual(summer.count(FROST), 0)

    def test_the_season_is_told_rather_than_the_forecast(self):
        """Nobody in 1247 knows what next Tuesday does. What a man knows is
        his own calendar, and that is what is offered."""
        odds = season_odds("winter")
        self.assertEqual(odds[0][0], FROST)
        self.assertAlmostEqual(sum(v for _k, v in odds), 1.0, places=6)


class TestWhatTheGroundIsWorth(unittest.TestCase):
    def test_a_fen_is_bad_for_horse_and_barely_touches_foot(self):
        d = Field(going=HEAVY, weather=MUD).mult()
        self.assertLess(d[HORSE], 0.85)
        self.assertGreater(d.get("foot", 1.0), 0.99)

    def test_a_hard_frost_gives_the_fen_back(self):
        """The one piece of weather that changes what the ground *is*. It is
        the reason the calendar is a weapon: the fen town nobody can take in
        April can be ridden into in January."""
        self.assertLess(Field(going=HEAVY, weather="fair").mult()[HORSE], 0.9)
        self.assertNotIn(HORSE, Field(going=HEAVY, weather=FROST).mult())

    def test_but_a_frozen_fen_is_only_ordinary_ground(self):
        """Not *better* than open country -- that would make a hard winter a
        reason to fight in a bog, which is the wrong lesson."""
        frozen = Field(going=HEAVY, weather=FROST).mult().get(HORSE, 1.0)
        open_field = Field(going=OPEN, weather=FROST).mult().get(HORSE, 1.0)
        self.assertLessEqual(frozen, open_field)

    def test_nothing_is_worth_less_than_an_order_is(self):
        """The bound that keeps this a decision rather than a verdict. This
        combat model is a knife edge -- see the note in military.py -- and
        ground and weather multiply together, so the pair of them has to be
        checked rather than each alone. The first cut of this had horse at
        0.70 in a fen in mud, which does not tilt a battle, it ends one."""
        from marchlands.military import GOING, WEATHER
        for g in GOING:
            for w in WEATHER:
                for kind, worth in Field(going=g, weather=w).mult().items():
                    self.assertGreater(worth, 0.8, f"{g}+{w} ruins {kind}")
                    self.assertLess(worth, 1.12, f"{g}+{w} gilds {kind}")

    def test_it_only_talks_about_soldiers_you_have(self):
        rows = field_note({"spearman": 40}, Field(going=HEAVY, weather=MUD))
        self.assertNotIn(HORSE, [r["kind"] for r in rows])
        rows = field_note({"knight": 40}, Field(going=HEAVY, weather=MUD))
        self.assertIn(HORSE, [r["kind"] for r in rows])


class TestItChangesBattlesWithoutDecidingThem(unittest.TestCase):
    """The standard the orders were held to, applied to this."""

    def wins(self, att, deff, fld, n=200):
        got = 0
        for seed in range(n):
            a, d = Side(dict(att)), Side(dict(deff))
            got += fight(a, d, rng=random.Random(seed), field=fld).winner == "attacker"
        return 100.0 * got / n

    CLOSE_FIGHT = ({"knight": 12, "man_at_arms": 12},
                   {"spearman": 40, "archer": 14})

    def test_a_close_fight_turns_on_it(self):
        att, deff = self.CLOSE_FIGHT
        on_grass = self.wins(att, deff, Field(going=OPEN, weather="fair"))
        in_a_fen = self.wins(att, deff, Field(going=HEAVY, weather=MUD))
        self.assertGreater(on_grass - in_a_fen, 15,
                           f"{on_grass:.0f}% on grass, {in_a_fen:.0f}% in a fen")

    def test_and_waiting_for_the_frost_gives_it_back(self):
        att, deff = self.CLOSE_FIGHT
        mud = self.wins(att, deff, Field(going=HEAVY, weather=MUD))
        frost = self.wins(att, deff, Field(going=HEAVY, weather=FROST))
        self.assertGreater(frost - mud, 15, f"{mud:.0f}% in mud, {frost:.0f}% frozen")

    def test_a_rout_is_still_a_rout(self):
        for fld in (Field(going=OPEN, weather="fair"), Field(going=HEAVY, weather=MUD)):
            self.assertEqual(self.wins({"knight": 5}, {"spearman": 60}, fld, n=60), 0.0)

    def test_and_a_walkover_is_still_a_walkover(self):
        for fld in (Field(going=OPEN, weather="fair"), Field(going=HEAVY, weather=MUD)):
            self.assertEqual(self.wins({"knight": 90}, {"archer": 8}, fld, n=60), 100.0)

    def test_foot_and_bows_can_fight_anywhere(self):
        """Which is the point of it: ground rewards the host you brought,
        rather than taxing everybody who turns up."""
        deff = {"spearman": 40, "archer": 14}
        foot = {"man_at_arms": 22, "archer": 12}
        spread = [self.wins(foot, deff, Field(going=g, weather=w), n=80)
                  for g, w in ((OPEN, "fair"), (CLOSE, "fair"), (HEAVY, MUD))]
        self.assertLess(max(spread) - min(spread), 12, spread)


class TestTheDialsComeOffAgain(unittest.TestCase):
    """The shape of the bug that orders shipped with: `fight` dressed copies,
    so the casualties landed on the copy and nobody died in a siege assault
    for several commits. Anything `fight` puts on a Side has to come off it.
    """

    def test_a_side_is_handed_back_as_it_was_given(self):
        a = Side({"knight": 30}, class_mult={"horse": 1.5})
        d = Side({"spearman": 30})
        fight(a, d, rng=random.Random(2), field=Field(going=HEAVY, weather=MUD))
        self.assertEqual(a.class_mult, {"horse": 1.5})
        self.assertEqual(d.class_mult, {})

    def test_and_the_dead_are_still_dead(self):
        a = Side({"knight": 30})
        d = Side({"spearman": 40})
        res = fight(a, d, rng=random.Random(2), field=Field(going=OPEN, weather="fair"))
        self.assertGreater(sum(res.defender_losses.values()), 0)
        self.assertLess(d.alive(), 40)


class TestABattleInPlay(unittest.TestCase):
    def test_a_real_assault_is_fought_somewhere(self):
        from marchlands import engine as E
        seen = []
        real = E.fight

        def spy(a, d, **kw):
            seen.append(kw.get("field"))
            return real(a, d, **kw)

        E.fight = spy
        try:
            g = start("siege", seed=3)
            for _ in range(120):
                g.advance(1)
                if g.over:
                    break
        finally:
            E.fight = real
        self.assertTrue(seen, "no battle happened to check")
        self.assertTrue(all(f is not None for f in seen),
                        "a battle was fought nowhere in particular")


if __name__ == "__main__":
    unittest.main()
