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


class TestTheHandsOutInTheCountry(unittest.TestCase):
    """Woodcutters, shepherds and quarrymen see further than the wall does,
    and say so when they see somebody coming."""

    def worked(self):
        g = new_game()
        g.advance(2)
        self.assertIn("woodcutters", g.world.settlements["aldworth"].rangers())
        return g

    def test_a_worked_woodcutter_widens_the_ring(self):
        g = self.worked()
        wide = len(g.shroud.visible)
        for b in g.world.settlements["aldworth"].buildings:
            if b.key in g.world.settlements["aldworth"].RANGERS:
                b.enabled = False
        g._scout()
        self.assertLess(len(g.shroud.visible), wide)
        self.assertFalse(g._rings)

    def test_farms_do_not_count(self):
        s = self.worked().world.settlements["aldworth"]
        self.assertNotIn("farm", s.RANGERS)
        self.assertEqual(len(s.rangers()),
                         sum(1 for b in s.buildings
                             if b.key in s.RANGERS and b.worked))

    def march_on(self, g, origin="caldmoor", days=12):
        """A real host on a real road: from a town well outside the ring,
        marching on Aldworth, morning after morning until it is there."""
        from marchlands.military import Army
        a = Army(uid=903, name="the Margrave's host", owner=origin,
                 units={"spearman": 30}, at=origin)
        g._set_march(a, origin, "aldworth", a.units)
        g.armies.append(a)
        lines = []
        for _ in range(days):
            before = len(g.chronicle.entries)
            g._look_around()
            lines += [e.text for e in g.chronicle.entries[before:]
                      if "saw the Margrave's host" in e.text]
            a.days_left -= 1
            if a.days_left <= 0:
                break
        return lines

    def test_a_host_marching_on_you_is_reported_once(self):
        # The case that mattered and never fired: a host bound for one of
        # yours is 'close' all the way, so a seen-yesterday test never let
        # the line through -- and it steps 18 leagues across a 6-league band.
        lines = self.march_on(self.worked())
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("out of Aldworth saw the Margrave's host", lines[0])
        self.assertIn("strong, on the road to Aldworth.", lines[0])

    def test_no_hands_out_no_line(self):
        g = self.worked()
        for b in g.world.settlements["aldworth"].buildings:
            if b.key in g.world.settlements["aldworth"].RANGERS:
                b.enabled = False
                b.throughput = 0.0
        self.assertEqual(self.march_on(g), [])

    def test_a_host_that_set_out_inside_the_ring_is_not_their_news(self):
        self.assertEqual(self.march_on(self.worked(), origin="dunmere"), [])

    def test_the_nearer_town_gets_the_credit(self):
        g = self.worked()
        g._scout()
        r = g._rings["aldworth"]
        ax, ay = g.world.coords["aldworth"]
        from marchlands.military import MARCHING, Army
        other = g.world.settlements["aldworth"]
        g.world.settlements["greyfell"] = start("marchlands", seed=3).world.settlements["aldworth"]
        g.world.settlements["greyfell"].name = "Greyfell"
        g.world.coords["greyfell"] = (ax + 40, ay)
        g._rings = {"aldworth": r, "greyfell": r}
        g.world.settlements["greyfell"].rangers = other.rangers
        a = Army(uid=904, name="the Margrave's host", owner="caldmoor",
                 units={"spearman": 30}, at="caldmoor", bound_for="aldworth",
                 state=MARCHING, days_left=3, leg_days=5)
        g.host_xy = lambda h: (ax + 40 + r - 2, ay)   # just inside Greyfell's
        g._ranger_saw(a)
        self.assertIn("out of Greyfell saw", g.chronicle.entries[-1].text)

    def test_no_road_no_dangling_comma(self):
        g = self.worked()
        g._scout()
        from marchlands.military import MARCHING, Army
        a = Army(uid=905, name="a host", owner="caldmoor",
                 units={"spearman": 12}, at="caldmoor", bound_for="nowhere",
                 state=MARCHING, days_left=3, leg_days=5)
        ax, ay = g.world.coords["aldworth"]
        g.host_xy = lambda h: (ax + 1, ay)
        g._ranger_saw(a)
        self.assertTrue(g.chronicle.entries[-1].text.endswith("about 12 strong."))


if __name__ == "__main__":
    unittest.main()
