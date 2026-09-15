"""The parts taken from the two parents: what each one actually does here.

Named for the two halves rather than the five features, because that is how
they earn their place -- Age of Empires put the contest on the map and made
the economy the target; Stronghold made the town's mood a coverage problem and
the lord a man who can die.
"""

import io
import json
import random
import unittest

from marchlands import config as C
from marchlands import lord as lordly
from marchlands.cli import Console
from marchlands.lord import Lord
from marchlands.military import Army, Side, raid_day
from marchlands.scenarios import start
from marchlands.settlement import BuildingInstance
from marchlands.sim import Bot


def game(seed=5, scenario="marchlands"):
    return start(scenario, seed=seed)


def stand(s, key, n=1):
    for i in range(n):
        s.buildings.append(BuildingInstance(uid=9000 + len(s.buildings),
                                            key=key, days_left=0))


# ----------------------------------------------------------- Stronghold: mood
class TestCoverage(unittest.TestCase):
    """Ale and a service reach so many souls, and a town outgrows them."""

    def test_an_inn_serves_a_number_of_people_not_a_town(self):
        g = game()
        s = g.world.settlements["aldworth"]
        stand(s, "inn")
        s.population = 100.0
        self.assertAlmostEqual(s.coverage("ale_reach"), 1.0)
        s.population = 400.0
        self.assertAlmostEqual(s.coverage("ale_reach"), 0.5)

    def test_growth_is_what_takes_the_ale_away(self):
        g = game()
        s = g.world.settlements["aldworth"]
        stand(s, "inn")
        for b in s.buildings:
            if b.key == "inn":
                b.throughput = 1.0       # the ale did arrive
        s.population = 150.0
        before = dict(s.mood_factors())["ale"]
        s.population = 600.0
        after = dict(s.mood_factors()).get("ale", 0.0)
        self.assertGreater(before, after)
        self.assertGreater(before, 8.0)

    def test_a_dry_inn_serves_nobody(self):
        g = game()
        s = g.world.settlements["aldworth"]
        stand(s, "inn")
        s.population = 100.0
        for b in s.buildings:
            if b.key == "inn":
                b.throughput = 0.0
        self.assertEqual(s.coverage("ale_reach", needs_running=True), 0.0)
        self.assertAlmostEqual(s.coverage("ale_reach"), 1.0)

    def test_a_second_house_reaches_further(self):
        g = game()
        s = g.world.settlements["aldworth"]
        s.population = 500.0
        stand(s, "chapel")
        one = s.coverage("faith_reach")
        stand(s, "chapel")
        self.assertGreater(s.coverage("faith_reach"), one)

    def test_coverage_never_runs_past_the_whole_town(self):
        g = game()
        s = g.world.settlements["aldworth"]
        s.population = 20.0
        stand(s, "chapel", 4)
        self.assertEqual(s.coverage("faith_reach"), 1.0)


# ------------------------------------------------- Age of Empires: the labour
class TestHands(unittest.TestCase):
    """More jobs than people, and a queue you get to order."""

    def _short_handed(self):
        g = game()
        s = g.world.settlements["aldworth"]
        stand(s, "inn")
        stand(s, "bakery")
        s.population = 30.0            # far fewer hands than jobs
        return g, s

    def test_the_back_of_the_queue_gets_nothing(self):
        g, s = self._short_handed()
        g.tick()
        last = [b for b in s.buildings if b.key == "inn"][0]
        self.assertEqual(last.staffed, 0)
        self.assertEqual(last.idle_reason, "short of hands")

    def test_asking_for_it_first_moves_the_hands(self):
        g, s = self._short_handed()
        s.set_band("inn", "first")
        g.tick()
        self.assertEqual([b for b in s.buildings if b.key == "inn"][0].staffed, 1)

    def test_sending_it_to_the_back_takes_them_away(self):
        g = game()
        s = g.world.settlements["aldworth"]
        stand(s, "poleturner", 12)           # far more jobs than there are hands
        s.population = 40.0
        g.tick()
        worked = sum(b.staffed for b in s.buildings if b.key == "farm")
        self.assertGreater(worked, 0)
        s.set_band("farm", "last")
        g.tick()
        self.assertLess(sum(b.staffed for b in s.buildings if b.key == "farm"),
                        worked)

    def test_a_standing_that_does_not_exist_is_refused(self):
        s = game().world.settlements["aldworth"]
        self.assertIn("no such standing", s.set_band("farm", "immediately"))

    def test_normal_is_stored_as_nothing_at_all(self):
        s = game().world.settlements["aldworth"]
        s.set_band("farm", "first")
        s.set_band("farm", "normal")
        self.assertEqual(s.priority, {})

    def test_the_queue_survives_a_save(self):
        g = game()
        g.world.settlements["aldworth"].set_band("bakery", "early")
        back = type(g).from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual(back.world.settlements["aldworth"].band("bakery"), 1)


# --------------------------------------------- Age of Empires: hurt the fields
class TestRaiding(unittest.TestCase):
    def test_riders_burn_more_country_than_footmen(self):
        foot = raid_day(Side({"man_at_arms": 60}), Side({}),
                        out_of_doors=300.0, rng=random.Random(1))[0]
        horse = raid_day(Side({"knight": 60}), Side({}),
                         out_of_doors=300.0, rng=random.Random(1))[0]
        self.assertGreater(horse, foot)

    def test_a_big_country_takes_longer_to_ruin(self):
        small = raid_day(Side({"knight": 30}), Side({}),
                         out_of_doors=200.0, rng=random.Random(1))[0]
        large = raid_day(Side({"knight": 30}), Side({}),
                         out_of_doors=900.0, rng=random.Random(1))[0]
        self.assertGreater(small, large)

    def test_a_stronger_garrison_comes_out_and_makes_them_pay(self):
        raiders = Side({"knight": 20})
        _w, _h, lost, lines = raid_day(raiders, Side({"man_at_arms": 200}),
                                       out_of_doors=300.0, rng=random.Random(3))
        self.assertTrue(lost)
        self.assertIn("comes out", " ".join(lines))

    def test_a_weaker_garrison_stays_behind_its_wall(self):
        _w, _h, lost, _l = raid_day(Side({"knight": 200}), Side({"spearman": 10}),
                                    out_of_doors=300.0, rng=random.Random(3))
        self.assertFalse(lost)

    def test_burning_a_rival_costs_him_the_thing_that_matters(self):
        g = game(seed=4)
        t = g.world.towns["dunmere"]
        before = t.prosperity
        g.armies.append(Army(uid=90, name="Riders", owner="player",
                             units={"knight": 60}, at="dunmere", home="aldworth",
                             state="raiding"))
        for _ in range(6):
            g.tick()
        self.assertLess(t.prosperity, before)

    def test_a_raid_brings_coin_home(self):
        g = game(seed=4)
        before = g.treasury
        g.armies.append(Army(uid=91, name="Riders", owner="player",
                             units={"knight": 60}, at="dunmere", home="aldworth",
                             state="raiding"))
        for _ in range(6):
            g.tick()
        self.assertGreater(g.ledger.plunder, 0.0)
        self.assertGreater(g.treasury, before - 5000)

    def test_being_raided_stops_the_fields_being_worked(self):
        g = game()
        s = g.world.settlements["aldworth"]
        quiet = s.productivity()
        s.raid_pressure = 1.0
        self.assertLess(s.productivity(), quiet * 0.5)

    def test_a_host_that_cannot_carry_a_wall_burns_the_country_instead(self):
        g = game()
        s = g.world.settlements["aldworth"]
        s.units = {"spearman": 200, "archer": 100}
        a = Army(uid=92, name="Weak host", owner="dunmere",
                 units={"militia": 20}, at="aldworth", home="dunmere")
        g.armies.append(a)
        g._arrive(a)
        self.assertEqual(a.state, "raiding")

    def test_raiders_go_home_when_there_is_nothing_left(self):
        g = game(seed=4)
        a = Army(uid=93, name="Riders", owner="player", units={"knight": 40},
                 at="dunmere", home="aldworth", state="raiding")
        g.armies.append(a)
        for _ in range(g.RAID_PATIENCE + 2):
            g.tick()
        self.assertNotEqual(a.state, "raiding")

    def test_you_cannot_raid_your_own_country(self):
        g = game()
        g.armies.append(Army(uid=94, name="Host", owner="player",
                             units={"knight": 10}, at="aldworth", home="aldworth"))
        self.assertIn("nothing to burn", g.raid(94))


# ----------------------------------------------- Age of Empires: on the map
class TestRelics(unittest.TestCase):
    def test_every_scenario_puts_the_shrines_out(self):
        for key in ("marchlands", "salt_road", "iron_marches", "winter_crown"):
            g = start(key, seed=3)
            self.assertEqual(len(g.world.shrines), 5, key)
            for sk in g.world.shrines:
                self.assertIn(sk, g.world.coords, key)

    def test_they_are_nowhere_near_your_walls(self):
        g = game()
        home = next(iter(g.world.settlements))
        for key in g.world.shrines:
            self.assertGreater(g.world.distance(home, key), 25.0)

    def test_a_host_can_actually_be_sent_to_one_by_name(self):
        """The shrines are no use if `march` cannot find them."""
        g = game(seed=4)
        out = io.StringIO()
        c = Console(g, out=out)
        g.armies.append(Army(uid=90, name="Pilgrims", owner="player",
                             units={"knight": 20}, at="aldworth", home="aldworth"))
        c.do("march 90 st_ceol")
        c.do("march 90 holy thorn")
        self.assertNotIn("no place matches", out.getvalue())
        self.assertIn("Holy Thorn", out.getvalue())

    def test_a_cart_is_not_offered_a_shrine_to_trade_at(self):
        g = game()
        self.assertNotIn("st_ceol", g.world.all_nodes())
        self.assertIn("st_ceol", g.world.march_nodes())

    def test_standing_there_long_enough_lifts_it(self):
        g = game(seed=4)
        g.armies.append(Army(uid=90, name="Pilgrims", owner="player",
                             units={"knight": 20}, at="aldworth", home="aldworth"))
        g.march(90, "st_ceol")
        for _ in range(20):
            g.tick()
            if g.relics_held():
                break
        self.assertEqual(g.relics_held(), 1)

    def test_a_day_at_the_shrine_is_not_enough(self):
        g = game(seed=4)
        a = Army(uid=90, name="Pilgrims", owner="player", units={"knight": 20},
                 at="st_ceol", home="aldworth")
        g.armies.append(a)
        g.tick()
        self.assertEqual(g.relics_held(), 0)

    def test_a_contested_shrine_is_settled_the_usual_way(self):
        """Two parties, one set of bones: somebody is driven off first."""
        g = game(seed=4)
        g.armies.append(Army(uid=90, name="Yours", owner="player",
                             units={"knight": 60}, at="st_ceol", home="aldworth"))
        g.armies.append(Army(uid=91, name="Theirs", owner="dunmere",
                             units={"militia": 8}, at="st_ceol", home="dunmere"))
        fought = False
        for _ in range(C.RELIC_DAYS * 2 + 4):
            msgs = g.tick()
            fought = fought or any("come to blows" in m for m in msgs)
            if g.world.shrines["st_ceol"].taken:
                break
        self.assertTrue(fought, "they stood there and nothing happened")
        self.assertTrue(g.world.shrines["st_ceol"].taken)

    def test_nobody_is_sent_where_men_are_already_standing(self):
        g = game(seed=4)
        g.armies.append(Army(uid=90, name="Yours", owner="player",
                             units={"knight": 20}, at="st_ceol", home="aldworth"))
        for t in g.world.towns.values():
            t.ambition = 40.0
        sent = []
        for _ in range(200):
            sent += [m for m in g.tick() if "sends men to" in m]
        self.assertNotIn("St Ceolwulf", " ".join(sent))

    def test_they_pay_and_a_cathedral_pays_better(self):
        g = game()
        self.assertEqual(g.relic_income(), 0.0)
        g.world.shrines["st_ceol"].holder = "player"
        bare = g.relic_income()
        self.assertAlmostEqual(bare, C.RELIC_COIN)
        stand(g.world.settlements["aldworth"], "cathedral")
        self.assertGreater(g.relic_income(), bare)

    def test_taking_a_lord_s_town_takes_his_bones_with_it(self):
        g = game()
        g.world.shrines["st_ceol"].holder = "dunmere"
        town = g.world.towns["dunmere"]
        g._take_town(town, Army(uid=9, name="Host", owner="player",
                                units={"man_at_arms": 40}, at="dunmere",
                                home="aldworth"))
        self.assertEqual(g.world.shrines["st_ceol"].holder, "player")

    def test_holding_them_long_enough_wins_the_march(self):
        g = game()
        for i, sh in enumerate(g.world.shrines.values()):
            if i < g.goals.relics:
                sh.holder = "player"
        for _ in range(g.goals.relic_days + 2):
            g.tick()
            if g.over:
                break
        self.assertIn("Reliquary", g.over)

    def test_losing_one_puts_the_count_back(self):
        g = game()
        for sh in g.world.shrines.values():
            sh.holder = "player"
        g.tick()
        g.tick()
        self.assertGreater(g.relic_days, 0)
        for sh in g.world.shrines.values():
            sh.holder = "dunmere"
        g.tick()
        self.assertEqual(g.relic_days, 0)

    def test_a_pilgrimage_is_not_a_lord_s_host(self):
        """It must not gate his wars: that made relic tuning retune the map.

        A party of spearmen away at a shrine used to count as "his host is
        already out", so how often the lords went relic-hunting quietly set how
        often they declared on anybody.
        """
        g = game(seed=4)
        for t in g.world.towns.values():
            t.ambition = 45.0
        party = None
        for _ in range(400):
            g.tick()
            party = next((a for a in g.armies if a.errand == "pilgrimage"), None)
            if party:
                break
        self.assertIsNotNone(party, "no lord ever went for a relic")
        self.assertEqual(party.errand, "pilgrimage")
        # Their own lord is still free to make war while they are away.
        town = g.world.towns[party.owner]
        town.hostility = C.HOSTILITY_WAR
        out = []
        for _ in range(6):
            out += g.tick()
            if any(a.owner == party.owner and not a.errand for a in g.armies):
                break
        self.assertTrue(any(a.owner == party.owner and not a.errand
                            for a in g.armies),
                        "a lord with men at a shrine could not raise a host")

    def test_the_lords_go_for_them_too(self):
        g = game(seed=3)
        Bot(g).run(900)
        taken = [sh for sh in g.world.shrines.values() if sh.taken]
        self.assertTrue(taken, "nobody ever went for the relics")

    def test_shrines_survive_a_save(self):
        g = game()
        g.world.shrines["st_ceol"].holder = "player"
        back = type(g).from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual(back.world.shrines["st_ceol"].holder, "player")
        self.assertEqual(back.relics_held(), 1)


# --------------------------------------------------- Stronghold: the lord
class TestLord(unittest.TestCase):
    def test_every_game_has_its_own_lord_in_his_own_hall(self):
        a, b = game(seed=3), game(seed=11)
        self.assertTrue(a.lord.name and b.lord.name)
        self.assertNotEqual(a.lord.name, b.lord.name)
        self.assertIn(a.lord.seat, a.world.settlements)

    def test_he_is_worth_something_in_residence(self):
        g = game()
        g.tick()
        s = g.world.settlements[g.lord.seat]
        self.assertIn("the lord in his hall", dict(s.mood_factors()))

    def test_riding_out_takes_that_away(self):
        g = game()
        g.armies.append(Army(uid=90, name="Host", owner="player",
                             units={"knight": 20}, at="aldworth", home="aldworth"))
        g.lead(90)
        g.tick()
        s = g.world.settlements[g.lord.seat]
        self.assertNotIn("the lord in his hall", dict(s.mood_factors()))

    def test_a_host_he_rides_with_hits_harder(self):
        g = game()
        self.assertEqual(lordly.attack_bonus(g.lord, 7), 1.0)
        g.lord.riding = 7
        self.assertGreater(lordly.attack_bonus(g.lord, 7), 1.0)
        self.assertEqual(lordly.attack_bonus(g.lord, 8), 1.0)

    def test_he_can_fall_and_the_line_goes_on(self):
        lord = Lord(name="Osric the Grim", heirs=2)
        msgs = lord.falls(random.Random(0), "Edric the Red")
        self.assertTrue(msgs)
        if not lord.alive:
            self.assertEqual(lord.name, "Edric the Red")
            self.assertGreater(lord.heir_days, 0)

    def test_an_heir_is_raised_in_time(self):
        lord = Lord(alive=False, heirs=1, heir_days=2)
        self.assertEqual(lord.day(), [])
        out = lord.day()
        self.assertTrue(lord.alive)
        self.assertTrue(out)
        self.assertEqual(lord.heirs, 0)

    def test_the_last_of_a_line_is_the_last(self):
        lord = Lord(heirs=0)
        rng = random.Random()
        for _ in range(60):
            lord.alive = True
            lord.falls(rng, "nobody")
            if not lord.alive:
                break
        self.assertFalse(lord.alive)
        self.assertEqual(lord.day(), [])      # nobody left to raise

    def test_a_captured_lord_can_be_bought_back(self):
        g = game()
        g.lord.captured = True
        g.lord.ransom = 500.0
        g.treasury = 100.0
        self.assertIn("you have", g.ransom_lord())
        g.treasury = 5000.0
        self.assertIn("bought back", g.ransom_lord())
        self.assertFalse(g.lord.captured)

    def test_a_lord_who_is_gone_cannot_be_sent_anywhere(self):
        g = game()
        g.lord.captured = True
        self.assertIn("ransom", g.lead(1))

    def test_he_survives_a_save(self):
        g = game()
        g.lord.riding = 4
        g.lord.heirs = 1
        back = type(g).from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual(back.lord.name, g.lord.name)
        self.assertEqual(back.lord.riding, 4)
        self.assertEqual(back.lord.heirs, 1)


class TestConsole(unittest.TestCase):
    def speak(self, *cmds, seed=5):
        g = game(seed=seed)
        out = io.StringIO()
        c = Console(g, out=out)
        for cmd in cmds:
            c.do(cmd)
        return g, out.getvalue()

    def test_the_hands_command_shows_the_shortage(self):
        _g, text = self.speak("work")
        self.assertIn("hands for", text)

    def test_the_hands_command_sets_a_standing(self):
        g, text = self.speak("work bakery first")
        self.assertEqual(g.world.settlements["aldworth"].band("bakery"), 2)

    def test_the_relics_command_lists_every_shrine(self):
        g, text = self.speak("relics")
        for sh in g.world.shrines.values():
            self.assertIn(sh.name, text)

    def test_the_lord_command_names_him(self):
        g, text = self.speak("lord")
        self.assertIn(g.lord.name.upper(), text)

    def test_none_of_them_emit_escapes_when_piped(self):
        _g, text = self.speak("work", "relics", "lord", "raid 1", "work farm last")
        self.assertNotIn("\033", text)


if __name__ == "__main__":
    unittest.main()
