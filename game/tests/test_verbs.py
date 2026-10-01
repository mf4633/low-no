"""One list of verbs, whichever way in you came.

The browser is a remote control for the console: every button, tool and
shortcut sends a line through the same registry the terminal reads, and the
palette is built off that registry rather than written beside it. These
pin the bijection, and the one way a Python dict can quietly break it -- a
key written twice, where the second silently wins. That happened: "gate"
was the gatehouse you lay in the wall and, forty lines further down, an
alias for the sortie odds, so the drawbar's gate tool asked the odds of a
coordinate and nobody could lay a gate by name.
"""

import ast
import io
import pathlib
import re
import unittest

from marchlands.cli import COMMANDS, Console, catalogue
from marchlands.scenario import new_game

PKG = pathlib.Path(__file__).resolve().parent.parent / "marchlands"
JS = (PKG / "static" / "marchlands.js").read_text(encoding="utf-8")
HTML = (PKG / "static" / "index.html").read_text(encoding="utf-8")


def _registry_literal() -> ast.Dict:
    tree = ast.parse((PKG / "cli.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, (ast.Assign, ast.AnnAssign))
                and "COMMANDS" in ast.unparse(node.targets[0]
                                              if isinstance(node, ast.Assign)
                                              else node.target)
                and isinstance(node.value, ast.Dict)):
            return node.value
    raise AssertionError("no COMMANDS literal in cli.py")


def _sent_verbs() -> set:
    """Every verb the page sends by name: `send('verb ...')`, the build and
    draw tools, and the data-do buttons."""
    out = set()
    for src in (JS, HTML):
        out |= set(re.findall(r"""send\(\s*[`'"]([a-z_]+)""", src))
        out |= set(re.findall(r"""data-do=["']([a-z_]+)""", src))
        out |= set(re.findall(r"""data-lay=["']([a-z_]+)""", src))
    return out


class TestOneRegistry(unittest.TestCase):
    def test_no_verb_is_written_twice(self):
        keys = [k.value for k in _registry_literal().keys
                if isinstance(k, ast.Constant)]
        twice = sorted({k for k in keys if keys.count(k) > 1})
        self.assertEqual(twice, [], f"a later entry silently replaces: {twice}")

    def test_every_verb_the_page_sends_is_a_command(self):
        missing = sorted(v for v in _sent_verbs() if v not in COMMANDS)
        self.assertEqual(missing, [])

    def test_the_palette_is_the_registry(self):
        listed = set()
        for e in catalogue():
            listed.add(e["name"])
            listed |= set(e["aliases"])
        self.assertEqual(listed, set(COMMANDS))

    def test_the_drawbar_tools_lay_what_they_say(self):
        """Each tool on the wall's drawbar is the verb that lays that piece."""
        tools = set(re.findall(r"""data-lay=["']([a-z_]+)""", HTML))
        self.assertIn("gate", tools)
        for tool in tools:
            self.assertNotIn("odds", COMMANDS[tool].__name__, tool)

    def test_a_gate_is_laid_by_name(self):
        g = new_game(seed=5)
        out = io.StringIO()
        con = Console(g, out=out)
        con.do("castle")
        con.do("gate 14,13")
        said = re.sub(r"\x1b\[[0-9;]*m", "", out.getvalue())
        self.assertNotIn("is not one of your towns", said)
        self.assertIn("gatehouse", said)


if __name__ == "__main__":
    unittest.main()
