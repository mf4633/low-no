"""The counting house: what a cart would actually earn.

Reading two posted prices and subtracting is how new merchants go broke. The
scan here fills the trade against *copies* of the real markets, so the number
it reports already includes price impact, the spread, tolls, the weight of the
goods, and the days on the road. If it says 40c a day, that is after all of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import config as C
from .goods import ALL_KEYS, good
from .market import Market
from .trade import Order, Stop


def _snap(m: Market, key: str) -> Tuple[float, float]:
    return (m.stock[key], m.posted[key])


def _restore(m: Market, key: str, snap: Tuple[float, float]) -> None:
    m.stock[key], m.posted[key] = snap


#: How finely a scratch copy walks the price curve. The ranking is the same
#: either way; the estimate is a little pessimistic when coarse, which is the
#: safe direction for an advisor. The console scans on demand and can afford to
#: be exact; a bot scanning every few days for a whole fleet cannot.
FINE_STEPS = 20
FAST_STEPS = 6


def _clone(m: Market, steps: int = FINE_STEPS) -> Market:
    c = Market(name=m.name, stock=dict(m.stock), target=dict(m.target),
               spread=m.spread, tariff_rate=m.tariff_rate, tradeable=m.tradeable,
               max_steps=steps)
    c.posted.update(m.posted)
    return c


@dataclass
class Leg:
    """One direction of a trip: what goes in the hold, and what it makes."""
    cargo: Dict[str, float] = field(default_factory=dict)
    costs: Dict[str, float] = field(default_factory=dict)     # per good, paid
    revenues: Dict[str, float] = field(default_factory=dict)  # per good, taken
    buy_cost: float = 0.0
    sell_value: float = 0.0

    def unit_cost(self, key: str) -> float:
        """What a unit of this good actually cost on this leg."""
        return self.costs.get(key, 0.0) / max(self.cargo.get(key, 0.0), 1e-6)

    @property
    def profit(self) -> float:
        return self.sell_value - self.buy_cost

    @property
    def good(self) -> str:
        return max(self.cargo, key=lambda k: self.cargo[k]) if self.cargo else ""

    @property
    def qty(self) -> float:
        return sum(self.cargo.values())

    def describe(self) -> str:
        return ", ".join(f"{q:.0f} {good(k).name}"
                         for k, q in sorted(self.cargo.items(), key=lambda kv: -kv[1]))


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
            bits.append(f"{self.out.describe()} -> {name_of(self.to)} "
                        f"({self.out.profit:+.0f}c)")
        if self.back:
            bits.append(f"{self.back.describe()} -> {name_of(self.frm)} "
                        f"({self.back.profit:+.0f}c)")
        return (f"{name_of(self.frm)} <-> {name_of(self.to)}  "
                f"{self.days:.0f}d round trip  {self.profit:+.0f}c  "
                f"({self.per_day:+.1f}c/day): " + "; ".join(bits))


#: A merchant who empties his own stores to fill a cart is not a merchant.
HOME_DRAW = 0.40
#: Fractions of the remaining hold to test for each good. Filling the hold with
#: one commodity is how you turn a good trade into a bad one.
LOTS = (1.0, 0.55, 0.28, 0.12)
#: How many different goods one leg will carry.
MANIFEST_WIDTH = 3
#: How many candidate goods get the full quantity search each round.
SHORTLIST = 7


def _try_good(src: Market, dst: Market, key: str, space: float,
              budget: float) -> Optional[Tuple[float, float, float]]:
    """Best (quantity, cost, revenue) for one good in `space` cart units.

    Works on the caller's markets and puts them back afterwards: only one
    good's stock and posted price move in a fill, so there is no reason to copy
    two whole markets for every candidate lot.
    """
    best = None
    room = space / max(good(key).weight, 1e-6)
    for frac in LOTS:
        qty = room * frac
        if qty <= 0.5:
            continue
        sa, sb = _snap(src, key), _snap(dst, key)
        buy = src.buy_from(key, qty, budget=budget)
        profit = None
        if buy.quantity > 0:
            sell = dst.sell_to(key, buy.quantity)
            profit = (sell.value - sell.tariff) - buy.net
            got = (buy.quantity, buy.net, sell.value - sell.tariff)
        _restore(src, key, sa)
        _restore(dst, key, sb)
        if profit is None or profit <= 0:
            continue
        if best is None or profit > best[0]:
            best = (profit,) + got
    return best[1:] if best else None


def _best_manifest(src: Market, dst: Market, capacity: float,
                   budget: float, tariff_src: float, tariff_dst: float,
                   exclude: Sequence[str] = (), from_home: bool = False,
                   steps: int = FINE_STEPS) -> Optional[Leg]:
    """Fill a hold src -> dst, priced honestly and spread over a few goods.

    Each good is committed against shared copies of the two markets, so the
    second choice sees the prices the first one moved. This is the difference
    between a scan a big hull can act on and a scan that says every voyage is
    worthless.
    """
    a, b = _clone(src, steps), _clone(dst, steps)
    a.tariff_rate, b.tariff_rate = tariff_src, tariff_dst
    leg = Leg()
    space = capacity
    taken = set(exclude)
    for _ in range(MANIFEST_WIDTH):
        # Rank the candidates by the crude margin per cart unit first and only
        # price the best handful properly. The quantity search is the expensive
        # part; spending it on goods that are obviously not going is waste.
        shortlist: List[Tuple[float, str]] = []
        for k in ALL_KEYS:
            if k in taken or not (a.sells(k) and b.sells(k)):
                continue
            ask = a.ask(k)
            margin = b.bid(k) - ask
            if margin <= ask * 0.04:             # not worth the wheels
                continue
            shortlist.append((margin / good(k).weight, k))
        shortlist.sort(reverse=True)
        best, best_key = None, None
        for _score, k in shortlist[:SHORTLIST]:
            room = space
            if from_home:
                room = min(room, src.stock.get(k, 0.0) * HOME_DRAW
                           * good(k).weight)
            cash = None if from_home else max(0.0, budget - leg.buy_cost)
            got = _try_good(a, b, k, room, cash if cash is not None else 1e12)
            if got and (best is None or (got[2] - got[1]) > (best[2] - best[1])):
                best, best_key = got, k
        if best is None or best_key is None:
            break
        qty, cost, revenue = best
        a.buy_from(best_key, qty, budget=None if from_home else 1e12)
        b.sell_to(best_key, qty)
        leg.cargo[best_key] = leg.cargo.get(best_key, 0.0) + qty
        leg.costs[best_key] = leg.costs.get(best_key, 0.0) + cost
        leg.revenues[best_key] = leg.revenues.get(best_key, 0.0) + revenue
        leg.buy_cost += cost
        leg.sell_value += revenue
        space -= qty * good(best_key).weight
        taken.add(best_key)
        if space <= capacity * 0.05:
            break
    return leg if leg.cargo and leg.profit > 0 else None


def scan(world, home: str, capacity: float = C.CARAVAN_BASE_CAPACITY,
         speed: float = C.CARAVAN_BASE_SPEED, budget: float = 1e9,
         daily_cost: float = C.CARAVAN_UPKEEP + C.GUARD_COST,
         top: int = 8, include_home: bool = True,
         sails: bool = False, steps: int = FINE_STEPS) -> List[Opportunity]:
    """Rank round trips by coin per day, the only number a hull cares about."""
    nodes = list(world.towns.keys())
    if include_home:
        nodes += list(world.settlements.keys())
    if sails:
        nodes = [n for n in nodes if world.is_port(n)]
    # Two passes. The first is arithmetic on posted prices and ranks every pair
    # of places; the second does the expensive honest fill on the best of them.
    # Pricing all fifty-odd pairs properly costs more than it can ever tell you.
    ranked: List[Tuple[float, str, str]] = []
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
            gap = 0.0
            for k in ALL_KEYS:
                if not (ma.sells(k) and mb.sells(k)):
                    continue
                w = good(k).weight
                gap = max(gap, (mb.bid(k) - ma.ask(k)) / w,
                          (ma.bid(k) - mb.ask(k)) / w)
            if gap <= 0:
                continue
            dist = world.sea_distance(a, b) if sails else world.distance(a, b)
            ranked.append((gap / max(1.0, dist / max(speed, 1.0)), a, b))
    ranked.sort(reverse=True)

    out: List[Opportunity] = []
    for _score, a, b in ranked[:min(max(top * 2, 10), 16)]:
        ma, mb = world.market_of(a), world.market_of(b)
        ta = world.tariff_for(a, None)
        tb = world.tariff_for(b, None)
        # Delivering into your own town earns no coin -- it is a supply run,
        # and pretending otherwise is how a scanner lies to you. Goods
        # *taken* from your own stores still cost you what you could have
        # sold them for, so the buy side of a home leg is priced normally.
        a_home, b_home = a in world.settlements, b in world.settlements
        leg_out = None if b_home else _best_manifest(
            ma, mb, capacity, budget, ta, tb, from_home=a_home, steps=steps)
        leg_back = None if a_home else _best_manifest(
            mb, ma, capacity, budget, tb, ta, steps=steps,
            exclude=tuple(leg_out.cargo) if leg_out else (), from_home=b_home)
        if not leg_out and not leg_back:
            continue
        dist = world.sea_distance(a, b) if sails else world.distance(a, b)
        travel = 2.0 * max(1.0, dist / max(speed, 1.0))
        profit = (leg_out.profit if leg_out else 0.0) + \
                 (leg_back.profit if leg_back else 0.0)
        per_day = profit / travel - daily_cost
        out.append(Opportunity(frm=a, to=b, out=leg_out, back=leg_back,
                               days=travel, profit=profit, per_day=per_day))
    out.sort(key=lambda o: -o.per_day)
    return out[:top]


#: How far past the scanned price a standing order may chase a purchase.
BUY_SLIP = 1.06
#: The floor a standing order will sell at, as a multiple of what it paid.
#: Anchoring the floor to the *cost* rather than to the hoped-for price is what
#: keeps a cart from sitting on a hold full of tools it will not part with.
SELL_FLOOR = 1.12


def route_from(opp: Opportunity, safety: float = 1.0,
               carrying: Optional[Dict[str, float]] = None) -> List[Stop]:
    """Turn an opportunity into a standing two-stop loop.

    The limit prices are the important part. A cart runs its loop over and over,
    and each lap closes the gap it was living on; without a tight ceiling on
    what it will pay it goes on buying long after the trade has turned against
    it, and quietly bleeds. With one, the volume falls to nothing, the route
    reports itself worked out, and you go and find another.
    """
    stops: List[Stop] = []
    first = Stop(node=opp.frm)
    second = Stop(node=opp.to)
    for leg, buy_at, sell_at in ((opp.out, first, second),
                                 (opp.back, second, first)):
        if not leg:
            continue
        for key, qty in leg.cargo.items():
            avg = max(leg.unit_cost(key), 0.01)
            buy_at.buy.append(Order(good=key, quantity=qty,
                                    limit_price=round(avg * BUY_SLIP * safety, 2)))
            sell_at.sell.append(Order(good=key, quantity=-1,
                                      limit_price=round(avg * SELL_FLOOR, 2)))
    # Anything already in the cart has to go somewhere, or it rides forever and
    # the capacity is gone for good.
    planned = {o.good for st in (first, second) for o in list(st.buy) + list(st.sell)}
    for k, qty in (carrying or {}).items():
        if qty <= 0.05 or k in planned:
            continue
        second.sell.append(Order(good=k, quantity=-1))
        first.sell.append(Order(good=k, quantity=-1))
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
