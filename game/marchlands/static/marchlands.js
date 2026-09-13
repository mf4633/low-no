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
const iso = (x, y) => [(x - y) * TW / 2, (x + y) * TH / 2];
/* Accepts what it returns. Shading an already-shaded colour used to give NaN,
 * which canvas paints as black -- every forest and every road came out as a
 * hole in the ground until this took rgb() as well as #rrggbb. */
const shade = (colour, f) => {
  let r, g, b;
  if (colour[0] === '#') {
    const n = parseInt(colour.slice(1), 16);
    r = (n >> 16) & 255; g = (n >> 8) & 255; b = n & 255;
  } else {
    const m = colour.match(/-?\d+(\.\d+)?/g) || [0, 0, 0];
    r = +m[0]; g = +m[1]; b = +m[2];
  }
  const c = [r, g, b].map(v => Math.max(0, Math.min(255, Math.round(v * f))));
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
  else if (kind === 'forest') base = shade(p.tree, 0.75);
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
    const t = (performance.now() - t0) / 1000;
    ctx.strokeStyle = 'rgba(255,255,255,.20)';
    ctx.lineWidth = 1;
    for (let i = 0; i < 2; i++) {
      const wy = sy + (i - 0.5) * 9 + Math.sin(t * 1.4 + x + y + i) * 2.2;
      ctx.beginPath();
      ctx.moveTo(sx - 13, wy); ctx.quadraticCurveTo(sx, wy - 2.5, sx + 13, wy);
      ctx.stroke();
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

function puff(x, y, t) {
  if (Math.random() < 0.12) smoke.push({ x, y, born: t, drift: Math.random() - 0.5 });
}
function burn(x, y, t) {
  if (Math.random() < 0.55) {
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
  const v = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.42,
                                     w / 2, h / 2, Math.max(w, h) * 0.78);
  v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(12,9,6,.55)');
  ctx.fillStyle = v; ctx.fillRect(0, 0, w, h);
}

/* ------------------------------------------------------------------ frame */
function frame() {
  const t = (performance.now() - t0) / 1000;
  const w = canvas.width / dpr, h = canvas.height / dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
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
    things.sort((a, b) => a.d - b.d);
    for (const it of things) {
      if (it.kind === 'wood') drawTrees(it.x, it.y);
      else if (it.kind === 'b') drawBuilding(it.b, t);
      else if (it.kind === 'w') drawWall(it.w, t);
      else drawFolk(it.f, it.i, t);
    }
    drawEffects(t);
    ctx.restore();
  }
  drawWeather(w, h, t);
  requestAnimationFrame(frame);
}

/* ------------------------------------------------------------------- shell */
function resize() {
  dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = canvas.clientWidth * dpr;
  canvas.height = canvas.clientHeight * dpr;
}
window.addEventListener('resize', resize);

let drag = null;
canvas.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY }; });
window.addEventListener('pointerup', () => { drag = null; });
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
  if (!plan) return;
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
const $ = id => document.getElementById(id);
function meter(el, frac, warnAt, badAt) {
  el.classList.toggle('warn', frac < warnAt);
  el.classList.toggle('bad', frac < badAt);
  el.firstElementChild.style.width = Math.max(0, Math.min(100, frac * 100)) + '%';
}

function paint(s) {
  state = s; plan = s.plan;
  $('place').textContent = s.town.name;
  $('date').textContent = `${s.date} · ${s.age}`;
  $('purse').textContent = Math.round(s.treasury).toLocaleString() + 'c';
  $('souls').textContent = `${Math.round(s.town.population)} of ${Math.round(s.town.housing)} roofs`;
  meter($('moodbar'), s.town.popularity / 100, 0.45, 0.25);
  $('hands').textContent = `${Math.round(s.town.employed)} of ${Math.round(s.town.workforce)}`;
  meter($('wallbar'), s.town.wall_max ? s.town.wall_hp / s.town.wall_max : 0, 0.6, 0.3);
  $('soldiers').textContent = s.town.soldiers;
  $('mood').innerHTML = s.town.mood.map(m =>
    `<li><label>${m.what}</label><span class="${m.by > 0 ? 'up' : 'down'}">` +
    `${m.by > 0 ? '+' : ''}${m.by}</span></li>`).join('');
  const L = s.ledger;
  $('ledger').innerHTML = [['taxes', L.taxes], ['trade', L.trade], ['tribute', L.tribute],
                           ['wages', -L.wages], ['upkeep', -L.upkeep], ['net', L.net]]
    .map(([k, v]) => `<li><label>${k}</label><span class="${v >= 0 ? 'up' : 'down'}">` +
                     `${v >= 0 ? '+' : ''}${Math.round(v)}</span></li>`).join('');
  const alarm = $('alarm');
  const bad = s.town.besieged ? 'under siege' : s.town.raided ? 'the country is burning'
    : s.town.fires ? `${s.town.fires} roofs alight`
    : s.town.blockaded ? 'the roads are cut' : s.over ? s.over : '';
  alarm.textContent = bad; alarm.hidden = !bad;
}

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
  const vw = canvas.clientWidth - 300, vh = canvas.clientHeight - 230;
  camera.zoom = Math.max(0.5, Math.min(1.9, Math.min(vw / wide, vh / tall)));
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const [mx, my] = iso(cx, cy);
  const [ox, oy] = [-(plan.w - plan.h) * TW / 4, -(plan.w + plan.h) * TH / 4];
  camera.x = 120 - (mx + ox) * camera.zoom;
  camera.y = -40 - (my + oy) * camera.zoom;
}

(async function boot() {
  resize();
  paint(await (await fetch('/state')).json());
  frameTown();
  say('Marchlands. Drag to move, scroll to zoom, hover a roof to ask what it is.');
  say('Type `hint` if you are not sure what to do next, or `help` for everything.');
  requestAnimationFrame(frame);
})();
