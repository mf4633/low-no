# Marchlands

A medieval town, trade and war game that takes the parts of **Age of Empires II**
and **Stronghold** that made them worth replaying, and puts the economy in the
middle where both of them had it.

Pure Python, standard library only, runs in a terminal.

```bash
cd game
python3 -m marchlands                     # play
python3 -m marchlands --house hansa       # pick your house
python3 -m marchlands --sim 1080          # run it headless and print a report
python3 -m unittest discover -s tests     # 140 tests, ~80s
```

> Housed in this repository under `game/` because the session's branch scope is
> `mf4633/low-no`. It shares no code with the trading system in the repository
> root and lifts out cleanly with `git subtree split -P game`.

---

## What it takes from each

**From Age of Empires II** — four ages you climb by paying for them, a
technology tree that is a series of permanent decisions rather than a checklist,
unit types that beat each other in a triangle, resource patches that run dry, a
civilisation bonus and a unique unit, and more than one way to win.

**From Stronghold** — popularity as the master dial, rations and taxes as the
two levers on it, ale and a chapel and a garden against gallows and stocks, a
weapons industry that *is* the army (coin plus a sword your own smith made), and
walls that decide sieges.

**Its own** — the trade layer. In both parents trade was a side activity. Here
coin only enters your treasury through thin taxes and the road, so the market is
where the game is played.

## The three systems

**Land → labour.** Fixed slots of fertile, forest, hill, clay and coastal
ground, plus town plots and a separate castle perimeter. A quarry needs hills; a
farm needs fields. No site has enough of everything, so no site closes every
chain alone. Quarries and mines work a *seam*: the hill holds a finite amount,
and when it is gone the sheds stand idle for good.

**Labour → goods.** Buildings turn inputs into outputs at a rate set by how many
jobs are filled, the season, the town's mood, and what you have researched.
Wheat → flour → bread nearly doubles what a field feeds, which is the whole
argument for paying a miller and a baker rather than eating the grain.

**Goods → coin.** Population is labour, not a revenue farm: it eats far more
than it ever pays in tax. What you make has to reach somebody who wants it.

## Why the prices behave

A price is a function of stock:

```
price = base × (target / stock) ^ elasticity      clamped to [0.25×, 6×] base
```

Everything follows from that one line:

* **Trades move prices.** Orders fill in small lots and each lot changes the
  stock, so the second hundred bushels never fetch what the first did. A trade
  closes its own gap as it executes.
* **Posted prices lag.** The quoted price relaxes toward the fundamental by 20%
  a day, so a shock takes a week to be priced. That lag is the merchant's
  margin.
* **Dumping is real.** Sell four hundred bolts of cloth into one town and you
  have crashed its cloth market for a month, including for yourself.
* **Foreign towns have a metabolism.** Each has a daily surplus or deficit and a
  pull back to equilibrium standing in for its trade with everyone who is not
  you. A town long of wool is a place to buy wool; sell into it hard enough and
  you invert it.
* **A route wears out.** Your own laps close the gap you were living on. When
  the volume falls away the cart reports the route worked out and stands idle,
  and you go and find another.

Spreads are opened by seasonal shocks — a siege eats weapons, a blight eats
grain, a fashion eats silk — and closed again by three rival trading houses
running the same arithmetic every day.

`scan` fills every candidate trade against *copies* of the live markets, so the
coins-per-day it reports already includes price impact, spread, tolls, cargo
weight, and days on the road. It will not book revenue for delivering into your
own town: that is a supply run, not a sale. And it never proposes emptying more
than a third of your own stores, because a merchant who does that is not a
merchant for long.

## The long game

**Ages.** Clearing → Craft → Castle → Crown. Each is paid for in coin and goods,
takes weeks of work, and gates a tier of buildings, technologies and soldiers.

**Technologies.** Twenty-five of them, researched one at a time in a guildhall:
heavy ploughs and three-field rotation, watermills and blast furnaces, drove
roads and ox carts, letters of credit and a counting house, masonry and murder
holes, crossbows, plate armour, chivalry, trebuchet frames. Multipliers compound,
so the order you take them in is a real decision.

**Houses.** Pick one at the start; it is a hidden technology you are simply born
knowing, with its own bonuses and one soldier nobody else can muster.

| house | bonus | unique |
|---|---|---|
| House of the Plough | +15% field yield, +10% housing | Billman |
| The Hansa of Havnhold | +35 cart capacity, −25% tolls, interest | Hanse Guard |
| House Ironhand | +15% craft yield, −10% recruiting | Ironhand Serjeant |
| The Marcher Lords | +25% walls, +10% attack, −15% recruiting | Border Horse |
| Abbey of Saint Cuth | +7 mood, −30% spoilage, +30% research | Abbey Guard |

## War

Soldiers are **made, not bought**: a barracks turns coin plus arms from your own
workshops into men — spears from a poleturner, bows from a fletcher, swords from
an armoury, plate from an armourer. Every soldier also walks out of the labour
pool, so an army is paid for twice: once in coin, once in fields nobody works.

Spears break horse. Horse rides down bows and siege crews. Foot in armour walks
through bows. None of it matters while a wall is standing — without rams or
trebuchets a host can only sit outside until it gets bored and goes home. While
the wall is high the garrison is barely exposed; as it comes down they are
shooting over rubble.

Lords grow bolder the richer you look, and they take offence at their own rates,
so wars arrive one at a time rather than as a committee. `war` shows who is
arming and what each could field today. Take a town and it bends the knee: no
tolls, daily tribute, and every other lord one step angrier. A beaten host walks
home and thickens the garrison you will have to get through next time.

Being stormed is a catastrophe, not a trapdoor: the keep is thrown down, the town
gutted, and you carry on from whatever else you hold — which is the best argument
there is for founding a second settlement before you need one.

## Winning

Three ways, inside three years:

* **Wealth** — 120,000c of net worth with 450 souls under your rule.
* **Dominion** — three of the seven towns sworn to you *and held*.
* **The bells** — finish the cathedral and hold it half a year.

You lose if your debts pass 3,000c or there is nowhere left that you hold.

## A first session

```
> map                       where everything is, and how far
> town                      buildings, mood, seams, walls, what you're burning
> needs                     what is running down and how many days are left
> scan                      what a cart would actually earn today
> auto 1                    put a cart on the best of it
> build mill                bread is worth more than the wheat in it
> age                       what the next age costs, and `age begin` to start
> tech                      what the guildhall could take up
> next 10                   ten days pass
> prices bread              every market's price, with a trend line
> market caldmoor           a mining camp that cannot feed itself
> ration generous           mood costs food; food costs land
> units                     who you may muster, and what arms they need
> recruit spearman 6
> war                       who is arming, and how big a host they could field
> host aldworth spearman 20 archer 12 ram 3 engineer 6
> march 1 dunmere
> truce marchand 180        peace, by the day, from the lord you are not ready for
```

Type `help`, or `help trade`, `help town`, `help war`, `help win`.

## Layout

| file | role |
|---|---|
| `goods.py` | 25 goods: price, weight, spoilage, elasticity, nourishment |
| `buildings.py` | 47 buildings: land, jobs, recipes, effects, age, seams |
| `market.py` | the price curve, lot-by-lot filling, spread, tolls, transfers |
| `settlement.py` | land, labour, production, feeding, mood, fear, walls, seams |
| `world.py` | the map, foreign towns and their lords, roads, unclaimed sites |
| `trade.py` | caravans, standing routes, banditry, loading and unloading |
| `advisor.py` | the counting house: honest arbitrage scan, route builder |
| `tech.py` | four ages, 25 technologies, five houses |
| `military.py` | 14 unit types, the counter triangle, battles, sieges |
| `events.py` | shocks, rival trading houses, bandits |
| `engine.py` | the tick, the ledger, research, war, endings, save/load |
| `scenario.py` | the starting map |
| `cli.py` | the terminal interface |
| `sim.py` | two headless bots (trader, conqueror), used as balance tests |
| `config.py` | every tunable number in the game |

## Tuning

All balance lives in `config.py` and the data tables. The one number to respect
is `WAGE`: every base price in `goods.py` was set against the cost of a
worker-day, so moving it moves the margin on every trade at once.

Several tests are balance guards rather than correctness tests. The trading bot
in `sim.py` should survive most starts (or the opening is too punishing), should
climb at least to the second age and usually the third (or the age costs are out
of reach), should manage some research and a second settlement, and should
**not** reach the goal (or the goal is too easy). At the time of writing it
finishes six seeds alive, all of them in the Age of the Castle with 13–16
technologies and three settlements, at 40k–70k against a 120,000c target — while
the lords take three or four towns off each other in the background.

An honest note on the conquest path. `Conqueror` in `sim.py` grows an economy,
turns it into a war footing, buys the iron two hills cannot supply, and takes
towns — but it peaks at one or two of them, not three. The mechanics are proven
by tests (a properly equipped host takes a town; a town taken and garrisoned is
held; the ending fires), so Dominion is reachable rather than decorative, but it
is the hardest of the three paths and a bot that plays it naively does not get
there. If you retune the military numbers, run both bots.
