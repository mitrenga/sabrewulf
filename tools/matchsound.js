#!/usr/bin/env node
/**
 * Porovná zvuk remaku se zvukem originálu **pulz po pulzu**.
 *
 *   PYTHONPATH=tools/vendor ./tools/tracesound.py
 *   ./tools/matchsound.js [--verbose] [--case jmeno]
 *
 * `tracesound.py` nahraje, co originál doopravdy pošle do reproduktoru: každý
 * `OUT ($FE),A` i s časem v T-stavech Z80. Tenhle nástroj proti tomu pustí
 * `app/beeper.js` – tedy kód, který zvuk doopravdy dělá v prohlížeči – a
 * porovná **každý zápis, jeho čas i celkovou délku rutiny**. Cíl je nula
 * rozdílů.
 *
 * Proč zrovna takhle: výška tónu na jednobitovém beeperu **je** ten čas, takže
 * chyba jednoho T-stavu v jedné instrukci je slyšitelná chyba ladění. Kdyby se
 * porovnávaly jen „frekvence", propadla by; takhle propadnout nemůže.
 *
 * K tomu se křížem kontroluje `data/music.json`: půlperiody, které si
 * `dumpmusic.py` dopočítal pro tabulku 61 not, musí sedět na to, co
 * `app/beeper.js` spočítá ze svého modelu T-stavů – jinak by se dva popisy
 * téhož rozešly.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const url = require('url');

const ROOT = path.join(__dirname, '..');

/** kolik prvních rozdílů v případu vypsat */
const SHOW = 6;

function fail(message) {
  console.error(message);
  process.exit(1);
}

/** jak nahrávka ukládá zápisy: rozestupy → absolutní časy */
function absolute(run) {
  const times = [];
  let at = 0;
  run.deltas.forEach((delta) => { at += delta; times.push(at); });
  return times;
}

async function main() {
  const verbose = process.argv.includes('--verbose');
  const only = [];
  process.argv.forEach((arg, index) => {
    if (arg === '--case') { only.push(process.argv[index+1]); }
  });

  const traces = path.join(ROOT, 'build/sound-traces.json');
  if (!fs.existsSync(traces)) {
    fail('chybi '+path.relative(ROOT, traces)+' – spust nejdriv:\n'
         + '  PYTHONPATH=tools/vendor ./tools/tracesound.py');
  }
  const recording = JSON.parse(fs.readFileSync(traces, 'utf8'));
  const sounds = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/sounds.json'), 'utf8'));
  const music = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/music.json'), 'utf8'));

  // app/beeper.js je ES modul a importuje se přímo ze zdroje (R-001)
  const { Beeper } = await import(url.pathToFileURL(path.join(ROOT, 'app/beeper.js')).href);
  const beeper = new Beeper(sounds, music);

  // -- co který případ nahrávky znamená pro beeper.js ----------------------
  const replay = {
    squareWave: (run) => beeper.effect('squareWave', {b: run.b}),
    waveSequence: (run) => beeper.effect('waveSequence', {b: run.b, c: run.c}),
    step: (run) => beeper.effect('step', {counter: run.counter, colour: run.colour}),
    fly: (run) => beeper.effect('fly', {phase: run.phase}),
    land: () => beeper.effect('land'),
    repel: () => beeper.effect('repel'),
    object: () => beeper.effect('object'),
    orchid: () => beeper.effect('orchid'),
    orchidEnd: () => beeper.effect('orchidEnd'),
    materialise: (run) => beeper.effect('materialise', {sprite: run.sprite}),
    pointing: (run) => beeper.effect('pointing',
                                     {distance: run.distance, x: run.x, y: run.y}),
    fireball: (run) => beeper.effect('fireball', {sweeps: run.sweeps}),
    explosion: (run) => beeper.effect('explosion', {rom: run.rom}),
    music: (run) => beeper.tune(run.tune),
    menu: (run) => beeper.tune(run.tune, {waitKey: true})
  };

  let checks = 0, differences = 0, writes = 0;
  const summary = [];

  Object.keys(recording.cases).sort().forEach((name) => {
    if (only.length && only.indexOf(name) < 0) { return; }
    const test = recording.cases[name];
    if (!replay[name]) { fail('neznamy pripad nahravky: '+name); }
    let caseChecks = 0, caseDifferences = 0, caseWrites = 0;
    test.runs.forEach((run, index) => {
      const got = replay[name](run);
      const wanted = absolute(run);
      const label = name+'['+index+']'
        + (run.tune ? ' '+run.tune : '')
        + (run.b !== undefined ? ' B=$'+run.b.toString(16) : '')
        + (run.c !== undefined ? ' C=$'+run.c.toString(16) : '')
        + (run.counter !== undefined ? ' counter='+run.counter : '')
        + (run.colour !== undefined ? ' colour=$'+run.colour.toString(16) : '')
        + (run.phase !== undefined ? ' phase='+run.phase : '')
        + (run.sprite !== undefined ? ' sprite=$'+run.sprite.toString(16) : '')
        + (run.sweeps !== undefined ? ' sweeps='+run.sweeps : '')
        + (run.rand !== undefined ? ' rand=$'+run.rand.toString(16) : '')
        + (run.distance !== undefined
           ? ' d='+run.distance+' x='+run.x+' y='+run.y : '');
      if (!got) {
        console.log('  %s: beeper.js nic nezahral', label);
        caseDifferences++;
        return;
      }
      caseChecks++;
      if (got.writes.length !== wanted.length) {
        if (caseDifferences < SHOW) {
          console.log('  %s: %d zapisu, originál jich ma %d',
                      label, got.writes.length, wanted.length);
        }
        caseDifferences++;
        return;
      }
      let bad = 0;
      for (let i = 0; i < wanted.length; i++) {
        caseChecks++;
        caseWrites++;
        const value = (got.writes[i].value & 0x10) ? 1 : 0;
        if (got.writes[i].t !== wanted[i] || value !== run.values[i]) {
          if (caseDifferences+bad < SHOW) {
            console.log('  %s: zapis %d je v %d T (bit %d), originál ma %d T (bit %d)',
                        label, i, got.writes[i].t, value, wanted[i], run.values[i]);
          }
          bad++;
        }
      }
      caseChecks++;
      if (got.tstates !== run.tstates) {
        if (caseDifferences+bad < SHOW) {
          console.log('  %s: rutina trvala %d T, originálu %d T',
                      label, got.tstates, run.tstates);
        }
        bad++;
      }
      if (run.counterAfter !== undefined) {
        caseChecks++;
        if (got.counter !== run.counterAfter) {
          if (caseDifferences+bad < SHOW) {
            console.log('  %s: pocitadlo po kroku %d, originál %d',
                        label, got.counter, run.counterAfter);
          }
          bad++;
        }
      }
      caseDifferences += bad;
    });
    checks += caseChecks;
    differences += caseDifferences;
    writes += caseWrites;
    summary.push({name: name, routine: test.routine, runs: test.runs.length,
                  checks: caseChecks, writes: caseWrites,
                  differences: caseDifferences});
  });

  // -- křížová kontrola s data/music.json ---------------------------------
  let scale = 0, scaleBad = 0;
  music.notes.forEach((note) => {
    if (!note.index) { return; }
    scale++;
    checks++;
    if (Beeper.delay(note.b, note.c) !== note.halfPeriodTStates) {
      scaleBad++;
      differences++;
      if (scaleBad <= SHOW) {
        console.log('  nota %d: beeper.js pocita pulperiodu %d T, '
                    + 'data/music.json ma %d T',
                    note.index, Beeper.delay(note.b, note.c),
                    note.halfPeriodTStates);
      }
    }
  });

  if (verbose) {
    summary.forEach((entry) => {
      console.log('%s %s %s behu  %s kontrol  %s zapisu  %d rozdilu',
                  entry.name.padEnd(12), entry.routine.padEnd(6),
                  String(entry.runs).padStart(4),
                  String(entry.checks).padStart(8),
                  String(entry.writes).padStart(7), entry.differences);
    });
    console.log('tabulka not: %d pulperiod proti data/music.json, %d rozdilu',
                scale, scaleBad);
  }

  console.log('%d kontrol v %d pripadech (%d zapisu do reproduktoru), %d rozdilu',
              checks, summary.length, writes, differences);
  process.exit(differences ? 1 : 0);
}

main().catch((error) => { console.error(error); process.exit(1); });
