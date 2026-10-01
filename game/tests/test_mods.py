"""Changing the game without editing the game.

The thing worth taking from a modding scene is not scripting. It is that
somebody who wants a cheaper trebuchet can have one in ten minutes and keep
it when the game updates. That wants one feature: a folder of small files
saying what to change.

Every test here is about not lying to the player. A mod that quietly does
nothing is worse than one that refuses to load.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace

from marchlands import mods


class TestAMod(unittest.TestCase):
    def setUp(self):
        from marchlands import buildings, goods, lords, military, tech
        # Every table this can touch is global, so put each one back.
        self._was = {
            "units": dict(military.UNITS),
            "buildings": dict(buildings.BUILDINGS),
            "goods": dict(goods.GOODS),
            "houses": dict(tech.HOUSES),
            "techs": dict(tech.TECHS),
            "lords": dict(lords.SORTS),
        }
        self.tables = {"units": military.UNITS, "buildings": buildings.BUILDINGS,
                       "goods": goods.GOODS, "houses": tech.HOUSES,
                       "techs": tech.TECHS, "lords": lords.SORTS}

    def tearDown(self):
        for name, was in self._was.items():
            table = self.tables[name]
            table.clear()
            table.update(was)

    def folder(self, **files):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        for name, data in files.items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                if isinstance(data, str):
                    fh.write(data)
                else:
                    json.dump(data, fh)
        return tmp

    # ------------------------------------------------------- what it does
    def test_it_changes_the_field_you_name(self):
        from marchlands.military import UNITS
        was = UNITS["trebuchet"].coin
        where = self.folder(**{"a.json": {"units": {"trebuchet": {"coin": 11}}}})
        mods.load(where)
        self.assertEqual(UNITS["trebuchet"].coin, 11)
        self.assertNotEqual(was, 11)

    def test_and_leaves_the_rest_of_the_entry_alone(self):
        # A mod patches fields; it does not replace tables. One written
        # against an old version must not silently delete what a new one
        # added.
        from marchlands.military import UNITS
        was = UNITS["trebuchet"]
        where = self.folder(**{"a.json": {"units": {"trebuchet": {"coin": 11}}}})
        mods.load(where)
        now = UNITS["trebuchet"]
        self.assertEqual(now.name, was.name)
        self.assertEqual(now.siege_power, was.siege_power)
        self.assertEqual(now.unit_class, was.unit_class)

    def test_it_can_reach_every_table_it_claims_to(self):
        for table, key, field, value in (
                ("units", "spearman", "coin", 7),
                ("buildings", "bakery", "build_days", 3),
                ("goods", "bread", "weight", 2.5),
                ("lords", "boar", "aggression", 9.0)):
            where = self.folder(**{"m.json": {table: {key: {field: value}}}})
            mods.load(where)
            self.assertEqual(getattr(self.tables[table][key], field), value,
                             f"{table}.{key}.{field}")

    def test_files_are_applied_in_name_order_so_it_is_repeatable(self):
        from marchlands.military import UNITS
        where = self.folder(**{
            "b_second.json": {"units": {"ram": {"coin": 2}}},
            "a_first.json": {"units": {"ram": {"coin": 1}}}})
        mods.load(where)
        self.assertEqual(UNITS["ram"].coin, 2, "the later file should win")

    # --------------------------------------------- what it refuses to do
    def test_an_unknown_entry_is_reported(self):
        where = self.folder(**{"a.json": {"units": {"dragoon": {"coin": 1}}}})
        [mod] = mods.load(where)
        self.assertFalse(mod.applied)
        self.assertTrue(any("dragoon" in r for r in mod.refused))

    def test_an_unknown_field_is_reported_with_the_ones_that_exist(self):
        where = self.folder(**{"a.json": {"units": {"ram": {"nope": 1}}}})
        [mod] = mods.load(where)
        self.assertTrue(any("nope" in r and "coin" in r for r in mod.refused))

    def test_an_unknown_table_is_reported_with_the_ones_that_exist(self):
        where = self.folder(**{"a.json": {"weather": {"rain": {}}}})
        [mod] = mods.load(where)
        self.assertTrue(any("weather" in r and "units" in r
                            for r in mod.refused))

    def test_a_near_miss_is_offered_a_suggestion(self):
        where = self.folder(**{"a.json": {"units": {"speargoon": {"coin": 1}}}})
        [mod] = mods.load(where)
        self.assertTrue(any("spearman" in r for r in mod.refused))

    def test_broken_json_is_refused_rather_than_raised(self):
        where = self.folder(**{"a.json": "{not json at all"})
        [mod] = mods.load(where)
        self.assertTrue(any("JSON" in r for r in mod.refused))

    def test_a_wrong_type_is_refused_rather_than_raised(self):
        where = self.folder(**{"a.json": {"units": "a string"}})
        [mod] = mods.load(where)
        self.assertTrue(mod.refused)

    def test_one_bad_entry_does_not_stop_the_good_ones(self):
        from marchlands.military import UNITS
        where = self.folder(**{"a.json": {"units": {
            "dragoon": {"coin": 1}, "ram": {"coin": 42}}}})
        [mod] = mods.load(where)
        self.assertEqual(UNITS["ram"].coin, 42)
        self.assertTrue(mod.refused)

    def test_a_note_to_the_reader_is_not_a_table(self):
        where = self.folder(**{"a.json": {"_note": "why I did this",
                                          "units": {"ram": {"coin": 5}}}})
        [mod] = mods.load(where)
        self.assertFalse(mod.refused)

    def test_a_folder_that_is_not_there_is_not_an_error(self):
        self.assertEqual(mods.load("/tmp/no-such-mods-folder-at-all"), [])

    def test_only_json_files_are_read(self):
        where = self.folder(**{"readme.txt": "not a mod",
                               "a.json": {"units": {"ram": {"coin": 6}}}})
        self.assertEqual(len(mods.load(where)), 1)

    def test_the_report_says_what_happened_either_way(self):
        where = self.folder(**{"a.json": {"units": {"ram": {"coin": 6},
                                                    "dragoon": {"coin": 1}}}})
        said = "\\n".join(mods.report(mods.load(where)))
        self.assertIn("a.json", said)
        self.assertIn("coin=6", said)
        self.assertIn("refused", said)

    def test_nothing_in_a_mod_is_executed(self):
        # A game that ships no dependencies should not acquire the ability to
        # run a stranger's code the week it acquires mods.
        source = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "marchlands", "mods.py"),
            encoding="utf-8").read()
        for danger in ("eval(", "exec(", "import_module", "__import__(",
                       "pickle", "subprocess"):
            self.assertNotIn(danger, source, danger)




class TestTheShippedFolderChangesNothing(unittest.TestCase):
    """An example that loaded would quietly change the price of every siege
    engine in everybody's game, which is the opposite of what an example is
    for."""

    def test_the_folder_we_ship_applies_no_changes(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        folder = os.path.join(here, "mods")
        if not os.path.isdir(folder):
            return self.skipTest("no mods folder shipped")
        for mod in mods.load(folder):
            self.assertFalse(mod.applied, f"{mod.name} changed the game")

    def test_but_there_is_an_example_to_copy(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        folder = os.path.join(here, "mods")
        if not os.path.isdir(folder):
            return self.skipTest("no mods folder shipped")
        names = os.listdir(folder)
        self.assertTrue(any(n.endswith(".example") for n in names), names)
        self.assertIn("README.md", names)



if __name__ == "__main__":
    unittest.main()
