"""A window onto the game, served from the standard library and nothing else.

The terminal view has place and motion and it is still glyphs. This is the
same game with a picture on it: a small HTTP server that hands the browser the
state, and a canvas that draws a town out of it -- timber frames, thatch,
stone, water, smoke, weather, people in the streets.

Everything is drawn, nothing is loaded. There are no images in this
repository and there is no dependency list, because the roofs are vector paths
and the rule that this game installs with nothing is worth more than a texture
atlas.

    python3 -m marchlands --web

The browser is a view and a keyboard. Every command the console takes works
here, because it is the same Console underneath.
"""

from __future__ import annotations

import itertools
import json
import os
import random
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

from . import __version__
from .cli import Console, catalogue
from . import config as C
from .economics import marginal_hands
from .military import MARCHING, sky_on
from . import rivers as waters
from .kin import SKILLS
from .league import PLAYER as LEAGUE_PLAYER
from . import cartography as carto
from . import chancery
from . import culture as cultures
from . import keep as keeps
from . import voices
from .clock import Clock
from . import estates as estates_mod
from . import roles as roles_mod
from . import feats as feats_mod
from . import missions as missions_mod
from . import military
from . import plague as plague_mod
from . import supply
from .buildings import BUILDINGS
from .military import BESIEGING, UNITS
from .layout import plan_for
from . import goods as goods_mod


def _static_dir() -> str:
    """Where the page, its stylesheet and its scripts actually are.

    Not simply `__file__`'s directory. A PyInstaller one-file build unpacks
    everything into a temporary directory and points `sys._MEIPASS` at it, so
    a frozen Marchlands.exe that resolved this the obvious way would start,
    serve index.html from a path that does not exist, and show a blank page --
    which is the same failure `pyproject.toml` already warns about for wheels,
    arrived at by a different route.
    """
    here = getattr(sys, "_MEIPASS", None)
    if here:
        bundled = os.path.join(here, "marchlands", "static")
        if os.path.isdir(bundled):
            return bundled
        return os.path.join(here, "static")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


STATIC = _static_dir()

TYPES = {".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8",
         ".json": "application/json"}


def _matchup_target(game, a):
    """Whose host this one would meet. Where it is going if it is going
    somewhere, otherwise whoever is standing in front of it."""
    from .military import BESIEGING, MARCHING
    key = a.bound_for if a.state == MARCHING else a.at
    if key in game.world.towns and not game.world.towns[key].mine:
        return key
    foe = next((b for b in game.armies
                if b.owner != "player" and b.at == a.at and b.uid != a.uid), None)
    return foe.owner if foe else ""


def _matchup_for(game, a) -> list:
    key = _matchup_target(game, a)
    if not key:
        return []
    from .military import matchup
    # What you *believe* they can field, not what they can. Costing a battle
    # off the true muster would be reading their books.
    return matchup(a.units, game.believed_host(key))


def _matchup_note(game, a) -> str:
    key = _matchup_target(game, a)
    if not key:
        return ""
    from .military import counter_note
    theirs = game.believed_host(key)
    if not theirs:
        return f"you have never looked at {game.world.node_name(key)}"
    return counter_note(a.units, theirs)


def _believed_works(game, key: str) -> dict:
    """What you think that lord's castle is, and what each approach would
    find there.

    Off the prosperity you *saw*, so a seat that has been building since you
    last sent a cart is the seat you remember, not the one that is there.
    Never off the true figure: that would be reading his mason's accounts.
    """
    from .castle import PLANS
    town = game.world.towns.get(key)
    if town is None or town.mine:
        return {}
    seen, age = game.known(key)
    if age < 0:
        return {}                          # never looked; nothing to say
    w = town.works(seen.get("prosperity"))
    lines = []
    for plan in PLANS.values():
        met = w.answers(plan.key)      # the works that bear on this approach
        lines.append({"key": plan.key, "name": plan.name, "blurb": plan.blurb,
                      "needs": plan.needs_siege,
                      "engineers": plan.needs_engineers, "meets": met})
    return {
        "moat": w.moat, "towers": w.towers, "naked": w.naked, "depth": w.depth,
        "stone": bool(w.stone), "gate": bool(w.gate),
        "traps": w.pitch + w.pits + w.oil,
        "age": age, "plans": lines,
    }


def _field_view(game, key: str) -> dict:
    """The country round a place and the sky over it today.

    Not fogged, and deliberately. What a fen is like underfoot is not a
    secret a lord keeps -- anyone who has driven a cart that way knows, and
    the map has been drawing the country all along. The fog in this game
    covers how many men are behind a wall, which is the thing you would
    actually have to send somebody to find out.
    """
    fld = game.field_at(key)
    mine = [a for a in game.armies if a.owner == "player"]
    near = next((a for a in mine if a.at == key), None) or (mine[0] if mine else None)
    return {
        "words": fld.words(),
        "going": fld.ground.name, "going_note": fld.ground.note,
        "sky": fld.sky.name, "sky_note": fld.sky.note,
        "firm": bool(fld.sky.firms and fld.going == military.HEAVY),
        "dials": [{"kind": k, "worth": round(v, 3)}
                  for k, v in sorted(fld.mult().items())],
        "host": military.field_note(near.units, fld) if near else [],
        "season": [{"sky": k, "odds": round(v, 2)}
                   for k, v in military.season_odds(game.season)],
    }


def _supply_view(game, a) -> dict:
    """A host's baggage, and what the country round it will give."""
    where = a.at or a.bound_for
    view = supply.note(a.size, a.stores, game._ground_at(where), game.season,
                       game.world.grazed.get(where, 0.0))
    larder, far = game._larder(a)
    from .military import BESIEGING, GARRISON, RAIDING
    settled = a.state in (BESIEGING, GARRISON, RAIDING)
    view["from_home"] = round(supply.convoy_share(far, settled), 2) if larder else 0.0
    view["larder"] = game.world.node_name(larder) if larder else ""
    view["leagues"] = round(far) if larder else 0
    view["fed"] = a.fed
    return view


def _their_host_name(game, a) -> str:
    """What you call a host that is not yours. Their lord's, not its own:
    you would not know what they have named it."""
    return f"{game.world.node_name(a.owner)}'s host"


def march(game, here: str, good: str = "bread") -> dict:
    """The map the trade layer actually lives on.

    The town view shows the part of the game that is not the point. This is the
    point: who is where, what the roads between them are worth, where your
    carts have got to this morning, and which two places are currently further
    apart in price than the distance between them can justify.
    """
    w = game.world
    fog = game.shroud
    if not fog.visible:
        game._scout()           # a new game, or one just loaded
    nodes = []
    for key, (x, y) in w.coords.items():
        # Country nobody of yours has had in sight is not on your map: not
        # the town, not its price, not its name.
        if not fog.known(x, y):
            continue
        if key in w.settlements:
            s = w.settlements[key]
            kind, name, who = "mine", s.name, "you"
            stock = s.market.stock.get(good, 0.0)
            price = s.market.bid(good)
        elif key in w.towns:
            t = w.towns[key]
            kind = "vassal" if t.mine else "town"
            name, who = t.name, (t.lord or "")
            stock, price = t.market.stock.get(good, 0.0), t.market.bid(good)
        elif key in w.shrines:
            sh = w.shrines[key]
            kind = "shrine"
            name = sh.short or sh.name
            who = ("yours" if sh.holder == "player"
                   else w.node_name(sh.holder) if sh.holder else "")
            stock = price = 0.0
        else:
            continue
        # Prices travel: merchants talk, and `prices` has always listed every
        # market. What does not travel is how many men a lord has behind his
        # wall, so that -- and only that -- is what the fog covers here.
        seen, age = game.known(key) if key in w.towns else ({}, 0)
        from .military import host_strength
        host = (round(host_strength(game.believed_host(key)))
                if key in w.towns and age >= 0 else None)
        nodes.append({"key": key, "name": name, "x": x, "y": y, "kind": kind,
                      "who": who, "port": w.is_port(key),
                      "price": round(price, 2), "stock": round(stock),
                      "known": age, "host": host,
                      # His castle as you last saw it, and what each way in
                      # would meet. Every lord used to build the identical
                      # wall, so there was nothing to adapt to.
                      "keep": _believed_works(game, key),
                      # Where a battle here would be fought, and under what.
                      "field": _field_view(game, key),
                      "walls": round(seen.get("wall_hp", 0.0)) if seen else None,
                      "sees": fog.sees(x, y),
                      # A sworn town's oath, and a wall that has thrown a
                      # storm back lately.
                      "loyalty": (round(w.towns[key].loyalty)
                                  if key in w.towns and w.towns[key].mine else None),
                      "hardened": (round(w.towns[key].hardened)
                                   if key in w.towns else 0),
                      "here": key == here})
    for key, site in w.sites.items():
        if not fog.known(site.x, site.y):
            continue
        nodes.append({"key": key, "name": site.name, "x": site.x, "y": site.y,
                      "kind": "site", "who": "", "port": False,
                      "price": 0.0, "stock": 0, "known": 0, "here": False})

    carts = []
    for c in game.caravans:
        frm = c.at or (c.route[c.leg - 1].node if c.route and c.leg else c.home)
        to = c.bound_for or c.at or c.home
        total = max(1.0, w.distance(frm, to) / max(c.speed, 1.0)) if frm and to else 1.0
        _frm, pos = game.cart_xy(c)
        carts.append({
            "xy": list(pos) if pos else None,
            "uid": c.uid, "name": c.name, "kind": c.kind,
            "from": frm, "to": to,
            "done": 0.0 if not c.bound_for else
                    max(0.0, min(1.0, 1.0 - c.days_left / total)),
            "moving": bool(c.bound_for), "running": c.running,
            "load": round(c.load), "capacity": round(c.capacity),
            "cargo": {k: round(v) for k, v in c.cargo.items() if v >= 1},
            "profit": round(c.total_profit),
        })

    # --- the hosts in the field ------------------------------------------
    #
    # Yours in full, because they are yours. Theirs only as far as you can
    # actually see: on your doorstep it is a host, anywhere else it is the
    # last place you saw it with a date on it, and where you have never seen
    # it at all there is nothing to draw. The map has always been willing to
    # lie by omission and must not start lying by commission.
    from .military import BESIEGING, MARCHING, RAIDING
    hosts = []
    for a in game.armies:
        mine = a.owner == "player"
        fresh = mine or (a.seen_day >= 0 and a.seen_day == game.day)
        if not mine and a.seen_day < 0:
            continue                      # never seen: it is not on your map
        at = a.at if fresh else a.seen_at
        frm, to = (a.at, a.bound_for) if (fresh and a.state == MARCHING) else ("", "")
        total = max(1.0, a.days_left + 1.0)
        led = None
        if mine:
            who = next((p for p in game.kin.living()
                        if p.post == "captain" and p.target == str(a.uid)), None)
            led = who.name if who else None
        # Where it is drawn, from the engine that decides whether you can
        # see it -- a host between two towns, one of them still in the blank,
        # has nowhere else to be put.
        pos = game.host_xy(a) if fresh else w.coords.get(a.seen_at)
        hosts.append({
            "xy": list(pos) if pos else None,
            "uid": a.uid, "name": a.name if mine else _their_host_name(game, a),
            "mine": mine, "at": at, "from": frm, "to": to,
            "done": 0.0 if not frm else max(0.0, min(1.0, 1.0 - a.days_left / total)),
            "moving": bool(frm), "state": a.state if fresh else "remembered",
            "size": a.size if mine else (a.seen_size or a.size),
            "units": ({k: round(v) for k, v in a.units.items() if v >= 1}
                      if mine else {}),
            "days_left": round(a.days_left, 1) if fresh else 0.0,
            "upkeep": round(a.upkeep, 1) if mine else 0.0,
            "siege_days": a.siege_days if fresh else 0,
            "captain": led,
            # What this host is worth against the place it is going, said in
            # counters rather than left in the arithmetic. A rock-paper-
            # scissors nobody can see is a dice roll.
            "matchup": _matchup_for(game, a) if mine else [],
            "note": _matchup_note(game, a) if mine else "",
            # What it is eating, and for how much longer. A commander told
            # after he starves has been given a cutscene; told before, he
            # has a decision -- march on, sit, or turn for home.
            "supply": _supply_view(game, a) if mine else {},
            "stale": 0 if fresh else max(0, game.day - a.seen_day),
            "owner": "" if mine else w.node_name(a.owner),
        })

    runs = []
    seat = here if here in w.settlements else next(iter(w.settlements))
    try:
        from .advisor import scan as scan_trades
        sails = any(s.count("harbour") for s in w.settlements.values())
        for opp in scan_trades(w, seat, top=4, sails=sails, steps=6):
            goods = {}
            for leg in (opp.out, opp.back):
                if leg:
                    for k, v in leg.cargo.items():
                        goods[k] = goods.get(k, 0.0) + v
            runs.append({"from": opp.frm, "to": opp.to,
                         "per_day": round(opp.per_day, 1),
                         "days": round(opp.days, 1),
                         "goods": [k for k, _v in sorted(
                             goods.items(), key=lambda kv: -kv[1])[:3]]})
    except Exception:
        runs = []          # the map is worth drawing even if the scan is not
    # The schedule belongs on the map more than anywhere else: an arrow from
    # a lord to the place he has said he is going is the whole of it.
    fixtures = [{"who": f.who, "target": f.target,
                 "at_you": f.target in w.settlements,
                 "reason": getattr(f, "reason", "")}
                for f in game.league.season.fixtures if not f.done]
    known = {n["key"] for n in nodes}
    runs = [r for r in runs if r["from"] in known and r["to"] in known]
    fixtures = [f for f in fixtures if f["who"] in known and f["target"] in known]
    return {"good": good, "nodes": nodes, "carts": carts, "runs": runs,
            "hosts": hosts, "fixtures": fixtures,
            "roads": _roads(w, known), "shroud": _shroud_view(fog),
            # The edges of the parchment, so the map holds still while the
            # blank fills in. Where the corners are is not a secret.
            "bounds": [min(x for x, _ in w.coords.values()),
                       min(y for _, y in w.coords.values()),
                       max(x for x, _ in w.coords.values()),
                       max(y for _, y in w.coords.values())]}


def _roads(w, known) -> list:
    """The roads the engine keeps (`World.roads`), drawn wherever one end of
    one is somewhere you know. The shroud covers the rest of the line, so a
    road runs off into the blank the way it would on a map you were making."""
    out = []
    for a, b in w.roads():
        if a in known or b in known:
            (ax, ay), (bx, by) = w.coords[a], w.coords[b]
            out.append([ax, ay, bx, by])
    return out


def _shroud_view(sh) -> dict:
    """The shroud as the page paints it: the cells explored and the cells
    in sight, each a flat list of i, j pairs."""
    from .sight import CELL
    flat = lambda cells: [v for c in sorted(cells) for v in c]
    return {"cell": CELL, "all": sh.everything,
            "explored": flat(sh.explored), "visible": flat(sh.visible)}


def options(game, here: str = "") -> dict:
    """What the town could raise today, and why not where not.

    The page never decides any of this. It asks, it draws the answer, and when
    you click it sends the same `build cottage` a person would have typed --
    so there is exactly one place the rules live, and it is not in JavaScript.
    """
    from .buildings import BUILDINGS
    key = here or next(iter(game.world.settlements))
    s = game.world.settlements[key]
    out = []
    for bkey, spec in BUILDINGS.items():
        ok, why = s.can_build(bkey, game.progress)
        coin = spec.build_cost.get("coin", 0.0)
        if ok and game.treasury < coin:
            ok, why = False, f"costs {coin:,.0f}c; you have {game.treasury:,.0f}c"
        out.append({
            "key": bkey, "name": spec.name, "category": spec.category,
            "terrain": spec.terrain, "age": spec.age, "jobs": spec.jobs,
            "coin": coin, "days": spec.build_days,
            "goods": {k: v for k, v in spec.build_cost.items() if k != "coin"},
            "makes": dict(spec.outputs), "wants": dict(spec.inputs),
            "note": spec.note, "can": ok, "why": "" if ok else why,
        })
    out.sort(key=lambda b: (not b["can"], b["age"], b["coin"]))
    free = {t: s.slots_free(t) for t in
            ("fertile", "forest", "hills", "clay", "coast", "urban", "rampart")}
    return {"here": key, "slots": free, "buildings": out}


def _best_skill(person) -> str:
    """What one of yours is known for, or nothing if they have not been used."""
    best = max(SKILLS, key=lambda sk: person.xp.get(sk, 0.0))
    return f"{best} {person.level(best)}" if person.level(best) > 0 else ""


#: The names a household answers to. Seeded on the roof rather than the day or
#: the figure's place in the list, because a house does not rename itself
#: overnight and two figures out of the same door are the same family.
def _household(game, settlement, roof_uid: int) -> str:
    from . import kin as kinly
    rng = random.Random(f'{getattr(game, "seed", 0)}:'
                        f'{getattr(settlement, "key", "")}:{roof_uid}')
    return "the " + rng.choice(kinly.FIRST_M + kinly.FIRST_F) + "s"


def _officers(game, key: str) -> list:
    """The few people in this town who are somebody, for the layout to place.

    Resolved here rather than in `layout`, which knows nothing about houses
    and should go on knowing nothing about them.
    """
    from . import kin as kinly
    out = []
    kin = getattr(game, "kin", None)
    if kin is None:
        return out
    for post in kinly.POSTS:
        who = kin.holder(post)
        if not who or post not in ("steward", "factor", "master", "captain"):
            continue
        # A steward governs one town and a captain rides with one host. Draw
        # them where they actually are, not in every town at once.
        if who.target and who.target != key and post == "steward":
            continue
        out.append({"name": who.name, "post": post})
    return out


def folk(game, here: str, index: int) -> dict:
    """Who one figure in the picture is, and what they would say.

    Every answer here is read off the town rather than invented. A worker
    already knew the roof he sleeps under and the shed he walks to -- that is
    how his path was drawn -- and the watch already knew which yard of wall it
    is standing on. The only thing this adds is a name for the household and a
    voice, and both are seeded rather than rolled, because a browser polling
    once a second must not re-roll anybody.
    """
    from . import kin as kinly
    key = here or next(iter(game.world.settlements))
    s = game.world.settlements[key]
    plan = plan_for(s, officers=_officers(game, key))
    if not 0 <= index < len(plan.folk):
        return {"error": "nobody there"}
    f = plan.folk[index]
    named = {b.uid: b for b in plan.buildings}
    rep = s.report

    # A different figure is a different person with a different worry, so the
    # dice turn on the figure as well as the day.
    rng = random.Random(f'{getattr(game, "seed", 0)}:{game.day}:{key}:{index}')
    heard = voices.speak(s, game, rng, how_many=4)
    said = heard[index % len(heard)] if heard else None

    out = {"i": index, "kind": f.kind, "souls": f.souls, "facts": [],
           "said": f'{said[0]}: “{said[1]}”' if said else "",
           "home": named[f.home].name if f.home in named else "",
           "work": named[f.work].name if f.work in named else ""}

    if f.kind == "kin":
        who = game.kin.holder(f.post)
        spec = kinly.POSTS.get(f.post)
        out["title"] = f.who
        out["doing"] = (spec.verb.replace("{t}", f.at) if spec
                        else "one of yours")
        if who:
            out["person"] = {
                "name": who.name, "age": who.age(game.day), "post": who.post,
                "skills": sorted(
                    ({"skill": sk, "level": who.level(sk)}
                     for sk in kinly.SKILLS if who.level(sk) > 0),
                    key=lambda d: -d["level"]),
                "traits": sorted(who.traits),
            }
            out["facts"].append(
                {"k": "holds", "v": f"{spec.key} — {spec.blurb}"
                 if spec else who.post})
            if spec:
                out["facts"].append(
                    {"k": "gaining", "v": f"{spec.skill} "
                     f"{who.level(spec.skill)}, by doing it"})
            if who.target:
                out["facts"].append({"k": "posted to", "v": who.target})
        # Two of the five posts need somewhere to be -- a steward governs a
        # named town and a captain rides with a named host -- and the panel
        # has to supply that, or the button quietly does the wrong thing.
        # `post X steward` with no town resolves to whichever settlement comes
        # first in the dictionary, which is not the one you are looking at.
        host = next((a.uid for a in game.armies if a.owner == "player"), None)
        offer = []
        for k, v in kinly.POSTS.items():
            if v.needs == "town":
                target, can = key, True
            elif v.needs == "host":
                target, can = ("" if host is None else str(host)), host is not None
            else:
                target, can = "", True
            offer.append({"key": k, "blurb": v.blurb, "needs": v.needs,
                          "held": bool(game.kin.holder(k)), "target": target,
                          "can": can,
                          "why": "" if can else "you have no host in the field"})
        out["posts"] = offer
        return out

    if f.kind == "watch":
        held = sum(1 for w in plan.folk if w.kind == "watch")
        yards = len(plan.walls)
        out["title"] = f"{f.souls} of the garrison"
        out["doing"] = "standing this stretch of the wall"
        out["facts"].append({"k": "the wall", "v": f"{yards} yards drawn"})
        out["facts"].append(
            {"k": "standing it", "v": f"{held} such watches, "
             f"{held * f.souls} men"})
        if yards and held * f.souls < yards:
            out["facts"].append(
                {"k": "which is", "v": "fewer men than yards of wall"})
        return out

    trade = named[f.work].name if f.work in named else ""
    out["title"] = (_household(game, s, f.home) if f.home >= 0
                    else "folk of the town")
    if f.kind == "worker":
        # What this figure is actually doing, off the figure itself, which is
        # where the picture gets it too -- so the card and the man on screen
        # cannot say different things. It used to read "walking between their
        # roof and the smithy" for everybody, which was true when every
        # worker shuttled a road and stopped being true the day they started
        # standing at the work.
        out["doing"] = f"{f.at} at {trade}" if trade else f.at
        spec = BUILDINGS.get(named[f.work].key) if f.work in named else None
        if spec and spec.outputs:
            out["facts"].append(
                {"k": "makes", "v": ", ".join(sorted(spec.outputs))})
    else:
        # Where they are standing is drawn, so say the same thing the
        # picture is saying rather than a second version of it.
        out["doing"] = f.at or "standing about, because nothing wants doing"
        out["facts"].append(
            {"k": "why", "v": f"{s.employed:.0f} of {s.workforce:.0f} "
             f"hands have work"})
    out["facts"].append({"k": "eating", "v": f"{s.ration_level} rations, "
                         f"{int(rep.variety or 1)} kinds of food"})
    out["facts"].append({"k": "paying", "v": f"tax {s.tax_level}"})
    if rep.unpaid:
        out["facts"].append({"k": "owed", "v": "they have not been paid"})
    if s.housing(game.progress) < s.population:
        out["facts"].append({"k": "roof", "v": "more people than beds"})
    return out


def beast(game, here: str, index: int) -> dict:
    """What one animal in a yard is, and what it is worth to you.

    Answers in the same shape as `folk` so the same panel can show it. A
    beast is not a sample of anything -- a sheep is a sheep -- so the count
    here is the real head in that yard, which is also what a raid takes.
    """
    key = here or next(iter(game.world.settlements))
    s = game.world.settlements[key]
    plan = plan_for(s, officers=_officers(game, key))
    if not 0 <= index < len(plan.beasts):
        return {"error": "nothing there"}
    a = plan.beasts[index]
    named = {b.uid: b for b in plan.buildings}
    yard = named.get(a.at)
    herd = [x for x in plan.beasts if x.at == a.at]
    keeper = next((f for f in plan.folk
                   if f.trade == "herd" and f.work == a.at), None)
    spec = BUILDINGS.get(yard.key) if yard else None

    out = {"i": index, "kind": "beast", "souls": 1,
           "title": {"sheep": "the flock", "cow": "the herd",
                     "horse": "the horses"}.get(a.kind, a.kind),
           "doing": ("grazing, and somebody is watching them" if keeper
                     else "grazing, with nobody set to watch them"),
           "facts": [], "said": "",
           "home": yard.name if yard else "", "work": ""}
    inst = next((b for b in s.buildings if b.uid == a.at), None)
    full = C.HERD_FULL.get(inst.key, 0) if inst is not None else 0
    if full:
        out["facts"].append(
            {"k": "head", "v": f"{max(0.0, inst.head):.0f} of {full}"})
        if inst.head >= 0 and inst.head < full * C.HERD_SEED:
            out["facts"].append(
                {"k": "too few", "v": "to breed from -- this flock only comes "
                                      "back if you buy one in"})
    else:
        out["facts"].append({"k": "head", "v": f"{len(herd)} {a.kind}"})
    if yard is not None:
        if not yard.running:
            out["facts"].append(
                {"k": "but", "v": "that yard is not working, so the head is "
                                  "down to what it can keep"})
    if spec and spec.outputs:
        out["facts"].append({"k": "yields", "v": ", ".join(sorted(spec.outputs))})
    if keeper is not None:
        out["facts"].append(
            {"k": "kept by", "v": _household(game, s, keeper.home)
             if keeper.home >= 0 else "somebody of the town"})
    out["facts"].append(
        {"k": "if raided", "v": "driven off -- beasts are the first thing a "
                                "raid takes and the last thing it leaves"})
    return out


def _save_path() -> str:
    """Where a game goes when nobody has said where.

    Beside the executable for a packaged build, so a player who double-clicked
    something can find their save without knowing what a working directory is;
    beside the checkout otherwise.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "marchlands.save")
    return os.path.abspath("marchlands.save")


#: Whether the browser should open on the front door rather than straight into
#: a game. True when nobody chose anything -- a packaged build somebody
#: double-clicked, or a bare `--web` -- and False the moment they have, because
#: a player who typed `--scenario iron_marches` has already answered the only
#: question that screen asks.
SHOW_FRONT = False

#: The thread letting the days pass, once a server is up. None in the tests
#: that call these functions directly, which is the point: the game does not
#: need a clock to be a game.
CLOCK = None


def _front_door(console, route: str, body: dict) -> dict:
    """Start, save or resume a game without anybody typing a command.

    The three things a person who double-clicked an icon expects to be able
    to do, and the three that were console-only: `save`, `load` and choosing
    what to play at all.
    """
    global SHOW_FRONT
    from .scenarios import start
    path = body.get("path") or _save_path()
    if route == "/save":
        try:
            console.game.save(path)
        except OSError as exc:
            return {"error": f"could not write it: {exc}"}
        return {"said": f"saved to {path}", "saved": True}
    if route == "/load":
        try:
            from .engine import GameState
            console.game = GameState.load(path)
            console.game.battles_mode = "play"
        except (OSError, ValueError, KeyError) as exc:
            return {"error": f"could not open it: {exc}"}
        console.here = next(iter(console.game.world.settlements))
        SHOW_FRONT = False
        return {"said": "picked up where you left it",
                "state": snapshot(console.game, console.here)}
    house = body.get("house", "plough")
    role = body.get("role") or "lord"
    seed = int(body.get("seed") or 7)
    region = body.get("region") or ""
    try:
        if region:
            from .scenario import drawn_game
            console.game = drawn_game(region, seed=seed, house=house)
            console.game.battles_mode = "play"
            if role != "lord":
                roles_mod.apply(console.game, role)
        else:
            console.game = start(body.get("scenario", "marchlands"),
                                 seed=seed, house=house, role=role)
            console.game.battles_mode = "play"
    except KeyError as exc:
        return {"error": str(exc)}
    console.here = next(iter(console.game.world.settlements))
    SHOW_FRONT = False
    if CLOCK is not None:
        CLOCK.set_speed(0)                 # a new country starts stopped
    return {"said": console.game.briefing,
            "state": snapshot(console.game, console.here)}


def _at(name: str, value: float) -> "carto.Dials":
    return carto.Dials(**{name: value})


def _dials_from(q: dict) -> "carto.Dials":
    """Dials off a query string, starting from the region's own."""
    region = q.get("region", [carto.DEFAULT_REGION])[0]
    d = carto.REGIONS.get(region, carto.REGIONS[carto.DEFAULT_REGION]).dials
    parts = [f"{n}={q[n][0]}" for n in carto.DIAL_NAMES if n in q]
    return carto.parse_dials(",".join(parts), d) if parts else d


def _preview(plan) -> dict:
    """A drawn march, small enough to send on every twitch of a slider."""
    return {
        "region": plan.region, "note": plan.note, "seed": plan.seed,
        "dials": plan.dials.as_dict(),
        "words": [{"dial": n, "value": v, "says": w}
                  for n, v, w in carto.describe(plan.dials)],
        "home": {"name": plan.home_name, "terrain": dict(plan.home_terrain)},
        "towns": [{"name": t["name"], "x": t["x"], "y": t["y"],
                   "lord": t["lord"], "blurb": t["blurb"],
                   "port": t["port"], "walls": t["walls"],
                   "culture": cultures.for_ground(t["ground"]),
                   "sells": sorted(t["produces"], key=t["produces"].get,
                                   reverse=True)[:3],
                   "buys": sorted(t["consumes"], key=t["consumes"].get,
                                  reverse=True)[:3]}
                  for t in plan.towns],
        "sites": [{"name": s["name"], "x": s["x"], "y": s["y"]}
                  for s in plan.sites],
        "shrines": [{"name": s["name"], "x": s["x"], "y": s["y"]}
                    for s in plan.shrines],
    }


def _idiom(c) -> dict:
    """One idiom, as four channels the renderer can act on: what the walls
    are, what the roofs are, how steep, and what colour the street is."""
    return {"key": c.key, "name": c.name, "blurb": c.blurb,
            "walls": dict(c.walls), "roofs": dict(c.roofs),
            "pitch": c.pitch, "gable": c.gable, "stretch": c.stretch,
            "tone": c.tone, "tint": c.tint, "tint_by": c.tint_by,
            "roof_tint": c.roof_tint, "roof_by": c.roof_by}


def _culture(s) -> dict:
    return _idiom(s.idiom())


def _court(game) -> dict:
    """The march as a web of opinion, for the map that draws it."""
    c, day = game.court, game.day
    towns = {}
    for key, t in game.world.towns.items():
        if t.mine:
            continue
        view = c.opinion(key, day)
        ground = c.ground_for(key, day)
        towns[key] = {
            "name": t.name, "lord": t.lord,
            "opinion": round(view, 1), "temper": chancery.temper(view),
            "offence": round(c.offence(key, day), 1),
            "culture": chancery and t.culture or t.culture,
            "signed": key in c.coalition,
            "allied": key in c.allies,
            "claim": key in c.claims,
            "ground": ground.label if ground else "",
            # Trust apart from liking, and the war as he reckons it.
            "trust": round(c.trust_of(key)),
            # His reckoning about a war on you, the last time his temper
            # was up: each reason and its weight, and where he marches.
            "reckoning": [{"what": r[0], "by": r[1]} for r in t.reckoning],
            "reckoned": t.reckoned, "declares_at": game.DECLARE,
            "war": round(c.score.get(key, 0.0)),
            "sued": day - c.sued.get(key, -9999) <= game.SUIT_DAYS,
            "why": [{"what": w, "by": round(v, 1)}
                    for w, v, _d in c.reasons(key, day)[:4]],
        }
    called = c.called
    return {
        "towns": towns,
        "coalition": list(c.coalition),
        "bar": chancery.COALITION_BAR,
        "price": round(c.coalition_price(day)),
        "called": {"town": called[0],
                   "days": game.CALL_DAYS - (day - called[1])} if called else None,
    }


def _castle(s) -> dict:
    """What the wall is, for the bar you draw it with."""
    drawing = s.plan()
    r = keeps.read(drawing)
    return {
        "yards": r.yards, "stone": r.stone, "timber": r.timber,
        "towers": r.towers, "gates": r.gates, "shut": r.shut,
        "inside": r.inside, "covered": r.covered, "depth": r.depth,
        "weak": [{"x": x, "y": y} for x, y in r.weak],
        "side": r.weak_side,
        "per_yard": round(s.per_yard(), 2),
        "outside": len(s.outside_the_wall()),
        "own": bool(s.castle.own),
        "hand": {k: v for k, v in keeps.unlaid(s.buildings, drawing).items()
                 if v > 0},
    }


def _water_view(game) -> dict:
    """The rivers, what they are doing, and what you have put over them.

    Everything here is public: a river is not fogged. What you cannot see
    from this panel is what it is doing *tomorrow*, and that is the whole
    design -- see rivers.forecast.
    """
    level = waters.stage(game.day, game.seed, game.start_month)
    sky = sky_on(game.season, game.day, game.seed)
    lines = []
    for r in game.world.waters():
        st = waters.state_of(r, level, sky)
        lines.append({"key": r.key, "name": r.name, "size": r.size,
                      "state": st, "words": waters.WORDS[st],
                      "days": round(waters.DELAY.get(st, 0.0), 1)})
    spans = []
    for b in game.world.bridges:
        if b.owner != "player":
            continue
        river = game.world.river(b.river)
        spans.append({"uid": b.uid, "name": b.name,
                      "river": river.name if river else "",
                      "broken": b.broken, "days_left": b.days_left,
                      "standing": b.standing,
                      "toll": round(game.toll_on(b), 1) if b.standing else 0.0})
    threat = []
    for a in game.armies:
        if a.owner == "player" or a.state != MARCHING:
            continue
        if a.bound_for not in game.world.settlements:
            continue
        for r, x, y, bridge in game.world.crossings(a.at or a.home, a.bound_for):
            if bridge is not None and bridge.owner == "player":
                threat.append({"uid": bridge.uid, "bridge": bridge.name,
                               "host": a.name, "river": r.name,
                               "days": round(a.days_left, 1)})
    want = game.worst_unbridged()
    offer = None
    if want is not None and want[2].ford_limit <= waters.WORTH_BRIDGING:
        offer = {"from": want[0], "to": want[1], "river": want[2].name,
                 "where": game.world.node_name(want[0]),
                 "afford": game.treasury >= waters.BRIDGE_COST}
    return {"stage": round(level, 2), "forecast": waters.forecast(game.season),
            "rivers": lines, "bridges": spans, "threat": threat, "offer": offer,
            "cost": waters.BRIDGE_COST, "build_days": waters.BRIDGE_DAYS,
            "mend": round(waters.BRIDGE_COST * waters.REBUILD_SHARE)}


def _siege_view(game, s, key: str = "") -> Optional[dict]:
    """What a defender needs to decide with, and nothing he cannot see.

    A besieged player was being told the ring was there and given no numbers
    to act on: the console had `shore` and `sally` from the day they were
    written, and the picture had neither. Both levers turn on three
    readings -- what the wall has left, what stone is in store to shore it
    with, and whether there are engines outside worth going out at.
    """
    if not s.besieged:
        return None
    outside = [a for a in game.armies
               if a.owner != "player" and a.state == BESIEGING
               and game.world.node_name(a.at) == s.name]
    engines, guard = 0.0, 0.0
    for host in outside:
        for unit, n in host.units.items():
            if UNITS[unit].siege_power > 0 or unit == "engineer":
                engines += n
            else:
                guard += n
    # What a sortie would risk, at each size the panel offers. Shown before
    # it is ordered, because the whole of the rework is that the player is
    # choosing odds rather than pressing a button.
    fld = game.field_at(key)
    sat = max((a.siege_days for a in outside), default=0)
    tries = []
    for share, label in ((0.15, "a handful"), (0.3, "a quarter of them"),
                         (0.5, "half the garrison"), (0.8, "most of it"),
                         (1.0, "everyone")):
        o = military.sortie_odds(share, fld.weather, sat, s.sorties)
        tries.append({"share": share, "label": label,
                      "surprise": round(o.surprise, 2), "words": o.words,
                      "helps": o.helps, "hurts": o.hurts})
    return {
        "shoring": s.shoring,
        "sorties": s.sorties,
        "odds": tries,
        "stone": round(s.market.stock.get("stone", 0.0)),
        "men": round(sum(s.units.values())),
        "wall": round(s.wall_hp, 1),
        "wall_max": round(s.wall_max(game.progress), 1),
        # The sortie is aimed at the works, not at the host, so the host's
        # own size is the wrong number to show a man deciding whether to
        # open the gate. These two are the right ones.
        "engines": round(engines),
        # Both halves of the bet, because there is no single number any
        # more: this is what stands over the works if you are not seen, and
        # what turns out if you are.
        # What is in his wagons, in days -- the other thing a sortie can be
        # aimed at, and the only reading that says whether it is worth it.
        "stores_out": round(max(
            (supply.days_left(a.size, a.stores) for a in outside), default=0.0)),
        "guard": round(guard * military.SORTIE_QUIET),
        "roused": round(guard * military.SORTIE_ROUSED),
        "host": round(sum(a.size for a in outside)),
    }


#: The piles that sit along the top of the screen, and what goes into each.
#: Six, because Age of Empires got by on four and Stronghold's stockpile
#: showed you twenty and nobody read it: the ones a player acts on, in the
#: order the town needs them. Food is not here -- it is counted in days.
STORES = (
    ("wood", "wood", ("wood", "planks")),
    ("stone", "stone", ("stone",)),
    ("iron", "iron", ("iron_ore", "iron")),
    ("ale", "ale", ("ale", "hops")),
    ("arms", "arms", ("spears", "bows", "armour", "weapons")),
)


def _stores(game, s) -> dict:
    """What is in the town's yards, read the way a top bar reads it.

    Food as days rather than units, because four hundred cheese and four
    hundred wheat are not the same four hundred and the only question the
    number is asked is "how long have I got". The rest are plain piles, each
    with what it is made of, so the tooltip can say why "wood" is 212 when
    the forester has only cut 90.
    """
    stock = s.market.stock
    per_head, _mood = C.RATION_LEVELS[s.ration_level]
    need = per_head * s.population
    rations = goods_mod.nourishment(
        {k: stock.get(k, 0.0) for k in goods_mod.RATION_GOODS})
    # What each pile is now against what it was when the day began: the
    # whole of the change, where adding up made, used and eaten left out the
    # building, the mending, the rot and the road, and so showed wood rising
    # on the very day it was being spent.
    opened = s.report.opened

    def change(k):
        if opened is None:
            return 0.0
        return stock.get(k, 0.0) - opened.get(k, 0.0)

    def pile(keys):
        return {k: round(stock.get(k, 0.0)) for k in keys
                if stock.get(k, 0.0) >= 0.5}

    def moved(keys):
        return round(sum(change(k) for k in keys), 1)

    # Food moves in rations, like the pile it belongs to: a day that turned
    # ten wheat into eight bread moved the units and barely moved the meals.
    fed = round(sum(change(k) * goods_mod.GOODS[k].nourish
                    for k in goods_mod.RATION_GOODS), 1)
    out = [{"key": "food", "label": "food",
            "have": round(rations),
            "days": round(rations / need, 1) if need > 0 else None,
            "of": pile(goods_mod.RATION_GOODS),
            "moved": fed}]
    for key, label, keys in STORES:
        out.append({"key": key, "label": label,
                    "have": round(sum(stock.get(k, 0.0) for k in keys)),
                    "of": pile(keys), "moved": moved(keys)})
    held = sum(v for v in stock.values() if v > 0)
    return {"piles": out, "held": round(held),
            "room": round(s.storage(game.progress))}


def _book(s) -> dict:
    """The two levers the scribe's book is for, each band priced.

    What every ration and tax band would do to the mood, and what each tax
    band would collect, so the book can offer the whole dial rather than a
    "more" and a "less". The same figures `tax` prints on the console.
    """
    return {
        "rations": [{"level": k, "label": C.RATION_LABELS[k],
                     "mood": mood, "now": k == s.ration_level}
                    for k, (_per, mood) in sorted(C.RATION_LEVELS.items())],
        "tax": [{"level": k, "label": C.TAX_LABELS[k], "mood": mood,
                 "collects": round(s.tax_take(k), 1), "now": k == s.tax_level}
                for k, (_rate, mood) in sorted(C.TAX_LEVELS.items())],
    }


_GAMES = itertools.count(1)


def _which_game(game) -> int:
    """A number for this game, new each time one is begun or read back.

    The page tells a day that happened from a game that was loaded by
    whether this changed. Comparing the day and the place was a guess that
    a new game followed by an early save of the same country got past, and
    heralded the save's feats and sounded its siege as though both were
    news. Kept on the object and never written to a save, so a save read
    back is always a different game from the one that wrote it.
    """
    if getattr(game, "_web_game", None) is None:
        game._web_game = next(_GAMES)
    return game._web_game


def snapshot(game, here: str = "") -> dict:
    """Everything the picture needs, and nothing it does not."""
    key = here or next(iter(game.world.settlements))
    s = game.world.settlements[key]
    led = game.ledger
    return {
        "game": _which_game(game),
        "day": game.day,
        "date": game.date_str(),
        # The three you govern with. Not a fourth resource bar: what each one
        # is worth is a multiplier on something the game already does, so the
        # panel shows the multiplier rather than a mood face.
        "estates": [
            {"key": k, "name": spec.name, "blurb": spec.blurb,
             "gives": spec.gives,
             "loyalty": round(game.estates.by_key[k].loyalty),
             "worth": round(game.estates.mult(spec.gives), 3),
             "held": list(game.estates.by_key[k].privileges),
             "why": [{"what": w, "by": b}
                     for w, b in game.estates.why(k, game.day)[:4]]}
            for k, spec in estates_mod.ESTATES.items()],
        # Your house's own path. Only what is open and what is done, because
        # a mission you cannot start yet is not something to do next.
        "missions": {
            "house": game.house,
            "done": len(game.missions.to_dict()),
            "of": len(missions_mod.tree(game.house)),
            "open": [{"key": m.key, "name": m.name, "asks": m.asks,
                      "costs": m.costs, "pays": m.reward_words(),
                      "mine": bool(m.house)}
                     for m in game.missions.open(game.house)],
            "won": [{"key": m.key, "name": m.name,
                     "day": game.missions.to_dict()[m.key]}
                    for m in missions_mod.tree(game.house)
                    if m.key in game.missions.to_dict()],
        },
        "feats": {"done": len(game.feats.to_dict()),
                  "of": len(feats_mod.FEATS),
                  "list": [{"key": k, "name": f.name, "blurb": f.blurb,
                            "hard": f.hard,
                            "day": game.feats.to_dict().get(k)}
                           for k, f in feats_mod.FEATS.items()]},
        "privileges": [
            {"key": k, "estate": p.estate, "name": p.name, "blurb": p.blurb,
             "cost": p.cost, "held": game.estates.granted(k)}
            for k, p in estates_mod.PRIVILEGES.items()],
        "year": game.year,
        "month": game.month,
        "season": game.season,
        "over": game.over,
        "chapter": game.chapter,
        "treasury": round(game.treasury, 1),
        "net_worth": round(game.net_worth(), 1),
        # Where the race stands, projected. The same reading the console
        # gives, because two interfaces that disagree about whether you are
        # winning are worse than one.
        # The table, and who has said they are coming. Both halves of a league:
        # where everyone stands, and what is on the schedule.
        "league": {
            "year": game.league.season.year,
            "place": game.league.season.place(LEAGUE_PLAYER),
            "table": [{"key": r.key, "name": r.name or r.key, "lord": r.lord,
                       "towns": r.towns, "won": r.won, "lost": r.lost,
                       "muster": round(r.muster),
                       "me": r.key == LEAGUE_PLAYER}
                      for r in game.league.season.table()],
            "fixtures": [{"who": f.who, "target": f.target,
                          "at_you": f.target in game.world.settlements,
                          "reason": getattr(f, "reason", "")}
                         for f in game.league.season.fixtures if not f.done],
            "clock": game.league.season.on_the_clock(),
            "left": len(game.league.season.undrafted()),
        },
        "pace": [{"what": w, "now": round(n, 1), "want": round(k, 1),
                  "land": round(l, 1)} for w, n, k, l in game.pace()],
        "goals": {"net_worth": game.goals.net_worth,
                  "population": game.goals.population,
                  "towns": game.goals.towns,
                  "days": game.goals.days,
                  "paths": list(game.goals.paths)},
        "lord": {"name": game.lord.name,
                 "standing": game.lord.standing(game.world.node_name)},
        # The house, small enough to sit in a panel and complete enough to
        # follow: who they are, how old, what they are doing, what it made them.
        "kin": [{"name": p.name,
                 "age": p.age(game.day),
                 "head": p.uid == game.kin.head,
                 "doing": p.doing(game.world.node_name),
                 "skill": _best_skill(p)}
                for p in sorted(game.kin.living(),
                                key=lambda q: (q.uid != game.kin.head, q.born))],
        "reputation": (game.kin.lord.reputation() if game.kin.lord else []),
        # The macro reading. Four numbers, because a dashboard with twenty is
        # a dashboard nobody reads.
        "accounts": {
            "cpi": round(game.accounts.cpi, 1),
            "inflation": round(game.accounts.inflation, 1),
            "unemployment": round(game.accounts.unemployment, 1),
            "real_purse": round(100.0 * game.treasury
                                / max(game.accounts.cpi, 1e-9), 1),
            "minted": round(game.economy.minted, 1),
            "short": [{"good": k, "by": round(v, 3)}
                      for k, v in game.economy.shortage.items() if v > 0.01],
        },
        "here": key,
        # What this place is built out of, so the renderer can draw it in its
        # own idiom rather than in the one idiom it used to have.
        "culture": _culture(s),
        # Every idiom, not only yours -- so a town on the march map can be
        # drawn in its own. Seeing whose town it is from the roofline is the
        # whole point of having more than one.
        "idioms": {c.key: _idiom(c) for c in cultures.CULTURES.values()},
        # The politics: who thinks what, who has signed, and who is waiting
        # on an answer. The same reading `court` prints.
        "court": _court(game),
        # The castle, read: what you drew and what a besieger makes of it.
        # The same numbers `castle` prints, because there is one answer.
        "castle": _castle(s),
        # What the street would say, for a roof somebody clicks on. The same
        # facts as the mood breakdown, from somebody who has to live in it.
        "street": [{"who": who, "said": said}
                   for who, said in voices.speak(s, game, voices.street_rng(s, game), 2)],
        # What the next hand in each shed would be worth, so a roof you click
        # can tell you whether it is paying for itself. The same reading
        # `margin` gives, attached to the thing it is about.
        "margin": {r.uid: {"net": round(r.net, 2), "wage": C.WAGE,
                           "staffed": r.staffed, "jobs": r.jobs,
                           # Hands you put there by name, ahead of the queue.
                           "pinned": s.pins.get(r.uid, 0),
                           # Why the queue put it where it did.
                           "demand": next((b.demand_note for b in s.buildings
                                           if b.uid == r.uid), "")}
                   for r in marginal_hands(s)},
        "settlements": list(game.world.settlements),
        "town": {
            "name": s.name,
            "population": round(s.population, 1),
            "housing": round(s.housing(game.progress), 1),
            "popularity": round(s.popularity, 1),
            "workforce": round(s.workforce, 1),
            "employed": round(s.employed, 1),
            "soldiers": s.soldiers,
            "wall_hp": round(s.wall_hp, 1),
            "wall_max": round(s.wall_max(game.progress), 1),
            "besieged": s.besieged,
            # The sickness, the gates, and what your carts have reported.
            # Fogged like everything else: a town nobody of yours has been
            # to lately is a town you know nothing about.
            "sick": {
                "here": s.sick.here,
                "words": plague_mod.words(s.sick, game.day),
                "dead": round(s.sick.dead),
                "buried": round(s.buried),
                "shut": s.shut,
                "word": game.word_of_sickness(),
            },
            "siege": _siege_view(game, s, key),
            "water": _water_view(game),
            "field": _field_view(game, key),
            "raided": s.raided,
            "blockaded": s.blockaded,
            "fires": len(s.fires.blazes),
            "rations": s.ration_level,
            "tax": s.tax_level,
            "mood": [{"what": k, "by": round(v, 1)} for k, v in s.mood_factors(
                game.progress) if v],
            # Where the mood is going, not only where it is. Stronghold put a
            # number and the direction it was moving side by side, and the
            # direction is the half you act on: 62 and falling is a worse
            # town than 48 and rising. The same sum `update_mood` pulls
            # toward, so the arrow cannot disagree with tomorrow.
            "heading": round(max(0.0, min(100.0, 50.0 + sum(
                v for _, v in s.mood_factors(game.progress)))), 1),
            "arriving": round(s.report.migration, 1),
            "book": _book(s),
        },
        # The yards, as a top bar reads them. See `_stores`.
        "stores": _stores(game, s),
        "ledger": {"taxes": round(led.taxes, 1), "trade": round(led.trade, 1),
                   "tribute": round(led.tribute, 1), "wages": round(led.wages, 1),
                   "upkeep": round(led.upkeep, 1), "net": round(led.net, 1)},
        "plan": plan_for(s, officers=_officers(game, key)).to_dict(),
        "caravans": len(game.caravans),
        "age": game.progress.age_name(),
        "relics": game.relics_held(),
        # Off `marchlands.__version__`, which is the one place it is written
        # and the thing the release workflow keys on. Two downloads called
        # Marchlands.exe are otherwise indistinguishable in a downloads
        # folder, and the first bug report against the wrong one costs more
        # than this line.
        "version": __version__,
        # The fight the day is waiting on, if there is one. Top level, not
        # under the town: the day has stopped on it wherever you are looking.
        "battle": game.battle_view(),
    }


class Handler(BaseHTTPRequestHandler):
    console: Console = None            # set on the server before serving
    lock = threading.Lock()

    def log_message(self, fmt, *args) -> None:      # quiet by default
        pass

    # ------------------------------------------------------------- plumbing
    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), TYPES[".json"])

    def _static(self, path: str) -> None:
        name = os.path.basename(path) or "index.html"
        full = os.path.join(STATIC, name)
        if not os.path.isfile(full):
            return self._send(404, b"no such thing", "text/plain")
        ext = os.path.splitext(name)[1]
        with open(full, "rb") as fh:
            self._send(200, fh.read(), TYPES.get(ext, "text/plain"))

    # --------------------------------------------------------------- routes
    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route in ("/", "/index.html"):
            return self._static("index.html")
        if route == "/favicon.ico":
            return self._send(200, b"", "image/x-icon")
        if route == "/state":
            # `since` is the browser's place in the clock's stream. Without it
            # a poll that lands after three days have passed would show the
            # last one and quietly eat the other two.
            q = parse_qs(urlparse(self.path).query)
            try:
                since = int(q.get("since", ["-1"])[0])
            except ValueError:
                since = -1
            with self.lock:
                out = snapshot(self.console.game, self.console.here)
            if CLOCK is not None:
                out["clock"] = CLOCK.state()
                if since >= 0:
                    out["said"] = CLOCK.since(since)
            return self._json(out)
        if route == "/commands":
            # Straight off the console's own registry, so the palette cannot
            # drift from what the game will actually accept.
            return self._json(catalogue())
        if route == "/options":
            with self.lock:
                return self._json(options(self.console.game, self.console.here))
        if route == "/march":
            good = (urlparse(self.path).query.split("good=")[-1].split("&")[0]
                    if "good=" in self.path else "bread")
            with self.lock:
                return self._json(march(self.console.game, self.console.here, good))
        if route == "/clock":
            return self._json(CLOCK.state() if CLOCK else {"speed": 0})
        if route == "/folk":
            # Somebody clicked a person. The index is the figure's place in
            # the plan, which is stable while the town is: the plan is laid
            # out deterministically and the folk are built by index off it.
            q = parse_qs(urlparse(self.path).query)
            try:
                i = int(q.get("i", ["-1"])[0])
            except ValueError:
                return self._json({"error": "nobody there"})
            with self.lock:
                return self._json(folk(self.console.game, self.console.here, i))
        if route == "/beast":
            q = parse_qs(urlparse(self.path).query)
            try:
                i = int(q.get("i", ["-1"])[0])
            except ValueError:
                return self._json({"error": "nothing there"})
            with self.lock:
                return self._json(beast(self.console.game,
                                        self.console.here, i))
        if route == "/front":
            # What the front door needs: who you can be, what you can play,
            # and whether there is a game waiting to be picked back up. A
            # packaged build has to be able to start without anybody typing,
            # and this is everything that screen asks for.
            from .scenarios import CAMPAIGN, SCENARIOS
            from .tech import HOUSES
            save = _save_path()
            return self._json({
                "houses": [{"key": k, "name": h.name, "blurb": h.blurb}
                           for k, h in HOUSES.items()],
                # What you are, as against who: the same map, a different
                # place to be standing on it.
                "roles": [{"key": k, "name": r.name, "blurb": r.blurb,
                           "problem": r.problem}
                          for k, r in roles_mod.ROLES.items()],
                "scenarios": [{"key": k, "name": SCENARIOS[k].name,
                               "blurb": SCENARIOS[k].blurb,
                               "years": SCENARIOS[k].years}
                              for k in CAMPAIGN if k in SCENARIOS],
                "regions": [{"key": r.key, "name": r.name, "note": r.note}
                            for r in carto.REGIONS.values()],
                "saved": os.path.exists(save),
                "save_path": save,
                "open": SHOW_FRONT,
            })
        if route == "/regions":
            # Everything the slider screen needs to draw itself: the dials,
            # what each setting is called in words, and the six real places.
            return self._json({
                "dials": list(carto.DIAL_NAMES),
                "regions": [
                    {"key": r.key, "name": r.name, "note": r.note,
                     "dials": r.dials.as_dict()}
                    for r in carto.REGIONS.values()],
                "words": {name: [carto.describe(_at(name, v))[0][2]
                                 for v in (0.0, 0.3, 0.6, 1.0)]
                          for name in carto.DIAL_NAMES if name != "towns"},
            })
        if route == "/draw":
            # A preview. Drawing is cheap and starting a game is not, so the
            # sliders can be moved as fast as anybody likes and the country
            # redraws under them without a game being made at all.
            q = parse_qs(urlparse(self.path).query)
            try:
                dials = _dials_from(q)
            except KeyError as exc:
                return self._json({"error": str(exc)})
            plan = carto.draw(q.get("region", [carto.DEFAULT_REGION])[0],
                              int(q.get("seed", ["7"])[0]), dials)
            return self._json(_preview(plan))
        if route == "/chronicle":
            with self.lock:
                g = self.console.game
                return self._json({"entries": [
                    {"stamp": e.stamp(), "text": e.text.strip("* "),
                     "weight": e.weight, "chapter": e.chapter}
                    for e in g.chronicle.read(limit=80)]})
        return self._static(route)

    def do_POST(self) -> None:
        if urlparse(self.path).path == "/march-here":
            # Draw the country the sliders are set to, and play it. The
            # console keeps the same identity -- it is the same seat at the
            # same table, looking at a different country.
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            q = {k: [str(v)] for k, v in body.items()}
            try:
                dials = _dials_from(q)
            except KeyError as exc:
                return self._json({"error": str(exc)})
            with self.lock:
                from .scenario import drawn_game
                self.console.game = drawn_game(
                    body.get("region", carto.DEFAULT_REGION),
                    seed=int(body.get("seed", 7)),
                    house=body.get("house", "plough"), dials=dials)
                self.console.game.battles_mode = "play"
                self.console.here = next(iter(self.console.game.world.settlements))
                return self._json({
                    "said": self.console.game.briefing,
                    "state": snapshot(self.console.game, self.console.here)})
        route = urlparse(self.path).path
        if route == "/speed":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            if CLOCK is None:
                return self._json({"error": "no clock"})
            return self._json(CLOCK.set_speed(int(body.get("speed", 0))))
        if route in ("/new", "/save", "/load"):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            with self.lock:
                return self._json(_front_door(self.console, route, body))
        if route != "/do":
            return self._send(404, b"no such thing", "text/plain")
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "that was not json"}, 400)
        line = str(payload.get("line", ""))[:400]
        with self.lock:
            said = run_command(self.console, line)
            state = snapshot(self.console.game, self.console.here)
        return self._json({"said": said, "state": state})


def run_command(console: Console, line: str) -> str:
    """Run one console command and capture what it said."""
    buffer = StringIO()
    was, console.out = console.out, buffer
    try:
        if line.strip():
            console.do(line)
    finally:
        console.out = was
    return buffer.getvalue()


class _Server(ThreadingHTTPServer):
    """A server that refuses to quietly share its port.

    `HTTPServer` sets SO_REUSEADDR, and that flag does not mean the same
    thing on both sides of the world. On Unix it only means "do not make me
    wait out TIME_WAIT". On Windows it means this socket may bind a port
    another program is *actively listening on*, after which the operating
    system hands each incoming connection to one of the two more or less
    arbitrarily.

    The consequence was not theoretical. The bind below cannot fail on
    Windows, so the port walk never runs, and a player who double-clicked
    Marchlands while anything else sat on 8731 got a browser window pointed
    at that other server -- in the case this was found from, a directory
    listing of their own home folder. Turning the flag off on Windows makes
    an occupied port raise, which is what the walk is for.
    """

    allow_reuse_address = os.name != "nt"


def serve(console: Console, host: str = "127.0.0.1", port: int = 8731,
          open_browser: bool = True) -> Tuple[ThreadingHTTPServer, str]:
    global CLOCK
    Handler.console = console
    # A fight your men are in stops the day here and waits for you. Set on
    # the surface rather than on the game, because a save taken in the
    # window and loaded headless must not stop a test on a wall.
    console.game.battles_mode = "play"
    # Same lock the request handler takes, not a second one: the clock is
    # another writer of the same game, and two writers with two locks is not
    # locking.
    CLOCK = Clock(console, Handler.lock)
    # Somebody already on that port is the commonest way this fails, and a
    # traceback about EADDRINUSE is not an answer. Walk up a few and then let
    # the operating system pick.
    server = None
    for candidate in [port, port + 1, port + 2, port + 3, 0]:
        try:
            server = _Server((host, candidate), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise OSError(f"nothing free to listen on near port {port}")
    url = f"http://{host}:{server.server_address[1]}/"
    if open_browser:
        # A machine with no browser to open is not an error either.
        def _open() -> None:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Timer(0.6, _open).start()
    return server, url


def main(game=None, port: int = 8731, open_browser: bool = True,
         front: bool = False) -> int:
    global SHOW_FRONT
    SHOW_FRONT = front
    from .scenarios import start
    console = Console(game or start(), out=StringIO())
    server, url = serve(console, port=port, open_browser=open_browser)
    print(f"  Marchlands is at {url}")
    print("  ctrl-c to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        if CLOCK is not None:
            CLOCK.close()
        server.server_close()
    return 0
