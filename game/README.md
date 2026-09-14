# Marchlands

A medieval town, trade and war game that takes the parts of **Age of Empires II**
and **Stronghold** that made them worth replaying, and puts the economy in the
middle where both of them had it.

Pure Python, standard library only, runs in a terminal.

```bash
cd game
python3 -m marchlands --web                    # play it in a browser, drawn
python3 -m marchlands --campaign               # the six-chapter campaign
python3 -m marchlands                          # or one scenario on its own
python3 -m marchlands --list                   # chapters, scenarios and houses
python3 -m marchlands --scenario salt_road --house hansa
python3 -m marchlands --sim 1080               # run it headless and print a report
python3 -m unittest discover -s tests          # 902 tests, ~22min
```

In game, **`view`** draws your town and **`watch`** lets you sit and watch it
work, `chronicle` reads your reign back, `hint` tells you what a patient
steward would point at next, `briefing` restates why you are here, and `help`
lists everything.

### Just playing it

You do not need a terminal, and you do not need Python.

* **Download `Marchlands.exe`** from Releases and double-click it. The game
  opens in your browser: a title screen, a house to be born into, a country to
  play, and a button that says *begin*. Nothing is installed. Your save lands
  in the folder the exe is in.
* **Or double-click `Marchlands.bat`** (Windows) or **`Marchlands.command`**
  (macOS, Linux) in `game/`, if you already have Python 3.9 or newer. Same
  game, no download, and it tells you where to get Python if you have not.

Everything the console game could do is still there — `save`, `load`, picking
a scenario — as buttons on the bar: **menu**, **save**, **resume**,
**country**. The command line is now a shortcut, not the way in.
`packaging/README.md` says how to build the exe yourself.

### Installing it

```bash
pip install ./game            # or: python3 -m build --wheel && pip install dist/*.whl
marchlands --web              # the drawn game; --terminal for the console one
```

Nothing comes with it. `pip list` after installing shows one line, which is
the point — the dependency list has been empty since the first commit and the
browser view did not change that.

> Housed in this repository under `game/` because the session's branch scope is
> `mf4633/low-no`. It shares no code with the trading system in the repository
> root and lifts out cleanly with `git subtree split -P game`.

---

## The Marcher Chronicle

```bash
python3 -m marchlands --campaign
```

Six linked chapters, one house, and a man in the way. This is the part both
parents are actually remembered for, and for the same reason: a scenario asks
whether you can do a thing, a campaign asks what became of you, and the
difference is that the second one has a middle.

| | chapter | teaches | |
|---|---|---|---|
| 1 | **A Small Inheritance** | the market | Your father never once found out what wheat was worth in Vantry. |
| 2 | **The Reeve's Complaint** | the commons | The levy is going out whatever you do. Keep your people anyway. |
| 3 | **The Salt Road** | the sea | The Count is buying the coast and pays over the odds for salt. |
| 4 | **Dust on the Road** | the castle | There is no winning this one. Still be here at the end of it. |
| 5 | **The Bones of St Ceolwulf** | the map | His parties are already on the roads. |
| 6 | **The Count of Marchand** | everything | Three years. There is no seventh chapter. |

Each chapter hands the next one your purse (a share of it, not the whole
thing), everything your house worked out, your lord and whatever is left of
his line — and the chronicle. A chapter you lose still moves you on; you live
with it, and the record says so.

Running under all of it is the Count of Marchand. He is on the map from the
first chapter and has no particular reason to notice you. By the fourth he has
decided what you are, which is a gap in his map.

### The chronicle

Both parents needed this and neither had it. What anybody remembers about a
long game is not the final score, it is the shape of the thing — the year the
host came, the siege that nearly went, the season it was finally all paid for.
A number at the end throws that away.

So the game writes it down as it happens, and `chronicle` reads your reign
back:

```
  -- Dust on the Road --
  spring 1247   The Age of Craft begins
  autumn 1248   ALDWORTH IS STORMED. The keep is thrown down and 4,860c
                carried off. Raise another, or hold what is left of the
                march from somewhere else.
  spring 1249   You held. 116,166c and 483 souls still answer to you,
                which was the whole of what was asked.
```

It keeps its own housekeeping: a fortnight-long siege writes one line rather
than fourteen, another lord's pilgrimage is recorded but does not shoulder
your own years aside, and when it runs out of room the routine years go first
and the keep falling stays.

## What it takes from each

**From Age of Empires II** — four ages you climb by paying for them, a
technology tree that is a series of permanent decisions rather than a checklist,
unit types that beat each other in a triangle, resource patches that run dry, a
civilisation bonus and a unique unit, rival lords who develop and fight each
other, and more than one way to win.

Three of its less-copied ideas matter more than the ages do. **Labour is
always short** — a town has more jobs than hands from early on and never stops
having them, so `work <building> first` is the real economic lever and idle
capacity is the standing cost of everything you built. **You can win by
hurting an economy rather than a wall**: `raid` burns the country, stops the
fields being worked, drives people off the land and rides home with the
contents, and a lord who cannot carry your wall will do it to you. And the
**relics** put something on the map worth leaving home for — five shrines, far
from anybody's walls, paying pilgrims' offerings to whoever holds them, which
is the cheapest way ever invented to stop a strategy game being two players
farming in separate corners.

**From Stronghold** — popularity as the master dial, rations and taxes as the
two levers on it, a garden and a maypole against gallows and stocks, a weapons
industry that *is* the army (coin plus a sword your own smith made), and
castles that are designs rather than hit-point pools — moats, pitch ditches,
killing pits and oil, each answering a different way in.

Two of its ideas are implemented the way Stronghold actually did them rather
than the way they are usually summarised. **Ale and religion are coverage, not
cheer**: an inn serves two hundred souls and a chapel two hundred and sixty, so
a town that grows past them is a town half of which is drinking nothing — the
same building, bought again, is the price of success. And **the lord is a
man**, not a flag: he is worth real numbers in his hall, worth more riding with
a host, and he is then standing where the arrows are. He can fall, or be taken
and ransomed, and there are only so many of his line.

**From Gregory Mankiw's *Principles of Economics*** — the vocabulary. The
simulation was always a supply-and-demand model; what it lacked was the
*reading* of one. See **[The accounts](#the-accounts)**.

**From Mount & Blade: Bannerlord** — the third thing both of the others leave
out: a house. Your lord is a person who gets better at whatever he actually
spends his days doing, who marries somebody's daughter for reasons of state,
whose children grow up while you are busy, and who eventually dies and hands
the whole business to one of them. See **[Your house](#your-house)**.

**Its own** — the trade layer. In both parents trade was a side activity. Here
coin only enters your treasury through thin taxes and the road, so the market is
where the game is played.

## Country you have not memorised

```bash
python3 -m marchlands --region pennines
python3 -m marchlands --region fens --dials hills=0.4,towns=9
python3 -m marchlands --list          # every region, and what its dials say
```

The hand-made march is a good map and it is the only one. Played a sixth time
you are no longer reading the country, you are recalling it — Vantry has the
grain, Caldmoor has the ore, the best opening run is Dunmere and back. A map
you have memorised has stopped asking you anything.

So country can be drawn instead, from **dials** — how hilly, how marshy, how
wooded, how fertile, how much coast, how much ore, how many neighbours and how
far apart — and from **six real places**, each a set of those dials plus the
naming morphology of the actual region.

| | what it is | what that does |
|---|---|---|
| **the Welsh Marches** | oak, sandstone hills, a castle every eight miles | close, wooded, defensible |
| **the Fens** | peat, eels and sedge, no stone for forty miles | poor until you dig |
| **the Rhine Gorge** | one river, vines on the slope, a toll castle on every bend | nine rich neighbours at the gate |
| **the Po Valley** | flat, wet, absurdly fertile, towns close enough to quarrel before breakfast | ten of them, grain everywhere |
| **the Pennines** | gritstone, lead and rain; villages where the seam is | ore under everything, nothing grows |
| **the Baltic Shore** | sand, pine and amber, every town at a river mouth | coast, timber, faces out to sea |

### The dials are dials

```bash
python3 -m marchlands --web      # then `country` in the top bar
```

`--dials hills=0.8,marsh=0.3` on a command line is a string, not a slider: you
cannot feel what a number does by typing it. The browser has the real thing —
six presets, eight sliders, each reading out in words as you move it
(*mountainous*, *half fen*, *a seam under everything*), and the march redrawing
under your hand with its towns placed, sized by their walls and coloured by the
idiom their own ground builds in.

Drawing a country is cheap and starting a game is not, so the preview is live
and free: `GET /draw` makes a march and no game at all. `play this march` is
the only thing that starts one.

These are **characterisations, not survey data** — this is a game and there is
no map server behind it. What is real is the shape of the place and the way its
places are named: `Ludmore` and `Knighton` in the Marches, `Thornmere` and
`Quyfen` in the Fens, `Sanktberg` and `Bacharach` on the Rhine.

Every dial changes what the country is **for**, not what it looks like. A hill
town sells ore and buys bread; a fen town sells almost nothing and buys
everything; a shore town sells salt and wants timber — all of it falling out of
what is under the place rather than written next to it. It reaches the ledger:
the same bot on the same seed finishes at **11,019 in the Fens and 31,844 on
the Rhine**.

### Marsh is land you own and cannot work

The dial that does the most work, and the one worth being careful about. Fen is
not "poor farmland" — it is ground that yields *nothing at all* to anybody who
has not drained it, which is why the drainage of the Fens and the Dutch polders
were the great capital projects of the age. So marsh here is a terrain **no
building will stand on**, it is drawn as standing water and sedge, and the only
thing that has ever changed that is the one that worked in life: dig.

That is [`drainage`](#a-tech-tree-of-institutions), the one technology in the
tree that changes the map — one slot a quarter, slowly enough that the wettest
country is still the hardest place to open.

## The court

```
court [town]              who thinks what of you, and exactly why
ally <town>               swear to a lord who thinks well enough to swear back
call yes / call no        answer an ally who called you to his war
court buy                 pay off the whole letter against you
```

See [The march is a web, not eight quarrels](#the-march-is-a-web-not-eight-quarrels).

## A tech tree of institutions

A tech tree is usually a list of multipliers with a picture on each one. It can
be the other thing: every node an **institution** that the economics or the
politics layer already models, where researching it is what gives you the lever
rather than a percentage.

| | opens | age |
|---|---|---|
| **A Coinage of Your Own** | `mint` — and the whole of seigniorage | II |
| **The Assize of Bread** | `decree`, the legal maximum | II |
| **A Chancery** | `ally` — nobody swears to a house that cannot write | II |
| **The Staple** | foreign goods must be offered in your market first | III |
| **Safe-Conducts** | a sealed letter that gets a cart through a hostile gate | III |
| **Heralds** | a grievance you can *name* lasts twice as long | III |
| **Drainage** | fen becomes field, a slot a quarter | III |
| **The Exchequer** | the same tax rate collects more of itself | IV |

The prerequisites are the real ones. You cannot debase a coinage you do not
strike. You cannot fix the price of bread without a guild to enforce it and a
court to hear the complaints — so the Assize needs the Guild Charter. You
cannot offer a safe-conduct without an embassy to be trusted by, so both it and
the Heralds need the Chancery. An Exchequer is what a Counting House becomes
when it is the crown's.

Three of them change a **mechanic** rather than a number, which is the point of
the branch:

* A **safe-conduct** takes 55% off the *excess* of a hostile toll and nothing
  at all off a friendly one — protection against being stopped, not a discount,
  which is what the thing actually was. A hostile gate falls from 7.4% to 5.5%.
* **Heralds** double how long your own grounds for war stay good.
* **Drainage** is the only technology that edits the map.

And gating `mint`, `decree` and `ally` on institutions is the difference between
a tree that *describes* your town and one that decides what you may do in it.
Each gate says which institution opens it rather than failing silently.

This is also the one change in the project that broke twenty-three existing
tests at once, all of them correctly: they were written when the levers were
unconditional. A test about what a price ceiling *does* is not a test about
whether you are allowed one, so those grant the charter in their setup and get
on with the measurement, and `tests/test_institutions.py` is where being
allowed one is tested.

### It also found a bot that had been buying trebuchets it never used

Adding eight techs took the balance guard from two wins in twelve to none, and
the obvious reading — "the institutions cost too much" — was wrong. The bot
researches the first thing it can afford, in list order, and it had *always*
been buying plate armour, trebuchet frames and the preaching orders and then
never fielding a knight, an engine or a friar. That was invisible while every
tech in the tree was roughly worth having. Eight institutions a trader has no
use for made it visible.

Blocklisting the new techs would have been the fudge, and it made things worse.
The instrument's own docstring says it "plays the trading game competently and
no better", and competently means not buying trebuchet frames when you have no
trebuchets — so it now researches what improves what it actually does, and
whatever is on the road to that. Two wins in twelve again, from a better
instrument rather than a tuned number.

## The castle

```
castle [town]             the wall as you drew it, and what it is worth
wall [stone|timber] <x,y> [<x,y>]    lay a length of it
tower <x,y>               a tower covers the yards within an arrow of it
gate <x,y>                where the road comes in
moat / pitch / pits <x,y> [<x,y>]    what is dug in front
unwall <x,y> [<x,y>]      take it down; it goes back in hand
```

See [The castle is a shape you drew](#the-castle-is-a-shape-you-drew). In the
browser, **the wall** view draws it with the mouse.

## The accounts

```
economy                   prices, inflation, real output, idle hands
margin [town]             every shed as a firm: hire, or shut it
surplus <good> [town]     what a market is worth, and what a toll costs
advantage <good> [town]   who should be making what
mint [coin]               MV = PY, the hard way
assize <good> <price>     a legal maximum, and what one does
```

The engine underneath was already a supply-and-demand model: a price is a
function of stock, every trade moves the stock, so every trade moves the price
against the trader. What it was missing was the *reading* of that. A merchant
could feel that tolls hurt without ever being shown the triangle, and feel
that prices crept after a debasement without ever seeing an index. Making the
measurement explicit turns a good intuition pump into a thing you can be right
or wrong about on purpose.

Nothing in `economics.py` changes how the game works, with one deliberate
exception — the price level, which is the only honest way for a debasement to
be felt. Everything else measures.

### Opportunity cost and comparative advantage

`advantage wood` asks the question Mankiw opens with, and it is **not** who is
better at it:

```
── WHO SHOULD MAKE WOOD ────────────── what each gives up to make one ──
  Dunmere      buy it there   in coin:      you give up 7.20, they 1.57
  Vantry       make it here   in Wheat:     you give up 2.40, they cannot
```

You give up 7.20c of wheat to cut a load of wood; Dunmere gives up 1.57c of
clay. Dunmere should be cutting the wood even if you are better at it, and the
number that settles it is the thing forgone. Where two places share a good the
reading is the textbook ratio; where they share nothing it falls back to coin,
which is not a dodge — the reason unlike things can be added up at all is that
there are prices.

### The value of the marginal product

`margin` is the hiring decision in one table. It was always the decision
`work <building> first` made you take; the game simply never showed you the
number you were guessing at:

```
── ALDWORTH: THE NEXT HAND ───────────────── a hand costs 2.50c a day ──
   id  shed                staff    made   fetches    eats      net
   43  Weaver's Shop       0/2     2.35   138.45c   12.57c  125.88c  worth hiring
   16  Bakery              2/2     0.59    35.77c   53.78c  -18.01c  shut it
```

Four bakeries running at eighteen coins a hand *in the red* is a thing a
player could stare straight at for three hours before. They are eating flour
worth more than the bread they sell. Hire while the value of the marginal
product beats the wage; close what sits under it.

### Surplus, and what a tax actually costs

`surplus wheat` integrates under the price curve, because the curve *is* an
inverse demand curve:

```
  to the buyers        1,297c   what they would have paid, over what they did
  to the sellers         340c   what they got, over what it cost to make
  to the toll            210c   at 20% on every sale
  to nobody              128c   trades worth making that stopped being made
```

That last line is the only way to see that the revenue is not the cost. It is
not a payment to anybody — it is the trade that did not happen. Double the
toll and it roughly quadruples, which is why the second half of a tax hurts
more than the first.

### The quantity theory of money

`mint 20000` strikes more pennies out of the same silver. You have the coin
today. Prices are bound for `M/M₀` of what they were and get there over a year
or two, which is the entire reason anybody has ever done this — and the town
knows what you did the same afternoon.

### A price ceiling, and what it does to the numbers

`assize bread 2.5` is the most famous experiment in the book, and it behaves:

```
day 501  stock    68   price 2.50   74% short   mood 71.4
day 531  stock     0   price 2.50   95% short   mood 61.9
```

The shelf empties from both ends — everybody wants more of it at that price,
and the back door is open to anyone who will pay what it is really worth. The
town queues, and knows whose proclamation put it there.

Then the part that is worth the whole feature. The price index is built on
what may be *charged*, so:

```
  prices              341   100 is every good at what it is worth
  inflation        -11.4%   a year, from the basket the town actually buys

  assize   Bread held at 2.5c (worth 48.0c) -- 95% short
           The index above is what may be charged, so it does not show this.
```

Measured inflation goes *negative* while the town starves. That is what a
price control does to a price index, and to everyone who reads one.

## Your house

```
kin                       who they are and what it made them
post <name> <post> [where] give one of them a job
marry <name> <town>       a peace that does not run out
```

Bannerlord's real contribution to this genre is not the horses. It is that a
campaign has a *person* in it who changes: you finish a war better at war than
you started it, and when he dies the game does not restart, it continues as
somebody else — somebody you have been training for a decade without
particularly meaning to.

That last clause is the whole design here. A succession that resets the numbers
is a death in a spreadsheet. This one hands the seat to a woman of twenty-two
who has had your carts since she was fifteen, and her trade is four, and you
can see it in the margin the week she takes over.

### A skill is earned by the day, not bought

Nobody spends points. There are five skills, one per post, and whoever holds
the post gets better at *that* and at nothing else:

| post | skill | what it is worth |
|---|---|---|
| `steward` *(a town)* | stewardship | mood there, and what the tax roll bears |
| `factor` | trade | every cart of yours sells a little better |
| `captain` *(a host)* | tactics | that host hits harder and breaks later |
| `master` *(a town)* | engineering | building and walls there, and your siege engines everywhere |
| `envoy` | charm | peace is cheaper and hostility cools faster |

Learning falls off — the fourth level costs more than twice the second — so
level four is a chapter of honest service and level ten is a working lifetime.
The young learn faster and the old slower. The lord is not posted: what he
learns is whatever he is *doing*, so a man who never leaves his hall is a fine
steward and an unproven soldier, and the campaign will say so at the worst
possible moment.

The cost of a post is not coin, it is the person. Everyone can only be in one
place, so a son governing Aldworth is a son not riding with the host, and both
the tax roll and the battle line know it.

### A trait is a verdict, not a choice

Nobody picks "merciful" off a list. You hold the tax light for two years and
the word gets about; you storm a town instead of taking its surrender and that
gets about too. Four of them, each running from one word to its opposite:
**just / grasping**, **merciful / cruel**, **open-handed / close-fisted**,
**bold / cautious**. A day moves any of them about a four-hundredth of the way
to its extreme, which is the point — a reputation you can change in a week is
not a reputation.

They cost and pay. A just lord's towns are happier and his tax roll is thinner.
A cruel one's neighbours stay angry longer. A cautious one is worth more on his
own wall and less at the head of a charge. And his children are born into half
of it, good or bad, because the march gives an heir the benefit of a doubt it
would never have given his father.

### The family

You start with a lord of about thirty-seven, a wife, and three children aged
roughly sixteen, eleven and five — half-grown on purpose, because a campaign is
twelve years and a child born in chapter one would be twelve at the end of it
and have done nothing. Children are born, come of age at fourteen, can be given
a post, and are what a succession draws on.

`marry <name> <town>` is the cheapest lasting peace in the game and the only
one that cannot be un-bought. A truce runs out. A gift is forgotten as the
favour decays. A daughter married into Ostmark is still married into Ostmark in
the fifth chapter. What it costs is a dowry now and a person you might have
posted somewhere.

And the whole house crosses a chapter boundary intact and *older*: the years
between chapters are not a gap it sits out. The son who was sixteen in **A
Small Inheritance** is twenty-six by **Dust on the Road**, carrying ten years of
whatever you had him doing.

### The house rolls its own dice

A birth in the hall must not move the weather. The kin keeps a random stream of
its own, seeded and saved separately, because sharing the world's one re-rolled
twelve seeds' worth of balance measurement the first time this was wired in —
without changing a single rule. That is the kind of bug that looks exactly like
a balance change, and there is a test that asserts it cannot come back.

It has now been written three times in this codebase — the kin, the league, and
the town's own voices — so it is a rule rather than an anecdote: **a subsystem
that draws gets a stream of its own, without exception.** The third one was the
worst of the three. A peasant's line is pure flavour, and drawn from the world's
stream it would not have been: a browser polling the street once a second would
have re-rolled the campaign between page paints. What the street says is seeded
on the day and the place instead, so it is the same street while you are looking
at it and a different one tomorrow, and it costs the game nothing.

## How it looks

### In a browser

```bash
python3 -m marchlands --web
```

The town, drawn. Timber frames and daub, thatch on the poor roofs and tile on
the comfortable ones, a stone curtain with merlons along it, water in the
ditch, mill sails turning, smoke from the ovens that are lit, windows glowing
where somebody is working, people on the road, and snow in winter with the
trees gone bare.

#### Five idioms

Age of Empires II is remembered for a lot of things, and one of them is that
you can tell whose town you are looking at from the roofline. Not from a banner
— from the fact that a Frankish castle and a Japanese one are different
objects.

This game had one idiom. Every settlement anybody founded, on chalk or granite,
in the fen or on the border, came out as timber frame and thatch. There are
five now, and a culture belongs to **the ground rather than the player** — so
one game has several skylines in it rather than one.

| | walls | roofs | silhouette |
|---|---|---|---|
| **the March** | timber frame, jettied | steep thatch | deep eaves, an upper floor that oversails |
| **the Hansa** | brick | tile | crow-stepped gables, tall and narrow |
| **the Abbey** | ashlar | slate | steep, pale, spires |
| **the Vale** | cob and lime | thatch | long low **hipped** roofs — four slopes, no gable |
| **the Ironhand** | drystone | slate | squat and heavy |

And you can see somebody else's. Clicking a town on the march map draws its
roofline in **its** idiom — four roofs of Havnhold's brick under crow-stepped
gables, or Ostmark's squat drystone under slate. Until that existed, a lord's
idiom was a word on the war screen and nothing you ever actually saw, which is
not what Age of Empires does at all: the whole payoff of five architecture sets
is recognising a place from its roofs.

Three rules kept it from being a reskin. **It is the same building** — a Hansa
granary holds what a March granary holds, and a bonus attached to a roof shape
would be a bonus pretending to be a culture. **It is legible from the picture
alone** — four channels (wall material, roof material, roof *form*, palette),
because any one of them on its own is a colour swap. **It is the ground's** —
a coast builds like a port, a hill builds in stone, chalk builds low, and
taking a town does not re-roof it.

With one exception: a house's *opening* hold is raised by masons who travelled
with it. That has to be checked before the ground or it is not an exception at
all — testing terrain first opened all five houses on the same chalk in the
same idiom, which is the one outcome that makes the whole feature pointless.

#### One figure stands for fourteen people

The tension every builder game has and most resolve by lying: the simulation
runs on aggregates — a population is a float, a garrison is a dictionary of
counts — and the picture draws people. One figure per soul is an unreadable
crowd and a dead framerate. A decorative handful of dots on a road is a picture
telling you something that is not true.

So a figure is a **sample, at a ratio the interface states out loud**, doing
something the aggregate is really doing:

```
one figure = 14 souls · 12 on the wall (6 men each)
```

A worker walks the route between the roof he sleeps under and the shed that is
staffed today. Somebody with no work stands in the street — shut every shed and
the whole town is in the square, with nobody drawing that as a special case.
And the watch stands on the yards of wall that are **really being held**, drawn
along [the castle you drew](#the-castle-is-a-shape-you-drew), so a wall you
enclosed more ground with than you have men for *looks* thinly held. No
warning, no icon, no number: you can see the gaps.

The share of figures going somewhere is the share of the **workforce** with a
job, not of the population — most of a town is children and the old, and
dividing by the whole of it put two people on the road in a town with every
shed running.

##### And you can click one

The obvious objection to a 14:1 ratio is that it puts a wall between you and
the town: a crowd is not people. So clicking a figure answers, and every line
of the answer is read off the town rather than invented — because a worker
already knew the roof he sleeps under and the shed he walks to. That is how
his path was drawn. It was simply being thrown away.

    the Aldreds                   one figure · 14 souls
    walking between their roof and Windmill
      sleeps at                              Cottage Row
      works at                                  Windmill
      makes                                        flour
      eating                 1 rations, 2 kinds of food
      paying                                     tax 2
    A widow from the row: "My wages have not moved and everything
    else has. You may call that what you like; I call it a pay cut."

The scale is stated rather than hidden, because pretending a figure is one
villager in order to make it feel like *Age of Empires* would be the lie. Two
figures out of the same door get the same family name — a household is a
household. Click a spearman and you are told how many yards of wall there
are and how many men are standing them, which is the same readout the wall
already was, asked from the other end.

The few figures that *are* one person are your own. A posted officer stands
at the building their post attaches to, marked in the house's gold, and
clicking them gives their age, what they are good at, what the post is worth
and a row of buttons to move them — which sends the same `post` command a
person would have typed, target and all. The envoy is not drawn, because
"sits with the other lords" means he is somewhere else.

#### The materials

Every surface used to be a flat polygon with a few ruled lines on it: thatch
was five arcs, a tiled roof was four straight strokes, a stone wall was a grid
at six-pixel intervals. What makes a painted surface read as a material is not
the lines on it — it is that no two square inches of it are the same.

* **Thatch** is thirteen courses, each lighter at its head and shadowed where
  the next laps over it, combed with stalks down the fall of the roof, a bound
  ridge at the top and the shadow the overhang throws on itself.
* **Tiles** are objects rather than stripes: sixty-three separately fired
  things, offset half a tile every other course, each a slightly different
  colour, with moss gathering at the eave where the roof stays wet longest.
* **Stone** is rubble, not graph paper — courses of uneven height, blocks of
  uneven width within them, each block its own shade, and damp at the foot of
  the wall where a stone wall is always darkest.
* **Timber** is a real frame: sill, top plate, studs and a brace every third
  bay, with lime daub panels between them.
* **The ground** is two scales of variation, and the second one is the whole
  trick. Per-tile noise alone paints a *checkerboard* — every diamond a
  different shade with a hard seam at its edge, which is exactly what the eye
  is best at finding. A broad smooth swell laid over the top gives sunlit and
  shaded ground that crosses tile boundaries, and the per-tile part can then be
  small enough to read as texture. On top of that: crop rows that stand taller
  in summer than in spring, cart ruts and gravel on the roads, tufts and bare
  patches and the odd ploughed-up stone in the meadow, and flowers in season.
* And a **grain** over all of it, baked once into a tiling bitmap and used as a
  fill pattern, because canvas cannot do per-pixel noise at thirty frames a
  second but it can composite one small texture a hundred times.

All of which is **free**, which is the part worth recording. Measured before
and after on the same machine: 24 fps before the materials pass, 23–25 after.
It is paid for by three things the renderer should have been doing anyway —
the static ground is baked into a bitmap once and blitted (9.6ms → 0.1ms a
frame), every water tile is clipped in one path instead of ninety (a third of
the frame budget was going on the cheapest-looking thing on the screen), and
buildings off the side of the screen are not drawn at all. Detail drops to
courses rather than individual tiles below about three-quarter zoom, which is
not a compromise: a roof drawn with sixty-three tiles at a zoom where each is
a pixel and a half looks *worse* than one drawn with seven courses, as well as
costing more.

### The hour of the day

A day passes in the simulation when you ask for one; the light does not wait to
be asked. It turns on its own -- one full round of dawn, noon, dusk and night
every two minutes or so -- and every simulated day gives it one more round to
make, so **`a week` wheels the sun round seven times** and you watch the week go
by. It is the cheapest way there is to make a button feel like it did
something.

Out of one number -- where the sun is -- comes everything else. The sky is
three stops rather than two, because the band of warm light along the horizon
at either end of a day is the whole difference between a time of day and a
brightness setting. Stars come out in a fixed field, which is the only thing
stars ever do. The moon rides the other half of the same wheel.

**Shadows are geometry, not light**, so they are drawn with the thing that
casts them: long and sideways at either end of the day, short and underfoot at
noon, gone at night. A long shadow is not a faint one — fading them out at dusk
loses the hour entirely.

**The light itself is one pass over the top of everything solid.** Doing it
that way rather than tinting every fill is not a shortcut: it is the only way
the hundred-odd colours in that file can stay readable as colours — thatch is
`#b8994f` whatever the hour — while all obeying one sun. Noon is white and does
nothing. A low sun takes the blue out first, which is why evening is warm;
night takes the red out, which is why it is not.

Then the things that make their own light are drawn *after* the dark, which is
exactly what makes a lit window worth having. At midnight the town is a
constellation of small warm windows, and you can see which sheds are running.

**Water** is three crossing waves at different speeds, so the surface never
repeats on any count a player could hold, plus the sun's own road across it —
which only exists when the sun is low, and turns cold and narrow when the moon
has it instead.

Everything is a vector path. There are no images in this repository and there
is still no dependency list — the thatch is a row of arcs, the stone is a
clipped brick pattern, the smoke is forty particles with a lifetime. The rule
that this game installs with nothing was worth more than a texture atlas.

The server is `http.server` from the standard library, and the browser is a
view with a command line in it: every command the console takes works there,
because it is the same `Console` underneath. Drag to move, scroll to zoom,
hover a roof to ask what it is.

Where a building actually stands is decided in Python (`layout.py`), not in
the drawing code, for one reason: layout is a decision and decisions should be
testable. The renderer's only job is to make it look like somewhere.

**`the march`** switches to the other half, and the half that is actually the
point. A town is a picture of what you have; the march is a picture of what
things are worth *somewhere else*, which is the only reason any of the carts
move. On parchment rather than grass, because a map is a different kind of
seeing from a view:

* every market ringed by what it pays for one good, which you choose — green
  where it is cheap, red where it is dear, scaled to the median so one crashed
  market does not recolour the whole march
* your carts where they have actually got to this morning, with what is in
  them, crawling along their legs in real time; cogs drawn as cogs
* the best runs the scanner found, drawn as arcs between the two places they
  join, the best one labelled with its coin per day and what it carries
* the fog on it: a town you have never sent a cart to is labelled *never
  visited* rather than given a number it has not earned

#### Fit and finish

The parts nobody names when they work:

* **Names are cut out of the map.** Every place name, price and cart load is
  drawn with a parchment halo, so a road or a route arc passes behind the
  lettering instead of through it.
* **A panel that has more in it says so.** The side panel darkens along its
  bottom edge when the list continues below the fold; a list that simply stops
  looks like the whole list.
* **It fits a phone.** Under 720px the panel lies down along the bottom as a
  strip of the four numbers the game is played on — souls, mood, hands, wall —
  rather than hiding itself, and the town is re-fitted to the different shape
  of room that leaves. Cross the breakpoint and it re-frames.
* **Asked to hold still, it holds still.** With `prefers-reduced-motion`, smoke
  does not rise, sails do not turn and nobody walks; the picture still redraws
  when the day does.
* **The page asks the network for nothing.** No font host, no CDN, no favicon
  file — the tab's mark is a drawn `data:` URI. A test asserts it, because the
  easiest way to acquire a dependency is to add one link to an HTML head.

### Finding out what you can do

```
⌘K / ctrl-K      every command, searchable
space W M        a day, a week, a month
T / R            the town / the march
H                what now?      /  type a command      ?  the keys
```

A command line is the fastest interface there is for somebody who knows the
commands and the worst for somebody who does not. The palette is the bridge:
all seventy, searchable by subsequence (`mkt` finds `market`), each with the
one line its own docstring gives it — **fetched from the console's own
registry**, so it cannot drift from what the game will actually accept and a
renamed command cannot go on being offered under the old name. A test asserts
that every command says something about itself, because one that does not is
one nobody will ever find.

The blurbs are searched by whole word only. A loose subsequence over a
sentence matches nearly everything — `mar` found *"Open a saved game, and
survive it not being one"* — which is the fastest way to make a palette
useless while looking like it works.

Unmodified keys fire only when the cursor is not in a text field, which is the
one rule that lets a game with a command prompt in it also have shortcuts.

Three smaller things that are only noticeable when they are missing: a number
that **moved** says so for a second and then stops, because a panel where
everything is always highlighted highlights nothing; anything the chronicle
thought was **momentous** — a birth, a death, an age beginning — gets a toast,
because the console keeps everything and you would still have scrolled past
it; and clicking a roof now tells you **what the next hand in it is worth
against the wage**, which is the one number that decides whether the shed
should be open, attached to the shed.

### The thing people actually describe

Ask anybody what they remember about Stronghold and they will not start with
the popularity dial. They will tell you about the sound, and about watching
the little men carry wheat to the mill and flour to the bakery.

**Carriers.** A load exists only where something running wants what something
running makes — the hauls are read straight off the production graph — so what
you watch crossing the street is what the ledger is doing. The sack is the
colour of what is in it: flour pale, charcoal near-black, cloth dyed. They
walk the lanes rather than the straight line, because a carrier who takes the
short way spends the trip inside other people's roofs, where you cannot see
him and he has no business being.

**Sound.** There are no audio files here for the same reason there are no
images: every layer is synthesised. The wind is filtered noise and it opens up
in winter. The crowd is noise with a formant on it, and it sits brighter when
the town is content and duller when it is not. A hammer is a click envelope,
and there is one for every few workshops actually running. Birds, but not in
winter. A crackle for each roof alight, a drum under a siege, and a bell for an
age beginning or a game ending. Press **sound**; browsers will not make a noise
until you have clicked something.

Both follow the state, which is the whole discipline of this renderer: a town
that is working sounds busy, a town in winter sounds bare, and neither the
picture nor the noise can flatter a town that is starving.

### Clicking things

The browser was a picture with a command line taped under it. Now the picture
is the interface: click a roof and you get what can be done to *that* — close
it, pull it down, move it up or down the queue for hands. Click an empty plot
and you get what can be raised on it, priced, with the reason beside anything
you cannot have yet. Click a town on the march and you get its price, what you
know of its strength, and a cart to put on the road.

One rule holds the whole thing together: **nothing in the page knows a rule.**
Every button composes the same line a person would have typed — `build hovel`,
`close 14`, `work bakery first`, `auto 2` — and posts it. The page asks the
engine what is possible and draws the answer; it never decides. There is
exactly one place the rules live and it is not in JavaScript.

That distinction caught a real bug the moment it was clicked. A town labelled
*never visited* was quoting a bread price in the same breath, which reads as a
contradiction — until you notice the game has always been right about this and
the wording was wrong. Prices travel: merchants talk, and `prices` has listed
every market since the first week. What does not travel is how many men are
behind a wall. The map now says each in its own words, and draws a hearsay
price as a dashed ring.

Which is the whole thesis of the game in one picture: bread at 3.8c in Bruille
and 16.4c in Ostmark, four days apart, and a cart of yours already on the road
between them.

### In a terminal

The terminal is still the game's native habitat, and it has the thing
Stronghold was actually selling: a place you can look at, from the corner, and
tell how it is doing.

`view` draws the holding in perspective, painted back to front, from the state
itself:

```
── ALDWORTH ──────────────────────────────────────────── autumn, 1247 ──
·                            ·                            ·           ☁
                       ·                            ·
                              ♣♣
                              ┃┃ ♣♣
                           ≋≋    ┃┃  ▲
                     ♠♠ ≋≋    ≋≋    ▀▄≈
                  ♠♠ ┃┃    ≋≋    ≋≋≈▄▀▄▀▀≈◣◢
                  ┃┃    ≋≋    ᵕᵕ≈██ █████ ██≈◣◢
                      ˛˛   ▀▀≈██ ▛▜ █████ ██ ██≈
                    ˛   ▀▀≈██ ██ ██ ███▟▙ ██ ██ ▀▀≈
          ˛          ▀▀≈██ ██ ▟▙ ██ ▟▙ ██ ▟▙ ██ ██ ▀▀≈
              ˛   ▀▀≈██ ██ ▟▙ ▛▜ ▟▙ ██ ▟▙ ██ ▬▬ ██ ██ ▀▀≈
   ◡◡          ≈≈≈██ ██ ▬▬ █° ██ █˙ ▟▙ █° ▄▄ ▒˙ ▄▄ ██·██ ≈≈≈
˛           ≈≈≈▀▀ █Î ▬▬ ▒▒ ▄▄ █˚ ▄▄ ∪✻ ▄▄ §✻ ▄▄ ¤✻ ▄▄ ██ ▀▀ ≈≈≈
         ≈≈≈   ██ ▀▀ ▒▒ ▄▄ ▓✻ ▄▄ ▓▓ ██ ▓▓ ██ ▓▓ ██ ▓▓ ▀▀ ██    ≈≈≈
      ˛     ≈≈≈   ██ ▀▀ ▓Î ██ ▓▓ ▄▄ ██ ▄▄ ██ ▄▄ ██ ▀▀ ██    ≈≈≈
               ≈≈≈   ██ ▀▀ ██ ▄▄ ▓▓    ▓▓    ▓▓ ▀▀ ██    ≈≈≈
             ˛    ≈≈≈   ██·▀▀ ▓Î    î       ì▀▀ ██    ≈≈≈
                     ≈≈≈   ██ ▀▀  î     ï ▀▀ ██    ≈≈≈           ˛
                    ˛   ≈≈≈   ██ ▀▀ í  ▀▀ ██    ≈≈≈
                           ≈≈≈   ██ ▀▀ ██    ≈≈≈          ˛
                              ≈≈≈   ██    ≈≈≈   ˛       ˛
                           ˛     ≈≈≈   ≈≈≈         ˛ ˛
                                    ≈≈≈
                                  ˛
                                          ˛

  souls      190 of 197 roofs     mood ██████████····  72     normal rations
  wall    ██████████████ 1,944/1,944  garrison 27 Archers, 44 Spearmen
  standing 7x Cottage Row · 6x Wheat Farm · 4x Bakery · 4x Windmill · 2x Granary · 2x Orchard · 2x Poleturner   (20 idle)
```

That is a real render, not a mock-up -- seed 7, two hundred and twenty days
in. The keep stands over the curtain wall, the near walls are drawn low so you
can see into your own town, the moat (`≈`) runs round the outside of them,
windmills rise above the workshops, and there are people (`î`) in the streets
when there are people. Ovens that are lit put up
smoke; the mill's sails turn a frame a day. Dwellings have pitched roofs,
workshops have shallow ones, stores are flat, civic halls are two storeys --
so the skyline tells you what kind of town you have built before you read a
word of it.

**`watch [days]`** lets the days run and redraws in place, which is as close as
a console gets to the thing you actually miss: seeing the place move.

Colour carries the rest, where the terminal has it: a workshop burns bright
while it is running, dims when it is short of hands or inputs, and goes out
when you close it; the wall turns amber under siege and red when it is going;
the ground and the trees change with the season; prices read green when cheap
and red when dear; the ledger is green above the line and red below. `view
flat` gives the same holding as a plan, which is easier to count and harder to
love. Piped to a file or a test it all comes out as plain text.

## The three systems

**Land → labour.** Fixed slots of fertile, forest, hill, clay and coastal
ground, plus town plots and a separate castle perimeter. A quarry needs hills; a
farm needs fields; a harbour needs a shore. No site has enough of everything, so
no site closes every chain alone. Quarries and mines work a *seam*: the hill
holds a finite amount, and when it is gone the sheds stand idle for good.

Labour is the tighter constraint of the two, and permanently. A settled town
runs something like forty-four hands against seventy jobs, so a third of what
you have built is standing idle on any given morning and the question is never
*whether* something goes short but *what*. `work` shows the queue and
`work <building> first` reorders it. This is the lever Age of Empires built its
whole skill curve on, and it is the reason an inn with no hand in it cheers
nobody however much ale you bought.

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
through bows. None of it matters while a wall is standing — which is what a
castle is for.

### The castle is a place, not a number

A wall in most games is a pool of hit points: buy more and the siege takes
longer. Here a castle is a set of **answers**, and a besieger has to pick which
of them he is going to walk into.

| plan | what it needs | what beats it |
|---|---|---|
| **batter** the gate | rams (20 engine power) | boiling oil over the gatehouse |
| **breach** the curtain | real engines (55) | towers shooting back at the crews |
| **escalade** the wall | nothing at all | towers, a pitch ditch, a manned wall |
| **sap** the foundation | engineers | water in a moat — stops it outright |
| **invest** and starve | nothing at all | a full granary and a gate to sortie from |

Each works differently rather than just scoring differently. A **moat** costs a
host three days under fire before it can come to grips, and a miner who strikes
water is simply finished. A **pitch ditch** is fired once, at the moment the
assault goes in, and it is spent. An **oil pot** punishes the gate every day and
does nothing at all against a man standing off at bowshot. **Ladders** need no
engines, which is the only kind thing about them: they are worse against an
intact wall, worse again with towers on it — but against a wall-walk you have
*emptied*, they take the place today while engines would still be breaking
stone. And **investing** touches nothing: it cuts the roads, which in a game
about trade is the sharpest thing anyone can do to you.

The defender's half of that is a real decision because the wall line is finite.
Works stand on it alongside the walls themselves, so every ditch you dig is a
tower you did not build. `plans <place>` reads any castle — yours or a rival's —
and names what each way in would meet there. `siege <host> <plan>` sets how your
own host goes in; changing your mind restarts the work, so a mine half-dug is a
mine wasted.

Rival lords read your castle the same way, and pick accordingly: bring nothing
that breaks stone and a captain will sit down and starve you instead. Their own
seats are graded by how rich and old they are — a market town like Dunmere has
an open wall, while Marchand has a moat, three towers, pits, a pitch ditch and
oil over the gate, and will force you onto the one expensive answer it has no
reply to.

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

One consequence worth knowing before you economise on soldiers: a holding with
no garrison at all now dies inside a couple of years without anybody needing to
storm it. Raiders burn the country, the country is what feeds the town, and a
town that cannot feed itself empties. There is a test for exactly that, and
another test had to start propping the player up once it became true.

Being stormed is a catastrophe, not a trapdoor: the keep is thrown down, the town
gutted, and you carry on from whatever else you hold — which is the best argument
there is for founding a second settlement before you need one.

### Raiding, relics and the lord

`raid <host>` looses a host on the country instead of the walls. Horsemen burn
more of it in a day than footmen, a big country takes longer to ruin than a
small one, and a garrison that is clearly the stronger will come out and catch
them at it — which is exactly what a raider wants if he is stronger still.
Against a rival it costs him prosperity, which is the number his walls, his
garrison and his muster are all computed from; against you it stops the fields
being worked at all.

One thing worth knowing about how that was built: a lord's relic party is
explicitly *not* his host. It was, at first, and because the war logic skips a
lord who already has men in the field, how often the lords went relic-hunting
quietly set how often they declared war on anybody — tuning the shrines
retuned the whole map. Parties now carry an errand and the war logic ignores
them.

`relics` lists the five shrines. A host that stands at one for six days lifts
what is in it and carries it home, where the offerings come to about 42c a day
— half again with a cathedral to rest them in. Hold four of them for a hundred
and twenty days and you have won the march that way. The other lords send
parties too, two parties at one shrine settle it the usual way, and taking a
lord's town takes whatever he had lifted along with it.

`lord` says where yours is. In his hall he is worth mood and nine points of
defence on the wall; riding with a host he is worth sixteen percent of its
strength, and he is where the arrows are. If that host breaks he may fall, in
which case the whole holding mourns and the hall stands empty until an heir is
raised — or he may be taken alive, and then somebody names a price.

### Fire

Timber and thatch burn, and a town is mostly timber and thatch. Ovens, kilns
and charcoal heaps start fires by themselves now and then; raiders carry
torches on purpose; men who get over a wall set light to what is behind it
whether or not they end up holding the ground.

Three rules do all the work. What is made of wood catches and what is made of
stone mostly does not. A fire reaches for one roof at a time, not for the whole
town — spread that rolls every blaze against every building is quadratic, and a
quadratic fire has exactly two outcomes with nothing in between worth playing.
And the only thing that puts it out is hands, which is the one thing the town
never has enough of.

That last rule is where the cost lands. Everybody runs at a fire, not just the
payroll, so the *water* scales with the town; but the hands that carry it are
hands not working, so the *bill* is a bite out of the day. A building you save
still wants days of work afterwards — a fire has taken hold before anyone
reaches it, so nothing is free. Summer is the dangerous season and winter the
forgiving one.

Past the point where a town can mobilise about half of itself the fire is
simply winning, so eight roofs alight is an expensive afternoon and eighteen is
the end of the town.

### The friars

The Preaching Orders, in the third age, unlock a unit whose attack is that the
enemy stops being the enemy. Friars with a besieging host talk men off the wall
and onto your side, a few a day, never more than a small share of a garrison at
once — and the answer is the one the period actually used: a man with a church
of his own is much harder to preach at. A defender's *faith coverage*, the same
number his chapels and his cathedral set, is what blunts it. A great seat with a
minster is deaf to preaching; a market town is not.

They count as siege for the purpose of the counter triangle, which means
cavalry ride them down. That is deliberate, and it is what Age of Empires did.

### What you know

You do not see the march. You see what you last looked at.

Your carts are your intelligence service, which is the right answer for this
game in particular: a lord you have never sent a cart to is a lord you are
guessing about, and `war` will say so rather than invent a number. A town you
traded with this morning is current. A town you passed through two seasons ago
is a report with a date on it, and the report is always *optimistic*, because
lords grow while you are not watching.

`plans <town>` refuses a castle you have never had eyes on, and warns you when
what it is describing is a season out of date — he has had time to dig.

## Scenarios

Five games on the same rules. `--list` describes them; the first four are meant
to be played in this order.

| scenario | length | what it is |
|---|---|---|
| **The Salt Road** | 2 years | A coastal seat with a quay, quiet lords and no conquest on the table. The trade game with the training wheels of geography: you start where the sea is. |
| **The Marchlands** | 3 years | The full game. One inland hill, seven towns, all three ways to win. |
| **The Iron Marches** | 3 years | Ore under you and nothing that grows. Every lord already dislikes you. Wealth or dominion, no cathedral. |
| **The Winter Crown** | 2½ years | Midwinter, a month of bread, a short rope and angry neighbours. The hard one. |
| **Freebuild** | no clock | A hill, a long purse and nobody coming. Every other system still running. See [Freebuild](#freebuild). |

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
| `render.py` | ink: palette, framing, bars, sparklines, colour discipline |
| `iso.py` | the holding in perspective: tiles, sprites, smoke, people |
| `view.py` | the same holding as a flat plan |
| `castle.py` | works, assault plans, and what answers what |
| `keep.py` | the castle as a drawing: enclosure, tower cover, the weak side, depth |
| `culture.py` | five architecture sets, and which ground builds in which |
| `cartography.py` | country drawn from dials, and six real places characterised as dials |
| `lord.py` | your lord: what he is worth, and what can happen to him |
| `lords.py` | the rival lords as six sorts of person, and what each of them says |
| `voices.py` | what the town would say, if you asked it |
| `kin.py` | the house: skills earned in the job, traits earned by choice, births, marriages, succession |
| `league.py` | the march as a competition: table, schedule, draft, and the cap |
| `chancery.py` | the diplomatic web: dated opinion, coalitions, grounds for war, alliances |
| `economics.py` | the accounts: price index, surplus and deadweight loss, comparative advantage, the marginal product, the mint |
| `fire.py` | what catches, how it spreads, and what puts it out |
| `layout.py` | where everything stands, so a renderer can draw a place |
| `web.py` | a stdlib server and the browser's view of the game |
| `static/` | the canvas renderer: every roof a vector path, every sound an oscillator |
| `campaign.py` | six chapters, what crosses between them, the Count |
| `chronicle.py` | what happened, written down as it happened |
| `cli.py` | the terminal interface |
| `sim.py` | two headless bots (trader, conqueror), used as balance tests |
| `config.py` | every tunable number in the game |

## What people actually say they love

A pass that started by reading what players of these three games bring up
unprompted, twenty years on, rather than what a design document would list.
Three things came back over and over, and we had none of them.

### The lords are people you learn

Ask anybody what they remember about Stronghold and you will not get the
popularity dial. You get **the Rat, the Snake, the Wolf and the Pig** —
characters people still have favourites among after twenty-four years, who are
remembered because each one *plays differently and says so out loud*.

This game had eight lords with excellent names and no character whatever.
`Reeve Halden` and `Abbot Gervase` behaved identically — same aggression, same
ambition, differing only in how much wall the map handed them.

Six sorts now, and the sort is a real difference rather than a label:

| | how he plays |
|---|---|
| **the Boar** | arms first and thinks afterwards; comes early and comes often |
| **the Heron** | builds wall and stands behind it; will not come unless you make him |
| **the Fox** | burns your fields rather than face your wall, and treats when losing |
| **the Ox** | slow, steady and hard to shift; what he takes he keeps |
| **the Magpie** | would always rather pay than fight, and grows fat doing it |
| **the Wolf** | good at everything and in no hurry; the one you plan around |

These are multipliers on the war engine's own dials, so the behaviour is real
rather than described: a Boar's ambition builds three times faster than a
Heron's, a Magpie prices a truce at two fifths of what the Wolf asks, and the
Fox's captains go for the harvest at a strength where anybody else would try
the wall.

And they talk. You learn a lord by being insulted by him:

> **Reeve Halden:** *"I am coming. Do not trouble to write back."*
> **the Lady of Caer Ithel:** *"A misunderstanding. Let us call it that."*
> **the Margrave Ekhart:** *"Held. That is the whole of it."*
> **the Count of Marchand:** *"As expected."*

What sort a lord is has to be found out — `war` names it only for places one of
your carts has actually called at. Character is intelligence, and intelligence
is the thing the trade layer buys.

The bug worth recording: the scenario used to roll aggression and temper
*straight over the top* of whatever the lord was, so the Heron and the Boar
came out the same man with different names. The band is the decade; his nature
multiplies it.

### The town talks back

The single most quoted thing about Stronghold is not a mechanic. It is a
peasant saying **"Double rations? Oh, thank you, Sire!"** when you move the
ration dial, and **"No taxes is good taxes, that's my motto!"** when you move
the other one. People who have not played it in twenty years still quote those
lines, and when a sequel dropped the voices the complaint was that the game had
gone *"more bland"* — which is a complaint about **information**, not charm. A
dial that answers you is a dial you understand.

We had a mood breakdown that was perfectly honest and entirely inhuman:
`taxes -3.5, crowding -2.6, ale +11`. Same information. Not the same thing at
all, because a number cannot be indignant.

```
── IN THE STREET AT ALDWORTH ──────────────────────────────── mood 62 ──
  A thatcher
    “Double rations, my lord! God bless you, and my wife says the same.”
  A woman at the well
    “No taxes is good taxes. That has always been my motto and I have
     never had cause to change it.”
```

Twenty-three voices, every one keyed to something actually true today — what
they are eating, what you are taking, whether they were paid on Friday, whether
there is a queue at the bakery, whether the pennies have got lighter. They are
weighted, so **the loudest thing in the town is the thing you hear about**: a
town with a host at the gate does not want to talk about the beer. Which makes
`ask` a diagnostic that happens to have a person in it. Click a cottage in the
browser and you get the same.

### Freebuild

Named in every retrospective anybody writes: *"construct the ultimate castle
without fear of attack"*, *"at your own pace without combat pressure"*. The
reason is not that people dislike the war — it is that **the building is the
thing they came for**, and a mode that lets them do only that is a mode they
play for a hundred hours.

```bash
python3 -m marchlands --scenario freebuild
```

A hill, a long purse and nobody coming. Nothing is counting. And it is not a
sandbox with the rules switched off: the market still prices by scarcity, the
labour still runs out, the mood still answers to bread and taxes, the house
still ages and inherits, and the other lords still quarrel among themselves —
merchants, not pacifists. A dead march is not a peaceful one, it is a diorama.

### The castle is a shape you drew

This was top of the "what we still do not have" list, and it was the right
thing to be top of it. *"The satisfaction of seeing your vision come to life
is unparalleled"* is the single most-repeated sentence anybody writes about
Stronghold, and it is never about the popularity dial.

We had the **works** — moat, pitch ditch, killing pits, towers — and they
really are the right abstraction of what a castle does to a besieger. They
were also completely invisible. You bought `stone_wall` and a square appeared
around whatever the town happened to be; buying a second one changed the
picture not at all. Nobody has ever posted a screenshot of an abstraction.

So the wall is a drawing now.

```
     78901234567890123
   8         x
   9         vx
  10        vvv
  11       vvvvv
  12      T######
  13      #oo.oo# x
  14   x v#oo.oo#vxx
  15  xxvv#.....#vxxx
  16   x  #oo.oo# x
  17      #oo.oo#
  18      ###G##T

  the wall          24 yards -- 21 stone, 2 tower(s), 1 gatehouse
  it shuts in       25 plots
  towers cover      14 of 24 yards
  the weak side     5 yards on the south-west with nothing looking down at them
  men to the yard   3.1 -- held
  outside it        15 building(s) nobody is defending: Windmill, Bakery ...
```

`wall 12,12 18,12` runs a length along the north side; `tower`, `gate`, `moat`,
`pitch`, `pits` and `unwall` do the rest. In the browser there is a **the wall**
view where you drag along the ground and the run goes where you dragged it —
and the yards no tower covers are painted red on your own castle, so the hole
in it is something you can see rather than a line in a report.

**The economy is untouched.** The same buildings at the same prices buying the
same effects: what changed is that one `stone_wall` is now 28 yards of stone
*to lay* rather than a ring that appears, and where you lay it decides four
things the siege actually reads.

| | what the shape buys |
|---|---|
| **what is inside** | The town fills the ground you enclosed. What does not fit stands outside — and outside is where the man with the torch already is. |
| **how long it is** | A garrison is men and a wall is yards, so what matters is men *to the yard*. Enclosing the valley is how you end up with a wall nobody is standing on. |
| **what the towers see** | A tower covers the wall within an arrow of it. A besieger does not average your towers: he walks round until he finds the longest run none of them cover, and that is where the ladders go. |
| **how many times** | A second ring inside the first is a second siege. It adds no stone; it adds a yard they have to cross with a wall shooting into it. |

None of it is scored. There is no castle rating and no stars for owning a moat.
It is read off the drawing by flood fill and arithmetic, because a castle
should be good on account of where its towers are and not because a rubric said
so. `shut` is a flood fill from the edge of the map; the weak side is the
longest run of wall outside every tower's reach; depth is a 0-1 breadth-first
walk inwards that adds one every time the path has to pass through stone.

And nobody has to draw anything. A player who never types `wall` gets the
square his steward would have laid — sized to the wall he has bought and the
town that has to fit in it, stone where there is stone, towers on the corners,
gate on the road. That is exactly the ring this game drew before, so a game
that never touches the new commands plays as it always did. The first yard you
lay yourself starts from his ring, and takes the pen off him for good.

Three things had to be right or the whole feature would have been a tax:

* **The steward's ring must never leave the town in the field.** It is sized by
  *usable plots* — the interior minus the streets minus the keep — rather than
  by the raw interior, which is how a town with thirty-six workshops first came
  out with twelve of them standing outside their own gate.
* **A drawing you pull down stays yours.** An emptied castle is a decision, and
  handing the pen back to the steward at that moment would have had him
  cheerfully redraw the square you had just spent an evening replacing.
* **The budget rule must never punch a hole in the ring.** Drawing more than
  you have paid for pulls the excess back down — but a tower you cannot afford
  is still a yard of wall somebody built, so it is *demoted* to the stone under
  it, and unpaid stone to timber, and only what has nothing to fall back on
  comes down at all. Removing it outright turned a concentric castle of seventy
  enclosed plots into sixteen, silently, because two towers were over.

The steward points at all of this. A hole in your own ring with a host on the
road is the most urgent sentence in the game at that moment, so it is *ranked*
into `hint` rather than appended to it — which is how the first version of it
fell off the bottom of a list capped at four.

## The march is a web, not eight quarrels

What people mean when they say they like Europa Universalis’ politics is
rarely the peace screen. It is four things, and none of them is a war.

This game had one number per lord called `hostility`, which went up on a timer
and down when you paid. Everything below is built on top of that rather than in
place of it: the timer is still the timer. What changed is that the number now
has **reasons** attached, that the reasons are visible and dated, and that they
add up *across the march* instead of only ever pointing at you one lord at a
time.

### You can see why somebody hates you

```
── THE COURT ────────────────────────────────── 6 names on the letter ──
  Dunmere        -12  cool        signed
      you took a town on this march                 -21  242 days left
      you have beaten their host, and they know it  +14  400 days left
  Havnhold       +19  warm
      you marched with no reason anybody accepted   -10  265 days left
      your houses are married                       +70  forever
```

Every reason is a dated row that decays at its own rate, and the rate is the
design. Taking a town is about four hundred days of ill-will at the
neighbours. An unjust war is rather more, because it is about your character
and not your appetite. A siege the march thought was fair is forgotten inside
a season. *"He is hostile"* is flavour; *"he is hostile because of the town you
took eighty days ago, and it has two hundred and forty days left to run"* is a
plan.

Two distinctions carry most of the weight:

* **Dislike is not offence.** A lord who resents being shaken down for tribute
  resents you. A lord who has watched you take three towns has a reason to
  write to his neighbours. Only the second kind signs anything.
* **Awe is not affection.** Breaking a lord’s host is a reason he will not put
  his name to a letter with you on it. It is not a reason he warms to you: he
  will not ally, and his temper does not cool. Letting the two share a number
  made a man you had beaten twice read as a friend.

### Conquest is self-limiting

```
  THE LETTER AGAINST YOU
  Bruille, Caer Ithel, Caldmoor, Marchand, Ostmark, Vantry have signed.
  None of them will take a truce alone.
  it lapses under 45 each:  Caldmoor 58, Ostmark 64, Bruille 46, ...
  three ways out:  beat their hosts (each broken host is worth 22),
                   wait, or `court buy` at 7,399c
```

The signature mechanic, and the one this game most needed: conquest that is
cheap once, dear twice and ruinous three times — not because any lord got
stronger, but because they started counting together. A signatory **will not
take a truce alone**, which is precisely what they signed it to stop you doing.

It is a genuine arc rather than a wall. Measured on one run of the conquering
bot: the letter forms on day 498 with seven names, lapses on day 706 after he
breaks two of their hosts and stops expanding, and re-forms on day 951 when he
takes a third town. And names come off it individually — cooling one lord takes
his name off without taking the letter down, because a lever that does nothing
is not a lever. The bar to sign (45) sits above the bar to stay (32), so
nobody signs and unsigns weekly.

### A war wants a reason

Nothing stops you marching on anybody at any hour. What a **ground** buys is
that the rest of the march shrugs instead of writing to each other, and that
your own town does not spend the season saying it was a wicked business.

Grounds come from things that already happen — they burned your country, they
cut your roads, their host is on your land, they marched while a treaty ran,
they signed against you, an ally called you — and from a claim by marriage,
which never expires. Marching without one offends every bystander twice over
*and* costs your own towns up to 14 of mood, because they have sons in the host
and no idea what any of this is for.

Measured, same seed, same conquering bot:

| | the march unites on |
|---|---|
| marching with no grounds | **day 498** |
| marching only when wronged | **day 1006** |

A lawful war also makes the *conquest* cheaper (a town taken in a war the march
accepted the reason for offends at 60%), which is the second half of what a
marriage is for, and why a dowry is worth paying years before anybody dies.

### Friends cost something

`ally <town>` needs a lord who already thinks well of you (+40). An ally does
not march on you, comes when you are attacked — and **calls when he is**. You
have twelve days to answer, and `call no` is a real answer: the alliance ends
and every other lord on the march is told what your word is worth, in a grudge
that decays slower than almost anything else in the book. Saying nothing is
saying no.

That last one was a bug for about an hour, and an instructive one: the timeout
path cleared the pending call and *then* asked the answering function to act on
it, which found nothing pending and did nothing at all. No broken alliance, no
grudge, no line in the chronicle. A silence with no consequence is not a
decision the player was ever offered.

### And a house that ends

The other reason to marry a daughter into Ostmark. A marriage makes a **claim**,
and if that house ends without an heir of its body, what it held comes to you
with nobody in the field. It is rare on purpose — but it is the only way a town
arrives without a war, and the only thing in this game that makes a dowry look
cheap in hindsight. Without a claim, a cousin takes the hall and you hear about
it, which is what most history is.

### And it is priced as money, not kept in a screen

The question a system like this has to answer is whether it is *integrated* or
merely *present*. A diplomacy screen you visit is a spreadsheet; a diplomacy
that decides what your carts pay is a world.

**A lord's opinion is the rate his customs post charges you.** That is the
whole seam, and it is one function:

| | his toll on your carts |
|---|---|
| allied | 1.4% |
| married into his house | 2.2% |
| a stranger | 4.0% |
| hostile | 6.5% |
| signed against you | 7.6% |

Which means a gift is an investment with a rate of return rather than only war
insurance, that a marriage pays a dividend every day for the rest of the
campaign, and that the cost of the third town is a number you watch in the
ledger long after the war is over.

And because the toll was already the thing the route-finder asked about,
everything downstream reads the politics **without a line of new code**. The
same `scan`, same seeds, three different diplomatic positions:

```
neutral :  dunmere -> aldworth  264.6c/day
hated   :  dunmere -> aldworth  246.8c/day   (and the 2nd and 3rd swap places)
married :  dunmere -> aldworth  278.9c/day
```

`surplus <good> <town>` — the one screen in the game that prices a tax
properly, with its consumer surplus, producer surplus and deadweight-loss
triangle — now names who is levying it and why. It was previously the only
screen that could not see the politics of the toll it was weighing.

**And the street knows.** A coalition is not a diplomatic event to a carter:

```
  One of the wall guard
    "My brother carts to Ostmark and they turned him at the bridge. He
     says every lord on the march has put his name to something."
  A fishwife
    "My son is in the host and I cannot tell his mother what for."
```

Eight new voices keyed to the politics and the accounts — the letter, an
unanswered call, a blockade, a war with no cause anybody can name, prices that
have moved, tolls that have doubled, and roads that are quiet because you paid
for them to be. They sit among the rest by weight rather than in a section of
their own, because that is how they arrive: you find out you have a coalition
from somebody whose brother was turned back at a bridge.

**The bug this turned up.** The toll had been quietly decaying to nothing for
the life of the project. `tariff_for` read the base rate off the market, the
trade engine wrote the *effective* rate back into the same field on every
visit, and so the trading posts' relief compounded once per cart: after two
hundred visits a six per cent toll was eight thousandths of one per cent, and
every customs post on the march had stopped charging for anything. The base
rate now lives on the town and the working rate on the market, which are two
different things that had been one field.

Fixing it makes the game **meaningfully harder** — an ordinary trading policy
now finishes at a mean of 87,300 against a goal of 120,000, where before the
fix it finished at 108,000. That is not a balance change dressed as a bugfix;
it is a designed cost that had been silently refunded. The balance guard
passes on its own twelve seeds with room, and the goal is still reached.

### Two things this cost to get right

* **A retaken town is not a second conquest.** Charging full aggressive
  expansion every time a garrison wavered and the town was retaken ran one lord
  to two hundred points of ill-will and a two-thousand-day decay. That is not a
  decision, it is a spiral. The march priced you as the man who took Caldmoor
  the first time.
* **The court screen promised something the arithmetic did not keep.** It told
  the player each broken host was worth 22 against the letter, while `offence`
  summed only the *negative* reasons — so a broken host was worth exactly
  nothing. An interface that makes a promise the model does not keep is worse
  than one that says nothing.

And the fourth instance of the same architectural lesson: the chancery rolls its
own dice. The kin moved the weather; the league re-rolled twelve seeds of
balance measurement; the voices would have re-rolled the campaign from a browser
poll. There are no exceptions left to find.

### What we still do not have

The flat `view` still draws a **schematic** rectangle rather than your castle:
sixty-eight columns of terminal will not hold a thirty-yard square honestly,
and half-doing it gives a picture that is neither. `castle` draws the real
shape, and `view` now says in a line when the two would disagree rather than
quietly drawing a workshop inside a wall that does not reach it.

## The march is a league

```
season [past]             the table, and who has said they are coming
draft [<name>]            the men looking for a lord, in reverse order of finish
```

The march always had eight rival lords taking towns off each other. What it
did not have was the one thing that turns a set of rivalries into a
competition you can follow — a **table**. You could not say who was ahead. You
could not say who was coming for you next. And a season that went badly went
badly for ever, because nothing in the design ever handed anything back to
whoever was losing.

Those three gaps have one well-known answer between them and it is not a
medieval one. The NFL is the most deliberately balanced competition anybody
has built: a standings table everyone reads the same way, a schedule published
before a ball is thrown, and a set of levers — a draft in reverse order of
finish, a ceiling on what anyone may spend — whose entire purpose is to stop
last year deciding next year. *Any given Sunday* is a design goal, not a
slogan.

Which is exactly the hole the [fair play](#fair-play) pass measured: outcomes
ranging five-fold across seeds on an identical map, because an early stumble
never compounds back. A league has faced precisely that problem and solved it
on purpose.

### The table

```
── THE 1249 SEASON ─────────────────────────────── you stand 1st of 9 ──
   #  place        who holds it          towns    W-L   could field
   1  you          Eadric the Fair          3     0-0           91
   2  Marchand     the Count of Marchand    2     1-0          108
   9  Dunmere      Reeve Halden             1     0-3           30
```

Towns first because towns are the game, then fields won because a lord who
keeps winning is coming for you whatever he holds, then what he could put in
the field. That last one is deliberately **muster and not worth**: a player
with a whole economy behind them is richer than any lord on the march by an
order of magnitude, so worth put them top of a column that meant nothing.

Every storm and every scrap at a shrine now leaves a **box score** — both
sides, both losses, the rounds it took. The log said who held the ground and
nothing else, which is the result without the game.

### The schedule

Lords declare at the turn of the year who they mean to move on. It can change
— a muster roll is an intention, not an oath — but you are no longer
blindsided by a host that was always coming. It is drawn on the march as a
bowed arrow from each lord to the place he named, and **the one pointed at you
is the only red thing on that map**.

Getting this wrong was instructive: reading a flat nought as "hostility is at
least ambition" put every lord on the march down as marching on your gate in
the first spring, which is a schedule that tells you nothing at all.

### The draft

Each spring four men worth having come looking for a lord — a steward who kept
a bishop's manors for nine years, a factor who walked the salt road twice a
year for a decade — and they go in **reverse order of last year's table**.
Finish last and you choose first. It is the single most effective parity
device ever designed and it plugs straight into a house that needs a steward.

A drafted man arrives knowing his trade and no further on than a son who has
held the post four years; a draft that handed out a steward of six would
decide the game by itself, which is the opposite of what a draft is for. He is
**sworn, not blood** — he can hold any post and he cannot inherit the seat.

The first spring is drawn for rather than given to you, because handing the
player first pick of the first class would be a head start the whole device
exists to prevent.

### The cap

Not a ceiling — a rising cost. Past what your holdings can reasonably keep
under arms, every further soldier eats more than the last:

| host against the cap | what each man costs |
|---|---|
| at the cap | 1.00× |
| half again | 1.57× |
| twice | 2.45× |
| three times | 4.70× |

A hard ceiling is a rule a player fights; a rising cost is a decision a player
makes, and it still ends runaway musters because the last man on the roll eats
like three.

## Fair play

A pass spent measuring rather than adding, on the three things a player is
entitled to: that the rules are consistent, that the systems agree with each
other, and that the game can be lost but not stolen. Four findings, all of
them measured before they were fixed.

### You could print the win

Net worth counts the chest and the granary at today's prices, and the goal was
net worth. So `mint 20000` raised the score by twenty thousand the instant the
dies came down, against a target of a hundred and twenty — no strategy, a
hole.

The goal is now measured in the coin of the first year, and the divisor is the
money you have *struck* rather than how far prices have caught up with it.
Prices lag a year or two and that lag is the whole reason anybody debases, but
a goal measured against the lagging number could be crossed by minting on the
last afternoon.

What this does **not** do is make debasement worthless, and it should not:
seigniorage is a real tax really collected. What it does is give it the shape
it has in life —

| when | what minting the limit does to the goal number |
|---|---|
| day 300, worth 21,591c | **+9,602** |
| day 900, worth 100,337c | **−10,084** |

— worth most to a poor house with nothing to lose, and a straight loss to a
rich one, because a third more coin against a hundred thousand of holdings
takes more than the twenty thousand it hands you. And a debased penny is now
dearer in Ostmark too: leaving foreign prices alone had made minting a
standing subsidy on imports, which is an arbitrage the mint itself printed.

### The tax dial had seven bands and one that worked

Measured over six seeds and three years each, holding one band the whole game:

| band | net worth | souls | wins |
|---|---|---|---|
| none | 2,224 | 91 | 0 |
| light | 9,065 | 151 | 0 |
| **normal** | **110,137** | **476** | **3** |
| heavy | 238,760 | 343 | 1 |
| cruel | **466,926** | 197 | 0 |

Cruel collected **four times** what normal did. The only thing stopping it
being the obvious answer was that the win also wants souls — a thin guard on a
dial where a player optimising coin would find the wrong end of it immediately.

The fix is the one the book gives: a tax is a lever on *behaviour* before it is
a lever on revenue. The day that is taxed away stops being worked, goods go
over the wall instead of through the market, and the reeve's books get
creative. `TAX_COMPLIANCE` makes the take per head fall as the rate climbs, so
total revenue peaks in the middle — cruel now collects **less** than heavy,
which makes it a genuinely wrong answer instead of a hidden right one.

Nothing leaks at the rates the game was actually tuned around, and that is
deliberate: this economy runs thin enough that **three per cent off the tax
roll compounds into half the net worth over three years**. A first attempt put
a 0.97 on "normal" and halved the baseline. There is a test that holds the
middle bands at exactly what they always collected.

And `tax` with no argument now prices every band before you pull it — what it
asks for, what it collects, what it costs in goodwill, and which one is the
most there is to collect today. A dial whose bands you cannot compare in
advance is not a decision, it is a surprise.

### The assize was a trap, not a choice

A price ceiling is usually a bad idea, which is not the same as never being any
use — but as built it had **no upside whatever**: capping bread cost five
sixths of the run's net worth and bought nothing. A lever that is always wrong
is decoration.

It is a transfer now: cheap bread is a real transfer to real people and they
are grateful for it, right up until there is none and they are standing in a
queue your proclamation put them in. So it runs **+11 mood while there is
stock, −15 once there is not**, and the decree says at the moment you make it
how long that will be — "about 11 days" on a thin granary, "about 52" on a
full one. A price control is a transfer out of a granary, so its whole life is
however much is in the granary; saying so up front is the difference between a
decision and an ambush.

And then it was a free lunch, which took a second pass to find. The shortage
was modelled as a *proportion of the shelf* — 3.5% a day at a cap that bit
entirely — and a proportional drain is not a shortage, it is a decay: the shelf
simply settles at forty days' output, and any town that bakes its own bread
never queues at all. Measured on a grown save, a fully biting cap cost **2% of
the granary over sixty days** and the queue the whole lever exists to create
never once formed. The +12 was free.

Excess demand is a **quantity**, not a fraction of the shelf, and the quantity
it is measured against is how much the town gets through in a day. With that
one change, the same save played the same way for 150 days:

| | net worth | mood | bread on the shelf |
|---|---|---|---|
| no decree | 36,633 | 73.1 | 198 |
| bread held 70% under | 27,083 | 57.5 | **0** |

A quarter of the house's worth and fifteen points of goodwill, for four months
of cheap bread. That is a decision. The forecast and the mechanic are now the
same function rather than two guesses at each other, so "about 40 days" is a
promise the simulation keeps.

The two tests that should have caught it were **freezing the town** — growing a
save, then ticking it with nobody buying or selling. A settlement with no hands
on it piles its sheds' output on a shelf nobody draws from, and a shortage
cannot be measured against a market that has stopped. They passed for a year on
a knife edge and failed the moment an unrelated change moved the trajectory,
which is the only reason any of this was found.

### The race was invisible until the last day

The map is identical across seeds — same deposits, same land, same best trade
route — and outcomes still ranged from 23,035c to 134,043c. The cause is
structural rather than random: income and costs are both roughly proportional
to population, so the *surplus* is a small difference between two big numbers,
and a run that misses the early window never compounds its way back. One seed
finished at a fifth of the goal without a single disaster in its log.

That is a legitimate difficulty spread. What was not legitimate is that the
player could not see it. `status` now carries the race:

```
  the race     net worth 18,856/120,000 →17,700   souls 197/450 →212   (660d left, at this rate)
```

A straight line through the last half-year, which is crude and is the point:
it is the arithmetic a steward would do on the back of the tax roll, and it is
enough to say in the first winter that the second year will not be enough.
Paths you have not started on are dim rather than red, because they are other
ways to win and not clauses you are failing. The hint ranks it at 68, above
almost everything else, and the browser panel carries the same reading —
two interfaces that disagree about whether you are winning are worse than one.

## Tuning

All balance lives in `config.py` and the data tables. The one number to respect
is `WAGE`: every base price in `goods.py` was set against the cost of a
worker-day, so moving it moves the margin on every trade at once. Victory terms
are per-scenario (`engine.Goals`), not global.

Several tests are balance guards rather than correctness tests. The important
one is `test_the_goal_is_reachable_but_not_assured`: the trading bot in `sim.py`
plays the economic game competently and no better, and over twelve seeds it
should take the crown **sometimes and not always**. Over sixteen seeds it wins
six, and the rest finish between 23k and 125k of a 120,000c target. A target
nobody can reach is decoration; one that falls out of an ordinary policy every
time is a formality.

The median run lands within a tenth of a per cent of the goal, which is not an
accident and is the calibration: the bot plays adequately and finishes on the
line, so a better player wins and a worse one does not.

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
