"""The holding in perspective."""

import io
import unittest

from marchlands import render as ink
from marchlands.buildings import BUILDINGS
from marchlands.cli import Console
from marchlands.iso import SPRITES, Grid, scene
from marchlands.scenarios import start
from marchlands.sim import Bot


class TestGeometry(unittest.TestCase):
    def test_the_grid_grows_with_the_town(self):
        small, big = Grid(4, 4), Grid(40, 20)
        self.assertLess(small.side, big.side)
        self.assertLess(small.w, big.w)

    def test_the_precinct_sits_inside_the_grid(self):
        for urban in (1, 9, 25, 60):
            g = Grid(urban, 12)
            self.assertGreaterEqual(g.x0 - 1, 0)
            self.assertGreaterEqual(g.y0 - 1, 0)
            self.assertLess(g.x1 + 1, g.gx)
            self.assertLess(g.y1 + 1, g.gy)

    def test_tiles_further_back_sit_higher_up(self):
        g = Grid(16, 12)
        near = g.screen(g.x1, g.y1)
        far = g.screen(g.x0, g.y0)
        self.assertLess(far[1], near[1])


class TestSprites(unittest.TestCase):
    def test_every_building_has_one(self):
        missing = [k for k in BUILDINGS if k not in SPRITES]
        self.assertEqual(missing, [], f"no sprite for {missing}")

    def test_they_are_narrow_enough_not_to_collide(self):
        for key, rows in SPRITES.items():
            for line, _colour in rows:
                self.assertLessEqual(len(line), 3, key)


class TestScene(unittest.TestCase):
    def setUp(self):
        ink.set_colour(False)
        self.g = start("marchlands", seed=5)
        Bot(self.g).run(360)
        self.s = self.g.world.settlements["aldworth"]

    def draw(self, **kw):
        return scene(self.s, self.g.progress, kw.pop("season", "summer"),
                     kw.pop("day", 100), **kw)

    def test_it_fits_a_terminal(self):
        for line in self.draw():
            self.assertLessEqual(ink.width(line), 78, repr(line))

    def test_the_keep_stands_above_the_wall(self):
        rows = self.draw()
        body = "\n".join(rows)
        self.assertIn("▀", body)       # roofs
        self.assertIn("█", body)       # walls and bodies
        self.assertGreater(len(rows), 12)

    def test_the_town_works_and_you_can_see_it(self):
        """Smoke over the ovens, sails on the mill, people in the street."""
        body = "\n".join(self.draw())
        self.assertTrue(any(ch in body for ch in "˚°·˙"), "no smoke anywhere")
        self.assertTrue(any(ch in body for ch in "îïìí"), "nobody in the streets")

    def test_the_days_are_not_identical(self):
        self.assertNotEqual("\n".join(self.draw(day=10)),
                            "\n".join(self.draw(day=11)))

    def test_the_seasons_are_not_identical(self):
        ink.set_colour(True)
        a = "\n".join(self.draw(season="summer"))
        b = "\n".join(self.draw(season="winter"))
        ink.set_colour(False)
        self.assertNotEqual(a, b)

    def test_a_siege_shows_on_the_wall(self):
        ink.set_colour(True)
        calm = "\n".join(self.draw())
        under = "\n".join(self.draw(besieged=True))
        ink.set_colour(False)
        self.assertNotEqual(calm, under)

    def test_an_empty_holding_still_draws(self):
        g = start("marchlands", seed=1)
        g.treasury = 20_000
        g.found("greyfell")
        rows = scene(g.world.settlements["greyfell"], g.progress, "winter", 3)
        self.assertTrue(rows)


class TestConsole(unittest.TestCase):
    def test_view_and_watch_render_without_escapes(self):
        buf = io.StringIO()
        con = Console(start("marchlands", seed=5), out=buf)
        con.do("view")
        con.do("view flat")
        con.do("watch 2")
        out = buf.getvalue()
        self.assertNotIn("\033", out)
        self.assertIn("ALDWORTH", out)
        self.assertIn("standing", out)

    def test_watch_advances_the_days(self):
        con = Console(start("marchlands", seed=5), out=io.StringIO())
        before = con.game.day
        con.do("watch 3")
        self.assertEqual(con.game.day, before + 3)


if __name__ == "__main__":
    unittest.main()
