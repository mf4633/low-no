"""The castle as a shape you drew, and what the shape is worth.

The most repeated sentence anybody writes about Stronghold is some version of
"the satisfaction of seeing your vision come to life". This game had the works
-- moat, ditch, pits, towers -- and they are the right abstraction of what a
castle does to a besieger, and they were entirely invisible: you bought
`stone_wall` and a square appeared around whatever the town happened to be.

So these are tests that the drawing is real. Not that it is pretty: that the
siege reads it, that a long wall is thinner than a short one, that a tower on
the far side is a tower the ladders have already walked past, and that what
will not fit inside is standing where the man with the torch is.
"""

import io
import json
import random
import unittest

from marchlands import keep as keeps
from marchlands.castle import ESCALADE, SiegeState, Works, approach, choose
from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.layout import plan_for
from marchlands.scenario import new_game
from marchlands.scenarios import start
from marchlands.settlement import BuildingInstance as B
from marchlands.sim import Bot
from marchlands.web import snapshot


def owned(*keys):
    return [B(uid=i, key=k, days_left=0) for i, k in enumerate(keys, 1)]


def square(side, x0=None, y0=None, kind=keeps.STONE):
    """A closed ring, which is the thing every other shape is measured against."""
    c = keeps.Castle()
    cx, cy = keeps.CENTRE
    x0 = cx - side // 2 if x0 is None else x0
    y0 = cy - side // 2 if y0 is None else y0
    for t in keeps.ring(x0, y0, x0 + side - 1, y0 + side - 1):
        c.lay(t, kind)
    return c


def grown(seed=5, days=300):
    g = start("marchlands", seed=seed)
    bot = Bot(g)
    for _ in range(days):
        bot.step()
        g.tick()
    return g, g.home()


class TestTheGeometryIsTheJudgement(unittest.TestCase):
    """Everything the castle is worth is read off the drawing by flood fill
    and arithmetic. Nothing is scored, rated, or stored -- a stored judgement
    goes stale the moment somebody lays a stone."""

    def test_a_closed_ring_shuts_the_ground_in(self):
        c = square(8)
        self.assertTrue(keeps.shut(c))
        self.assertEqual(len(keeps.enclosed(c)), 36)     # (8-2)^2
        self.assertEqual(c.yards, 28)                    # 4*8-4

    def test_a_ring_with_a_hole_in_it_is_a_fence(self):
        c = square(8)
        c.clear(sorted(c.wall)[len(c.wall) // 2])
        self.assertFalse(keeps.shut(c))
        self.assertEqual(keeps.enclosed(c), set())

    def test_and_the_hole_is_pointed_at_rather_than_merely_counted(self):
        c = square(8)
        hole = (keeps.CENTRE[0], keeps.CENTRE[1] - 4)
        c.lay(hole, keeps.STONE)
        c.clear(hole)
        self.assertIn(hole, keeps.gaps(c))

    def test_a_diagonal_wall_is_a_wall(self):
        """Four-neighbour, deliberately: a besieger cannot squeeze between two
        stones set corner to corner, and anybody drawing a diamond needs that
        to be true before they spend an evening on it."""
        c = keeps.Castle()
        cx, cy = keeps.CENTRE
        for i in range(6):
            for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                c.lay((cx + dx * i, cy + dy * (5 - i)), keeps.STONE)
        self.assertTrue(keeps.shut(c), "a diamond is not a sieve")

    def test_a_bigger_ring_costs_more_wall_and_shuts_more_in(self):
        small, big = square(6), square(12)
        self.assertLess(small.yards, big.yards)
        self.assertLess(len(keeps.enclosed(small)), len(keeps.enclosed(big)))

    def test_towers_cover_what_is_near_them_and_nothing_else(self):
        c = square(12)
        corner = min(c.wall)
        c.lay(corner, keeps.TOWER)
        seen = keeps.covered(c)
        self.assertIn(corner, seen)
        self.assertLess(len(seen), c.yards, "one tower is not a castle")
        for w in seen:
            self.assertLessEqual(keeps.reach(w, corner), keeps.TOWER_REACH)

    def test_the_weak_side_is_the_longest_run_nobody_watches(self):
        c = square(12)
        for t in (min(c.wall), max(c.wall)):
            c.lay(t, keeps.TOWER)
        run = keeps.weak(c)
        self.assertTrue(run)
        self.assertEqual(len(run), max(len(r) for r in keeps.stretches(keeps.naked(c))))
        for t in run:
            self.assertNotIn(t, keeps.covered(c))

    def test_a_castle_covered_all_round_has_no_weak_side(self):
        c = square(8)
        for t in c.wall:
            c.lay(t, keeps.TOWER)
        self.assertEqual(keeps.weak(c), [])

    def test_the_weak_side_is_named_in_words(self):
        c = square(10)
        r = keeps.read(c)
        self.assertIn(r.weak_side, ("north", "south", "east", "west",
                                    "north-east", "north-west",
                                    "south-east", "south-west"))

    def test_a_second_ring_is_a_second_siege(self):
        inner, outer = square(6), square(14)
        both = keeps.Castle(dict(inner.pieces))
        both.pieces.update(outer.pieces)
        self.assertEqual(keeps.depth(inner), 1)
        self.assertEqual(keeps.depth(both), 2)

    def test_a_ditch_only_answers_the_stretch_it_is_dug_in_front_of(self):
        c = square(10)
        near = min(c.wall)
        c.lay((near[0] - 1, near[1] - 1), keeps.MOAT)
        far = max(c.wall)
        self.assertEqual(keeps.ditch_at(c, [near])[keeps.MOAT], 1)
        self.assertEqual(keeps.ditch_at(c, [far])[keeps.MOAT], 0)

    def test_nothing_can_be_drawn_off_the_edge_of_the_ground(self):
        c = keeps.Castle()
        c.lay((-1, 4), keeps.STONE)
        c.lay((keeps.SIDE, 4), keeps.STONE)
        self.assertEqual(c.pieces, {})


class TestYouCanOnlyLayWhatYouPaidFor(unittest.TestCase):
    """The economy is untouched: the same buildings at the same prices buying
    the same effects. What changed is that each one is a length of wall to
    lay rather than a ring that appears."""

    def test_a_wall_you_have_not_bought_is_not_yards_in_hand(self):
        self.assertEqual(keeps.budget([])[keeps.STONE], 0)
        self.assertEqual(keeps.budget(owned("stone_wall"))[keeps.STONE],
                         keeps.YARDS["stone_wall"][1])

    def test_a_wall_still_being_built_is_not_a_wall_you_can_stand_on(self):
        half = [B(uid=1, key="stone_wall", days_left=3)]
        self.assertEqual(keeps.budget(half)[keeps.STONE], 0)

    def test_what_is_laid_comes_off_what_is_in_hand(self):
        have = owned("stone_wall")
        c = square(6)                       # 20 yards of the 28
        left = keeps.unlaid(have, c)
        self.assertEqual(left[keeps.STONE], keeps.YARDS["stone_wall"][1] - 20)

    def test_drawing_more_than_you_paid_for_comes_back_down(self):
        have = owned("palisade")            # 28 yards
        c = square(14, kind=keeps.TIMBER)   # 52 of them
        self.assertTrue(keeps.over_budget(have, c))
        gone = keeps.trim(have, c)
        self.assertTrue(gone)
        self.assertEqual(keeps.over_budget(have, c), {})
        self.assertLessEqual(c.yards, 28)

    def test_an_unpaid_tower_becomes_the_stone_it_stands_on(self):
        """Never a hole. A tower you cannot afford is still a yard of wall
        somebody built, and taking the whole stone out from under it punches
        a gap in the ring -- which is the one thing a budget rule must not do
        to a castle somebody drew. It cost a concentric castle fifty-four of
        its seventy enclosed plots, silently, because two towers were over."""
        have = owned("stone_wall")                  # stone, and no towers
        c = square(8)
        for t in (min(c.wall), max(c.wall)):
            c.lay(t, keeps.TOWER)
        self.assertTrue(keeps.shut(c))
        keeps.trim(have, c)
        self.assertTrue(keeps.shut(c), "the budget rule opened the ring")
        self.assertEqual(c.towers, [])
        self.assertEqual(c.yards, 28)

    def test_and_unpaid_stone_becomes_timber_before_it_becomes_nothing(self):
        have = owned("palisade")                    # timber only
        c = square(8)                               # drawn in stone
        keeps.trim(have, c)
        self.assertTrue(keeps.shut(c))
        self.assertEqual(keeps.read(c).timber, 28)

    def test_but_what_has_nothing_to_fall_back_on_does_come_down(self):
        c = square(14, kind=keeps.TIMBER)
        keeps.trim(owned("palisade"), c)
        self.assertLessEqual(c.yards, keeps.YARDS["palisade"][1])

    def test_a_castle_inside_a_castle_is_two_sieges(self):
        _g, s = grown()
        s.buildings.extend(owned("stone_wall", "stone_wall", "stone_wall"))
        for i, b in enumerate(s.buildings):
            b.uid = 3000 + i
        s.take_the_pen()
        s.castle.pieces.clear()
        for t in keeps.ring(9, 10, 20, 20):
            s.castle.lay(t, keeps.STONE)
        for t in keeps.ring(12, 12, 17, 17):
            s.castle.lay(t, keeps.STONE)
        r = keeps.read(s.plan())
        self.assertEqual(r.depth, 2)
        self.assertTrue(r.shut)
        self.assertGreater(r.inside, 60)
        self.assertEqual(s.outside_the_wall(), [])

    def test_and_the_furthest_out_is_what_comes_down(self):
        have = owned("palisade")
        c = square(14, kind=keeps.TIMBER)
        keeps.trim(have, c)
        for t in c.wall:
            self.assertLessEqual(keeps.reach(t, keeps.CENTRE), 7)


class TestTheStewardsRing(unittest.TestCase):
    """Nobody is obliged to draw anything. A player who never touches `wall`
    gets the square his steward would have laid, which is exactly the ring
    this game drew before the wall was a drawing."""

    def test_no_wall_bought_is_no_wall_drawn(self):
        self.assertEqual(keeps.default_castle([]).pieces, {})

    def test_one_wall_bought_closes_a_ring(self):
        c = keeps.default_castle(owned("palisade"))
        self.assertTrue(keeps.shut(c))

    def test_it_is_sized_to_the_town_that_has_to_fit_in_it(self):
        small = keeps.default_castle(owned("stone_wall", "stone_wall"), want_inside=4)
        big = keeps.default_castle(owned("stone_wall", "stone_wall"), want_inside=40)
        self.assertLess(small.yards, big.yards)

    def test_and_never_bigger_than_the_yards_in_hand_will_close(self):
        c = keeps.default_castle(owned("palisade"), want_inside=400)
        self.assertTrue(keeps.shut(c), "it drew a ring it could not finish")
        self.assertLessEqual(c.yards, keeps.YARDS["palisade"][1])

    def test_a_grown_town_still_fits_inside_its_own_wall(self):
        """The whole risk of making the wall a drawing: a town that used to be
        enclosed by definition can now be left standing in the field by a ring
        one size too small. The steward's ring must never do that."""
        _g, s = grown()
        self.assertTrue(s.sheltered())
        self.assertEqual(s.outside_the_wall(), [])

    def test_the_towers_go_where_a_steward_would_put_them(self):
        c = keeps.default_castle(owned("palisade", "wall_tower", "wall_tower"))
        self.assertEqual(len(c.towers), 2)
        for t in c.towers:
            self.assertIn(t, c.wall)


class TestTakingThePen(unittest.TestCase):
    def test_the_first_yard_you_lay_starts_from_what_is_standing(self):
        _g, s = grown()
        was = s.plan().yards
        s.take_the_pen()
        self.assertEqual(s.castle.yards, was,
                         "drawing one stone knocked the castle down")

    def test_and_the_steward_stops_rearranging_it(self):
        _g, s = grown()
        s.take_the_pen()
        s.castle.clear(min(s.castle.wall))
        self.assertNotIn(min(s.plan().wall), [])
        self.assertTrue(s.castle.own)

    def test_pulling_the_whole_thing_down_does_not_hand_the_pen_back(self):
        _g, s = grown()
        s.take_the_pen()
        s.castle.pieces.clear()
        self.assertEqual(s.plan().yards, 0,
                         "the steward redrew a castle the player had razed")

    def test_a_drawing_survives_a_save(self):
        g, s = grown()
        s.take_the_pen()
        s.castle.lay((3, 3), keeps.TOWER)
        back = GameState.from_dict(json.loads(json.dumps(g.to_dict())))
        there = back.home()
        self.assertEqual(there.castle.pieces, s.castle.pieces)
        self.assertTrue(there.castle.own)


class TestTheSiegeReadsTheShape(unittest.TestCase):
    """A wall is yards and a garrison is men, so what decides whether the
    wall-walk is held is men to the yard. That is the price of enclosing more
    ground than you can man, and it is why a small tight castle is an answer
    rather than a poor man's one."""

    def test_a_longer_wall_is_a_thinner_wall(self):
        tight, sprawl = keeps.read(square(6)), keeps.read(square(16))
        self.assertGreater(tight.density(60), sprawl.density(60))
        self.assertGreater(keeps.manning(tight.density(60)),
                           keeps.manning(sprawl.density(60)))

    def test_a_wall_nobody_is_standing_on_is_worth_less_than_nothing(self):
        self.assertLess(keeps.manning(0.4), 0.0)
        self.assertGreater(keeps.manning(6.0), 0.0)

    def test_but_it_cannot_run_away_with_the_fight(self):
        for per in (0.0, 0.01, 1e6):
            self.assertGreaterEqual(keeps.manning(per), -5.0)
            self.assertLessEqual(keeps.manning(per), 7.0)

    def test_the_ladders_go_where_no_tower_looks(self):
        watched = Works(towers=4, naked=0)
        open_flank = Works(towers=4, naked=9)
        state = SiegeState(plan=ESCALADE)
        kw = dict(siege_power=0.0, engineers=0.0, wall=100.0, wall_max=100.0,
                  have_pitch=False, rng=random.Random(1))
        a = approach(ESCALADE, watched, SiegeState(plan=ESCALADE), **kw)
        b = approach(ESCALADE, open_flank, state, **kw)
        self.assertGreater(a.attacker_mult, b.attacker_mult,
                           "towers on the far side still hurt the ladders")

    def test_and_the_captain_picks_that_side_on_purpose(self):
        """The same host, the same wall, the same four towers -- and where he
        goes in depends only on whether they can see each other."""
        kw = dict(siege_power=25.0, engineers=0.0, host=600.0, garrison=150.0,
                  wall=100.0, wall_max=100.0)
        shut = choose(Works(towers=4, naked=0, stone=True, oil=1), **kw)
        open_flank = choose(Works(towers=4, naked=12, stone=True, oil=1), **kw)
        self.assertNotEqual(shut, open_flank)
        self.assertEqual(open_flank, ESCALADE)

    def test_a_second_wall_cuts_what_a_storm_can_reach(self):
        kw = dict(siege_power=40.0, engineers=0.0, wall=100.0, wall_max=100.0,
                  have_pitch=False, rng=random.Random(3))
        one = approach("breach", Works(depth=1), SiegeState(), **kw)
        two = approach("breach", Works(depth=2), SiegeState(), **kw)
        self.assertAlmostEqual(two.defender_mult, one.defender_mult / 2, places=6)

    def test_the_works_can_be_read_off_the_ground(self):
        c = square(10)
        for t in (min(c.wall), max(c.wall)):
            c.lay(t, keeps.TOWER)
        c.lay((keeps.CENTRE[0], keeps.CENTRE[1] + 5), keeps.GATE)
        w = Works.read(c)
        self.assertEqual(w.towers, 2)
        self.assertTrue(w.gate)
        self.assertTrue(w.stone)
        self.assertEqual(w.naked, len(keeps.weak(c)))

    def test_what_the_besieger_is_told_names_the_open_flank(self):
        said = Works(towers=3, naked=7).answers(ESCALADE)
        self.assertTrue(any("cannot see" in line for line in said), said)
        shut = Works(towers=3, naked=0).answers(ESCALADE)
        self.assertTrue(any("no stretch" in line for line in shut), shut)


class TestWhatIsOutsideIsWhatBurns(unittest.TestCase):
    """A town does not stop growing when its wall stops. Drawing a small
    castle is cheap in stone and dear in everything standing in the field,
    which is the trade the whole feature exists to offer."""

    def test_a_small_ring_leaves_workshops_in_the_field(self):
        _g, s = grown()
        s.take_the_pen()
        s.castle.pieces.clear()
        for t in keeps.ring(13, 13, 17, 17):
            s.castle.lay(t, keeps.STONE)
        self.assertTrue(s.outside_the_wall())

    def test_and_a_ring_round_the_whole_town_leaves_none(self):
        _g, s = grown()
        self.assertEqual(s.outside_the_wall(), [])

    def test_the_torch_finds_them_first(self):
        _g, s = grown()
        s.take_the_pen()
        s.castle.pieces.clear()
        for t in keeps.ring(13, 13, 17, 17):
            s.castle.lay(t, keeps.STONE)
        exposed = set(s.outside_the_wall())
        self.assertTrue(exposed)
        s.fires = type(s.fires)()
        s.kindle(random.Random(4), 3)
        lit = {uid for uid in exposed if s.fires.burning(uid)}
        self.assertTrue(lit, "the raiders walked past the undefended half")

    def test_a_farm_is_not_a_building_left_outside(self):
        """It is supposed to be out there. Counting the fields as exposed made
        every castle in the game read as a disaster."""
        _g, s = grown()
        plan = plan_for(s)
        country = {b.uid for b in plan.buildings
                   if b.terrain in ("fertile", "forest", "hills", "clay")}
        self.assertTrue(country)
        self.assertFalse(country & set(s.outside_the_wall()))


class TestTheConsoleDrawsIt(unittest.TestCase):
    def setUp(self):
        self.buf = io.StringIO()
        self.g = new_game(seed=5)
        self.s = self.g.home()
        self.s.buildings.extend(owned("stone_wall", "wall_tower", "gatehouse"))
        for i, b in enumerate(self.s.buildings):
            b.uid = 900 + i
        self.con = Console(self.g, out=self.buf)

    def said(self):
        return self.buf.getvalue()

    def test_castle_prints_the_drawing_itself(self):
        self.con.do("castle")
        out = self.said()
        self.assertIn("THE CASTLE", out)
        self.assertIn("yards", out)
        self.assertIn("men to the yard", out)

    def test_a_town_with_no_wall_says_so_and_says_what_buys_one(self):
        self.s.buildings = [b for b in self.s.buildings
                            if b.spec.terrain != "rampart"]
        self.con.do("castle")
        self.assertIn("No wall at all", self.said())

    def test_wall_lays_a_run_between_two_points(self):
        was = self.s.plan().yards
        self.con.do("unwall 0,0 29,29")
        self.s.castle.pieces.clear()
        self.con.do("wall 10,10 10,18")
        self.assertEqual(self.s.castle.yards, 9)
        self.assertNotEqual(was, self.s.castle.yards)

    def test_a_run_is_a_straight_line_between_the_two_ends(self):
        self.con.do("unwall 0,0 29,29")
        self.s.castle.pieces.clear()
        self.con.do("wall 10,10 14,10")
        self.assertEqual(sorted(self.s.castle.wall),
                         [(10, 10), (11, 10), (12, 10), (13, 10), (14, 10)])

    def test_it_will_not_lay_what_has_not_been_bought(self):
        self.con.do("unwall 0,0 29,29")
        self.s.castle.pieces.clear()
        self.con.do("wall 2,2 28,2")
        self.con.do("wall 2,3 28,3")
        self.con.do("wall 2,4 28,4")
        self.con.do("wall 2,5 28,5")
        hand = keeps.unlaid(self.s.buildings, self.s.castle)
        self.assertGreaterEqual(hand[keeps.STONE], 0)
        self.assertGreaterEqual(hand[keeps.TIMBER], 0)
        self.assertIn("more than you have paid for", self.said())

    def test_unwall_puts_it_back_in_hand(self):
        self.con.do("wall 10,10 10,14")
        before = keeps.unlaid(self.s.buildings, self.s.castle)[keeps.STONE]
        self.con.do("unwall 10,10 10,14")
        after = keeps.unlaid(self.s.buildings, self.s.castle)[keeps.STONE]
        self.assertGreater(after, before)

    def test_a_tower_goes_where_it_is_told(self):
        self.con.do("unwall 0,0 29,29")
        self.s.castle.pieces.clear()
        self.con.do("wall 10,10 18,10")
        self.con.do("tower 14,10")
        self.assertEqual(self.s.castle.at((14, 10)), keeps.TOWER)

    def test_an_open_ring_is_said_out_loud(self):
        self.con.do("unwall 0,0 29,29")
        self.s.castle.pieces.clear()
        self.con.do("wall 10,10 18,10")
        self.assertIn("not closed", self.said())

    def test_nonsense_coordinates_are_refused_rather_than_guessed_at(self):
        self.con.do("wall over there")
        self.assertIn("castle", self.said())

    def test_the_town_screens_admit_what_they_cannot_draw(self):
        """Both of them are a rectangle round the town, and the castle is a
        thirty-yard square of ground. What they must not do is let the picture
        quietly put a workshop inside a wall that does not reach it."""
        self.con.do("unwall 0,0 29,29")
        self.s.castle.pieces.clear()
        for t in keeps.ring(13, 13, 17, 17):
            self.s.castle.lay(t, keeps.STONE)
        for screen in ("view", "view flat"):
            self.buf.truncate(0)
            self.buf.seek(0)
            self.con.do(screen)
            self.assertIn("the wall does not reach", self.said(), screen)

    def test_the_steward_points_at_a_hole_in_your_own_castle(self):
        """Only worth saying while there is somebody coming and still days to
        lay stone in it, which is exactly where the rest of the war hints
        live."""
        g, s = grown()
        buf = io.StringIO()
        con = Console(g, out=buf)
        s.take_the_pen()
        # A corner is not a hole: four-neighbour, the outside can touch it and
        # go no further. The hole has to be in a side.
        wall = sorted(s.castle.wall)
        x0, y0 = wall[0]
        s.castle.clear((x0 + 2, y0))
        self.assertFalse(keeps.shut(s.plan()), "the test did not open the ring")
        self.assertTrue(any("not closed" in h for h in con.hints()), con.hints())
        self.assertIs(buf, buf)

    def test_and_at_what_is_standing_where_the_wall_does_not_reach(self):
        g, s = grown()
        con = Console(g, out=io.StringIO())
        # It has to beat the other four things a steward might say, because
        # the list is capped at four -- which is exactly how this one first
        # went missing.
        s.take_the_pen()
        s.castle.pieces.clear()
        for t in keeps.ring(13, 13, 17, 17):
            s.castle.lay(t, keeps.STONE)
        self.assertTrue(any("outside the wall" in h for h in con.hints()),
                        con.hints())

    def test_every_drawing_command_is_in_the_help(self):
        self.con.do("help")
        out = self.said()
        for word in ("castle", "wall", "tower", "gate", "moat", "unwall"):
            self.assertIn(word, out)


class TestTheBrowserGetsIt(unittest.TestCase):
    def test_the_snapshot_carries_the_reading(self):
        g, s = grown()
        snap = snapshot(g)
        c = snap["castle"]
        for field in ("yards", "towers", "shut", "inside", "covered", "weak",
                      "per_yard", "outside", "hand", "depth"):
            self.assertIn(field, c)
        self.assertEqual(c["yards"], s.plan().yards)

    def test_and_it_is_json(self):
        g, _s = grown()
        back = json.loads(json.dumps(snapshot(g)))
        self.assertIn("castle", back)

    def test_the_picture_draws_the_wall_it_was_given(self):
        _g, s = grown()
        s.buildings.append(B(uid=4242, key="wall_tower", days_left=0))
        s.take_the_pen()
        s.castle.pieces.clear()
        for t in keeps.ring(11, 11, 19, 19):
            s.castle.lay(t, keeps.STONE)
        s.castle.lay((11, 11), keeps.TOWER)
        plan = plan_for(s)
        kinds = {(w[0], w[1]): w[2] for w in plan.walls}
        self.assertEqual(len(kinds), 32)              # 4*9-4
        self.assertEqual(kinds[(11, 11)], "tower")

    def test_the_page_has_somewhere_to_draw_from(self):
        import os
        from marchlands.web import STATIC
        with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as fh:
            page = fh.read()
        self.assertIn('id="drawbar"', page)
        self.assertIn('data-lay="wall"', page)
        with open(os.path.join(STATIC, "marchlands.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("function drawPencil", js)
        self.assertIn("paintDrawbar", js)
