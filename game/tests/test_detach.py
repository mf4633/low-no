"""Part of a host as a host of its own, and two hosts made one.

A host is a count of men, not a crowd of sprites, so "select the knights
and send them" can only mean detaching them. That has to conserve men,
keep the captain with the host he was posted to, refuse on the road, and
survive a save.
"""
import io
import unittest

from marchlands.cli import Console
from marchlands.engine import GameState
from marchlands.military import GARRISON, MARCHING
from marchlands.scenarios import start


class TestDetach(unittest.TestCase):
    def setUp(self):
        self.g = start("marchlands", seed=3)
        self.home = next(iter(self.g.world.settlements))
        self.g.world.settlements[self.home].units = {"spearman": 30.0, "archer": 12.0}
        self.a, why = self.g.raise_host(self.home, {"spearman": 20, "archer": 10})
        self.assertIsNotNone(self.a, why)
        self.away = next(k for k in self.g.world.towns)

    def test_a_split_conserves_the_men(self):
        a = self.a
        stores = a.stores
        b, why = self.g.split_host(a.uid, {"archer": 10, "spearman": 5})
        self.assertIsNotNone(b, why)
        self.assertEqual(b.units, {"archer": 10.0, "spearman": 5.0})
        self.assertEqual(a.units, {"spearman": 15.0})
        self.assertEqual((b.at, b.home, b.order, b.state), (a.at, a.home, a.order, a.state))
        self.assertAlmostEqual(a.stores + b.stores, stores, places=6)
        self.assertIn(b, self.g.armies)
        self.assertTrue(a.log and b.log)

    def test_a_split_refuses_what_it_cannot_do(self):
        a = self.a
        self.assertIn("whole", self.g.split_host(a.uid, {"spearman": 20, "archer": 10})[1])
        self.assertIn("only", self.g.split_host(a.uid, {"archer": 11})[1])
        self.assertIn("name some", self.g.split_host(a.uid, {})[1])
        self.assertIn("no host", self.g.split_host(999, {"archer": 1})[1])
        self.g.march(a.uid, self.away)
        self.assertEqual(a.state, MARCHING)
        self.assertIn("road", self.g.split_host(a.uid, {"archer": 1})[1])

    def test_a_join_conserves_the_men_and_moves_the_captain(self):
        a = self.a
        b, _ = self.g.split_host(a.uid, {"archer": 10})
        who = next(p for p in self.g.kin.living() if p.post != "head")
        self.g.kin.give(who, "captain", str(b.uid))
        self.assertEqual(who.target, str(b.uid))
        said = self.g.join_hosts(a.uid, b.uid)
        self.assertIn("joins", said)
        self.assertNotIn(b, self.g.armies)
        self.assertEqual(a.units, {"spearman": 20.0, "archer": 10.0})
        self.assertEqual(who.target, str(a.uid))

    def test_a_join_wants_both_in_one_place(self):
        a = self.a
        b, _ = self.g.split_host(a.uid, {"archer": 4})
        self.assertIn("already one host", self.g.join_hosts(a.uid, a.uid))
        b.at, b.state = self.away, GARRISON
        said = self.g.join_hosts(a.uid, b.uid)
        self.assertIn(self.g.world.node_name(self.away), said)
        b.at = a.at
        self.g.march(b.uid, self.away)
        self.assertIn("road", self.g.join_hosts(a.uid, b.uid))

    def test_both_hosts_survive_a_save(self):
        a = self.a
        b, _ = self.g.split_host(a.uid, {"archer": 3})
        g2 = GameState.from_dict(self.g.to_dict())
        self.assertEqual({x.uid: x.units for x in g2.armies if x.owner == "player"},
                         {a.uid: a.units, b.uid: b.units})

    def test_the_console_speaks_it(self):
        buf = io.StringIO()
        con = Console(self.g, out=buf)
        con.do(f"split {self.a.uid} archer 4")
        new = max(x.uid for x in self.g.armies if x.owner == "player")
        con.do(f"join {self.a.uid} {new}")
        con.do("split")
        con.do(f"detach {self.a.uid} archer lots")
        text = buf.getvalue()
        self.assertIn("stands apart", text)
        self.assertIn("joins", text)
        self.assertIn("split <host>", text)
        self.assertIn("not a number", text)


if __name__ == "__main__":
    unittest.main()
