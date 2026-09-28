"""The accounts: what the march is worth, what came in, what went out, and the levers
on the coin -- the mint and the assize.

One slice of GameState, split out of engine.py by noun. The methods run on
the game state itself -- `self` is the GameState -- so nothing here holds
state of its own.
"""

from __future__ import annotations

from typing import List

from . import config as C
from .chronicle import MOMENTOUS
from .economics import MONEY_BASE
from .goods import good
from . import lords as lordly
from .military import UNITS, host_upkeep


class AccountsMixin:
    """GameState's accounts. Mixed into GameState; see engine.py."""

    # ------------------------------------------------------------- economics
    def net_worth(self) -> float:
        worth = self.treasury
        for s in self.world.settlements.values():
            worth += s.net_worth()
        fallback = next(iter(self.world.settlements.values())).market
        for c in self.caravans:
            m = self.world.market_of(c.at) or fallback
            worth += sum(q * m.bid(k) for k, q in c.cargo.items())
            worth += C.CARAVAN_COST * 0.5
        for a in self.armies:
            if a.owner == "player":
                worth += sum(UNITS[k].coin * n * 0.5 for k, n in a.units.items())
        return worth

    def real_worth(self) -> float:
        """Net worth in the coin of the first year, which is the only kind
        that can be a goal.

        The chest and the granary are both counted at today's prices, so a
        debasement raises net worth the instant it is struck -- twenty
        thousand coins of it, on a goal of a hundred and twenty. The target
        was therefore reachable by printing, which is not a strategy, it is a
        hole. Dividing the mint back out closes it: you cannot mint your way
        to a fortune, only to a larger number of smaller coins.

        Deliberately the price *level* and not the index. The index also
        carries how dear this particular town's basket is, which is a real
        fact about a place that grows wheat and buys everything else -- and
        deflating by it would have made every wealth goal in the game
        unreachable by a factor of four. The mint is the only thing that ought
        to be divided out, so the mint is the only thing that is.

        The divisor is the money you have *struck*, not the price level that
        has so far caught up with it. Prices lag by a year or two and that lag
        is the whole reason anybody debases -- but a goal measured against the
        lagging number could be crossed by minting on the last afternoon,
        before a single price had noticed. Measured against the money supply
        the debasement counts the moment the dies come down, which is when the
        decision was actually made.

        This does not make a debasement worthless, and it should not:
        seigniorage is a real tax really collected, and a lord who strikes
        light coin really is better off at the expense of everyone holding the
        old. It makes it *honest*, and gives it the shape it has in life --
        worth most to a poor house with nothing to lose, and a straight loss
        to a rich one, because a third more coin against a hundred thousand of
        holdings takes more than the twenty thousand it hands you.
        """
        return self.net_worth() / max(1.0, self.economy.money / MONEY_BASE)

    def restock(self, settlement_key: str = "", uid: int = -1) -> str:
        """Buy beasts in for a yard that has lost its flock.

        The other half of a raid driving them off. A flock below its seed
        share cannot breed back -- there is nothing left to breed from --
        and a rule like that is only fair if there is a way to pay your way
        out of it. This is the bill: so much a head, to fill the yard.
        """
        s = self.world.settlements.get(settlement_key or "") or self.home()
        yards = [b for b in s.buildings
                 if b.key in C.HERD_FULL and b.complete]
        if uid >= 0:
            yards = [b for b in yards if b.uid == uid]
        elif yards:
            # The emptiest one, because that is the one you meant.
            yards = [min(yards, key=lambda b: b.head / C.HERD_FULL[b.key])]
        if not yards:
            return f"{s.name} has no pasture, dairy or stable to stock"
        yard = yards[0]
        full = C.HERD_FULL[yard.key]
        want = full - max(0.0, yard.head)
        if want < 0.5:
            return f"the {yard.spec.name.lower()} at {s.name} is fully stocked"
        price = C.HERD_PRICE.get(yard.key, 50.0)
        bill = want * price
        if self.treasury < bill:
            return (f"{want:.0f} head for the {yard.spec.name.lower()} is "
                    f"{bill:,.0f}c and you have {self.treasury:,.0f}c")
        self.treasury -= bill
        yard.head = float(full)
        return (f"{want:.0f} head driven in to the "
                f"{yard.spec.name.lower()} at {s.name} for {bill:,.0f}c")

    def herds(self, settlement_key: str = "") -> List[dict]:
        """Every yard that keeps beasts, and how it stands."""
        s = self.world.settlements.get(settlement_key or "") or self.home()
        out = []
        for b in s.buildings:
            full = C.HERD_FULL.get(b.key, 0)
            if not full or not b.complete:
                continue
            head = max(0.0, b.head)
            out.append({"uid": b.uid, "name": b.spec.name, "key": b.key,
                        "head": round(head, 1), "full": full,
                        "share": round(head / full, 3),
                        "seed": head >= full * C.HERD_SEED,
                        "cost": round((full - head)
                                      * C.HERD_PRICE.get(b.key, 50.0))})
        return out

    # ------------------------------------------------------------ the money
    ASSIZE_DRAIN = 0.85          # extra demand, as a share of a day's use
    ASSIZE_LEAK = 0.004          # of stock a day out of the back door besides
    ASSIZE_RELIEF = 13.0         # what cheap bread is worth while there is any
    ASSIZE_MOOD = 16.0           # ...and what queuing for it costs when there is not
    SMUGGLE_SHARE = 0.55         # of the drained goods that leave for a profit
    MINT_MOOD = 9.0              # what a debased penny costs you in goodwill

    def _economy_day(self) -> List[str]:
        """What the mint and the assize did today.

        Both of these are the textbook's two most famous results and neither
        is a special case bolted on: minting moves the price *level*, which
        every price in the game is already multiplied by, and a cap is a
        number the market may not post above, which the sheds that sell into
        it can feel in what they are paid.
        """
        msgs: List[str] = []
        econ = self.economy
        econ.settle()
        econ.smuggled = 0.0
        for s in self.world.settlements.values():
            s.market.level = econ.price_level
            s.market.caps = dict(econ.assize)
            s.assize_mood = 0.0
        # And every market your carts deal with, because there is one coin on
        # this march and it is yours. A debased penny buys less in Ostmark
        # too; leaving foreign prices alone would have made minting a standing
        # subsidy on imports, which is an arbitrage the mint itself printed.
        for t in self.world.towns.values():
            t.market.level = econ.price_level
        for key, cap in list(econ.assize.items()):
            bite = max(s.market.binding(key)
                       for s in self.world.settlements.values())
            econ.shortage[key] = bite
            if bite <= 0.01:
                continue
            # Both halves of it, which is the whole point of the lever. Cheap
            # bread is a real transfer to real people and they are grateful
            # for it -- right up until there is none, and then they are
            # standing in a queue that your proclamation put them in. A price
            # control that only ever hurt was not a decision, it was a trap;
            # this one is a month of goodwill bought against the granary.
            for s in self.world.settlements.values():
                want = max(1.0, s.market.target.get(key, 0.0) * 0.6)
                plenty = min(1.0, s.market.stock.get(key, 0.0) / want)
                relief = self.ASSIZE_RELIEF * bite * plenty
                queue = self.ASSIZE_MOOD * bite * (1.0 - plenty)
                s.assize_mood = min(s.assize_mood, relief - queue) \
                    if s.assize_mood else relief - queue
            for s in self.world.settlements.values():
                # A shelf empties from both ends: everyone wants more of it at
                # that price, and the back door is open to anyone who will pay
                # what it is really worth.
                taken = s.market.take(key, self._assize_drain(s, key, bite))
                econ.smuggled += (taken * self.SMUGGLE_SHARE
                                  * (s.market.fundamental(key) - cap))
            if self.day % 30 == 0:
                msgs.append(self.note(
                    f"The assize holds {good(key).name} at {cap:,.1f}c, which is "
                    f"{bite * 100:.0f}% under what it is worth. The shelves are "
                    f"emptying and some of it is going out the back door."))
        return msgs

    #: Which institution opens which lever. A tech tree that only multiplies
    #: what you were already doing describes your town; one that decides what
    #: you may do in it is a tree.
    OPENS = {
        "mint": ("coinage", "You have no coinage of your own -- you are using "
                            "somebody else's pennies, and a man cannot debase "
                            "another man's coin. `research coinage`."),
        "decree": ("assize_of_bread", "There is no assize here: no standard "
                                      "loaf, no legal maximum and no court to "
                                      "hear a complaint about either. "
                                      "`research assize_of_bread`."),
        "ally": ("chancery", "You have no chancery -- no clerks, no seal and "
                             "no copy of anything you have ever sent. Nobody "
                             "swears to a house that cannot write. "
                             "`research chancery`."),
    }

    def opened(self, lever: str) -> str:
        """'' if the institution stands, else why it does not."""
        want, why = self.OPENS.get(lever, ("", ""))
        if not want or self.progress.knows(want):
            return ""
        return why

    def mint(self, coin: float) -> str:
        """Strike more pennies out of the same silver.

        MV = PY. More pennies is not more bread, and everybody finds that out
        -- but not today, and the gap between today and finding out is the
        entire reason anybody has ever done this.
        """
        shut = self.opened("mint")
        if shut:
            return shut
        coin = max(0.0, float(coin))
        if coin <= 0:
            econ = self.economy
            return (f"the mint has struck {econ.minted:,.0f}c so far; prices "
                    f"stand at {econ.price_level * 100:.0f} of what they were")
        if coin > C.MINT_LIMIT:
            return f"the mint cannot strike more than {C.MINT_LIMIT:,.0f}c at once"
        self.treasury += coin
        self.economy.strike(coin, self.net_worth())
        self.kin.did("just", -0.25)
        for s in self.world.settlements.values():
            s.popularity = max(0.0, s.popularity
                               - self.MINT_MOOD * coin / C.MINT_LIMIT)
        want = self.economy.money / MONEY_BASE
        return self.note(
            f"{coin:,.0f}c struck. The coin in the march stands at "
            f"{self.economy.money:,.0f}c, so prices are bound for "
            f"{want * 100:.0f} of what they were, and the town can already "
            f"feel it.", MOMENTOUS)

    def decree(self, key: str, price: float) -> str:
        """The assize: a legal maximum on what a good may be sold for.

        The first thing a ceiling teaches is that one above the market price
        does nothing whatever, and the second is what one below it does.
        """
        shut = self.opened("decree")
        if shut:
            return shut
        # A chartered market is theirs to price. This is the privilege
        # actually holding rather than being described as holding: you gave
        # away the right, and here is where you find you no longer have it.
        if self.estates.granted("charter") and price > 0:
            return ("you chartered the market: prices are the guilds' to set "
                    "while it stands. `estates revoke charter` first, and they "
                    "will remember that you did")
        spec = good(key)
        home = self.home()
        worth = home.market.fundamental(key)
        if price <= 0:
            self.economy.set_cap(key, 0.0)
            for s in self.world.settlements.values():
                s.market.caps.pop(key, None)
            return f"the assize on {spec.name} is lifted; it finds its own price"
        self.economy.set_cap(key, float(price))
        for s in self.world.settlements.values():
            s.market.caps[key] = float(price)
        if price >= worth:
            return (f"{spec.name} is held at {price:,.1f}c, which is above the "
                    f"{worth:,.1f}c it fetches. A ceiling over the market is a "
                    f"proclamation and nothing else.")
        self.kin.did("just", 0.10)
        short = 100.0 * (1.0 - price / worth)
        return self.note(
            f"{spec.name} is held at {price:,.1f}c against the {worth:,.1f}c it "
            f"is worth -- {short:.0f}% under. Cheap for whoever gets to the "
            f"front, and {self._assize_days(key, price)} before the shelves "
            f"are bare.", MOMENTOUS)

    def _assize_drain(self, s, key: str, bite: float) -> float:
        """How much of it goes today that would not have gone at its own price.

        Excess demand is a *quantity*, not a fraction of the shelf. This used
        to take 3.5% of stock a day, which is not a shortage, it is a decay:
        a proportional drain simply settles the shelf at forty days' output
        and any town that bakes its own bread never queues at all. Measured on
        a grown save, a fully biting cap cost 2% of the granary over sixty
        days and the queue the lever exists to create never once formed --
        which made the assize a standing +12 to the mood for nothing, the same
        free lunch the mint was.

        What a ceiling actually does is make more people want the good than
        there is of it at that price, and "more people" is measured against
        how much the town gets through in a day. Plus the back door, which is
        a small share of the shelf and the reason smugglers exist.
        """
        use = (max(0.0, s.report.eaten.get(key, 0.0))
               + max(0.0, s.report.consumed.get(key, 0.0)))
        return bite * (use * self.ASSIZE_DRAIN
                       + s.market.stock.get(key, 0.0) * self.ASSIZE_LEAK)

    def _assize_days(self, key: str, price: float) -> str:
        """How long the goodwill lasts, which is the only thing worth knowing.

        A price control is a transfer out of a granary, so its whole life is
        however much is in the granary. Saying so at the moment of the decree
        is the difference between a decision and an ambush -- and for a good
        that is eaten every day, the honest answer is usually "a fortnight".
        """
        home = self.home()
        stock = home.market.stock.get(key, 0.0)
        # Both ways it leaves: eaten off the ration, and used up by the sheds.
        # Missing the first of those made a forecast for bread that ignored
        # the town eating the bread.
        gone = (max(0.0, home.report.eaten.get(key, 0.0))
                + max(0.0, home.report.consumed.get(key, 0.0)))
        worth = home.market.fundamental(key)
        bite = max(0.0, 1.0 - price / worth) if worth > 0 else 0.0
        made = max(0.0, home.report.produced.get(key, 0.0))
        net = gone - made + self._assize_drain(home, key, bite)
        if net <= 0.01:
            return "no sign of running out on today's trade"
        days = stock / net
        if days >= 90:
            return "a season or more"
        return f"about {days:.0f} days"

    def relics_held(self, owner: str = "player") -> int:
        return sum(1 for sh in self.world.shrines.values() if sh.holder == owner)

    def relic_income(self) -> float:
        """Pilgrims' offerings. A cathedral is where they are meant to rest."""
        held = self.relics_held()
        if not held:
            return 0.0
        housed = any(s.count("cathedral") for s in self.world.settlements.values())
        return C.RELIC_COIN * held * (1.6 if housed else 1.0)

    # --------------------------------------------------------- the lords' coin
    def _income_of(self, t) -> float:
        """What a lord's country pays him a day: a little over what his
        standing garrison costs, and a share of his town's trade."""
        return (1.3 * host_upkeep(t.target_garrison())
                + 0.5 * t.tribute() * lordly.sort_of(t.key).thrift)

    def _pay(self, mission, led=None) -> str:
        """Hand over what a mission promised.

        Coin goes through the day's ledger, not around it. A reward added
        straight to the treasury is a coin the accounts cannot explain, and
        the first thing it broke was the test that says they always can.
        """
        kind, value = mission.gives
        if kind == "coin":
            self.treasury += float(value)
            if led is not None:
                led.reward += float(value)
            return f"{float(value):,.0f}c into the chest"
        if kind == "tech":
            self.progress.researched.add(str(value))
            return f"{value} learned outright, without the scholars"
        if kind == "claim":
            # "nearest" rather than a named town, because which town is
            # nearest depends on the map the scenario drew.
            key = self._nearest_foreign() if value == "nearest" else str(value)
            if key:
                # A claim is a town key and the day it was made -- claims
                # outlive the person the marriage was to, which is the whole
                # point of them.
                self.court.claims.setdefault(key, self.day)
                return f"a claim on {self.world.node_name(key)}"
            return "no claim to be had"
        if kind == "privilege":
            return self.estates.grant(str(value), self.day)
        if kind == "prosperity":
            for s in self.world.settlements.values():
                s.popularity = min(100.0, s.popularity + float(value) * 20.0)
            for t in self.world.towns.values():
                if t.mine:
                    t.prosperity += float(value)
            return f"your holdings prosper"
        if kind == "opinion":
            # Through the book, not onto `favour`: favour is re-read off the
            # book every morning, so writing to it directly was a reward that
            # lasted until breakfast.
            for key, t in self.world.towns.items():
                if not t.mine:
                    self.court.write(key, "gift", float(value), self.day)
            return f"every lord thinks better of you"
        if kind == "units":
            seat = self.home()
            for k, n in dict(value).items():
                seat.units[k] = seat.units.get(k, 0.0) + float(n)
            return "they muster at " + seat.name
        return mission.reward_words()
