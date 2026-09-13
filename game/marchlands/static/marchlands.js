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
const ctx = canvas.getContext('2d');

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
const styleOf = k => STYLE[k] || STYLE.default;

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
function poly(pts, fill, stroke) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke(); }
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
  else if (kind === 'water') base = p.water;
  else if (kind === 'road') base = shade(p.earth, 1.32);
  else if (kind === 'yard') base = shade(p.earth, 1.18);
  const tint = 0.94 + 0.12 * rnd(x, y, 1);
  poly(d, shade(base, tint));

  if (kind === 'field') {
    // Furrows, running the same way across the whole field.
    ctx.strokeStyle = shade(base, 0.82);
    ctx.lineWidth = 1;
    for (let i = 1; i < 5; i++) {
      const f = i / 5;
      ctx.beginPath();
      ctx.moveTo(sx - TW / 2 + f * TW / 2, sy - f * TH / 2);
      ctx.lineTo(sx + f * TW / 2, sy + TH / 2 - f * TH / 2);
      ctx.stroke();
    }
  } else if (kind === 'grass' && rnd(x, y, 2) > 0.55) {
    ctx.strokeStyle = shade(base, 0.78);
    ctx.lineWidth = 1;
    for (let i = 0; i < 3; i++) {
      const bx = sx + (rnd(x, y, i + 3) - 0.5) * TW * 0.5;
      const by = sy + (rnd(x, y, i + 7) - 0.5) * TH * 0.5;
      ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx + 1, by - 3); ctx.stroke();
    }
  } else if (kind === 'water') {
    const t = clock();
    ctx.strokeStyle = 'rgba(255,255,255,.20)';
    ctx.lineWidth = 1;
    for (let i = 0; i < 2; i++) {
      const wy = sy + (i - 0.5) * 9 + Math.sin(t * 1.4 + x + y + i) * 2.2;
      ctx.beginPath();
      ctx.moveTo(sx - 13, wy); ctx.quadraticCurveTo(sx, wy - 2.5, sx + 13, wy);
      ctx.stroke();
    }
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
    ctx.fillStyle = 'rgba(20,30,12,.20)';
    ctx.beginPath(); ctx.ellipse(tx, ty + 1, 9, 4, 0, 0, 7); ctx.fill();
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
  if (kind === 'stone') {
    ctx.strokeStyle = 'rgba(0,0,0,.18)'; ctx.lineWidth = 1;
    for (let yy = y0; yy < y1; yy += 6) {
      ctx.beginPath(); ctx.moveTo(x0, yy); ctx.lineTo(x1, yy + (x1 - x0) * 0.16); ctx.stroke();
      for (let xx = x0 + ((yy / 6) % 2) * 9; xx < x1; xx += 18) {
        ctx.beginPath(); ctx.moveTo(xx, yy + (xx - x0) * 0.16);
        ctx.lineTo(xx, yy + 6 + (xx - x0) * 0.16); ctx.stroke();
      }
    }
  } else if (kind === 'timber') {
    ctx.strokeStyle = 'rgba(58,40,24,.75)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x0, (y0 + y1) / 2); ctx.lineTo(x1, (y0 + y1) / 2 + 5);
    ctx.stroke();
    for (let xx = x0 + 5; xx < x1; xx += 11) {
      ctx.beginPath(); ctx.moveTo(xx, y0); ctx.lineTo(xx + 2, y1); ctx.stroke();
    }
  } else if (kind === 'plank') {
    ctx.strokeStyle = 'rgba(48,34,20,.45)'; ctx.lineWidth = 1;
    for (let xx = x0 + 4; xx < x1; xx += 7) {
      ctx.beginPath(); ctx.moveTo(xx, y0); ctx.lineTo(xx + 2, y1); ctx.stroke();
    }
  }
  ctx.restore();
}

function thatch(a, b, c, d, colour) {
  poly([a, b, c, d], colour);
  ctx.strokeStyle = shade(colour, 0.8); ctx.lineWidth = 1;
  for (let i = 1; i < 6; i++) {
    const f = i / 6;
    const p1 = [a[0] + (d[0] - a[0]) * f, a[1] + (d[1] - a[1]) * f];
    const p2 = [b[0] + (c[0] - b[0]) * f, b[1] + (c[1] - b[1]) * f];
    ctx.beginPath(); ctx.moveTo(p1[0], p1[1]);
    ctx.quadraticCurveTo((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 - 1.5, p2[0], p2[1]);
    ctx.stroke();
  }
}

function tiles(a, b, c, d, colour) {
  poly([a, b, c, d], colour);
  ctx.strokeStyle = 'rgba(0,0,0,.22)'; ctx.lineWidth = 1;
  for (let i = 1; i < 5; i++) {
    const f = i / 5;
    ctx.beginPath();
    ctx.moveTo(a[0] + (d[0] - a[0]) * f, a[1] + (d[1] - a[1]) * f);
    ctx.lineTo(b[0] + (c[0] - b[0]) * f, b[1] + (c[1] - b[1]) * f);
    ctx.stroke();
  }
}

/* --------------------------------------------------------------- buildings */
function drawBuilding(b, t) {
  const st = styleOf(b.key);
  const [sx, sy] = iso(b.x, b.y);
  if (st.roof === 'trees') { drawTrees(b.x, b.y); return; }

  const w = st.w / 2, d = (st.w / 2) * (TH / TW);
  const h = 22 * st.s;
  if (!b.complete) { drawScaffold(sx, sy, w, d, h); return; }

  // Ground shadow, so nothing floats.
  ctx.fillStyle = 'rgba(0,0,0,.22)';
  ctx.beginPath(); ctx.ellipse(sx, sy + 3, w * 0.95, d * 0.95, 0, 0, 7); ctx.fill();

  if (st.wall === 'pit') { drawPit(sx, sy, w, d, st); return; }

  const T = [sx, sy - d - h], L = [sx - w, sy - h];
  const R = [sx + w, sy - h], B = [sx, sy + d - h];
  const bl = [sx - w, sy], bb = [sx, sy + d], br = [sx + w, sy];

  wallFace([L, bl, bb, B], shade(st.c, 0.62), st.wall);      // south-west face
  wallFace([B, bb, br, R], shade(st.c, 0.80), st.wall);      // south-east face
  drawOpenings(sx, sy, w, d, h, st, b);

  const rise = st.roof === 'tile' ? 13 : st.roof === 'thatch' ? 17 : 9;
  const M1 = [sx - w / 2, sy - d / 2 - h - rise];
  const M2 = [sx + w / 2, sy + d / 2 - h - rise];

  if (st.roof === 'thatch' || st.roof === 'tile' || st.roof === 'plankroof') {
    const colour = st.roof === 'thatch' ? '#b8994f'
      : st.roof === 'tile' ? '#8c4a35' : '#7d6242';
    poly([T, M1, L], shade(colour, 0.68));                    // gable ends
    poly([R, M2, B], shade(colour, 0.68));
    if (st.roof === 'thatch') {
      thatch(T, M1, M2, R, shade(colour, 1.05));
      thatch(L, M1, M2, B, shade(colour, 0.78));
    } else {
      tiles(T, M1, M2, R, shade(colour, 1.05));
      tiles(L, M1, M2, B, shade(colour, 0.76));
    }
    // The ridge, and the overhang that stops it looking like a wedge.
    ctx.strokeStyle = shade(colour, 0.6); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(M1[0], M1[1]); ctx.lineTo(M2[0], M2[1]); ctx.stroke();
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
  ctx.fillStyle = 'rgba(0,0,0,.22)';
  ctx.beginPath(); ctx.ellipse(sx, sy + 2, hw * 0.9, hd * 0.9, 0, 0, 7); ctx.fill();
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
function drawFolk(f, i, t) {
  // They walk the road they were put on, up and back, at their own pace.
  const swing = Math.sin(t * 0.55 + i * 1.7);
  const [sx, sy] = iso(f.x + swing * 0.35, f.y + Math.cos(t * 0.4 + i) * 0.2);
  const bob = Math.abs(Math.sin(t * 3.1 + i)) * 1.6;
  ctx.fillStyle = 'rgba(0,0,0,.2)';
  ctx.beginPath(); ctx.ellipse(sx, sy + 1, 3.4, 1.6, 0, 0, 7); ctx.fill();
  const coat = ['#7a5a3c', '#6a6450', '#8a6a4a', '#5c5442'][i % 4];
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

function drawSky(w, h, t) {
  const p = pal();
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, p.sky[0]); g.addColorStop(1, p.sky[1]);
  ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  // The sun crosses with the months, which is all the clock a year needs.
  const frac = ((state ? state.month : 6) - 1) / 12;
  const sunx = w * (0.12 + 0.76 * frac), suny = h * (0.30 - 0.14 * Math.sin(frac * Math.PI));
  const halo = ctx.createRadialGradient(sunx, suny, 4, sunx, suny, 90);
  halo.addColorStop(0, p.sun); halo.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = halo;
  ctx.beginPath(); ctx.arc(sunx, suny, 90, 0, 7); ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,.40)';
  for (let i = 0; i < 5; i++) {
    const cx = ((i * 331 + t * (7 + i * 2)) % (w + 340)) - 170;
    const cy = 40 + i * 33 + Math.sin(i) * 12;
    for (let k = 0; k < 3; k++) {
      ctx.beginPath();
      ctx.ellipse(cx + k * 27, cy + (k === 1 ? -7 : 0), 30 - k * 4, 13, 0, 0, 7);
      ctx.fill();
    }
  }
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
  openWrit(b.name, `
    <p>${how}${b.terrain === 'urban' ? ' · inside the wall' : ''}</p>
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
  const acts = n.kind === 'town' ? `
    <div class="acts">
      ${idle ? `<button data-do="auto ${idle.uid}">put ${idle.name} on the best run</button>` : ''}
      <button data-do="scan">what is worth carrying</button>
      <button data-do="gift ${n.key} 500">gift 500c</button>
      <button data-do="truce ${n.key}">ask for a truce</button>
    </div>` : n.kind === 'site' ? `
    <div class="acts"><button data-do="found ${n.key}">settle it</button></div>` : '';
  openWrit(n.name, price + (known ? `<p class="why">${known}</p>` : '') + acts, ev);
}

for (const btn of document.querySelectorAll('#clock button')) {
  btn.addEventListener('click', () => send(btn.dataset.do));
}

/* ------------------------------------------------------------------ frame */
function frame() {
  const t = clock();
  const w = canvas.width / dpr, h = canvas.height / dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (mode === 'march') {
    drawMarch(w, h, t);
    nextFrame();
    return;
  }
  drawSky(w, h, t);
  if (plan) {
    ctx.save();
    ctx.translate(w / 2 + camera.x, h / 2 + camera.y);
    ctx.scale(camera.zoom, camera.zoom);
    ctx.translate(-(plan.w - plan.h) * TW / 4, -(plan.w + plan.h) * TH / 4);
    for (let y = 0; y < plan.h; y++)
      for (let x = 0; x < plan.w; x++) drawTile(x, y, plan.tiles[y][x]);
    // Everything that stands up, painted back to front.
    const things = [];
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
    for (const it of things) {
      if (it.kind === 'wood') drawTrees(it.x, it.y);
      else if (it.kind === 'b') drawBuilding(it.b, t);
      else if (it.kind === 'w') drawWall(it.w, t);
      else if (it.kind === 'h') drawHaul(it.h, it.i, t, it.at, it.pos);
      else drawFolk(it.f, it.i, t);
    }
    drawEffects(t);
    ctx.restore();
  }
  drawWeather(w, h, t);
  nextFrame();
}
/* Still means still: one redraw every so often is enough to pick up a new day. */
function nextFrame() {
  if (STILL) setTimeout(frame, 500); else requestAnimationFrame(frame);
}

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

let drag = null, pressed = null;
canvas.addEventListener('pointerdown', e => {
  drag = { x: e.clientX, y: e.clientY };
  pressed = { x: e.clientX, y: e.clientY, t: performance.now() };
});
window.addEventListener('pointerup', e => {
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
    const n = townNodeAt(e);
    return n ? nodeWrit(n, e) : closeWrit();
  }
  if (!plan) return;
  const b = buildingAt(e);
  if (b) return buildingWrit(b, e);
  const [tx, ty] = screenToTile(e);
  const p = plan.precinct;
  if (tx >= p.x0 && tx <= p.x1 && ty >= p.y0 && ty <= p.y1) return plotWrit(tx, ty, e);
  closeWrit();
});
window.addEventListener('pointermove', e => {
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
  $('place').textContent = s.town.name;
  // A browser tab full of identical "Marchlands" is no use to anyone playing
  // two chapters at once.
  document.title = `${s.town.name} · Marchlands`;
  $('date').textContent = `${s.date} · ${s.age}`;
  $('purse').textContent = num(s.treasury) + 'c';
  $('souls').textContent = `${num(s.town.population)} of ${num(s.town.housing)} roofs`;
  meter($('moodbar'), s.town.popularity / 100, 0.45, 0.25);
  $('hands').textContent = `${num(s.town.employed)} of ${num(s.town.workforce)}`;
  meter($('wallbar'), s.town.wall_max ? s.town.wall_hp / s.town.wall_max : 0, 0.6, 0.3);
  $('soldiers').textContent = num(s.town.soldiers);
  $('mood').innerHTML = s.town.mood.map(m =>
    `<li><label>${m.what}</label><span class="${m.by > 0 ? 'up' : 'down'}">` +
    `${m.by > 0 ? '+' : ''}${m.by}</span></li>`).join('');
  const L = s.ledger;
  $('ledger').innerHTML = [['taxes', L.taxes], ['trade', L.trade], ['tribute', L.tribute],
                           ['wages', -L.wages], ['upkeep', -L.upkeep], ['net', L.net]]
    .map(([k, v]) => `<li><label>${k}</label><span class="${v >= 0 ? 'up' : 'down'}">` +
                     `${v >= 0 ? '+' : ''}${num(v)}</span></li>`).join('');
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

function say(text, cls) {
  if (!text.trim()) return;
  const log = $('log');
  for (const line of text.replace(/\s+$/, '').split('\n')) {
    const li = document.createElement('li');
    li.textContent = line; if (cls) li.className = cls;
    log.appendChild(li);
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
  for (const [id, m] of [['v-town', 'town'], ['v-march', 'march']])
    $(id).setAttribute('aria-pressed', String(mode === m));
  document.body.classList.toggle('march', mode === 'march');
  $('goodpick').hidden = mode !== 'march';
  $('trade').hidden = mode !== 'march';
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
  say('Marchlands. Drag to move, scroll to zoom. Click a roof to do something '
      + 'with it, or an empty plot to raise something on it.');
  say('Type `hint` if you are not sure what to do next, or `help` for everything.');
  nextFrame();
})();
