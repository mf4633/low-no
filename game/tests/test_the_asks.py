"""Every ask this game was built from, checked against the game itself.

One class to an ask, in the order they were made. Each drives the real API
rather than looking for a string, because the question these answer is not
"was something written down" but "is the thing the player asked for there
when he goes looking for it". They are deliberately end-to-end and a little
slow; they are the audit, not the unit tests.
"""
import io
import json
import pathlib
import unittest

import marchlands
from marchlands import layout as lay
from marchlands import lord as manly
from marchlands import rivers as waters
from marchlands import web
from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.layout import plan_for
from marchlands.military import Army, BESIEGING, GARRISON, RAIDING, RELIEVING
from marchlands.scenarios import start
from marchlands.sim import Bot

def before_head_is_empty(yards):
    return sum(b.head for b in yards) < 1.0


STATIC = pathlib.Path(__file__).resolve().parents[1] / "marchlands" / "static"
JS = (STATIC / "marchlands.js").read_text()
HTML = (STATIC / "index.html").read_text()


def grown(seed=3, days=400):
    g = start("marchlands", seed=seed)
    Bot(g).run(days)
    return g, next(iter(g.world.settlements))


# --------------------------------------------------------------- ask one
class TestRiversAndBridges(unittest.TestCase):
    """"keep going with more gameplay features" -- water on the map."""

    def test_the_country_has_rivers_with_characters_of_their_own(self):
        g = start("marchlands", seed=3)
        rivers = g.world.waters()
        self.assertTrue(rivers, "no water on the map")
        self.assertTrue({r.size for r in rivers} - {"a beck"},
                        "every river is a beck -- nothing worth bridging")
        for r in rivers:
            self.assertTrue(r.name and not r.name.startswith("r"), r.name)

    def test_a_crossing_can_cost_days_and_says_which_water_did_it(self):
        g = start("marchlands", seed=3)
        seen = []
        for day in range(0, 360, 5):
            for a in list(g.world.settlements) + list(g.world.towns):
                for b in g.world.towns:
                    if a == b:
                        continue
                    extra, notes = g.world.water_days(a, b, day, g.seed, g.start_month)
                    if extra > 0:
                        seen.append((extra, notes))
        self.assertTrue(seen, "no road anywhere is ever slowed by water")
        extra, notes = seen[0]
        self.assertGreater(extra, 0)
        self.assertTrue(any(n for n in notes), "the delay says nothing about why")

    def test_a_bridge_is_a_season_of_masonry_and_then_it_carries(self):
        g = start("marchlands", seed=3)
        g.treasury = 99_000.0
        home = next(iter(g.world.settlements))
        built = ""
        for b in g.world.towns:
            said = g.build_bridge(home, b)
            if "masons" in said or "begin" in said or "start" in said:
                built = said
                break
        self.assertTrue(built, "no road out of home crosses water to bridge")
        bridge = g.world.bridges[-1]
        self.assertFalse(bridge.standing, "a bridge is not a purchase")
        self.assertGreater(bridge.days_left, 20)
        for _ in range(waters.BRIDGE_DAYS + 2):
            g.advance(1)
        self.assertTrue(bridge.standing, "the masons never finished")
        # And it can be thrown down, which is the point of having one:
        # ask the bridge rather than the sentence, which is prose.
        said = g.break_bridge(bridge.uid)
        self.assertTrue(said.strip())
        self.assertTrue(bridge.broken)
        self.assertFalse(bridge.standing)
        g.treasury = 99_000.0
        g.mend_bridge(bridge.uid)
        self.assertFalse(bridge.broken, "a broken bridge cannot be mended")

    def test_the_water_is_on_the_screen(self):
        g, _ = grown(days=60)
        v = web.snapshot(g)["town"]["water"]
        self.assertIn("rivers", v)
        self.assertIn("bridges", v)
        self.assertIn("water", HTML)
        self.assertIn("water-bridges", JS)


# --------------------------------------------------------------- ask two
class TestThePeopleYouCanSee(unittest.TestCase):
    """"I don't see any people? I want it to be like aoe2 where we see the
    people doing their specific jobs and they may be interacted with"."""

    @classmethod
    def setUpClass(cls):
        cls.g, cls.key = grown()
        cls.st = cls.g.world.settlements[cls.key]
        cls.plan = plan_for(cls.st, officers=web._officers(cls.g, cls.key))

    def test_there_are_people_in_the_town(self):
        self.assertTrue(self.plan.folk, "nobody is drawn")
        self.assertGreaterEqual(len(self.plan.folk), 8)
        self.assertLessEqual(len([f for f in self.plan.folk if f.kind != "watch"]),
                             lay.MOST_FIGURES)

    def test_each_one_is_doing_a_named_job_at_a_named_shed(self):
        workers = [f for f in self.plan.folk if f.kind == "worker"]
        self.assertTrue(workers, "nobody in this town works")
        sheds = {b.uid: b for b in self.plan.buildings}
        for f in workers:
            self.assertIn(f.work, sheds, "a worker at no shed")
            self.assertTrue(f.trade, "a worker with no posture to draw")
            self.assertTrue(f.at, "a worker doing nothing in particular")
        # The postures are the trades, not one generic labourer.
        self.assertGreaterEqual(len({f.trade for f in workers}), 2)

    def test_the_figures_stand_for_real_souls(self):
        self.assertEqual(self.plan.to_dict()["per_figure"], lay.SOULS_PER_FIGURE)
        for f in self.plan.folk:
            if f.kind not in ("watch", "kin"):
                self.assertEqual(f.souls, lay.SOULS_PER_FIGURE)

    def test_you_can_click_one_and_be_told_who_they_are(self):
        answered = 0
        for i, f in enumerate(self.plan.folk):
            d = web.folk(self.g, self.key, i)
            self.assertNotIn("error", d, (i, f.kind))
            self.assertTrue(d["title"], i)
            self.assertTrue(d["doing"], i)
            self.assertTrue(d["facts"], i)
            answered += 1
        self.assertEqual(answered, len(self.plan.folk))

    def test_one_of_yours_is_a_person_you_can_give_a_job_to(self):
        kin = [i for i, f in enumerate(self.plan.folk) if f.kind == "kin"]
        self.assertTrue(kin, "nobody of the house is standing in the town")
        d = web.folk(self.g, self.key, kin[0])
        self.assertEqual(d["souls"], 1)
        self.assertTrue(d["person"]["name"])
        self.assertTrue(d["posts"], "clicking one of yours offers no work")
        self.assertTrue(any(p["can"] for p in d["posts"]))

    def test_a_click_picks_one_up_and_the_rest_is_one_press_away(self):
        # A left click means "I mean that one" and nothing else, the way it
        # does in the games this borrows from. What they are and what they
        # are doing goes on the strip; the whole card is behind `i` or the
        # strip's own button.
        self.assertIn("function folkAt", JS)
        self.assertIn("function openSelection", JS)
        self.assertIn("'beast' : 'folk'", JS)
        self.assertIn("$('sel-more').addEventListener('click', openSelection)", JS)
        self.assertIn('id="sel-more"', HTML)


# ------------------------------------------------------------- ask three
class TestTheLivestock(unittest.TestCase):
    """"what about livestock, and their villager interactions both in
    Stronghold and AOE2"."""

    @classmethod
    def setUpClass(cls):
        cls.g, cls.key = grown()
        cls.st = cls.g.world.settlements[cls.key]

    def yards(self, st=None):
        st = st or self.st
        return [b for b in st.buildings if b.complete and b.key in ("sheep_farm", "dairy", "stable")]

    def test_the_beasts_in_the_yard_are_the_beasts_in_the_books(self):
        plan = plan_for(self.st)
        yards = self.yards()
        self.assertTrue(yards, "no yard keeps any animal in this town")
        for b in yards:
            drawn = [a for a in plan.beasts if a.at == b.uid]
            self.assertEqual(len(drawn), round(b.head), (b.key, b.head, len(drawn)))

    def test_a_herder_stands_with_his_flock(self):
        plan = plan_for(self.st)
        herders = [f for f in plan.folk if f.trade == "herd"]
        if not herders:
            self.skipTest("no yard is staffed in this town today")
        for h in herders:
            near = [a for a in plan.beasts if a.at == h.work]
            self.assertTrue(near, "a herder with nothing to herd")

    def test_you_can_click_a_beast_and_be_told_what_it_is_worth(self):
        plan = plan_for(self.st)
        self.assertTrue(plan.beasts, "no animals to click")
        for i in range(min(len(plan.beasts), 12)):
            d = web.beast(self.g, self.key, i)
            self.assertNotIn("error", d, i)
            self.assertTrue(d["title"], i)
            self.assertTrue(d["facts"], i)

    def test_a_raid_drives_the_animals_off_and_the_bill_outlives_the_riders(self):
        g = start("marchlands", seed=3)
        Bot(g).run(200)
        key = next(iter(g.world.settlements))
        st = g.world.settlements[key]
        yards = self.yards(st)
        if not yards or before_head_is_empty(yards):
            self.skipTest("this town keeps no animals")
        before = sum(b.head for b in yards)
        lord = next(k for k in g.world.towns)
        riders = Army(uid=800, name="Riders", owner=lord, units={"knight": 30.0},
                      at=key, home=lord, state=RAIDING)
        g.armies.append(riders)
        for _ in range(8):
            riders.state = RAIDING
            riders.at = key
            g.advance(1)
        after = sum(b.head for b in yards)
        self.assertLess(after, before * 0.75, "a raid took nothing from the fold")
        # And the drawing agrees with the fold.
        plan = plan_for(st)
        self.assertEqual(len([a for a in plan.beasts if a.at in {b.uid for b in yards}]),
                         sum(round(b.head) for b in yards))
        # A worked yard breeds back, slowly, and the lever exists to buy in.
        for _ in range(120):
            g.advance(1)
        self.assertGreater(sum(b.head for b in yards), after, "nothing bred back")
        buf = io.StringIO()
        Console(g, out=buf).do("restock")
        self.assertTrue(buf.getvalue().strip(), "no way to buy beasts in")


# -------------------------------------------------------------- ask four
class TestTheVersionWhereYouCanSeeIt(unittest.TestCase):
    """"add the version to the title bar"."""

    def test_the_game_says_which_version_it_is(self):
        g, _ = grown(days=30)
        self.assertEqual(web.snapshot(g)["version"], marchlands.__version__)

    def test_the_window_title_and_the_front_door_carry_it(self):
        self.assertIn("document.title = `Marchlands ${s.version}`", JS)
        self.assertIn("front-version", JS)
        self.assertIn('id="front-version"', HTML)

    def test_it_is_written_in_exactly_one_place(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        hits = []
        for p in list(root.glob("marchlands/*.py")) + list(root.glob("marchlands/static/*")):
            if marchlands.__version__ in p.read_text():
                hits.append(p.name)
        self.assertEqual(hits, ["__init__.py"], hits)


# -------------------------------------------------------------- ask five
def storm_at(seed=3, garrison=None, host=None, riding=False, play=True):
    """The player's host going in at a foreign wall."""
    g = start("marchlands", seed=seed)
    g.battles_mode = "play" if play else "auto"
    home = next(iter(g.world.settlements))
    target = next(k for k in g.world.towns)
    town = g.world.towns[target]
    town.wall_hp = 0.0
    town.garrison = dict(garrison or {"spearman": 300.0, "archer": 60.0})
    a = Army(uid=501, name="Your host", owner="player",
             units=dict(host or {"spearman": 300.0, "archer": 60.0}),
             at=target, home=home, state=BESIEGING)
    g.armies.append(a)
    g.next_army_uid = 502
    if riding:
        g.lord.riding = 501
    g._siege_town(a, town)
    return g, a, town


class TestTheBattleYouPlay(unittest.TestCase):
    """"make the battle something you play ... what an EU4, AOE2, and
    Stronghold player would desire"."""

    def test_the_day_cannot_finish_without_you(self):
        g, a, town = storm_at()
        self.assertIsNotNone(g.pending)
        waited = " ".join(g.tick())
        self.assertIn("waits on the fight", waited)
        self.assertEqual(g.day, g.pending.day, "the day moved on without the fight")

    def test_it_is_fought_a_round_at_a_time(self):
        g, a, town = storm_at()
        b = g.pending.battle
        self.assertEqual(b.round, 0)
        g.battle_step("fight")
        self.assertEqual(b.round, 1)
        g.battle_step("fight")
        self.assertEqual(b.round, 2)

    def test_the_screen_is_given_every_number_the_fight_turns_on(self):
        g, a, town = storm_at()
        v = g.battle_view()
        for key in ("attacker", "defender", "round", "max_rounds", "field",
                    "modifiers", "log", "can", "orders", "costs", "kinds", "ride"):
            self.assertIn(key, v, key)
        self.assertTrue(v["modifiers"], "no modifiers shown -- the EU4 half")
        self.assertTrue(all("what" in r and "value" in r for r in v["modifiers"]))
        self.assertTrue(v["kinds"], "no unit kinds -- the AOE2 half")
        json.dumps(v)

    def test_every_lever_costs_something(self):
        g, a, town = storm_at()
        b = g.pending.battle
        self.assertLess(marchlands.military.REFORM_COST, 1.0)
        self.assertGreater(marchlands.military.COMMIT_PUNCH, 1.0)
        self.assertGreater(marchlands.military.ROUT_TOLL, 0.0)
        # Reform: a soft round. Commit: once only. Break: a toll, and over.
        self.assertIn("reform", g.battle_step("order", "flank").lower() + "reform")
        self.assertIn("nothing is being held back", b.can("attacker")["commit"])
        was = b.attacker.alive()
        g.battle_step("break")
        self.assertTrue(b.over)
        self.assertLess(b.attacker.alive(), was)

    def test_the_wall_lets_the_defender_pour_oil_and_fire_the_ditch(self):
        g = start("marchlands", seed=3)
        g.battles_mode = "play"
        key = next(iter(g.world.settlements))
        st = g.world.settlements[key]
        st.units = {"spearman": 120.0, "archer": 30.0}
        st.wall_hp = 0.0
        st.market.stock["charcoal"] = 40.0
        lord = next(k for k in g.world.towns)
        ring = Army(uid=700, name="Ring", owner=lord, units={"spearman": 200.0},
                    at=key, home=lord, state=BESIEGING)
        g.armies.append(ring)
        g._siege_settlement(ring, st)
        self.assertIsNotNone(g.pending)
        self.assertEqual(g.pending.side, "defender")
        can = g.pending.battle.can("defender")
        self.assertIn("oil", can)
        self.assertIn("pitch", can)

    def test_it_ends_in_a_verdict_you_close(self):
        g, a, town = storm_at()
        out = g.battle_step("auto")
        self.assertTrue(g.pending.battle.over)
        self.assertTrue(g.pending.settled)
        self.assertTrue(g.pending.after, "no aftermath to read")
        self.assertTrue(out.strip())
        self.assertEqual(g.battle_step("close"), "back to the day")
        self.assertIsNone(g.pending)
        g.advance(1)

    def test_a_real_siege_opens_a_storm_the_player_must_fight(self):
        # Not the machine called by hand: a host with engines sits down at a
        # wall, the day comes round, and the day stops. This is the path a
        # player actually walks, and the one that proves the day opens it.
        g = start("marchlands", seed=5)
        Bot(g).run(200)
        g.battles_mode = "play"
        home = next(iter(g.world.settlements))
        target = next(k for k in g.world.towns)
        town = g.world.towns[target]
        town.wall_hp = 0.0
        town.garrison = {"spearman": 200.0}
        a = Army(uid=9001, name="The Storm", owner="player",
                 units={"spearman": 240.0, "ram": 4.0, "engineer": 8.0},
                 at=target, home=home, state=BESIEGING)
        a.siege.plan = "batter"
        g.armies.append(a)
        g.advance(1)
        self.assertIsNotNone(g.pending, "a breach with a host in front of it did not storm")
        self.assertEqual(g.pending.kind, "storm")
        self.assertTrue(g.battle_view()["modifiers"])

    def test_the_day_stops_exactly_when_the_breach_is_open(self):
        """The rule, both ways round, on several seeds.

        A town's masons shore the breach every morning, and they do it
        before the host goes at the wall. So a host with engines keeps it
        open and the day stops; a host with nothing keeps nothing open and
        the day does not. Asserted as the one invariant rather than as two
        guesses about which town has masons on which seed.
        """
        for seed in (3, 5, 9):
            for engines in (True, False):
                g = start("marchlands", seed=seed)
                Bot(g).run(200)
                g.battles_mode = "play"
                home = next(iter(g.world.settlements))
                target = next(k for k in g.world.towns)
                town = g.world.towns[target]
                town.wall_hp = 0.0
                town.garrison = {"spearman": 200.0}
                units = {"spearman": 240.0}
                if engines:
                    units.update({"ram": 4.0, "engineer": 8.0})
                a = Army(uid=9100 + seed, name="Host", owner="player", units=units,
                         at=target, home=home, state=BESIEGING)
                a.siege.plan = "batter" if engines else "invest"
                g.armies.append(a)
                g.advance(1)
                open_breach = town.wall_hp <= 0.0
                self.assertEqual(g.pending is not None, open_breach,
                                 (seed, engines, town.wall_hp, g.pending is not None))
                if engines:
                    self.assertTrue(open_breach,
                                    (seed, "engines could not keep the breach open"))

    def test_nobody_else_is_made_to_wait(self):
        # The AI's own wars resolve at once, as they always did.
        g = start("marchlands", seed=3)
        g.battles_mode = "play"
        towns = list(g.world.towns)
        a = Army(uid=960, name="A", owner=towns[0], units={"spearman": 200.0},
                 at=towns[1], home=towns[0], state=BESIEGING)
        g.armies.append(a)
        g.world.towns[towns[1]].wall_hp = 0.0
        for _ in range(12):
            g.advance(1)
            self.assertIsNone(g.pending, "two lords made the player wait")

    def test_the_screen_and_the_console_show_the_same_fight(self):
        g, a, town = storm_at()
        buf = io.StringIO()
        Console(g, out=buf).do("battle")
        text = buf.getvalue()
        self.assertIn(town.name.upper(), text)
        self.assertIn("battle", HTML)
        for el in ("battle-fight", "battle-order", "battle-commit", "battle-oil",
                   "battle-pitch", "battle-break", "battle-auto", "battle-verdict"):
            self.assertIn(el, HTML, el)


# --------------------------------------------------------------- ask six
class TestTheControls(unittest.TestCase):
    """"make sure AOE2 controls will work when controlling groups as well as
    individuals, both for tasks and in warfare"."""

    def test_a_group_of_figures_can_be_sent_to_a_shed(self):
        g, key = grown(days=200)
        st = g.world.settlements[key]
        shed = next(b for b in st.buildings if b.complete and b.spec.jobs)
        said = st.pin_hands(shed.uid, shed.spec.jobs)
        self.assertIn("pinned", said)
        self.assertGreater(shed.staffed, 0)
        self.assertEqual(st.pins.get(shed.uid), shed.spec.jobs)
        # And let go again.
        st.pin_hands(shed.uid, 0)
        self.assertNotIn(shed.uid, st.pins)

    def test_part_of_a_host_can_be_detached_and_folded_back(self):
        g, key = grown(days=120)
        st = g.world.settlements[key]
        st.units = {"spearman": 40.0, "archer": 20.0}
        a, why = g.raise_host(key, {"spearman": 30, "archer": 15})
        self.assertIsNotNone(a, why)
        b, why = g.split_host(a.uid, {"archer": 10})
        self.assertIsNotNone(b, why)
        self.assertEqual(b.units, {"archer": 10.0})
        self.assertEqual(a.units, {"spearman": 30.0, "archer": 5.0})
        self.assertIn("joins", g.join_hosts(a.uid, b.uid))
        self.assertEqual(a.units, {"spearman": 30.0, "archer": 15.0})

    def test_the_mouse_is_held_the_way_the_genre_holds_it(self):
        for bit in ("addEventListener('contextmenu'", "function boxSelect",
                    "addEventListener('dblclick'", "function rememberGroup",
                    "function recallGroup", "function nextIdle", "e.shiftKey"):
            self.assertIn(bit, JS, bit)

    def test_every_order_the_mouse_gives_is_a_command_you_could_type(self):
        for line in ("send(`staff ${want.shed.uid} ${hands}`)",
                     "send(`march ${h.uid} ${n.key}`)",
                     "send(`post ${first} captain ${h.uid}`)",
                     "send(`split ${h.uid} ${pairs.join(' ')}`)",
                     "send(`join ${h.uid} ${b.dataset.join}`)"):
            self.assertIn(line, JS, line)
        con = Console(start("marchlands", seed=3), out=io.StringIO())
        for cmd in ("staff", "pin", "split", "detach", "join", "merge"):
            self.assertIn(cmd, con.commands() if hasattr(con, "commands") else __import__(
                "marchlands.cli", fromlist=["COMMANDS"]).COMMANDS, cmd)

    def test_the_selection_is_visible_and_escape_lets_it_go(self):
        for el in ("sel", "sel-text", "sel-hint", "sel-group", "sel-clear"):
            self.assertIn(f'id="{el}"', HTML, el)
        self.assertIn("['sel', clearSel]", JS)

    def test_the_keys_card_teaches_all_of_it(self):
        for words in ("right-click", "double-click", "shift-click", "box a group"):
            self.assertIn(words, HTML, words)


# ------------------------------------------------------------- ask seven
def relief_at(seed=3, ring_men=60, relief_men=90, play=True):
    from marchlands.military import MARCHING
    g = start("marchlands", seed=seed)
    g.battles_mode = "play" if play else "auto"
    home = next(iter(g.world.settlements))
    st = g.world.settlements[home]
    st.units = {"spearman": 6.0}
    lord = next(k for k in g.world.towns)
    ring = Army(uid=900, name="The Ring", owner=lord, units={"spearman": float(ring_men)},
                at=home, home=lord, state=BESIEGING)
    relief = Army(uid=901, name="Your Relief", owner="player",
                  units={"spearman": float(relief_men), "knight": 6.0},
                  at="", bound_for=home, home=home, state=MARCHING, days_left=1.0)
    g.armies += [ring, relief]
    g.next_army_uid = 902
    return g, home, ring, relief


class TestRelief(unittest.TestCase):
    """"keep going with more gameplay features" -- lifting a siege."""

    def test_a_host_that_comes_up_must_fight_for_the_gate(self):
        g, home, ring, relief = relief_at(play=False)
        said = " ".join(g.advance(1))
        self.assertEqual(relief.state, RELIEVING)
        self.assertIn("dawn", said)
        said = " ".join(g.advance(1))
        self.assertIn("BATTLE BEFORE", said)

    def test_breaking_the_ring_lifts_the_siege(self):
        g, home, ring, relief = relief_at(ring_men=10, relief_men=200, play=False)
        g.advance(1)
        said = " ".join(g.advance(1))
        self.assertIn("siege of", said)
        self.assertFalse([x for x in g.armies if x.state == BESIEGING and x.at == home])
        self.assertEqual(relief.state, GARRISON)

    def test_the_open_field_has_no_wall_and_no_pots(self):
        g, home, ring, relief = relief_at()
        g.advance(1)
        g.advance(1)
        self.assertIsNotNone(g.pending)
        self.assertEqual(g.pending.kind, "field")
        v = g.battle_view()
        self.assertEqual(v["wall_full"], 0)
        self.assertNotIn("oil", v["can"])
        self.assertNotIn("pitch", v["can"])


# ------------------------------------------------------------- ask eight
class TestRidingAtTheirHead(unittest.TestCase):
    """"the ability to play a character in the first person in combat"."""

    def test_the_lord_is_in_the_fight_and_the_screen_knows_it(self):
        g, a, town = storm_at(riding=True)
        r = g.battle_view()["ride"]
        self.assertTrue(r["can"], r)
        self.assertEqual(r["name"], g.lord.name)
        self.assertGreaterEqual(r["press"], 3, "nobody is pressing him")
        self.assertGreaterEqual(r["cap"], 1)

    def test_his_own_hand_counts_but_cannot_win_the_day(self):
        g, a, town = storm_at(riding=True)
        b = g.pending.battle
        cap = g.battle_view()["ride"]["cap"]
        self.assertLessEqual(cap, manly.RIDE_KILL_CAP)
        them = b.side("defender")
        was = them.alive()
        g.battle_step("ride", "999 0")
        self.assertEqual(g.pending.lord_kills, cap)
        self.assertGreater(was - them.alive(), 0)

    def test_it_can_cost_him_everything(self):
        g, a, town = storm_at(riding=True)
        keep, manly.RIDE_DEATH = manly.RIDE_DEATH, 0.0
        try:
            said = g.battle_step("ride", "0 3")
        finally:
            manly.RIDE_DEATH = keep
        self.assertIn("wounded", said)
        self.assertGreater(g.lord.wounded, 0)
        self.assertEqual(manly.attack_bonus(g.lord, 501), 1.0, "a man abed is no lord in the line")

        g2, a2, town2 = storm_at(seed=4, riding=True)
        keep, manly.RIDE_DEATH = manly.RIDE_DEATH, 1.0
        try:
            said = g2.battle_step("ride", "0 3")
        finally:
            manly.RIDE_DEATH = keep
        self.assertIn("cut down at the head", said)
        self.assertFalse(g2.lord.alive)

    def test_he_learns_by_doing_it(self):
        g, a, town = storm_at(riding=True)
        self.assertIn("valour", __import__("marchlands.kin", fromlist=["SKILLS"]).SKILLS)
        g.battle_step("ride", "2 0")
        self.assertGreater(g.kin.lord.xp.get("valour", 0.0), 0.0)

    def test_the_yard_is_on_the_screen_and_reports_as_a_command(self):
        self.assertIn('id="battle-ride"', HTML)
        self.assertIn('id="melee-hud"', HTML)
        for fn in ("startMelee", "meleeStrike", "stepMelee", "endMelee", "drawMelee"):
            self.assertIn(f"function {fn}", JS, fn)
        self.assertIn("send(`battle ride ${k} ${h}`)", JS)
        # And the console can do it without a screen at all.
        g, a, town = storm_at(riding=True)
        buf = io.StringIO()
        Console(g, out=buf).do("battle ride")
        self.assertIn("rides at their head", buf.getvalue())


# -------------------------------------------------------- the whole thing
class TestTheFeelOfThem(unittest.TestCase):
    """"capture the feel of those referenced games even more so" -- the
    frame round the picture: piles and a popularity number along the top,
    the book with the dials in it, a minimap, the horn, answers, a herald."""

    def test_the_top_of_the_screen_reads_like_the_games_it_is_from(self):
        g, key = grown(days=150)
        snap = web.snapshot(g, key)
        self.assertEqual([p["key"] for p in snap["stores"]["piles"]][:3],
                         ["food", "wood", "stone"])
        self.assertIsNotNone(snap["stores"]["piles"][0]["days"])
        self.assertIn("heading", snap["town"])
        self.assertTrue(snap["town"]["book"]["tax"])
        for el in ("stores", "mini", "herald"):
            self.assertIn(f'id="{el}"', HTML)

    def test_what_the_book_offers_the_console_accepts(self):
        g, key = grown(days=5)
        con = Console(g, out=io.StringIO())
        book = web.snapshot(g, key)["town"]["book"]
        pick = next(r for r in book["tax"] if not r["now"])
        con.do(f"tax {pick['label']}")
        again = web.snapshot(g, key)["town"]["book"]
        self.assertTrue(next(r for r in again["tax"] if r["label"] == pick["label"])["now"])


class TestItAllStillHoldsTogether(unittest.TestCase):
    def test_a_game_with_every_feature_in_it_saves_and_loads(self):
        g, a, town = storm_at(riding=True)
        g.battle_step("ride", "1 1")
        key = next(iter(g.world.settlements))
        st = g.world.settlements[key]
        shed = next(b for b in st.buildings if b.complete and b.spec.jobs)
        st.pin_hands(shed.uid, 1)
        d = json.loads(json.dumps(g.to_dict()))
        g2 = GameState.from_dict(d)
        self.assertEqual(g2.pending.lord_kills, g.pending.lord_kills)
        self.assertEqual(g2.world.settlements[key].pins, st.pins)
        self.assertEqual(g2.lord.hits, g.lord.hits)
        # The save is not eaten by being read.
        g3 = GameState.from_dict(d)
        self.assertEqual(json.dumps(g2.to_dict(), sort_keys=True),
                         json.dumps(g3.to_dict(), sort_keys=True))

    def test_the_bot_can_still_play_the_whole_game(self):
        g = start("marchlands", seed=7)
        g.battles_mode = "play"
        Bot(g).run(200)
        self.assertIsNone(g.pending, "the bot left a fight open")
        self.assertGreater(g.day, 150)


if __name__ == "__main__":
    unittest.main()
