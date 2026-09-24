"""What was borrowed from the games that did it first.

Stronghold's stepped coverage, 0 A.D.'s back-off from work that cannot be
done, Warband's peddlers, siege hardness, starving garrisons and patient
lords, EU4's trust, war score, kinship and liberty, Freeciv's reasons for a
war. Each one here is a test that the mechanism is real, not a promise.
"""
import random
import unittest

from marchlands import chancery, web
from marchlands.engine import GameState
from marchlands.military import Army, BESIEGING, MARCHING
from marchlands.scenarios import start
from marchlands.settlement import stepped


def game(seed=3):
    return start("marchlands", seed=seed)


def home(g):
    return next(iter(g.world.settlements.values()))


def a_shed_with_inputs(s):
    """A finished shed that needs something brought to it, raised if the
    town has none yet."""
    from marchlands.buildings import BUILDINGS
    from marchlands.settlement import BuildingInstance
    got = next((b for b in s.buildings if b.complete and b.spec.jobs
                and b.spec.inputs), None)
    if got is not None:
        return got
    key = next(k for k, b in BUILDINGS.items() if b.jobs and b.inputs)
    got = BuildingInstance(uid=s.next_uid, key=key, days_left=0)
    s.next_uid += 1
    s.buildings.append(got)
    return got


# ------------------------------------------------------------------ the town
class TestTheTown(unittest.TestCase):
    def test_coverage_is_paid_in_quarters(self):
        self.assertEqual(stepped(0.24), 0.0)
        self.assertEqual(stepped(0.25), 0.25)
        self.assertEqual(stepped(0.74), 0.5)
        self.assertEqual(stepped(1.3), 1.0)

    def test_a_shed_that_cannot_work_gets_no_hands(self):
        g = game()
        s = home(g)
        shed = a_shed_with_inputs(s)
        for k in shed.spec.inputs:
            s.market.stock[k] = 0.0
        shed.dry_days = s.DRY_DAYS
        s._seat_hands()
        self.assertEqual(shed.staffed, 0)
        self.assertTrue(shed.idle_reason.startswith("no "))

    def test_a_pinned_shed_is_still_seated_whatever_it_lacks(self):
        g = game()
        s = home(g)
        shed = a_shed_with_inputs(s)
        for k in shed.spec.inputs:
            s.market.stock[k] = 0.0
        shed.dry_days = s.DRY_DAYS
        s.pin_hands(shed.uid, shed.spec.jobs)
        self.assertGreater(shed.staffed, 0, "your order stands")

    def test_twin_sheds_share_rather_than_one_filling_first(self):
        g = game()
        s = home(g)
        by_key = {}
        for b in s.buildings:
            if b.complete and b.spec.jobs > 1 and not b.spec.inputs:
                by_key.setdefault(b.key, []).append(b)
        twins = next((v for v in by_key.values() if len(v) >= 2), None)
        if twins is None:
            self.skipTest("no twin sheds in this town")
        s.units = {}
        for b in s.buildings:
            if b not in twins:
                b.enabled = False
        s.population = 2.0
        while s.workforce < twins[0].spec.jobs:
            s.population += 1.0
        s._seat_hands()
        seated = [b.staffed for b in twins]
        self.assertLessEqual(max(seated) - min(seated), 1, seated)


# --------------------------------------------------------------- the economy
class TestTheEconomy(unittest.TestCase):
    def test_peddlers_carry_surplus_to_a_dearer_neighbour(self):
        g = game()
        w = g.world
        a, b = next((a, b) for a, b in w.roads() if a in w.towns and b in w.towns)
        ta, tb = w.towns[a], w.towns[b]
        k = next(k for k in ta.market.stock if ta.market.sells(k) and tb.market.sells(k))
        ta.market.stock[k] = ta.market.target[k] * 4
        tb.market.stock[k] = max(1.0, tb.market.target[k] * 0.2)
        ta.market.settle_day(); tb.market.settle_day()
        for _ in range(30):
            ta.market.settle_day(); tb.market.settle_day()
        before = tb.market.stock[k]
        w.peddle()
        self.assertGreater(tb.market.stock[k], before)
        w2 = GameState.from_dict(g.to_dict()).world
        stock = w2.towns[b].market.stock[k]
        w2.peddle(closed={b})
        self.assertEqual(w2.towns[b].market.stock[k], stock, "a ringed town trades with nobody")

    def test_a_siege_cuts_a_towns_food(self):
        g = game()
        from marchlands.goods import good
        t, food = next((t, k) for t in g.world.towns.values()
                       for k, v in t.flow.items() if v > 0 and good(k).nourish > 0)
        t2 = GameState.from_dict(g.to_dict()).world.towns[t.key]
        t.tick(random.Random(1))
        t2.tick(random.Random(1), besieged=True)
        self.assertLess(t2.market.stock[food], t.market.stock[food])

    def test_prosperity_drifts_toward_what_trade_will_bear(self):
        g = game()
        t = next(iter(g.world.towns.values()))
        t.prosperity = 2.2
        ideal = t.ideal_prosperity()
        for d in range(50):
            t.grow(random.Random(d), day=d)
        if ideal < 2.2:
            self.assertLess(t.prosperity, 2.2)
        self.assertGreaterEqual(t.prosperity, 0.4)


# ------------------------------------------------------------------- the war
class TestTheWar(unittest.TestCase):
    def test_a_repulse_hardens_the_wall_and_it_wears_off(self):
        g = game()
        t = next(iter(g.world.towns.values()))
        t.hardened = 100.0
        t.grow(random.Random(0), day=1)
        self.assertEqual(t.hardened, 98.0)
        t2 = GameState.from_dict(g.to_dict()).world.towns[t.key]
        self.assertEqual(t2.hardened, 98.0)

    def test_a_starving_garrison_thins(self):
        from marchlands.military import Side
        g = game()
        t = next(iter(g.world.towns.values()))
        for k in t.market.stock:
            t.market.stock[k] = 0.0
        holder = Side({"spearman": 100.0})
        g._starve_town(t, None, holder, player=False)
        self.assertLess(holder.units["spearman"], 100.0)

    def test_a_patient_lord_settles_for_less(self):
        g = game()
        key = next(iter(g.world.towns))
        strict = g._prey_for(key, 0.0)
        self.assertIsNone(strict, "nobody is weaker than nothing")
        loose = g._prey_for(key, 10.0)
        self.assertIsNotNone(loose)

    def test_a_lords_humour_holds_for_the_week(self):
        g = game()
        g.day = 14
        a = g._week_mood("dunmere", "temper")
        g.day = 20
        self.assertEqual(a, g._week_mood("dunmere", "temper"))
        g.day = 21
        self.assertNotEqual(a, g._week_mood("dunmere", "temper"))


# ----------------------------------------------------------- the diplomacy
class TestTheLetters(unittest.TestCase):
    def test_trust_is_apart_from_liking_and_only_allies_pass_eighty(self):
        c = chancery.Chancery()
        self.assertEqual(c.trust_of("x"), 50.0)
        c.shake("x", 60.0)
        self.assertEqual(c.trust_of("x"), 80.0)
        c.allies.append("x")
        c.shake("x", 10.0)
        self.assertEqual(c.trust_of("x"), 90.0)
        d = chancery.Chancery.from_dict(c.to_dict())
        self.assertEqual(d.trust_of("x"), 90.0)

    def test_an_alliance_wants_trust(self):
        g = game()
        key = next(iter(g.world.towns))
        g.court.trust[key] = 10.0
        self.assertIn("does not trust", g.ally(key))

    def test_the_war_prices_the_truce(self):
        g = game()
        key = next(iter(g.world.towns))
        even = g.truce_cost(key, 100)
        g.court.reckon(key, 60.0)
        self.assertLess(g.truce_cost(key, 100), even)
        g.court.score[key] = -60.0
        self.assertIn("winning", g.truce(key))

    def test_a_beaten_lord_sues_and_the_truce_is_free(self):
        g = game()
        key = next(iter(g.world.towns))
        g.court.score[key] = 80.0
        said = " ".join(g._peace_day())
        self.assertIn("sues for peace", said)
        g.treasury = 0.0
        self.assertIn("swears off", g.truce(key))

    def test_raiding_a_lord_is_written_down(self):
        g = game()
        key, t = next(iter(g.world.towns.items()))
        a = Army(uid=950, name="raiders", owner="player",
                 units={"knight": 30}, at=key)
        g.armies.append(a)
        g._raid_town(a, t)
        whys = [gr.why for gr in g.court.ledger.get(key, [])]
        self.assertIn("raided_them", whys)

    def test_the_opinion_reward_outlives_the_morning(self):
        g = game()
        before = {k: g.court.goodwill(k, g.day) for k in g.world.towns}
        class Mission:
            gives = ("opinion", 20.0)
        g._pay(Mission())
        g._chancery_day()           # the morning that used to wipe it
        after = {k: g.court.goodwill(k, g.day) for k in g.world.towns}
        self.assertTrue(all(after[k] > before[k] for k in before if not g.world.towns[k].mine))

    def test_a_fixture_says_why(self):
        g = game()
        t = next(iter(g.world.towns.values()))
        self.assertTrue(g._intent_reason(t, next(iter(g.world.settlements))))
        self.assertTrue(g._intent_reason(t, next(k for k in g.world.towns if k != t.key)))

    def test_a_sworn_town_wavers_when_you_are_weak(self):
        g = game()
        key, t = next(iter(g.world.towns.items()))
        t.owner = "player"
        t.loyalty = 50.5
        for s in g.world.settlements.values():
            s.units = {}
        said = ""
        for _ in range(10):
            said = said or g._loyalty_day(key, t)
        self.assertLess(t.loyalty, 50.0)
        self.assertIn("wavers", said)

    def test_a_lord_with_no_hall_has_no_host(self):
        g = game()
        keys = list(g.world.towns)
        loser, taker = keys[0], keys[1]
        stray = Army(uid=960, name="stray", owner=loser,
                     units={"spearman": 20}, at=loser, state=MARCHING,
                     bound_for=keys[2])
        winner = Army(uid=961, name="winner", owner=taker,
                      units={"spearman": 200}, at=loser, state=BESIEGING)
        g.armies += [stray, winner]
        g._take_town(g.world.towns[loser], winner)
        self.assertEqual(stray.owner, taker, "his men go over to the new hall")

    def test_an_ally_sends_men_when_you_are_attacked(self):
        g = game()
        key = next(iter(g.world.towns))
        g.court.allies.append(key)
        home_key = next(iter(g.world.settlements))
        foe = next(k for k in g.world.towns if k != key)
        g.armies.append(Army(uid=970, name="foe", owner=foe,
                             units={"spearman": 40}, at=foe, state=MARCHING,
                             bound_for=home_key, days_left=5))
        sent = []
        for d in range(200):
            g.day = d
            sent += g._aid_day()
            if sent:
                break
        self.assertTrue(sent, "no ally came in two hundred days")
        mine = [a for a in g.armies if a.owner == "player" and "men" in a.name]
        self.assertTrue(mine)
        self.assertEqual(mine[0].bound_for, home_key)


if __name__ == "__main__":
    unittest.main()


# ------------------------------------------------- the hands go where wanted
class TestDemand(unittest.TestCase):
    def test_a_good_the_town_is_short_of_is_wanted(self):
        g = game()
        s = home(g)
        k = next(iter(s.market.target))
        s.market.stock[k] = 0.0
        s._made_yesterday = {}
        self.assertEqual(s.demand()[k], 1.5, "short and nobody on it: first")
        s._made_yesterday = {k: 3.0}
        self.assertEqual(s.demand()[k], 1.0)
        s.market.stock[k] = s.market.target[k] * 5
        self.assertLess(s.demand()[k], 0)

    def test_short_hands_go_to_the_shed_whose_goods_are_wanted(self):
        from marchlands.buildings import BUILDINGS
        from marchlands.settlement import BuildingInstance
        g = game()
        s = home(g)
        a_key, b_key = [k for k, b in BUILDINGS.items()
                        if b.jobs and b.outputs and not b.inputs
                        and not b.season and not b.draws][:2]
        for b in s.buildings:
            b.enabled = False
        a = BuildingInstance(uid=s.next_uid, key=a_key, days_left=0)
        b = BuildingInstance(uid=s.next_uid + 1, key=b_key, days_left=0)
        s.next_uid += 2
        s.buildings += [a, b]
        for k in BUILDINGS[a_key].outputs:
            s.market.stock[k] = s.market.target[k] * 5      # plenty
        for k in BUILDINGS[b_key].outputs:
            s.market.stock[k] = 0.0                         # none at all
        s.units = {}
        s.population = 2.0
        while s.workforce < BUILDINGS[b_key].jobs:
            s.population += 1.0
        s._seat_hands()
        self.assertEqual(b.staffed, BUILDINGS[b_key].jobs)
        self.assertEqual(a.staffed, 0, "the older shed no longer goes first")
        self.assertIn("short", b.demand_note)


# ------------------------------------------------------ a war, weighed first
class TestWeighingAWar(unittest.TestCase):
    def test_every_reason_has_a_name_and_a_weight(self):
        g = game()
        key, t = next(iter(g.world.towns.items()))
        terms = g._war_terms(t, next(iter(g.world.settlements)), 1.0)
        self.assertTrue(all(isinstance(l, str) and l for l, _v in terms))
        self.assertIn("his temper is up", [l for l, _v in terms])

    def test_a_strong_wall_keeps_him_home_and_he_says_why(self):
        g = game()
        key, t = next(iter(g.world.towns.items()))
        s = home(g)
        s.units = {"man_at_arms": 400}
        t.hostility = 100.0
        said = g._reckon_war(key, t, 1.0)
        self.assertFalse(any(a.owner == key for a in g.armies))
        self.assertIn("holds back", said)
        self.assertLess(t.reckoned, g.DECLARE)
        self.assertTrue(t.reckoning)

    def test_a_weak_one_does_not(self):
        g = game()
        key, t = next(iter(g.world.towns.items()))
        home(g).units = {}
        home(g).wall_hp = 0.0
        t.chest = 1e6
        t.aggression = 2.0
        t.hostility = 100.0
        g._reckon_war(key, t, 2.0)
        self.assertTrue(any(a.owner == key for a in g.armies))

    def test_waiting_wears_his_caution_down(self):
        g = game()
        key, t = next(iter(g.world.towns.items()))
        dest = next(iter(g.world.settlements))
        before = sum(v for _l, v in g._war_terms(t, dest, 1.0))
        t.gathering = 60
        after = sum(v for _l, v in g._war_terms(t, dest, 1.0))
        self.assertAlmostEqual(after - before, 15.0)


# ------------------------------------------------------------ the lords' coin
class TestTheChest(unittest.TestCase):
    def test_a_host_is_bought_out_of_the_chest(self):
        g = game()
        key, t = next(iter(g.world.towns.items()))
        g._keep_the_chest(key, t)
        full = g._host_price(g._muster_enemy(t, 1.0, spread=False))
        t.chest = full * 0.5
        g._send_host(t, 1.0, next(k for k in g.world.towns if k != key))
        a = next(a for a in g.armies if a.owner == key)
        self.assertLess(g._host_price(a.units), full)
        self.assertLessEqual(t.chest, 1.0)

    def test_a_lord_in_debt_loses_men(self):
        g = game()
        key, t = next(iter(g.world.towns.items()))
        g._keep_the_chest(key, t)
        t.chest = -500.0
        before = sum(t.garrison.values())
        g._keep_the_chest(key, t)
        self.assertLess(sum(t.garrison.values()), before)

    def test_the_chest_is_saved(self):
        g = game()
        key, t = next(iter(g.world.towns.items()))
        t.chest = 1234.0
        self.assertEqual(GameState.from_dict(g.to_dict()).world.towns[key].chest, 1234.0)
