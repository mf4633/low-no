"""The house: a person who gets better at what he does, and who comes after him.

The thing under test is not really any one number. It is that the heir is
somebody -- that the twenty-two-year-old who takes the seat is carrying what
she was doing for the six years before it, and that the game can say so.
"""

import io
import random
import unittest

from marchlands import config as C
from marchlands import kin as kinly
from marchlands.campaign import CHAPTERS, Carry, carry_from
from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.kin import COMES_OF_AGE, MAX_SKILL, Kin, Person, found
from marchlands.scenario import new_game

YEAR = C.DAYS_PER_YEAR


def house(seed: int = 3) -> Kin:
    k = found(random.Random(seed), seat="aldworth")
    k.seat = "aldworth"
    return k


class TestASkillOnlyGrowsInTheJob(unittest.TestCase):
    def setUp(self):
        self.k = house()
        self.spare = [p for p in self.k.living()
                      if p.uid != self.k.head and p.age(0) >= COMES_OF_AGE]

    def test_nobody_learns_anything_sitting_at_home(self):
        idle = self.spare[0]
        before = dict(idle.xp)
        for d in range(1, 400):
            self.k.day(d, head_doing="hall")
        self.assertEqual(idle.xp, before)

    def test_a_posted_person_gets_better_at_that_and_nothing_else(self):
        who = self.spare[0]
        self.k.give(who, "factor")
        for d in range(1, 600):
            self.k.day(d, head_doing="hall")
        self.assertGreater(who.level("trade"), 0)
        self.assertEqual(who.level("tactics"), 0)
        self.assertEqual(who.level("stewardship"), 0)

    def test_what_the_lord_learns_is_what_the_lord_is_doing(self):
        lord = self.k.lord
        tactics = lord.xp.get("tactics", 0.0)
        for d in range(1, 400):
            self.k.day(d, head_doing="field")
        self.assertGreater(lord.xp["tactics"], tactics + 300)

    def test_learning_falls_off(self):
        """The fourth level costs more than twice the second, or a steward of
        fifty is a god and the first year of a reign means nothing."""
        p = Person(uid=99, name="x", born=-20 * YEAR)
        costs = []
        for want in (2, 4):
            p.xp = {}
            day = 0
            while p.level("stewardship") < want:
                day += 1
                p.learn("stewardship", 1.0, 0)
            costs.append(day)
        self.assertGreater(costs[1], 2 * costs[0])

    def test_the_young_learn_faster_and_the_old_slower(self):
        day = 30 * YEAR
        young = Person(uid=1, name="y", born=day - 15 * YEAR)
        prime = Person(uid=2, name="p", born=day - 30 * YEAR)
        old = Person(uid=3, name="o", born=day - 60 * YEAR)
        for p in (young, prime, old):
            p.learn("trade", 100.0, day)
        self.assertGreater(young.xp["trade"], prime.xp["trade"])
        self.assertGreater(prime.xp["trade"], old.xp["trade"])

    def test_a_skill_stops_at_the_top(self):
        p = Person(uid=1, name="x", born=0)
        p.xp["charm"] = 10_000_000.0
        self.assertEqual(p.level("charm"), MAX_SKILL)
        self.assertEqual(p.to_next("charm"), 0.0)


class TestOnePersonOnePlace(unittest.TestCase):
    """The cost of a post is not coin, it is the person."""

    def setUp(self):
        self.k = house()
        self.spare = [p for p in self.k.living()
                      if p.uid != self.k.head and p.age(0) >= COMES_OF_AGE]

    def test_a_second_appointment_turns_the_first_out(self):
        a, b = self.spare[0], self.spare[1]
        self.k.give(a, "factor")
        self.k.give(b, "factor")
        self.assertEqual(a.post, "")
        self.assertEqual(self.k.holder("factor").uid, b.uid)

    def test_a_child_is_given_nothing(self):
        child = max(self.k.living(), key=lambda p: p.born)
        said = self.k.give(child, "factor")
        self.assertIn(str(COMES_OF_AGE), said)
        self.assertEqual(child.post, "")

    def test_a_post_that_wants_a_place_says_so(self):
        said = self.k.give(self.spare[0], "steward")
        self.assertIn("town", said)

    def test_calling_somebody_home_leaves_the_post_empty(self):
        who = self.spare[0]
        self.k.give(who, "factor")
        self.k.give(who, "")
        self.assertIsNone(self.k.holder("factor"))

    def test_the_lord_keeps_his_own_hall_without_being_posted(self):
        """A lord of fifteen years' standing is his own steward, and a game
        that made you type it would be asking for paperwork, not a choice."""
        self.assertGreater(self.k.at_town("steward", "aldworth"), 0)
        self.assertEqual(self.k.at_town("steward", "bruille"), 0)


class TestWhoComesAfterHim(unittest.TestCase):
    def setUp(self):
        self.k = house()

    def test_the_eldest_grown_child_takes_the_seat(self):
        kids = [p for p in self.k.children_of(self.k.head) if p.alive]
        self.assertEqual(self.k.heir(0).uid, kids[0].uid)

    def test_an_heir_arrives_carrying_what_they_were_doing(self):
        heir = self.k.heir(0)
        self.k.give(heir, "factor")
        for d in range(1, 900):
            self.k.day(d, head_doing="hall")
        trade = heir.level("trade")
        self.assertGreater(trade, 0)
        said = self.k.bury(self.k.lord, 900)
        self.assertEqual(self.k.head, heir.uid)
        self.assertEqual(heir.level("trade"), trade)   # not a fresh start
        self.assertIn(heir.name, said[0])

    def test_the_succession_says_what_it_is_getting(self):
        heir = self.k.heir(0)
        self.k.give(heir, "factor")
        for d in range(1, 1200):
            self.k.day(d, head_doing="hall")
        said = self.k.bury(self.k.lord, 1200)[0]
        self.assertIn("trade", said)

    def test_a_house_with_nobody_left_ends(self):
        k = Kin()
        lord = k.add("Alone", "m", born=-40 * YEAR)
        lord.post, k.head = "head", lord.uid
        said = k.bury(lord, 0)
        self.assertIn("nobody left", said[0])
        self.assertIsNone(k.lord)

    def test_a_child_too_young_still_inherits_rather_than_the_line_ending(self):
        k = Kin()
        lord = k.add("Father", "m", born=-40 * YEAR)
        lord.post, k.head = "head", lord.uid
        k.add("Infant", "m", born=-2 * YEAR, father=lord.uid)
        k.bury(lord, 0)
        self.assertIsNotNone(k.lord)
        self.assertEqual(k.lord.name, "Infant")

    def test_burying_anyone_else_is_not_a_succession(self):
        head = self.k.head
        other = [p for p in self.k.living() if p.uid != head][0]
        self.k.bury(other, 0)
        self.assertEqual(self.k.head, head)
        self.assertFalse(other.alive)


class TestTheHouseRollsItsOwnDice(unittest.TestCase):
    """A birth in the hall must not move the weather.

    Sharing the world's stream re-rolled twelve seeds' worth of balance
    measurement the first time this system was wired in, without changing a
    single rule -- which is the kind of bug that looks like a balance change.
    """

    def test_a_busier_house_leaves_the_world_stream_alone(self):
        a, b = new_game(seed=11), new_game(seed=11)
        for i in range(9):
            p = b.kin.add(f"Extra{i}", "f" if i % 2 else "m", born=-20 * YEAR)
            if i % 2:
                mate = b.kin.add(f"Mate{i}", "m", born=-22 * YEAR)
                p.spouse, mate.spouse = mate.uid, p.uid
        for _ in range(150):
            a.tick()
            b.tick()
        self.assertEqual(a.rng.getstate(), b.rng.getstate())
        self.assertEqual(round(a.treasury, 6), round(b.treasury, 6))


class TestMarriage(unittest.TestCase):
    def setUp(self):
        self.g = new_game(seed=5)
        self.g.treasury = 80_000.0
        self.who = [p for p in self.g.kin.living()
                    if p.uid != self.g.kin.head
                    and p.age(0) >= COMES_OF_AGE and not p.spouse][0]

    def test_it_costs_a_dowry_and_cools_a_lord(self):
        town = self.g.world.towns["dunmere"]
        town.hostility = 60.0
        purse, before = self.g.treasury, town.hostility
        self.g.wed(self.who.name, "dunmere")
        self.assertLess(self.g.treasury, purse)
        self.assertLess(town.hostility, before)
        self.assertGreater(town.truce_days, 0)

    def test_it_cannot_be_bought_twice(self):
        self.g.wed(self.who.name, "dunmere")
        other = [p for p in self.g.kin.living()
                 if not p.spouse and p.age(0) >= COMES_OF_AGE]
        if other:
            said = self.g.wed(other[0].name, "dunmere")
            self.assertIn("already", said)

    def test_an_empty_purse_buys_nobody(self):
        self.g.treasury = 5.0
        said = self.g.wed(self.who.name, "dunmere")
        self.assertIn("expects", said)
        self.assertFalse(self.who.spouse)

    def test_the_match_joins_the_house(self):
        self.g.wed(self.who.name, "dunmere")
        mate = self.g.kin.get(self.who.spouse)
        self.assertIsNotNone(mate)
        self.assertTrue(mate.inlaw)
        self.assertEqual(mate.married_to, "dunmere")

    def test_somebody_married_in_does_not_take_the_seat_over_a_child(self):
        self.g.wed(self.who.name, "dunmere")
        heir = self.g.kin.heir(self.g.day)
        self.assertFalse(heir.inlaw)


class TestReputationIsAVerdict(unittest.TestCase):
    """Nobody picks a trait off a list."""

    def _reign(self, tax: int, days: int = 400) -> float:
        """A bot keeps the town alive, because a ruined town stops the clock
        and takes the reputation with it. Taxing nothing at all ruins it in
        three months, which is its own answer about generosity."""
        from marchlands.sim import Bot
        g = new_game(seed=5)
        bot = Bot(g)
        for _ in range(days):
            bot.step()
            g.home().tax_level = tax
            g.tick()
            if g.over:
                break
        return g.kin.lord.trait("just")

    def test_the_tax_you_take_is_what_they_call_you(self):
        light, normal, cruel = (self._reign(1), self._reign(2),
                                self._reign(max(C.TAX_LEVELS)))
        self.assertGreater(light, normal)
        self.assertGreater(normal, cruel)
        self.assertGreater(light, 0.25, "a light hand earns nothing")
        self.assertLess(cruel, -0.25, "a heavy one costs nothing")

    def test_the_ordinary_band_is_nobody_s_verdict(self):
        """`normal` should not slowly make a man cruel for playing normally."""
        self.assertLess(abs(self._reign(2)), 0.4)

    def test_only_an_earned_word_is_said_out_loud(self):
        p = Person(uid=1, name="x", born=0)
        self.assertEqual(p.reputation(), [])
        p.shift("merciful", -2.5)
        self.assertIn("very cruel", p.reputation())

    def test_a_trait_cannot_run_away(self):
        p = Person(uid=1, name="x", born=0)
        for _ in range(500):
            p.shift("bold", 1.0)
        self.assertLessEqual(p.trait("bold"), kinly.TRAIT_CAP)


class TestItActuallyMovesTheNumbers(unittest.TestCase):
    """A skill nobody can feel is a number on a screen."""

    def test_a_steward_raises_what_the_tax_roll_bears(self):
        k = house()
        who = [p for p in k.living()
               if p.uid != k.head and p.age(0) >= COMES_OF_AGE][0]
        k.seat = "elsewhere"                    # so the lord's own hall is out of it
        plain = k.mult("taxes", "aldworth")
        k.give(who, "steward", "aldworth")
        for d in range(1, 1500):
            k.day(d, head_doing="hall")
        self.assertGreater(k.mult("taxes", "aldworth"), plain)

    def test_an_envoy_makes_peace_cheaper(self):
        g = new_game(seed=5)
        plain = g.truce_cost("dunmere", 180)
        who = [p for p in g.kin.living()
               if p.uid != g.kin.head and p.age(0) >= COMES_OF_AGE][0]
        g.post(who.name, "envoy")
        who.xp["charm"] = kinly.STEEP * 64      # a lifetime of it
        self.assertLess(g.truce_cost("dunmere", 180), plain)

    def test_a_captain_only_helps_the_host_he_is_with(self):
        k = house()
        who = [p for p in k.living()
               if p.uid != k.head and p.age(0) >= COMES_OF_AGE][0]
        k.give(who, "captain", "4")
        who.xp["tactics"] = kinly.STEEP * 25
        self.assertGreater(k.mult("attack", 4), k.mult("attack", 9))

    def test_who_governs_here_reaches_the_town_s_own_mood(self):
        g = new_game(seed=5)
        who = [p for p in g.kin.living()
               if p.uid != g.kin.head and p.age(0) >= COMES_OF_AGE][0]
        g.post(who.name, "steward", "aldworth")
        who.xp["stewardship"] = kinly.STEEP * 36
        g.tick()
        factors = dict(g.home().mood_factors(g.progress))
        self.assertIn("who governs here", factors)
        self.assertGreater(factors["who governs here"], 0)


class TestItSurvivesBeingPutDown(unittest.TestCase):
    def test_a_saved_house_comes_back_whole(self):
        g = new_game(seed=5)
        who = [p for p in g.kin.living()
               if p.uid != g.kin.head and p.age(0) >= COMES_OF_AGE][0]
        g.post(who.name, "factor")
        g.advance(300)
        back = GameState.from_dict(g.to_dict())
        self.assertEqual([p.name for p in back.kin.people],
                         [p.name for p in g.kin.people])
        self.assertEqual(back.kin.get(who.uid).xp, who.xp)
        self.assertEqual(back.kin.get(who.uid).post, "factor")
        self.assertEqual(back.kin.head, g.kin.head)

    def test_the_house_s_own_dice_are_put_back_where_they_were(self):
        g = new_game(seed=5)
        g.advance(120)
        back = GameState.from_dict(g.to_dict())
        self.assertEqual(back.kin.rng.getstate(), g.kin.rng.getstate())

    def test_a_save_from_before_the_house_existed_gets_one(self):
        g = new_game(seed=5)
        raw = g.to_dict()
        del raw["kin"]
        back = GameState.from_dict(raw)
        self.assertTrue(back.kin.people)
        self.assertIsNotNone(back.kin.lord)
        self.assertEqual(back.kin.lord.name, g.lord.name)


class TestTheHouseCrossesAChapter(unittest.TestCase):
    """The part of a campaign that is actually a campaign."""

    def test_everybody_is_older_in_the_next_chapter(self):
        g = CHAPTERS[0].start(seed=5)
        ages = {p.uid: p.age(g.day) for p in g.kin.living()}
        g.advance(700)
        carry = carry_from(g, Carry(), won=True)
        nxt = CHAPTERS[1].start(seed=5, carry=carry)
        for uid, was in ages.items():
            now = nxt.kin.get(uid)
            if now is not None and now.alive:
                self.assertGreaterEqual(now.age(nxt.day), was + 1)

    def test_what_they_learned_crosses_with_them(self):
        g = CHAPTERS[0].start(seed=5)
        who = [p for p in g.kin.living()
               if p.uid != g.kin.head and p.age(g.day) >= COMES_OF_AGE][0]
        g.post(who.name, "factor")
        g.advance(700)
        earned = who.xp.get("trade", 0.0)
        self.assertGreater(earned, 0)
        carry = carry_from(g, Carry(), won=True)
        nxt = CHAPTERS[1].start(seed=5, carry=carry)
        self.assertAlmostEqual(nxt.kin.get(who.uid).xp.get("trade", 0.0), earned)

    def test_posts_do_not_cross_but_people_do(self):
        g = CHAPTERS[0].start(seed=5)
        who = [p for p in g.kin.living()
               if p.uid != g.kin.head and p.age(g.day) >= COMES_OF_AGE][0]
        g.post(who.name, "factor")
        carry = carry_from(g, Carry(), won=True)
        nxt = CHAPTERS[1].start(seed=5, carry=carry)
        self.assertEqual(nxt.kin.get(who.uid).post, "")
        self.assertEqual(nxt.kin.head, g.kin.head)


class TestTheConsoleSaysAllOfIt(unittest.TestCase):
    def setUp(self):
        self.g = new_game(seed=5)
        self.buf = io.StringIO()
        self.con = Console(self.g, out=self.buf)

    def said(self, line):
        self.buf.truncate(0)
        self.buf.seek(0)
        self.con.do(line)
        return self.buf.getvalue()

    def test_the_house_lists_everyone_living(self):
        out = self.said("kin")
        for p in self.g.kin.living():
            self.assertIn(p.name, out)

    def test_one_of_them_gets_a_sheet_of_their_own(self):
        out = self.said(f"kin {self.g.kin.lord.name.split()[0]}")
        for skill in kinly.SKILLS:
            self.assertIn(skill, out)

    def test_the_posts_screen_names_every_post(self):
        out = self.said("post")
        for key in kinly.POSTS:
            self.assertIn(key, out)

    def test_a_post_can_be_given_and_taken_back_from_the_console(self):
        who = [p for p in self.g.kin.living()
               if p.uid != self.g.kin.head and p.age(0) >= COMES_OF_AGE][0]
        first = who.name.split()[0]
        self.said(f"post {first} factor")
        self.assertEqual(who.post, "factor")
        self.said(f"post {first} none")
        self.assertEqual(who.post, "")

    def test_nobody_of_that_name_is_said_plainly(self):
        self.assertIn("nobody", self.said("post Ethelred factor"))

    def test_a_post_somewhere_that_is_not_yours_is_refused(self):
        who = [p for p in self.g.kin.living()
               if p.uid != self.g.kin.head and p.age(0) >= COMES_OF_AGE][0]
        out = self.said(f"post {who.name.split()[0]} steward ostmark")
        self.assertIn("no settlement of yours", out)
        self.assertEqual(who.post, "")

    def test_the_matches_screen_prices_them(self):
        out = self.said("marry")
        self.assertIn("c", out)
        self.assertIn("Dunmere", out)

    def test_the_hint_points_at_a_child_with_nothing_to_do(self):
        self.g.advance(30)
        hints = " ".join(self.con.hints())
        self.assertIn("nothing to do", hints)
        self.assertIn("post ", hints)


if __name__ == "__main__":
    unittest.main()
