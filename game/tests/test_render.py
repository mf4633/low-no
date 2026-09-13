"""Ink and the town plan.

The rule that matters: a piped transcript, a test's StringIO and a dumb
terminal must all come out as plain text. Everything else here is layout.
"""

import io
import unittest

from marchlands import render as ink
from marchlands.buildings import BUILDINGS
from marchlands.cli import Console
from marchlands.scenarios import start
from marchlands.sim import Bot
from marchlands.view import GLYPHS, townscape


class TestColourDiscipline(unittest.TestCase):
    def tearDown(self):
        ink.set_colour(False)

    def test_colour_off_means_plain_text(self):
        ink.set_colour(False)
        self.assertEqual(ink.c("hello", ink.GOLD, bold=True), "hello")
        self.assertNotIn("\033", ink.head("TITLE", "right"))
        self.assertNotIn("\033", ink.bar(5, 10))
        self.assertNotIn("\033", ink.coin(-40))

    def test_colour_on_wraps_and_resets(self):
        ink.set_colour(True)
        out = ink.c("hello", ink.GOLD)
        self.assertTrue(out.startswith("\033["))
        self.assertTrue(out.endswith("\033[0m"))
        self.assertIn("hello", out)

    def test_width_ignores_the_escapes(self):
        ink.set_colour(True)
        self.assertEqual(ink.width(ink.c("abcd", ink.GOLD, bold=True)), 4)
        self.assertEqual(ink.width(ink.pad(ink.c("ab", ink.GOLD), 8)), 8)

    def test_a_piped_console_never_emits_escapes(self):
        buf = io.StringIO()
        con = Console(start("marchlands", seed=5), out=buf)
        for cmd in ("status", "view", "town", "map", "war", "prices bread",
                    "stores", "scan 2", "caravans", "units", "age", "tech",
                    "hint", "briefing", "scenarios", "next 2"):
            con.do(cmd)
        self.assertNotIn("\033", buf.getvalue())

    def test_bars_warn_by_colour(self):
        ink.set_colour(True)
        self.assertIn(str(ink.BLOOD), ink.bar(1, 10))
        self.assertIn(str(ink.LEAF), ink.bar(9, 10))
        self.assertIn(str(ink.LEAF), ink.coin(50, plus=True))
        self.assertIn(str(ink.BLOOD), ink.coin(-50, plus=True))


class TestTownPlan(unittest.TestCase):
    def setUp(self):
        ink.set_colour(False)
        self.g = start("marchlands", seed=5)
        Bot(self.g).run(300)
        self.s = self.g.world.settlements["aldworth"]

    def test_every_building_has_a_glyph(self):
        missing = [k for k in BUILDINGS if k not in GLYPHS]
        self.assertEqual(missing, [], f"no glyph for {missing}")

    def test_the_plan_draws_the_walls_and_the_keep(self):
        rows = townscape(self.s, self.g.progress, "summer")
        body = "\n".join(rows)
        self.assertIn("▣", body, "the keep is not on the plan")
        self.assertTrue(any("─" in r or "═" in r for r in rows), "no walls drawn")
        self.assertIn("The Keep", body, "the legend omits the keep")

    def test_the_plan_fits_the_terminal(self):
        for line in townscape(self.s, self.g.progress, "summer"):
            self.assertLessEqual(ink.width(line), 76, repr(line))

    def test_what_is_standing_is_what_is_drawn(self):
        rows = "\n".join(townscape(self.s, self.g.progress, "summer"))
        for b in self.s.buildings:
            if b.complete and b.spec.terrain != "rampart":
                self.assertIn(BUILDINGS[b.key].name, rows, b.key)

    def test_the_seasons_look_different(self):
        ink.set_colour(True)
        spring = "\n".join(townscape(self.s, self.g.progress, "spring"))
        winter = "\n".join(townscape(self.s, self.g.progress, "winter"))
        self.assertNotEqual(spring, winter)
        ink.set_colour(False)

    def test_a_besieged_wall_reads_as_trouble(self):
        ink.set_colour(True)
        calm = "\n".join(townscape(self.s, self.g.progress, "summer"))
        under = "\n".join(townscape(self.s, self.g.progress, "summer",
                                    besieged=True))
        self.assertNotEqual(calm, under)
        self.assertIn(str(ink.AMBER), under)   # the wall reads as at risk
        ink.set_colour(False)

    def test_a_town_with_nothing_built_still_draws(self):
        g = start("marchlands", seed=1)
        g.treasury = 20_000
        g.found("greyfell")
        rows = townscape(g.world.settlements["greyfell"], g.progress, "winter")
        self.assertTrue(rows)


if __name__ == "__main__":
    unittest.main()
