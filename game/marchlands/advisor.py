"""The counting house: what a cart would actually earn.

Reading two posted prices and subtracting is how new merchants go broke. The
scan here fills the trade against *copies* of the real markets, so the number
it reports already includes price impact, the spread, tolls, the weight of the
goods, and the days on the road. If it says 40c a day, that is after all of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from . import config as C
from .goods import ALL_KEYS, good
from .market import Market
from .trade import Order, Stop


def _clone(m: Market) -> Market:
    c = Market(name=m.name, stock=dict(m.stock), target=dict(m.target),
               spread=m.spread, tariff_rate=m.tariff_rate, tradeable=m.tradeable)
    c.posted.update(m.posted)
    return c


@dataclass
class Leg:
    good: str
    qty: float
    buy_cost: float
    sell_value: float

    @property
    def profit(self) -> float:
        return self.sell_value - self.buy_cost


@dataclass
class Opportunity:
    frm: str
    to: str
    out: Optional[Leg]          # goods carried there
    back: Optional[Leg]         # goods carried home
    days: float
    profit: float
    per_day: float

    def describe(self, name_of) -> str:
        bits = []
        if self.out:
            bits.append(f"{self.out.qty:.0f} {good(self.out.good).name} "
                        f"-> {name_of(self.to)} ({self.out.profit:+.0f}c)")
        if self.back:
            bits.append(f"{self.back.qty:.0f} {good(self.back.good).name} "
                        f"-> {name_of(self.frm)} ({self.back.profit:+.0f}c)")
        return (f"{name_of(self.frm)} <-> {name_of(self.to)}  "
                f"{self.days:.0f}d round trip  {self.profit:+.0f}c  "
                f"({self.per_day:+.1f}c/day): " + "; ".join(bits))


def _best_cargo(src: Market, dst: Market, capacity: float,
                budget: float, tariff_src: float, tariff_dst: float,
                exclude: Sequence[str] = ()) -> Optional[Leg]:
    """The single most profitable good to carry src -> dst, priced honestly."""
    best: Optional[Leg] = None
    for k in ALL_KEYS:
        if k in exclude or not (src.sells(k) and dst.sells(k)):
            continue
        if dst.bid(k) <= src.ask(k):
            continue
        a, b = _clone(src), _clone(dst)
        a.tariff_rate, b.tariff_rate = tariff_src, tariff_dst
        qty = capacity / max(good(k).weight, 1e-6)
        buy = a.buy_from(k, qty, budget=budget)
        if buy.quantity <= 0:
            continue
        sell = b.sell_to(k, buy.quantity)
        leg = Leg(good=k, qty=buy.quantity, buy_cost=buy.net,
                  sell_value=sell.value - sell.tariff)
        if leg.profit <= 0:
            continue
        if best is None or leg.profit > best.profit:
            best = leg
    return best


def scan(world, home: str, capacity: float = C.CARAVAN_BASE_CAPACITY,
         speed: float = C.CARAVAN_BASE_SPEED, budget: float = 1e9,
         daily_cost: float = C.CARAVAN_UPKEEP + C.GUARD_COST,
         top: int = 8, include_home: bool = True) -> List[Opportunity]:
    """Rank round trips by coin per day, the only number a cart cares about."""
    nodes = list(world.towns.keys())
    if include_home:
        nodes += list(world.settlements.keys())
    out: List[Opportunity] = []
    seen = set()
    for a in nodes:
        ma = world.market_of(a)
        for b in nodes:
            if a == b or (b, a) in seen:
                continue
            seen.add((a, b))
            mb = world.market_of(b)
            if ma is None or mb is None:
                continue
            ta = world.tariff_for(a, None)
            tb = world.tariff_for(b, None)
            # Delivering into your own town earns no coin -- it is a supply run,
            # and pretending otherwise is how a scanner lies to you. Goods
            # *taken* from your own stores still cost you what you could have
            # sold them for, so the buy side of a home leg is priced normally.
            a_home, b_home = a in world.settlements, b in world.settlements
            leg_out = None if b_home else _best_cargo(ma, mb, capacity, budget, ta, tb)
            leg_back = None if a_home else _best_cargo(
                mb, ma, capacity, budget, tb, ta,
                exclude=(leg_out.good,) if leg_out else ())
            if not leg_out and not leg_back:
                continue
            dist = world.distance(a, b)
            travel = 2.0 * max(1.0, dist / max(speed, 1.0))
            profit = (leg_out.profit if leg_out else 0.0) + \
                     (leg_back.profit if leg_back else 0.0)
            per_day = profit / travel - daily_cost
            out.append(Opportunity(frm=a, to=b, out=leg_out, back=leg_back,
                                   days=travel, profit=profit, per_day=per_day))
    out.sort(key=lambda o: -o.per_day)
    return out[:top]


def route_from(opp: Opportunity, safety: float = 0.85) -> List[Stop]:
    """Turn an opportunity into a standing two-stop loop.

    Limit prices are set a little inside the scanned prices: by the time the
    cart arrives the market has moved, and a merchant who buys at any price is
    a merchant the market is happy to see coming.
    """
    stops: List[Stop] = []
    first = Stop(node=opp.frm)
    second = Stop(node=opp.to)
    if opp.out:
        avg = opp.out.buy_cost / max(opp.out.qty, 1e-6)
        first.buy.append(Order(good=opp.out.good, quantity=opp.out.qty,
                               limit_price=round(avg / safety, 2)))
        sell_avg = opp.out.sell_value / max(opp.out.qty, 1e-6)
        second.sell.append(Order(good=opp.out.good, quantity=-1,
                                 limit_price=round(sell_avg * safety, 2)))
    if opp.back:
        avg = opp.back.buy_cost / max(opp.back.qty, 1e-6)
        second.buy.append(Order(good=opp.back.good, quantity=opp.back.qty,
                                limit_price=round(avg / safety, 2)))
        sell_avg = opp.back.sell_value / max(opp.back.qty, 1e-6)
        first.sell.append(Order(good=opp.back.good, quantity=-1,
                                limit_price=round(sell_avg * safety, 2)))
    stops.append(first)
    stops.append(second)
    return stops


def shortage_report(settlement) -> List[Tuple[str, float, float]]:
    """Goods your own town is burning faster than it makes them."""
    rep = settlement.report
    rows = []
    for k in ALL_KEYS:
        made = rep.produced.get(k, 0.0)
        used = rep.consumed.get(k, 0.0) + rep.eaten.get(k, 0.0)
        if used > made + 1e-6:
            rows.append((k, made - used, settlement.market.stock.get(k, 0.0)))
    rows.sort(key=lambda r: r[1])
    return rows
