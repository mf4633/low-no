"""Riding at their head: the lord as one man in the line.

The screen fights it and the console rolls it, and either way the engine
believes only so much -- kills capped at an order's worth of the men facing
him, blows counted against the three that bear him down. What it costs is
himself: weeks abed, or dead where he stood and the hall empty.
"""
import io
import pathlib
import unittest

from marchlands import lord as manly
from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.military import Army, BESIEGING
from marchlands.scenarios import start

STATIC = pathlib.Path(__file__).resolve().parents[1] / "marchlands" / "static"


def storm(seed=3, garrison=None, riding=True, host=None):
    host = host or (dict(EVEN) if garrison is not None else None)
    """The player's host going in at a foreign wall, the lord with it."""
    g = start("marchlands", seed=seed)
    g.battles_mode = "play"
    home = next(iter(g.world.settlements))
    target = next(k for k in g.world.towns)
    town = g.world.towns[target]
    town.wall_hp = 0.0
    if garrison:
        town.garrison = dict(garrison)
    a = Army(uid=501, name="Your host", owner="player",
             units=host or {"spearman": 40.0, "archer": 10.0},
             at=target, home=home, state=BESIEGING)
    g.armies.append(a)
    g.next_army_uid = 502
    if riding:
        g.lord.riding = 501
    g._siege_town(a, town)
    assert g.pending is not None
    return g, a, town


#: A wall held in strength against a host of the same strength: three or
#: more rounds at seed 3, which is what a test about blows across rounds
#: needs. A garrison that breaks in one round puts the lord's blows down
#: with the fight before they can be counted.
BIG = {"spearman": 300.0, "archer": 60.0}
EVEN = {"spearman": 300.0, "archer": 60.0}


class TestTheRide(unittest.TestCase):
    def test_the_lord_with_the_host_may_ride(self):
        g, a, town = storm(garrison=BIG)
        r = g.battle_view()["ride"]
        self.assertTrue(r["can"], r)
        self.assertEqual(r["down"], manly.RIDE_HITS_DOWN)
        self.assertGreaterEqual(r["press"], 3)
        self.assertEqual(r["cap"], min(manly.RIDE_KILL_CAP, int(360 * manly.RIDE_KILL_SHARE)))

    def test_a_lord_elsewhere_may_not(self):
        g, a, town = storm(riding=False)
        r = g.battle_view()["ride"]
        self.assertFalse(r["can"])
        self.assertIn("not with this host", r["why"])
        self.assertIn("not with this host", g.battle_step("ride", "3 0"))

    def test_kills_are_capped_and_come_off_the_line(self):
        g, a, town = storm(garrison=BIG)
        b = g.pending.battle
        them = b.side("defender")
        cap = g.battle_view()["ride"]["cap"]
        before = them.alive()
        said = g.battle_step("ride", "99 0")
        self.assertIn(f"{cap} men cut down", said)
        self.assertEqual(g.pending.lord_kills, cap)
        # What the round then took is on top; the ride's own share is the cap.
        self.assertLess(them.alive(), before - cap + 0.01)

    def test_his_men_are_steadier_for_seeing_him_and_he_learns_valour(self):
        g, a, town = storm(garrison=BIG)
        b = g.pending.battle
        mine = b.side("attacker")
        was = mine.morale
        g.battle_step("ride", "0 0")
        self.assertGreater(g.pending.lord_rally, 0)
        self.assertGreater(g.kin.lord.xp.get("valour", 0.0), 0)
        # Capped over the fight: ride and ride and it stops giving.
        for _ in range(8):
            if g.pending.battle.over:
                break
            g.battle_step("ride", "0 0")
        self.assertLessEqual(g.pending.lord_rally, manly.RIDE_RALLY_CAP + 1e-9)

    def test_three_blows_bear_him_down_wounded(self):
        g, a, town = storm(garrison=BIG)
        manly_death, manly.RIDE_DEATH = manly.RIDE_DEATH, 0.0
        try:
            said = g.battle_step("ride", "0 3")
        finally:
            manly.RIDE_DEATH = manly_death
        self.assertIn("borne back wounded", said)
        lo, hi = manly.WOUND_DAYS
        self.assertTrue(lo <= g.lord.wounded <= hi)
        self.assertEqual(g.lord.hits, 0)
        r = g.battle_view()["ride"]
        self.assertFalse(r["can"])
        self.assertIn("abed", r["why"])
        # Abed he is no use to the host and not to be sent anywhere.
        self.assertEqual(manly.attack_bonus(g.lord, 501), 1.0)
        self.assertIn("abed", g.lead(501))
        # And he heals, a day at a time.
        days = g.lord.wounded
        for _ in range(days - 1):
            g.lord.day()
        self.assertEqual(g.lord.wounded, 1)
        self.assertIn("on his feet", " ".join(g.lord.day()))
        self.assertEqual(manly.attack_bonus(g.lord, 501), 1.0 + manly.FIELD_ATTACK)

    def test_blows_accumulate_across_rounds(self):
        g, a, town = storm(garrison=BIG)
        manly_death, manly.RIDE_DEATH = manly.RIDE_DEATH, 0.0
        try:
            g.battle_step("ride", "0 1")
            self.assertEqual(g.lord.hits, 1)
            g.battle_step("ride", "0 1")
            self.assertEqual(g.lord.hits, 2)
            said = g.battle_step("ride", "0 1")
        finally:
            manly.RIDE_DEATH = manly_death
        self.assertIn("borne back", said)

    def test_a_blow_too_many_can_kill_him(self):
        g, a, town = storm(garrison=BIG)
        was = g.lord.name
        manly_death, manly.RIDE_DEATH = manly.RIDE_DEATH, 1.0
        try:
            said = g.battle_step("ride", "0 3")
        finally:
            manly.RIDE_DEATH = manly_death
        self.assertIn("cut down at the head of his men", said)
        self.assertFalse(g.lord.alive)
        self.assertEqual(g.lord.riding, 0)
        self.assertNotEqual(g.lord.name, was, "the heir is named")
        self.assertTrue(any("cut down at the head" in ln for ln in g.pending.lord_lines))

    def test_the_aftermath_says_what_his_hand_did(self):
        g, a, town = storm(garrison=BIG)
        g.battle_step("ride", "2 0")
        g.battle_step("auto")
        after = " ".join(g.pending.after)
        self.assertIn("rode 1 round at their head", after)
        self.assertIn("by his own hand", after)
        self.assertEqual(g.lord.hits, 0, "the fight's blows are put down with it")

    def test_the_dice_ride_where_there_is_no_screen(self):
        g, a, town = storm(garrison=BIG)
        buf = io.StringIO()
        Console(g, out=buf).do("battle ride")
        self.assertIn("rides at their head", buf.getvalue())
        self.assertEqual(g.pending.lord_rode, 1)

    def test_the_ride_survives_a_save(self):
        g, a, town = storm(garrison=BIG)
        g.battle_step("ride", "1 1")
        g2 = GameState.from_dict(g.to_dict())
        self.assertEqual((g2.pending.lord_rode, g2.pending.lord_kills), (1, 1))
        self.assertEqual(g2.lord.hits, 1)
        self.assertEqual(g2.lord.wounded, 0)

    def test_at_home_on_his_own_wall_he_may_ride(self):
        g = start("marchlands", seed=3)
        g.battles_mode = "play"
        home = next(iter(g.world.settlements))
        st = g.world.settlements[home]
        st.units = {"spearman": 20.0}
        st.wall_hp = 0.0
        lord_key = next(k for k in g.world.towns)
        ring = Army(uid=700, name="Ring", owner=lord_key, units={"spearman": 60.0},
                    at=home, home=lord_key, state=BESIEGING)
        g.armies.append(ring)
        g.lord.seat = st.name
        g._siege_settlement(ring, st)
        self.assertIsNotNone(g.pending)
        self.assertEqual(g.pending.kind, "wall")
        r = g.battle_view()["ride"]
        self.assertTrue(r["can"], r)


class TestTheScreen(unittest.TestCase):
    def test_the_client_fights_it_and_reports_it_as_the_same_command(self):
        js = (STATIC / "marchlands.js").read_text()
        html = (STATIC / "index.html").read_text()
        self.assertIn('id="battle-ride"', html)
        self.assertIn('id="melee-hud"', html)
        self.assertIn("send(`battle ride ${k} ${h}`)", js)
        for fn in ("startMelee", "meleeStrike", "stepMelee", "endMelee", "drawMelee"):
            self.assertIn(f"function {fn}", js)
        # Kills the screen may claim stop at the engine's cap; the engine
        # caps again regardless, but the screen should not lie to the eye.
        self.assertIn("if (m.kills < m.cap) m.kills++", js)


if __name__ == "__main__":
    unittest.main()
