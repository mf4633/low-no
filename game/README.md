# Marchlands

A medieval town-and-trade game in the spirit of **Stronghold**'s economy screen and
**Age of Empires II**'s production chains — with the trade layer promoted from a
side activity to the point of the game.

Pure Python, standard library only, runs in a terminal.

```bash
cd game
python3 -m marchlands              # play
python3 -m marchlands --sim 1080   # run the economy headless and print a report
python3 -m unittest discover -s tests
```

> Housed in this repository under `game/` because the session's branch scope is
> `mf4633/low-no`. It shares no code with the trading system in the repository
> root and can be lifted out with `git subtree split -P game` whenever you want
> it to have its own home.

---

## The idea

Three systems, each feeding the next:

**Land → labour.** Your settlement has a fixed number of fertile, forest, hill,
clay and coastal slots. A farm needs fertile ground, a quarry needs hills. No
site has enough of everything, so no site can close every production chain on
its own.

**Labour → goods.** Buildings turn inputs into outputs at a rate set by how many
of their jobs are filled, how the season is running, and how the townspeople
feel. Wheat → flour → bread nearly doubles the food a field yields, which is the
whole argument for paying a miller and a baker.

**Goods → coin.** Coin only enters your treasury through thin taxes and through
the road. A population is labour, not a revenue farm: it eats more than it ever
pays. What you make must reach somebody who wants it.

## Why the prices behave

A price is a function of stock:

```
price = base × (target / stock) ^ elasticity      clamped to [0.25×, 6×] base
```

Everything follows from that one line:

* **Trades move prices.** Orders are filled in small lots, and each lot changes
  the stock, so the second hundred bushels never fetch what the first did. There
  is no infinite arbitrage — the trade closes its own gap as it executes.
* **Posted prices lag.** The market's quoted price relaxes toward the
  fundamental by 20% a day, so a shock takes a week to be fully priced. That lag
  is where a merchant's profit lives.
* **Dumping is real.** Sell four hundred bolts of cloth into one town and you
  have crashed its cloth market for a month, including for yourself.
* **Foreign towns have a metabolism.** Each has a daily surplus or deficit and a
  pull back toward equilibrium standing in for its trade with everyone who is
  not you. A town long of wool is a place to buy wool; sell into it hard enough
  and you invert it.

## Why the spreads don't just sit there

* **Shocks open them.** A siege eats weapons, a blight eats grain, a fashion eats
  silk. Each runs for a season or two and is announced in the log.
* **Rival houses close them.** Three AI trading companies run the same
  arithmetic you do, every day, and every run they make narrows the gap you were
  about to take. An edge you found last month is worth less this month.
* **The road taxes them.** Tolls on both sides of a foreign deal, a day per 32
  leagues, wages for the cart and its guards, and bandits who take a quarter of
  the load when they catch you.

`scan` fills every candidate trade against *copies* of the live markets, so the
coins-per-day it reports already includes price impact, spread, tolls, the
weight of the goods and the days on the road. It will not book revenue for
delivering into your own town — that is a supply run, not a sale, and a scanner
that pretends otherwise is how a merchant goes broke confidently.

## A first session

```
> map                       where everything is, and how far
> town                      your buildings, your mood, what you're burning
> needs                     what is running down and how many days are left
> scan                      what a cart would actually earn today
> auto 1                    put your cart on the best of it
> build mill                bread is worth more than the wheat in it
> next 10                   ten days pass
> prices bread              every market's price, with a trend line
> market caldmoor           a mining camp that cannot feed itself
> ration generous           mood costs food; food costs land
> route 2 add aldworth buy ale 80@9
> route 2 add ostmark sell ale all@11 buy iron 60@16
> go 2
```

Type `help`, or `help trade`, `help town`, `help win`.

### Winning

120,000c of net worth with 450 souls, inside three years. One hill will not hold
450 people — the sites at Sealow (salt flats) and Greyfell (iron and stone) are
there to be settled, and a new colony starves without a cart running food to it
until its own fields come in.

You lose at 3,000c of debt, or when the last family walks out of the gate.

## Layout

| file | role |
|---|---|
| `goods.py` | 22 goods: price, weight, spoilage, elasticity, nourishment |
| `buildings.py` | 32 buildings: land, jobs, recipes, effects |
| `market.py` | the price curve, lot-by-lot order filling, spread, tolls |
| `settlement.py` | land, labour, production, feeding, mood, migration |
| `world.py` | the map, foreign towns, distances, road danger, unclaimed sites |
| `trade.py` | caravans, standing routes, banditry, loading and unloading |
| `advisor.py` | the counting house: honest arbitrage scan, route builder |
| `events.py` | shocks, rival trading houses, raids |
| `engine.py` | the tick, the ledger, endings, save/load |
| `scenario.py` | the starting map |
| `cli.py` | the terminal interface |
| `sim.py` | headless bot, used as a balance test |
| `config.py` | every tunable number in the game |

## Tuning

All balance lives in `config.py` and the two data tables. The one number to
respect is `WAGE`: every base price in `goods.py` was set against the cost of a
worker-day, so moving it moves the margin on every trade in the game at once.

Two tests in `tests/test_engine.py` are balance guards rather than correctness
tests: the naive bot in `sim.py` should survive most starts (or the opening is
too punishing) and should not reach the goal (or the goal is too easy). If you
retune, run them.

```bash
python3 -m unittest discover -s tests     # 80 tests, ~25s
```
