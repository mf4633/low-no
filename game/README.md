# Marchlands

A medieval town, trade and war game that takes the parts of **Age of Empires II**
and **Stronghold** that made them worth replaying, and puts the economy in the
middle where both of them had it.

Pure Python, standard library only, runs in a terminal.

```bash
cd game
python3 -m marchlands                          # play the default scenario
python3 -m marchlands --list                   # the four scenarios and five houses
python3 -m marchlands --scenario salt_road --house hansa
python3 -m marchlands --sim 1080               # run it headless and print a report
python3 -m unittest discover -s tests          # 186 tests, ~100s
```

In game, `hint` tells you what a patient steward would point at next, `briefing`
restates why you are here, and `help` lists everything.

> Housed in this repository under `game/` because the session's branch scope is
> `mf4633/low-no`. It shares no code with the trading system in the repository
> root and lifts out cleanly with `git subtree split -P game`.

---

## What it takes from each

**From Age of Empires II** — four ages you climb by paying for them, a
technology tree that is a series of permanent decisions rather than a checklist,
unit types that beat each other in a triangle, resource patches that run dry, a
civilisation bonus and a unique unit, rival lords who develop and fight each
other, and more than one way to win.

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
farm needs fields; a harbour needs a shore. No site has enough of everything, so
no site closes every chain alone. Quarries and mines work a *seam*: the hill
holds a finite amount, and when it is gone the sheds stand idle for good.

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

* **Trades move prices.** Orders fill in lots, each lot priced at the level it
  leaves behind, so the second hundred bushels never fetch what the first did.
  A trade closes its own gap as it executes, and a round trip always loses.
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
weight and days on the road. It spreads a hold over several goods rather than
filling it with one (which would crater the price of that one), it will not
book revenue for delivering into your own town — that is a supply run, not a
sale — and it never proposes emptying more than a third of your own stores.

## The road and the sea

A cart carries 150 units at 32 leagues a day and can be robbed. A **cog** carries
420 at 60 sea leagues a day, calls only where there is a harbour, and answers to
the weather instead of to bandits — the winter sea is three times the risk of
the summer one, and no number of guards changes that.

Three foreign towns have harbours and your own coast can have one, which is the
argument for settling the shore: bring the inland surplus down by cart, then move
it in bulk. Caer Ithel has no road worth the name at all; you come by sea or you
do not come.

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

**The other lords are playing too.** Every town has a prosperity that climbs in
peace and drives its walls, garrison and muster together, so a town you meant to
take next season is a harder problem than the one you scouted. They scheme
against each other as well as against you — in a typical game three or four
towns change hands between AI lords while you are busy, your own sworn towns
included. `war` shows who answers to whom and what each could field today.

Not all of it has to be met with soldiers. A **gift** cools a temper, a **truce**
buys a fixed number of quiet days at a price set by the lord's strength, and a
**demand** squeezes tribute out of a lord too weak to refuse — and is remembered
by one who is not.

Take a town and it bends the knee: no tolls, daily tribute, a garrison left
behind out of your own host, and every other lord one step angrier. Hold it with
something visible, though — a vassal you cannot overawe eventually remembers it
has walls of its own.

Being stormed is a catastrophe, not a trapdoor: the keep is thrown down, the town
gutted, and you carry on from whatever else you hold — which is the best argument
there is for founding a second settlement before you need one.

## Scenarios

Four games on the same rules. `--list` describes them; they are meant to be
played in this order.

| scenario | length | what it is |
|---|---|---|
| **The Salt Road** | 2 years | A coastal seat with a quay, quiet lords and no conquest on the table. The trade game with the training wheels of geography: you start where the sea is. |
| **The Marchlands** | 3 years | The full game. One inland hill, seven towns, all three ways to win. |
| **The Iron Marches** | 3 years | Ore under you and nothing that grows. Every lord already dislikes you. Wealth or dominion, no cathedral. |
| **The Winter Crown** | 2½ years | Midwinter, a month of bread, a short rope and angry neighbours. The hard one. |

## Winning

Three ways, where the scenario offers them:

* **Wealth** — a target net worth *and* a population to go with it.
* **Dominion** — three of the seven towns sworn to you and still held.
* **The bells** — finish the cathedral and hold it half a year.

You lose if your debts run away, or there is nowhere left that you hold.

## A first session

```
> hint                      what a patient steward would point at
> map                       where everything is, and how far
> town                      buildings, mood, seams, walls, what you're burning
> scan                      what a cart would actually earn today
> auto 1                    put a cart on the best of it
> build mill                bread is worth more than the wheat in it
> age                       what the next age costs; `age begin` starts it
> tech                      what the guildhall could take up
> next 10                   ten days pass
> prices bread              every market's price, with a trend line
> found sealow              settle the coast; build a harbour; `scan sea`
> war                       who is arming, and how big a host they could field
> truce marchand 180        peace by the day, from the lord you are not ready for
> host aldworth spearman 20 archer 12 ram 3 engineer 6
> march 1 dunmere
```

## Layout

| file | role |
|---|---|
| `goods.py` | 25 goods: price, weight, spoilage, elasticity, nourishment |
| `buildings.py` | 48 buildings: land, jobs, recipes, effects, age, seams |
| `market.py` | the price curve, lot-by-lot filling, spread, tolls, transfers |
| `settlement.py` | land, labour, production, feeding, mood, fear, walls, seams |
| `world.py` | the map, towns and their lords, roads, sea lanes, unclaimed land |
| `trade.py` | carts and cogs, standing routes, banditry, storms |
| `advisor.py` | the counting house: two-pass scan, manifests, route builder |
| `tech.py` | four ages, 25 technologies, five houses |
| `military.py` | 14 unit types, the counter triangle, battles, sieges |
| `events.py` | shocks, rival trading houses, bandits |
| `engine.py` | the tick, the ledger, research, war, diplomacy, endings, saves |
| `scenario.py` | the map's pieces, and the default seat |
| `scenarios.py` | the four scenarios and their terms |
| `cli.py` | the terminal interface |
| `sim.py` | two headless bots (trader, conqueror), used as balance tests |
| `config.py` | every tunable number in the game |

## Tuning

All balance lives in `config.py` and the data tables. The one number to respect
is `WAGE`: every base price in `goods.py` was set against the cost of a
worker-day, so moving it moves the margin on every trade at once. Victory terms
are per-scenario (`engine.Goals`), not global.

Several tests are balance guards rather than correctness tests. The important
one is `test_the_goal_is_reachable_but_not_assured`: the trading bot in `sim.py`
plays the economic game competently and no better, and over four seeds it should
take the crown **sometimes and not always**. At the time of writing it wins four
of eight seeds on the default scenario, usually in the last few months, with the
rest finishing between 21k and 83k of a 120,000c target. A target nobody can
reach is decoration; one that falls out of an ordinary policy every time is a
formality.

The others: every scenario must be survivable by that bot and none of them a
walkover; the lords must take towns off each other; the second and third ages
must be affordable.

An honest note on the conquest path. `Conqueror` in `sim.py` grows an economy,
turns it into a war footing, buys the iron two hills cannot supply, and takes
towns — but it peaks at one or two, not three. The mechanics are proven by tests
(a properly equipped host takes a town; a town taken and garrisoned is held; the
ending fires), so Dominion is reachable rather than decorative, but it is the
hardest of the three paths and a bot that plays it naively does not get there.
If you retune the military numbers, run both bots:

```bash
python3 -m marchlands --sim 1080                      # the trader
python3 -m marchlands --sim 1080 --scenario iron_marches
```
