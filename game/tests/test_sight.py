"""The shroud: the march is blank until somebody of yours goes and looks.

Two layers, the way every game with a shroud keeps them -- explored, which
is for good and is saved, and in sight, which is worked out every morning
from where your towns, carts and hosts stand.
"""
import io
import unittest

from marchlands import sight, web
from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.scenarios import start

NEAR = {"aldworth", "dunmere", "vantry", "st_ceol", "holy_thorn"}


def keys(m):
    return {n["key"] for n in m["nodes"]}


def new_game():
    g = start("marchlands", seed=3)
    web.march(g, "aldworth")          # the first look, as the page takes it
    return g


def a_host(g):
    s = g.world.settlements["aldworth"]
    Console(g, out=io.StringIO()).do("host aldworth spearman 4")
    return next(a for a in g.armies if a.owner == "player")


class TestTheGrid(unittest.TestCase):
    def test_a_disc_is_a_circle(self):
        cells = set(sight.disc(0.0, 0.0, 20.0))
        self.assertIn(sight.cell_of(0, 0), cells)
        self.assertIn(sight.cell_of(15, 0), cells)
        self.assertNotIn(sight.cell_of(20, 20), cells)     # the corner is out

    def test_explored_outlives_the_morning(self):
        sh = sight.Shroud()
        sh.look(0, 0, 10)
        sh.morning()
        self.assertTrue(sh.known(0, 0))
        self.assertFalse(sh.sees(0, 0))

    def test_a_trail_explores_the_road_between(self):
        sh = sight.Shroud()
        sh.trail((0, 0), (100, 0), 10)
        self.assertTrue(sh.known(50, 0))
        self.assertFalse(sh.sees(50, 0))


class TestTheMap(unittest.TestCase):
    def test_you_begin_seeing_round_your_own_walls(self):
        m = web.march(start("marchlands", seed=3), "aldworth")
        self.assertEqual(keys(m), NEAR)
        for r in m["runs"]:
            self.assertIn(r["from"], NEAR)
            self.assertIn(r["to"], NEAR)
        self.assertTrue(m["roads"])
        self.assertEqual(len(m["bounds"]), 4)

    def test_a_marching_host_clears_the_road_it_takes(self):
        g = new_game()
        a = a_host(g)
        Console(g, out=io.StringIO()).do(f"march {a.uid} caldmoor")
        seen = []
        for _ in range(8):
            g.advance(1)
            m = web.march(g, "aldworth")
            seen.append(keys(m))
            mine = next(h for h in m["hosts"] if h["mine"])
            self.assertIsNotNone(mine["xy"])
        self.assertIn("caldmoor", seen[-1])
        # And it came out of the blank on the way, not at the end.
        self.assertIn("bruille", seen[2])
        self.assertNotIn("caldmoor", seen[0])

    def test_between_two_towns_is_somewhere(self):
        g = new_game()
        a = a_host(g)
        Console(g, out=io.StringIO()).do(f"march {a.uid} caldmoor")
        g.advance(2)
        x, y = g.host_xy(a)
        home = g.world.coords["aldworth"]
        self.assertNotEqual((x, y), tuple(home))
        self.assertTrue(g.shroud.sees(x, y))

    def test_theirs_in_sight_are_seen_and_theirs_beyond_are_not(self):
        from marchlands.military import Army
        g = new_game()
        near = Army(uid=901, name="near", owner="vantry",
                    units={"spearman": 20}, at="vantry")
        far = Army(uid=902, name="far", owner="havnhold",
                   units={"spearman": 20}, at="havnhold")
        g.armies += [near, far]
        g._look_around()
        self.assertEqual(near.seen_day, g.day)
        self.assertLess(far.seen_day, 0)


class TestTheSave(unittest.TestCase):
    def test_what_you_explored_is_kept(self):
        g = new_game()
        g2 = GameState.from_dict(g.to_dict())
        self.assertEqual(g2.shroud.explored, g.shroud.explored)
        self.assertFalse(g2.shroud.everything)
        self.assertEqual(keys(web.march(g2, "aldworth")), NEAR)

    def test_a_save_from_before_the_shroud_shows_the_whole_map(self):
        g = new_game()
        d = g.to_dict()
        del d["shroud"]
        g2 = GameState.from_dict(d)
        self.assertTrue(g2.shroud.everything)
        self.assertLessEqual(set(g.world.coords), keys(web.march(g2, "aldworth")))


if __name__ == "__main__":
    unittest.main()
