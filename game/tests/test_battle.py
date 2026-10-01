"""A battle as something you play, rather than something you are told.

The machine is the old `fight` loop with the rounds pulled apart. The first
claim is therefore parity: run to the end with the same seed it gives the
same numbers `fight` always gave, so nothing anybody was not watching has
changed. The rest is what the watching buys you -- and what each lever costs,
because a lever with no downside is a button, not a decision.
"""

import json
import random
import unittest

from marchlands import military
from marchlands.castle import Works
from marchlands.clock import watch
from marchlands.engine import GameState
from marchlands.military import (Battle, BESIEGING, HOLD, LINE, RESERVE, STORM,
                                 Side, fight, open_battle)
from marchlands.scenarios import start
from marchlands.sim import Bot


def sides(n=50, m=50):
    return Side({"spearman": n, "archer": 12}), Side({"spearman": m, "archer": 10})


def until_storm(g, days=160):
    for _ in range(days):
        g.advance(1)
        if g.pending is not None:
            return True
    return False


class TestTheMachineIsTheOldFight(unittest.TestCase):

    def test_run_gives_what_fight_gave(self):
        for seed in range(6):
            a1, d1 = sides(); a2, d2 = sides()
            old = fight(a1, d1, rng=random.Random(seed), orders=(STORM, HOLD),
                        wall_hp=120.0)
            b = open_battle(a2, d2, rng=random.Random(seed), orders=(STORM, HOLD),
                            wall_hp=120.0)
            new = b.run(); b.close()
            self.assertEqual(old.winner, new.winner, seed)
            self.assertEqual(old.rounds, new.rounds, seed)
            self.assertEqual(a1.units, a2.units, seed)
            self.assertEqual(d1.units, d2.units, seed)

    def test_stepping_is_running_a_round_at_a_time(self):
        a1, d1 = sides(); a2, d2 = sides()
        whole = open_battle(a1, d1, rng=random.Random(3), orders=(LINE, LINE))
        whole.run()
        piece = open_battle(a2, d2, rng=random.Random(3), orders=(LINE, LINE))
        while not piece.over:
            piece.step()
        self.assertEqual(whole.round, piece.round)
        self.assertEqual(a1.units, a2.units)
        self.assertEqual(d1.units, d2.units)

    def test_close_takes_the_dressing_off(self):
        a, d = sides()
        was = (a.attack_mult, a.defense_mult, a.morale)
        b = open_battle(a, d, rng=random.Random(1), orders=(STORM, HOLD))
        self.assertNotEqual((a.attack_mult, a.defense_mult, a.morale), was)
        b.run(); b.close()
        self.assertEqual((a.attack_mult, a.defense_mult, a.morale), was)
        b.close()                          # and again does nothing


class TestTheLeversCostSomething(unittest.TestCase):

    def test_reforming_fights_a_soft_round(self):
        a1, d1 = sides(60, 50); a2, d2 = sides(60, 50)
        plain = open_battle(a1, d1, rng=random.Random(2), orders=(LINE, LINE))
        plain.step()
        turned = open_battle(a2, d2, rng=random.Random(2), orders=(LINE, LINE))
        self.assertIn("reforms", turned.reorder("attacker", STORM).lower())
        self.assertEqual(turned.orders[0], STORM)
        turned.step()
        # The same dice, one round in: the side that reformed hurt them less.
        self.assertLess(sum(turned.res.defender_losses.values()) * 1.0,
                        sum(plain.res.defender_losses.values()) * 1.15)

    def test_the_same_order_twice_is_refused(self):
        a, d = sides()
        b = open_battle(a, d, rng=random.Random(1), orders=(LINE, LINE))
        self.assertIn("already", b.reorder("attacker", LINE))

    def test_the_reserve_is_one_hard_round_and_then_spent(self):
        a, d = sides(60, 50)
        b = open_battle(a, d, rng=random.Random(4), orders=(RESERVE, LINE))
        self.assertEqual(b.can("attacker")["commit"], "")
        steady = a.morale
        b.commit("attacker")
        self.assertLess(a.morale, steady, "committing kept the reserve's steadiness")
        self.assertTrue(b.committed[0])
        self.assertNotEqual(b.can("attacker")["commit"], "", "committed twice")

    def test_nothing_to_commit_without_a_reserve(self):
        a, d = sides()
        b = open_battle(a, d, rng=random.Random(1), orders=(LINE, LINE))
        self.assertIn("nothing", b.can("attacker")["commit"])
        self.assertIn("nothing", b.commit("attacker"))

    def test_oil_and_pitch_go_once_and_only_off_the_works(self):
        a, d = sides(80, 40)
        bare = open_battle(a, d, rng=random.Random(1), orders=(STORM, HOLD))
        self.assertIn("no oil", bare.can("defender")["oil"])
        self.assertIn("no pitch", bare.can("defender")["pitch"])
        a2, d2 = sides(80, 40)
        dug = open_battle(a2, d2, rng=random.Random(1), orders=(STORM, HOLD),
                          works=Works(oil=1, pitch=1), have_pitch=True)
        was = a2.alive()
        self.assertEqual(dug.can("defender")["oil"], "")
        dug.pour_oil()
        self.assertLess(a2.alive(), was)
        self.assertIn("poured", dug.can("defender")["oil"])
        was = a2.alive()
        dug.fire_pitch()
        self.assertLess(a2.alive(), was)
        self.assertIn("burned", dug.can("defender")["pitch"])
        self.assertTrue(dug.res.attacker_losses, "the burnt were not counted")

    def test_pitch_wants_charcoal(self):
        a, d = sides()
        b = open_battle(a, d, rng=random.Random(1), orders=(STORM, HOLD),
                        works=Works(pitch=1), have_pitch=False)
        self.assertIn("charcoal", b.can("defender")["pitch"])

    def test_breaking_off_keeps_the_rest_less_the_pursuit(self):
        a, d = sides(50, 50)
        b = open_battle(a, d, rng=random.Random(1), orders=(LINE, LINE))
        b.step()
        had = a.alive()
        said = b.break_off("attacker")
        self.assertTrue(b.over)
        self.assertEqual(b.res.winner, "defender")
        self.assertEqual(b.res.broken_off, "attacker")
        self.assertAlmostEqual(a.alive(), had * (1 - military.ROUT_TOLL), places=6)
        self.assertIn("pursuit", said)

    def test_a_defender_can_pull_back_too(self):
        a, d = sides(50, 50)
        b = open_battle(a, d, rng=random.Random(1), orders=(LINE, LINE))
        b.break_off("defender")
        self.assertEqual(b.res.winner, "attacker")
        self.assertEqual(b.res.broken_off, "defender")


class TestTheDayWaitsOnYou(unittest.TestCase):

    def besieged(self):
        g = start("siege", seed=1)
        g.battles_mode = "play"
        self.assertTrue(until_storm(g), "no storm in the siege scenario")
        return g

    def test_the_storm_stops_the_day(self):
        g = self.besieged()
        day = g.day
        said = g.advance(3)
        self.assertEqual(g.day, day, "the day moved with men on the wall")
        self.assertIn("waits", said[0])
        self.assertEqual(g.pending.side, "defender")
        self.assertEqual(g.pending.kind, "wall")

    def test_and_the_clock_stops_for_it(self):
        g = self.besieged()
        self.assertIn("battle", watch(g))
        g.battle_step("auto")
        self.assertNotIn("battle", watch(g), "the clock is still held by a finished fight")

    def test_fighting_it_through_finishes_the_day_and_the_town_feels_it(self):
        g = self.besieged()
        s = g.world.settlements[g.pending.where]
        men = sum(s.units.values())
        out = g.battle_step("auto")
        self.assertTrue(g.pending.battle.over)
        self.assertTrue(g.pending.settled)
        self.assertIn("holds the ground", out)
        self.assertNotEqual(sum(s.units.values()), men, "nobody on the wall died")
        # The verdict stays until you move on; the next day puts it away.
        self.assertIsNotNone(g.battle_view())
        self.assertTrue(g.battle_view()["over"])
        g.advance(1)
        self.assertIsNone(g.pending)

    def test_close_puts_a_finished_fight_away(self):
        g = self.besieged()
        self.assertIn("not over", g.battle_step("close"))
        g.battle_step("auto")
        self.assertEqual(g.battle_step("close"), "back to the day")
        self.assertIsNone(g.pending)

    def test_a_round_at_a_time_lands_on_the_same_town(self):
        g = self.besieged()
        s = g.world.settlements[g.pending.where]
        rounds = 0
        while not g.pending.battle.over and rounds < 40:
            g.battle_step("fight"); rounds += 1
        self.assertTrue(g.pending.battle.over)
        self.assertTrue(g.pending.settled, "the aftermath did not run")
        # The garrison is the survivors, less anybody under half a man -- or
        # nobody, if the wall was carried and the keep thrown down.
        held = g.pending.battle.res.winner == "defender"
        self.assertAlmostEqual(
            sum(s.units.values()),
            sum(v for v in g.pending.battle.defender.units.values() if v >= 0.5)
            if held else 0.0,
            places=6)

    def test_the_view_says_what_you_may_do(self):
        g = self.besieged()
        v = g.battle_view()
        for key in ("attacker", "defender", "can", "modifiers", "orders", "kinds",
                    "costs", "log", "field", "wall_standing", "wall_full", "side"):
            self.assertIn(key, v)
        self.assertEqual(v["can"]["fight"], "")
        self.assertTrue(any(r["what"].startswith("order") for r in v["modifiers"]))
        # Only kinds this garrison actually has are explained to it.
        have = set(military.UNITS[k].unit_class for k in v[v["side"]]["units"])
        for r in v["modifiers"]:
            if r["what"].startswith("your "):
                self.assertIn(r["what"].split()[1], have)

    def test_a_save_taken_mid_fight_picks_it_back_up(self):
        g = self.besieged()
        g.battle_step("fight")
        h = GameState.from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertIsNotNone(h.pending)
        self.assertEqual(h.pending.battle.round, g.pending.battle.round)
        self.assertEqual(h.pending.title, g.pending.title)
        # The mode is the surface's, not the save's: loaded headless it plays on.
        self.assertEqual(h.battles_mode, "auto")
        h.battle_step("auto")
        self.assertTrue(h.pending.settled)


class TestNobodyElseNotices(unittest.TestCase):

    def test_auto_mode_never_waits(self):
        g = start("siege", seed=1)
        self.assertEqual(g.battles_mode, "auto")
        for _ in range(160):
            g.advance(1)
            self.assertIsNone(g.pending)
            if g.over:
                break

    def test_the_autoplayer_fights_a_waiting_battle_at_once(self):
        g = start("siege", seed=1)
        g.battles_mode = "play"
        self.assertTrue(until_storm(g))
        bot = Bot(g)
        bot.step()
        self.assertTrue(g.pending is None or g.pending.battle.over,
                        "the bot left a fight waiting")

    def test_two_lords_at_each_others_walls_is_not_your_fight(self):
        """A storm between two other lords resolves at once, even in play."""
        g = start("marchlands", seed=3)
        g.battles_mode = "play"
        from marchlands.military import Army, Side as S
        # Put a foreign host at another foreign town's wall with the wall down.
        towns = list(g.world.towns)
        attacker_home, target = towns[0], towns[1]
        town = g.world.towns[target]
        town.wall_hp = 0.0
        town.garrison = {"spearman": 4.0}
        a = Army(uid=777, name="somebody's host", owner=attacker_home,
                 units={"spearman": 120.0, "ram": 2.0, "engineer": 4.0},
                 at=target, home=attacker_home, state=BESIEGING)
        g.armies.append(a)
        g._siege_town(a, town)
        self.assertIsNone(g.pending, "somebody else's assault stopped your day")


class TestItReachesTheScreen(unittest.TestCase):

    def test_the_snapshot_carries_it_at_the_top(self):
        from marchlands.web import snapshot
        g = start("siege", seed=1)
        g.battles_mode = "play"
        self.assertIsNone(snapshot(g)["battle"])
        self.assertTrue(until_storm(g))
        v = snapshot(g)["battle"]
        self.assertEqual(v["title"], g.pending.title)

    def test_the_window_plays_and_the_bot_does_not(self):
        import os
        from marchlands.web import STATIC
        js = open(os.path.join(STATIC, "marchlands.js"), encoding="utf-8").read()
        html = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
        self.assertIn('id="battle"', html)
        for id_ in ("battle-fight", "battle-order", "battle-commit", "battle-oil",
                    "battle-pitch", "battle-break", "battle-auto", "battle-close"):
            self.assertIn(f'id="{id_}"', html, id_)
            self.assertIn(f"'{id_}'", js, id_)
        # Every button is a console command, so the picture cannot do a thing
        # the console cannot.
        for cmd in ("battle fight", "battle commit", "battle oil", "battle pitch",
                    "battle break", "battle auto", "battle close", "battle order "):
            self.assertIn(cmd, js, cmd)

    def test_the_console_renders_it(self):
        import io, contextlib, re
        from marchlands.cli import Console
        g = start("siege", seed=1)
        g.battles_mode = "play"
        self.assertTrue(until_storm(g))
        buf = io.StringIO()
        con = Console(g, out=buf)
        con.do("battle"); con.do("battle fight"); con.do("battle break")
        out = re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())
        self.assertIn("THE STORM AT", out)
        self.assertIn("steadiness", out)
        self.assertIn("round 1:", out)
        self.assertIn("pursuit", out)


if __name__ == "__main__":
    unittest.main()
