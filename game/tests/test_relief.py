"""Relief: a host that comes up to a place under siege gives battle in the open.

Before this a host you marched to your own besieged town stood down beside
the besiegers and nobody fought anybody. Now it stands off, the ring must
turn and face it at dawn, and the fight runs on the same Battle machine as
the storm -- playable when you are in it, no wall, no oil, no pitch.
"""
import unittest

from marchlands.clock import watch
from marchlands.engine import GameState
from marchlands.military import (Army, BESIEGING, GARRISON, MARCHING, RAIDING,
                                 RELIEVING, RETURNING)
from marchlands.scenarios import start


def besieged_home(seed=3, ring_men=12, relief_men=80):
    """The player's town with a lord's host sitting before it, and a
    player host one day's march out with orders to come home."""
    g = start("marchlands", seed=seed)
    home = next(iter(g.world.settlements))
    st = g.world.settlements[home]
    st.units = {"spearman": 6.0}
    lord = next(k for k in g.world.towns)
    ring = Army(uid=900, name="The Ring", owner=lord,
                units={"spearman": float(ring_men)}, at=home, home=lord, state=BESIEGING)
    g.armies.append(ring)
    relief = Army(uid=901, name="Your Relief", owner="player",
                  units={"spearman": float(relief_men), "knight": 6.0},
                  at="", bound_for=home, home=home, state=MARCHING, days_left=1.0)
    g.armies.append(relief)
    g.next_army_uid = 902
    return g, home, ring, relief


class TestComingUp(unittest.TestCase):
    def test_a_host_arriving_at_the_ring_stands_off_for_dawn(self):
        g, home, ring, relief = besieged_home()
        said = " ".join(g.advance(1))
        self.assertEqual(relief.state, RELIEVING)
        self.assertIn("must turn and fight at dawn", said)
        # The ring is still sitting; nothing has been fought yet.
        self.assertEqual(ring.state, BESIEGING)

    def test_a_host_arriving_at_a_quiet_place_just_walks_in(self):
        g, home, ring, relief = besieged_home()
        g.armies.remove(ring)
        g.advance(1)
        self.assertEqual(relief.state, GARRISON)


class TestTheFieldResolved(unittest.TestCase):
    """Auto mode: the fight runs at dawn and the day carries on."""

    def test_a_strong_relief_breaks_the_siege(self):
        g, home, ring, relief = besieged_home(ring_men=10, relief_men=120)
        g.advance(1)
        said = " ".join(g.advance(1))
        self.assertIn("BATTLE BEFORE", said)
        self.assertIn("siege of", said)
        self.assertEqual(relief.state, GARRISON, "the relief is inside now")
        # Routed, or destroyed outright and buried by the day: either way
        # it is not sitting before the town any more.
        if ring in g.armies:
            self.assertIn(ring.state, (MARCHING, RETURNING), "the ring falls back")
            self.assertEqual(ring.bound_for, ring.home)
        else:
            self.assertIn("is no more", said)
        self.assertFalse(any(a.state == BESIEGING and a.at == home for a in g.armies))
        self.assertIsNone(g.pending)

    def test_a_weak_relief_is_thrown_back_and_the_ring_stays(self):
        g, home, ring, relief = besieged_home(ring_men=120, relief_men=8)
        g.advance(1)
        said = " ".join(g.advance(1))
        self.assertIn("BATTLE BEFORE", said)
        self.assertEqual(ring.state, BESIEGING)
        self.assertEqual(ring.at, home)
        # Its own gate: what is left slips inside rather than marching home.
        if relief in g.armies:
            self.assertEqual(relief.state, GARRISON)
            self.assertIn("slips inside", said)

    def test_men_are_conserved_across_the_pooled_line(self):
        g, home, ring, relief = besieged_home(ring_men=40, relief_men=40)
        second = Army(uid=903, name="Second", owner="player",
                      units={"archer": 20.0}, at=home, home=home, state=RELIEVING)
        g.armies.append(second)
        g.advance(1)
        before = relief.size + second.size + ring.size
        g.advance(1)
        after = sum(a.size for a in g.armies if a.uid in (901, 903, 900))
        self.assertLess(after, before, "somebody fell")
        for a in g.armies:
            for k, v in a.units.items():
                self.assertGreaterEqual(v, 0.5, (a.name, k, v))

    def test_a_lord_coming_home_through_your_lines_fights_you(self):
        g = start("marchlands", seed=3)
        home = next(iter(g.world.settlements))
        g.world.settlements[home].units = {"spearman": 60.0, "archer": 20.0}
        lord = next(k for k in g.world.towns)
        mine, why = g.raise_host(home, {"spearman": 50, "archer": 15})
        self.assertIsNotNone(mine, why)
        mine.at, mine.state, mine.bound_for = lord, BESIEGING, ""
        theirs = Army(uid=950, name="Their Riders", owner=lord,
                      units={"knight": 4.0}, at="", bound_for=lord, home=lord,
                      state=MARCHING, days_left=1.0)
        g.armies.append(theirs)
        said = " ".join(g.advance(1))
        self.assertEqual(theirs.state, RELIEVING)
        self.assertIn("comes up behind your lines", said)
        said = " ".join(g.advance(1))
        self.assertIn("BATTLE BEFORE", said)
        self.assertNotIn(theirs, g.armies, "beaten or inside, either way not standing outside")
        self.assertEqual(mine.state, BESIEGING)

    def test_two_lords_at_each_others_walls_are_not_your_business(self):
        g = start("marchlands", seed=3)
        towns = list(g.world.towns)
        a, b = towns[0], towns[1]
        besieger = Army(uid=960, name="A's host", owner=a, units={"spearman": 30.0},
                        at=b, home=a, state=BESIEGING)
        homecoming = Army(uid=961, name="B's riders", owner=b, units={"knight": 3.0},
                          at="", bound_for=b, home=b, state=MARCHING, days_left=1.0)
        g.armies += [besieger, homecoming]
        g.battles_mode = "play"
        g.advance(1)
        self.assertNotIn(homecoming, g.armies, "walked in as it always has")
        self.assertIsNone(g.pending)


class TestTheFieldPlayed(unittest.TestCase):
    def setUp(self):
        self.g, self.home, self.ring, self.relief = besieged_home(ring_men=40, relief_men=60)
        self.g.battles_mode = "play"
        self.g.advance(1)
        self.said = " ".join(self.g.advance(1))

    def test_the_day_waits_on_the_field(self):
        g = self.g
        self.assertIsNotNone(g.pending)
        self.assertEqual((g.pending.kind, g.pending.side), ("field", "attacker"))
        self.assertIn("BATTLE IS JOINED", self.said)
        self.assertIn("battle is joined before", watch(g)["battle"])
        waited = g.tick()
        self.assertIn("waits on the fight", " ".join(waited))

    def test_the_open_field_has_no_wall_and_no_pots(self):
        v = self.g.battle_view()
        self.assertEqual(v["wall_full"], 0)
        self.assertNotIn("oil", v["can"])
        self.assertNotIn("pitch", v["can"])
        # And the other side's levers, read directly.
        self.assertNotIn("oil", self.g.pending.battle.can("defender"))

    def test_letting_it_run_settles_it_and_the_day_goes_on(self):
        g = self.g
        out = g.battle_step("auto")
        self.assertIn("BATTLE BEFORE", out)
        self.assertTrue(g.pending.settled)
        after = g.pending.after
        self.assertTrue(any("BATTLE BEFORE" in line for line in after))
        g.tick()
        self.assertIsNone(g.pending)
        self.assertIn(self.relief.state if self.relief in g.armies else GARRISON,
                      (GARRISON, MARCHING, RETURNING))

    def test_a_field_survives_a_save_mid_fight(self):
        g = self.g
        g.battle_step("fight")
        g2 = GameState.from_dict(g.to_dict())
        self.assertEqual(g2.pending.kind, "field")
        self.assertEqual(g2.pending.foes, [self.ring.uid])
        self.assertEqual(g2.pending.stationed, [self.relief.uid])
        g2.battles_mode = "play"
        out = g2.battle_step("auto")
        self.assertIn("BATTLE BEFORE", out)


if __name__ == "__main__":
    unittest.main()
