"""The economy, in the terms an economist would use for it.

Nothing in this file changes how the game works. It *measures* what the game
already does, in the vocabulary of a first-year course, and hands the player
the same instruments a real steward would want: what a thing is worth at the
margin, who should be making what, what a tax actually costs, and what a
purse of coin is worth this year against last.

Why bother. The simulation underneath was already a supply-and-demand model --
price is a function of stock, every trade moves stock, so every trade moves
the price against the trader. What it was missing was the *reading* of that:
a merchant playing it could feel that tolls hurt without ever being shown the
triangle, and could feel that prices crept up after a debasement without ever
seeing an index. Making the measurement explicit turns a good intuition pump
into a thing you can be right or wrong about on purpose.

The five ideas that do the work, in the order they show up in Mankiw:

* **Opportunity cost and comparative advantage** (ch. 3). Two towns can both
  gain from trade even when one is better at everything, and the test is not
  who is better -- it is who gives up less. `advantage` computes both sides'
  opportunity costs out of the production the game is actually running.
* **Elasticity** (ch. 5). Every good already carries one. It decides whether a
  shortage is an inconvenience or a catastrophe, and whether a seller's
  revenue rises or falls when the price does.
* **Surplus, and the deadweight loss of a tax** (ch. 7-8). The price curve is
  an inverse demand curve, so consumer surplus is a definite integral under
  it. A toll is a wedge; the triangle it cuts out goes to nobody, and this is
  the only way to see that the revenue is not the cost.
* **The value of the marginal product** (ch. 18). A hand is worth hiring while
  the output of the next one is worth more than the wage. That rule is exactly
  the decision `work <building> first` already makes you take, blind.
* **The quantity theory of money** (ch. 17). MV = PY. Strike more pennies from
  the same silver and you have more pennies, not more bread -- but not today,
  which is the whole reason anybody ever does it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config as C
from .buildings import BUILDINGS
from .goods import ALL_KEYS, good
from .market import MIN_STOCK, Market

#: The basket the index is built on. A price index is only as honest as its
#: basket, so this one is what a household in this game actually buys: bread
#: and ale first, a little cloth and pottery, and the fuel to get through a
#: winter. Fixed weights, fixed for the whole game -- a basket that drifts
#: with consumption measures something, but it does not measure inflation.
BASKET: Tuple[Tuple[str, float], ...] = (
    ("bread", 0.34),
    ("ale", 0.14),
    ("cheese", 0.10),
    ("apples", 0.07),
    ("cloth", 0.11),
    ("pottery", 0.06),
    ("wood", 0.10),
    ("salt", 0.05),
    ("tools", 0.03),
)

#: How fast the price level chases the money supply. Nothing in economics says
#: prices move the day the mint does; everything in economics says they move.
#: The lag is the whole short-run tradeoff, so it is a tunable and not a 1.
PRICE_LEVEL_ADJUST = 0.004
#: Money in circulation at the start, against which a debasement is measured.
#: Not the treasury: the coin in the hands of everyone your town trades with.
MONEY_BASE = 60_000.0


def basket_cost(m: Market) -> float:
    """What the basket costs, at the prices a shopper is actually charged.

    Deliberately the posted price and not the curve. Under a binding assize
    the two come apart -- the loaf may not be sold above the cap, and there is
    no loaf -- and an index built on what a thing is *worth* would read the
    shortage as inflation. Built on what is charged, it reads the way a real
    one does under a price control: prices look fine, and the shelves are
    empty. The second half is in the assize line underneath it.
    """
    return sum(share * m.price(k) for k, share in BASKET)


@dataclass
class Accounts:
    """One day of national accounts, kept so they can be read as a series."""
    day: int = 0
    cpi: float = 100.0            # index, base = the first day of the game
    inflation: float = 0.0        # per cent a year, from the last 360 days
    nominal: float = 0.0          # value of what was produced today
    real: float = 0.0             # ...the same, in first-day prices
    money: float = MONEY_BASE     # coin in circulation
    velocity: float = 0.0         # PY / M
    employed: float = 0.0
    workforce: float = 0.0

    @property
    def unemployment(self) -> float:
        if self.workforce <= 0:
            return 0.0
        return 100.0 * max(0.0, self.workforce - self.employed) / self.workforce

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Accounts":
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


def base_basket() -> float:
    """The basket at every good's long-run value.

    The index base is deliberately *not* day one. On day one a new holding is
    sitting on its founding stores, so its prices are at the floor, and an
    index based there reads the town eating through its granary as four
    hundred per cent inflation. Basing it on equilibrium prices means 100 is
    "everything is worth what it is worth", which is a number that means the
    same thing in every scenario and every chapter.
    """
    return sum(share * good(k).base_price for k, share in BASKET)


@dataclass
class Economy:
    """The measuring apparatus, and the one lever that moves prices directly.

    The price level is the only thing here that writes back into the
    simulation, and it is deliberately the only one: an index that changed the
    world it was measuring would be a thermometer that heats the room.
    """
    base_cpi: float = 0.0         # the basket's cost on day one, in home prices
    money: float = MONEY_BASE
    minted: float = 0.0           # what you have struck, cumulative
    price_level: float = 1.0      # what the mint has done to prices so far
    series: List[dict] = field(default_factory=list)
    #: Legal maximum prices, by good. The assize of bread, and what it does.
    assize: Dict[str, float] = field(default_factory=dict)
    shortage: Dict[str, float] = field(default_factory=dict)
    smuggled: float = 0.0         # coin that left through the back door today

    # ------------------------------------------------------------- measuring
    def observe(self, game) -> Accounts:
        """Take the day's readings. Called once per tick, after everything."""
        home = next(iter(game.world.settlements.values()), None)
        if home is None:
            return Accounts(day=game.day)
        cost = basket_cost(home.market)
        if self.base_cpi <= 0:
            self.base_cpi = base_basket()
        cpi = 100.0 * cost / max(self.base_cpi, 1e-9)

        nominal = real = 0.0
        for s in game.world.settlements.values():
            for k, qty in s.report.produced.items():
                nominal += qty * s.market.curve(k, s.market.stock.get(k, 0.0))
                real += qty * good(k).base_price
        employed = sum(s.employed for s in game.world.settlements.values())
        workforce = sum(s.workforce for s in game.world.settlements.values())

        acc = Accounts(day=game.day, cpi=cpi, nominal=nominal, real=real,
                       money=self.money, employed=employed, workforce=workforce)
        # Annualised, because a velocity per day is a number nobody holds.
        acc.velocity = nominal * C.DAYS_PER_YEAR / max(self.money, 1.0)
        acc.inflation = self.inflation_rate(cpi)
        self.series.append(acc.to_dict())
        if len(self.series) > 2000:
            del self.series[:-2000]
        return acc

    def inflation_rate(self, cpi: float) -> float:
        """Year on year, per cent. Falls back to the longest run there is."""
        if not self.series:
            return 0.0
        want = C.DAYS_PER_YEAR
        then = self.series[-want] if len(self.series) > want else self.series[0]
        span = max(1, self.series[-1]["day"] - then["day"] + 1)
        old = max(then["cpi"], 1e-9)
        return 100.0 * ((cpi / old) ** (C.DAYS_PER_YEAR / span) - 1.0)

    def last(self) -> Accounts:
        return Accounts.from_dict(self.series[-1]) if self.series else Accounts()

    def at(self, days_ago: int) -> Optional[Accounts]:
        if len(self.series) <= days_ago:
            return None
        return Accounts.from_dict(self.series[-1 - days_ago])

    # ------------------------------------------------------------ the mint
    def strike(self, coin: float, output: float) -> None:
        """More pennies out of the same silver. MV = PY, eventually.

        The target price level is the one the quantity theory names: if M goes
        up by a fifth and nothing real has changed, prices end up a fifth
        higher. `PRICE_LEVEL_ADJUST` is how slowly they get there, and every
        coin of benefit a debasement ever bought somebody lives in that gap.
        """
        self.money += coin
        self.minted += coin

    def settle(self) -> None:
        """Prices walk toward what the money supply says they must be."""
        want = self.money / max(MONEY_BASE, 1.0)
        self.price_level += PRICE_LEVEL_ADJUST * (want - self.price_level)

    # --------------------------------------------------------- the assize
    def cap(self, key: str) -> float:
        return self.assize.get(key, 0.0)

    def set_cap(self, key: str, price: float) -> None:
        if price <= 0:
            self.assize.pop(key, None)
            self.shortage.pop(key, None)
        else:
            self.assize[key] = price

    def to_dict(self) -> dict:
        return {"base_cpi": self.base_cpi, "money": self.money,
                "minted": self.minted, "price_level": self.price_level,
                "series": self.series[-1200:], "assize": dict(self.assize),
                "shortage": dict(self.shortage)}

    @classmethod
    def from_dict(cls, d: dict) -> "Economy":
        return cls(base_cpi=d.get("base_cpi", 0.0),
                   money=d.get("money", MONEY_BASE),
                   minted=d.get("minted", 0.0),
                   price_level=d.get("price_level", 1.0),
                   series=list(d.get("series", [])),
                   assize=dict(d.get("assize", {})),
                   shortage=dict(d.get("shortage", {})))


# ------------------------------------------------------------------ surplus
@dataclass
class Surplus:
    """What a market is worth to the people on either side of it."""
    good: str
    price: float = 0.0
    quantity: float = 0.0
    consumer: float = 0.0
    producer: float = 0.0
    revenue: float = 0.0        # what the toll collects
    deadweight: float = 0.0     # what it destroys on the way

    @property
    def total(self) -> float:
        return self.consumer + self.producer + self.revenue


def surplus(m: Market, key: str, steps: int = 64) -> Surplus:
    """Consumer and producer surplus at the posted price, and the toll's cost.

    The curve `base * (target/stock)^elasticity` is willingness to pay read
    off the stock axis, so the area under it above the price is exactly
    consumer surplus. The integral is done in strips because a closed form
    that stops being right the moment somebody changes the curve is worse than
    a loop that cannot.
    """
    out = Surplus(good=key)
    stock = m.stock.get(key, 0.0)
    if stock <= MIN_STOCK:
        return out
    out.price = m.price(key)
    out.quantity = stock
    # Consumers: everyone who would have paid more than the going price.
    # Walk from the last unit sold back toward the first, which is where the
    # thirsty are.
    lo, hi = MIN_STOCK, stock
    step = (hi - lo) / steps
    for i in range(steps):
        q = lo + step * (i + 0.5)
        willing = m.curve(key, q)
        if willing > out.price:
            out.consumer += (willing - out.price) * step
    # Producers: the wage is the cost of the marginal unit, so anything the
    # market pays above what it cost to make is theirs.
    cost = _unit_cost(key)
    if out.price > cost:
        out.producer = (out.price - cost) * stock
    # The toll is a wedge. It raises what a buyer pays and lowers what a seller
    # keeps, and the trades that were worth doing in between simply stop.
    rate = m.tariff_rate
    if rate > 0:
        wedge = out.price * rate
        out.revenue = wedge * stock
        # The lost trades, from the elasticity of the curve at this point.
        el = max(0.05, good(key).elasticity)
        lost = stock * min(0.9, rate / el)
        out.deadweight = 0.5 * wedge * lost
    return out


def _unit_cost(key: str) -> float:
    """What a unit costs to make here, in wages and inputs, per Mankiw's firm.

    Not the price -- the cost. A building's recipe says how many hands it ties
    up for how much output, and the wage says what a hand costs, so the two of
    them say what the last loaf cost to bake.
    """
    best = None
    for spec in BUILDINGS.values():
        out = spec.outputs.get(key, 0.0)
        if out <= 0:
            continue
        wages = C.WAGE * spec.jobs / out
        inputs = sum(qty * good(k).base_price for k, qty in spec.inputs.items())
        unit = wages + inputs / out
        best = unit if best is None else min(best, unit)
    return best if best is not None else good(key).base_price * 0.6


# --------------------------------------------------- comparative advantage
@dataclass
class Advantage:
    good: str
    other: str                  # the good it is weighed against, "" for coin
    here: float = 0.0           # units of `other` given up per unit of `good`
    there: float = 0.0
    their_name: str = ""
    mine_alt: str = ""          # what you would be making instead
    their_alt: str = ""

    @property
    def in_coin(self) -> bool:
        return not self.other

    def unit(self) -> str:
        return "c" if self.in_coin else f" {good(self.other).name}"

    @property
    def theirs(self) -> bool:
        """Should they be making it? True when they give up less than you."""
        return self.there < self.here

    def reads(self) -> str:
        cheap, dear = ((self.their_name, "you") if self.theirs
                       else ("you", self.their_name))
        return (f"{cheap} gives up less to make it than {dear} does -- "
                f"{min(self.here, self.there):.2f} against "
                f"{max(self.here, self.there):.2f}")


def opportunity_cost(hourly: Dict[str, float], key: str, other: str) -> float:
    """How much `other` a place forgoes for one more unit of `key`.

    The whole of comparative advantage is this ratio and nothing else. It is
    not about who is better; a place that is worse at everything still gives
    up less of something.
    """
    a, b = hourly.get(key, 0.0), hourly.get(other, 0.0)
    if a <= 0:
        return float("inf")
    return b / a


def daily_output(settlement) -> Dict[str, float]:
    """What a place could make per day of each good if it ran flat out.

    Capacity, not production: comparative advantage is about what a place
    *can* do with the hands and the land it has, which is why a town with a
    seam it is not working still has the advantage in iron.
    """
    out: Dict[str, float] = {}
    for b in settlement.buildings:
        if not b.complete:
            continue
        for k, qty in b.spec.outputs.items():
            out[k] = out.get(k, 0.0) + qty
    return out


def town_output(town) -> Dict[str, float]:
    """The same reading for a foreign town, out of what its market makes.

    A foreign town is a flow, not a list of sheds: `flow` is units a day,
    signed, so the positive half of it is its production possibilities.
    """
    return {k: v for k, v in town.flow.items() if v > 0}


def _best_alternative(out: Dict[str, float], key: str) -> Tuple[str, float]:
    """The most valuable thing a place could be making instead of `key`."""
    best, worth = "", 0.0
    for k, qty in out.items():
        if k == key or qty <= 0:
            continue
        value = qty * good(k).base_price
        if value > worth:
            best, worth = k, value
    return best, worth


def compare(mine: Dict[str, float], theirs: Dict[str, float],
            key: str, their_name: str,
            against: str = "") -> List[Advantage]:
    """What each of you gives up to make one more unit of `key`.

    The textbook case is two places that both make two goods, and then the
    answer is a ratio of physical quantities. Two towns on a march usually do
    not overlap that neatly, so there are two readings here and the first one
    that applies wins:

    * a good you both make -- the ratio, exactly as it is taught;
    * otherwise the best *other* thing each of you could be doing with the
      same hands, in coin. Coin as the numeraire is not a dodge: opportunity
      cost is whatever you gave up, and the reason we can add up unlike things
      at all is that there are prices.
    """
    if mine.get(key, 0.0) <= 0 and theirs.get(key, 0.0) <= 0:
        return []
    rows: List[Advantage] = []
    shared = ([against] if against
              else [k for k in ALL_KEYS
                    if k != key and mine.get(k, 0.0) > 0 and theirs.get(k, 0.0) > 0])
    for other in shared:
        here = opportunity_cost(mine, key, other)
        there = opportunity_cost(theirs, key, other)
        if here == float("inf") and there == float("inf"):
            continue
        rows.append(Advantage(good=key, other=other, here=here, there=there,
                              their_name=their_name))
    if rows:
        rows.sort(key=lambda r: -abs(r.here - r.there))
        return rows
    # Nothing in common. Weigh each against the best thing it could be doing
    # instead, in coin, which always exists and always means something.
    my_alt, my_worth = _best_alternative(mine, key)
    their_alt, their_worth = _best_alternative(theirs, key)
    here = (my_worth / mine[key]) if mine.get(key, 0.0) > 0 else float("inf")
    there = (their_worth / theirs[key]) if theirs.get(key, 0.0) > 0 else float("inf")
    if here == float("inf") and there == float("inf"):
        return []
    row = Advantage(good=key, other="", here=here, there=there,
                    their_name=their_name)
    row.mine_alt, row.their_alt = my_alt, their_alt
    return [row]


# ---------------------------------------------------- the labour market
@dataclass
class MarginalHand:
    """One building, read as a firm deciding whether to hire."""
    key: str
    name: str
    uid: int = 0
    staffed: int = 0
    jobs: int = 0
    product: float = 0.0        # share of the recipe one more hand drives
    units: float = 0.0          # ...which is this many units of output
    value: float = 0.0          # ...what that output fetches here
    input_cost: float = 0.0     # ...less what it eats to make it
    wage: float = C.WAGE

    @property
    def net(self) -> float:
        """The value of the marginal product, net of what it consumes."""
        return self.value - self.input_cost

    @property
    def hire(self) -> bool:
        return self.net > self.wage

    @property
    def shut(self) -> bool:
        """Below this a shed loses money on every unit it makes."""
        return self.staffed > 0 and self.net < self.wage


def marginal_hands(settlement) -> List[MarginalHand]:
    """Every shed, sorted by what the next hand in it would be worth.

    This is the whole of the hiring decision in one table: hire while the
    value of the marginal product beats the wage, and close what is under it.
    The game already made you take that decision with `work` and `close`; it
    simply never showed you the number you were guessing at.
    """
    prod = settlement.productivity()
    rows: List[MarginalHand] = []
    for b in settlement.buildings:
        spec = b.spec
        if not b.complete or not spec.jobs or not spec.outputs:
            continue
        per_hand = prod / spec.jobs
        price = settlement.market.price
        value = sum(qty * per_hand * price(k) for k, qty in spec.outputs.items())
        eats = sum(qty * per_hand * price(k) for k, qty in spec.inputs.items())
        rows.append(MarginalHand(
            key=spec.key, name=spec.name, uid=b.uid, staffed=b.staffed,
            jobs=spec.jobs, product=per_hand,
            units=sum(qty * per_hand for qty in spec.outputs.values()),
            value=value, input_cost=eats))
    rows.sort(key=lambda r: -r.net)
    return rows
