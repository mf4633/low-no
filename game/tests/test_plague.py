"""The sickness, and the roads it comes down.

Every other bad thing in this game arrives because somebody sent it, and
you can watch it cross the map. This one comes down the roads the player
built, on the carts he is making his money with -- which is the whole
reason it is worth having: it makes the trade network a liability as well
as an asset, without a second map or a second economy.
"""

from __future__ import annotations

import random
import unittest

from marchlands import plague
from marchlands.engine import GameState
from marchlands.scenarios import start
from marchlands.sim import Bot


class TestTheSicknessItself(unittest.TestCase):
    def test_it_has_an_end_written_into_it(self):
        """A sickness that never goes out is a permanent tax, and a
        permanent tax is not an event."""
        r = random.Random(1)
        for _ in range(40):
            s = plague.takes_hold(10, r)
            self.assertGreater(s.until, 10)
            self.assertLess(s.until - 10, plague.LIFE + plague.LIFE_SPREAD)

    def test_and_no_two_towns_are_ill_on_the_same_schedule(self):
        r = random.Random(1)
        lives = {plague.takes_hold(0, r).until for _ in range(30)}
        self.assertGreater(len(lives), 5)

    def test_crowding_kills(self):
        """The same reading that already drives the mood."""
        roomy = plague.toll(200, 200)
        packed = plague.toll(200, 100)
        self.assertGreater(packed, roomy)

    def test_a_season_of_it_costs_a_town_a_real_share_of_itself(self):
        people = 200.0
        for _ in range(plague.LIFE):
            people -= plague.toll(people, 200.0)
        lost = 1.0 - people / 200.0
        # About a fifth, measured. The upper bound is the one that matters:
        # past roughly half, a town in this game stops recovering at all --
        # see the note on TOLL.
        self.assertGreater(lost, 0.15, f"only {lost:.0%} -- not worth a lever")
        self.assertLess(lost, 0.45, f"{lost:.0%} -- no town comes back from that")


class TestItTravelsOnTraffic(unittest.TestCase):
    """Not by distance. A town nobody trades with is a town it never
    reaches, however close; a hub with six routes into it is the likeliest
    place on the march to be ill."""

    def sick_neighbour(self, seed=2):
        g = start("marchlands", seed=seed)
        town = next(iter(g.world.towns.values()))
        town.sick = plague.takes_hold(g.day, g.rng)
        return g, town

    def test_a_cart_that_traded_somewhere_ill_can_bring_it_home(self):
        g, town = self.sick_neighbour()
        home = next(iter(g.world.settlements))
        cart, _why = g.new_caravan(home)
        cart.carrying_it = town.key
        cart.at = home
        g.advance(1)
        self.assertTrue(g.world.settlements[home].sick.here,
                        "the cart came home and nothing happened")

    def test_a_cart_still_on_the_road_keeps_carrying_it(self):
        """Cleared wherever the cart happened to be on the first morning,
        a cart on a foreign circuit dropped the sickness in the mud between
        two towns and nobody ever caught anything."""
        g, town = self.sick_neighbour()
        home = next(iter(g.world.settlements))
        cart, _why = g.new_caravan(home)
        cart.carrying_it = town.key
        cart.at = ""
        cart.bound_for = town.key
        g.advance(1)
        self.assertEqual(cart.carrying_it, town.key)

    def test_a_shut_gate_turns_it_away(self):
        g, town = self.sick_neighbour()
        home = next(iter(g.world.settlements))
        g.shut_gates(home, True)
        cart, _why = g.new_caravan(home)
        cart.carrying_it = town.key
        cart.at = home
        g.advance(1)
        self.assertFalse(g.world.settlements[home].sick.here)

    def test_and_a_shut_gate_stops_the_carts_too(self):
        """Which is the price, and the reason it is a decision. A lever
        with a cost is a decision; one without is a button."""
        from marchlands.trade import Order, Stop
        g, town = self.sick_neighbour()
        home = next(iter(g.world.settlements))
        cart, _why = g.new_caravan(home)
        cart.at = home
        # A cart actually on a route, which is the only kind a gate can
        # stop: one with nowhere to go was never going anywhere.
        cart.set_route([Stop(node=home, buy=[Order("bread", 20)]),
                        Stop(node=town.key, sell=[Order("bread", -1)])])
        cart.start()
        g.shut_gates(home, True)
        said = []
        for _ in range(4):
            said += g.advance(1)
        self.assertTrue(cart.stalled, "a cart left a town with shut gates")
        self.assertTrue(any("gates are shut" in m for m in said), said)

    def test_a_sick_market_still_trades(self):
        """Made to shut its own gates at first, which is what they did and
        is self-defeating here: a market nobody can trade in is a market
        nobody can catch anything at, so it could never leave the town it
        started in. News travels slower than carts -- that is why it
        spread."""
        g, town = self.sick_neighbour()
        home = next(iter(g.world.settlements))
        self.assertTrue(town.sick.here)
        cart, _why = g.new_caravan(home)
        cart.at = town.key
        for _ in range(3):
            g.advance(1)
        self.assertFalse(cart.stalled)

    def test_a_town_does_not_catch_it_twice_in_a_season(self):
        """Without this a hub reinfects itself off its own carts for ever
        and the sickness is a climate rather than an event."""
        g, town = self.sick_neighbour()
        home = next(iter(g.world.settlements))
        place = g.world.settlements[home]
        place.last_sick = g.day - 5
        cart, _why = g.new_caravan(home)
        cart.carrying_it = town.key
        cart.at = home
        g.advance(1)
        self.assertFalse(place.sick.here)


class TestWhatItDoesToATown(unittest.TestCase):
    def ill(self, days=30):
        g = start("marchlands", seed=3)
        s = g.world.settlements["aldworth"]
        s.sick = plague.takes_hold(g.day, g.rng)
        before = s.population
        for _ in range(days):
            g.advance(1)
        return g, s, before

    def test_it_buries_people(self):
        _g, s, before = self.ill()
        self.assertLess(s.population, before)
        self.assertGreater(s.sick.dead, 0)

    def test_it_takes_hands_off_the_work(self):
        _g, s, _before = self.ill(days=5)
        self.assertGreater(s.plague_labour, 0)

    def test_it_is_in_the_mood(self):
        g, s, _before = self.ill(days=5)
        self.assertIn("the sickness", [k for k, _v in s.mood_factors(g.progress)])

    def test_and_shutting_the_gates_is_felt_as_well(self):
        g = start("marchlands", seed=3)
        s = g.world.settlements["aldworth"]
        g.shut_gates("aldworth", True)
        g.advance(1)
        self.assertIn("the gates are shut",
                      [k for k, _v in s.mood_factors(g.progress)])

    def test_it_goes_out_and_says_what_it_took(self):
        g = start("marchlands", seed=3)
        s = g.world.settlements["aldworth"]
        s.sick = plague.takes_hold(g.day, g.rng)
        said = []
        for _ in range(plague.LIFE + plague.LIFE_SPREAD + 2):
            said += g.advance(1)
        self.assertFalse(s.sick.here)
        self.assertGreater(s.buried, 0, "it went out having killed nobody")
        self.assertTrue(any("gone out" in m and "took" in m for m in said),
                        "nobody was told what it cost")

    def test_the_toll_is_not_lost_when_the_sickness_is(self):
        """Read off `sick.dead` after it ended, every outbreak in the game
        reported as having killed nobody."""
        g = start("marchlands", seed=3)
        s = g.world.settlements["aldworth"]
        s.sick = plague.takes_hold(g.day, g.rng)
        for _ in range(plague.LIFE + plague.LIFE_SPREAD + 2):
            g.advance(1)
        self.assertEqual(s.sick.dead, 0.0)
        self.assertGreater(s.buried, 0.0)


class TestWhatYouAreAllowedToKnow(unittest.TestCase):
    def test_word_comes_off_the_same_fog_as_everything_else(self):
        """A town you have never sent anybody to could be burying half its
        people and you would not know. That is what makes shutting the
        gates a bet rather than a lookup."""
        g = start("marchlands", seed=3)
        for t in g.world.towns.values():
            t.sick = plague.takes_hold(g.day, g.rng)
            t.seen_day = -999
        self.assertEqual(g.word_of_sickness(), [])

    def test_and_stale_word_stops_counting(self):
        g = start("marchlands", seed=3)
        t = next(iter(g.world.towns.values()))
        t.sick = plague.takes_hold(g.day, g.rng)
        t.seen_day = g.day
        self.assertTrue(g.word_of_sickness())
        t.seen_day = g.day - (g.WORD_KEEPS + 5)
        self.assertEqual(g.word_of_sickness(), [])

    def test_fresh_word_is_marked_as_fresh(self):
        g = start("marchlands", seed=3)
        t = next(iter(g.world.towns.values()))
        t.sick = plague.takes_hold(g.day, g.rng)
        t.seen_day = g.day
        self.assertTrue(g.word_of_sickness()[0]["sure"])


class TestATownComesBack(unittest.TestCase):
    """The cliff under all of this, which was not the sickness's.

    Soldiers come off the working population -- the note at the top of
    settlement.py -- and a garrison raised for a big town did not shrink
    when the town did. A town of 216 souls with 79 under arms has 39 hands
    left; halve the town and the same 79 leaves it *zero*. Nothing was
    produced, the granary emptied, hunger pinned at 1.00, and it starved to
    four souls over the following year, with nothing anywhere saying that
    the reason nobody was farming was the garrison.

    Nothing about that was particular to the sickness. A war, a famine or a
    bad raid would have found it in exactly the same way, and the only
    reason it had not been found is that nothing before this took half a
    town at once.
    """

    def gutted(self, share=0.45):
        g = start("marchlands", seed=3)
        bot = Bot(g)
        s = g.world.settlements["aldworth"]
        for _ in range(400):
            bot.step()
            g.tick()
        s.population *= share
        return g, bot, s

    def test_a_garrison_never_eats_the_whole_workforce(self):
        # From the next morning: the men are stood down in the town's own
        # tick, so the instant after half of it dies there is indeed nobody
        # in the fields. A day of that is a disaster; a year of it was the
        # bug.
        g, bot, s = self.gutted()
        bot.step()
        g.tick()
        self.assertGreater(s.workforce, 0,
                           "nobody is left to reap and nothing says why")

    def test_the_men_go_back_to_the_fields_and_it_says_so(self):
        g, bot, s = self.gutted()
        before = s.soldiers
        said = []
        for _ in range(2):
            bot.step()
            said += g.tick()
        self.assertLess(s.soldiers, before)
        self.assertTrue(any("back to the fields" in m for m in said), said)

    def test_and_the_town_recovers(self):
        g, bot, s = self.gutted()
        low = s.population
        for _ in range(240):
            bot.step()
            g.tick()
        self.assertGreater(s.population, low * 1.5,
                           f"{low:.0f} souls went to {s.population:.0f}")
        self.assertEqual(s.report.hunger, 0.0)

    def test_the_garrison_comes_back_with_the_people(self):
        """Standing men down is not disbanding the army: as the town grows
        it can keep them again."""
        g, bot, s = self.gutted()
        for _ in range(3):
            bot.step()
            g.tick()
        thin = s.soldiers
        for _ in range(240):
            bot.step()
            g.tick()
        self.assertGreater(s.soldiers, thin)

    def test_the_sickness_does_not_spare_the_wall(self):
        """A sickness that took only civilians would leave a town of nobody
        defended by a garrison of everybody."""
        g = start("marchlands", seed=3)
        s = g.world.settlements["aldworth"]
        s.units = {"spearman": 20}
        s.population = 300.0
        s.sick = plague.takes_hold(g.day, g.pest)
        for _ in range(30):
            g.advance(1)
        self.assertLess(s.soldiers, 20)


class TestItSurvivesASave(unittest.TestCase):
    def test_everything_the_sickness_keeps(self):
        g = start("marchlands", seed=3)
        s = g.world.settlements["aldworth"]
        s.sick = plague.takes_hold(g.day, g.rng)
        s.shut = True
        s.buried = 12.0
        s.last_sick = 44
        t = next(iter(g.world.towns.values()))
        t.sick = plague.takes_hold(g.day, g.rng)
        again = GameState.from_dict(g.to_dict())
        back = again.world.settlements["aldworth"]
        self.assertEqual(back.sick.until, s.sick.until)
        self.assertTrue(back.shut)
        self.assertEqual(back.buried, 12.0)
        self.assertEqual(back.last_sick, 44)
        self.assertTrue(next(iter(again.world.towns.values())).sick.here)


class TestItIsWorthHaving(unittest.TestCase):
    def test_doing_nothing_about_it_costs_a_town(self):
        """Measured over a long game rather than asserted.

        The outbreak is put in the neighbouring market by hand rather than
        waited for. Written the other way round this asked the world to
        roll a plague inside seven hundred days on one seed, and when the
        sickness got its own RNG stream -- as every subsystem here must --
        that seed stopped rolling one and the test reported that the
        sickness costs nothing. What is under test is the lever, not the
        dice.
        """
        def play(shut: bool):
            g = start("marchlands", seed=2)
            bot = Bot(g)
            if not shut:
                # The bot shuts its own gates now, so a run that did not
                # take the policy off it was comparing the policy with
                # itself and reporting that the sickness costs nothing.
                bot._shut_out = lambda: None
            s = g.world.settlements["aldworth"]
            for day in range(700):
                bot.step()
                g.tick()
                if day == 40:
                    # Every market abroad, so the bot's own routes are
                    # certain to touch one. Seeding a single neighbour meant
                    # picking a town the bot might never trade with, and the
                    # test then reported that the sickness costs nothing
                    # when what it had measured was a road nobody uses.
                    for t in g.world.towns.values():
                        t.sick = plague.takes_hold(g.day, g.pest)
                if g.over:
                    break
            return s.buried, s.population

        loose_dead, loose_left = play(False)
        shut_dead, shut_left = play(True)
        self.assertGreater(loose_dead, 20,
                           "the sickness never reached a town trading with it")
        self.assertLess(shut_dead, loose_dead, "shutting the gates bought nothing")
        self.assertGreater(shut_left, loose_left)


if __name__ == "__main__":
    unittest.main()
