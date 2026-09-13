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
python3 -m unittest discover -s tests          # 474 tests, ~5min
```

In game, **`view`** draws your town and **`watch`** lets you sit and watch it
work, `chronicle` reads your reign back, `hint` tells you what a patient
steward would point at next, `briefing` restates why you are here, and `help`
lists everything.

### Installing it

```bash
pip install ./game            # or: python3 -m build --wheel && pip install dist/*.whl
marchlands --web
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

**Its own** — the trade layer. In both parents trade was a side activity. Here
coin only enters your treasury through thin taxes and the road, so the market is
where the game is played.

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
| `render.py` | ink: palette, framing, bars, sparklines, colour discipline |
| `iso.py` | the holding in perspective: tiles, sprites, smoke, people |
| `view.py` | the same holding as a flat plan |
| `castle.py` | works, assault plans, and what answers what |
| `lord.py` | your lord: what he is worth, and what can happen to him |
| `fire.py` | what catches, how it spreads, and what puts it out |
| `layout.py` | where everything stands, so a renderer can draw a place |
| `web.py` | a stdlib server and the browser's view of the game |
| `static/` | the canvas renderer: every roof a vector path, every sound an oscillator |
| `campaign.py` | six chapters, what crosses between them, the Count |
| `chronicle.py` | what happened, written down as it happened |
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
