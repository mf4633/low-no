"""A save is read, not eaten.

Loading the same dict twice must give the same game twice, and the dict
must be what it was. The caravan reader used to pop its cargo, route and
log out of the caller's dict, so a second load from the same object had
carts with nothing in them and nowhere to go -- invisible from a file on
disk, which is read once, and found the first time a soak loaded one save
twice to check that two loads agree.
"""
import json
import unittest

from marchlands.engine import GameState
from marchlands.roles import ROLES
from marchlands.scenarios import start
from marchlands.sim import Bot


def grown_save(seed=1, days=30):
    g = start("marchlands", seed=seed)
    bot = Bot(g)
    for _ in range(days):
        bot.step()
        g.advance(1)
    d = json.loads(json.dumps(g.to_dict()))
    assert d["caravans"] and any(c.get("route") for c in d["caravans"]), "the fixture wants a cart on the road"
    return d


class TestReadingASave(unittest.TestCase):
    def test_loading_does_not_change_the_dict(self):
        d = grown_save()
        before = json.dumps(d, sort_keys=True)
        GameState.from_dict(d)
        self.assertEqual(json.dumps(d, sort_keys=True), before)

    def test_two_loads_of_one_save_are_the_same_game(self):
        d = grown_save()
        g1, g2 = GameState.from_dict(d), GameState.from_dict(d)
        self.assertEqual(json.dumps(g1.to_dict(), sort_keys=True),
                         json.dumps(g2.to_dict(), sort_keys=True))
        for _ in range(7):
            g1.advance(1)
            g2.advance(1)
        self.assertEqual(json.dumps(g1.to_dict(), sort_keys=True),
                         json.dumps(g2.to_dict(), sort_keys=True))


if __name__ == "__main__":
    unittest.main()


class TestASaveGoesOnMatching(unittest.TestCase):
    """A load must not merely look like the game it came from; it has to go
    on being it. Anything the game decides from days ago -- a cooldown, a
    heat, yesterday's hands -- is state whether or not it looks derived.

    Found by walking every scenario and role and letting the original and a
    load of its save run on side by side: the lords' shrine cooldown was
    never written, so every lord came back believing he had never sent men
    to a shrine and sent a party the next morning, which moved armies, and
    the two games parted company within a day.
    """

    def walk(self, scenario, role, seed=3, before=120, after=10):
        a = start(scenario, seed=seed, role=role)
        a.battles_mode = "play"
        for _ in range(before):
            a.advance(1)
            if a.pending:
                a.battle_step("auto")
        b = GameState.from_dict(json.loads(json.dumps(a.to_dict())))
        b.battles_mode = "play"
        for day in range(after):
            a.advance(1)
            b.advance(1)
            if a.pending:
                a.battle_step("auto")
            if b.pending:
                b.battle_step("auto")
            self.assertEqual(json.dumps(a.to_dict(), sort_keys=True),
                             json.dumps(b.to_dict(), sort_keys=True),
                             f"{scenario}/{role} parted from its own save on day {day + 1}")

    def test_every_role_goes_on_matching(self):
        for role in ROLES:
            self.walk("marchlands", role)

    def test_a_few_scenarios_go_on_matching(self):
        for scenario in ("siege", "salt_road", "iron_marches"):
            self.walk(scenario, "lord", before=80, after=8)

    def test_the_lords_remember_their_last_pilgrimage(self):
        g = start("marchlands", seed=3)
        town = next(iter(g.world.towns.values()))
        town.last_pilgrimage = 42
        again = GameState.from_dict(json.loads(json.dumps(g.to_dict())))
        self.assertEqual(next(iter(again.world.towns.values())).last_pilgrimage, 42)


class TestASaveIsADocument(unittest.TestCase):
    """How a save is written down must not change what it says.

    A save is JSON, and JSON tools reorder keys: any pretty-printer with
    `sort_keys` on, a diff-friendly rewrite, a hand edit. The day walks the
    towns in the order the dict holds them, and a dict rebuilt from a file
    holds them in the file's order -- so a reordered save was a different
    campaign, with another town taking the shock and another lord taking
    offence first. The world now carries the order it was laid out in.
    """

    def played(self, seed=3, days=90):
        g = start("marchlands", seed=seed)
        g.battles_mode = "play"
        for _ in range(days):
            g.advance(1)
            if g.pending:
                g.battle_step("auto")
        return g

    def test_the_world_remembers_the_order_it_was_laid_out_in(self):
        g = self.played(days=20)
        alphabetised = json.loads(json.dumps(g.to_dict(), sort_keys=True))
        again = GameState.from_dict(alphabetised)
        self.assertEqual(list(again.world.towns), list(g.world.towns))
        self.assertEqual(list(again.world.settlements), list(g.world.settlements))

    def test_a_reordered_save_plays_the_same_game(self):
        g = self.played()
        again = GameState.from_dict(json.loads(json.dumps(g.to_dict(), sort_keys=True)))
        again.battles_mode = "play"
        for day in range(30):
            said = [m for m in g.advance(1) if m]
            also = [m for m in again.advance(1) if m]
            if g.pending:
                g.battle_step("auto")
            if again.pending:
                again.battle_step("auto")
            # What happened, said in words, and the shape of the war: the
            # last bit of a float may differ where a sum was added up in
            # another order, and nothing that decides anything may.
            self.assertEqual(said, also, f"day {day + 1} happened differently")
            self.assertEqual([(a.uid, a.at, a.state, round(a.size)) for a in g.armies],
                             [(a.uid, a.at, a.state, round(a.size)) for a in again.armies],
                             f"the hosts differ on day {day + 1}")

    def test_an_old_save_without_the_order_still_loads(self):
        g = self.played(days=15)
        d = json.loads(json.dumps(g.to_dict()))
        del d["world"]["order"]
        again = GameState.from_dict(d)
        self.assertEqual(list(again.world.towns), list(g.world.towns))
        again.advance(1)
