"""The march as a diplomatic web rather than eight separate quarrels.

What people mean when they say they like Europa Universalis' politics is
rarely the peace screen. It is that you can see *why* somebody hates you and
watch it wear off; that conquest is self-limiting because the neighbours stop
quarrelling with each other and start writing to each other; that a war wants
a reason and the difference is paid by everybody on the fence; and that an
ally who comes when you are attacked is an ally who calls when he is.

These are tests that all four are real -- that the reasons are dated and
decay, that the letter can be got out of three different ways, that a ground
changes what a war costs, and that "no" to a call is a real answer with a
real price rather than a button that does nothing.
"""

import io
import json
import re
import unittest

from marchlands import chancery as court
from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.scenario import new_game
from marchlands.scenarios import start
from marchlands.sim import Bot, Conqueror
from marchlands.web import snapshot


#: The three levers that used to be simply available and are now institutions
#: you have to found: see tech.py. A test about what a price ceiling *does* is
#: not a test about whether you are allowed one, so these grant the charter
#: and get on with the measurement -- and tests/test_tech.py is where being
#: allowed one is tested.
CHARTERED = ("coinage", "assize_of_bread", "chancery")


def chartered(game):
    game.progress.researched |= set(CHARTERED)
    return game


def plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _a_host(g):
    """A host of the player's, standing somewhere, to hand to _take_town."""
    home = next(iter(g.world.settlements))
    g.world.settlements[home].units = {"spearman": 40.0}
    g.raise_host(home, {"spearman": 30})
    a = g.armies[-1]
    a.owner = "player"
    return a


def grown(seed=5, days=300, bot=Bot):
    g = chartered(start("marchlands", seed=seed))
    runner = bot(g)
    for _ in range(days):
        runner.step()
        g.tick()
        if g.over:
            break
    return g


class TestTheLedgerIsTheOpinion(unittest.TestCase):
    """A number is a mood. A dated, decaying list of reasons is a plan."""

    def setUp(self):
        self.c = court.Chancery(seed=1)

    def test_a_reason_is_worth_what_it_was_on_the_day(self):
        self.c.write("dunmere", "took_town", -30.0, 100)
        self.assertEqual(self.c.opinion("dunmere", 100), -30.0)

    def test_and_less_every_day_after(self):
        self.c.write("dunmere", "took_town", -30.0, 0)
        a = self.c.opinion("dunmere", 100)
        b = self.c.opinion("dunmere", 200)
        self.assertGreater(a, -30.0)
        self.assertGreater(b, a)

    def test_until_it_is_nothing_and_not_the_other_way(self):
        """Decay stops at nothing. Running past it would turn an old grievance
        into affection, which is not how anybody works."""
        self.c.write("dunmere", "took_town", -30.0, 0)
        self.assertEqual(self.c.opinion("dunmere", 100000), 0.0)
        self.c.write("vantry", "gift", 40.0, 0)
        self.assertEqual(self.c.opinion("vantry", 100000), 0.0)

    def test_some_things_are_never_forgotten(self):
        self.c.write("vantry", "marriage", 70.0, 0)
        self.assertEqual(self.c.opinion("vantry", 99999), 70.0)

    def test_the_reasons_come_back_in_words_biggest_first(self):
        self.c.write("dunmere", "took_town", -30.0, 0)
        self.c.write("dunmere", "gift", 8.0, 0)
        rows = self.c.reasons("dunmere", 0)
        self.assertEqual([r[0] for r in rows],
                         [court.WHYS["took_town"].label,
                          court.WHYS["gift"].label])

    def test_the_same_reason_twice_is_one_line(self):
        self.c.write("dunmere", "gift", 5.0, 0)
        self.c.write("dunmere", "gift", 7.0, 0)
        self.assertEqual(len(self.c.reasons("dunmere", 0)), 1)
        self.assertAlmostEqual(self.c.reasons("dunmere", 0)[0][1], 12.0)

    def test_a_reason_nobody_wrote_down_cannot_exist(self):
        self.c.write("dunmere", "because_i_said_so", -99.0, 0)
        self.assertEqual(self.c.opinion("dunmere", 0), 0.0)

    def test_the_book_is_swept_of_what_has_worn_out(self):
        self.c.write("dunmere", "took_town", -30.0, 0)
        self.c.sweep(100000)
        self.assertNotIn("dunmere", self.c.ledger)

    def test_but_never_of_what_still_stands(self):
        self.c.write("vantry", "marriage", 70.0, 0)
        self.c.sweep(100000)
        self.assertEqual(self.c.opinion("vantry", 100000), 70.0)

    def test_a_word_for_the_number(self):
        for value, want in ((90, "devoted"), (50, "friendly"), (0, "correct"),
                            (-20, "cool"), (-50, "hostile"), (-90, "implacable")):
            self.assertEqual(court.temper(value), want, value)


class TestOffenceIsNotDislike(unittest.TestCase):
    """Only some feelings put a name on a letter. A lord who dislikes you for
    demanding tribute dislikes you; a lord who has watched you take three
    towns has a reason to write to his neighbours, and the coalition is about
    the second kind only."""

    def setUp(self):
        self.c = court.Chancery(seed=1)

    def test_a_grievance_that_is_not_about_appetite_does_not_count(self):
        self.c.write("dunmere", "demanded", -40.0, 0)
        self.assertLess(self.c.opinion("dunmere", 0), 0)
        self.assertEqual(self.c.offence("dunmere", 0), 0.0)

    def test_one_that_is_does(self):
        self.c.write("dunmere", "took_town", -40.0, 0)
        self.assertEqual(self.c.offence("dunmere", 0), 40.0)

    def test_a_broken_host_takes_a_bite_out_of_it(self):
        """The court screen promises this and for a while the arithmetic did
        not keep the promise: offence summed only the negative reasons, so
        beating a host was worth exactly nothing to the letter."""
        self.c.write("dunmere", "took_town", -40.0, 0)
        self.c.write("dunmere", "beaten", 22.0, 0)
        self.assertAlmostEqual(self.c.offence("dunmere", 0), 18.0)

    def test_but_it_is_awe_and_not_affection(self):
        """A man whose host you broke will not sign a letter with you on it.
        He does not like you, will not ally, and his temper is not cooled."""
        self.c.write("dunmere", "beaten", 40.0, 0)
        self.assertEqual(self.c.goodwill("dunmere", 0), 0.0)
        self.assertGreater(self.c.opinion("dunmere", 0), 0.0)

    def test_goodwill_is_what_a_gift_and_a_marriage_buy(self):
        self.c.write("vantry", "marriage", 70.0, 0)
        self.c.write("vantry", "gift", 10.0, 0)
        self.assertAlmostEqual(self.c.goodwill("vantry", 0), 80.0)


class TestTheLetterAgainstYou(unittest.TestCase):
    """The signature mechanic: conquest that is cheap once, dear twice and
    ruinous three times -- not because any lord got stronger, but because
    they started counting together."""

    def setUp(self):
        self.g = chartered(new_game(seed=5))
        self.c = self.g.court
        self.keys = list(self.g.world.towns)

    def offend(self, n, weight=-60.0):
        for k in self.keys[:n]:
            self.c.write(k, "took_town", weight, self.g.day)

    def test_two_angry_lords_are_two_quarrels(self):
        self.offend(2)
        self.g.tick()
        self.assertEqual(self.c.coalition, [])

    def test_three_are_a_letter(self):
        self.offend(3)
        self.g.tick()
        self.assertEqual(len(self.c.coalition), 3)

    def test_and_it_is_announced_rather_than_discovered(self):
        self.offend(3)
        said = " ".join(self.g.tick())
        self.assertIn("one letter", said)

    def test_a_signatory_will_not_treat_alone(self):
        self.offend(3)
        self.g.tick()
        who = self.c.coalition[0]
        self.g.treasury = 500000
        said = self.g.truce(who)
        self.assertIn("will not treat alone", said)
        self.assertEqual(self.g.world.towns[who].truce_days, 0)

    def test_a_lord_who_has_cooled_takes_his_name_off(self):
        """Buying one lord off has to do something, or it is not a lever."""
        self.offend(4)
        self.g.tick()
        self.assertEqual(len(self.c.coalition), 4)
        cooled = self.c.coalition[0]
        self.c.write(cooled, "beaten", 55.0, self.g.day)
        self.g.tick()
        self.assertNotIn(cooled, self.c.coalition)
        self.assertEqual(len(self.c.coalition), 3)

    def test_and_when_too_few_are_left_it_lapses(self):
        self.offend(3)
        self.g.tick()
        for k in list(self.c.coalition):
            self.c.write(k, "beaten", 55.0, self.g.day)
        said = " ".join(self.g.tick())
        self.assertEqual(self.c.coalition, [])
        self.assertIn("not renewed", said)

    def test_names_do_not_flicker_on_and_off(self):
        """A coalition that reforms every few days is one nobody can plan
        around, which is why the bar to sign is above the bar to stay."""
        self.assertLess(court.COALITION_LAPSE, court.COALITION_BAR)

    def test_an_ally_does_not_sign(self):
        self.offend(4)
        self.c.allies.append(self.keys[0])
        self.g.tick()
        self.assertNotIn(self.keys[0], self.c.coalition)

    def test_the_whole_thing_can_be_bought_at_a_price(self):
        self.offend(3)
        self.g.tick()
        price = self.c.coalition_price(self.g.day)
        self.assertGreater(price, 0)
        self.g.treasury = price + 1
        said = self.g.buy_off_coalition()
        self.assertIn("buys the letter back", said)
        self.assertEqual(self.c.coalition, [])

    def test_but_not_on_credit(self):
        self.offend(3)
        self.g.tick()
        self.g.treasury = 1.0
        said = self.g.buy_off_coalition()
        self.assertIn("costs", said)
        self.assertEqual(len(self.c.coalition), 3)

    def test_it_forms_against_somebody_who_keeps_taking_towns(self):
        g = grown(days=1080, bot=Conqueror)
        self.assertTrue(g.court.declared, "the conqueror never went to war")
        self.assertTrue(g.court.taken or g.court.coalition
                        or any(t.mine for t in g.world.towns.values()))

    def test_and_never_against_somebody_who_only_trades(self):
        g = grown(days=900)
        self.assertEqual(g.court.coalition, [],
                         "the march united against a merchant")


class TestAWarWantsAReason(unittest.TestCase):
    """Nothing stops you marching on anybody. What a ground buys is that the
    rest of the march shrugs instead of writing to each other about you."""

    def setUp(self):
        self.g = chartered(new_game(seed=5))
        self.c = self.g.court

    def test_being_burned_out_is_a_reason(self):
        self.c.give_ground("dunmere", "raided", self.g.day)
        self.assertIsNotNone(self.c.ground_for("dunmere", self.g.day))

    def test_and_it_does_not_last_forever(self):
        self.c.give_ground("dunmere", "raided", 0)
        self.assertIsNone(self.c.ground_for("dunmere", 10_000))

    def test_a_claim_by_marriage_lasts_two_years_as_a_reason(self):
        # EU4's unpressed claim lapses; the right to inherit does not.
        self.c.claims["vantry"] = 0
        self.assertIsNotNone(self.c.ground_for("vantry", self.c.CLAIM_DAYS))
        self.assertIsNone(self.c.ground_for("vantry", self.c.CLAIM_DAYS + 1))
        self.assertIn("vantry", self.c.claims, "the right to inherit stays")

    def test_marching_with_one_offends_less_than_marching_without(self):
        def cost(ground):
            g = chartered(new_game(seed=5))
            if ground:
                g.court.give_ground("dunmere", "raided", g.day)
            g._declare(g.world.towns["dunmere"])
            return sum(g.court.offence(k, g.day) for k in g.world.towns)
        self.assertLess(cost(True), cost(False))

    def test_and_the_town_at_home_is_not_a_spectator(self):
        g = chartered(new_game(seed=5))
        was = g.home().popularity
        g._declare(g.world.towns["dunmere"])
        self.assertLess(g.home().popularity, was)

    def test_but_not_when_you_had_a_reason(self):
        g = chartered(new_game(seed=5))
        g.court.give_ground("dunmere", "raided", g.day)
        was = g.home().popularity
        said = g._declare(g.world.towns["dunmere"])
        self.assertEqual(g.home().popularity, was)
        self.assertIn("You have grounds", said)

    def test_one_siege_is_one_quarrel_however_long_it_runs(self):
        g = chartered(new_game(seed=5))
        g._declare(g.world.towns["dunmere"])
        first = g.court.offence("vantry", g.day)
        for _ in range(5):
            g._declare(g.world.towns["dunmere"])
        self.assertAlmostEqual(g.court.offence("vantry", g.day), first)

    def test_a_town_taken_lawfully_offends_less(self):
        def take(lawful):
            g = chartered(new_game(seed=5))
            if lawful:
                g.court.give_ground("dunmere", "raided", g.day)
            g._declare(g.world.towns["dunmere"])
            before = {k: g.court.offence(k, g.day) for k in g.world.towns}
            army = _a_host(g)
            g._take_town(g.world.towns["dunmere"], army)
            return sum(g.court.offence(k, g.day) - before[k]
                       for k in g.world.towns if not g.world.towns[k].mine)
        self.assertLess(take(True), take(False))

    def test_and_retaking_one_that_revolted_is_not_a_second_conquest(self):
        g = chartered(new_game(seed=5))
        a = _a_host(g)
        town = g.world.towns["dunmere"]
        g._take_town(town, a)
        first = g.court.offence("vantry", g.day)
        town.owner = ""
        g._take_town(town, a)
        again = g.court.offence("vantry", g.day) - first
        self.assertLess(again, first * 0.5)


class TestFriendsCostSomething(unittest.TestCase):
    def setUp(self):
        self.g = chartered(new_game(seed=5))
        self.c = self.g.court

    def test_a_lord_who_does_not_think_much_of_you_will_not_swear(self):
        said = self.g.ally("dunmere")
        self.assertIn("will not swear", said)
        self.assertEqual(self.c.allies, [])

    def test_one_who_does_will(self):
        self.c.write("dunmere", "marriage", 70.0, self.g.day)
        said = self.g.ally("dunmere")
        self.assertIn("allied", said)
        self.assertIn("dunmere", self.c.allies)

    def test_and_then_he_does_not_march_on_you(self):
        self.c.write("dunmere", "marriage", 90.0, self.g.day)
        self.g.ally("dunmere")
        t = self.g.world.towns["dunmere"]
        t.hostility = 999.0
        t.truce_days = 0
        for _ in range(3):
            self.g.tick()
        self.assertFalse([a for a in self.g.armies if a.owner == "dunmere"])

    def test_a_call_wants_an_answer(self):
        """Built rather than waited for: a test that skips when the dice do
        not oblige is a test that does not test."""
        self.c.write("vantry", "marriage", 90.0, self.g.day)
        self.g.ally("vantry")
        a = _a_host(self.g)
        a.owner = "dunmere"
        a.bound_for = "vantry"
        said = " ".join(self.g._alliance_day())
        self.assertIsNotNone(self.c.called)
        self.assertEqual(self.c.called[0], "vantry")
        self.assertIn("calls you to the war", said)

    def test_coming_when_called_is_remembered(self):
        self.c.write("vantry", "marriage", 90.0, self.g.day)
        self.g.ally("vantry")
        self.c.called = ("vantry", self.g.day)
        before = self.c.opinion("vantry", self.g.day)
        self.g.answer_call(True)
        self.assertGreater(self.c.opinion("vantry", self.g.day), before)

    def test_and_not_coming_is_remembered_by_everybody(self):
        """No is a real answer, and the price is that every other lord on the
        march now knows what your word is worth."""
        self.c.write("vantry", "marriage", 90.0, self.g.day)
        self.g.ally("vantry")
        self.c.called = ("vantry", self.g.day)
        others = [k for k in self.g.world.towns if k != "vantry"]
        was = {k: self.c.opinion(k, self.g.day) for k in self.g.world.towns}
        # Freeciv's three asks: disappointed, warned, done.
        for _ in range(self.g.ALLY_PATIENCE - 1):
            said = self.g.answer_call(False)
            self.assertIn("disappointed", said)
            self.assertIn("vantry", self.c.allies)
            self.c.called = ("vantry", self.g.day)
        self.assertIn("not ask many more times", said)
        self.g.answer_call(False)
        self.assertNotIn("vantry", self.c.allies)
        self.assertLess(self.c.opinion("vantry", self.g.day), was["vantry"] - 50)
        for k in others:
            self.assertLess(self.c.opinion(k, self.g.day), was[k], k)

    def test_coming_forgives_the_times_you_did_not(self):
        self.c.write("vantry", "marriage", 90.0, self.g.day)
        self.g.ally("vantry")
        self.c.called = ("vantry", self.g.day)
        self.g.answer_call(False)
        self.c.called = ("vantry", self.g.day)
        self.g.answer_call(True)
        self.assertNotIn("vantry", self.c.refused)

    def test_saying_nothing_is_saying_no(self):
        self.c.write("vantry", "marriage", 90.0, self.g.day)
        self.g.ally("vantry")
        self.c.called = ("vantry", self.g.day - self.g.CALL_DAYS - 1)
        self.g.tick()
        self.assertIsNone(self.c.called)
        self.assertEqual(self.c.refused.get("vantry"), 1)


class TestAHouseThatEnds(unittest.TestCase):
    """The other reason to marry a daughter into Ostmark: the one way a town
    comes to you with nobody in the field."""

    def test_a_claim_takes_the_hall(self):
        g = chartered(new_game(seed=5))
        first = next(iter(g.world.towns))
        g.court.claims[first] = 0
        g.SUCCESSION_ODDS = 1.0
        said = " ".join(g._succession_abroad())
        self.assertTrue(g.world.towns[first].mine, said)
        self.assertIn("without an heir", said)
        self.assertNotIn(first, g.court.claims, "the claim was spent")

    def test_and_no_claim_means_a_cousin_takes_it(self):
        g = chartered(new_game(seed=5))
        g.SUCCESSION_ODDS = 1.0
        said = " ".join(g._succession_abroad())
        self.assertIn("cousin", said)
        self.assertFalse(any(t.mine for t in g.world.towns.values()))

    def test_a_marriage_makes_the_claim(self):
        g = chartered(new_game(seed=5))
        g.treasury = 500000
        who = next(p for p in g.kin.people
                   if p.alive and not p.married_to and not p.spouse
                   and p.age(g.day) >= 16)
        said = g.wed(who.name, "vantry")
        self.assertIn("vantry", g.court.claims, said)

    def test_and_even_a_bloodless_one_is_noticed(self):
        """A town is a town. Coming by it without a war is cheap, not free."""
        g = chartered(new_game(seed=5))
        first = next(iter(g.world.towns))
        g.court.claims[first] = 0
        g.SUCCESSION_ODDS = 1.0
        said = " ".join(g._succession_abroad())
        self.assertTrue(g.world.towns[first].mine, said)
        self.assertTrue(any(g.court.offence(k, g.day) > 0
                            for k in g.world.towns
                            if not g.world.towns[k].mine))


class TestItDrawsFromItsOwnDice(unittest.TestCase):
    """Fourth time. The kin moved the weather, the league re-rolled twelve
    seeds of balance measurement, the voices would have re-rolled the
    campaign from a browser poll."""

    def test_the_chancery_does_not_touch_the_world_stream(self):
        g = chartered(new_game(seed=5))
        before = g.rng.getstate()
        for _ in range(200):
            g._succession_abroad()
            g._coalition_day()
        self.assertEqual(before, g.rng.getstate())

    def test_and_it_is_seeded_from_the_game(self):
        a, b = chartered(new_game(seed=5)), chartered(new_game(seed=5))
        self.assertEqual(a.court.seed, b.court.seed)
        self.assertNotEqual(chartered(new_game(seed=6)).court.seed, a.court.seed)

    def test_and_it_survives_a_save(self):
        g = chartered(new_game(seed=5))
        g.court.write("dunmere", "took_town", -30.0, g.day)
        g.court.give_ground("vantry", "raided", g.day)
        g.court.allies.append("bruille")
        g.court.claims["ostmark"] = 4
        g.court.taken.add("dunmere")
        back = GameState.from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual(back.court.opinion("dunmere", g.day), -30.0)
        self.assertIsNotNone(back.court.ground_for("vantry", g.day))
        self.assertEqual(back.court.allies, ["bruille"])
        self.assertEqual(back.court.claims, {"ostmark": 4})
        self.assertIn("dunmere", back.court.taken)
        self.assertEqual(back.court.rng.random(), g.court.rng.random())


class TestPoliticsIsPricedAsMoney(unittest.TestCase):
    """The seam where the two halves of the game meet.

    A merchant's world is the diplomatic one. A lord's opinion is the rate his
    customs post charges *you*, which makes a gift an investment with a return
    rather than only war insurance -- and makes the third town you take
    something you watch in the ledger every day afterwards.
    """

    def toll(self, setup):
        g = chartered(new_game(seed=5))
        setup(g)
        g.tick()
        return g.world.tariff_for("dunmere", None)

    def test_a_lord_who_likes_you_charges_you_less(self):
        plain = self.toll(lambda g: None)
        fond = self.toll(lambda g: g.court.write("dunmere", "marriage", 70.0, 0))
        self.assertLess(fond, plain)

    def test_and_one_who_does_not_charges_more(self):
        plain = self.toll(lambda g: None)
        sour = self.toll(lambda g: g.court.write("dunmere", "took_town", -70.0, 0))
        self.assertGreater(sour, plain)

    def test_an_ally_waves_your_carts_through(self):
        def swear(g):
            g.court.write("dunmere", "marriage", 90.0, 0)
            g.ally("dunmere")
        self.assertLess(self.toll(swear), self.toll(lambda g: None) * 0.5)

    def test_and_a_signatory_does_not(self):
        def sign(g):
            g.court.write("dunmere", "took_town", -60.0, 0)
            g.court.coalition.append("dunmere")
        self.assertGreater(self.toll(sign), self.toll(lambda g: None) * 1.5)

    def test_it_cannot_run_away_in_either_direction(self):
        low = self.toll(lambda g: g.court.write("dunmere", "marriage", 900.0, 0))
        high = self.toll(lambda g: g.court.write("dunmere", "took_town", -900.0, 0))
        self.assertGreater(low, 0.0)
        self.assertLess(high, 0.25)

    def test_a_town_of_yours_tolls_nobody(self):
        g = chartered(new_game(seed=5))
        g.world.towns["dunmere"].owner = "player"
        self.assertEqual(g.world.tariff_for("dunmere", None), 0.0)

    def test_the_base_rate_does_not_wear_away_with_use(self):
        """It did, for the life of the project. The trade engine wrote the
        *effective* rate back into the market and `tariff_for` read that as
        the base, so the trading posts' relief compounded once per visiting
        cart: two hundred visits turned a six per cent toll into eight
        thousandths of one per cent, and every customs post on the march had
        quietly stopped charging for anything."""
        g = grown(days=400)
        for key, t in g.world.towns.items():
            if t.mine:
                continue
            self.assertGreater(g.world.tariff_for(key, None), 0.005, key)

    def test_the_scanner_prices_it_without_being_told_to(self):
        """No new code: the route-finder already asked what the toll was. The
        point of putting the politics *into* the toll rather than beside it is
        that everything downstream reads it for free."""
        from marchlands.advisor import scan

        def best(setup):
            g = chartered(new_game(seed=5))
            setup(g)
            g.tick()
            rows = scan(g.world, next(iter(g.world.settlements)))
            return rows[0].per_day if rows else 0.0

        plain = best(lambda g: None)
        fond = best(lambda g: [g.court.write(k, "marriage", 80.0, 0)
                               for k in g.world.towns])
        sour = best(lambda g: [g.court.write(k, "took_town", -80.0, 0)
                               for k in g.world.towns])
        self.assertGreater(fond, plain)
        self.assertLess(sour, plain)

    def test_the_surplus_screen_reads_the_politics(self):
        """The one screen in the game that prices a tax properly was the only
        one that could not see who was levying it."""
        g = chartered(new_game(seed=5))
        g.court.write("dunmere", "took_town", -70.0, 0)
        g.tick()
        buf = io.StringIO()
        Console(g, out=buf).do("surplus bread dunmere")
        out = plain(buf.getvalue())
        self.assertIn("charges you more than a stranger", out)

    def test_and_the_court_screen_reads_the_money(self):
        g = chartered(new_game(seed=5))
        buf = io.StringIO()
        con = Console(g, out=buf)
        con.do("court")
        self.assertIn("toll", plain(buf.getvalue()))
        buf.truncate(0)
        buf.seek(0)
        con.do("court dunmere")
        self.assertIn("his toll on you", plain(buf.getvalue()))


class TestTheStreetKnowsAboutIt(unittest.TestCase):
    """Politics and prices are not screens to the people living under them. A
    coalition is the Ostmark road closing; inflation is what bread cost last
    year. If neither ever comes up in the street, both are spreadsheets a
    player reads instead of a world a player lives in."""

    def test_the_street_can_see_the_letter(self):
        from marchlands import voices
        g = chartered(new_game(seed=5))
        g.court.coalition = list(g.world.towns)[:4]
        m = voices.read(g.home(), g)
        self.assertEqual(m.signed, 4)
        said = voices.loudest(g.home(), g)
        self.assertTrue(said)

    def test_and_a_war_nobody_can_name_a_cause_for(self):
        from marchlands import voices
        g = chartered(new_game(seed=5))
        g._declare(g.world.towns["dunmere"])
        self.assertTrue(voices.read(g.home(), g).unjust)

    def test_but_not_one_it_can(self):
        from marchlands import voices
        g = chartered(new_game(seed=5))
        g.court.give_ground("dunmere", "raided", g.day)
        g._declare(g.world.towns["dunmere"])
        self.assertFalse(voices.read(g.home(), g).unjust)

    def test_it_can_see_the_price_of_bread_last_year(self):
        from marchlands import voices
        g = chartered(new_game(seed=5))
        m = voices.read(g.home(), g)
        self.assertIsInstance(m.inflation, float)

    def test_and_what_the_march_charges_the_carts(self):
        from marchlands import voices
        g = chartered(new_game(seed=5))
        g.tick()
        self.assertGreater(voices.read(g.home(), g).toll, 0.0)

    def test_every_new_line_belongs_to_something_that_can_happen(self):
        from marchlands import voices
        g = chartered(new_game(seed=5))
        base = voices.read(g.home(), g)
        for key in ("called", "coalition", "blockade", "unjust", "inflation",
                    "tolls", "allies", "cheap_roads"):
            v = next(x for x in voices.VOICES if x.key == key)
            self.assertTrue(v.lines, key)
            self.assertFalse(v.when(base) and key in ("coalition", "called"),
                             f"{key} fires on a quiet day")


class TestTheConsoleSaysAllOfIt(unittest.TestCase):
    def setUp(self):
        self.buf = io.StringIO()
        self.g = chartered(new_game(seed=5))
        self.con = Console(self.g, out=self.buf)

    def said(self):
        return plain(self.buf.getvalue())

    def test_court_lists_every_lord_with_a_word_and_a_number(self):
        self.con.do("court")
        out = self.said()
        self.assertIn("THE COURT", out)
        for t in self.g.world.towns.values():
            self.assertIn(t.name, out)

    def test_and_one_lord_in_full_says_why(self):
        self.g.court.write("dunmere", "took_town", -30.0, self.g.day)
        self.con.do("court dunmere")
        out = self.said()
        self.assertIn(court.WHYS["took_town"].label, out)
        self.assertIn("wears off in", out)

    def test_it_says_whether_you_have_a_reason_to_march(self):
        self.con.do("court dunmere")
        self.assertIn("none", self.said())
        self.g.court.give_ground("dunmere", "raided", self.g.day)
        self.buf.truncate(0)
        self.buf.seek(0)
        self.con.do("court dunmere")
        self.assertIn(court.GROUNDS["raided"].label, self.said())

    def test_the_letter_names_all_three_ways_out(self):
        for k in list(self.g.world.towns)[:3]:
            self.g.court.write(k, "took_town", -60.0, self.g.day)
        self.g.tick()
        self.buf.truncate(0)
        self.buf.seek(0)
        self.con.do("court")
        out = self.said()
        self.assertIn("THE LETTER AGAINST YOU", out)
        self.assertIn("beat their hosts", out)
        self.assertIn("court buy", out)

    def test_ally_and_call_are_commands(self):
        self.con.do("ally nowhere")
        self.assertIn("no town called", self.said())
        self.buf.truncate(0)
        self.buf.seek(0)
        self.con.do("call yes")
        self.assertIn("nobody has called", self.said())

    def test_the_steward_says_when_the_march_is_about_to_unite(self):
        for k in list(self.g.world.towns)[:4]:
            self.g.court.write(k, "took_town", -60.0, self.g.day)
        self.g.tick()
        self.assertTrue(any("signed one letter" in h for h in self.con.hints()),
                        self.con.hints())

    def test_and_an_unanswered_call_beats_everything_else_he_could_say(self):
        self.g.court.allies.append("vantry")
        self.g.court.called = ("vantry", self.g.day)
        self.assertTrue(any("called you to his war" in h
                            for h in self.con.hints()), self.con.hints())

    def test_every_command_is_in_the_help(self):
        self.con.do("help")
        out = self.said()
        for word in ("court", "ally", "call"):
            self.assertIn(word, out)


class TestTheBrowserGetsIt(unittest.TestCase):
    def test_the_snapshot_carries_the_whole_web(self):
        g = grown(days=200)
        snap = json.loads(json.dumps(snapshot(g)))
        c = snap["court"]
        for field in ("towns", "coalition", "bar", "price", "called"):
            self.assertIn(field, c)
        one = c["towns"]["dunmere"]
        for field in ("opinion", "temper", "offence", "signed", "allied",
                      "claim", "ground", "why"):
            self.assertIn(field, one)

    def test_the_letter_has_a_panel_of_its_own(self):
        """It should not be possible to have the march unite against you and
        not notice. A number buried in a tooltip is not a notice."""
        import os
        from marchlands.web import STATIC
        with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as fh:
            page = fh.read()
        self.assertIn('id="letter"', page)
        self.assertIn('id="signed"', page)
        with open(os.path.join(STATIC, "marchlands.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("ct.coalition", js)

    def test_the_page_shows_the_reasons_rather_than_the_mood(self):
        import os
        from marchlands.web import STATIC
        with open(os.path.join(STATIC, "marchlands.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("state.court", js)
        self.assertIn("why-list", js)
        with open(os.path.join(STATIC, "marchlands.css"), encoding="utf-8") as fh:
            self.assertIn(".why-list", fh.read())
