"""Headless runs, for balance work rather than play.

A bot that plays adequately is the cheapest balance test there is: if a naive
policy starves by month four the numbers are wrong, and if it wins the game
without ever reading a price they are wrong in the other direction.
"""

from __future__ import annotations

import argparse
from typing import ClassVar, Dict, List, Optional

from . import config as C
from .advisor import FAST_STEPS, route_from, scan
from .engine import GameState
from .tech import TECHS
from .kin import SKILLS
from .goods import RATION_GOODS, good, nourishment
from .military import BESIEGING, UNITS, host_strength
from .trade import MOVING, SHIP, Order, Stop
from . import supply

# Feed the town, then work up the chain. Order is a preference, not a queue --
# the bot takes the first thing it can actually afford and has land for.
HOME_PLAN = [
    # feed the town
    "farm", "mill", "bakery", "quarry", "orchard", "granary", "woodcutter",
    "farm", "mill", "bakery", "trading_post", "sawmill", "poleturner",
    "farm", "mill", "bakery", "orchard", "cottage", "guildhall",
    # make something worth carrying
    "clay_pit", "kiln", "cottage", "market", "farm", "mill", "bakery",
    "fletcher", "stone_wall", "sheep_farm", "weaver", "poleturner", "brewery",
    # grow, and start thinking about the walls
    "inn", "townhouse", "charcoal_burner", "iron_mine", "smelter",
    "stone_wall", "townhouse", "warehouse", "blacksmith", "wall_tower",
    "iron_mine", "smelter", "armoury", "armourer", "townhouse", "stable",
    "trading_post", "chapel", "pitch_ditch",
    "fletcher", "townhouse", "wall_tower", "gatehouse", "garden",
    "guardhouse", "townhouse", "siege_yard", "oil_pot", "moat",
    "townhouse", "cottage", "kill_pit",
]
COLONY_PLAN = [
    "woodcutter", "cottage", "farm", "sawmill", "quarry", "saltworks",
    "orchard", "harbour", "cottage", "mill", "bakery", "clay_pit", "granary",
    "iron_mine", "charcoal_burner", "smelter", "cottage", "market", "palisade",
    "townhouse", "barracks", "poleturner", "stone_wall", "townhouse",
]

#: Days a new cart is given to clear its own upkeep before it is sold off.
#: Long enough for a slow route with a bad first season, short enough that a
#: dead route is not paid for all year.
CART_TRIAL = 40

#: What share of a garrison goes out of the gate. A quarter, because a
#: sortie is a bet on not being seen forming up -- see military.sortie_odds
#: and the table in tests/test_siege.py.
SORTIE_SHARE = 0.3

#: And the most food a besieger can be carrying for burning it to be worth
#: the men. One raid takes about a third of a camp.
TORCH_UNDER = 60.0


class Bot:
    """A plain policy, used as a balance test rather than an opponent.

    It has one rule that matters: never spend the wage chest. Everything else
    is a priority ladder -- eat, defend, climb, build, learn, buy, expand --
    drawn from whatever is left after a month's payroll is set aside. Most of
    the ways a real player goes broke are ways this rule prevents.
    """

    def __init__(self, game: GameState, verbose: bool = False) -> None:
        #: The smoothed daily loss the reserve is built on. See `burn`.
        self._burn = 0.0
        self.game = game
        self.plans: Dict[str, List[str]] = {}
        self.verbose = verbose
        self.home = next(iter(game.world.settlements))
        self.supply_cart: Optional[int] = None
        self.errand: Optional[tuple] = None    # (cart uid, good, target stock)
        self._survey: List = []                # the last market survey
        self._scanned_on = -99
        #: Which of your towns has already sent its garrison out at the
        #: works. Once each: a sortie is a thing you spend, not a tactic.
        self._sallied: Dict[str, bool] = {}
        #: And which has put a torch in his baggage. Also once: the camp
        #: watches the gate harder after every sortie of either kind.
        self._torched: Dict[str, bool] = {}
        #: The day each cart joined the fleet, so the bot can tell a cart
        #: that has not yet paid for itself from one that never will.
        self._bought: Dict[int, int] = {}

    def plan_for(self, key: str) -> List[str]:
        if key not in self.plans:
            self.plans[key] = list(HOME_PLAN if key == self.home else COLONY_PLAN)
        return self.plans[key]

    # ------------------------------------------------------------- the purse
    #: The wage chest. Flat on purpose: a reserve that grows with the payroll
    #: throttles the very growth that pays the payroll, and the town stalls.
    RESERVE_BASE = 900.0
    RESERVE_PER_CART = 40.0

    #: Days of the current burn the bot wants in hand before it lays out
    #: coin on anything that is not food or defence.
    #:
    #: The flat reserve above is a floor, not a policy. It assumes income,
    #: and the two ways a run of this game dies are both ways income stops:
    #: a ring closed round the seat, and a gate shut against the sickness.
    #: The siege case was special-cased in `step` after it had bankrupted a
    #: town that held its wall. The sickness case had not been, and it went
    #: on doing the same thing -- measured over sixteen seeds the two worst
    #: runs of the game both ended "Ruined. Your debts outran your carts",
    #: one of them on day 386 with a sickness in the capital and the masons
    #: still out.
    #:
    #: A runway is the rule both cases are instances of, so neither needs
    #: its own clause: on a day the town is losing three hundred coin, the
    #: bot wants a month of that in hand before it starts a bakery. When
    #: the day paid for itself this is zero and the floor applies.
    #: Chosen on the mechanism, not on a median. Swept over sixteen seeds
    #: at 0, 7, 14, 22 and 30 days: every non-zero value took ruin from two
    #: runs in sixteen to none, and the medians bounced between forty-two
    #: and sixty-eight thousand with no order to them -- which is what a
    #: five-to-one spread does to sixteen samples, and reading the best of
    #: them as "the right number" is how this codebase has been burnt
    #: before. So: a fortnight, because that is half a sickness (plague.LIFE
    #: is sixty-two days) and most of the twenty-one a besieger will sit at
    #: a wall, and because over-reserving costs growth while under-reserving
    #: costs the run.
    #:
    #: It does not narrow the spread and was not expected to. Net worth
    #: tracks trade profit at +0.95 and trade compounds, so nine hundred
    #: days of it fans out however well the bot plays. That is an economy.
    #: What the runway removes is the tail where the bot goes bankrupt with
    #: masons in the yard, which is not spread, it is a mistake.
    RUNWAY = 14
    #: How much of the day's net a single day is allowed to move the figure
    #: the reserve is built on. One bad Tuesday is not a trend, and a policy
    #: that reads yesterday alone flips between building and hoarding every
    #: other morning -- which costs more than either.
    SMOOTH = 0.08

    def burn(self) -> float:
        """What the last few weeks have cost over what they brought in."""
        self._burn += self.SMOOTH * (-self.game.ledger.net - self._burn)
        return max(0.0, self._burn)

    @property
    def reserve(self) -> float:
        floor = self.RESERVE_BASE + self.RESERVE_PER_CART * len(self.game.caravans)
        return max(floor, self.RUNWAY * self.burn())

    def spendable(self) -> float:
        return self.game.treasury - self.reserve

    # ------------------------------------------------------------------ play
    def step(self) -> None:
        # Order matters more than any ladder. Capital first -- a town that arms
        # before it has anything worth defending never grows one -- and the
        # carts last, so they trade with whatever the day left in the chest.
        g = self.game
        # A siege is not a morning for laying out a bakery. Under one, the
        # bot governs, holds and defends and does nothing else -- it used to
        # go on buying carts and buildings with a besieged town's last coin
        # and hand back "Ruined. Your debts outran your carts" from inside
        # its own walls.
        if any(s.besieged for s in g.world.settlements.values()):
            for s in g.world.settlements.values():
                self._govern(s)
            self._hold_out()
            self._defend()
            # A cart that cannot move is still on the books. Skipping the
            # whole of `_carts` under siege skipped the one part of it that
            # matters under siege, which is selling the ones that are never
            # going anywhere again.
            self._prune()
            return
        self._climb()
        self._build()
        self._learn()
        self._settle()
        for s in g.world.settlements.values():
            self._govern(s)
            self._shutter(s)
        self._dig()
        self._hold_out()
        self._shut_out()
        self._defend()
        self._house()
        self._span()
        self._carts()

    # ------------------------------------------------------------- the house
    def _house(self) -> None:
        """Give everyone of age a job, seat first.

        A bot that never posts anybody is a bot playing a different game from
        the one the balance guard is supposed to be measuring -- and it would
        make the house look free, because nothing in the numbers would ever
        show what holding a post is worth.
        """
        g = self.game
        k = g.kin
        seat = g.kin.seat or next(iter(g.world.settlements), "")
        wants = [("steward", seat), ("factor", ""), ("master", seat),
                 ("envoy", "")]
        for post, target in wants:
            if k.holder(post, target):
                continue
            free = [p for p in k.living()
                    if p.uid != k.head and not p.post and not p.inlaw
                    and p.age(g.day) >= 14]
            if not free:
                return
            # The oldest first: they have the most years left in the job and
            # the least time to waste before the seat falls to one of them.
            free.sort(key=lambda p: p.born)
            g.post(free[0].name, post, target)

    # -------------------------------------------------------------- the town
    def _govern(self, s) -> None:
        food = nourishment({k: s.market.stock[k] for k in RATION_GOODS})
        days = food / max(0.2 * s.population, 1e-6)
        s.ration_level = 3 if days > 30 else (2 if days > 10 else 1)
        s.tax_level = 2 if s.popularity > 30 else 1

    def _shutter(self, s) -> None:
        """Close works whose output is piled up and worthless; open them when
        the glut clears. Wages do not stop for an unsold barrel."""
        for b in s.buildings:
            if not b.complete or not b.spec.outputs:
                continue
            rel = [s.market.price(k) / good(k).base_price for k in b.spec.outputs]
            if b.enabled and max(rel) < 0.55:
                b.enabled = False
            elif not b.enabled and max(rel) > 0.95:
                b.enabled = True

    def _build(self) -> None:
        g = self.game
        buffer = self.reserve
        nxt = g.progress.next_age()
        if nxt and not g.progress.advancing:
            buffer = max(buffer, nxt.cost.get("coin", 0.0) * 1.15)
        if g.treasury <= buffer:
            return
        home = g.world.settlements[self.home]
        # A thrown-down keep is not just a ruin: without one there is no way
        # into the later ages at all. Put it back before anything else.
        if not home.count("keep") and "begun" in g.build(self.home, "keep"):
            return
        # One thing raised in each settlement each day: a colony that waits its
        # turn behind the capital never gets off the ground.
        for key in list(g.world.settlements):
            if g.treasury <= buffer:
                return
            plan = self.plan_for(key)
            for i, b in enumerate(plan[:6]):
                if "begun" in g.build(key, b):
                    plan.pop(i)
                    break

    #: What the bot wants in the chest before it lays out for masonry. A
    #: bridge is the longest payback in the game and the one thing that can
    #: never be sold, so it comes out of surplus rather than out of working
    #: capital.
    BRIDGE_FLOAT = 2400.0

    def _span(self) -> None:
        """Bridge the water its own carts keep losing days in.

        The bot needs a bridge policy for the same reason it needs a cart
        policy: a mechanic the autoplayer never touches is a mechanic the
        balance guard never measures, and this one costs 1400c of a purse
        the guard watches.

        It is deliberately narrow. Only the crossing its own running routes
        actually use, only out of surplus, and only one at a time.
        """
        from . import rivers as waters
        g = self.game
        if g.treasury < self.BRIDGE_FLOAT + waters.BRIDGE_COST:
            return
        if any(b.owner == "player" and not b.standing and not b.broken
               for b in g.world.bridges):
            return                      # masons are already out
        found = g.worst_unbridged()
        # A beck is not worth 1400c. Only the water that actually stops carts.
        if found is None or found[2].ford_limit > waters.WORTH_BRIDGING:
            return
        g.build_bridge(found[0], found[1], found[2].key)

    def _settle(self) -> None:
        g = self.game
        if not g.world.sites or g.treasury < 9000:
            return
        g.found(min(g.world.sites, key=lambda k: g.world.sites[k].coin_cost))

    # ------------------------------------------------------------ the ladder
    def _climb(self) -> None:
        g, p = self.game, self.game.progress
        nxt = p.next_age()
        if p.advancing or not nxt:
            return
        if g.treasury < nxt.cost.get("coin", 0.0) + self.reserve:
            return
        msg = g.begin_age()
        if "needs" in msg:
            self._hoard(nxt)
            self._procure(nxt)

    #: What this bot's play is actually improved by.
    #:
    #: It used to research the first thing it could afford, in list order,
    #: which meant a *trading* bot cheerfully bought plate armour, trebuchet
    #: frames and the preaching orders and then never fielded a knight, an
    #: engine or a friar. That was invisible while the tree was small and
    #: every tech was roughly worth having. Adding eight institutions made it
    #: visible: the bot spent its whole surplus on a chancery it would never
    #: write a letter from and a coinage it would never debase, and the
    #: balance guard fell to nothing.
    #:
    #: The fix is not to blocklist the new ones. A measuring instrument that
    #: buys levers it never pulls is not a cautious player, it is a broken
    #: instrument -- and its own docstring says it "plays the trading game
    #: competently and no better". Competently means not buying trebuchet
    #: frames when you have no trebuchets.
    USEFUL = {"yield_field", "yield_mine", "yield_craft", "spoilage",
              "tariff", "housing", "deposit_yield", "productivity", "storage",
              "cart_capacity", "cart_speed", "mood", "interest",
              "caravan_slots", "research_speed"}

    def _worth_learning(self, t) -> bool:
        """A trader buys what makes trading better, and nothing else."""
        if t.key == "drainage":
            return any(s.terrain.get("marsh", 0)
                       for s in self.game.world.settlements.values())
        if set(t.effects) & self.USEFUL:
            return True
        # ...and whatever is on the road to something it does want.
        return any(o.prereq == t.key and set(o.effects) & self.USEFUL
                   for o in TECHS.values())

    def _learn(self) -> None:
        g, p = self.game, self.game.progress
        if p.researching:
            return
        for t in p.available():
            if not self._worth_learning(t):
                continue
            if g.treasury > t.cost.get("coin", 0.0) + self.reserve * 1.5:
                if "takes up" in g.research(t.key):
                    return

    def _hoard(self, age) -> None:
        """Stop spending the very thing the next age is waiting on.

        A blacksmith quietly eating three iron a day will hold a house in the
        same age for years. Shut it while the pile builds, open it after.
        """
        home = self.game.world.settlements[self.home]
        short = {k for k, q in age.cost.items()
                 if k != "coin" and home.market.stock.get(k, 0.0) < q * 1.4}
        for b in home.buildings:
            if not b.complete or not b.spec.inputs:
                continue
            if short & set(b.spec.inputs) and not short & set(b.spec.outputs):
                b.enabled = False
            elif not short and not b.enabled:
                b.enabled = True

    def _procure(self, age) -> None:
        """Buy what the next age wants and your own land will not give you.

        Iron under somebody else's hill is still iron -- this is the trade
        layer doing the thing it exists for.
        """
        g = self.game
        if self.errand is not None:
            return
        home = g.world.settlements[self.home]
        short = [(k, q * 1.4 - home.market.stock.get(k, 0.0))
                 for k, q in age.cost.items()
                 if k != "coin" and home.market.stock.get(k, 0.0) < q * 1.4]
        if not short:
            return
        key, need = max(short, key=lambda kv: kv[1])
        ceiling = good(key).base_price * 2.2      # dear, but not at any price
        need = min(need, max(0.0, g.treasury - 2 * self.reserve) * 0.3 / ceiling)
        if need < 5:
            return
        cart = next((c for c in g.caravans if not c.running and c.load < 5), None)
        if cart is None:
            return
        sellers = [(n, m.ask(key)) for n in g.world.towns
                   for m in [g.world.market_of(n)] if m and m.sells(key)]
        if not sellers:
            return
        where = min(sellers, key=lambda s: s[1])[0]
        cart.set_route([
            Stop(node=where, buy=[Order(key, min(need, cart.capacity), ceiling)]),
            Stop(node=self.home, sell=[Order(key, -1)]),
        ])
        cart.start()
        self.errand = (cart.uid, key, home.market.stock.get(key, 0.0) + need * 0.9)

    # ----------------------------------------------------------------- the wall
    #: Cheap works, in the order a steward would dig them when he sees dust on
    #: the road. Stakes and a fired ditch are days of work, not seasons, which
    #: is the whole reason they are worth digging late.
    DIG = ("pitch_ditch", "kill_pit", "oil_pot", "moat")
    #: Slots kept clear on the wall line for walls and towers.
    WALL_LINE_RESERVE = 4

    def _dig(self) -> None:
        """Works go in when a host is actually coming, not on a rainy Tuesday.

        A ditch costs coin and a length of wall line, so digging one in a quiet
        year is a tower you will wish you had. Digging one with dust on the
        road is the cheapest defence in the game.
        """
        g = self.game
        coming = [a for a in g.armies if a.owner != "player"]
        if not coming:
            return
        if g.treasury < self.reserve + 400:
            return
        home = g.world.settlements[self.home]
        # Leave room on the wall line for the walls themselves: a ditch dug
        # into the last slot is a tower that can never be built after it.
        if home.slots_free("rampart") < self.WALL_LINE_RESERVE:
            return
        for key in self.DIG:
            if home.count(key):
                continue
            if key == "oil_pot" and not home.count("gatehouse"):
                continue
            if "begun" in g.build(self.home, key):
                return

    SORTIE_SHARE = SORTIE_SHARE
    TORCH_UNDER = TORCH_UNDER

    def _hold_out(self) -> None:
        """What to do when somebody is already at the gate.

        Three levers now, used the way the measurements say they work.

        Shore the breach while there is stone for it. Go out at the works
        *early* -- on the first day the engines are there, not when the wall
        is falling -- because by then the men who could have gone are the men
        who have been holding the wall-walk. And send about a quarter of the
        garrison rather than most of it: a sortie is a bet on getting out of
        the gate unseen, and a big party is a thing the camp can watch you
        form up. This policy sent four fifths of the garrison until the
        sortie was reworked under it, and went on sending four fifths after,
        which is how a bot that had been holding the town started starving
        in it.

        Then, if he is close enough to the end of his baggage for it to
        matter, put a torch in it. One raid takes about a third, so against a
        camp carrying a year it is men spent teaching him to watch the gate,
        and against one carrying a fortnight it is the siege.

        The bot knowing all this is also the argument that the scenario is a
        game: a policy this simple should not be able to change the outcome
        of something that is decided in advance.
        """
        g = self.game
        for key, s in g.world.settlements.items():
            if not s.besieged:
                continue
            if s.market.stock.get("stone", 0.0) > 20 and not s.shoring:
                g.shore(key, True)
            works = [a for a in g.armies
                     if a.owner != "player" and a.state == BESIEGING
                     and any(UNITS[u].siege_power > 0 or u == "engineer"
                             for u in a.units)]
            men = sum(s.units.values())
            if works and men >= 30 and not self._sallied.get(key):
                g.sally(key, men=max(8, int(men * self.SORTIE_SHARE)))
                self._sallied[key] = True
                continue
            # And his wagons, once, where burning them would actually bite.
            outside = [a for a in g.armies
                       if a.owner != "player" and a.state == BESIEGING
                       and g.world.node_name(a.at) == s.name]
            camp = max((supply.days_left(a.size, a.stores) for a in outside),
                       default=0.0)
            if (outside and men >= 20 and not self._torched.get(key)
                    and 0 < camp <= self.TORCH_UNDER):
                g.fire_baggage(key, men=max(5, int(men * self.SORTIE_SHARE)))
                self._torched[key] = True

    #: How old a word of sickness may be before it stops closing a gate.
    #: A month-old rumour out of a market your carts left long ago is not a
    #: reason to stop trading; today's is.
    WORD_FRESH = 18
    #: And how near. A sick market you do not trade with can still reach you
    #: on somebody else's drovers, but only in proportion to how near it is
    #: -- so the bot's radius is the world's own falloff (plague.CARRY)
    #: rather than a number of its own. One e-folding: past it, a sick
    #: market is under a third of the risk of one on your doorstep and not
    #: worth closing a market for.

    def _shut_out(self) -> None:
        """The gates, against the sickness.

        Shut on the word your own carts bring back and open again when the
        word goes quiet -- which is all a player can do, because the word is
        fogged and a market nobody of yours has been to lately is a market
        you know nothing about.

        It costs what it is worth: nothing comes in, so nothing is earned on
        the road either. The bot does it anyway for the same reason it
        sallies: a scenario measured with a policy that ignores one of its
        levers is a scenario measured wrong. Without this the sickness took
        a town from two hundred and forty souls to seven, three games in
        eight, and the balance guard was reading that as the game.

        The first cut of it shut every gate on any word from anywhere, which
        is a different way to be wrong. On seed 3 that closed a town for a
        hundred and seventy-three days of nine hundred, caught nothing at
        all -- nobody there was ever ill -- and cost about a quarter of the
        bot's net worth, enough that the peaceable-kingdom feat stopped
        being reachable and the feats test went red. Insurance against a
        risk you are not carrying is not caution, it is a standing charge.
        So: fresh word only, and only about a market this town actually
        trades with or sits near.

        Shutting at all is worth it, which is worth writing down because it
        is not obvious once the recovery cliff is gone. Measured over eight
        seeds and nine hundred days, with this policy against no policy:
        median net worth 57,100 against 48,400, and 206 buried against 788.
        The gate earns its keep four times over in graves and about a fifth
        in coin.
        """
        g = self.game
        word = [r for r in g.word_of_sickness() if r["days"] <= self.WORD_FRESH]
        for key, s in g.world.settlements.items():
            if s.sick.here:
                # Already here. Shutting now saves nobody and costs the
                # trade that pays for the recovery.
                if s.shut:
                    g.shut_gates(key, False)
                continue
            near = self._exposed(key, word)
            if near and not s.shut:
                g.shut_gates(key, True)
            elif not near and s.shut:
                g.shut_gates(key, False)

    def _exposed(self, key: str, word) -> bool:
        """Is this town on the road to anywhere it has heard is ill?"""
        g = self.game
        if not word:
            return False
        sick = {r["key"] for r in word}
        for c in g.caravans:
            if not c.running or c.home != key:
                continue
            if any(stop.node in sick for stop in c.route):
                return True
        # And a market near enough that somebody else's drovers bring it --
        # the `VISITORS` half of plague.py, which no route of yours covers.
        from . import plague as pest
        return any(g.world.distance(key, k) <= pest.CARRY for k in sick
                   if k in g.world.coords)

    def _defend(self) -> None:
        """Enough men on the wall to make a siege not worth a lord's time --
        and not one more, because every soldier is a field nobody is working."""
        g = self.game
        home = g.world.settlements[self.home]
        if not home.effect("muster") or g.treasury < 2 * self.reserve:
            return
        coming = [a for a in g.armies if a.owner != "player"]
        urgent = bool(coming)
        # Never past what the town can actually keep under arms -- see
        # `Settlement.max_garrison`. Its own threat-based cap could sit above
        # that rule, and the two then took turns: recruit to the cap, send
        # the excess back to the fields, recruit again. The bot paid for the
        # same men every morning and never reached a third age or a second
        # town.
        cap = min(int((0.35 if urgent else 0.22) * home.population),
                  home.max_garrison())
        if home.soldiers >= cap:
            return
        # Judge the wall by the biggest host the march could send at it, not by
        # the quiet of this particular morning. Walls and towers are worth
        # roughly double, so parity is not the target -- half of it is.
        # Arm to the temper of the march, not to its worst imaginable day: a
        # garrison raised in a quiet year is a year of fields not worked.
        # The bot judges the march by what it has actually seen, same as a
        # player: it runs carts everywhere, so its intelligence is usually
        # fresh, which is the point of tying the two together.
        worst = max((host_strength(g.believed_host(k))
                     * (0.15 + 0.85 * (t.hostility / C.HOSTILITY_WAR) ** 1.5)
                     for k, t in g.world.towns.items() if not t.mine), default=0.0)
        threat = max(0.55 * worst,
                     0.9 * sum(host_strength(a.units) for a in coming))
        if host_strength(home.units) >= threat:
            return
        # A wall of archers loses the moment the gate goes: fill a mix, and
        # take whichever part of it is furthest behind.
        want = {"spearman": 0.35, "man_at_arms": 0.20, "archer": 0.30,
                "crossbowman": 0.15}
        have = max(1.0, float(home.soldiers))
        order = sorted(want, key=lambda k: home.units.get(k, 0.0) / have - want[k])
        for batch in (8 if urgent else 4, 3, 1):
            for key in order + ["militia"]:
                if "muster at" in g.recruit(self.home, key, batch):
                    return

    # ---------------------------------------------------------------- the road
    def _trim(self, stops):
        """Never carry food out of a town down to its last fortnight."""
        home = self.game.world.settlements[self.home]
        food = nourishment({k: home.market.stock[k] for k in RATION_GOODS})
        if food / max(0.2 * home.population, 1e-6) > 12:
            return stops
        for st in stops:
            if st.node in self.game.world.settlements:
                st.buy = [o for o in st.buy if o.good not in RATION_GOODS]
        return stops

    def _errand_cart(self) -> Optional[int]:
        return self.errand[0] if self.errand else None

    def _port(self) -> Optional[str]:
        """One of yours with a quay, if the coast has been settled."""
        return next((k for k, s in self.game.world.settlements.items()
                     if s.effect("port")), None)

    def _prune(self) -> None:
        """Sell a cart that has not paid for its own wheels.

        A cart costs its ten coin a day whether or not it is carrying
        anything, and a route that has come up dry does not stop the charge:
        the engine stands the cart down with a notice and goes on billing
        for it. A player reads the notice. A bot that never did kept a dead
        cart on the books for the rest of the clock, which is a slow way of
        losing a game nobody was attacking.
        """
        g = self.game
        for c in list(g.caravans):
            born = self._bought.setdefault(c.uid, g.day)
            age = g.day - born
            if age < CART_TRIAL or c.state == MOVING:
                continue
            if c.uid in (self.supply_cart, self._errand_cart()):
                continue
            if c.total_profit >= c.daily_cost * age:
                continue
            g.disband(c.uid)
            self._bought.pop(c.uid, None)

    def _carts(self) -> None:
        g = self.game
        self._prune()
        port = self._port()
        if len(g.caravans) < g.caravan_limit:
            # A hull carries four carts' worth and outruns them; once there is
            # a quay it is the better buy.
            if port and g.treasury > C.SHIP_COST * 2.5 and not any(
                    c.sails for c in g.caravans):
                g.new_caravan(port, kind=SHIP)
            elif g.treasury > C.CARAVAN_COST * 4:
                cart, _why = g.new_caravan(self.home)
                if cart:
                    cart.guards = 3
        colonies = [k for k in g.world.settlements if k != self.home]
        idle: List = []
        for c in g.caravans:
            # One cart runs food out to the newest colony until it feeds itself.
            if colonies and (self.supply_cart in (None, c.uid)):
                col = g.world.settlements[colonies[-1]]
                if col.market.stock["bread"] + col.market.stock["apples"] < 150:
                    self.supply_cart = c.uid
                    if not c.running:
                        c.set_route([
                            Stop(node=self.home,
                                 buy=[Order("bread", 60), Order("apples", 40)]),
                            Stop(node=colonies[-1],
                                 sell=[Order("bread", -1), Order("apples", -1)]),
                        ])
                        c.start()
                    continue
                if self.supply_cart == c.uid:
                    self.supply_cart = None
                    c.halt()
            if c.uid == getattr(self, "arms_cart", None) and c.running:
                continue
            if c.uid == self._errand_cart():
                # An errand is one journey, not a standing route: once the pile
                # is home the cart goes back on the books.
                uid, key, target = self.errand
                home = g.world.settlements[self.home]
                if home.market.stock.get(key, 0.0) >= target or not c.running:
                    self.errand = None
                    c.halt()
                else:
                    continue
            if c.running and c.route:
                continue
            idle.append(c)
        if idle:
            # Shop once for the whole fleet and hand each cart a different
            # trade: three carts on one route is three carts crushing one price.
            # Trading capital is not capital spending: a cart spends and
            # recovers within the trip, so it draws on the whole treasury.
            # The survey keeps for a few days. Prices move, but not that fast,
            # and pricing every trade in the march is the expensive part.
            if g.day - self._scanned_on >= 3 or not self._survey:
                self._survey = scan(g.world, self.home, capacity=idle[0].capacity,
                                    speed=idle[0].speed, steps=FAST_STEPS,
                                    budget=max(0.0, g.treasury * 0.5),
                                    top=3 + len(idle))
                self._scanned_on = g.day
            opts = self._survey
            taken = {tuple(sorted(s.node for s in c.route)) for c in g.caravans
                     if c.running and c.route}
            for c in idle:
                shopping = opts
                if c.sails:
                    shopping = scan(g.world, c.at or c.home, capacity=c.capacity,
                                    speed=c.speed, sails=True, steps=FAST_STEPS,
                                    daily_cost=c.daily_cost,
                                    budget=max(0.0, g.treasury * 0.5), top=4)
                for opp in shopping:
                    sig = tuple(sorted((opp.frm, opp.to)))
                    if sig in taken or opp.per_day <= 0:
                        continue
                    c.set_route(self._trim(route_from(opp, carrying=c.cargo)))
                    c.start()
                    taken.add(sig)
                    break
        # Re-shop every three weeks; an edge does not keep.
        if g.day % 21 == 0:
            for c in g.caravans:
                if c.uid not in (self.supply_cart, self._errand_cart()) \
                        and c.load < 0.15 * c.capacity:
                    c.halt()

    def run(self, days: int) -> List[dict]:
        out = []
        for _ in range(days):
            self.step()
            self.game.tick()
            out.append(self.game.history[-1])
            if self.game.over:
                break
        return out


class Conqueror(Bot):
    """The other way to play: build enough of an economy to arm a host, then
    take the march one town at a time.

    Kept alongside the trading bot because a victory condition nobody can reach
    is decoration. If this one stops taking towns, the conquest path is broken.
    """

    WAR_PLAN: ClassVar[List[str]] = [
        "farm", "mill", "bakery", "quarry", "orchard", "granary", "woodcutter",
        "farm", "mill", "bakery", "poleturner", "sawmill", "trading_post",
        "farm", "mill", "bakery", "cottage", "guildhall", "poleturner",
        "charcoal_burner", "iron_mine", "smelter", "cottage", "market",
        "fletcher", "stone_wall", "armoury", "armourer", "clay_pit", "kiln",
        "townhouse", "siege_yard", "blacksmith", "fletcher", "armourer",
        "townhouse", "wall_tower", "stable", "inn", "townhouse", "armoury",
    ]

    arms_cart: Optional[int] = None

    def plan_for(self, key: str) -> List[str]:
        if key not in self.plans:
            self.plans[key] = list(self.WAR_PLAN if key == self.home else COLONY_PLAN)
        return self.plans[key]

    #: An army is bought with an economy. Campaigning before there is one to
    #: spend is how a war bot ends the game with two towns and no treasury.
    WAR_CHEST = 9000.0
    WAR_SOULS = 240.0

    _at_war = False

    @property
    def warlike(self) -> bool:
        """Once a house turns to war it does not quietly turn back: an army
        half-raised and then abandoned is the worst of both plans."""
        if not self._at_war:
            g = self.game
            self._at_war = (g.population >= self.WAR_SOULS
                            and g.treasury >= self.WAR_CHEST)
        return self._at_war

    def step(self) -> None:
        if not self.warlike:
            super().step()
            return
        # On a war footing the ladder changes: no more ages, no more research,
        # every spare coin into the muster and the arms trade.
        g = self.game
        self._build()
        self._settle()
        for s in g.world.settlements.values():
            self._govern(s)
            self._shutter(s)
        self._dig()
        self._defend()
        self._house()
        self._war_house()
        self._buy_arms()
        self._carts()
        self._campaign()

    def _war_house(self) -> None:
        """At war the eldest spare rides, because a captain is worth more in
        the field than a third steward is at home."""
        g = self.game
        mine = [a for a in g.armies if a.owner == "player"]
        if not mine:
            return
        held = g.kin.holder("captain", str(mine[0].uid))
        if held is not None:
            return
        spare = [p for p in g.kin.living()
                 if p.uid != g.kin.head and not p.inlaw
                 and p.age(g.day) >= 16 and p.post in ("", "envoy")]
        spare.sort(key=lambda p: (p.post == "", p.born))
        if spare:
            g.post(spare[0].name, "captain", str(mine[0].uid))

    def _buy_arms(self) -> None:
        """One cart kept permanently on the arms trade.

        Aldworth has two hills. You cannot mine, smelt, forge and plate an army
        out of that, so a war economy buys half its kit from the towns it means
        to march on -- which is the joke at the centre of this game.
        """
        g = self.game
        if self.arms_cart is not None:
            cart = g.caravan(self.arms_cart)
            if cart is None:
                self.arms_cart = None
            elif cart.running:
                return
        home = g.world.settlements[self.home]
        # Iron first: it is the neck of the whole war economy -- rams, plate
        # and swords all come out of it, and two hills will not supply them.
        wants = [k for k, floor in (("iron", 90), ("armour", 40), ("weapons", 40),
                                    ("bows", 40))
                 if home.market.stock.get(k, 0.0) < floor]
        if not wants:
            return
        key = wants[0]
        sellers = [(n, m.ask(key)) for n in g.world.towns
                   for m in [g.world.market_of(n)] if m and m.sells(key)]
        if not sellers:
            return
        where, price = min(sellers, key=lambda s: s[1])
        cart = (g.caravan(self.arms_cart) if self.arms_cart is not None
                else next((c for c in g.caravans if not c.running), None))
        if cart is None or g.treasury < 2500:
            return
        cart.set_route([
            Stop(node=where, buy=[Order(key, 90 if key == "iron" else 60,
                                        price * 1.6)]),
            Stop(node=self.home, sell=[Order(key, -1)]),
        ])
        cart.start()
        self.arms_cart = cart.uid

    def _campaign(self) -> None:
        g = self.game
        home = g.world.settlements[self.home]
        host = next((a for a in g.armies if a.owner == "player"), None)
        if host is not None:
            if host.state != "garrison":
                return
            # A host that has just taken a town stays put a while: an oath is
            # held by whoever is standing in the square.
            target = self._next_target(host.units, frm=host.at)
            if target:
                g.march(host.uid, target)
            elif host.at in g.world.settlements:
                g.disband_host(host.uid)
            elif g.world.towns.get(host.at) and g.world.towns[host.at].mine:
                if host_strength(host.units) < 200:
                    g.march(host.uid, host.home)   # go home and be made whole
            return
        # Muster at home until the garrison can crack somebody, then set out.
        pooled_all: Dict[str, float] = {}
        for s in g.world.settlements.values():
            for k, n in s.units.items():
                pooled_all[k] = pooled_all.get(k, 0.0) + n
        target = self._next_target(pooled_all)
        if target is None:
            return
        # Bring the colonies' men in to the capital first.
        for key, s in g.world.settlements.items():
            if key == self.home or not s.units:
                continue
            a, _why = g.raise_host(key, {k: int(v) for k, v in s.units.items()
                                         if int(v) > 0})
            if a:
                g.march(a.uid, self.home)
                return
        # Draw the host from every garrison, not just the capital's.
        pooled: Dict[str, float] = {}
        for s in g.world.settlements.values():
            for k, n in s.units.items():
                pooled[k] = pooled.get(k, 0.0) + n
        marching = {k: int(v) for k, v in home.units.items() if int(v) > 0}
        keep_back = {"archer": min(marching.get("archer", 0), 8),
                     "spearman": min(marching.get("spearman", 0), 8)}
        for k, n in keep_back.items():
            marching[k] = marching.get(k, 0) - n
        marching = {k: n for k, n in marching.items() if n > 0}
        if not marching:
            return
        a, _why = g.raise_host(self.home, marching)
        if a:
            g.march(a.uid, target)

    def _next_target(self, units: Dict[str, float],
                     frm: Optional[str] = None) -> Optional[str]:
        """The weakest town this host could actually take, if any."""
        g = self.game
        frm = frm or self.home
        strength = host_strength(units)
        siege = sum(UNITS[k].siege_power * n for k, n in units.items())
        if siege <= 0:
            return None
        best, best_cost = None, 0.0
        for key, t in g.world.towns.items():
            if t.mine or key == frm:
                continue
            defence = host_strength(t.garrison) + t.wall_hp / 14.0
            if strength < defence * 2.0:
                continue
            score = 1.0 / (1.0 + g.world.distance(frm, key) / 60.0)
            if score > best_cost:
                best, best_cost = key, score
        return best

    def _defend(self) -> None:
        """A conqueror musters to a target, not to a threat -- and musters in
        every town that has a barracks, not only the capital."""
        if not self.warlike:
            return super()._defend()
        g = self.game
        if g.treasury < self.reserve:
            return
        # No engines, no conquest: a siege train comes before another spearman,
        # because without one every wall in the march is simply a wall.
        home = g.world.settlements[self.home]
        rams = sum(s.units.get("ram", 0.0) for s in g.world.settlements.values())
        rams += sum(a.units.get("ram", 0.0) for a in g.armies if a.owner == "player")
        if rams < 4 and home.effect("muster"):
            for unit_key in ("ram", "engineer"):
                if "muster at" in g.recruit(self.home, unit_key, 2):
                    return
        want = {"spearman": 0.28, "man_at_arms": 0.22, "archer": 0.20,
                "engineer": 0.12, "ram": 0.10, "crossbowman": 0.08}
        for key, s in g.world.settlements.items():
            if not s.effect("muster") or s.soldiers >= int(0.34 * s.population):
                continue
            have = max(1.0, float(s.soldiers))
            order = sorted(want, key=lambda k: s.units.get(k, 0.0) / have - want[k])
            for batch in (4, 2, 1):
                for unit_key in order + ["militia"]:
                    if "muster at" in g.recruit(key, unit_key, batch):
                        return


def report(game: GameState) -> str:
    p = game.progress
    lines = [f"day {game.day} ({game.date_str()})  --  {p.age_name()}",
             f"  treasury  {game.treasury:>12,.0f}c",
             f"  net worth {game.net_worth():>12,.0f}c",
             f"  souls     {game.population:>12,.0f}   caravans {len(game.caravans)}"
             f"   trade {sum(c.total_profit for c in game.caravans):>10,.0f}c",
             f"  soldiers  {game.soldiers:>12}   sworn towns "
             f"{len(game.world.vassals())}   known {len(p.researched) - 1}"]
    for s in game.world.settlements.values():
        stock = sorted(((v, k) for k, v in s.market.stock.items() if v > 1), reverse=True)
        lines.append(f"  {s.name:<10} pop {s.population:>5,.0f} mood {s.popularity:>3.0f}"
                     f" roofs {s.housing(p):>5,.0f} wall {s.wall_hp:>5,.0f}"
                     f" works {len(s.buildings):>3}"
                     f"  | " + ", ".join(f"{k} {v:.0f}" for v, k in stock[:5]))
    a = game.accounts
    lines.append(f"  prices    {a.cpi:>12,.0f}   inflation {a.inflation:>+6.1f}%"
                 f"   idle {a.unemployment:>4.0f}%"
                 f"   real out {a.real:>8,.0f}")
    lord = game.kin.lord
    if lord is not None:
        best = sorted(SKILLS, key=lambda sk: -lord.xp.get(sk, 0.0))
        kept = ", ".join(f"{sk} {lord.level(sk)}" for sk in best
                         if lord.level(sk) > 0) or "untried"
        lines.append(f"  {lord.name}, {lord.age(game.day)} -- {kept}"
                     + (f" ({', '.join(lord.reputation())})"
                        if lord.reputation() else ""))
        posted = [f"{q.name} {q.doing(game.world.node_name)}"
                  for q in game.kin.living() if q.post and q.post != "head"]
        lines.append(f"  the house {len(game.kin.living()):>12}"
                     + ("   " + "; ".join(posted) if posted else
                        "   nobody is posted to anything"))
    if game.over:
        lines.append(f"  ENDING    {game.over}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="run Marchlands headless")
    ap.add_argument("--days", type=int, default=C.GOAL_DAYS)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--every", type=int, default=180, help="report interval")
    ap.add_argument("--scenario", default="marchlands")
    ap.add_argument("--war", action="store_true", help="run the conqueror instead")
    args = ap.parse_args(argv)
    from .scenarios import start
    game = start(args.scenario, seed=args.seed)
    bot = (Conqueror if args.war else Bot)(game)
    for _ in range(args.days):
        bot.step()
        game.tick()
        if game.day % args.every == 0:
            print(report(game), flush=True)
        if game.over:
            break
    print("-" * 60)
    print(report(game))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
