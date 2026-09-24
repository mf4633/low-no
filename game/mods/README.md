# Mods

A folder of small JSON files that change the game's tables. Anything in here
ending `.json` is applied before the game starts, in name order.

    mods/cheap_siege.json
    {
      "_note": "engines a poorer lord could afford",
      "units": {
        "trebuchet": {"coin": 300, "upkeep": 1.1},
        "ram":       {"coin": 90}
      }
    }

Tables you can touch: `buildings`, `units`, `goods`, `houses`, `techs`,
`lords`. Run `marchlands --list` to see what is in each, or read the module
the table lives in — the field names in a mod are the field names in the
dataclass.

Three rules, and they are all about not lying to you.

**A mod patches fields, it does not replace tables.** Naming a unit changes
the fields you name and leaves the rest, so a mod written against one version
does not silently delete what a later one added.

**Anything it cannot apply is printed, not swallowed.** A typo is the
commonest thing to go wrong, and a mod that quietly does nothing is worse
than one that refuses to load. You will get the line, the reason, and a
suggestion where there is an obvious one:

    cheap_siege.json: 2 change(s), 1 refused
        units.trebuchet: coin=300, upkeep=1.1
        units.ram: coin=90
        refused: units: nothing called 'speargoon' -- did you mean spearman?

**Nothing is executed.** These are tables, not scripts. A game that ships no
dependencies should not acquire the ability to run a stranger's code the week
it acquires mods.

`--mods FOLDER` reads somewhere else instead.

There is one file here already: `cheap_siege.json.example`. It does not load,
because the loader only reads `.json` — an example that shipped live would
quietly change the price of every siege engine in everybody's game. Copy it to
`cheap_siege.json` to try it.
