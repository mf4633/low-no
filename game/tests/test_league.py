"""The march as a competition: a table, a schedule, and the parity machinery.

The march always had eight lords taking towns off each other. What it did not
have was a table, a published schedule, or anything that ever handed something
back to whoever was losing -- which is exactly the hole the fair-play pass
measured, and exactly what a league is designed to fill.
"""

import io
import unittest

from marchlands import league as lg
from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.league import League, PLAYER, Season
from marchlands.scenario import new_game
from marchlands.sim import Bot


def played(seed: int = 5, days: int = 760):
    g = new_game(seed=seed)
    bot = Bot(g)
    for _ in range(days):
        bot.step()
        g.tick()
        if g.over:
            break
    return g, bot


def on_the_clock(g, order=None):
    """Give the player a full intake and the first pick of it.

    The first tick already ran the draft, and the order is drawn for, so
    whatever is left after it is not a fixture a test can stand on.
    """
    se = g.league.season
    se.prospects = lg.draft_class(g.rng, se.year)
    se.order = list(order or [PLAYER])
    se.picking = 0
    return se


class TestTheTable(unittest.TestCase):
    def setUp(self):
        self.g, _ = played(days=420)

    def test_everybody_on_the_march_is_in_it(self):
        keys = set(self.g.league.season.records)
        self.assertIn(PLAYER, keys)
        for town in self.g.world.towns:
            self.assertIn(town, keys)

    def test_it_sorts_by_a_rule_anybody_can_check(self):
        table = self.g.league.season.table()
        ordered = [tuple(-getattr(r, k) for k in lg.STANDINGS_KEYS) for r in table]
        self.assertEqual(ordered, sorted(ordered))

    def test_the_tie_break_is_the_same_measure_for_everybody(self):
        """Worth put the player top of a column that meant nothing: a whole
        economy is richer than any lord on the march by an order of magnitude.
        What a lord could put in the field is comparable."""
        self.assertIn("muster", lg.STANDINGS_KEYS)
        self.assertNotIn("worth", lg.STANDINGS_KEYS)

    def test_a_field_carried_shows_up_in_the_record(self):
        se = self.g.league.season
        before = se.record("dunmere").won
        self.g.scored("dunmere", won=True)
        self.assertEqual(se.record("dunmere").won, before + 1)

    def test_a_town_taken_shows_up_on_both_sides_of_it(self):
        se = self.g.league.season
        took = se.record("bruille").taken
        gave = se.record("dunmere").given
        self.g.took_town("bruille", "dunmere")
        self.assertEqual(se.record("bruille").taken, took + 1)
        self.assertEqual(se.record("dunmere").given, gave + 1)

    def test_your_place_is_a_number_between_one_and_the_field(self):
        se = self.g.league.season
        where = se.place(PLAYER)
        self.assertGreaterEqual(where, 1)
        self.assertLessEqual(where, len(se.records))


class TestTheSchedule(unittest.TestCase):
    """The difference between a war and an ambush is a fortnight's notice."""

    def setUp(self):
        self.g, _ = played(days=400)

    def test_the_lords_say_where_they_are_going(self):
        self.assertTrue(self.g.league.season.fixtures)

    def test_and_mostly_at_each_other(self):
        """Reading a flat nought as 'hostility is at least ambition' put every
        lord down as marching on your gate in the first spring, which is a
        schedule that tells you nothing."""
        g = new_game(seed=5)
        g.tick()
        at_me = [f for f in g.league.season.fixtures
                 if f.target in g.world.settlements]
        self.assertLess(len(at_me), len(g.league.season.fixtures))

    def test_a_lord_you_have_bought_off_says_nothing(self):
        g = new_game(seed=5)
        for t in g.world.towns.values():
            t.truce_days = 200
        g.league.season = Season()
        g.tick()
        self.assertEqual(g.league.season.fixtures, [])

    def test_what_is_coming_at_you_can_be_asked_for_by_name(self):
        se = self.g.league.season
        se.fixtures.append(lg.Fixture(who="dunmere", target="aldworth"))
        self.assertTrue(se.coming_for("aldworth"))

    def test_it_reaches_the_hints_loudly(self):
        se = self.g.league.season
        se.fixtures.insert(0, lg.Fixture(who="dunmere", target="aldworth"))
        hints = " ".join(Console(self.g, out=io.StringIO()).hints())
        self.assertIn("mean to move on", hints)


class TestTheDraft(unittest.TestCase):
    """The most effective parity device anybody has designed: finish last and
    you choose first."""

    def setUp(self):
        self.g, _ = played(days=400)

    def test_a_class_arrives_every_spring(self):
        se = self.g.league.season
        self.assertEqual(len(se.prospects), len(lg.DRAFT_GRADES))
        for p in se.prospects:
            self.assertIn(p.skill, lg.DRAFT_SKILLS)
            self.assertTrue(p.story)

    def test_the_order_is_last_year_reversed(self):
        g = self.g
        old = g.league.season
        table = old.table()
        g._open_season(old.year + 1)
        self.assertEqual(g.league.season.order,
                         [r.key for r in reversed(table)])

    def test_the_first_spring_is_drawn_for_rather_than_given_to_you(self):
        """Handing the player first pick of the first class would be a head
        start the whole device exists to prevent."""
        firsts = set()
        for seed in (3, 5, 7, 11, 17, 23):
            g = new_game(seed=seed)
            g.tick()
            firsts.add(g.league.season.order[0])
        self.assertGreater(len(firsts), 1)

    def test_nobody_gets_a_man_twice(self):
        se = self.g.league.season
        taken = [p.taken_by for p in se.prospects if p.taken_by]
        self.assertEqual(len(taken), len(set(taken)))

    def test_a_drafted_man_arrives_knowing_his_trade(self):
        g = new_game(seed=5)
        g.tick()
        se = on_the_clock(g)
        pick = se.undrafted()[0]
        before = len(g.kin.living())
        said = g.draft(pick.name.split()[0])
        self.assertIn(pick.name, said)
        self.assertEqual(len(g.kin.living()), before + 1)
        man = g.kin.by_name(pick.name)
        self.assertEqual(man.level(pick.skill), pick.grade)

    def test_a_sworn_man_does_not_inherit_the_seat(self):
        """He took service. He is not of the blood, and a succession that
        handed the hall to a hired steward would be a different game."""
        g = new_game(seed=5)
        g.tick()
        se = on_the_clock(g)
        g.draft(se.undrafted()[0].name.split()[0])
        for p in list(g.kin.living()):
            if p.uid != g.kin.head and not p.sworn:
                p.alive = False
        heir = g.kin.heir(g.day)
        self.assertTrue(heir is None or not heir.sworn)

    def test_it_is_not_your_turn_until_it_is(self):
        g = new_game(seed=5)
        g.tick()
        se = on_the_clock(g, ["dunmere", PLAYER])
        said = g.draft(se.undrafted()[0].name.split()[0])
        self.assertIn("on the clock", said)

    def test_a_name_nobody_answers_to_is_said_plainly(self):
        g = new_game(seed=5)
        g.tick()
        on_the_clock(g)
        self.assertIn("nobody called", g.draft("Ethelred the Unready"))


class TestTheCap(unittest.TestCase):
    """Not a ceiling. A ceiling is a rule a player fights; a rising cost is a
    decision a player makes, and it still ends runaway musters."""

    def test_a_host_within_your_holdings_costs_what_it_says(self):
        self.assertEqual(lg.overage(10.0, 1), 1.0)
        self.assertEqual(lg.overage(lg.cap_for(1), 1), 1.0)

    def test_past_it_every_further_man_costs_more_than_the_last(self):
        cap = lg.cap_for(1)
        steps = [lg.overage(cap * f, 1) for f in (1.0, 1.5, 2.0, 3.0)]
        self.assertEqual(steps, sorted(steps))
        gaps = [b - a for a, b in zip(steps, steps[1:])]
        self.assertEqual(gaps, sorted(gaps), "the bite does not accelerate")

    def test_more_towns_keep_more_men(self):
        self.assertGreater(lg.cap_for(3), lg.cap_for(1))
        self.assertLess(lg.overage(200.0, 3), lg.overage(200.0, 1))

    def test_the_engine_charges_it(self):
        g, _ = played(days=300)
        self.assertAlmostEqual(g.muster_cost(), lg.overage(
            float(g.soldiers),
            len(g.world.settlements) + len(g.world.vassals())))

    def test_and_says_so_before_the_wage_bill_does(self):
        g, _ = played(days=300)
        s = g.home()
        s.units = {"spearman": 900.0}
        hints = " ".join(Console(g, out=io.StringIO()).hints())
        self.assertIn("times his wage", hints)


class TestTheSeasonTurns(unittest.TestCase):
    def test_a_finished_season_is_remembered(self):
        g, _ = played(days=760)
        self.assertTrue(g.league.past)
        row = g.league.past[0]
        self.assertIn("year", row)
        self.assertIn("first", row)
        self.assertTrue(row["table"])

    def test_the_year_it_closes_on_goes_in_the_chronicle(self):
        g, _ = played(days=400)
        text = " ".join(e.text for e in g.chronicle.entries)
        self.assertIn("season", text.lower())

    def test_a_record_stands_until_it_is_beaten(self):
        lge = League()
        self.assertFalse(lge.mark("fields", 3, "you", 1247))
        self.assertFalse(lge.mark("fields", 2, "them", 1248))
        self.assertTrue(lge.mark("fields", 9, "them", 1249))
        self.assertEqual(lge.bests["fields"][1], "them")

    def test_an_empty_season_is_not_a_record(self):
        g, _ = played(days=400)
        for value, _who, _year in g.league.bests.values():
            self.assertGreater(value, 0)


class TestTheLeagueRollsItsOwnDice(unittest.TestCase):
    """Who turned up looking for a lord this spring must not decide the
    weather. Drawing the draft class out of the world's stream moved every
    seeded outcome in the game, which looks exactly like a balance change."""

    def test_the_world_stream_does_not_notice_the_league(self):
        a, b = new_game(seed=11), new_game(seed=11)
        for i in range(9):
            b.league.season.records[f"x{i}"] = lg.Record(key=f"x{i}")
        for _ in range(150):
            a.tick()
            b.tick()
        self.assertEqual(a.rng.getstate(), b.rng.getstate())
        self.assertEqual(round(a.treasury, 6), round(b.treasury, 6))

    def test_its_own_dice_are_put_back_where_they_were(self):
        g, _ = played(days=400)
        back = GameState.from_dict(g.to_dict())
        self.assertEqual(back.league.rng.getstate(), g.league.rng.getstate())


class TestItSurvivesBeingPutDown(unittest.TestCase):
    def test_the_whole_league_comes_back(self):
        g, _ = played(days=760)
        back = GameState.from_dict(g.to_dict())
        self.assertEqual(back.league.season.year, g.league.season.year)
        self.assertEqual(len(back.league.season.records),
                         len(g.league.season.records))
        self.assertEqual([f.who for f in back.league.season.fixtures],
                         [f.who for f in g.league.season.fixtures])
        self.assertEqual([p.name for p in back.league.season.prospects],
                         [p.name for p in g.league.season.prospects])
        self.assertEqual(len(back.league.past), len(g.league.past))
        self.assertEqual(back.league.bests, g.league.bests)

    def test_a_save_from_before_there_was_a_league_loads(self):
        g, _ = played(days=300)
        raw = g.to_dict()
        del raw["league"]
        back = GameState.from_dict(raw)
        back.tick()
        self.assertTrue(back.league.season.records)


class TestTheConsoleSaysIt(unittest.TestCase):
    def setUp(self):
        self.g, _ = played(days=760)
        self.buf = io.StringIO()
        self.con = Console(self.g, out=self.buf)

    def said(self, line):
        self.buf.truncate(0)
        self.buf.seek(0)
        self.con.do(line)
        return self.buf.getvalue()

    def test_the_table_names_every_lord(self):
        out = self.said("season")
        for t in self.g.world.towns.values():
            self.assertIn(t.name, out)
        self.assertIn("WHO IS GOING WHERE", out)

    def test_the_intake_names_every_man_in_it(self):
        out = self.said("draft")
        for p in self.g.league.season.prospects:
            self.assertIn(p.name.split()[0], out)

    def test_the_years_before_this_one_can_be_read_back(self):
        out = self.said("season past")
        self.assertIn(str(self.g.league.past[0]["year"]), out)

    def test_a_battle_leaves_a_box_score(self):
        boxes = [m for m in self.g.battles if m.strip().startswith("box")]
        self.assertTrue(boxes, "no battle in 760 days left a line")
        self.assertIn("lost", boxes[0])


if __name__ == "__main__":
    unittest.main()
