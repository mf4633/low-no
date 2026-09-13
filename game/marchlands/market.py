"""The price mechanism.

One idea does most of the work here: **a price is a function of stock**, and
every trade moves the stock, so every trade moves the price against the trader.
Large orders walk up (or down) the curve lot by lot, which is what stops a
single fat caravan from draining an arbitrage forever. The posted price is a
lagged tracker of that curve; the lag is exactly where a merchant's profit
lives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config as C
from .goods import ALL_KEYS, good

MIN_STOCK = 0.5


@dataclass
class Fill:
    """Result of a transaction against a market."""
    good: str
    quantity: float = 0.0
    value: float = 0.0          # coins moved, before tariff
    tariff: float = 0.0         # coins skimmed by the host town
    price_start: float = 0.0
    price_end: float = 0.0

    @property
    def avg_price(self) -> float:
        return self.value / self.quantity if self.quantity > 0 else 0.0

    @property
    def net(self) -> float:
        """Coins the trader pays (buy) or receives (sell), tariff included."""
        return self.value + self.tariff


@dataclass
class Market:
    """Stock, posted prices, and the curve that ties them together."""

    name: str
    stock: Dict[str, float] = field(default_factory=dict)
    target: Dict[str, float] = field(default_factory=dict)
    posted: Dict[str, float] = field(default_factory=dict)
    spread: float = C.SPREAD
    tariff_rate: float = 0.0
    history: Dict[str, List[float]] = field(default_factory=dict)
    tradeable: Tuple[str, ...] = ALL_KEYS

    def __post_init__(self) -> None:
        for k in ALL_KEYS:
            self.stock.setdefault(k, 0.0)
            self.target.setdefault(k, 0.0)
            self.posted.setdefault(k, self.curve(k, self.stock[k]))
            self.history.setdefault(k, [])

    # -- the curve -----------------------------------------------------------
    def curve(self, key: str, stock: float) -> float:
        """Fundamental price at a hypothetical stock level."""
        g = good(key)
        tgt = max(self.target.get(key, 0.0), 1.0)
        ratio = tgt / max(stock, MIN_STOCK)
        price = g.base_price * (ratio ** g.elasticity)
        return _clamp(price, g.base_price * C.PRICE_FLOOR_MULT,
                      g.base_price * C.PRICE_CEIL_MULT)

    def fundamental(self, key: str) -> float:
        return self.curve(key, self.stock.get(key, 0.0))

    def price(self, key: str) -> float:
        return self.posted.get(key, good(key).base_price)

    def ask(self, key: str) -> float:
        """What a trader pays the market, per unit, for a small lot."""
        return self.price(key) * (1.0 + self.spread / 2.0)

    def bid(self, key: str) -> float:
        """What the market pays a trader, per unit, for a small lot."""
        return self.price(key) * (1.0 - self.spread / 2.0)

    def sells(self, key: str) -> bool:
        return key in self.tradeable

    # -- daily relaxation ----------------------------------------------------
    def settle_day(self) -> None:
        for k in ALL_KEYS:
            f = self.fundamental(k)
            self.posted[k] += C.PRICE_ADJUST * (f - self.posted[k])
            hist = self.history[k]
            hist.append(self.posted[k])
            if len(hist) > 120:
                del hist[:-120]

    # -- transactions --------------------------------------------------------
    def buy_from(self, key: str, quantity: float,
                 max_price: Optional[float] = None,
                 budget: Optional[float] = None) -> Fill:
        """A trader buys `quantity` out of this market, walking the curve up."""
        fill = Fill(good=key, price_start=self.ask(key))
        if not self.sells(key) or quantity <= 0:
            fill.price_end = fill.price_start
            return fill
        # A market never sells its last crumb.
        available = max(0.0, self.stock[key] - max(MIN_STOCK, 0.02 * self.target.get(key, 0.0)))
        remaining = min(quantity, available)
        p0 = self.curve(key, self.stock[key])
        while remaining > 1e-9:
            lot = min(C.MARKET_LOT, remaining)
            unit = self.price(key) * (1.0 + self.spread / 2.0)
            if max_price is not None and unit > max_price + 1e-9:
                break
            cost = unit * lot
            if budget is not None and fill.net + cost * (1 + self.tariff_rate) > budget:
                affordable = max(0.0, (budget - fill.net) / (unit * (1 + self.tariff_rate)))
                if affordable < 1e-6:
                    break
                lot, cost = affordable, unit * affordable
            self.stock[key] -= lot
            self._reprice_after_trade(key, p0)
            p0 = self.curve(key, self.stock[key])
            fill.quantity += lot
            fill.value += cost
            remaining -= lot
        fill.tariff = fill.value * self.tariff_rate
        fill.price_end = self.ask(key)
        return fill

    def sell_to(self, key: str, quantity: float,
                min_price: Optional[float] = None) -> Fill:
        """A trader sells `quantity` into this market, walking the curve down."""
        fill = Fill(good=key, price_start=self.bid(key))
        if not self.sells(key) or quantity <= 0:
            fill.price_end = fill.price_start
            return fill
        remaining = quantity
        p0 = self.curve(key, self.stock[key])
        while remaining > 1e-9:
            lot = min(C.MARKET_LOT, remaining)
            unit = self.price(key) * (1.0 - self.spread / 2.0)
            if min_price is not None and unit < min_price - 1e-9:
                break
            self.stock[key] += lot
            self._reprice_after_trade(key, p0)
            p0 = self.curve(key, self.stock[key])
            fill.quantity += lot
            fill.value += unit * lot
            remaining -= lot
        fill.tariff = fill.value * self.tariff_rate
        fill.price_end = self.bid(key)
        return fill

    def _reprice_after_trade(self, key: str, price_before: float) -> None:
        """Move the posted price by the same factor the curve moved."""
        after = self.curve(key, self.stock[key])
        if price_before > 0:
            g = good(key)
            self.posted[key] = _clamp(self.posted[key] * (after / price_before),
                                      g.base_price * C.PRICE_FLOOR_MULT,
                                      g.base_price * C.PRICE_CEIL_MULT)

    # -- moving your own goods ----------------------------------------------
    def transfer_out(self, key: str, quantity: float,
                     limit_price: Optional[float] = None) -> float:
        """Load your own stock onto your own cart. No coin changes hands, but
        scarcity still bites: the load walks the price up, and a limit price
        is what stops a cart emptying a granary the town is about to need."""
        moved = 0.0
        remaining = max(0.0, quantity)
        while remaining > 1e-9 and self.stock.get(key, 0.0) > MIN_STOCK:
            if limit_price is not None and self.ask(key) > limit_price + 1e-9:
                break
            p0 = self.curve(key, self.stock[key])
            lot = min(C.MARKET_LOT, remaining, self.stock[key])
            self.stock[key] -= lot
            self._reprice_after_trade(key, p0)
            moved += lot
            remaining -= lot
        return moved

    def transfer_in(self, key: str, quantity: float) -> float:
        remaining = max(0.0, quantity)
        while remaining > 1e-9:
            p0 = self.curve(key, self.stock[key])
            lot = min(C.MARKET_LOT, remaining)
            self.stock[key] += lot
            self._reprice_after_trade(key, p0)
            remaining -= lot
        return quantity

    # -- inventory helpers ---------------------------------------------------
    def add(self, key: str, qty: float) -> None:
        self.stock[key] = self.stock.get(key, 0.0) + qty

    def take(self, key: str, qty: float) -> float:
        """Remove up to `qty`; returns what was actually there."""
        have = self.stock.get(key, 0.0)
        moved = min(have, max(0.0, qty))
        self.stock[key] = have - moved
        return moved

    def total_units(self) -> float:
        return sum(self.stock.values())

    def inventory_value(self) -> float:
        """What the pile is worth, valuing scarcity soberly.

        A market holding two units of a good it has never seen prices them at
        the ceiling; counting that as wealth would let anyone inflate their
        books by importing a thimbleful of silk.
        """
        total = 0.0
        for k in ALL_KEYS:
            unit = min(self.bid(k), 2.0 * good(k).base_price)
            total += self.stock[k] * unit
        return total

    # -- serialisation -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "stock": dict(self.stock),
            "target": dict(self.target),
            "posted": dict(self.posted),
            "spread": self.spread,
            "tariff_rate": self.tariff_rate,
            "history": {k: v[-40:] for k, v in self.history.items()},
            "tradeable": list(self.tradeable),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Market":
        m = cls(name=d["name"], stock=dict(d["stock"]), target=dict(d["target"]),
                spread=d["spread"], tariff_rate=d["tariff_rate"],
                tradeable=tuple(d.get("tradeable", ALL_KEYS)))
        m.posted.update(d["posted"])
        m.history.update({k: list(v) for k, v in d.get("history", {}).items()})
        return m


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def price_table(markets: Dict[str, Market], key: str) -> List[Tuple[str, float, float]]:
    """(town, buy price, sell price) across markets, dearest buyer first."""
    rows = [(m.name, m.ask(key), m.bid(key)) for m in markets.values() if m.sells(key)]
    rows.sort(key=lambda r: -r[2])
    return rows
