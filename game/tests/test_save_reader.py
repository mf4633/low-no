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
