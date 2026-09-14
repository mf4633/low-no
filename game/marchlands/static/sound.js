/* The sound of a town, made out of arithmetic.
 *
 * Ask anybody what they remember about Stronghold and they will tell you
 * about the sound before they tell you about the popularity dial: the hum,
 * the birds, the hammering somewhere off to the left. It is the reason people
 * say they left it running.
 *
 * There are no audio files here for the same reason there are no images. Every
 * layer is synthesised: the wind is filtered noise, the birds are two
 * oscillators chasing each other, the hammer is a click envelope, the bell is
 * four detuned partials with a long tail. It follows the state, so a town that
 * is working sounds busy, a town in winter sounds bare, and a town on fire
 * does not sound like either.
 */
'use strict';

const Sound = (() => {
  let ctx = null, master = null, on = false, layers = {}, state = null;
  let timer = null, lastDay = -1, made = 0;   // `made` is how many
  // voices have been started: the page has no other way to check that
  // the synthesis is running rather than merely switched on.

  function noiseBuffer(seconds = 2) {
    const n = ctx.sampleRate * seconds;
    const buf = ctx.createBuffer(1, n, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    return buf;
  }

  function bed() {
    // Wind: noise through a lowpass, breathing slowly. Winter opens it up.
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer(4); src.loop = true;
    const filt = ctx.createBiquadFilter();
    filt.type = 'lowpass'; filt.frequency.value = 380; filt.Q.value = 0.6;
    const gain = ctx.createGain(); gain.gain.value = 0.05;
    const lfo = ctx.createOscillator(), lfoGain = ctx.createGain();
    lfo.frequency.value = 0.07; lfoGain.gain.value = 0.028;
    lfo.connect(lfoGain).connect(gain.gain);
    src.connect(filt).connect(gain).connect(master);
    src.start(); lfo.start();
    return { gain, filt };
  }

  function murmur() {
    // A crowd is noise with a formant on it. Content towns sit brighter.
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer(3); src.loop = true;
    const filt = ctx.createBiquadFilter();
    filt.type = 'bandpass'; filt.frequency.value = 520; filt.Q.value = 1.4;
    const gain = ctx.createGain(); gain.gain.value = 0.0;
    src.connect(filt).connect(gain).connect(master);
    src.start();
    return { gain, filt };
  }

  function ping(freq, when, dur, type, level, glide) {
    const osc = ctx.createOscillator(), g = ctx.createGain();
    osc.type = type || 'sine';
    osc.frequency.setValueAtTime(freq, when);
    if (glide) osc.frequency.exponentialRampToValueAtTime(glide, when + dur);
    g.gain.setValueAtTime(0.0001, when);
    g.gain.exponentialRampToValueAtTime(level, when + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, when + dur);
    osc.connect(g).connect(master);
    osc.start(when); osc.stop(when + dur + 0.05);
    made++;
  }

  function knock(when, level) {
    // A hammer is a click: noise, very short, with a woody resonance.
    const src = ctx.createBufferSource();
    src.buffer = noiseBuffer(0.2);
    const filt = ctx.createBiquadFilter();
    filt.type = 'bandpass';
    filt.frequency.value = 900 + Math.random() * 500; filt.Q.value = 5;
    const g = ctx.createGain();
    g.gain.setValueAtTime(level, when);
    g.gain.exponentialRampToValueAtTime(0.0001, when + 0.09);
    src.connect(filt).connect(g).connect(master);
    src.start(when); src.stop(when + 0.2);
    made++;
  }

  function bird(when) {
    const base = 1700 + Math.random() * 900;
    ping(base, when, 0.09, 'sine', 0.05, base * 1.5);
    ping(base * 1.4, when + 0.11, 0.07, 'sine', 0.035, base * 0.9);
  }

  function bell(when) {
    // Four partials, deliberately not harmonic, with a long tail.
    for (const [mult, level] of [[1, .10], [2.01, .05], [2.97, .03], [4.2, .018]]) {
      const osc = ctx.createOscillator(), g = ctx.createGain();
      osc.type = 'sine'; osc.frequency.value = 262 * mult;
      g.gain.setValueAtTime(0.0001, when);
      g.gain.exponentialRampToValueAtTime(level, when + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, when + 3.4);
      osc.connect(g).connect(master);
      osc.start(when); osc.stop(when + 3.6);
      made++;
    }
  }

  /* The alarm bell: rung fast, rung hard, and slightly out of tune with
   * itself. Every other sound this file makes is meant to be pleasant to sit
   * inside for an hour. This one is meant to make you look up, which is a
   * different job and wants a different noise -- so it is three strikes of a
   * pair of bells a semitone apart, which is a sound nothing in nature makes
   * by accident.
   *
   * It is the honest version of the thing people quote about Stronghold. We
   * cannot ship a recording of somebody shouting "the castle is collapsing";
   * what we can do is make the moment sound like an emergency and put the
   * words on the screen. */
  function alarm(when) {
    for (let i = 0; i < 3; i++) {
      const t = when + i * 0.17;
      ping(784, t, 0.42, 'triangle', 0.16);
      ping(740, t + 0.012, 0.42, 'triangle', 0.13);
      ping(392, t, 0.6, 'sine', 0.1);
    }
  }

  function drum(when) {
    const osc = ctx.createOscillator(), g = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(96, when);
    osc.frequency.exponentialRampToValueAtTime(48, when + 0.22);
    g.gain.setValueAtTime(0.16, when);
    g.gain.exponentialRampToValueAtTime(0.0001, when + 0.3);
    osc.connect(g).connect(master);
    osc.start(when); osc.stop(when + 0.35);
    made++;
  }

  /* Once a second, decide what the town sounds like now. */
  function tick() {
    if (!on || !state) return;
    const now = ctx.currentTime;
    const town = state.town || {};
    const season = state.season || 'spring';
    const running = (state.plan && state.plan.buildings || [])
      .filter(b => b.running).length;
    const burning = town.fires || 0;
    const mood = (town.popularity || 50) / 100;

    layers.bed.filt.frequency.value = season === 'winter' ? 900 : 420;
    layers.bed.gain.gain.setTargetAtTime(
      season === 'winter' ? 0.10 : 0.05, now, 1.5);

    // The crowd follows the mood: quieter and duller when they are unhappy.
    layers.murmur.gain.gain.setTargetAtTime(
      Math.min(0.05, 0.006 + (town.population || 0) / 9000) * (0.35 + mood),
      now, 2.0);
    layers.murmur.filt.frequency.value = 380 + 340 * mood;

    // Work: a hammer for every few workshops that are actually running.
    const hits = Math.min(5, Math.round(running / 4));
    for (let i = 0; i < hits; i++) {
      if (Math.random() < 0.55) knock(now + Math.random() * 0.95, 0.05 + Math.random() * 0.04);
    }
    if (season !== 'winter' && Math.random() < 0.28) bird(now + Math.random() * 0.9);
    // Fire is a crackle, and a big fire is a lot of crackle.
    for (let i = 0; i < Math.min(8, burning * 2); i++) {
      if (Math.random() < 0.6) knock(now + Math.random(), 0.03);
    }
    if (town.besieged && Math.random() < 0.5) drum(now + Math.random() * 0.6);

    // A bell for a day that mattered.
    if (state.day !== lastDay) {
      if (lastDay >= 0 && state.chapterBell) bell(now + 0.1);
      lastDay = state.day;
    }
  }

  return {
    get on() { return on; },
    /* Browsers will not make a sound until somebody has clicked something, so
     * this is only ever called from a button. */
    toggle() {
      if (!ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return false;
        ctx = new AC();
        master = ctx.createGain();
        master.gain.value = 0.0;
        master.connect(ctx.destination);
        layers.bed = bed();
        layers.murmur = murmur();
        timer = setInterval(tick, 1000);
      }
      on = !on;
      if (ctx.state === 'suspended') ctx.resume();
      master.gain.setTargetAtTime(on ? 0.9 : 0.0, ctx.currentTime, 0.25);
      return on;
    },
    feed(s) { state = s; },
    mark(kind) {
      if (!on || !ctx) return;
      if (kind === 'bell') bell(ctx.currentTime + 0.05);
      if (kind === 'drum') drum(ctx.currentTime + 0.05);
      if (kind === 'alarm') alarm(ctx.currentTime + 0.05);
    },
    stop() { if (timer) clearInterval(timer); },
    /* For the page to check what it is hearing. */
    get state() { return ctx ? ctx.state : 'none'; },
    get made() { return made; },
  };
})();

/* A top-level `const` in a classic script is a lexical binding, not a property
 * of window -- so `window.Sound && ...` was quietly false and the soundscape
 * never received a single state update. Say it out loud. */
window.Sound = Sound;
