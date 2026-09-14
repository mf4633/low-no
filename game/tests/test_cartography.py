"""Country drawn from dials, and six real places characterised as dials.

The hand-made march is a good map and it is the only one. Played a sixth time
you are no longer reading the country, you are recalling it, and a map you have
memorised has stopped asking you anything.

These are tests that a drawn march is a *real* one: that the dials change what
the country is for and not only what it looks like, that a fen is poor because
fens are poor, that every generated place has a name a person would give it,
and that everything downstream -- lords, league, chancery, culture -- reads the
drawn map exactly as it reads the hand-made one.
"""

import json
import unittest

from marchlands import cartography as carto
from marchlands import culture as cultures
from marchlands.engine import GameState
from marchlands.layout import MARSH, plan_for
from marchlands.scenario import drawn_game
from marchlands.sim import Bot


def played(region="marches", seed=5, days=320, dials=None, house="plough"):
    g = drawn_game(region, seed=seed, house=house, dials=dials)
    bot = Bot(g)
    for _ in range(days):
        bot.step()
        g.tick()
        if g.over:
            break
    return g


class TestTheDials(unittest.TestCase):
    def test_they_clamp_rather_than_explode(self):
        d = carto.Dials(hills=9.0, marsh=-3.0, towns=99).clamp()
        self.assertEqual(d.hills, 1.0)
        self.assertEqual(d.marsh, 0.0)
        self.assertLessEqual(d.towns, 12)

    def test_a_player_can_say_what_they_want_in_one_go(self):
        d = carto.parse_dials("hills=0.8, marsh=0.25,towns=9")
        self.assertAlmostEqual(d.hills, 0.8)
        self.assertAlmostEqual(d.marsh, 0.25)
        self.assertEqual(d.towns, 9)

    def test_and_is_told_when_they_ask_for_something_that_is_not_there(self):
        with self.assertRaises(KeyError):
            carto.parse_dials("rainfall=0.5")
        with self.assertRaises(KeyError):
            carto.parse_dials("hills=very")

    def test_every_dial_has_words_for_every_setting(self):
        for value in (0.0, 0.3, 0.6, 1.0):
            d = carto.Dials(hills=value, marsh=value, wood=value,
                            fertile=value, coast=value, ore=value,
                            spread=value)
            for name, _v, word in carto.describe(d):
                self.assertTrue(word, name)


class TestSixRealPlaces(unittest.TestCase):
    """Not survey data -- this is a game and there is no map server behind it.
    What is real is the characterisation, and it has to be right or the names
    are decoration."""

    def test_each_says_what_the_real_place_is(self):
        for reg in carto.REGIONS.values():
            self.assertGreater(len(reg.note), 60, reg.key)
            self.assertTrue(reg.heads and reg.tails and reg.lords, reg.key)

    def test_the_fens_are_wet_and_the_pennines_are_not(self):
        self.assertGreater(carto.REGIONS["fens"].dials.marsh,
                           carto.REGIONS["pennines"].dials.marsh)
        self.assertGreater(carto.REGIONS["pennines"].dials.hills,
                           carto.REGIONS["fens"].dials.hills)

    def test_the_po_is_rich_land_and_the_fens_are_not(self):
        """Undrained fen is not bad farmland, it is land that yields nothing
        to anybody who has not dug it -- which is why draining the Fens was
        one of the great capital projects of the period."""
        self.assertGreater(carto.REGIONS["po"].dials.fertile,
                           carto.REGIONS["fens"].dials.fertile * 3)

    def test_the_rhine_has_neighbours_at_the_gate(self):
        rhine = carto.REGIONS["rhine"].dials
        self.assertGreaterEqual(rhine.towns, 8)
        self.assertLess(rhine.spread, 0.4)

    def test_only_the_coasts_have_coast(self):
        self.assertGreater(carto.REGIONS["baltic"].dials.coast, 0.5)
        self.assertEqual(carto.REGIONS["marches"].dials.coast, 0.0)

    def test_the_names_come_out_of_the_right_language(self):
        for key, want in (("rhine", ("berg", "burg", "heim", "bach", "fels",
                                     "stein", "eck", "thal", "hausen", "rach")),
                          ("pennines", ("thwaite", "dale", "scar", "fell",
                                        "gill", "sett", "rigg", "beck",
                                        "moor", "clough"))):
            drawn = carto.draw(key, seed=3)
            for t in drawn.towns:
                self.assertTrue(any(t["name"].endswith(w) for w in want),
                                f"{t['name']} is not a {key} name")


class TestTheCountryIsForSomething(unittest.TestCase):
    """A dial that changes only what the map looks like is a filter. Each of
    these has to change what the place is *for*."""

    def draw(self, **kw):
        return carto.draw("marches", seed=9, dials=carto.Dials(**kw).clamp())

    def test_hills_make_ore_and_eat_bread(self):
        d = self.draw(hills=1.0, fertile=0.05, wood=0.05, marsh=0.0)
        sells = set()
        buys = set()
        for t in d.towns:
            sells |= set(t["produces"])
            buys |= set(t["consumes"])
        self.assertTrue({"stone", "iron_ore"} & sells)
        self.assertIn("bread", buys)

    def test_good_land_makes_grain(self):
        d = self.draw(fertile=1.0, hills=0.0, wood=0.0, marsh=0.0)
        self.assertTrue(any("wheat" in t["produces"] for t in d.towns))

    def test_and_fen_makes_almost_nothing(self):
        fen = self.draw(marsh=1.0, fertile=0.05, hills=0.02, wood=0.05)
        rich = self.draw(fertile=1.0, hills=0.5, wood=0.6, marsh=0.0)
        made = lambda p: sum(sum(t["produces"].values()) for t in p.towns)
        self.assertLess(made(fen), made(rich) * 0.5)

    def test_a_coast_gets_ports(self):
        d = self.draw(coast=1.0)
        self.assertTrue(any(t["port"] for t in d.towns))
        dry = self.draw(coast=0.0)
        self.assertFalse(any(t["port"] for t in dry.towns))

    def test_spread_decides_how_far_the_neighbours_are(self):
        near = self.draw(spread=0.0)
        far = self.draw(spread=1.0)
        reach = lambda p: sum(abs(t["x"]) + abs(t["y"]) for t in p.towns) / len(p.towns)
        self.assertLess(reach(near), reach(far))

    def test_towns_is_how_many_there_are(self):
        self.assertEqual(len(self.draw(towns=4).towns), 4)
        self.assertEqual(len(self.draw(towns=11).towns), 11)

    def test_every_place_has_a_name_a_person_would_give_it(self):
        d = carto.draw("marches", seed=4)
        names = [d.home_name] + [t["name"] for t in d.towns] \
            + [s["name"] for s in d.sites]
        self.assertEqual(len(names), len(set(names)), "two places share a name")
        for n in names:
            self.assertTrue(n[0].isupper() and len(n) > 3, n)

    def test_and_a_lord_who_is_a_person_rather_than_a_place(self):
        """Naming every lord with the place generator gave a march of men
        called Painmore and Ludcliff -- a real medieval custom that still
        reads as a bug when it happens eight times out of eight."""
        d = carto.draw("marches", seed=4)
        given = set(carto.REGIONS["marches"].given)
        self.assertTrue(any(any(g in t["lord"] for g in given)
                            for t in d.towns))

    def test_the_same_dials_and_seed_draw_the_same_country(self):
        a = carto.draw("fens", seed=13)
        b = carto.draw("fens", seed=13)
        self.assertEqual([t["name"] for t in a.towns],
                         [t["name"] for t in b.towns])
        self.assertNotEqual([t["name"] for t in a.towns],
                            [t["name"] for t in carto.draw("fens", seed=14).towns])


class TestADrawnMarchIsARealOne(unittest.TestCase):
    """Everything downstream reads the map it is given. If a generated march
    needed special cases anywhere, it would be a sandbox rather than a map."""

    def test_every_region_starts_and_runs(self):
        for key in carto.REGIONS:
            with self.subTest(region=key):
                g = played(key, days=120)
                self.assertGreater(g.home().population, 0)
                self.assertTrue(g.world.towns)
                self.assertTrue(g.world.shrines)

    def test_the_lords_have_characters_on_a_drawn_map_too(self):
        g = drawn_game("po", seed=5)
        self.assertGreater(len({round(t.aggression, 2)
                                for t in g.world.towns.values()}), 3)

    def test_and_the_towns_have_skylines_off_their_own_ground(self):
        g = drawn_game("baltic", seed=5)
        self.assertTrue(all(t.culture in cultures.CULTURES
                            for t in g.world.towns.values()))

    def test_the_chancery_works_on_it(self):
        g = played("pennines", days=200)
        for key in g.world.towns:
            self.assertIsInstance(g.court.opinion(key, g.day), float)

    def test_it_saves_and_loads(self):
        g = played("fens", days=60)
        back = GameState.from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual(back.home().name, g.home().name)
        self.assertEqual(sorted(back.world.towns), sorted(g.world.towns))

    def test_the_briefing_says_where_you_are_and_what_it_is_like(self):
        g = drawn_game("fens", seed=5)
        self.assertIn("the Fens", g.briefing)
        self.assertIn("mostly water", g.briefing)

    def test_a_fen_march_is_poorer_than_a_river_one(self):
        """The dials have to reach the ledger or they are scenery."""
        fen = played("fens", days=360).net_worth()
        rhine = played("rhine", days=360).net_worth()
        self.assertLess(fen, rhine)

    def test_marsh_is_land_you_own_and_cannot_work(self):
        g = drawn_game("fens", seed=5)
        s = g.home()
        self.assertGreater(s.terrain.get("marsh", 0), 0)
        from marchlands.buildings import BUILDINGS
        self.assertFalse([b for b in BUILDINGS.values()
                          if b.terrain == "marsh"],
                         "something can be built on undrained fen")

    def test_but_you_can_see_it(self):
        g = drawn_game("fens", seed=5)
        plan = plan_for(g.home())
        self.assertGreater(sum(row.count(MARSH) for row in plan.tiles), 0)

    def test_the_renderer_knows_what_a_fen_looks_like(self):
        import os
        from marchlands.web import STATIC
        with open(os.path.join(STATIC, "marchlands.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("kind === 'marsh'", js)


class TestTheCommandLine(unittest.TestCase):
    def test_region_and_dials_are_both_offered(self):
        from marchlands.__main__ import main
        import contextlib
        import io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["--list"])
        out = buf.getvalue()
        self.assertIn("--region", out)
        self.assertIn("--dials", out)
        for key in carto.REGIONS:
            self.assertIn(key, out)
