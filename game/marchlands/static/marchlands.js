/* Marchlands, drawn.
 *
 * Everything here is a vector path. There are no images in this repository and
 * there is no dependency list: the thatch is a row of arcs, the stone is a
 * brick pattern, and the smoke is forty particles with a lifetime. The rule
 * that this game installs with nothing was worth more than a texture atlas.
 *
 * The layout arrives from Python already decided -- which building stands on
 * which plot, where the road runs, where the wood is. This file's only job is
 * to make it look like somewhere.
 */
'use strict';

const TW = 64, TH = 32;                 // tile, in screen pixels
const canvas = document.getElementById('view');
let ctx = canvas.getContext('2d');   /* let, not const: the ground is baked on a second context of its own */

let state = null, plan = null, t0 = performance.now(), smoke = [], flames = [];
let camera = { x: 0, y: 0, zoom: 1 }, hover = null, dpr = 1;

/* Some people cannot watch a scene that never stops moving. Asked to be still,
 * the town holds one frozen instant -- smoke does not rise, sails do not turn,
 * nobody walks -- and the picture still redraws whenever the day does. */
const STILL = !!(window.matchMedia &&
                 window.matchMedia('(prefers-reduced-motion: reduce)').matches);
const clock = () => STILL ? 9 : (performance.now() - t0) / 1000;
/* Matches the stylesheet's one breakpoint: past it the panel lies down. */
const NARROW = () => canvas.clientWidth <= 720;
/* Every number a player reads is grouped. `+1488` in a ledger beside `2,989c`
 * in the purse is two people writing the same page. */
const num = v => Math.round(v).toLocaleString();

/* ------------------------------------------------------------------ light
 * A day passes in the simulation when you ask for one; the light does not
 * wait to be asked. It turns on its own, and every simulated day it is given
 * one more turn to make -- so `a week` wheels the sun round seven times and
 * you can watch a week go by, which is the cheapest way there is to make a
 * button feel like it did something.
 *
 * `phase` is 0 at dawn, .25 at noon, .5 at dusk, .75 at midnight.
 */
const DAY_SECONDS = 110;          // one turn of the sky, left alone
const SWEEP = 1.9;                // turns a second when it is catching up
let phase = 0.18, phaseTarget = 0.18, lastClock = 0, lastDay = null;
let glows = [];                   // things that shine, drawn after the light

function turnTheSky(t) {
  if (lastClock === 0) lastClock = t;
  const dt = Math.max(0, Math.min(0.25, t - lastClock));
  lastClock = t;
  if (state && lastDay !== null && state.day !== lastDay) {
    phaseTarget += Math.max(0, state.day - lastDay);   // a turn for each day
  }
  if (state) lastDay = state.day;
  phaseTarget += STILL ? 0 : dt / DAY_SECONDS;
  const gap = phaseTarget - phase;
  phase += STILL ? gap : Math.min(gap, SWEEP * dt);
  if (phase > 8) { phase -= 8; phaseTarget -= 8; }     // keep the maths small
}

/* Where the sun is and what colour the day is, out of one number.
 *
 * p runs 0 dawn, .25 noon, .5 dusk, .75 midnight, so the elevation is just a
 * sine of it and everything else falls out: how dark it is, how warm the low
 * light is, and which way a shadow is thrown.
 */
function sun() {
  const p = phase % 1;
  const up = Math.sin(p * Math.PI * 2);            // -1 midnight, +1 noon
  const alt = Math.max(0, up);
  const night = Math.max(0, Math.min(1, (0.06 - up) / 0.34));
  const warm = Math.max(0, 1 - Math.abs(up) * 2.6) * (1 - night * 0.7);
  return { p, up, alt, night, warm,
           az: Math.PI * (0.12 + 1.46 * p) };
}

/* ---------------------------------------------------------------- palette */
const SEASON = {
  spring: { sky: ['#9dc4e8', '#dfe9f2'], grass: '#6f8f4a', crop: '#8fae52',
            tree: '#4b7434', water: '#4f7fa8', earth: '#7b6749', sun: '#fff3c4' },
  summer: { sky: ['#86b7e2', '#e8eef1'], grass: '#7d9a45', crop: '#c9a93f',
            tree: '#3f6b2c', water: '#4a86b4', earth: '#8a7553', sun: '#fff6cf' },
  autumn: { sky: ['#a9b6c4', '#e3dccd'], grass: '#8a8a48', crop: '#a8853a',
            tree: '#8a6a2a', water: '#4a7595', earth: '#7d6a4c', sun: '#ffe9b0' },
  winter: { sky: ['#9fb0c2', '#d8dee5'], grass: '#c9d2d6', crop: '#b9c2c6',
            tree: '#4a5a4a', water: '#5c7f97', earth: '#9aa0a2', sun: '#f2f4f8' },
};
const pal = () => SEASON[(state && state.season) || 'spring'] || SEASON.spring;

/* Roofs and walls by what a building is. Thatch for the poor, tile for the
 * comfortable, slate and stone for anything the lord paid for. */
const STYLE = {
  hovel:      { w: 43, roof: 'thatch', wall: 'daub',   c: '#b79a63', s: 0.8 },
  cottage:    { w: 44, roof: 'thatch', wall: 'timber', c: '#c2a469', s: 0.95 },
  townhouse:  { w: 53, roof: 'tile',   wall: 'timber', c: '#9c5638', s: 1.25 },
  keep:       { w: 69, roof: 'none',   wall: 'stone',  c: '#8d8a80', s: 2.1 },
  barracks:   { w: 50, roof: 'tile',   wall: 'stone',  c: '#8a6a52', s: 1.0 },
  chapel:     { w: 46, roof: 'spire',  wall: 'stone',  c: '#9b978c', s: 1.35 },
  cathedral:  { w: 69, roof: 'spire',  wall: 'stone',  c: '#a9a59a', s: 2.4 },
  granary:    { w: 54, roof: 'thatch', wall: 'plank',  c: '#b08f56', s: 1.05 },
  warehouse:  { w: 57, roof: 'tile',   wall: 'plank',  c: '#8d6a45', s: 1.0 },
  market:     { w: 56, roof: 'awning', wall: 'open',   c: '#a8412f', s: 0.7 },
  mill:       { w: 37, roof: 'cone',   wall: 'stone',  c: '#9a9086', s: 1.9 },
  inn:        { w: 51, roof: 'tile',   wall: 'timber', c: '#a2603a', s: 1.15 },
  guildhall:  { w: 56, roof: 'tile',   wall: 'stone',  c: '#8f6b45', s: 1.3 },
  bakery:     { w: 47, roof: 'tile',   wall: 'daub',   c: '#9d6a46', s: 0.95, oven: 1 },
  kiln:       { w: 43, roof: 'cone',   wall: 'clay',   c: '#8c5a3c', s: 1.1, oven: 1 },
  smelter:    { w: 46, roof: 'cone',   wall: 'stone',  c: '#7a6a5c', s: 1.2, oven: 1 },
  brewery:    { w: 48, roof: 'tile',   wall: 'timber', c: '#94663c', s: 1.05, oven: 1 },
  blacksmith: { w: 44, roof: 'tile',   wall: 'stone',  c: '#7f6a58', s: 1.0, oven: 1 },
  armourer:   { w: 47, roof: 'tile',   wall: 'stone',  c: '#7a6858', s: 1.05, oven: 1 },
  charcoal_burner: { w: 40, roof: 'mound', wall: 'earth', c: '#4a3c30', s: 0.7, oven: 1 },
  sawmill:    { w: 48, roof: 'plankroof', wall: 'plank', c: '#8a6f48', s: 0.95 },
  farm:       { w: 41, roof: 'thatch', wall: 'plank',  c: '#a89055', s: 0.7 },
  orchard:    { w: 30,  roof: 'trees',  wall: 'none',   c: '#4b7434', s: 0 },
  woodcutter: { w: 38, roof: 'thatch', wall: 'plank',  c: '#9c8450', s: 0.7 },
  quarry:     { w: 44, roof: 'none',   wall: 'pit',    c: '#9a958c', s: 0.2 },
  iron_mine:  { w: 43, roof: 'plankroof', wall: 'timber', c: '#6d6258', s: 0.8 },
  clay_pit:   { w: 43, roof: 'none',   wall: 'pit',    c: '#8a5a3c', s: 0.2 },
  harbour:    { w: 54, roof: 'plankroof', wall: 'plank', c: '#8a6f4c', s: 0.75 },
  default:    { w: 46, roof: 'tile',   wall: 'timber', c: '#96714a', s: 1.0 },
};
/* ...and then by where you are. An architecture set changes four things at
 * once -- what the walls are, what the roofs are, how steep they sit and what
 * colour the street is -- because any one of them alone is a palette swap and
 * four of them together is a place. See culture.py for why it belongs to the
 * ground rather than to the player. */
const NO_CULTURE = { walls: {}, roofs: {}, pitch: 1, gable: 'plain',
                     stretch: 1, tone: 1, tint: '', tint_by: 0,
                     roof_tint: '', roof_by: 0 };
let forceIdiom = null;
function idiom() {
  // `forceIdiom` is how a *foreign* town gets drawn in its own architecture.
  // Five idioms are worth having only if you can tell whose town you are
  // looking at, and until now a lord's idiom was a word on the war screen and
  // nothing else: you never actually saw Havnhold's brick gables.
  if (forceIdiom) return forceIdiom;
  return (state && state.culture) || NO_CULTURE;
}

const BASE_STYLE_OF = k => STYLE[k] || STYLE.default;
function styleOf(k) {
  const base = BASE_STYLE_OF(k);
  const c = idiom();
  if (c === NO_CULTURE) return base;
  const key = c.key + ':' + k;
  if (STYLE_CACHE[key]) return STYLE_CACHE[key];
  const st = Object.assign({}, base);
  st.wall = c.walls[st.wall] || st.wall;
  st.roof = c.roofs[st.roof] || st.roof;
  st.c = c.tint ? mix(st.c, c.tint, c.tint_by) : st.c;
  if (c.tone !== 1) st.c = shade(st.c, c.tone);
  st.s = base.s * (c.stretch || 1);
  st.pitch = c.pitch || 1;
  st.gable = c.gable || 'plain';
  st.roof_tint = c.roof_tint;
  st.roof_by = c.roof_by;
  STYLE_CACHE[key] = st;
  return st;
}
const STYLE_CACHE = {};

/* ---------------------------------------------------------------- helpers */
const $ = id => document.getElementById(id);
const iso = (x, y) => [(x - y) * TW / 2, (x + y) * TH / 2];
/* Accepts what it returns. Shading an already-shaded colour used to give NaN,
 * which canvas paints as black -- every forest and every road came out as a
 * hole in the ground until this took rgb() as well as #rrggbb. */
const rgbOf = colour => {
  if (colour[0] === '#') {
    const n = parseInt(colour.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const m = colour.match(/-?\d+(\.\d+)?/g) || [0, 0, 0];
  return [+m[0], +m[1], +m[2]];
};
const shade = (colour, f) => {
  const c = rgbOf(colour).map(v => Math.max(0, Math.min(255, Math.round(v * f))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
};
const mix = (a, b, f) => {
  const x = rgbOf(a), y = rgbOf(b);
  const c = x.map((v, i) => Math.round(v + (y[i] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
};
/* A shadow is geometry, not light, so it is drawn with the thing that casts
 * it rather than in the wash. Long and sideways at either end of the day,
 * short and under your feet at noon, and gone at night -- where a soft patch
 * of contact shade takes over, because a building with nothing under it at
 * all floats. */
function castShadow(sx, sy, w, d, h) {
  const s = sun();
  if (s.night > 0.93) return;
  const len = h * (0.35 + 2.6 * Math.pow(1 - s.alt, 2)) * (1 - s.night);
  const dx = Math.cos(s.az) * len, dy = -Math.sin(s.az) * len * 0.42;
  // A long shadow is not a faint one. It softens at the edges in life, which
  // a flat fill cannot do, but fading it out at dusk loses the hour entirely.
  const soft = 0.26 * (1 - s.night * 0.85);
  ctx.fillStyle = `rgba(24,20,14,${soft.toFixed(3)})`;
  ctx.beginPath();
  ctx.moveTo(sx - w, sy);
  ctx.lineTo(sx, sy - d);
  ctx.lineTo(sx + dx, sy - d + dy);
  ctx.lineTo(sx + w + dx, sy + dy);
  ctx.lineTo(sx + w, sy);
  ctx.lineTo(sx, sy + d);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(sx, sy + 1, w * 0.92, d * 0.92, 0, 0, 7);
  ctx.fill();
}

function poly(pts, fill, stroke) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
}
/* Smooth low-frequency noise over the tile grid: bilinear between hash values
 * on a coarse lattice. Cheap, stable, and the only thing that makes a meadow
 * look like ground rather than like a spreadsheet of greens. */
function swell(x, y, scale) {
  const gx = x / scale, gy = y / scale;
  const x0 = Math.floor(gx), y0 = Math.floor(gy);
  const fx = gx - x0, fy = gy - y0;
  const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
  const a = rnd(x0, y0, 91), b = rnd(x0 + 1, y0, 91);
  const c = rnd(x0, y0 + 1, 91), e = rnd(x0 + 1, y0 + 1, 91);
  return (a + (b - a) * sx) + ((c + (e - c) * sx) - (a + (b - a) * sx)) * sy;
}

/* A cheap deterministic hash, so the same tile always grows the same tuft. */
const rnd = (x, y, n) => {
  const s = Math.sin(x * 127.1 + y * 311.7 + n * 74.7) * 43758.5453;
  return s - Math.floor(s);
};

/* ------------------------------------------------------------------ ground */
function drawTile(x, y, kind) {
  const [sx, sy] = iso(x, y), p = pal();
  const d = [[sx, sy - TH / 2], [sx + TW / 2, sy], [sx, sy + TH / 2], [sx - TW / 2, sy]];
  let base = p.grass;
  if (kind === 'field') base = p.crop;
  // A wood is grass with less light on it. Painted at the leaf colour it read
  // as a dark diamond stamped into the field, which is a hole, not a wood.
  else if (kind === 'forest') base = mix(p.grass, shade(p.tree, 0.88), 0.52);
  else if (kind === 'hill') base = '#8e8a80';
  else if (kind === 'clay') base = '#9a6742';
  else if (kind === 'marsh') base = mix('#5f6b4a', p.water, 0.28);
  else if (kind === 'water') base = p.water;
  else if (kind === 'road') base = shade(p.earth, 1.32);
  else if (kind === 'yard') base = shade(p.earth, 1.18);
  // Two scales of variation, and the second one is what stops the ground
  // reading as a checkerboard. Per-tile noise alone paints a grid: every
  // diamond a different shade with a hard seam at its edge, which is exactly
  // what the eye is best at picking out. A broad smooth swell laid over the
  // top gives sunlit and shaded ground that crosses tile boundaries, and the
  // per-tile part can then be small enough to read as texture rather than
  // tiling.
  const tint = (0.975 + 0.05 * rnd(x, y, 1)) * (0.93 + 0.15 * swell(x, y, 5));
  poly(d, shade(base, tint));

  if (kind !== 'water')
    tooth(d, kind === 'grass' || kind === 'forest' ? 2 : 1, 0.40,
          kind === 'yard' || kind === 'road' ? 0.34 : 0.30);

  if (kind === 'field') {
    // Furrows, running the same way across the whole field -- and a crop
    // standing in them that is not the same crop in February as in August.
    ctx.strokeStyle = shade(base, 0.80);
    ctx.lineWidth = 1;
    for (let i = 1; i < 8; i++) {
      const f = i / 8;
      ctx.beginPath();
      ctx.moveTo(sx - TW / 2 + f * TW / 2, sy - f * TH / 2);
      ctx.lineTo(sx + f * TW / 2, sy + TH / 2 - f * TH / 2);
      ctx.stroke();
      ctx.strokeStyle = shade(base, 1.10);
      ctx.beginPath();
      ctx.moveTo(sx - TW / 2 + f * TW / 2, sy - f * TH / 2 + 1.2);
      ctx.lineTo(sx + f * TW / 2, sy + TH / 2 - f * TH / 2 + 1.2);
      ctx.stroke();
      ctx.strokeStyle = shade(base, 0.80);
    }
    const season = state && state.season;
    if (season && season !== 'winter') {
      const tall = season === 'summer' ? 4.2 : season === 'autumn' ? 3.0 : 1.8;
      ctx.strokeStyle = shade(base, season === 'autumn' ? 1.22 : 1.12);
      ctx.lineWidth = 0.9;
      for (let i = 0; i < 14; i++) {
        const cx = sx + (rnd(x, y, i + 40) - 0.5) * TW * 0.78;
        const cy = sy + (rnd(x, y, i + 60) - 0.5) * TH * 0.78;
        ctx.beginPath(); ctx.moveTo(cx, cy);
        ctx.lineTo(cx + 0.8, cy - tall - rnd(x, y, i + 80) * 1.6);
        ctx.stroke();
      }
    }
  } else if (kind === 'grass') {
    // A meadow is tufts and bare patches and the odd stone, not a green
    // diamond with three ticks on it. The patches are large and soft so they
    // cross tile edges; the tufts are many and small so they read as grass
    // rather than as marks.
    for (let i = 0; i < 4; i++) {
      const px = sx + (rnd(x, y, i + 11) - 0.5) * TW * 0.85;
      const py = sy + (rnd(x, y, i + 13) - 0.5) * TH * 0.85;
      ctx.fillStyle = shade(base, 0.88 + rnd(x, y, i + 15) * 0.26);
      ctx.beginPath();
      ctx.ellipse(px, py, 7 + rnd(x, y, i + 17) * 11, 3 + rnd(x, y, i + 19) * 3,
                  0, 0, 7);
      ctx.fill();
    }
    ctx.lineWidth = 1;
    for (let i = 0; i < 22; i++) {
      const bx = sx + (rnd(x, y, i + 3) - 0.5) * TW * 0.84;
      const by = sy + (rnd(x, y, i + 7) - 0.5) * TH * 0.84;
      ctx.strokeStyle = shade(base, 0.68 + rnd(x, y, i + 21) * 0.62);
      ctx.beginPath(); ctx.moveTo(bx, by);
      ctx.lineTo(bx + (rnd(x, y, i + 23) - 0.5) * 3.0,
                 by - 2.0 - rnd(x, y, i + 27) * 3.2);
      ctx.stroke();
    }
    if (rnd(x, y, 30) > 0.80) {         // a clump of something in flower
      const fx = sx + (rnd(x, y, 31) - 0.5) * 26;
      const fy = sy + (rnd(x, y, 32) - 0.5) * 12;
      ctx.fillStyle = state && state.season === 'spring' ? '#d9d27a'
                    : state && state.season === 'summer' ? '#c9b8d2' : '#b8ab72';
      for (let i = 0; i < 5; i++) {
        ctx.beginPath();
        ctx.ellipse(fx + (rnd(x, y, i + 60) - 0.5) * 9,
                    fy + (rnd(x, y, i + 64) - 0.5) * 5, 0.9, 0.7, 0, 0, 7);
        ctx.fill();
      }
    }
    if (rnd(x, y, 33) > 0.88) {                 // a stone somebody ploughed up
      ctx.fillStyle = '#948d82';
      ctx.beginPath();
      ctx.ellipse(sx + (rnd(x, y, 34) - 0.5) * 20, sy + (rnd(x, y, 35) - 0.5) * 9,
                  2.4, 1.5, 0, 0, 7);
      ctx.fill();
      ctx.fillStyle = 'rgba(30,28,22,.28)';
      ctx.beginPath();
      ctx.ellipse(sx + (rnd(x, y, 34) - 0.5) * 20 + 1.2,
                  sy + (rnd(x, y, 35) - 0.5) * 9 + 1.2, 2.2, 1.1, 0, 0, 7);
      ctx.fill();
    }
  } else if (kind === 'road' || kind === 'yard') {
    // Trodden earth: two ruts where the carts go, gravel where they do not,
    // and the puddles they leave in the hollows.
    if (kind === 'road') {
      ctx.strokeStyle = shade(base, 0.80); ctx.lineWidth = 2.2;
      for (const off of [-4, 4]) {
        ctx.beginPath();
        ctx.moveTo(sx - TW / 2, sy + off * 0.5);
        ctx.lineTo(sx + TW / 2, sy + off * 0.5);
        ctx.stroke();
      }
    }
    // Trodden ground is not one colour: it is bare patches, gravel, and the
    // places the water stands after rain.
    for (let i = 0; i < 4; i++) {
      const px = sx + (rnd(x, y, i + 44) - 0.5) * TW * 0.7;
      const py = sy + (rnd(x, y, i + 46) - 0.5) * TH * 0.7;
      ctx.fillStyle = shade(base, 0.88 + rnd(x, y, i + 48) * 0.22);
      ctx.beginPath();
      ctx.ellipse(px, py, 6 + rnd(x, y, i + 49) * 9, 3 + rnd(x, y, i + 51) * 3,
                  0, 0, 7);
      ctx.fill();
    }
    for (let i = 0; i < 16; i++) {
      const gx = sx + (rnd(x, y, i + 50) - 0.5) * TW * 0.84;
      const gy = sy + (rnd(x, y, i + 55) - 0.5) * TH * 0.84;
      ctx.fillStyle = shade(base, 0.76 + rnd(x, y, i + 58) * 0.5);
      ctx.beginPath(); ctx.ellipse(gx, gy, 1.4, 0.85, 0, 0, 7); ctx.fill();
    }
  } else if (kind === 'marsh') {
    // Fen: standing water in the hollows, sedge standing out of it, and the
    // odd hummock of peat somebody has been cutting. Land you own and cannot
    // work until you drain it, and it ought to look like it.
    for (let i = 0; i < 3; i++) {
      const px = sx + (rnd(x, y, i + 120) - 0.5) * TW * 0.75;
      const py = sy + (rnd(x, y, i + 124) - 0.5) * TH * 0.75;
      ctx.fillStyle = shade(pal().water, 1.02);
      ctx.beginPath();
      ctx.ellipse(px, py, 7 + rnd(x, y, i + 128) * 9, 3 + rnd(x, y, i + 130) * 2,
                  0, 0, 7);
      ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,.10)';
      ctx.beginPath();
      ctx.ellipse(px - 1, py - 0.8, 5 + rnd(x, y, i + 128) * 6, 1.2, 0, 0, 7);
      ctx.fill();
    }
    ctx.lineWidth = 1;
    for (let i = 0; i < 18; i++) {
      const bx = sx + (rnd(x, y, i + 140) - 0.5) * TW * 0.85;
      const by = sy + (rnd(x, y, i + 150) - 0.5) * TH * 0.85;
      ctx.strokeStyle = shade(base, 0.72 + rnd(x, y, i + 160) * 0.8);
      ctx.beginPath(); ctx.moveTo(bx, by);
      ctx.lineTo(bx + (rnd(x, y, i + 164) - 0.5) * 2.2,
                 by - 4.0 - rnd(x, y, i + 168) * 4.5);   // sedge, taller than grass
      ctx.stroke();
    }
  } else if (kind === 'hill' || kind === 'clay') {
    // Broken ground: scree and exposed faces catching the light on one side.
    for (let i = 0; i < 6; i++) {
      const px = sx + (rnd(x, y, i + 70) - 0.5) * TW * 0.7;
      const py = sy + (rnd(x, y, i + 74) - 0.5) * TH * 0.7;
      const r = 2 + rnd(x, y, i + 78) * 3;
      ctx.fillStyle = shade(base, 0.80 + rnd(x, y, i + 82) * 0.12);
      ctx.beginPath(); ctx.ellipse(px, py + 1, r, r * 0.55, 0, 0, 7); ctx.fill();
      ctx.fillStyle = shade(base, 1.14);
      ctx.beginPath(); ctx.ellipse(px - r * 0.2, py - 0.4, r * 0.7, r * 0.38, 0, 0, 7);
      ctx.fill();
    }
  } else if (kind === 'water') {
    // Three things make water read as water: it moves, it is darker where it
    // is deep, and it throws the sky back at you off the side facing the sun.
    const t = clock(), s = sun();
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(d[0][0], d[0][1]);
    for (let i = 1; i < 4; i++) ctx.lineTo(d[i][0], d[i][1]);
    ctx.closePath(); ctx.clip();
    // Swell: three crossing waves at different speeds, so the surface never
    // repeats on any count a player could hold.
    for (let i = 0; i < 3; i++) {
      const a = 0.055 + 0.05 * (2 - i);
      ctx.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
      const wy = sy + (i - 1) * 8
        + Math.sin(t * (0.9 + i * 0.35) + (x + y) * 0.8 + i * 2.1) * 3.0;
      ctx.beginPath();
      ctx.moveTo(sx - TW / 2, wy);
      ctx.quadraticCurveTo(sx - TW / 4, wy - 3.4, sx, wy);
      ctx.quadraticCurveTo(sx + TW / 4, wy + 3.4, sx + TW / 2, wy);
      ctx.lineTo(sx + TW / 2, wy + 2.6);
      ctx.quadraticCurveTo(sx + TW / 4, wy + 6.0, sx, wy + 2.6);
      ctx.quadraticCurveTo(sx - TW / 4, wy - 0.8, sx - TW / 2, wy + 2.6);
      ctx.closePath(); ctx.fill();
    }
    // The sun's own road across the water, which only exists when it is low.
    const glint = Math.max(0, 1 - Math.abs(s.up) * 2.2) * (1 - s.night);
    if (glint > 0.02) {
      ctx.fillStyle = `rgba(255,226,168,${(0.38 * glint).toFixed(3)})`;
      for (let i = 0; i < 3; i++) {
        const gy = sy + (i - 1) * 7 + Math.sin(t * 1.6 + x * 1.3 + i) * 2.4;
        const gw = 7 + 5 * Math.sin(t * 2.1 + y + i);
        ctx.beginPath();
        ctx.ellipse(sx + Math.cos(s.az) * 7, gy, gw, 1.15, 0, 0, 7);
        ctx.fill();
      }
    }
    // And the moon's, colder and narrower.
    if (s.night > 0.2) {
      ctx.fillStyle = `rgba(198,216,245,${(0.22 * s.night).toFixed(3)})`;
      for (let i = 0; i < 2; i++) {
        const gy = sy + (i - 0.5) * 9 + Math.sin(t * 1.1 + x + i) * 2.0;
        ctx.beginPath(); ctx.ellipse(sx, gy, 6, 0.9, 0, 0, 7); ctx.fill();
      }
    }
    ctx.restore();
  } else if (kind === 'forest') {
    // Dapple, so the edge of the wood is leaf shadow rather than a drawn line.
    ctx.fillStyle = 'rgba(22,36,14,.17)';
    for (let i = 0; i < 4; i++) {
      const bx = sx + (rnd(x, y, i + 41) - 0.5) * TW * 0.74;
      const by = sy + (rnd(x, y, i + 43) - 0.5) * TH * 0.74;
      ctx.beginPath();
      ctx.ellipse(bx, by, 6 + rnd(x, y, i + 47) * 6, 3.2, 0, 0, 7); ctx.fill();
    }
  } else if (kind === 'hill') {
    ctx.fillStyle = shade(base, 0.84);
    for (let i = 0; i < 2; i++) {
      const bx = sx + (rnd(x, y, i + 11) - 0.5) * 26;
      const by = sy + (rnd(x, y, i + 13) - 0.5) * 12;
      ctx.beginPath(); ctx.ellipse(bx, by, 5, 2.6, 0, 0, 7); ctx.fill();
    }
  } else if (kind === 'road' || kind === 'yard') {
    ctx.fillStyle = 'rgba(0,0,0,.09)';
    for (let i = 0; i < 3; i++) {
      const bx = sx + (rnd(x, y, i + 17) - 0.5) * 30;
      const by = sy + (rnd(x, y, i + 19) - 0.5) * 14;
      ctx.beginPath(); ctx.ellipse(bx, by, 2.4, 1.2, 0, 0, 7); ctx.fill();
    }
  }
  if (state && state.season === 'winter' && kind !== 'water') {
    poly(d, 'rgba(236,242,246,.42)');
  }
}

function drawTrees(x, y) {
  const [sx, sy] = iso(x, y), p = pal();
  for (let i = 0; i < 3; i++) {
    const tx = sx + (rnd(x, y, i + 23) - 0.5) * 34;
    const ty = sy + (rnd(x, y, i + 29) - 0.5) * 15;
    const h = 16 + rnd(x, y, i + 31) * 10;
    castShadow(tx, ty, 8, 3.6, h * 0.75);
    ctx.strokeStyle = '#4a3722'; ctx.lineWidth = 2.2;
    ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(tx, ty - h); ctx.stroke();
    const leaf = state && state.season === 'winter' ? null : p.tree;
    if (leaf) {
      ctx.fillStyle = shade(leaf, 0.88 + rnd(x, y, i + 37) * 0.3);
      ctx.beginPath(); ctx.ellipse(tx, ty - h - 3, 8.5, 9.5, 0, 0, 7); ctx.fill();
      ctx.fillStyle = shade(leaf, 1.18);
      ctx.beginPath(); ctx.ellipse(tx - 2.5, ty - h - 6, 4.5, 4.5, 0, 0, 7); ctx.fill();
    } else {
      ctx.strokeStyle = '#5a4a38'; ctx.lineWidth = 1.2;
      for (const a of [-0.7, 0.7, -1.2]) {
        ctx.beginPath(); ctx.moveTo(tx, ty - h + 3);
        ctx.lineTo(tx + Math.sin(a) * 8, ty - h - 5); ctx.stroke();
      }
    }
  }
}

/* ------------------------------------------------------------------ grain */
/* What makes a painted surface read as a material is not the lines on it, it
 * is that no two square inches of it are the same colour. Canvas cannot do
 * that per pixel at thirty frames a second, so the noise is baked once into a
 * small tiling bitmap and used as a fill pattern -- which costs one composite
 * per face instead of a hundred thousand arithmetic operations.
 *
 * Three weights, because thatch wants a coarse tooth, plaster a fine one and
 * stone something between. */
let GRAIN = {}, GRAIN_OWNER = null;
function grain(step, strength) {
  // A CanvasPattern belongs to the context that made it. The ground is baked
  // on a second context, so the cache has to know which one it is holding.
  if (GRAIN_OWNER !== ctx) { GRAIN = {}; GRAIN_OWNER = ctx; }
  const key = step + ':' + strength;
  if (GRAIN[key]) return GRAIN[key];
  const n = 64, c = document.createElement('canvas');
  c.width = c.height = n;
  const g = c.getContext('2d');
  const img = g.createImageData(n, n);
  let s = 1;
  for (let y = 0; y < n; y += step) {
    for (let x = 0; x < n; x += step) {
      // xorshift: deterministic, and the same tooth every time the page loads.
      s ^= s << 13; s ^= s >>> 17; s ^= s << 5;
      const v = 128 + ((s & 255) - 128) * strength;
      for (let dy = 0; dy < step; dy++) {
        for (let dx = 0; dx < step; dx++) {
          const i = ((y + dy) * n + (x + dx)) * 4;
          if (i >= img.data.length) continue;
          img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
          img.data[i + 3] = 255;
        }
      }
    }
  }
  g.putImageData(img, 0, 0);
  GRAIN[key] = ctx.createPattern(c, 'repeat');
  return GRAIN[key];
}

/* How close the eye is. Grain, individual tiles and rubble coursing are all
 * invisible below about three-quarter zoom and all of them cost real time, so
 * they are simply not drawn there. This is not a compromise: a roof drawn with
 * sixty-three separate tiles at a zoom where each one is a pixel and a half is
 * worse than one drawn with seven courses, as well as slower. */
function near() { return camera.zoom >= 1.25; }

/* And what is actually in front of the eye. Fifty roofs of sixty-three tiles
 * each is nine thousand filled paths a frame, and at two-and-a-bit zoom four
 * fifths of them are off the side of the screen. Culling is what pays for the
 * detail: far out there is less of it per building, close in there are fewer
 * buildings. */
let clipBox = null;
function onScreen(sx, sy, pad) {
  if (!clipBox) return true;
  return sx > clipBox[0] - pad && sx < clipBox[2] + pad
      && sy > clipBox[1] - pad && sy < clipBox[3] + pad;
}
function setClip(w, h) {
  const z = camera.zoom;
  const ox = (plan.w - plan.h) * TW / 4, oy = (plan.w + plan.h) * TH / 4;
  clipBox = [(-w / 2 - camera.x) / z + ox, (-h / 2 - camera.y) / z + oy,
             (w / 2 - camera.x) / z + ox, (h / 2 - camera.y) / z + oy];
}

/* Lay grain over whatever has just been painted, inside the given outline.
 * `overlay` keeps the hue and moves only the value, which is what weathering
 * does to a real surface. */
function tooth(pts, step, strength, alpha) {
  if (!baking && !near()) return;
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
  ctx.clip();
  ctx.globalCompositeOperation = 'overlay';
  ctx.globalAlpha = alpha;
  ctx.fillStyle = grain(step, strength);
  const x0 = Math.min(...pts.map(p => p[0])) - 64;
  const y0 = Math.min(...pts.map(p => p[1])) - 64;
  const x1 = Math.max(...pts.map(p => p[0])) + 64;
  const y1 = Math.max(...pts.map(p => p[1])) + 64;
  ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
  ctx.restore();
}

/* Points along the edge a->b, used by every roof and course below. */
function along(a, b, f) {
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
}

/* A stepped gable, drawn as courses climbing the rake of the roof. `eave` and
 * `apex` are the two ends of the slope; `side` is which way the steps face. */
function drawCrowSteps(eave, apex, low, st, side) {
  const n = 5;
  const brick = shade(st.c, 1.06);
  for (let i = 0; i < n; i++) {
    const f0 = i / n, f1 = (i + 1) / n;
    const a = along(low, apex, f0), b = along(low, apex, f1);
    const rise = 3.2;
    poly([[a[0], a[1]], [b[0], a[1] - rise * 0.2],
          [b[0], b[1] - rise], [a[0], b[1] - rise * 0.4]], brick);
    ctx.strokeStyle = 'rgba(0,0,0,.22)'; ctx.lineWidth = 0.8;
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1] - rise);
    ctx.stroke();
  }
  void eave; void side;
}

/* ----------------------------------------------------------------- masonry */
function wallFace(pts, colour, kind) {
  poly(pts, colour);
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath(); ctx.clip();
  const x0 = Math.min(...pts.map(p => p[0])), x1 = Math.max(...pts.map(p => p[0]));
  const y0 = Math.min(...pts.map(p => p[1])), y1 = Math.max(...pts.map(p => p[1]));
  const slope = 0.16;                 // the rake of a course across this face
  if (kind === 'stone') {
    // Rubble, not graph paper. Courses of uneven height, blocks of uneven
    // width within them, and each block a shade of its own -- which is the
    // whole difference between a wall and a fill with lines ruled on it.
    let row = 0;
    const one = !baking && !near();       // far off: courses, not blocks
    for (let yy = y0 - 4; yy < y1 + 8; row++) {
      const hgt = 5 + (row * 37 % 5);
      let xx = x0 - 20 + (row * 53 % 17);
      while (xx < x1 + 8) {
        const wid = one ? (x1 - x0 + 40) : 11 + ((row * 31 + xx) % 13);
        const lift = (xx - x0) * slope;
        const v = 0.90 + ((row * 71 + xx * 13) % 100) / 420;
        poly([[xx, yy + lift], [xx + wid, yy + lift + wid * slope],
              [xx + wid, yy + hgt + lift + wid * slope], [xx, yy + hgt + lift]],
             shade(colour, v));
        xx += wid + 1.1;
      }
      yy += hgt + 1.1;
    }
    // Mortar catches the light; the joints under each block do not.
    ctx.strokeStyle = 'rgba(0,0,0,.16)'; ctx.lineWidth = 0.9;
    for (let yy = y0; yy < y1; yy += 6.1) {
      ctx.beginPath(); ctx.moveTo(x0, yy); ctx.lineTo(x1, yy + (x1 - x0) * slope);
      ctx.stroke();
    }
    // Damp at the foot of the wall, where a stone wall is always darkest.
    if (!baking && !near()) { ctx.restore(); return; }
    const damp = ctx.createLinearGradient(0, y1 - (y1 - y0) * 0.42, 0, y1);
    damp.addColorStop(0, 'rgba(30,26,20,0)');
    damp.addColorStop(1, 'rgba(30,26,20,.30)');
    ctx.fillStyle = damp; ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
  } else if (kind === 'timber') {
    // Half-timbering: daub panels between a real frame. A sill, a top plate,
    // studs between them and a brace in the end bays, which is how the frame
    // actually stood up and is what the eye recognises it by.
    const mid = (y0 + y1) / 2;
    ctx.fillStyle = 'rgba(226,214,188,.40)';        // lime daub, not timber
    ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
    ctx.strokeStyle = 'rgba(58,40,24,.80)';
    ctx.lineWidth = 2.4; ctx.lineCap = 'round';
    for (const yy of [y0 + 2.5, mid, y1 - 2.5]) {
      ctx.beginPath(); ctx.moveTo(x0, yy); ctx.lineTo(x1, yy + (x1 - x0) * slope * 0.5);
      ctx.stroke();
    }
    ctx.lineWidth = 2;
    let i = 0;
    for (let xx = x0 + 5; xx < x1; xx += 11, i++) {
      ctx.beginPath(); ctx.moveTo(xx, y0); ctx.lineTo(xx + 2, y1); ctx.stroke();
      if (i % 3 === 1) {                              // a brace every third bay
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.moveTo(xx, mid + (xx - x0) * slope * 0.5);
        ctx.lineTo(xx + 9, y1);
        ctx.stroke();
        ctx.lineWidth = 2;
      }
    }
    ctx.lineCap = 'butt';
  } else if (kind === 'brick') {
    // Brick is regular where rubble is not: that is the whole visual
    // difference, and it is why a brick town reads as a richer one.
    let row = 0;
    for (let yy = y0 - 3; yy < y1 + 6; yy += 4.2, row++) {
      let xx = x0 - 16 + (row % 2) * 5.5;
      while (xx < x1 + 6) {
        const lift = (xx - x0) * slope;
        const v = 0.93 + ((row * 29 + xx * 7) % 100) / 700;
        poly([[xx, yy + lift], [xx + 10, yy + lift + 10 * slope],
              [xx + 10, yy + 3.4 + lift + 10 * slope], [xx, yy + 3.4 + lift]],
             shade(colour, v));
        xx += 11;
      }
    }
    if (baking || near()) {
      const damp = ctx.createLinearGradient(0, y1 - (y1 - y0) * 0.4, 0, y1);
      damp.addColorStop(0, 'rgba(26,20,18,0)');
      damp.addColorStop(1, 'rgba(26,20,18,.26)');
      ctx.fillStyle = damp; ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
    }
  } else if (kind === 'plank') {
    // Sawn boards: a seam every few inches and a grain running with them.
    ctx.strokeStyle = 'rgba(48,34,20,.45)'; ctx.lineWidth = 1;
    for (let xx = x0 + 4; xx < x1; xx += 7) {
      ctx.beginPath(); ctx.moveTo(xx, y0); ctx.lineTo(xx + 2, y1); ctx.stroke();
      ctx.strokeStyle = 'rgba(48,34,20,.16)';
      ctx.beginPath(); ctx.moveTo(xx + 3.5, y0); ctx.lineTo(xx + 5, y1); ctx.stroke();
      ctx.strokeStyle = 'rgba(48,34,20,.45)';
    }
  }
  ctx.restore();
  tooth(pts, kind === 'stone' ? 2 : 1, kind === 'timber' ? 0.22 : 0.34,
        kind === 'stone' || kind === 'brick' ? 0.30 : 0.20);
}

/* Thatch is a deep material: two feet of straw with the light only reaching
 * the top inch of it. Five ruled arcs read as a striped tarpaulin. What it
 * wants is many fine courses, each one slightly ragged, a dark eave where the
 * overhang shades itself, and a bound ridge along the top. */
function thatch(a, b, c, d, colour) {
  poly([a, b, c, d], colour);
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(a[0], a[1]);
  for (const q of [b, c, d]) ctx.lineTo(q[0], q[1]);
  ctx.closePath(); ctx.clip();
  const N = near() ? 13 : 7;
  ctx.lineWidth = 1;
  for (let i = 1; i < N; i++) {
    const f = i / N;
    const p1 = along(a, d, f), p2 = along(b, c, f);
    // Straw laid in courses: each course is lighter at its head and shadowed
    // where the next one laps over it.
    ctx.strokeStyle = shade(colour, 1.06 - 0.02 * (i % 3));
    ctx.beginPath(); ctx.moveTo(p1[0], p1[1]);
    ctx.quadraticCurveTo((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 1.8,
                         p2[0], p2[1]);
    ctx.stroke();
    ctx.strokeStyle = shade(colour, 0.80);
    ctx.beginPath(); ctx.moveTo(p1[0], p1[1] + 1.1);
    ctx.quadraticCurveTo((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 0.7,
                         p2[0], p2[1] + 1.1);
    ctx.stroke();
  }
  // The stalks themselves, combed down the fall of the roof.
  ctx.strokeStyle = shade(colour, 0.86);
  ctx.lineWidth = 0.6;
  for (let j = 1; near() && j < 16; j++) {
    const g = j / 16;
    const t1 = along(a, b, g), t2 = along(d, c, g);
    ctx.beginPath(); ctx.moveTo(t1[0], t1[1]); ctx.lineTo(t2[0], t2[1]);
    ctx.stroke();
  }
  // A bound ridge at the head, and the shadow the overhang throws on itself.
  ctx.strokeStyle = shade(colour, 0.72); ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(a[0], a[1] + 1); ctx.lineTo(b[0], b[1] + 1);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(28,22,14,.34)'; ctx.lineWidth = 2.4;
  ctx.beginPath(); ctx.moveTo(d[0], d[1] - 0.6); ctx.lineTo(c[0], c[1] - 0.6);
  ctx.stroke();
  ctx.restore();
  tooth([a, b, c, d], 2, 0.45, 0.34);
}

/* Tiles are objects, not stripes: every one of them is a separate fired thing
 * that came out of the kiln a slightly different colour and has been on that
 * roof for thirty years. */
function tiles(a, b, c, d, colour) {
  poly([a, b, c, d], colour);
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(a[0], a[1]);
  for (const q of [b, c, d]) ctx.lineTo(q[0], q[1]);
  ctx.closePath(); ctx.clip();
  const ROWS = near() ? 7 : 5, COLS = near() ? 9 : 1;
  for (let i = 0; i < ROWS; i++) {
    const f0 = i / ROWS, f1 = (i + 1) / ROWS;
    const l0 = along(a, d, f0), r0 = along(b, c, f0);
    const l1 = along(a, d, f1), r1 = along(b, c, f1);
    for (let j = 0; j < COLS; j++) {
      // Every other course offset by half a tile, as they are laid.
      const g0 = (j + (i % 2) * 0.5) / COLS, g1 = (j + 1 + (i % 2) * 0.5) / COLS;
      if (g0 >= 1) continue;
      const h1 = Math.min(1, g1);
      const v = 0.88 + ((i * 17 + j * 41) % 100) / 330;
      poly([along(l0, r0, g0), along(l0, r0, h1),
            along(l1, r1, h1), along(l1, r1, g0)], shade(colour, v));
    }
    // The lap: every course throws a line of shade on the one below it.
    ctx.strokeStyle = 'rgba(0,0,0,.30)'; ctx.lineWidth = 1.1;
    ctx.beginPath(); ctx.moveTo(l1[0], l1[1]); ctx.lineTo(r1[0], r1[1]);
    ctx.stroke();
  }
  // Moss gathers at the eave, where the roof stays wet longest.
  if (!baking && !near()) {
    ctx.strokeStyle = shade(colour, 0.74); ctx.lineWidth = 2.6;
    ctx.beginPath(); ctx.moveTo(a[0], a[1] + 0.8); ctx.lineTo(b[0], b[1] + 0.8);
    ctx.stroke();
    ctx.restore();
    return;
  }
  const moss = ctx.createLinearGradient(0, (a[1] + d[1]) / 2, 0, (d[1] + c[1]) / 2 + 4);
  moss.addColorStop(0, 'rgba(96,110,66,0)');
  moss.addColorStop(1, 'rgba(96,110,66,.20)');
  ctx.fillStyle = moss;
  ctx.fillRect(Math.min(a[0], d[0]) - 4, Math.min(a[1], b[1]) - 4,
               Math.abs(b[0] - a[0]) + Math.abs(c[0] - d[0]) + 8,
               Math.abs(c[1] - a[1]) + 12);
  // A ridge tile along the top.
  ctx.strokeStyle = shade(colour, 0.74); ctx.lineWidth = 2.6;
  ctx.beginPath(); ctx.moveTo(a[0], a[1] + 0.8); ctx.lineTo(b[0], b[1] + 0.8);
  ctx.stroke();
  ctx.restore();
  tooth([a, b, c, d], 1, 0.30, 0.22);
}

/* --------------------------------------------------------------- buildings */
function drawBuilding(b, t) {
  const st = styleOf(b.key);
  const [sx, sy] = iso(b.x, b.y);
  if (st.roof === 'trees') { drawTrees(b.x, b.y); return; }

  const w = st.w / 2, d = (st.w / 2) * (TH / TW);
  const h = 22 * st.s;
  if (!b.complete) { drawScaffold(sx, sy, w, d, h); return; }

  castShadow(sx, sy, w, d, h + 12 * st.s);

  if (st.wall === 'pit') { drawPit(sx, sy, w, d, st); return; }

  const T = [sx, sy - d - h], L = [sx - w, sy - h];
  const R = [sx + w, sy - h], B = [sx, sy + d - h];
  const bl = [sx - w, sy], bb = [sx, sy + d], br = [sx + w, sy];

  wallFace([L, bl, bb, B], shade(st.c, 0.62), st.wall);      // south-west face
  wallFace([B, bb, br, R], shade(st.c, 0.80), st.wall);      // south-east face
  drawOpenings(sx, sy, w, d, h, st, b);

  const rise = (st.roof === 'tile' ? 13 : st.roof === 'thatch' ? 17 : 9)
             * (st.pitch || 1);
  const M1 = [sx - w / 2, sy - d / 2 - h - rise];
  const M2 = [sx + w / 2, sy + d / 2 - h - rise];

  if (st.roof === 'thatch' || st.roof === 'tile' || st.roof === 'plankroof') {
    let colour = st.roof === 'thatch' ? '#b8994f'
      : st.roof === 'tile' ? '#8c4a35' : '#7d6242';
    if (st.roof_tint) colour = mix(colour, st.roof_tint, st.roof_by);
    if (st.gable === 'hipped') {
      // Four slopes and no gable at all: a low wide roof that sheds wind in
      // every direction, which is why the chalk country builds them.
      const apex1 = [sx - w * 0.34, sy - d * 0.34 - h - rise * 0.72];
      const apex2 = [sx + w * 0.34, sy + d * 0.34 - h - rise * 0.72];
      poly([T, L, apex1], shade(colour, 0.86));
      poly([R, B, apex2], shade(colour, 0.70));
      if (st.roof === 'thatch') {
        thatch(T, apex1, apex2, R, shade(colour, 1.05));
        thatch(L, apex1, apex2, B, shade(colour, 0.78));
      } else {
        tiles(T, apex1, apex2, R, shade(colour, 1.05));
        tiles(L, apex1, apex2, B, shade(colour, 0.76));
      }
      ctx.strokeStyle = shade(colour, 0.6); ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(apex1[0], apex1[1]); ctx.lineTo(apex2[0], apex2[1]);
      ctx.stroke();
    } else {
      poly([T, M1, L], shade(colour, 0.68));                  // gable ends
      poly([R, M2, B], shade(colour, 0.68));
      if (st.gable === 'stepped') {
        // Crow steps: the gable carried up past the roof in courses, so the
        // brickwork can be finished without a bargeboard. The one silhouette
        // in this game you can name from the far side of the map.
        drawCrowSteps(T, M1, L, st, 1);
        drawCrowSteps(R, M2, B, st, -1);
      }
      if (st.roof === 'thatch') {
        thatch(T, M1, M2, R, shade(colour, 1.05));
        thatch(L, M1, M2, B, shade(colour, 0.78));
      } else {
        tiles(T, M1, M2, R, shade(colour, 1.05));
        tiles(L, M1, M2, B, shade(colour, 0.76));
      }
      // The ridge, and the overhang that stops it looking like a wedge.
      ctx.strokeStyle = shade(colour, 0.6); ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(M1[0], M1[1]); ctx.lineTo(M2[0], M2[1]);
      ctx.stroke();
    }
  } else if (st.roof === 'cone' || st.roof === 'spire') {
    const apex = [sx, sy - d - h - (st.roof === 'spire' ? 44 : 15) * st.s];
    const colour = st.roof === 'spire' ? '#6a6f74' : '#8a6a4a';
    poly([L, T, apex], shade(colour, 1.06));
    poly([T, R, apex], shade(colour, 0.9));
    poly([R, B, apex], shade(colour, 0.72));
    poly([B, L, apex], shade(colour, 0.82));
    if (st.roof === 'spire') {
      ctx.strokeStyle = '#d9c98d'; ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.moveTo(apex[0], apex[1]); ctx.lineTo(apex[0], apex[1] - 9);
      ctx.moveTo(apex[0] - 3.5, apex[1] - 6); ctx.lineTo(apex[0] + 3.5, apex[1] - 6);
      ctx.stroke();
    }
  } else if (st.roof === 'mound') {
    ctx.fillStyle = '#3f342a';
    ctx.beginPath(); ctx.ellipse(sx, sy - h * 0.4, w, d + h * 0.5, 0, Math.PI, 0);
    ctx.fill();
  } else if (st.roof === 'awning') {
    poly([T, L, B, R], 'rgba(168,65,47,.9)');
    ctx.strokeStyle = 'rgba(255,255,255,.3)'; ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
      const f = i / 4;
      ctx.beginPath();
      ctx.moveTo(L[0] + (T[0] - L[0]) * f, L[1] + (T[1] - L[1]) * f);
      ctx.lineTo(B[0] + (R[0] - B[0]) * f, B[1] + (R[1] - B[1]) * f);
      ctx.stroke();
    }
  } else {                                   // flat top: the keep, the quarry
    poly([T, R, B, L], shade(st.c, 1.12));
    if (b.key === 'keep') {
      drawBattlements(sx, sy, w, d, h, st.c);
      drawTower(sx - w * 0.52, sy + d * 0.3, w * 0.42, d * 0.42, h * 1.55, st.c, t);
    }
  }

  if (b.key === 'mill') drawSails(sx, sy - d - h - 22 * st.s, b.running ? t : 0);
  if (st.oven && b.running) puff(sx + w * 0.35, sy - d - h - rise - 4, t);
  if (b.burning) burn(sx, sy - h * 0.5, t);
  if (b.idle && !b.burning) {
    ctx.fillStyle = 'rgba(20,17,13,.30)';
    poly([T, R, B, L], 'rgba(20,17,13,.22)');
  }
}

function drawOpenings(sx, sy, w, d, h, st, b) {
  if (st.wall === 'open' || st.wall === 'earth') return;
  // A door on the south-east face, and a lit window if anyone is working.
  const dw = Math.min(9, w * 0.3), dh = Math.min(13, h * 0.55);
  const dx = sx + w * 0.42, dy = sy + d * 0.42;
  poly([[dx - dw / 2, dy - dh], [dx + dw / 2, dy - dh + dw * 0.3],
        [dx + dw / 2, dy + dw * 0.3], [dx - dw / 2, dy]], 'rgba(38,26,16,.85)');
  if (b && (b.running || st.oven)) {
    // A window is a hole in a wall by day and a light by night, so the glow
    // is set aside and drawn after the dark is laid down.
    glows.push({ x: sx - w * 0.34, y: sy + d * 0.12 - h * 0.55, r: 15,
                 a: b.running ? 0.34 : 0.16 });
    const lit = b.running ? 'rgba(255,206,110,.85)' : 'rgba(255,206,110,.25)';
    const wx = sx - w * 0.45, wy = sy - h * 0.55;
    poly([[wx - 3, wy - 5], [wx + 3, wy - 3.2], [wx + 3, wy + 2],
          [wx - 3, wy + 0.2]], lit);
  }
}

function drawSails(x, y, t) {
  const a0 = t * 0.9;
  ctx.strokeStyle = '#5c4a30'; ctx.lineWidth = 2;
  ctx.fillStyle = 'rgba(228,216,186,.86)';
  for (let i = 0; i < 4; i++) {
    const a = a0 + i * Math.PI / 2;
    const dx = Math.cos(a) * 21, dy = Math.sin(a) * 21 * 0.55;
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + dx, y + dy); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x + dx * 0.35, y + dy * 0.35);
    ctx.lineTo(x + dx, y + dy);
    ctx.lineTo(x + dx * 0.9 - dy * 0.22, y + dy * 0.9 + dx * 0.12);
    ctx.closePath(); ctx.fill();
  }
  ctx.fillStyle = '#4a3c28';
  ctx.beginPath(); ctx.arc(x, y, 2.6, 0, 7); ctx.fill();
}

function drawBattlements(sx, sy, w, d, h, colour) {
  const T = [sx, sy - d - h], L = [sx - w, sy - h];
  const R = [sx + w, sy - h], B = [sx, sy + d - h];
  ctx.fillStyle = shade(colour, 1.22);
  for (let i = 0; i < 4; i++) {
    const f = 0.12 + i * 0.25;
    for (const [a, b2] of [[T, R], [L, B], [L, T], [B, R]]) {
      const mx = a[0] + (b2[0] - a[0]) * f, my = a[1] + (b2[1] - a[1]) * f;
      ctx.fillRect(mx - 2.6, my - 6, 5.2, 6);
    }
  }
}

function drawTower(sx, sy, w, d, h, colour, t) {
  // The tower is what makes a keep read as a keep from across a field.
  const T = [sx, sy - d - h], L = [sx - w, sy - h];
  const R = [sx + w, sy - h], B = [sx, sy + d - h];
  wallFace([L, [sx - w, sy], [sx, sy + d], B], shade(colour, 0.58), 'stone');
  wallFace([B, [sx, sy + d], [sx + w, sy], R], shade(colour, 0.76), 'stone');
  poly([T, R, B, L], shade(colour, 1.16));
  ctx.fillStyle = shade(colour, 1.3);
  for (const [a, b2] of [[T, R], [L, B], [L, T], [B, R]]) {
    for (const f of [0.22, 0.62]) {
      const mx = a[0] + (b2[0] - a[0]) * f, my = a[1] + (b2[1] - a[1]) * f;
      ctx.fillRect(mx - 2.4, my - 6, 4.8, 6);
    }
  }
  const bx = sx, by = sy - d - h - 4;
  ctx.strokeStyle = '#5a4a34'; ctx.lineWidth = 1.8;
  ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx, by - 30); ctx.stroke();
  const wave = Math.sin(t * 2.2) * 3;
  poly([[bx, by - 30], [bx + 19 + wave, by - 25 + wave * 0.4],
        [bx + 17 + wave, by - 16], [bx, by - 18]], '#a8412f');
}

function drawPit(sx, sy, w, d, st) {
  poly([[sx, sy - d], [sx + w, sy], [sx, sy + d], [sx - w, sy]], shade(st.c, 0.7));
  poly([[sx, sy - d * 0.55], [sx + w * 0.6, sy], [sx, sy + d * 0.55],
        [sx - w * 0.6, sy]], shade(st.c, 0.45));
  ctx.fillStyle = shade(st.c, 1.1);
  for (let i = 0; i < 4; i++) {
    ctx.beginPath();
    ctx.ellipse(sx + (rnd(sx, sy, i) - 0.5) * w, sy + (rnd(sx, sy, i + 5) - 0.5) * d,
                3.4, 1.8, 0, 0, 7);
    ctx.fill();
  }
}

function drawScaffold(sx, sy, w, d, h) {
  ctx.strokeStyle = '#8a7450'; ctx.lineWidth = 1.6;
  const corners = [[sx - w, sy], [sx + w, sy], [sx, sy - d], [sx, sy + d]];
  for (const [cx, cy] of corners) {
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx, cy - h); ctx.stroke();
  }
  ctx.beginPath();
  ctx.moveTo(sx - w, sy - h * 0.6); ctx.lineTo(sx, sy - d - h * 0.6);
  ctx.lineTo(sx + w, sy - h * 0.6); ctx.lineTo(sx, sy + d - h * 0.6);
  ctx.closePath(); ctx.stroke();
  poly([[sx, sy - d], [sx + w, sy], [sx, sy + d], [sx - w, sy]],
       'rgba(150,120,80,.28)');
}

/* ------------------------------------------------------------------- walls */
function drawWall(w, t) {
  const [sx, sy] = iso(w.x, w.y);
  const hw = TW / 2, hd = TH / 2;
  const stone = w.kind !== 'timber';
  const colour = stone ? '#a2988a' : '#8a6a45';
  const h = w.kind === 'tower' ? 52 : w.kind === 'gate' ? 40 : 28;
  castShadow(sx, sy, hw * 0.92, hd * 0.92, h);
  if (w.kind === 'gap') return;

  const T = [sx, sy - hd - h], L = [sx - hw, sy - h];
  const R = [sx + hw, sy - h], B = [sx, sy + hd - h];
  wallFace([L, [sx - hw, sy], [sx, sy + hd], B], shade(colour, 0.62),
           stone ? 'stone' : 'plank');
  wallFace([B, [sx, sy + hd], [sx + hw, sy], R], shade(colour, 0.8),
           stone ? 'stone' : 'plank');
  poly([T, R, B, L], shade(colour, 1.1));
  if (stone) {
    // Merlons stand along the two outward edges of the wall-top diamond, so
    // they follow the wall instead of hovering over the middle of it.
    ctx.fillStyle = shade(colour, 1.1);
    for (let i = 0; i < 3; i++) {
      const f = 0.18 + i * 0.32;
      for (const [a, b2] of [[T, R], [L, B]]) {
        const mx = a[0] + (b2[0] - a[0]) * f, my = a[1] + (b2[1] - a[1]) * f;
        ctx.fillRect(mx - 2.5, my - 5.5, 5, 5.5);
      }
    }
  }
  if (w.kind === 'gate') {
    poly([[sx - 8, sy + hd - 2], [sx - 8, sy + hd - 20], [sx, sy + hd - 26],
          [sx + 8, sy + hd - 20], [sx + 8, sy + hd - 2]], 'rgba(30,20,12,.9)');
  }
}

/* ------------------------------------------------------------------- life */
/* One figure stands for fourteen souls, or six men on the wall, and the
 * interface says so. What each one is *doing* is read off the town rather
 * than invented: a worker walks the route between the roof he sleeps under
 * and the shed that is staffed today, somebody with no work stands in the
 * street, and the watch stands on the yards of wall that are really held --
 * so a wall you enclosed more ground with than you have men for looks thinly
 * held without anybody drawing a warning. */
function walkAlong(path, f) {
  if (!path || path.length < 2) return null;
  const span = (path.length - 1) * f;
  const i = Math.min(path.length - 2, Math.floor(span));
  const g = span - i;
  return [path[i].x + (path[i + 1].x - path[i].x) * g,
          path[i].y + (path[i + 1].y - path[i].y) * g];
}

/* Where each figure was drawn this frame, in the same space `buildingAt`
 * works in. A worker moves along his path every frame, so the only honest
 * hit target is the place he was actually painted -- computing it a second
 * time from the clock would be a second answer to the same question. */
const folkSpots = new Map();

/* Where each host was drawn, so one can be clicked. Same bargain as the
 * figures in the town: the thing that moved is only clickable where it was
 * actually painted. */
const hostSpots = new Map();

function drawFolk(f, i, t) {
  let wx = f.x, wy = f.y, bob = 0;
  if (f.kind === 'worker' && f.path && f.path.length > 1) {
    // Up the street and back again, each at their own pace.
    const cycle = (t * 0.06 + i * 0.17) % 2;
    const at = walkAlong(f.path, cycle < 1 ? cycle : 2 - cycle);
    if (at) { wx = at[0]; wy = at[1]; }
    bob = Math.abs(Math.sin(t * 3.1 + i)) * 1.6;
  } else if (f.kind === 'idle') {
    wx += Math.sin(t * 0.3 + i * 1.7) * 0.18;
    bob = Math.abs(Math.sin(t * 0.9 + i)) * 0.5;
  }
  const [sx, sy] = iso(wx, wy);
  const lift = f.kind === 'watch' ? 16 : 0;      // up on the wall-walk
  folkSpots.set(i, [sx, sy - lift]);
  ctx.fillStyle = 'rgba(0,0,0,.2)';
  ctx.beginPath(); ctx.ellipse(sx, sy + 1 - lift * 0.5, 3.4, 1.6, 0, 0, 7);
  ctx.fill();
  if (f.kind === 'watch') {
    // A spearman, facing out, shifting his weight the way a man does when
    // he has been standing on a wall since dawn.
    const sway = Math.sin(t * 0.5 + i * 2.3) * 0.6;
    ctx.strokeStyle = '#5c5e63'; ctx.lineWidth = 3.2;
    ctx.beginPath(); ctx.moveTo(sx + sway, sy - lift);
    ctx.lineTo(sx + sway, sy - 9 - lift); ctx.stroke();
    ctx.strokeStyle = '#8a7a58'; ctx.lineWidth = 1.1;
    ctx.beginPath(); ctx.moveTo(sx + sway + 3, sy - 2 - lift);
    ctx.lineTo(sx + sway + 3, sy - 17 - lift); ctx.stroke();
    ctx.fillStyle = '#b9b2a0';
    ctx.beginPath(); ctx.arc(sx + sway, sy - 11.6 - lift, 2.6, 0, 7); ctx.fill();
    return;
  }
  if (f.kind === 'kin') {
    // One of yours, and the only figure on the board that is one person
    // rather than fourteen. Marked so you can find them to click: a ring on
    // the ground, a taller stance, and the house's gold instead of a coat
    // the colour of mud.
    const pulse = 0.8 + Math.sin(t * 1.6 + i) * 0.14;
    ctx.strokeStyle = `rgba(201,162,39,${0.3 * pulse})`;
    ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.ellipse(sx, sy + 1, 6.4, 3.1, 0, 0, 7); ctx.stroke();
    ctx.strokeStyle = '#8a6a2e'; ctx.lineWidth = 3.6;
    ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(sx, sy - 11); ctx.stroke();
    ctx.strokeStyle = '#c9a227'; ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(sx - 2.6, sy - 8); ctx.lineTo(sx + 2.6, sy - 8);
    ctx.stroke();
    ctx.fillStyle = '#e8dcc0';
    ctx.beginPath(); ctx.arc(sx, sy - 13.8, 2.9, 0, 7); ctx.fill();
    return;
  }
  const coat = f.kind === 'idle'
    ? ['#6a6450', '#5c5442', '#6f6152', '#585044'][i % 4]
    : ['#7a5a3c', '#8a6a4a', '#7d6a44', '#8f6d4e'][i % 4];
  ctx.strokeStyle = coat; ctx.lineWidth = 3.2;
  ctx.beginPath(); ctx.moveTo(sx, sy - bob); ctx.lineTo(sx, sy - 9 - bob); ctx.stroke();
  ctx.fillStyle = '#d8c9a8';
  ctx.beginPath(); ctx.arc(sx, sy - 11.6 - bob, 2.7, 0, 7); ctx.fill();
}

/* A sack has a colour. Grain is pale, iron is dark, cloth is dyed -- so you
 * can read what the town is moving without being told. */
const SACK = {
  wheat: '#d8bf6a', flour: '#e6dcc0', bread: '#b98545', apples: '#a8432f',
  cheese: '#e0cf86', wool: '#e3dbcb', cloth: '#8a5f86', wood: '#7a5c38',
  planks: '#a8834e', stone: '#9a968b', clay: '#9a6742', charcoal: '#33302c',
  iron_ore: '#6f5a4a', iron: '#5d5a58', salt: '#eae4d6', hops: '#7f9a45',
  ale: '#b07a2c', pottery: '#a8613c', tools: '#7d7468', weapons: '#6a6e74',
  armour: '#7a7e86', spears: '#8a6a44', bows: '#86603a',
};

function haulAt(h, i, t, at) {
  // Where the carrier has got to this instant, in tiles, following the street
  // route the layout worked out. The scene is painted back to front, so this
  // has to be the sort key -- using the midpoint of the two buildings put
  // every carrier at the wrong depth and buried them all.
  const a = at[h.frm], b = at[h.to];
  if (!a || !b) return null;
  const way = (h.path && h.path.length > 1)
    ? h.path : [{ x: a.x, y: a.y }, { x: b.x, y: b.y }];
  const legs = [];
  let total = 0;
  for (let k = 1; k < way.length; k++) {
    const d = Math.hypot(way[k].x - way[k - 1].x, way[k].y - way[k - 1].y);
    legs.push(d); total += d;
  }
  if (total <= 0) return { x: a.x, y: a.y, out: true, back: false };
  const period = total / 1.5 + 1.2;
  const phase = ((t + i * 1.7) % (period * 2)) / period;
  const out = phase < 1;
  let want = (out ? phase : 2 - phase) * total;
  for (let k = 0; k < legs.length; k++) {
    if (want <= legs[k] || k === legs.length - 1) {
      const f = legs[k] > 0 ? Math.min(1, want / legs[k]) : 0;
      const p0 = way[k], p1 = way[k + 1];
      return { x: p0.x + (p1.x - p0.x) * f, y: p0.y + (p1.y - p0.y) * f,
               out, back: (out ? p1.x - p0.x : p0.x - p1.x) < 0 };
    }
    want -= legs[k];
  }
  return { x: b.x, y: b.y, out, back: false };
}

function drawHaul(h, i, t, at, pos) {
  const p = pos || haulAt(h, i, t, at);
  if (!p) return;
  const [x, y] = iso(p.x, p.y);
  const out = p.out;
  const bob = Math.abs(Math.sin(t * 4.2 + i)) * 1.7;

  // Big enough to be a person rather than a dot. This is the thing people
  // remember about the game it is borrowed from; drawn small it reads as
  // dust, and the whole point is that you can see what is being carried.
  const step = Math.sin(t * 5.4 + i * 2.1);
  ctx.fillStyle = 'rgba(0,0,0,.26)';
  ctx.beginPath(); ctx.ellipse(x, y + 1, 5, 2.3, 0, 0, 7); ctx.fill();
  ctx.strokeStyle = '#4a3a26'; ctx.lineWidth = 2.4;
  ctx.beginPath();
  ctx.moveTo(x, y - 6 - bob); ctx.lineTo(x - 2.4 * step, y - bob);
  ctx.moveTo(x, y - 6 - bob); ctx.lineTo(x + 2.4 * step, y - bob);
  ctx.stroke();
  const coat = ['#7a5a3c', '#6a6450', '#8a6a4a', '#5c5442'][i % 4];
  poly([[x - 3.4, y - 6 - bob], [x + 3.4, y - 6 - bob],
        [x + 2.6, y - 14 - bob], [x - 2.6, y - 14 - bob]], coat);
  ctx.fillStyle = '#e6d8b6';
  ctx.beginPath(); ctx.arc(x, y - 16.6 - bob, 3.3, 0, 7); ctx.fill();
  if (out) {
    const sx2 = x + (p.back ? 6.4 : -6.4);
    ctx.strokeStyle = coat; ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, y - 12 - bob); ctx.lineTo(sx2, y - 11 - bob); ctx.stroke();
    ctx.fillStyle = SACK[h.good] || '#b09a6a';
    ctx.beginPath();
    ctx.ellipse(sx2, y - 9 - bob, 4.6, 5.6, 0, 0, 7);
    ctx.fill();
    ctx.strokeStyle = 'rgba(40,30,16,.45)'; ctx.lineWidth = 1; ctx.stroke();
    ctx.strokeStyle = 'rgba(40,30,16,.55)'; ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(sx2 - 2, y - 14 - bob); ctx.lineTo(sx2 + 2, y - 14 - bob);
    ctx.stroke();
  }
}

function puff(x, y, t) {
  if (!STILL && Math.random() < 0.12) {
    smoke.push({ x, y, born: t, drift: Math.random() - 0.5 });
  }
}
function burn(x, y, t) {
  if (!STILL && Math.random() < 0.55) {
    flames.push({ x: x + (Math.random() - 0.5) * 16, y, born: t });
    smoke.push({ x, y: y - 10, born: t, drift: Math.random() - 0.5, dark: true });
  }
}
function drawEffects(t) {
  smoke = smoke.filter(s => t - s.born < 3.4);
  for (const s of smoke) {
    const age = (t - s.born) / 3.4;
    ctx.globalAlpha = (1 - age) * (s.dark ? 0.5 : 0.34);
    ctx.fillStyle = s.dark ? '#3a3128' : '#d9d2c4';
    ctx.beginPath();
    ctx.arc(s.x + s.drift * age * 26, s.y - age * 44, 2.5 + age * 11, 0, 7);
    ctx.fill();
  }
  flames = flames.filter(f => t - f.born < 0.55);
  for (const f of flames) {
    const age = (t - f.born) / 0.55;
    ctx.globalAlpha = 1 - age;
    ctx.fillStyle = age < 0.5 ? '#ffca4a' : '#e0632a';
    ctx.beginPath();
    ctx.ellipse(f.x, f.y - age * 16, 4 - age * 2.5, 8 - age * 4, 0, 0, 7);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

/* Dawn, day, dusk, night. The sky is three stops rather than two, because the
 * band of warm light along the horizon at either end of a day is the whole
 * difference between a time of day and a brightness setting. */
const NIGHT_SKY = ['#0d1830', '#1b2b47'];
const DAWN_SKY = ['#2e4a72', '#e9a367'];
const DUSK_SKY = ['#3a3560', '#d97a4e'];

function skyStops(s, p) {
  const top = rgbOf(p.sky[0]), bottom = rgbOf(p.sky[1]);
  let a = top, b = bottom;
  if (s.warm > 0) {
    const warm = s.up >= 0 || s.p < 0.5 ? DAWN_SKY : DUSK_SKY;
    a = rgbOf(mix(`rgb(${a})`, warm[0], s.warm * 0.85));
    b = rgbOf(mix(`rgb(${b})`, warm[1], s.warm * 0.9));
  }
  if (s.night > 0) {
    a = rgbOf(mix(`rgb(${a})`, NIGHT_SKY[0], s.night));
    b = rgbOf(mix(`rgb(${b})`, NIGHT_SKY[1], s.night));
  }
  return [`rgb(${a})`, `rgb(${b})`];
}

function drawSky(w, h, t) {
  const p = pal(), s = sun();
  const [a, b] = skyStops(s, p);
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, a); g.addColorStop(1, b);
  ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);

  // Stars, where the sky is dark enough to hold them. A fixed field, so they
  // are the same stars every night, which is the only thing stars ever do.
  if (s.night > 0.05) {
    ctx.globalAlpha = s.night * 0.9;
    ctx.fillStyle = '#e8eef8';
    for (let i = 0; i < 70; i++) {
      const x = rnd(i, 3, 11) * w, y = rnd(i, 7, 13) * h * 0.55;
      const tw = 0.55 + 0.45 * Math.sin(t * 1.7 + i);
      ctx.globalAlpha = s.night * tw * 0.85;
      ctx.beginPath(); ctx.arc(x, y, 0.6 + rnd(i, 5, 17) * 0.9, 0, 7); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // The sun, and the moon on the other side of the same wheel. The month sets
  // how far north it rides; the hour sets where along the arc it is.
  const season = ((state ? state.month : 6) - 1) / 12;
  // High enough to clear the land at the top of the view for most of the
  // day: a sun that spends noon behind a wheat field is not a sun.
  const arc = x => [w * (0.06 + 0.88 * x),
                    h * (0.50 - 0.44 * Math.sin(x * Math.PI)
                         - 0.05 * Math.sin(season * Math.PI * 2))];
  if (s.up > -0.12) {
    const [sx, sy] = arc(s.p * 2 <= 1 ? s.p * 2 : s.p * 2 - 1);
    const halo = ctx.createRadialGradient(sx, sy, 3, sx, sy, 110);
    const core = s.warm > 0.25 ? '#ffd9a0' : p.sun;
    halo.addColorStop(0, core);
    halo.addColorStop(0.10, core);
    halo.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.globalAlpha = 0.55 + 0.45 * s.alt;
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(sx, sy, 110, 0, 7); ctx.fill();
    ctx.globalAlpha = 1;
  } else {
    const [mx, my] = arc((s.p - 0.5) * 2);
    ctx.globalAlpha = Math.min(1, s.night * 1.2);
    ctx.fillStyle = '#e6ecf6';
    ctx.beginPath(); ctx.arc(mx, my, 13, 0, 7); ctx.fill();
    ctx.fillStyle = 'rgba(190,205,228,.55)';
    ctx.beginPath(); ctx.arc(mx - 4, my - 3, 3.2, 0, 7); ctx.fill();
    ctx.beginPath(); ctx.arc(mx + 3, my + 4, 2.2, 0, 7); ctx.fill();
    ctx.globalAlpha = 1;
  }

  // Cloud, lit from whichever side the sun is on and unlit at night.
  const bright = 0.40 * (1 - s.night * 0.75);
  for (let i = 0; i < 5; i++) {
    const cx = ((i * 331 + t * (7 + i * 2)) % (w + 340)) - 170;
    const cy = 40 + i * 33 + Math.sin(i) * 12;
    ctx.fillStyle = s.warm > 0.2
      ? `rgba(255,${Math.round(214 - 40 * s.warm)},190,${bright + 0.1})`
      : `rgba(255,255,255,${bright})`;
    for (let k = 0; k < 3; k++) {
      ctx.beginPath();
      ctx.ellipse(cx + k * 27, cy + (k === 1 ? -7 : 0), 30 - k * 4, 13, 0, 0, 7);
      ctx.fill();
    }
  }
}

/* The light itself, laid over the world once everything solid is drawn.
 *
 * Doing it this way rather than tinting every fill is not a shortcut: it is
 * the only way the hundred or so colours in this file can stay readable as
 * colours -- thatch is #b8994f whatever the hour -- while still all obeying
 * one sun. Anything that is meant to shine rather than be lit is drawn after
 * this pass, which is exactly what makes a lit window worth having.
 */
function lightWash(w, h) {
  const s = sun();
  // Noon is white and does nothing. A low sun takes the blue out first, which
  // is why evening is warm; night takes the red out, which is why it is not.
  const low = Math.max(0, 1 - s.alt * 2.4) * (1 - s.night);
  const k = s.night;
  if (k < 0.01 && low < 0.01) return;
  const r = Math.round(255 - 188 * k - 16 * low);
  const g = Math.round(255 - 168 * k - 36 * low);
  const b = Math.round(255 - 104 * k - 68 * low);
  ctx.save();
  ctx.globalCompositeOperation = 'multiply';
  ctx.fillStyle = `rgb(${r},${g},${b})`;
  ctx.fillRect(0, 0, w, h);
  if (s.warm > 0.02) {
    // The last of the sun coming in sideways, over the top of everything.
    ctx.globalCompositeOperation = 'overlay';
    ctx.globalAlpha = 0.26 * s.warm;
    ctx.fillStyle = '#ff9040';
    ctx.fillRect(0, 0, w, h);
  }
  ctx.restore();
}

/* Everything that makes its own light, once the night has been laid over the
 * things that do not. Collected during the pass rather than drawn in it, so a
 * window can be behind a roof and still glow through the dark. */
function drawGlows() {
  const s = sun();
  const lit = Math.min(1, s.night * 1.25);
  if (lit > 0.02) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (const g of glows) {
      // Small and sharp. Thirty of these in a courtyard on a `lighter` pass
      // add up, and a town that glows white all over is not a lit town, it is
      // an overexposed one.
      const r = g.r * (0.8 + 0.35 * lit);
      const grad = ctx.createRadialGradient(g.x, g.y, 0, g.x, g.y, r);
      const a = (g.a || 0.5) * lit;
      grad.addColorStop(0, `rgba(255,208,128,${a.toFixed(3)})`);
      grad.addColorStop(0.35, `rgba(255,186,96,${(a * 0.34).toFixed(3)})`);
      grad.addColorStop(1, 'rgba(255,170,70,0)');
      ctx.fillStyle = grad;
      ctx.beginPath(); ctx.arc(g.x, g.y, r, 0, 7); ctx.fill();
    }
    ctx.restore();
  }
  glows = [];
}

function drawWeather(w, h, t) {
  if (!state) return;
  if (state.season === 'winter') {
    ctx.fillStyle = 'rgba(255,255,255,.75)';
    for (let i = 0; i < 90; i++) {
      const x = (i * 137.5 + t * 12 + Math.sin(t + i) * 26) % w;
      const y = (i * 91.3 + t * 46) % h;
      ctx.beginPath(); ctx.arc(x, y, 1.5, 0, 7); ctx.fill();
    }
  }
  // The vignette is what makes it read as a place rather than a diagram.
  // Enough to seat the picture on the page, not enough to muddy its corners.
  // At .55 it read as a smudge wherever it met the panel.
  const v = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.54,
                                     w / 2, h / 2, Math.max(w, h) * 0.82);
  v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(12,9,6,.34)');
  ctx.fillStyle = v; ctx.fillRect(0, 0, w, h);
}

/* ------------------------------------------------------------------ march
 * The other half of the game, and the half the town view cannot show. A town
 * is a picture of what you have; the march is a picture of what things are
 * worth somewhere else, which is the only reason any of the carts move.
 */
let world = null, mode = 'town', good = 'bread', mapCam = null;

function mapFit(w, h) {
  const xs = world.nodes.map(n => n.x), ys = world.nodes.map(n => n.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const pad = 96;
  const side = NARROW() ? 24 : 300, below = NARROW() ? 300 : 200;
  const k = Math.min((w - side - pad) / Math.max(1, x1 - x0),
                     (h - below - pad) / Math.max(1, y1 - y0));
  return { k, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, w, h,
           dx: NARROW() ? 0 : 90, dy: NARROW() ? -45 : -30 };
}
const mapXY = (n, f) => [f.w / 2 + f.dx + (n.x - f.cx) * f.k,
                         f.h / 2 + f.dy - (n.y - f.cy) * f.k];

function priceBand(nodes) {
  const vs = nodes.filter(n => n.price > 0).map(n => n.price).sort((a, b) => a - b);
  if (!vs.length) return null;
  return { lo: vs[0], mid: vs[Math.floor(vs.length / 2)], hi: vs[vs.length - 1] };
}
function priceColour(price, band) {
  if (!band || !price) return '#8a7f6a';
  // Cheap is green because cheap is where you buy. The scale is the median,
  // not the mean: one crashed market should not recolour the whole march.
  const f = price <= band.mid
    ? (price - band.lo) / Math.max(1e-6, band.mid - band.lo) * 0.5
    : 0.5 + (price - band.mid) / Math.max(1e-6, band.hi - band.mid) * 0.5;
  const r = Math.round(90 + 150 * f), g = Math.round(160 - 90 * f);
  return `rgb(${r},${g},70)`;
}

function drawMarch(w, h, t) {
  // Parchment, not grass: a map is a different kind of seeing from a view.
  const g0 = ctx.createLinearGradient(0, 0, w, h);
  g0.addColorStop(0, '#ded0ac'); g0.addColorStop(1, '#cdbb92');
  ctx.fillStyle = g0; ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = 'rgba(120,96,58,.05)';
  for (let i = 0; i < 240; i++) {
    const x = (i * 137.9 % w), y = ((i * 311.7) % h);
    ctx.beginPath(); ctx.arc(x, y, 1 + (i % 3), 0, 7); ctx.fill();
  }
  if (!world) return;
  const f = mapFit(w, h);
  const by = {}; for (const n of world.nodes) by[n.key] = n;
  const band = priceBand(world.nodes);

  // Every name on a real map is cut out of whatever it crosses. Without the
  // halo, a road or a route arc runs straight through the lettering.
  const label = (text, x, y, colour) => {
    ctx.lineWidth = 3.5; ctx.lineJoin = 'round';
    ctx.strokeStyle = 'rgba(230,219,189,.88)';
    ctx.strokeText(text, x, y);
    ctx.fillStyle = colour; ctx.fillText(text, x, y);
  };

  // Roads: each place joined to its nearest few, which is how roads happen.
  const trade = world.nodes.filter(n => n.kind !== 'shrine' && n.kind !== 'site');
  ctx.strokeStyle = 'rgba(92,70,40,.34)';
  ctx.lineWidth = 1.6; ctx.setLineDash([7, 5]);
  const drawn = new Set();
  for (const a of trade) {
    const near = trade.filter(b => b !== a)
      .sort((p, q) => Math.hypot(p.x - a.x, p.y - a.y) - Math.hypot(q.x - a.x, q.y - a.y))
      .slice(0, 3);
    for (const b of near) {
      const id = [a.key, b.key].sort().join('|');
      if (drawn.has(id)) continue;
      drawn.add(id);
      const [ax, ay] = mapXY(a, f), [bx, by2] = mapXY(b, f);
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by2); ctx.stroke();
    }
  }
  ctx.setLineDash([]);

  // The trades worth making, drawn where they actually are.
  world.runs.forEach((r, i) => {
    const a = by[r.from], b = by[r.to];
    if (!a || !b) return;
    const [ax, ay] = mapXY(a, f), [bx, by2] = mapXY(b, f);
    const mx = (ax + bx) / 2, my = (ay + by2) / 2 - 34 - i * 9;
    ctx.strokeStyle = `rgba(150,115,26,${0.75 - i * 0.14})`;
    ctx.lineWidth = Math.max(1.4, 4 - i);
    ctx.beginPath(); ctx.moveTo(ax, ay);
    ctx.quadraticCurveTo(mx, my, bx, by2); ctx.stroke();
    if (i === 0) {
      const label = `${r.per_day}c/day · ${r.goods.join(', ')}`;
      ctx.font = '600 12px ui-monospace, Menlo, monospace';
      ctx.textAlign = 'center';
      const tw = ctx.measureText(label).width;
      // Sit it on the arc's own apex with parchment behind it, or it reads as
      // part of whichever town name it happens to land on.
      poly([[mx - tw / 2 - 6, my - 18], [mx + tw / 2 + 6, my - 18],
            [mx + tw / 2 + 6, my - 3], [mx - tw / 2 - 6, my - 3]],
           'rgba(232,220,186,.92)', 'rgba(150,115,26,.5)');
      ctx.fillStyle = '#6b5212';
      ctx.fillText(label, mx, my - 7);
      ctx.textAlign = 'left';
    }
  });

  // The schedule, drawn. A lord who has said where he is going gets an arrow
  // to the place he said, and the one pointed at you is the only red thing on
  // this map. The difference between a war and an ambush is a fortnight's
  // notice; this is what the fortnight looks like.
  for (const fx of (world.fixtures || [])) {
    const a = by[fx.who], b = by[fx.target];
    if (!a || !b) continue;
    const [ax, ay] = mapXY(a, f), [bx, by2] = mapXY(b, f);
    const dx = bx - ax, dy = by2 - ay, len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len;
    // Stop short of both ends so the arrow joins the places rather than
    // covering them, and bow it away from the straight line, because a road
    // is already a dashed grey line between the same two towns and a second
    // one would be invisible.
    const x0 = ax + ux * 20, y0 = ay + uy * 20;
    const x1 = bx - ux * 26, y1 = by2 - uy * 26;
    const mx = (x0 + x1) / 2 - uy * len * 0.14;
    const my = (y0 + y1) / 2 + ux * len * 0.14;
    ctx.save();
    ctx.strokeStyle = fx.at_you ? 'rgba(150,34,28,.85)' : 'rgba(128,58,44,.42)';
    ctx.lineWidth = fx.at_you ? 2.4 : 1.5;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.quadraticCurveTo(mx, my, x1, y1);
    ctx.stroke();
    // The head points along the curve's last leg, not along the chord.
    const hx = x1 - mx, hy = y1 - my, hl = Math.hypot(hx, hy) || 1;
    const vx = hx / hl, vy = hy / hl, wing = fx.at_you ? 10 : 7;
    poly([[x1, y1],
          [x1 - vx * wing - vy * wing * 0.45, y1 - vy * wing + vx * wing * 0.45],
          [x1 - vx * wing + vy * wing * 0.45, y1 - vy * wing - vx * wing * 0.45]],
         fx.at_you ? 'rgba(150,34,28,.9)' : 'rgba(128,58,44,.5)');
    ctx.restore();
  }

  // Carts, where they have actually got to this morning.
  for (const c of world.carts) {
    const a = by[c.from], b = by[c.to];
    if (!a) continue;
    const [ax, ay] = mapXY(a, f);
    const [bx, by2] = b ? mapXY(b, f) : [ax, ay];
    const x = ax + (bx - ax) * c.done, y = ay + (by2 - ay) * c.done;
    const bob = c.moving ? Math.sin(t * 4 + c.uid) * 1.2 : 0;
    ctx.fillStyle = 'rgba(60,44,22,.28)';
    ctx.beginPath(); ctx.ellipse(x, y + 5, 8, 3, 0, 0, 7); ctx.fill();
    if (c.kind === 'ship') {
      ctx.strokeStyle = '#4a3a22'; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(x, y - 10 + bob); ctx.lineTo(x, y + 1 + bob); ctx.stroke();
      poly([[x, y - 10 + bob], [x + 9, y - 3 + bob], [x, y - 2 + bob]], '#e9dcbc');
      poly([[x - 8, y + 1 + bob], [x + 8, y + 1 + bob], [x + 5, y + 5 + bob],
            [x - 5, y + 5 + bob]], '#6a4f2c');
    } else {
      poly([[x - 8, y - 4 + bob], [x + 8, y - 4 + bob], [x + 8, y + 2 + bob],
            [x - 8, y + 2 + bob]], c.running ? '#7a5a2e' : '#6a6458');
      poly([[x - 8, y - 8 + bob], [x + 4, y - 8 + bob], [x + 6, y - 4 + bob],
            [x - 8, y - 4 + bob]], '#d8c8a2');
      ctx.fillStyle = '#3a2c18';
      for (const wx of [-5, 5]) {
        ctx.beginPath(); ctx.arc(x + wx, y + 3 + bob, 2.4, 0, 7); ctx.fill();
      }
    }
    if (c.load > 0) {
      ctx.font = '10px ui-monospace, Menlo, monospace';
      ctx.textAlign = 'center';
      label(`${c.load}`, x, y - 13 + bob, '#4a3a1e');
      ctx.textAlign = 'left';
    }
  }

  /* The hosts. Drawn the way the carts are, because a host crossing the
   * country is the same problem the carts already solved -- and it was the
   * one thing happening on this map that the map did not show.
   *
   * Yours are solid. Theirs, seen today, are red. Theirs remembered are the
   * ghost of a sighting with the days written on it, because the alternative
   * is a live tracker of every enemy army, which would quietly delete the
   * fog of war. */
  hostSpots.clear();
  for (const h of (world.hosts || [])) {
    const a = by[h.at] || by[h.from];
    if (!a) continue;
    const [ax, ay] = mapXY(a, f);
    const b = h.to ? by[h.to] : null;
    const [bx, by2] = b ? mapXY(b, f) : [ax, ay];
    const x = ax + (bx - ax) * h.done, y = ay + (by2 - ay) * h.done - 9;
    hostSpots.set(h.uid, [x, y, h]);
    const ghost = h.state === 'remembered';
    const ink = h.mine ? '#c9a227' : (ghost ? 'rgba(150,120,110,.5)' : '#96221c');
    ctx.globalAlpha = ghost ? 0.55 : 1;
    ctx.fillStyle = 'rgba(40,30,18,.25)';
    ctx.beginPath(); ctx.ellipse(x, y + 12, 9, 3.2, 0, 0, 7); ctx.fill();
    // A pennon on a staff. Its length is the size of the host, so a thin
    // one looks thin without a number being read.
    const flag = 6 + Math.min(11, h.size / 14);
    ctx.strokeStyle = ghost ? 'rgba(90,76,60,.6)' : '#4a3a22';
    ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(x, y + 11); ctx.lineTo(x, y - 11); ctx.stroke();
    poly([[x, y - 11], [x + flag, y - 8], [x, y - 5]], ink);
    if (h.state === 'besieging') {
      ctx.strokeStyle = ink; ctx.lineWidth = 1.3;
      ctx.beginPath(); ctx.arc(x, y + 2, 10, 0, 7); ctx.stroke();
    }
    if (ghost) {
      ctx.font = '9px ui-monospace, Menlo, monospace';
      ctx.textAlign = 'center';
      label(`${h.stale}d`, x, y + 22, '#6a5c4a');
      ctx.textAlign = 'left';
    }
    ctx.globalAlpha = 1;
  }

  // The places themselves.
  for (const n of world.nodes) {
    const [x, y] = mapXY(n, f);
    if (n.kind === 'shrine') {
      ctx.strokeStyle = n.who === 'yours' ? '#96731a' : '#6a5a44';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x, y - 9); ctx.lineTo(x, y + 5);
      ctx.moveTo(x - 5, y - 4); ctx.lineTo(x + 5, y - 4); ctx.stroke();
    } else if (n.kind === 'site') {
      ctx.strokeStyle = 'rgba(90,110,60,.8)'; ctx.lineWidth = 1.4;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.arc(x, y, 8, 0, 7); ctx.stroke();
      ctx.setLineDash([]);
    } else {
      const mine = n.kind === 'mine' || n.kind === 'vassal';
      const size = n.kind === 'mine' ? 1.35 : 1;
      // A ring of price round every market: green is where you buy.
      if (n.price > 0) {
        ctx.strokeStyle = priceColour(n.price, band);
        ctx.lineWidth = 3.5;
        // Dashed where nobody of yours has been: the price is hearsay, and a
        // solid ring would claim more than the game knows.
        if (n.kind === 'town' && n.known < 0) ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.arc(x, y - 4, 15 * size, 0, 7); ctx.stroke();
        ctx.setLineDash([]);
      }
      poly([[x - 9 * size, y + 2], [x - 9 * size, y - 5 * size],
            [x - 4 * size, y - 10 * size], [x + 1 * size, y - 5 * size],
            [x + 1 * size, y + 2]], mine ? '#8a6a3a' : '#7a6a56');
      poly([[x + 1 * size, y + 2], [x + 1 * size, y - 9 * size],
            [x + 9 * size, y - 9 * size], [x + 9 * size, y + 2]],
           mine ? '#9c7c46' : '#8b7b66');
      ctx.fillStyle = mine ? '#5e4420' : '#574b3a';
      ctx.fillRect(x + 3 * size, y - 15 * size, 4 * size, 6 * size);
      if (n.kind === 'mine') {
        ctx.strokeStyle = '#5a4a34'; ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.moveTo(x + 5, y - 15); ctx.lineTo(x + 5, y - 26); ctx.stroke();
        poly([[x + 5, y - 26], [x + 17, y - 23], [x + 5, y - 19]], '#a8412f');
      }
      if (n.port) {
        ctx.strokeStyle = 'rgba(40,80,110,.8)'; ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(x - 14, y + 8); ctx.quadraticCurveTo(x, y + 12, x + 14, y + 8);
        ctx.stroke();
      }
    }
    ctx.font = (n.kind === 'mine' ? '600 13px ' : '12px ') +
               '"Iowan Old Style", Palatino, Georgia, serif';
    ctx.textAlign = 'center';
    label(n.name, x, y + 19, n.kind === 'mine' ? '#4a3607' : '#3c3323');
    if (n.kind === 'town' && n.known < 0) {
      ctx.font = 'italic 11px Georgia, serif';
      label('never visited', x, y + 32, 'rgba(70,58,36,.72)');
    } else if (n.price > 0) {
      ctx.font = '600 11px ui-monospace, Menlo, monospace';
      label(`${n.price.toFixed(1)}c`, x, y + 32, priceColour(n.price, band));
    }
    ctx.textAlign = 'left';
  }
  // A compass, because every map of a march has one -- unless the screen is
  // narrow enough that the console is already standing where it would go.
  if (NARROW()) return;
  ctx.strokeStyle = 'rgba(90,70,40,.6)'; ctx.lineWidth = 1.4;
  ctx.beginPath(); ctx.arc(w - 74, h - 148, 22, 0, 7); ctx.stroke();
  poly([[w - 74, h - 168], [w - 69, h - 146], [w - 74, h - 150],
        [w - 79, h - 146]], '#8f2b26');
  ctx.fillStyle = '#5a4a30'; ctx.font = '11px Georgia, serif';
  ctx.textAlign = 'center'; ctx.fillText('N', w - 74, h - 174); ctx.textAlign = 'left';
  // A map is read indoors, so the hour barely touches it -- but a parchment
  // that stays noon-bright while the town outside is dark reads as a bug.
  const s = sun();
  if (s.night > 0.05) {
    ctx.save();
    ctx.globalCompositeOperation = 'multiply';
    ctx.fillStyle = `rgba(${Math.round(255 - 46 * s.night)},` +
                    `${Math.round(255 - 44 * s.night)},` +
                    `${Math.round(255 - 26 * s.night)},1)`;
    ctx.fillRect(0, 0, w, h);
    ctx.restore();
  }
}

async function loadOptions() {
  try { opts = await (await fetch('/options')).json(); } catch (e) { opts = null; }
}

async function loadMarch() {
  const r = await fetch('/march?good=' + encodeURIComponent(good));
  world = await r.json();
  paintTrade();
}

function paintTrade() {
  if (!world) return;
  $('runs').innerHTML = world.runs.length ? world.runs.map(r =>
    `<li><b>${r.per_day}c/day</b> <span>${nameOf(r.from)} → ${nameOf(r.to)}, ` +
    `${r.days}d · ${r.goods.join(', ') || 'nothing worth carrying'}</span></li>`
  ).join('') : '<li><span>nothing worth carrying today</span></li>';
  $('carts').innerHTML = world.carts.length ? world.carts.map(c =>
    `<li><b>${c.name}</b> <span>${c.moving
      ? `${nameOf(c.from)} → ${nameOf(c.to)}, ${Math.round(c.done * 100)}%`
      : `standing at ${nameOf(c.from)}`} · ${c.load}/${c.capacity}</span></li>`
  ).join('') : '<li><span>no carts on the road</span></li>';
  scrollCue();
}
function nameOf(key) {
  const n = world && world.nodes.find(x => x.key === key);
  return n ? n.name : key;
}

/* ------------------------------------------------------------------- writ
 * What you can do to the thing you just clicked.
 *
 * Nothing in here knows a rule. Every button composes the same line a person
 * would have typed and posts it, so there is exactly one place the rules live
 * and it is not in this file. The page asks the engine what is possible and
 * draws the answer; it never decides.
 */
let opts = null, picked = null;

function screenToTile(ev) {
  const r = canvas.getBoundingClientRect();
  const px = (ev.clientX - r.left - r.width / 2 - camera.x) / camera.zoom
           + (plan.w - plan.h) * TW / 4;
  const py = (ev.clientY - r.top - r.height / 2 - camera.y) / camera.zoom
           + (plan.w + plan.h) * TH / 4;
  // Invert the isometric projection: a screen point back to a tile.
  const tx = Math.round((px / (TW / 2) + py / (TH / 2)) / 2);
  const ty = Math.round((py / (TH / 2) - px / (TW / 2)) / 2);
  return [tx, ty];
}
function buildingAt(ev) {
  const r = canvas.getBoundingClientRect();
  const px = (ev.clientX - r.left - r.width / 2 - camera.x) / camera.zoom
           + (plan.w - plan.h) * TW / 4;
  const py = (ev.clientY - r.top - r.height / 2 - camera.y) / camera.zoom
           + (plan.w + plan.h) * TH / 4;
  let best = null, bestD = 40;
  for (const b of plan.buildings) {
    const [sx, sy] = iso(b.x, b.y);
    const d = Math.hypot(sx - px, (sy - py) * 1.9);
    if (d < bestD) { bestD = d; best = b; }
  }
  return best;
}
/* Which figure was clicked. Tighter than the building test on purpose: a
 * person is small, and a near miss should open the roof behind them rather
 * than the wrong villager. */
function folkAt(ev) {
  const r = canvas.getBoundingClientRect();
  const px = (ev.clientX - r.left - r.width / 2 - camera.x) / camera.zoom
           + (plan.w - plan.h) * TW / 4;
  const py = (ev.clientY - r.top - r.height / 2 - camera.y) / camera.zoom
           + (plan.w + plan.h) * TH / 4;
  let best = null, bestD = 13;
  for (const [i, at] of folkSpots) {
    const d = Math.hypot(at[0] - px, (at[1] - 7 - py) * 0.85);
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

function hostAt(ev) {
  if (!world) return null;
  const r = canvas.getBoundingClientRect();
  const px = ev.clientX - r.left, py = ev.clientY - r.top;
  let best = null, bestD = 16;
  for (const [, at] of hostSpots) {
    const d = Math.hypot(at[0] + 4 - px, at[1] - py);
    if (d < bestD) { bestD = d; best = at[2]; }
  }
  return best;
}

function townNodeAt(ev) {
  if (!world) return null;
  const r = canvas.getBoundingClientRect();
  const f = mapFit(canvas.clientWidth, canvas.clientHeight);
  const px = ev.clientX - r.left, py = ev.clientY - r.top;
  let best = null, bestD = 26;
  for (const n of world.nodes) {
    const [x, y] = mapXY(n, f);
    const d = Math.hypot(x - px, y - py);
    if (d < bestD) { bestD = d; best = n; }
  }
  return best;
}

function openWrit(title, html, ev) {
  const writ = $('writ');
  // The hover tip is the same fact in fewer words. Two of them, one showing
  // faintly through the other, is how the panel used to open.
  $('tip').hidden = true;
  $('writ-title').textContent = title;
  $('writ-body').innerHTML = html;
  writ.hidden = false;
  const r = canvas.getBoundingClientRect();
  const x = Math.min(Math.max(12, ev.clientX - r.left + 16),
                     r.width - 302);
  const y = Math.min(Math.max(52, ev.clientY - r.top - 30), r.height - 260);
  writ.style.left = x + 'px';
  writ.style.top = y + 'px';
  // How much room is actually left under it. A flat 60% of the window put the
  // foot of a long build list below the bottom of the screen, where the only
  // way to reach it was a scrollbar nobody could see.
  writ.style.maxHeight = Math.max(160, r.height - y - 18) + 'px';
  for (const btn of writ.querySelectorAll('[data-do]')) {
    btn.addEventListener('click', async () => {
      await send(btn.dataset.do);
      if (btn.dataset.keep === undefined) closeWrit();
      else reopen(ev);
    });
  }
}
const closeWrit = () => { $('writ').hidden = true; picked = null; };
$('writ-close').addEventListener('click', closeWrit);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeWrit(); });

function reopen(ev) {
  if (picked && picked.kind === 'plot') return plotWrit(picked.x, picked.y, ev);
  if (picked && picked.kind === 'building') {
    const again = plan.buildings.find(b => b.uid === picked.uid);
    if (again) return buildingWrit(again, ev);
  }
  closeWrit();
}

function buildingWrit(b, ev) {
  picked = { kind: 'building', uid: b.uid };
  const how = !b.complete ? 'being built'
    : b.burning ? 'on fire' : b.running ? 'working' : 'idle';
  // What the next hand here is worth against the wage. The one number that
  // decides whether this shed should be open, attached to the shed.
  const m = state && state.margin ? state.margin[b.uid] : null;
  let worth = '';
  if (m && b.complete) {
    const good = m.net > m.wage;
    worth = `<p class="why ${good ? 'up' : 'down'}">a hand here makes ` +
      `<b>${m.net.toFixed(2)}c</b> a day against a wage of ` +
      `${m.wage.toFixed(2)}c — ${good ? 'worth working' : 'it loses money open'}` +
      `${m.jobs ? ` · ${m.staffed} of ${m.jobs} hands` : ''}</p>`;
  }
  // And what somebody who lives here thinks of it. The mood breakdown is
  // honest and inhuman; a number cannot be indignant.
  const street = (state && state.street) || [];
  const homely = ['cottage', 'hovel', 'townhouse', 'inn', 'market'];
  const voice = street.length && homely.includes(b.key)
    ? `<p class="said"><em>${esc(street[0].who)}</em>` +
      `&ldquo;${esc(street[0].said)}&rdquo;</p>` : '';
  openWrit(b.name, `
    <p>${how}${b.terrain === 'urban' ? ' · inside the wall' : ''}</p>
    ${voice}${worth}
    <div class="acts">
      <button data-do="close ${b.uid}">${b.running || b.idle ? 'close / open' : 'close'}</button>
      <button data-do="raze ${b.uid}">pull down</button>
    </div>
    <p class="why">who gets hands first when there are not enough</p>
    <div class="acts">
      <button data-do="work ${b.key} first" data-keep="1">first</button>
      <button data-do="work ${b.key} normal" data-keep="1">normal</button>
      <button data-do="work ${b.key} last" data-keep="1">last</button>
    </div>`, ev);
}

function plotWrit(x, y, ev) {
  picked = { kind: 'plot', x, y };
  if (!opts) { openWrit('this plot', '<p class="why">asking…</p>', ev); return; }
  const rows = opts.buildings.slice(0, 30).map(b => `
    <button data-do="build ${b.key}" ${b.can ? '' : 'disabled'}
            title="${b.can ? (b.note || b.name) : b.why}">
      <span>${b.name}</span>
      <em>${b.can ? num(b.coin) + 'c · ' + b.days + 'd' : b.why}</em>
    </button>`).join('');
  const room = Object.entries(opts.slots)
    .filter(([, n]) => n > 0).map(([k, n]) => `${n} ${k}`).join(', ');
  openWrit('raise something', `
    <p class="why">room for: ${room || 'nothing — the land is full'}</p>
    <div class="pick">${rows}</div>`, ev);
}

function nodeWrit(n, ev) {
  const carts = world.carts.filter(c => !c.moving);
  const idle = carts.length ? carts[0] : null;
  // Prices are public -- merchants talk. Strength is not, and saying so in the
  // same breath as a price is what made this read as a contradiction.
  const price = n.price > 0
    ? `<p>${world.good} at <b>${n.price.toFixed(2)}c</b> · ${n.stock} in store` +
      `<span class="why"> — merchants report it</span></p>` : '';
  const known = n.kind !== 'town' ? ''
    : n.known < 0
      ? 'you have never sent anyone, so you know nothing of its strength'
      : `about ${n.host} of strength behind ${n.walls} of wall — ` +
        (n.known === 0 ? 'seen today' : `and that is ${n.known} days old`);
  // What he thinks of you and why, which is public in a way strength is not:
  // an envoy does not have to guess whether a man is still angry about the
  // town you took, because he will tell you at length.
  const c = (state && state.court && state.court.towns) || {};
  const st = c[n.key];
  const marks = !st ? '' : [
    st.signed ? '<span class="bad">signed against you</span>' : '',
    st.allied ? '<span class="good">allied</span>' : '',
    st.claim ? '<span class="claim">your claim by marriage</span>' : '',
  ].filter(Boolean).join(' · ');
  // What the place looks like, which is public in the plainest possible way:
  // anybody who has been there has seen the roofs.
  const set = st && st.culture && state.idioms && state.idioms[st.culture];
  const skyline = set
    ? `<canvas class="skyline" data-culture="${st.culture}"></canvas>` +
      `<p class="why">built in ${esc(set.name)} — ${esc(set.blurb)}</p>` : '';
  const standing = !st ? '' :
    `<p class="standing"><b>${st.opinion > 0 ? '+' : ''}${st.opinion}</b> ` +
    `${esc(st.temper)}${marks ? ' · ' + marks : ''}</p>` +
    (st.why.length ? `<ul class="why-list">` + st.why.map(w =>
      `<li><span>${esc(w.what)}</span><em class="${w.by > 0 ? 'up' : 'down'}">` +
      `${w.by > 0 ? '+' : ''}${w.by}</em></li>`).join('') + '</ul>' : '') +
    `<p class="why">${st.ground
      ? 'a reason to march: ' + esc(st.ground)
      : 'no reason to march anybody would accept'}</p>`;
  const acts = n.kind === 'town' ? `
    <div class="acts">
      ${idle ? `<button data-do="auto ${idle.uid}">put ${idle.name} on the best run</button>` : ''}
      <button data-do="scan">what is worth carrying</button>
      <button data-do="gift ${n.key} 500">gift 500c</button>
      <button data-do="truce ${n.key}">ask for a truce</button>
      ${st && !st.allied && !st.signed
        ? `<button data-do="ally ${n.key}">ask him to swear</button>` : ''}
    </div>` : n.kind === 'site' ? `
    <div class="acts"><button data-do="found ${n.key}">settle it</button></div>` : '';
  openWrit(n.name, skyline + price + (known ? `<p class="why">${known}</p>` : '')
           + standing + acts, ev);
  for (const c of writ.querySelectorAll('canvas.skyline')) {
    c.width = Math.round(c.clientWidth * dpr);
    c.height = Math.round(104 * dpr);
    c.style.height = '104px';
    drawSkyline(c, c.dataset.culture);
  }
}

for (const btn of document.querySelectorAll('#clock button')) {
  btn.addEventListener('click', () => send(btn.dataset.do));
}

/* ------------------------------------------------------------------ frame */
function frame() {
  const t = clock();
  turnTheSky(t);
  const w = canvas.width / dpr, h = canvas.height / dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (mode === 'march') {
    drawMarch(w, h, t);
    nextFrame();
    return;
  }
  glows = [];
  drawSky(w, h, t);
  if (plan) {
    ctx.save();
    ctx.translate(w / 2 + camera.x, h / 2 + camera.y);
    ctx.scale(camera.zoom, camera.zoom);
    ctx.translate(-(plan.w - plan.h) * TW / 4, -(plan.w + plan.h) * TH / 4);
    drawGround();
    // Everything that stands up, painted back to front.
    const things = [];
    folkSpots.clear();
    for (let y = 0; y < plan.h; y++)
      for (let x = 0; x < plan.w; x++)
        if (plan.tiles[y][x] === 'forest') things.push({ d: x + y, x, y, kind: 'wood' });
    for (const b of plan.buildings) things.push({ d: b.x + b.y, kind: 'b', b });
    for (const w2 of plan.walls) things.push({ d: w2.x + w2.y, kind: 'w', w: w2 });
    plan.folk.forEach((f, i) => things.push({ d: f.x + f.y, kind: 'f', f, i }));
    const at = {};
    for (const b of plan.buildings) at[b.uid] = b;
    (plan.hauls || []).forEach((h, i) => {
      const p = haulAt(h, i, t, at);
      if (p) things.push({ d: p.x + p.y + 0.4, kind: 'h', h, i, at, pos: p });
    });
    things.sort((a, b) => a.d - b.d);
    setClip(w, h);
    for (const it of things) {
      const [ix, iy] = iso(it.x !== undefined ? it.x : it.b ? it.b.x
                           : it.w ? it.w.x : it.pos ? it.pos.x : it.f.x,
                           it.y !== undefined ? it.y : it.b ? it.b.y
                           : it.w ? it.w.y : it.pos ? it.pos.y : it.f.y);
      if (!onScreen(ix, iy, 120)) continue;
      if (it.kind === 'wood') drawTrees(it.x, it.y);
      else if (it.kind === 'b') drawBuilding(it.b, t);
      else if (it.kind === 'w') drawWall(it.w, t);
      else if (it.kind === 'h') drawHaul(it.h, it.i, t, it.at, it.pos);
      else drawFolk(it.f, it.i, t);
    }
    drawEffects(t);
    ctx.restore();
  }
  // The light goes on last over everything solid, and then the things that
  // make their own. A brazier is not less bright because the sun went down.
  lightWash(w, h);
  if (plan) {
    ctx.save();
    ctx.translate(w / 2 + camera.x, h / 2 + camera.y);
    ctx.scale(camera.zoom, camera.zoom);
    ctx.translate(-(plan.w - plan.h) * TW / 4, -(plan.w + plan.h) * TH / 4);
    drawGlows();
    ctx.restore();
  }
  drawWeather(w, h, t);
  if (plan && drawing()) {
    ctx.save();
    ctx.translate(w / 2 + camera.x, h / 2 + camera.y);
    ctx.scale(camera.zoom, camera.zoom);
    ctx.translate(-(plan.w - plan.h) * TW / 4, -(plan.w + plan.h) * TH / 4);
    drawPencil(t);
    ctx.restore();
  }
  nextFrame();
}

/* What the pencil is about to do, over the top of everything. Two layers:
 * the yards no tower covers, marked in red so the hole in your own castle is
 * a thing you can see rather than a line in a report; and the run under the
 * mouse while it is down. */
function drawPencil(t) {
  const weak = (state && state.castle && state.castle.weak) || [];
  for (const p of weak) tileMark(p.x, p.y, 'rgba(196,90,74,.42)');
  if (!stroke) return;
  const laying = lay === 'unwall' ? 'rgba(196,90,74,.55)' : 'rgba(201,162,39,.55)';
  for (const [x, y] of runBetween(stroke.from, stroke.to)) tileMark(x, y, laying);
}
function tileMark(x, y, fill) {
  const [sx, sy] = iso(x, y);
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(sx, sy - TH / 2);
  ctx.lineTo(sx + TW / 2, sy);
  ctx.lineTo(sx, sy + TH / 2);
  ctx.lineTo(sx - TW / 2, sy);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.restore();
}
/* The ground, painted once and kept.
 *
 * Nine hundred tiles of crop rows, cart ruts and grass tufts is a great deal
 * of drawing to do sixty times a second for a picture that does not change
 * between days. It is baked into a bitmap the size of the plan instead, and
 * redrawn only when the plan or the season does -- which is what pays for the
 * texture being worth looking at in the first place. Water is the exception:
 * water has to move, so it stays live on top.
 */
let ground = null, groundKey = '', baking = false;
function drawGround() {
  const wet = [];
  const key = [plan.w, plan.h, state && state.season,
               plan.tiles.map(r => r.join('')).join('')].join('|');
  if (!ground || groundKey !== key) {
    const pad = TW, W = (plan.w + plan.h) * TW / 2 + pad * 2;
    const H = (plan.w + plan.h) * TH / 2 + pad * 2;
    const c = document.createElement('canvas');
    c.width = Math.ceil(W * dpr); c.height = Math.ceil(H * dpr);
    const keepCtx = ctx;
    baking = true;
    ctx = c.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.translate(plan.h * TW / 2 + pad, pad);
    for (let y = 0; y < plan.h; y++)
      for (let x = 0; x < plan.w; x++)
        if (plan.tiles[y][x] !== 'water') drawTile(x, y, plan.tiles[y][x]);
    ctx = keepCtx;
    baking = false;
    ground = { canvas: c, dx: -(plan.h * TW / 2 + pad), dy: -pad };
    groundKey = key;
    GRAIN_OWNER = null;              // the patterns belong to a context
  }
  ctx.drawImage(ground.canvas, ground.dx, ground.dy,
                ground.canvas.width / dpr, ground.canvas.height / dpr);
  for (let y = 0; y < plan.h; y++)
    for (let x = 0; x < plan.w; x++)
      if (plan.tiles[y][x] === 'water') {
        const [sx, sy] = iso(x, y);
        if (onScreen(sx, sy, TW)) wet.push([x, y, sx, sy]);
      }
  drawWater(wet);
}

/* Water, all of it at once.
 *
 * A clip region is the dearest thing on a canvas and the old painter set one
 * per tile: a moat and a river came to ninety clips a frame and nine
 * milliseconds, which was a third of the budget spent on the cheapest-looking
 * thing on the screen. One path round every wet tile, clipped once, and the
 * waves drawn inside it.
 */
function drawWater(wet) {
  if (!wet.length) return;
  const t = clock(), s = sun(), p = pal();
  ctx.save();
  ctx.beginPath();
  for (const [x, y, sx, sy] of wet) {
    ctx.moveTo(sx, sy - TH / 2);
    ctx.lineTo(sx + TW / 2, sy);
    ctx.lineTo(sx, sy + TH / 2);
    ctx.lineTo(sx - TW / 2, sy);
    ctx.closePath();
  }
  ctx.fillStyle = p.water;
  ctx.fill();
  ctx.clip();
  // Swell: three crossing waves at different speeds, so the surface never
  // repeats on any count a player could hold.
  for (let i = 0; i < 3; i++) {
    const a = 0.055 + 0.05 * (2 - i);
    ctx.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
    ctx.beginPath();
    for (const [x, y, sx, sy] of wet) {
      const wy = sy + (i - 1) * 8
        + Math.sin(t * (0.9 + i * 0.35) + (x + y) * 0.8 + i * 2.1) * 3.0;
      ctx.moveTo(sx - TW / 2, wy);
      ctx.quadraticCurveTo(sx - TW / 4, wy - 3.4, sx, wy);
      ctx.quadraticCurveTo(sx + TW / 4, wy + 3.4, sx + TW / 2, wy);
      ctx.lineTo(sx + TW / 2, wy + 2.6);
      ctx.quadraticCurveTo(sx + TW / 4, wy + 6.0, sx, wy + 2.6);
      ctx.quadraticCurveTo(sx - TW / 4, wy - 0.8, sx - TW / 2, wy + 2.6);
      ctx.closePath();
    }
    ctx.fill();
  }
  // The sun's own road across the water, which only exists when it is low.
  const glint = Math.max(0, 1 - Math.abs(s.up) * 2.2) * (1 - s.night);
  if (glint > 0.02) {
    ctx.fillStyle = `rgba(255,226,168,${(0.38 * glint).toFixed(3)})`;
    ctx.beginPath();
    for (const [x, y, sx, sy] of wet) {
      for (let i = 0; i < 3; i++) {
        const gy = sy + (i - 1) * 7 + Math.sin(t * 1.6 + x * 1.3 + i) * 2.4;
        const gw = 7 + 5 * Math.sin(t * 2.1 + y + i);
        ctx.moveTo(sx + Math.cos(s.az) * 7 + gw, gy);
        ctx.ellipse(sx + Math.cos(s.az) * 7, gy, gw, 1.15, 0, 0, 7);
      }
    }
    ctx.fill();
  }
  // And the moon's, colder and narrower.
  if (s.night > 0.2) {
    ctx.fillStyle = `rgba(198,216,245,${(0.22 * s.night).toFixed(3)})`;
    ctx.beginPath();
    for (const [x, y, sx, sy] of wet) {
      for (let i = 0; i < 2; i++) {
        const gy = sy + (i - 0.5) * 9 + Math.sin(t * 1.1 + x + i) * 2.0;
        ctx.moveTo(sx + 6, gy);
        ctx.ellipse(sx, gy, 6, 0.9, 0, 0, 7);
      }
    }
    ctx.fill();
  }
  ctx.restore();
}

/* Still means still: one redraw every so often is enough to pick up a new day. */
function nextFrame() {
  if (STILL) setTimeout(frame, 500); else requestAnimationFrame(frame);
}

/* ---------------------------------------------------------------- palette
 * A command line is the fastest interface there is for somebody who knows the
 * commands and the worst for somebody who does not. The palette is the bridge:
 * the same seventy commands, searchable, each with the one line its own
 * docstring gives it, fetched from the console's registry so it cannot drift
 * from what the game will actually accept.
 */
let commands = [], palHot = 0, shown = [];

async function loadCommands() {
  try { commands = await (await fetch('/commands')).json(); }
  catch (e) { commands = []; }
}

/* Subsequence match, the way every palette worth using does it: `mkt` finds
 * `market`. Scored so a prefix beats a scatter and a name beats a blurb. */
function score(needle, hay) {
  if (!needle) return 1;
  const n = needle.toLowerCase(), h = hay.toLowerCase();
  if (h.startsWith(n)) return 1000 - h.length;
  let i = 0, gaps = 0, last = -1;
  for (const ch of n) {
    const at = h.indexOf(ch, i);
    if (at < 0) return 0;
    if (last >= 0) gaps += at - last - 1;
    last = at; i = at + 1;
  }
  return Math.max(1, 400 - gaps * 8 - h.length);
}

function rankCommands(q) {
  const typed = q.trim();
  const head = typed.split(/\s+/)[0] || '';
  const rows = [];
  for (const c of commands) {
    const names = [c.name].concat(c.aliases || []);
    let best = 0;
    for (const nm of names) best = Math.max(best, score(head, nm));
    // The blurb is searched by whole words only. A loose subsequence over a
    // sentence matches nearly everything -- "mar" found "Open a saved game,
    // and survive it not being one" -- which is the fastest way to make a
    // palette useless while looking like it works.
    let inBlurb = 0;
    if (head.length > 1) {
      for (const word of (c.help || '').toLowerCase().split(/[^a-z]+/)) {
        if (word.startsWith(head.toLowerCase())) { inBlurb = 120; break; }
      }
    }
    const s = Math.max(best, inBlurb);
    if (s > 0) rows.push({ c, s });
  }
  rows.sort((a, b) => b.s - a.s || a.c.name.localeCompare(b.c.name));
  return rows.slice(0, 14).map(r => r.c);
}

function paintPalette() {
  const q = $('palette-q').value;
  shown = rankCommands(q);
  palHot = Math.max(0, Math.min(palHot, shown.length - 1));
  const rest = q.trim().split(/\s+/).slice(1).join(' ');
  $('palette-list').innerHTML = shown.map((c, i) => {
    const args = rest ? ` <em>${esc(rest)}</em>` : '';
    return `<li role="option" id="pal-${i}" aria-selected="${i === palHot}"` +
      `${i === palHot ? ' class="on"' : ''} data-i="${i}">` +
      `<b>${esc(c.name)}</b>${args}` +
      `<span>${esc(c.help || '')}</span></li>`;
  }).join('') || '<li class="none">nothing by that name</li>';
  const on = $('pal-' + palHot);
  if (on) on.scrollIntoView({ block: 'nearest' });
  $('palette-q').setAttribute('aria-activedescendant', on ? on.id : '');
}

const esc = t => String(t).replace(/[&<>"]/g,
  ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));

function openPalette(seed) {
  const box = $('palette');
  box.hidden = false;
  const q = $('palette-q');
  q.value = seed || '';
  palHot = 0;
  paintPalette();
  q.focus();
  q.select();
}

function closePalette() {
  $('palette').hidden = true;
  $('line').focus();
}

function runPicked() {
  const chosen = shown[palHot];
  if (!chosen) return;
  const rest = $('palette-q').value.trim().split(/\s+/).slice(1).join(' ');
  closePalette();
  send(rest ? `${chosen.name} ${rest}` : chosen.name);
}

$('palette-q').addEventListener('input', () => { palHot = 0; paintPalette(); });
$('palette-q').addEventListener('keydown', e => {
  if (e.key === 'ArrowDown' || (e.key === 'n' && e.ctrlKey)) {
    palHot = Math.min(palHot + 1, shown.length - 1); paintPalette(); e.preventDefault();
  } else if (e.key === 'ArrowUp' || (e.key === 'p' && e.ctrlKey)) {
    palHot = Math.max(palHot - 1, 0); paintPalette(); e.preventDefault();
  } else if (e.key === 'Enter') {
    runPicked(); e.preventDefault();
  } else if (e.key === 'Escape') {
    closePalette(); e.preventDefault();
  } else if (e.key === 'Tab' && shown[palHot]) {
    $('palette-q').value = shown[palHot].name + ' ';
    paintPalette(); e.preventDefault();
  }
});
$('palette-list').addEventListener('click', e => {
  const li = e.target.closest('li[data-i]');
  if (!li) return;
  palHot = +li.dataset.i;
  runPicked();
});
$('palette').addEventListener('mousedown', e => {
  if (e.target === $('palette')) closePalette();
});

/* ------------------------------------------------------------------- keys
 * Unmodified keys only when the cursor is not in a text field, which is the
 * only rule that lets a game with a command prompt in it also have shortcuts.
 */
const typing = () => {
  const el = document.activeElement;
  return el && (el.tagName === 'INPUT' || el.tagName === 'SELECT'
                || el.isContentEditable);
};
const KEYS = {
  ' ': 'next', w: 'next 7', m: 'next 30', h: 'hint',
};
document.addEventListener('keydown', e => {
  const meta = e.metaKey || e.ctrlKey;
  if (meta && (e.key === 'k' || e.key === 'K' || e.key === 'p')) {
    openPalette(''); e.preventDefault(); return;
  }
  if (e.key === 'Escape') {
    if (!$('palette').hidden) { closePalette(); return; }
    if (!$('keys').hidden) { $('keys').hidden = true; $('line').focus(); return; }
    closeWrit();
    return;
  }
  if (meta || e.altKey) return;
  if (e.key === '/' && !typing()) { $('line').focus(); e.preventDefault(); return; }
  if (typing()) return;
  if (e.key === '?') { $('keys').hidden = !$('keys').hidden; e.preventDefault(); return; }
  if (e.key === 't' || e.key === 'T') { setMode('town'); return; }
  if (e.key === 'r' || e.key === 'R') { setMode('march'); return; }
  if (e.key === 'w' || e.key === 'W') { setMode(drawing() ? 'town' : 'castle'); return; }
  const line = KEYS[e.key.toLowerCase()] || (e.key === ' ' ? 'next' : '');
  if (line) { send(line); e.preventDefault(); }
});
$('keys').addEventListener('click', () => { $('keys').hidden = true; });

/* ------------------------------------------------------------------- shell */
let wasNarrow = null;
function resize() {
  dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = canvas.clientWidth * dpr;
  canvas.height = canvas.clientHeight * dpr;
  scrollCue();
  // Crossing the breakpoint changes the shape of the room the town is in.
  const now = NARROW();
  if (wasNarrow !== null && now !== wasNarrow && mode === 'town') frameTown();
  wasNarrow = now;
}
window.addEventListener('resize', resize);

/* ------------------------------------------------------------ the pencil */
/* Drawing is a drag along the ground rather than a form: press where the
 * wall starts, let go where it ends. The run is previewed while the mouse
 * is down and only sent when it is released, so a slip costs nothing. */
let lay = 'wall', stroke = null;
function drawing() { return mode === 'castle'; }
function runBetween(a, b) {
  const n = Math.max(Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
  if (!n) return [a];
  const out = [];
  for (let i = 0; i <= n; i++)
    out.push([Math.round(a[0] + (b[0] - a[0]) * i / n),
              Math.round(a[1] + (b[1] - a[1]) * i / n)]);
  return out;
}
for (const btn of document.querySelectorAll('#drawbar [data-lay]')) {
  btn.addEventListener('click', () => {
    lay = btn.dataset.lay;
    for (const o of document.querySelectorAll('#drawbar [data-lay]'))
      o.setAttribute('aria-pressed', String(o === btn));
  });
}

let drag = null, pressed = null;
canvas.addEventListener('pointerdown', e => {
  if (drawing() && plan) {
    stroke = { from: screenToTile(e), to: screenToTile(e) };
    pressed = null;
    return;
  }
  drag = { x: e.clientX, y: e.clientY };
  pressed = { x: e.clientX, y: e.clientY, t: performance.now() };
});
window.addEventListener('pointerup', e => {
  if (stroke) {
    const a = stroke.from, b = stroke.to;
    stroke = null;
    const one = a[0] === b[0] && a[1] === b[1];
    const where = one ? `${a[0]},${a[1]}` : `${a[0]},${a[1]} ${b[0]},${b[1]}`;
    send(`${lay} ${where}`);
    return;
  }
  drag = null;
  // A click is a press that did not turn into a drag. Without this the writ
  // opens every time you finish moving the camera.
  if (!pressed) return;
  const moved = Math.hypot(e.clientX - pressed.x, e.clientY - pressed.y);
  const quick = performance.now() - pressed.t < 600;
  pressed = null;
  if (moved > 5 || !quick) return;
  if (e.target !== canvas) return;
  if (mode === 'march') {
    // Sending a host somewhere is two clicks: the host, then the place. While
    // the second is pending every node is a destination, so the node writ
    // would be in the way.
    const n = townNodeAt(e);
    if (sending !== null) {
      const to = n ? n.key : '';
      const uid = sending;
      sending = null;
      canvas.style.cursor = '';
      if (!to) return say('nowhere there to march to');
      return send(`march ${uid} ${to}`);
    }
    const h = hostAt(e);
    if (h) return openHost(h);
    return n ? nodeWrit(n, e) : closeWrit();
  }
  if (!plan) return;
  // People first. A figure standing in front of a roof is the thing you were
  // pointing at, and the roof is a bigger target that would always win.
  const who = folkAt(e);
  if (who !== null) return openSoul(who);
  const b = buildingAt(e);
  if (b) return buildingWrit(b, e);
  const [tx, ty] = screenToTile(e);
  const p = plan.precinct;
  if (tx >= p.x0 && tx <= p.x1 && ty >= p.y0 && ty <= p.y1) return plotWrit(tx, ty, e);
  closeWrit();
});
window.addEventListener('pointermove', e => {
  if (stroke) { stroke.to = screenToTile(e); return; }
  if (!drag) return;
  camera.x += e.clientX - drag.x; camera.y += e.clientY - drag.y;
  drag = { x: e.clientX, y: e.clientY };
});
canvas.addEventListener('wheel', e => {
  e.preventDefault();
  camera.zoom = Math.max(0.45, Math.min(2.4, camera.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
}, { passive: false });

canvas.addEventListener('mousemove', e => {
  if (!plan || mode !== 'town') return;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const px = (e.clientX - w / 2 - camera.x) / camera.zoom + (plan.w - plan.h) * TW / 4;
  const py = (e.clientY - h / 2 - camera.y) / camera.zoom + (plan.w + plan.h) * TH / 4;
  let best = null, bestD = 42;
  for (const b of plan.buildings) {
    const [sx, sy] = iso(b.x, b.y);
    const d = Math.hypot(sx - px, (sy - py) * 1.9);
    if (d < bestD) { bestD = d; best = b; }
  }
  const tip = document.getElementById('tip');
  if (best) {
    const how = !best.complete ? 'being built'
      : best.burning ? 'on fire' : best.running ? 'working' : 'idle';
    tip.innerHTML = `<b>${best.name}</b> — ${how}`;
    tip.style.left = (e.clientX + 14) + 'px';
    tip.style.top = (e.clientY + 14) + 'px';
    tip.hidden = false;
  } else tip.hidden = true;
  hover = best;
});

/* -------------------------------------------------------------------- data */
/* A number that moved is the only number worth looking at after a month has
 * passed. It says so for a second and then stops, because a panel where
 * everything is always highlighted highlights nothing. */
const wasShowing = {};
function show(id, text) {
  const el = $(id);
  if (el.textContent === text) return;
  if (wasShowing[id] !== undefined) {
    el.classList.remove('moved');
    void el.offsetWidth;                 // restart the animation, not queue it
    el.classList.add('moved');
  }
  wasShowing[id] = text;
  el.textContent = text;
}

function meter(el, frac, warnAt, badAt) {
  el.classList.toggle('warn', frac < warnAt);
  el.classList.toggle('bad', frac < badAt);
  el.firstElementChild.style.width = Math.max(0, Math.min(100, frac * 100)) + '%';
}

function paint(s) {
  const wasAge = state && state.age;
  state = s; plan = s.plan;
  if (window.Sound) {
    Sound.feed(s);
    // A bell for the things worth stopping to hear.
    if (wasAge && s.age !== wasAge) Sound.mark('bell');
    if (s.over) Sound.mark('bell');
  }
  paintDrawbar(s);
  $('place').textContent = s.town.name;
  // A browser tab full of identical "Marchlands" is no use to anyone playing
  // two chapters at once.
  document.title = `${s.town.name} · Marchlands`;
  $('date').textContent = `${s.date} · ${s.age}`;
  show('purse', num(s.treasury) + 'c');
  show('souls', `${num(s.town.population)} of ${num(s.town.housing)} roofs`);
  // What the picture is showing, stated. A figure that stands for fourteen
  // people is only honest if the interface says it does.
  if (plan && plan.per_figure) {
    const watch = plan.folk.filter(f => f.kind === 'watch').length;
    const out = plan.folk.filter(f => f.kind === 'idle').length;
    $('scale').textContent =
      `one figure = ${plan.per_figure} souls · ${watch} on the wall ` +
      `(${plan.per_watch} men each)` + (out ? ` · ${out} with no work` : '');
  }
  meter($('moodbar'), s.town.popularity / 100, 0.45, 0.25);
  show('hands', `${num(s.town.employed)} of ${num(s.town.workforce)}`);
  meter($('wallbar'), s.town.wall_max ? s.town.wall_hp / s.town.wall_max : 0, 0.6, 0.3);
  show('soldiers', num(s.town.soldiers));
  $('mood').innerHTML = s.town.mood.map(m =>
    `<li><label>${m.what}</label><span class="${m.by > 0 ? 'up' : 'down'}">` +
    `${m.by > 0 ? '+' : ''}${m.by}</span></li>`).join('');
  const L = s.ledger;
  $('ledger').innerHTML = [['taxes', L.taxes], ['trade', L.trade], ['tribute', L.tribute],
                           ['wages', -L.wages], ['upkeep', -L.upkeep], ['net', L.net]]
    .map(([k, v]) => `<li><label>${k}</label><span class="${v >= 0 ? 'up' : 'down'}">` +
                     `${v >= 0 ? '+' : ''}${num(v)}</span></li>`).join('');
  // The table, and who has said they are coming. A league is a table and a
  // schedule; without them the march is eight lords quarrelling off-screen.
  const lea = s.league;
  if (lea && lea.table && lea.table.length) {
    $('standings').innerHTML = lea.table.map((r, i) =>
      `<li class="${r.me ? 'me' : ''}"><label>${i + 1}. ${r.name}</label>` +
      `<span>${r.towns} · ${r.won}-${r.lost}</span></li>`).join('');
    const at = (lea.fixtures || []).filter(f => f.at_you);
    const clock = $('clock');
    clock.textContent = at.length
      ? `${nameOf(at[0].who)} means to move on ${nameOf(at[0].target)}`
      : (lea.clock === 'player' && lea.left
         ? `you are on the clock — ${lea.left} left in the intake` : '');
    clock.className = at.length ? 'down' : 'dim';
    clock.hidden = !clock.textContent;
  }
  $('league').hidden = mode !== 'march' || !(lea && lea.table && lea.table.length);
  // The signature of the whole diplomatic layer: the moment the march stops
  // quarrelling with itself and starts counting together. It should not be
  // possible to have this happen to you and not notice.
  const ct = s.court || {};
  const signed = ct.coalition || [];
  $('letter').hidden = mode !== 'march' || !signed.length;
  if (signed.length) {
    $('signed').innerHTML = signed.map(k => {
      const t = (ct.towns || {})[k] || {};
      const left = Math.max(0, (t.offence || 0) - (ct.bar || 0));
      return `<li><label>${esc(t.name || k)}</label>` +
             `<span class="${left > 0 ? 'down' : 'up'}">${left > 0
               ? '+' + left.toFixed(0) + ' over' : 'cooling'}</span></li>`;
    }).join('');
    $('letter-out').textContent =
      `None of them will treat alone. It lapses as each falls under ` +
      `${(ct.bar || 0).toFixed(0)} of offence — beat their hosts, wait, ` +
      `or pay ${num(ct.price || 0)}c for the whole of it.`;
  }

  // The race, projected. A game whose result you only learn on the last day
  // is one you could not have played differently.
  const race = (s.pace || []).filter(r => r.now > 0);
  $('race').innerHTML = race.map(r => {
    const short = r.land < r.want * 0.995;
    return `<li><label>${r.what}</label><span class="${short ? 'down' : 'up'}">` +
      `${num(r.now)}<em>/${num(r.want)}</em> →${num(r.land)}</span></li>`;
  }).join('');
  $('racing').hidden = !race.length;

  // The house. A name, an age, and what the years in that job made of them --
  // which is the only reason to care which of them takes the seat.
  $('kinlist').innerHTML = (s.kin || []).map(p =>
    `<li class="kinrow${p.head ? ' head' : ''}"><label>${p.name}` +
    `<em>${p.age}</em></label><span>${p.skill || p.doing}</span></li>`).join('');
  const repute = $('repute');
  repute.textContent = (s.reputation || []).length
    ? 'they call him ' + s.reputation.join(', ') : '';
  repute.hidden = !repute.textContent;
  const alarm = $('alarm');
  const bad = s.town.besieged ? 'under siege' : s.town.raided ? 'the country is burning'
    : s.town.fires ? `${s.town.fires} roofs alight`
    : s.town.blockaded ? 'the roads are cut' : s.over ? s.over : '';
  alarm.textContent = bad; alarm.hidden = !bad;
  scrollCue();
}

/* A panel that quietly stops mid-list is a lie about what it is showing. When
 * there is more below the fold, the bottom edge says so. */
function scrollCue() {
  const el = $('panel');
  el.classList.toggle('more', el.scrollHeight - el.scrollTop - el.clientHeight > 4);
}
$('panel').addEventListener('scroll', scrollCue);

/* The console keeps everything; a toast catches the one line in a month that
 * you would have been sorry to scroll past. Only what the chronicle itself
 * thought was momentous -- the game already marks those with stars. */
function toast(text) {
  const bar = $('toasts');
  const li = document.createElement('li');
  li.textContent = text.replace(/^\*+\s*|\s*\*+$/g, '');
  bar.appendChild(li);
  requestAnimationFrame(() => li.classList.add('in'));
  setTimeout(() => {
    li.classList.remove('in');
    setTimeout(() => li.remove(), 600);
  }, 6000 + Math.min(4000, li.textContent.length * 40));
  while (bar.children.length > 4) bar.firstChild.remove();
}

function say(text, cls) {
  if (!text.trim()) return;
  const log = $('log');
  for (const line of text.replace(/\s+$/, '').split('\n')) {
    const li = document.createElement('li');
    li.textContent = line; if (cls) li.className = cls;
    log.appendChild(li);
    if (cls === 'said' && line.trim().startsWith('***')) toast(line.trim());
  }
  while (log.children.length > 220) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}

async function send(line) {
  say('> ' + line, 'you');
  const r = await fetch('/do', { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ line }) });
  const data = await r.json();
  if (data.said) say(data.said, 'said');
  if (data.state) paint(data.state);
  if (mode === 'march') loadMarch(); else loadOptions();
}

$('ask').addEventListener('submit', e => {
  e.preventDefault();
  const input = $('line'), line = input.value.trim();
  input.value = '';
  if (line) send(line);
});

function frameTown() {
  // Fit the view to what exists, so a small town is not a speck in a field.
  if (!plan) return;
  let x0 = plan.w, y0 = plan.h, x1 = 0, y1 = 0;
  const seen = (x, y) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y);
                           x1 = Math.max(x1, x); y1 = Math.max(y1, y); };
  for (const b of plan.buildings) seen(b.x, b.y);
  for (const w of plan.walls) seen(w.x, w.y);
  if (x1 < x0) { x0 = y0 = 0; x1 = plan.w - 1; y1 = plan.h - 1; }
  x0 -= 1; y0 -= 1; x1 += 1; y1 += 1;
  const wide = (x1 - x0 + y1 - y0) * TW / 2;
  const tall = (x1 - x0 + y1 - y0) * TH / 2 + 120;
  // What the furniture leaves for the picture. On a narrow screen the panel
  // lies along the bottom instead of standing at the side, so the room the
  // town gets is a different shape and the town has to be fitted to it.
  const vw = canvas.clientWidth - (NARROW() ? 34 : 300);
  const vh = canvas.clientHeight - (NARROW() ? 350 : 230);
  camera.zoom = Math.max(0.5, Math.min(1.9, Math.min(vw / wide, vh / tall)));
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const [mx, my] = iso(cx, cy);
  const [ox, oy] = [-(plan.w - plan.h) * TW / 4, -(plan.w + plan.h) * TH / 4];
  camera.x = (NARROW() ? 0 : 120) - (mx + ox) * camera.zoom;
  camera.y = (NARROW() ? -50 : -40) - (my + oy) * camera.zoom;
}

function setMode(next) {
  mode = next;
  for (const [id, m] of [['v-town', 'town'], ['v-march', 'march'],
                         ['v-castle', 'castle']])
    $(id).setAttribute('aria-pressed', String(mode === m));
  document.body.classList.toggle('march', mode === 'march');
  $('goodpick').hidden = mode !== 'march';
  $('trade').hidden = mode !== 'march';
  // The pencil is the town with your hands on it, so the town is still what
  // is drawn underneath -- only the click means something else.
  $('drawbar').hidden = mode !== 'castle';
  canvas.style.cursor = mode === 'castle' ? 'crosshair' : '';
  if (mode === 'castle') closeWrit();
  if (state) paint(state);
  $('tip').hidden = true;
  scrollCue();
  if (mode === 'march') loadMarch();
}
$('ear').addEventListener('click', () => {
  const on = Sound.toggle();
  $('ear').setAttribute('aria-pressed', String(!!on));
  if (on) say('The town has a sound now. It follows what is happening in it.');
});
$('v-town').addEventListener('click', () => setMode('town'));
$('v-march').addEventListener('click', () => setMode('march'));
$('v-castle').addEventListener('click', () =>
  setMode(mode === 'castle' ? 'town' : 'castle'));
$('good').addEventListener('change', e => { good = e.target.value; loadMarch(); });

const GOODS = ['bread', 'wheat', 'flour', 'ale', 'cheese', 'wool', 'cloth',
               'wood', 'planks', 'stone', 'clay', 'pottery', 'iron', 'tools',
               'weapons', 'armour', 'salt', 'spice', 'silk'];
$('good').innerHTML = GOODS.map(g =>
  `<option value="${g}"${g === good ? ' selected' : ''}>${g}</option>`).join('');

(async function boot() {
  resize();
  paint(await (await fetch('/state')).json());
  frameTown();
  loadOptions();
  loadCommands();
  say('Marchlands. Drag to move, scroll to zoom. Click a roof to do something '
      + 'with it, or an empty plot to raise something on it.');
  say('Type `hint` if you are not sure what to do next, or `help` for everything.');
  nextFrame();
  // The server decides whether anybody has chosen yet. A packaged build or a
  // bare `--web` opens on the front door; `--scenario iron_marches` does not,
  // because that player has already answered the only question it asks.
  doorman = await (await fetch('/front')).json();
  if (doorman.open) openFront(false);
})();


/* The wall, read back to whoever is drawing it. Four facts and no score:
 * how long it is, whether it is actually shut, what the towers cannot see,
 * and how many men are standing on each yard. */
function paintDrawbar(s) {
  const c = s.castle;
  if (!c) return;
  const hand = Object.entries(c.hand || {})
    .map(([k, v]) => `${v} ${k}`).join(', ');
  $('drawhand').textContent = hand ? `in hand: ${hand}` : 'nothing left in hand';
  const bits = [];
  bits.push(`<b>${c.yards}</b> yards`);
  if (!c.shut && c.yards) bits.push('<span class="bad">the ring is open</span>');
  bits.push(c.towers ? `towers cover <b>${c.covered}</b> of <b>${c.yards}</b>`
                     : '<span class="bad">no towers</span>');
  if (c.weak && c.weak.length)
    bits.push(`<span class="bad">${c.weak.length} yards on the ${c.side}` +
              ` nothing watches</span>`);
  bits.push(`<b>${c.per_yard}</b> men to the yard`);
  if (c.outside) bits.push(`<span class="bad">${c.outside} outside</span>`);
  if (c.depth > 1) bits.push(`<b>${c.depth}</b> walls deep`);
  $('drawread').innerHTML = bits.join(' &middot; ');
}


/* ------------------------------------------------------------- the country */
/* The dials, as dials. `--dials hills=0.8,marsh=0.3` on a command line is a
 * string, not a slider: you cannot feel what a number does by typing it. Here
 * the march redraws under your hand on every twitch, because drawing a country
 * is cheap and starting a game is not -- so the preview can be live and the
 * game is only made when you say so. */
let atlas = null, drawnPlan = null, drawSeed = 7, drawRegion = null;
const dialNow = {};

async function openCountry() {
  if (!atlas) atlas = await (await fetch('/regions')).json();
  if (!drawRegion) drawRegion = atlas.regions[0].key;
  buildRegions();
  pickRegion(drawRegion, true);
  $('drawmap').hidden = false;
}
function closeCountry() { $('drawmap').hidden = true; }

function buildRegions() {
  $('regionpick').innerHTML = atlas.regions.map(r =>
    `<button type="button" data-region="${r.key}" aria-pressed="false">` +
    `${esc(r.name)}</button>`).join('');
  for (const b of $('regionpick').querySelectorAll('[data-region]'))
    b.addEventListener('click', () => pickRegion(b.dataset.region, true));
}

function pickRegion(key, reset) {
  drawRegion = key;
  const reg = atlas.regions.find(r => r.key === key);
  for (const b of $('regionpick').querySelectorAll('[data-region]'))
    b.setAttribute('aria-pressed', String(b.dataset.region === key));
  $('drawmap-note').textContent = reg.note;
  if (reset) {
    for (const name of atlas.dials) dialNow[name] = reg.dials[name];
    buildDials();
  }
  redrawCountry();
}

function buildDials() {
  $('dialbank').innerHTML = atlas.dials.map(name => {
    const towns = name === 'towns';
    return `<div class="dial">
      <label for="d-${name}">${name}</label>
      <input id="d-${name}" type="range" data-dial="${name}"
             min="${towns ? 3 : 0}" max="${towns ? 12 : 1}"
             step="${towns ? 1 : 0.01}" value="${dialNow[name]}">
      <output id="o-${name}"></output>
    </div>`;
  }).join('');
  for (const el of $('dialbank').querySelectorAll('[data-dial]')) {
    el.addEventListener('input', () => {
      dialNow[el.dataset.dial] = parseFloat(el.value);
      redrawCountry();
    });
  }
}

let drawPending = null;
function redrawCountry() {
  clearTimeout(drawPending);
  drawPending = setTimeout(async () => {
    const q = new URLSearchParams({ region: drawRegion, seed: drawSeed });
    for (const [k, v] of Object.entries(dialNow)) q.set(k, v);
    const plan = await (await fetch('/draw?' + q)).json();
    if (plan.error) return;
    drawnPlan = plan;
    for (const w of plan.words) {
      const out = document.getElementById('o-' + w.dial);
      if (out) out.textContent = w.says;
    }
    $('drawmap-says').textContent =
      `${plan.home.name}, and ${plan.towns.length} neighbours. ` + plan.note;
    $('drawmap-towns').innerHTML = plan.towns.map(t =>
      `<li><b>${esc(t.name)}</b><span>${esc(t.sells.join(', ') || 'little')}` +
      `${t.port ? ' · a harbour' : ''}</span></li>`).join('');
    paintCountry(plan);
  }, 60);
}

/* The march itself: the seat in the middle, the neighbours where the spread
 * put them, sized by their walls and coloured by the idiom their own ground
 * builds in -- so a glance at the preview tells you what kind of country it
 * is before you have read a word of it. */
const IDIOM_INK = { march: '#9a7a4a', hansa: '#a8563f', abbey: '#9aa0a8',
                    vale: '#c9bb8a', ironhand: '#78796e' };
function paintCountry(plan) {
  const c = $('drawmap-view'), g = c.getContext('2d');
  const W = c.width, H = c.height;
  g.clearRect(0, 0, W, H);
  g.fillStyle = '#1a1712'; g.fillRect(0, 0, W, H);
  const pts = plan.towns.concat(plan.sites, plan.shrines, [{ x: 0, y: 0 }]);
  const far = Math.max(40, ...pts.map(p => Math.max(Math.abs(p.x), Math.abs(p.y))));
  const k = Math.min(W, H) / (2.35 * far);
  const at = p => [W / 2 + p.x * k, H / 2 + p.y * k];
  g.strokeStyle = 'rgba(201,162,39,.13)'; g.lineWidth = 1;
  for (const t of plan.towns) {
    const [x, y] = at(t), [hx, hy] = at({ x: 0, y: 0 });
    g.beginPath(); g.moveTo(hx, hy); g.lineTo(x, y); g.stroke();
  }
  for (const s of plan.shrines) {
    const [x, y] = at(s);
    g.strokeStyle = 'rgba(216,201,168,.5)'; g.lineWidth = 1.4;
    g.beginPath(); g.moveTo(x, y - 4); g.lineTo(x, y + 4);
    g.moveTo(x - 3, y - 1); g.lineTo(x + 3, y - 1); g.stroke();
  }
  for (const s of plan.sites) {
    const [x, y] = at(s);
    g.strokeStyle = 'rgba(143,184,106,.6)'; g.lineWidth = 1.2;
    g.beginPath(); g.arc(x, y, 4, 0, 7); g.stroke();
  }
  for (const t of plan.towns) {
    const [x, y] = at(t);
    const r = 4 + Math.min(7, t.walls / 170);
    g.fillStyle = IDIOM_INK[t.culture] || '#9a7a4a';
    g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
    if (t.port) {
      g.strokeStyle = 'rgba(122,164,196,.85)'; g.lineWidth = 1.4;
      g.beginPath(); g.arc(x, y, r + 3, 0, 7); g.stroke();
    }
    g.fillStyle = '#a8a08c'; g.font = '10px ui-sans-serif, system-ui';
    g.textAlign = 'center';
    g.fillText(t.name, x, y - r - 4);
  }
  const [hx, hy] = at({ x: 0, y: 0 });
  g.fillStyle = 'var(--gold)'; g.fillStyle = '#c9a227';
  g.beginPath();
  g.moveTo(hx, hy - 8); g.lineTo(hx + 7, hy); g.lineTo(hx, hy + 8);
  g.lineTo(hx - 7, hy); g.closePath(); g.fill();
  g.fillStyle = '#e8dcc0'; g.font = '11px ui-sans-serif, system-ui';
  g.fillText(plan.home.name, hx, hy + 21);
}

$('v-draw').addEventListener('click', openCountry);
$('drawmap-close').addEventListener('click', closeCountry);
$('drawmap').addEventListener('click', e => {
  if (e.target === $('drawmap')) closeCountry();
});
$('reseed').addEventListener('click', () => {
  drawSeed = Math.floor(Math.random() * 99999);
  redrawCountry();
});
$('drawgo').addEventListener('click', async () => {
  const body = Object.assign({ region: drawRegion, seed: drawSeed }, dialNow);
  const out = await (await fetch('/march-here', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })).json();
  if (out.error) return say(out.error);
  closeCountry();
  ground = null;                     // a different country: bake it again
  paint(out.state);
  frameTown();
  say(out.said);
});


/* ------------------------------------------------------------- a skyline */
/* Three roofs of somebody else's town, drawn in their idiom. The whole point
 * of five architecture sets is recognising a place from its roofline, and
 * that only works if you are ever shown one that is not your own. */
const SKYLINE_KEYS = ['townhouse', 'guildhall', 'cottage', 'inn'];
function drawSkyline(canvas, cultureKey) {
  const set = (state && state.idioms && state.idioms[cultureKey]) || null;
  if (!set) return;
  const g = canvas.getContext('2d');
  const W = canvas.width / dpr, H = canvas.height / dpr;
  const keepCtx = ctx, keepForce = forceIdiom, keepCache = {};
  for (const k in STYLE_CACHE) keepCache[k] = STYLE_CACHE[k];
  ctx = g;
  forceIdiom = set;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  ctx.save();
  ctx.translate(W / 2, H * 0.72);
  ctx.scale(0.92, 0.92);
  // Four roofs in a short street, back to front, so the near one overlaps the
  // far one the way a street does. Four rather than five: a strip this size
  // wants the roofs big enough to tell a hipped one from a crow-stepped one,
  // which is the entire reason it is here.
  const row = [[-1, -1], [1, -1], [-1, 1], [1, 1]];
  const things = row.map((p, i) => ({ d: p[0] + p[1], p, i }));
  things.sort((a, b) => a.d - b.d);
  for (const t of things) {
    drawBuilding({
      x: t.p[0], y: t.p[1], key: SKYLINE_KEYS[t.i % SKYLINE_KEYS.length],
      name: '', complete: true, running: true, idle: false, burning: false,
      terrain: 'urban', category: 'civic', uid: -1 - t.i,
    }, 0);
  }
  ctx.restore();
  ctx = keepCtx;
  forceIdiom = keepForce;
  for (const k in STYLE_CACHE) delete STYLE_CACHE[k];
  for (const k in keepCache) STYLE_CACHE[k] = keepCache[k];
}


/* ----------------------------------------------------------- the front door */
/* Everything a person who double-clicked an icon needs before they can play:
 * who they are, where they are, and whether there is a game to pick back up.
 * These three were console commands, which is fine for somebody who opened a
 * terminal on purpose and no use at all to somebody who did not. */
let doorman = null, pickedHouse = 'plough', pickedWhere = 'scenario:marchlands';

async function openFront(manual) {
  if (!doorman) doorman = await (await fetch('/front')).json();
  else doorman.saved = (await (await fetch('/front')).json()).saved;
  $('front-resume').hidden = !doorman.saved;
  $('front-close').hidden = !manual;
  buildHouses();
  buildWheres();
  $('front').hidden = false;
}
function closeFront() { $('front').hidden = true; }

function buildHouses() {
  $('housepick').innerHTML = doorman.houses.map(h =>
    `<button type="button" data-house="${h.key}" aria-pressed="false">` +
    `${esc(h.name)}</button>`).join('');
  for (const b of $('housepick').children) {
    b.addEventListener('click', () => pickHouse(b.dataset.house));
  }
  pickHouse(pickedHouse);
}
function pickHouse(key) {
  pickedHouse = key;
  const h = doorman.houses.find(x => x.key === key) || doorman.houses[0];
  for (const b of $('housepick').children) {
    b.setAttribute('aria-pressed', b.dataset.house === key ? 'true' : 'false');
  }
  $('house-note').textContent = h ? h.blurb : '';
}

/* One row, two kinds of thing. A scenario is a written game with an ending;
 * a region is a real place the map is drawn from. Keeping them apart on the
 * screen would be truer to the code and worse to use -- from the player's
 * side both answer the same question, which is where. */
function buildWheres() {
  const bits = doorman.scenarios.map(s =>
    `<button type="button" data-where="scenario:${s.key}" aria-pressed="false">` +
    `${esc(s.name)}</button>`).concat(doorman.regions.map(r =>
    `<button type="button" data-where="region:${r.key}" aria-pressed="false">` +
    `${esc(r.name)}</button>`));
  $('wherepick').innerHTML = bits.join('');
  for (const b of $('wherepick').children) {
    b.addEventListener('click', () => pickWhere(b.dataset.where));
  }
  pickWhere(pickedWhere);
}
function pickWhere(key) {
  pickedWhere = key;
  const [kind, name] = key.split(':');
  const it = kind === 'scenario'
    ? doorman.scenarios.find(s => s.key === name)
    : doorman.regions.find(r => r.key === name);
  for (const b of $('wherepick').children) {
    b.setAttribute('aria-pressed', b.dataset.where === key ? 'true' : 'false');
  }
  if (!it) return;
  $('where-note').textContent = kind === 'scenario'
    ? `${it.blurb} — ${it.years} years to see it through.`
    : `${it.note} Drawn from the real country; the dials change it.`;
}

/* Swapping in a new game means the baked ground is a picture of somewhere
 * else, so it has to go. Forgetting this leaves the old country's fields
 * underneath the new country's town. */
function enter(out) {
  if (out.error) { say(out.error); return false; }
  closeFront();
  ground = null;
  paint(out.state);
  frameTown();
  say(out.said);
  return true;
}

async function post(route, body) {
  return (await (await fetch(route, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  })).json());
}

$('front-go').addEventListener('click', async () => {
  const [kind, name] = pickedWhere.split(':');
  const body = { house: pickedHouse, seed: Math.floor(Math.random() * 99999) };
  body[kind] = name;
  enter(await post('/new', body));
});
$('front-continue').addEventListener('click', async () => {
  enter(await post('/load', {}));
});
$('front-close').addEventListener('click', closeFront);
$('front-dials').addEventListener('click', () => { closeFront(); openCountry(); });
$('v-menu').addEventListener('click', () => openFront(true));
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('front').hidden && !$('front-close').hidden) {
    closeFront();
  }
});

/* Save and load as buttons rather than typed words. The command still exists
 * and still works; this is the same thing for somebody who never learned it. */
$('v-save').addEventListener('click', async () => {
  const out = await post('/save', {});
  say(out.error || out.said, out.error ? null : 'said');
  if (!out.error) toast('*** the chronicle is written down ***');
});
$('v-load').addEventListener('click', async () => {
  const out = await post('/load', {});
  if (!out.error) enter(out); else say(out.error);
});


/* --------------------------------------------------------------- a person */
/* What clicking somebody says. Every line of it is read off the town by the
 * server -- who they are, the roof they sleep under, the shed they walk to,
 * whether they were paid -- because a panel that invented any of it would be
 * the one place in this game where the picture and the ledger disagreed.
 *
 * The scale is stated rather than hidden. Fourteen souls is what a figure is;
 * pretending otherwise to make it feel like a villager would be the lie. The
 * few who are one person are your own, and those you can give a job to. */
let soulNow = null;

async function openSoul(i) {
  closeWrit();
  const d = await (await fetch(`/folk?i=${i}`)).json();
  if (d.error) return say(d.error);
  soulNow = d;
  paintSoul(d);
  $('soul').hidden = false;
}
function closeSoul() { $('soul').hidden = true; soulNow = null; }

function paintSoul(d) {
  const mine = d.kind === 'kin';
  $('soul-name').textContent = d.title || 'somebody';
  $('soul-doing').textContent = d.doing || '';
  $('soul-count').textContent = mine ? 'one of yours'
    : `one figure · ${d.souls} ${d.kind === 'watch' ? 'men' : 'souls'}`;
  $('soul-count').classList.toggle('mine', mine);

  const rows = [];
  if (d.home) rows.push(['sleeps at', d.home]);
  if (d.work && !mine) rows.push(['works at', d.work]);
  if (d.work && mine) rows.push(['stands at', d.work]);
  for (const f of d.facts || []) rows.push([f.k, f.v]);
  $('soul-facts').innerHTML = rows.map(([k, v]) =>
    `<li><span class="dim">${esc(k)}</span><span>${esc(v)}</span></li>`).join('');

  $('soul-said').textContent = d.said || '';
  $('soul-said').hidden = !d.said;

  const p = d.person;
  $('soul-person').hidden = !p;
  if (p) {
    $('soul-age').textContent = `${p.age} years old`;
    $('soul-skills').innerHTML = (p.skills.length ? p.skills : [])
      .map(sk => `<li>${esc(sk.skill)} <b>${sk.level}</b></li>`).join('')
      || '<li class="dim">nothing learned yet</li>';
  }

  // The jobs, as buttons. `post` is still the command that runs; this only
  // saves somebody typing it, which is the whole point of the exercise.
  $('soul-posts').hidden = !mine;
  if (!mine) $('soul-posts').innerHTML = '';
  if (mine) {
    const held = d.person ? d.person.post : '';
    // The target matters: a steward governs a named town and a captain rides
    // with a named host. Sent blank, the first resolves to whichever town
    // happens to come first rather than the one you are looking at, and the
    // second fails. The server says what each post needs and what to send.
    $('soul-posts').innerHTML =
      '<h4>give them a different job</h4><div class="pickrow">' +
      (d.posts || []).map(q =>
        `<button type="button" data-post="${q.key}" data-target="${q.target}"` +
        ` title="${esc(q.can ? q.blurb : q.why)}"${q.can ? '' : ' disabled'}` +
        ` aria-pressed="${q.key === held ? 'true' : 'false'}">` +
        `${esc(q.key)}${q.held && q.key !== held ? ' \u00b7' : ''}</button>`).join('') +
      '<button type="button" data-post="none" data-target="">call them home' +
      '</button></div>' +
      '<p class="dim">a dot means one of yours already holds it — ' +
      'everybody can only be in one place</p>';
    const first = (d.person ? d.person.name : d.title).split(' ')[0];
    for (const b of $('soul-posts').querySelectorAll('button')) {
      b.addEventListener('click', async () => {
        await send(`post ${first} ${b.dataset.post} ${b.dataset.target}`.trim());
        closeSoul();
      });
    }
  }
}

$('soul-close').addEventListener('click', closeSoul);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && !$('soul').hidden) closeSoul();
});


/* ------------------------------------------------------------- a host */
/* Clicking a pennon. The same panel the town figures use, because a host is
 * the same kind of question -- who is that, what are they doing, and can I
 * tell them to do something else -- and one answer shape is easier to read
 * than two.
 *
 * Yours gets orders. Theirs gets what you actually know, which on a
 * remembered sighting is a date and not much else. */
let sending = null;

function openHost(h) {
  closeWrit();
  soulNow = null;
  $('soul-name').textContent = h.name;
  $('soul-count').textContent = h.mine ? 'one of your hosts'
    : (h.state === 'remembered' ? `last seen ${h.stale} days ago`
       : `${h.owner}'s, and in sight`);
  $('soul-count').classList.toggle('mine', h.mine);
  $('soul-doing').textContent = hostDoing(h);

  const rows = [['strength', `${h.size} men`]];
  if (h.captain) rows.push(['led by', h.captain]);
  if (h.mine) {
    for (const [k, n] of Object.entries(h.units || {})) {
      rows.push([k.replace(/_/g, ' '), String(n)]);
    }
    rows.push(['costing', `${h.upkeep}c a day`]);
  }
  if (h.state === 'besieging' && h.siege_days) {
    rows.push(['sat down', `${h.siege_days} days`]);
  }
  if (h.state === 'remembered') {
    rows.push(['where', `near ${nodeName(h.at)}`]);
    rows.push(['since then', 'anywhere within a few days’ march']);
  }
  $('soul-facts').innerHTML = rows.map(([k, v]) =>
    `<li><span class="dim">${esc(k)}</span><span>${esc(v)}</span></li>`).join('');

  $('soul-said').hidden = true;
  $('soul-person').hidden = true;
  // Emptied, not just hidden. A panel that keeps the last host's orders in
  // its markup is one stylesheet change away from offering you the recall of
  // somebody else's army.
  $('soul-posts').hidden = !h.mine;
  if (!h.mine) $('soul-posts').innerHTML = '';
  if (h.mine) {
    $('soul-posts').innerHTML =
      '<h4>orders</h4><div class="pickrow">' +
      `<button type="button" data-host="march">march to…</button>` +
      `<button type="button" data-host="recall">recall</button>` +
      `<button type="button" data-host="siege">lay siege</button>` +
      `<button type="button" data-host="disband">disband</button>` +
      '</div><p class="dim">the same orders you can type, and they go through ' +
      'the same commands</p>';
    for (const b of $('soul-posts').querySelectorAll('button')) {
      b.addEventListener('click', () => {
        const what = b.dataset.host;
        closeSoul();
        if (what === 'march') {
          // Pick the place next. A destination cannot be guessed from here.
          sending = h.uid;
          canvas.style.cursor = 'crosshair';
          return say('now click where it should march.');
        }
        send(`${what} ${h.uid}`);
      });
    }
  }
  $('soul').hidden = false;
}

function hostDoing(h) {
  if (h.state === 'marching') {
    return `marching on ${nodeName(h.to)}, ${h.days_left} days out`;
  }
  if (h.state === 'besieging') return `sitting before ${nodeName(h.at)}`;
  if (h.state === 'raiding') return `burning the country around ${nodeName(h.at)}`;
  if (h.state === 'remembered') return 'you have not seen it since';
  return `standing at ${nodeName(h.at)}`;
}

function nodeName(key) {
  const n = world && world.nodes.find(q => q.key === key);
  return n ? n.name : (key || 'somewhere');
}

/* Escape gives up on picking a destination as well as closing the panel. */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && sending !== null) {
    sending = null;
    canvas.style.cursor = '';
    say('the host stays where it is.');
  }
});
