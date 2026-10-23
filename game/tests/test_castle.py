"""The castle as a place: works, plans, and the counters between them."""

import io
import json
import random
import unittest

from marchlands.castle import (BATTER, BREACH, CROSS_DAYS, ESCALADE, INVEST,
                               PLANS, SAP, SAP_DAYS, SiegeState, Works,
                               approach, choose, storms_now)
from marchlands.cli import Console
from marchlands.military import Army, Side, siege_day
from marchlands.scenarios import start
from marchlands.settlement import BuildingInstance


def rng():
    return random.Random(1234)


def works_free():
    return Works()


def dig(s, *keys):
    """Stand the named works up in a settlement, complete, without paying."""
    uid = 9000
    for k in keys:
        s.buildings.append(BuildingInstance(uid=uid, key=k, days_left=0))
        uid += 1


class TestPlans(unittest.TestCase):
    def test_a_plan_that_needs_engines_is_refused_without_them(self):
        ok, why = PLANS[BREACH].viable(siege_power=10, engineers=0)
        self.assertFalse(ok)
        self.assertIn("engine power", why)

    def test_ladders_need_nothing_at_all(self):
        ok, _ = PLANS[ESCALADE].viable(siege_power=0, engineers=0)
        self.assertTrue(ok)

    def test_a_mine_needs_somebody_who_can_dig(self):
        self.assertFalse(PLANS[SAP].viable(siege_power=999, engineers=0)[0])
        self.assertTrue(PLANS[SAP].viable(siege_power=0, engineers=3)[0])

    def test_every_plan_has_something_that_answers_it(self):
        full = Works(moat=1, pitch=1, pits=1, oil=1, towers=2, gate=True, stone=True)
        for key in PLANS:
            self.assertTrue(full.answers(key), f"nothing answers {key}")


class TestMoat(unittest.TestCase):
    def test_water_stops_a_mine_outright(self):
        st = SiegeState(plan=SAP)
        for _ in range(SAP_DAYS + 4):
            ap = approach(SAP, Works(moat=1), st, siege_power=0, engineers=4,
                          wall=500, wall_max=500, have_pitch=False, rng=rng())
        self.assertEqual(ap.wall_damage, 0.0)
        self.assertIn("water", " ".join(ap.lines))

    def test_without_water_the_mine_brings_a_wall_down(self):
        st = SiegeState(plan=SAP)
        damage = 0.0
        for _ in range(SAP_DAYS):
            ap = approach(SAP, Works(), st, siege_power=0, engineers=4,
                          wall=500, wall_max=500, have_pitch=False, rng=rng())
            damage += ap.wall_damage
        self.assertGreater(damage, 100.0)

    def test_a_moat_costs_a_host_days_before_it_can_come_to_grips(self):
        st = SiegeState(plan=BATTER)
        for day in range(CROSS_DAYS):
            ap = approach(BATTER, Works(moat=1), st, siege_power=90, engineers=0,
                          wall=500, wall_max=500, have_pitch=False, rng=rng())
            self.assertEqual(ap.wall_damage, 0.0, f"ram reached the gate on day {day}")
            self.assertIn("ditch", " ".join(ap.lines))
        after = approach(BATTER, Works(moat=1), st, siege_power=90, engineers=0,
                         wall=500, wall_max=500, have_pitch=False, rng=rng())
        self.assertGreater(after.wall_damage, 0.0)

    def test_engines_standing_off_do_not_care_about_the_ditch(self):
        st = SiegeState(plan=BREACH)
        ap = approach(BREACH, Works(moat=1), st, siege_power=90, engineers=0,
                      wall=500, wall_max=500, have_pitch=False, rng=rng())
        self.assertGreater(ap.wall_damage, 0.0)


class TestWorksInAction(unittest.TestCase):
    def test_pitch_is_fired_once_and_only_once(self):
        st = SiegeState(plan=ESCALADE)
        bursts = []
        for _ in range(4):
            ap = approach(ESCALADE, Works(pitch=1), st, siege_power=0, engineers=0,
                          wall=100, wall_max=500, have_pitch=True, rng=rng())
            bursts.append(ap.burst)
        self.assertGreater(bursts[0], 0.05)
        self.assertEqual([b for b in bursts[1:] if b > 0.05], [])

    def test_a_ditch_with_nothing_to_light_it_does_nothing(self):
        st = SiegeState(plan=ESCALADE)
        ap = approach(ESCALADE, Works(pitch=1), st, siege_power=0, engineers=0,
                      wall=100, wall_max=500, have_pitch=False, rng=rng())
        self.assertEqual(ap.burst, 0.0)

    def test_oil_punishes_the_gate_and_ignores_the_curtain(self):
        gate = approach(BATTER, Works(oil=1, gate=True), SiegeState(plan=BATTER),
                        siege_power=90, engineers=0, wall=500, wall_max=500,
                        have_pitch=False, rng=rng())
        curtain = approach(BREACH, Works(oil=1, gate=True), SiegeState(plan=BREACH),
                           siege_power=90, engineers=0, wall=500, wall_max=500,
                           have_pitch=False, rng=rng())
        self.assertGreater(gate.burst, 0.0)
        self.assertEqual(curtain.burst, 0.0)

    def test_ladders_are_worse_against_a_wall_that_is_still_standing(self):
        intact = approach(ESCALADE, Works(), SiegeState(plan=ESCALADE),
                          siege_power=0, engineers=0, wall=500, wall_max=500,
                          have_pitch=False, rng=rng())
        rubble = approach(ESCALADE, Works(), SiegeState(plan=ESCALADE),
                          siege_power=0, engineers=0, wall=40, wall_max=500,
                          have_pitch=False, rng=rng())
        self.assertGreater(intact.attacker_mult, rubble.attacker_mult)
        self.assertLess(intact.defender_mult, rubble.defender_mult)

    def test_towers_make_an_escalade_worse_again(self):
        bare = approach(ESCALADE, Works(), SiegeState(plan=ESCALADE),
                        siege_power=0, engineers=0, wall=500, wall_max=500,
                        have_pitch=False, rng=rng())
        towered = approach(ESCALADE, Works(towers=3), SiegeState(plan=ESCALADE),
                           siege_power=0, engineers=0, wall=500, wall_max=500,
                           have_pitch=False, rng=rng())
        self.assertGreater(towered.attacker_mult, bare.attacker_mult)

    def test_investing_cuts_the_roads_and_touches_nothing(self):
        ap = approach(INVEST, Works(), SiegeState(plan=INVEST), siege_power=200,
                      engineers=9, wall=500, wall_max=500, have_pitch=True, rng=rng())
        self.assertTrue(ap.blockade)
        self.assertEqual(ap.wall_damage, 0.0)


class TestStorming(unittest.TestCase):
    def test_a_breach_waits_for_the_stone(self):
        self.assertFalse(storms_now(BREACH, wall=200, defenders=0))
        self.assertTrue(storms_now(BREACH, wall=0, defenders=40))

    def test_ladders_go_over_an_empty_wall_walk(self):
        self.assertTrue(storms_now(ESCALADE, wall=500, defenders=0))
        self.assertFalse(storms_now(ESCALADE, wall=500, defenders=40))


class TestChoosing(unittest.TestCase):
    def test_no_captain_mines_into_a_flooded_ditch(self):
        plan = choose(Works(moat=1), siege_power=0, engineers=8, host=400,
                      garrison=200, wall=800, wall_max=800)
        self.assertNotEqual(plan, SAP)

    def test_a_host_with_no_engines_at_all_does_not_promise_a_breach(self):
        plan = choose(Works(stone=True), siege_power=0, engineers=0, host=300,
                      garrison=200, wall=800, wall_max=800)
        self.assertIn(plan, (ESCALADE, INVEST))

    def test_an_empty_wall_is_taken_with_ladders_not_engines(self):
        plan = choose(Works(), siege_power=120, engineers=4, host=300,
                      garrison=0, wall=600, wall_max=600)
        self.assertEqual(plan, ESCALADE)

    def test_a_patient_lord_starves_what_he_could_only_slowly_batter(self):
        """One ram against a manned wall: worth trying, unless you can wait."""
        args = dict(siege_power=26, engineers=0, host=200, garrison=200,
                    wall=900, wall_max=900)
        eager = choose(Works(stone=True, gate=False), patient=False, **args)
        patient = choose(Works(stone=True, gate=False), patient=True, **args)
        self.assertEqual(eager, BATTER)
        self.assertEqual(patient, INVEST)


class TestReadingACastle(unittest.TestCase):
    def test_works_are_read_off_what_is_standing(self):
        w = Works.of(["stone_wall", "wall_tower", "wall_tower", "moat", "gatehouse"])
        self.assertEqual((w.towers, w.moat, w.gate, w.stone), (2, 1, True, True))
        self.assertEqual(w.pitch, 0)

    def test_a_great_seat_has_a_better_castle_than_a_market_town(self):
        g = start("marchlands", seed=3)
        towns = g.world.towns
        great = max(towns.values(), key=lambda t: t.wall_base).works()
        small = min(towns.values(), key=lambda t: t.wall_base).works()
        self.assertGreater(great.towers, small.towers)
        self.assertTrue(great.moat and not small.moat)


class TestSiegeDay(unittest.TestCase):
    def _besiege(self, works, plan, units=None):
        host = Side(dict(units or {"man_at_arms": 120, "ram": 3}))
        town = Side({"archer": 60, "spearman": 60}, battlement=8.0)
        state = SiegeState(plan=plan)
        wall = 600.0
        for _ in range(6):
            wall, _la, _ld, _lines = siege_day(
                host, town, wall, random.Random(7), "the place", wall_max=600.0,
                works=works, state=state, have_pitch=True)
        return host.alive(), town.alive(), wall

    def test_works_make_a_siege_cost_the_besieger_more(self):
        bare, _, _ = self._besiege(Works(stone=True), BATTER)
        dug, _, _ = self._besiege(
            Works(stone=True, moat=1, pitch=1, pits=1, oil=1, gate=True), BATTER)
        self.assertLess(dug, bare, "a dug-in castle must cost the host more men")

    def test_a_plan_with_no_engines_leaves_the_wall_alone(self):
        _, _, wall = self._besiege(Works(stone=True), ESCALADE,
                                   units={"man_at_arms": 200})
        self.assertEqual(wall, 600.0)

    def test_the_old_path_still_works_without_a_plan(self):
        host = Side({"ram": 4})
        town = Side({"archer": 20})
        wall, _la, _ld, lines = siege_day(host, town, 500.0, random.Random(3),
                                          "the place", wall_max=500.0)
        self.assertLess(wall, 500.0)
        self.assertTrue(lines)


class TestInGame(unittest.TestCase):
    def test_a_siege_state_survives_a_save(self):
        a = Army(uid=3, name="Host", owner="player")
        a.siege = SiegeState(plan=SAP, days=4, sap_days=2, pitch_spent=True)
        back = Army.from_dict(json.loads(json.dumps(a.to_dict())))
        self.assertEqual(back.siege.plan, SAP)
        self.assertEqual(back.siege.sap_days, 2)
        self.assertTrue(back.siege.pitch_spent)

    def test_a_lord_who_cannot_break_the_wall_cuts_the_roads_instead(self):
        """No engines and a manned wall: the captain sits down, and it bites."""
        g = start("marchlands", seed=5)
        s = g.world.settlements["aldworth"]
        s.units = {"spearman": 120, "archer": 60}
        host = Army(uid=77, name="Besiegers", owner="dunmere",
                    units={"man_at_arms": 150}, at="aldworth", home="dunmere",
                    state="besieging")
        g.armies.append(host)
        for _ in range(12):
            g.tick()
            if s.blockaded:
                break
        self.assertEqual(host.siege.plan, INVEST)
        self.assertTrue(s.blockaded)
        self.assertIn("the roads are cut", [k for k, _ in s.mood_factors()])

    def test_a_blockade_is_felt_in_the_workshops(self):
        g = start("marchlands", seed=5)
        s = g.world.settlements["aldworth"]
        s.besieged = False
        free = s.productivity()
        s.blockaded = True
        self.assertLess(s.productivity(), free)


class TestConsole(unittest.TestCase):
    def run_lines(self, *cmds, seed=5):
        g = start("marchlands", seed=seed)
        out = io.StringIO()
        c = Console(g, out=out)
        for cmd in cmds:
            c.do(cmd)
        return g, out.getvalue()

    def test_plans_names_what_stands_against_each_way_in(self):
        g = start("marchlands", seed=5)
        g.world.towns["marchand"].observe(g.day)     # you have to look first
        out = io.StringIO()
        Console(g, out=out).do("plans marchand")
        text = out.getvalue()
        for plan in PLANS.values():
            self.assertIn(plan.name, text)
        self.assertIn("moat", text)

    def test_plans_for_your_own_holding_reads_your_own_works(self):
        g = start("marchlands", seed=5)
        dig(g.world.settlements["aldworth"], "moat", "kill_pit")
        out = io.StringIO()
        Console(g, out=out).do("plans aldworth")
        self.assertIn("moat", out.getvalue())
        self.assertIn("killing pit", out.getvalue())

    def test_a_host_cannot_be_ordered_to_do_what_it_cannot(self):
        g = start("marchlands", seed=5)
        g.armies.append(Army(uid=41, name="Host", owner="player",
                             units={"spearman": 40}, at="aldworth", home="aldworth"))
        out = io.StringIO()
        Console(g, out=out).do("siege 41 breach")
        self.assertIn("engine power", out.getvalue())
        self.assertEqual(g.army(41).siege.plan, BREACH)   # order refused, not applied

    def test_an_order_it_can_obey_sticks(self):
        g = start("marchlands", seed=5)
        g.armies.append(Army(uid=42, name="Host", owner="player",
                             units={"spearman": 40}, at="aldworth", home="aldworth"))
        out = io.StringIO()
        Console(g, out=out).do("siege 42 escalade")
        self.assertEqual(g.army(42).siege.plan, ESCALADE)
        self.assertIn("escalade", out.getvalue())

    def test_changing_the_plan_starts_the_work_again(self):
        g = start("marchlands", seed=5)
        a = Army(uid=43, name="Host", owner="player",
                 units={"engineer": 6}, at="aldworth", home="aldworth")
        a.siege = SiegeState(plan=SAP, sap_days=4)
        g.armies.append(a)
        out = io.StringIO()
        Console(g, out=out).do("siege 43 escalade")
        self.assertEqual(g.army(43).siege.sap_days, 0)

    def test_the_console_lists_standing_orders(self):
        g = start("marchlands", seed=5)
        g.armies.append(Army(uid=44, name="Host", owner="player",
                             units={"spearman": 9}, at="aldworth", home="aldworth"))
        out = io.StringIO()
        Console(g, out=out).do("siege")
        self.assertIn("Host", out.getvalue())


if __name__ == "__main__":
    unittest.main()
