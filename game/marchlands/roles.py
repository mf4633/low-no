"""What you are, as distinct from who you are.

The house you pick changes your bonuses and your architecture. It does not
change your *situation*: every game in this codebase has opened the same way,
with one hill, a full treasury and nobody's permission needed for anything,
and the only question has been how you spend the next three years.

The sandbox everybody praises in Bannerlord is not really about freedom of
movement. It is that you can be a *different kind of person in the same
world*: a merchant who never fights, a mercenary with a company and no land,
a vassal who owes somebody, a king with more to lose than anyone. The map is
identical; what differs is where you start standing on it and what counts as
winning.

So a role is three things and no new subsystems:

* **A different opening position.** Carts instead of walls; a host instead of
  a granary; a debt instead of a treasury.
* **A different definition of winning.** The merchant is not asked to hold
  towns. The king is asked to keep the ones he has.
* **A different first problem.** Stated in the briefing, because a player
  who does not know what their problem is will default to the last game's.

Each is built from what the game already does. A role that needed a new
mechanic would be a role I could not test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Tuple

from . import config as C


@dataclass(frozen=True)
class Role:
    key: str
    name: str
    blurb: str                  # what you are, in one line
    problem: str                # and what your first problem is
    setup: Callable[["GameState"], None]
    #: Which victory paths are open to you. The engine already reads these.
    paths: Tuple[str, ...] = ("wealth", "dominion", "bells", "reliquary")


def _merchant(g) -> None:
    """Carts and coin, and a wall you cannot afford to man.

    The trading game already exists and has never been a *starting position*
    -- you could choose to play it, but you began with the same spearmen as
    everybody else. This begins with the carts and without the garrison, so
    the first raid is a real problem rather than an inconvenience.
    """
    seat = g.home()
    g.treasury += 6_000.0
    for k in list(seat.units):
        seat.units[k] = max(0.0, seat.units[k] * 0.35)
    # The limit on trains is earned by building for it, and it is the
    # merchant's whole trade -- leaving him at a lord's two meant the role's
    # defining feature quietly did not happen. So he starts with the posts
    # that earn it, rather than with the rule bent for him.
    for _ in range(2):
        seat.start_build("trading_post").days_left = 0
    for i in range(3):
        _c, why = g.new_caravan(next(iter(g.world.settlements)),
                                name=f"Pack {i + 1}")
        if why:
            break
    g.goals.towns = 99            # not your business
    g.goals.net_worth = C.GOAL_NET_WORTH * 1.15
    g.briefing = (
        "You are a merchant with a charter and a hill nobody envies. Three "
        "trains on the road, coin enough to lose some of it, and a garrison "
        "you could count from the gate. Nobody is asked to swear to you and "
        "you are asked to swear to nobody. Get rich enough that it stops "
        "mattering -- and remember that a road you do not police is a road "
        "somebody else does.")


def _mercenary(g) -> None:
    """A company, and somebody else's war to spend it in.

    No contract system was written for this, and none is needed: a mercenary
    is a man whose army costs more than his land earns, and this game already
    charges upkeep by the day. The pressure is the arithmetic.
    """
    seat = g.home()
    g.treasury = max(1_400.0, g.treasury * 0.6)
    # Sized against the village that has to feed it. A hundred and ten men
    # cost a hundred and six a day against sixty in tax: forty-five a day of
    # bleed on thirteen days of runway, which is not a hard opening, it is a
    # decided one. Raiding does not close a gap that size either, so the
    # company was a death sentence whatever the player did -- and a role you
    # cannot play is not a role. At this size the captain breaks about even
    # standing still, and the pressure is the right one: an army that earns
    # nothing where it is.
    seat.units.update({"spearman": seat.units.get("spearman", 0.0) + 26,
                       "archer": seat.units.get("archer", 0.0) + 12,
                       "man_at_arms": seat.units.get("man_at_arms", 0.0) + 7})
    seat.population = max(70.0, seat.population * 0.7)
    g.goals.towns = 2
    g.goals.net_worth = C.GOAL_NET_WORTH * 0.65
    g.briefing = (
        "You are a captain with a company and almost nothing else: a hundred "
        "men under arms, a village that cannot feed them, and a purse that "
        "empties every morning at dawn. Nobody owes you anything. Get paid -- "
        "by plunder, by tribute, or by making yourself expensive enough to "
        "buy off -- before the upkeep gets you.")


def _vassal(g) -> None:
    """Sworn to somebody bigger, and paying for the privilege.

    Vassalage is modelled with the pieces that exist: a standing truce with
    your liege so he will not come for you, a tribute leaving your chest
    every day, and his favour high enough that breaking it will be expensive.
    """
    liege = max((k for k, t in g.world.towns.items() if not t.mine),
                key=lambda k: g.world.towns[k].muster)
    t = g.world.towns[liege]
    t.truce_days = 400
    t.favour += 40.0
    t.hostility = 0.0
    g.liege = liege
    g.treasury = max(400.0, g.treasury * 0.4)
    g.goals.towns = 2
    g.goals.paths = ("wealth", "dominion")
    name = g.world.node_name(liege)
    g.briefing = (
        f"You hold this valley from {name}, and he does not let you forget "
        f"it. His peace keeps the others off you and his reeve takes a cut "
        f"of everything that moves. It is a good arrangement for exactly as "
        f"long as you are small. Grow out of it -- and decide, before he "
        f"does, whether you are buying your way out or fighting your way "
        f"out.")


def _king(g) -> None:
    """Two holdings and everybody's attention.

    The interesting thing about starting ahead is that this game already
    punishes it: aggressive expansion, coalitions and the opinion ledger all
    read how much you hold. A king does not need a handicap written for him.
    He needs to be given what he has.
    """
    keys = [k for k, t in g.world.towns.items() if not t.mine]
    near = sorted(keys, key=lambda k: g.world.towns[k].muster)[:1]
    for key in near:
        g.world.towns[key].owner = "player"
        g.world.towns[key].garrison = {"spearman": 24.0, "archer": 12.0}
    g.treasury += 2_500.0
    for key, t in g.world.towns.items():
        if not t.mine:
            t.hostility += 18.0
            t.temper *= 1.25
    g.goals.towns = max(4, g.goals.towns)
    g.briefing = (
        "You begin with two holdings and the suspicion of everyone who has "
        "one. That is the whole of your advantage and the whole of your "
        "problem: every lord on this march can count, and what they have "
        "counted is that you are the largest thing on it. Hold what you have "
        "-- the letter against you is already being drafted.")


ROLES: Dict[str, Role] = {r.key: r for r in [
    Role("lord", "a lord of the march",
         "the way this game has always opened: one hill, a full chest, "
         "nobody's leave to ask",
         "everything at once, and three years to do it in",
         setup=lambda g: None),
    Role("merchant", "a merchant",
         "carts and coin, and a garrison you could count from the gate",
         "a road you do not police",
         setup=_merchant, paths=("wealth",)),
    Role("mercenary", "a captain of free lances",
         "a company that costs more than your land earns",
         "the upkeep, every morning at dawn",
         setup=_mercenary, paths=("wealth", "dominion")),
    Role("vassal", "a vassal",
         "somebody else's peace, and his reeve taking a cut",
         "growing out of an arrangement that only suits you while you are small",
         setup=_vassal, paths=("wealth", "dominion")),
    Role("king", "a king already",
         "two holdings and the suspicion of everyone who has one",
         "being the largest thing on a march that can count",
         setup=_king),
]}

DEFAULT = "lord"


def apply(g, key: str) -> str:
    """Put a game into a role. Returns what changed, in words."""
    role = ROLES.get(key or DEFAULT)
    if role is None:
        return (f"there is no role called {key!r}; try "
                + ", ".join(sorted(ROLES)))
    role.setup(g)
    g.role = role.key
    g.goals.paths = role.paths
    return role.blurb
