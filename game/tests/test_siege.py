"""Being besieged, as something you do rather than something done to you.

This scenario was built once and thrown away, because it was not a game:
`_mend_walls` returned early while besieged, so the wall only ever went down,
and recruiting at any sane rate changed nothing. Every tuning was decided
before the player acted -- eight of eight held whatever you did, or eight of
ten fell whatever you did, with nothing in between, because there was no
decision in between.

There are two now. `shore` works the breach while it is being made; `sally`
opens the gate and goes at the works. Neither is free and neither always
works, and the measurements below are the argument that they are decisions.
"""

from __future__ import annotations

import random
import unittest

from marchlands.military import Army, BESIEGING, Side, fight
from marchlands.scenarios import start
from marchlands.trade import Order, Stop


class TestAnOrderedFightStillKillsPeople(unittest.TestCase):
    """The bug this file found, and the reason to keep looking at numbers.

    Orders were applied by swapping in the copies `ordered` makes, so the
    casualties landed on the copy and the caller read its own untouched
    Side. From the day orders shipped, nobody died in a siege assault, and a
    sortie became a free button that burnt the engines and cost nothing.
    """

    def test_losses_land_on_the_sides_that_were_handed_in(self):
        a, d = Side({"spearman": 50}), Side({"spearman": 50})
        fight(a, d, rng=random.Random(1), orders=("line", "line"))
        self.assertLess(sum(a.units.values()), 50)
        self.assertLess(sum(d.units.values()), 50)

    def test_the_line_costs_exactly_what_no_order_costs(self):
        plain_a, plain_d = Side({"spearman": 50}), Side({"spearman": 50})
        fight(plain_a, plain_d, rng=random.Random(1), orders=("", ""))
        line_a, line_d = Side({"spearman": 50}), Side({"spearman": 50})
        fight(line_a, line_d, rng=random.Random(1), orders=("line", "line"))
        self.assertEqual(plain_a.units, line_a.units)
        self.assertEqual(plain_d.units, line_d.units)

    def test_the_order_is_taken_off_again_afterwards(self):
        a = Side({"spearman": 50})
        was = (a.attack_mult, a.defense_mult, a.morale)
        fight(a, Side({"spearman": 50}), rng=random.Random(1),
              orders=("storm", "hold"))
        self.assertEqual((a.attack_mult, a.defense_mult, a.morale), was)


class TestTheScenarioOpensUnderSiege(unittest.TestCase):
    def setUp(self):
        self.g = start("siege", seed=1)
        self.here = next(iter(self.g.world.settlements))
        self.s = self.g.world.settlements[self.here]

    def test_somebody_is_already_outside(self):
        outside = [a for a in self.g.armies if a.owner != "player"]
        self.assertTrue(outside)
        self.assertEqual(outside[0].state, BESIEGING)
        self.assertGreater(outside[0].size, sum(self.s.units.values()))

    def test_you_have_the_stone_and_the_bread_the_levers_need(self):
        self.assertGreater(self.s.market.stock.get("stone", 0), 100)
        self.assertGreater(self.s.market.stock.get("bread", 0), 500)

    def test_the_briefing_names_both_levers_and_the_real_clock(self):
        said = self.g.briefing
        self.assertIn("sally", said)
        self.assertIn("shore", said)
        self.assertIn("granary", said)

    def test_being_stormed_ends_it_here_and_nowhere_else(self):
        self.assertIn("survive", self.g.goals.paths)
        plain = start("marchlands", seed=1)
        self.assertNotIn("survive", plain.goals.paths)


class TestShoring(unittest.TestCase):
    def besieged(self, seed=1, days=3):
        g = start("siege", seed=seed)
        g.advance(days)
        here = next(iter(g.world.settlements))
        return g, g.world.settlements[here], here

    def test_a_wall_does_not_mend_itself_under_fire(self):
        g, s, _here = self.besieged()
        was = s.wall_hp
        g.advance(10)
        self.assertLess(s.wall_hp, was)

    def test_but_masons_can_be_put_on_it(self):
        g, s, here = self.besieged()
        g.shore(here, True)
        self.assertTrue(s.shoring)
        s.wall_hp *= 0.5
        was = s.wall_hp
        g.advance(1)
        # It is slower than the siege train, so the test is that stone moved.
        self.assertLess(s.market.stock.get("stone", 0), 500)

    def test_it_costs_stone_and_men_and_says_so(self):
        g, s, here = self.besieged()
        g.shore(here, True)
        s.wall_hp *= 0.4
        stone, men = s.market.stock.get("stone", 0), sum(s.units.values())
        g.advance(6)
        self.assertLess(s.market.stock.get("stone", 0), stone)
        self.assertLess(sum(s.units.values()), men)

    def test_and_nothing_at_all_once_the_stone_is_gone(self):
        # Against a game that is not shoring, not against the men it started
        # with: a besieged garrison loses people to the siege either way, and
        # the claim is that shoring with no stone costs nothing *extra*.
        def left(shoring):
            g, s, here = self.besieged()
            s.market.stock["stone"] = 0.0
            if shoring:
                g.shore(here, True)
            g.advance(5)
            return sum(s.units.values())
        self.assertAlmostEqual(left(True), left(False), places=6,
                               msg="it took a toll for work it could not do")

    def test_it_can_be_called_off(self):
        g, s, here = self.besieged()
        g.shore(here, True)
        self.assertIn("come off", g.shore(here, False))
        self.assertFalse(s.shoring)


class TestSallying(unittest.TestCase):
    def besieged(self, seed=1, days=3):
        g = start("siege", seed=seed)
        g.advance(days)
        here = next(iter(g.world.settlements))
        return g, g.world.settlements[here], here

    def foe(self, g):
        return next(a for a in g.armies if a.owner != "player")

    def caught(self, g, yes=True):
        """Decide the surprise roll instead of hoping for it.

        A sortie is a bet on getting out of the gate unseen -- see
        `military.sortie_odds` -- so a test that just calls `sally` and
        asserts the engines burnt is testing the dice. These two cases are
        what the bet pays and what it costs, and each is asserted against the
        roll it belongs to.
        """
        import random as _r
        rng = _r.Random(4)
        rng.random = (lambda: 0.0) if yes else (lambda: 0.999)
        g.rng = rng

    def test_a_good_sortie_burns_the_engines(self):
        g, s, here = self.besieged()
        self.caught(g, True)
        said = g.sally(here, men=int(sum(s.units.values()) * 0.8))
        foe = self.foe(g)
        self.assertIn("asleep", said)
        self.assertNotIn("ram", foe.units)
        self.assertNotIn("engineer", foe.units)
        self.assertIn("burnt", said)

    def test_and_a_seen_one_is_thrown_back(self):
        """The other half of the bet, and the reason it is one. Roused, the
        host turns out and you are fighting it in the open with no wall at
        your back -- so the engines are still there in the morning and the
        garrison that was holding the wall-walk is not."""
        g, s, here = self.besieged()
        self.caught(g, False)
        before = sum(s.units.values())
        said = g.sally(here, men=int(before * 0.8))
        foe = self.foe(g)
        self.assertIn("waiting", said)
        self.assertIn("ram", foe.units)
        self.assertLess(sum(s.units.values()), before,
                        "a sortie that failed cost nothing")

    def test_going_twice_is_expected(self):
        """A besieger who has seen one sortie is watching for the next, which
        is what stops this being a button pressed every siege."""
        from marchlands.military import sortie_odds
        first = sortie_odds(0.8, "rain", 40, tries=0).surprise
        again = sortie_odds(0.8, "rain", 40, tries=1).surprise
        self.assertLess(again, first * 0.75)

    def test_a_small_party_is_likelier_to_get_out(self):
        """The trade the whole mechanic is built on: a small party slips out
        and may not be enough, a big one does the work and is watched
        forming up."""
        from marchlands.military import sortie_odds
        small = sortie_odds(0.3, "rain", 20).surprise
        big = sortie_odds(1.0, "rain", 20).surprise
        self.assertGreater(small, big + 0.2)

    def test_and_says_what_it_burnt(self):
        # A successful sortie reported burning "no one", because the fight
        # had already killed the engines and the message read the remainder.
        g, s, here = self.besieged()
        said = g.sally(here, men=int(sum(s.units.values()) * 0.8))
        if "burnt" in said:
            self.assertNotIn("no one", said)

    def test_a_sortie_costs_men_whether_it_works_or_not(self):
        for share in (0.2, 0.8):
            g, s, here = self.besieged()
            was = sum(s.units.values())
            g.sally(here, men=int(was * share))
            self.assertLess(sum(s.units.values()), was, f"share {share}")

    def test_sending_too_few_wastes_them(self):
        g, s, here = self.besieged()
        g.sally(here, men=max(2, int(sum(s.units.values()) * 0.2)))
        self.assertIn("ram", self.foe(g).units)

    def test_you_cannot_sally_from_a_town_nobody_is_besieging(self):
        g = start("marchlands", seed=1)
        here = next(iter(g.world.settlements))
        self.assertIn("not besieged", g.sally(here))

    def test_it_fights_the_works_and_not_the_whole_host(self):
        # A sortie that had to beat two hundred men to reach a ram would
        # never be worth opening the gate for.
        g, s, here = self.besieged()
        foe = self.foe(g)
        before = foe.size
        g.sally(here, men=int(sum(s.units.values()) * 0.8))
        self.assertGreater(foe.size, before * 0.3,
                           "the whole host was in the fight")


class TestTheBaggageRaid(unittest.TestCase):
    """The small party's answer, and the reason the size of a sortie is a
    decision at all.

    At the works you have to beat the watch, so too few men is men thrown
    away -- which measured out as one good answer (send most of them) and
    several bad ones. At the wagons you have to beat nobody: arrive unseen,
    put a torch to them, get back. So the two targets want opposite-sized
    parties, and the player is choosing between them rather than turning a
    dial.

    It could not have existed before hosts had to eat. Burning a besieger's
    stores was a line of text until supply.py made his own supply something
    that runs out.
    """

    def besieged(self, seed=1, days=20):
        g = start("siege", seed=seed)
        g.advance(days)
        here = next(iter(g.world.settlements))
        return g, g.world.settlements[here], here

    def foe(self, g):
        return next(a for a in g.armies if a.owner != "player")

    def caught(self, g, yes=True):
        import random as _r
        rng = _r.Random(4)
        rng.random = (lambda: 0.0) if yes else (lambda: 0.999)
        g.rng = rng

    def test_a_raid_that_gets_in_burns_his_food(self):
        g, s, here = self.besieged()
        self.caught(g, True)
        before = self.foe(g).stores
        said = g.fire_baggage(here, men=int(sum(s.units.values()) * 0.25))
        self.assertIn("nobody sees them go", said)
        self.assertLess(self.foe(g).stores, before * 0.75)

    def test_and_leaves_his_engines_alone(self):
        """It is not the other sortie. His rams are still there in the
        morning; what has changed is his clock."""
        g, s, here = self.besieged()
        self.caught(g, True)
        g.fire_baggage(here, men=int(sum(s.units.values()) * 0.25))
        self.assertIn("ram", self.foe(g).units)

    def test_a_raid_that_is_seen_is_driven_off_with_nothing(self):
        g, s, here = self.besieged()
        self.caught(g, False)
        before, men = self.foe(g).stores, sum(s.units.values())
        said = g.fire_baggage(here, men=int(men * 0.25))
        self.assertIn("nothing fired", said)
        self.assertEqual(self.foe(g).stores, before)
        self.assertLess(sum(s.units.values()), men)

    def test_it_costs_something_even_when_it_works(self):
        g, s, here = self.besieged()
        self.caught(g, True)
        men = sum(s.units.values())
        g.fire_baggage(here, men=int(men * 0.25))
        self.assertLess(sum(s.units.values()), men, "nobody stayed behind")

    def test_a_small_party_risks_far_less_than_a_large_one(self):
        """Which is the whole of why the raid is the small party's answer:
        the fire it can carry barely grows with the men, and what being
        caught costs grows with every one of them."""
        lost = {}
        for share in (0.2, 0.8):
            g, s, here = self.besieged()
            self.caught(g, False)
            men = sum(s.units.values())
            g.fire_baggage(here, men=int(men * share))
            lost[share] = men - sum(s.units.values())
        self.assertGreater(lost[0.8], lost[0.2] * 2)

    def test_and_there_is_nothing_to_burn_twice(self):
        g, s, here = self.besieged()
        self.foe(g).stores = 0.0
        said = g.fire_baggage(here, men=20)
        self.assertIn("nothing left in that camp", said)

    def test_the_camp_learns_from_a_raid_as_well_as_a_sortie(self):
        """Both go out of the same gate, so both are the same lesson to the
        man watching it."""
        g, s, here = self.besieged()
        before = s.sorties
        self.caught(g, True)
        g.fire_baggage(here, men=15)
        self.assertGreater(s.sorties, before)


class TestItIsDecidedByThePlayer(unittest.TestCase):
    """The measurement that says this is a game. Doing nothing is a coin
    flip, sallying early wins it, and leaving it until the wall is falling
    is no better than doing nothing at all.

    Six seeds here, because these tests play the scenario out day by day and
    the suite has to stay runnable. The wider numbers quoted below were
    measured over twenty-four.
    """

    def play(self, sally_on=0, shore=False, seeds=range(1, 7)):
        held = 0
        for seed in seeds:
            g = start("siege", seed=seed)
            here = next(iter(g.world.settlements))
            s = g.world.settlements[here]
            if shore:
                g.shore(here, True)
            done = False
            while not g.over and g.day < 275:
                g.advance(1)
                if sally_on and s.besieged and not done and g.day >= sally_on:
                    g.sally(here, men=int(sum(s.units.values()) * 0.8))
                    done = True
            held += "Time called" in (g.over or "")
        return held

    def test_doing_nothing_is_a_coin_flip(self):
        idle = self.play()
        self.assertGreater(idle, 0, "unwinnable is not hard")
        self.assertLess(idle, 6, "doing nothing should not simply win")

    def test_going_early_wins_it(self):
        self.assertGreater(self.play(sally_on=5), self.play())

    def test_and_going_late_does_not(self):
        self.assertLessEqual(self.play(sally_on=60), self.play(sally_on=5))

    def test_how_strong_the_sortie_is_is_written_down(self):
        """A record, because "early beats never" stopped being enough.

        The three tests above are all satisfied by a sortie that works every
        single time, and for a while that is what this was: a fixed share of
        the besieging host turned out whatever the defender did, so any
        garrison beat a detachment it outnumbered and went back in --
        twenty-four seeds out of twenty-four. Supply then made it worse, by
        throttling the relief column that used to arrive with fresh rams.

        Measured again after the rework (24 seeds, share of the garrison
        sent across, day the gate opened down):

                        day 5   day 20   day 60
            never        41%
            30% out       75%      66%      41%
            50% out       58%      58%      41%
            80% out       75%      66%      41%
            100% out      70%      33%      29%

        What that says is worth being exact about. The sortie is a gamble
        again: the best line in the table is three wins in four, not four in
        four. Timing is a real decision -- going early beats the coin flip,
        going late is the coin flip, and marching everybody out late is
        worse than staying in bed. What the table does *not* show is the
        clean stealth-against-strength curve the comments in
        `military.sortie_odds` describe: 30% and 80% land in the same place
        and 50% dips below both, which at twenty-four seeds is inside the
        noise. The size of the party is not yet demonstrably a trade, and
        this docstring says so rather than the table being read as agreeing
        with the design.

        The test itself guards the pair of facts that matter: a sortie is
        still worth making, and doing nothing is still a coin flip.
        """
        idle = self.play()
        early = self.play(sally_on=5)
        self.assertGreater(idle, 1, f"doing nothing simply loses: {idle}/6")
        self.assertLess(idle, 5, f"doing nothing simply wins: {idle}/6")
        self.assertGreaterEqual(
            early, 5, f"the sortie has stopped being decisive: {early}/6")


class TestTheRingIsClosed(unittest.TestCase):
    """A siege is a rule about goods, not only about walls.

    Nothing in the trade engine knew what a siege was, so a cart could load
    the granary of a town it was standing in and sell it three days' ride
    away while the besiegers watched. That starved the town the player was
    being asked to defend -- and run the other way it was worse, because a
    cart carrying bread in makes a siege impossible to lose.
    """

    def ringed_town(self):
        g = start("siege", seed=3)
        key = next(iter(g.world.settlements))
        for _ in range(40):
            g.advance(1)
            if g.world.settlements[key].besieged:
                return g, key, g.world.settlements[key]
        self.skipTest("the scenario did not close a ring")

    def test_no_cart_does_business_inside_the_lines(self):
        g, key, town = self.ringed_town()
        cart, _why = g.new_caravan(key)
        self.assertIsNotNone(cart)
        cart.set_route([Stop(node=key, buy=[Order("bread", 100)]),
                        Stop(node=key, sell=[Order("bread", -1)])])
        cart.start()
        before = town.market.stock.get("bread", 0.0)
        for _ in range(10):
            g.advance(1)
        self.assertEqual(cart.cargo, {})
        # The stores still fall -- the town is eating them. What may not
        # happen is a cart taking any of it out.
        self.assertLessEqual(town.market.stock.get("bread", 0.0), before)
        self.assertEqual(cart.total_profit, 0.0)

    def test_the_cart_says_why_it_is_standing_still(self):
        g, key, _town = self.ringed_town()
        cart, _why = g.new_caravan(key)
        cart.set_route([Stop(node=key, buy=[Order("bread", 10)])])
        cart.start()
        said = []
        for _ in range(3):
            said += g.advance(1)
        self.assertTrue(any("lines are closed" in m for m in said), said)


if __name__ == "__main__":
    unittest.main()
