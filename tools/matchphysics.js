#!/usr/bin/env node
/**
 * Porovná **fyziku remaku s fyzikou originálu, krok po kroku**.
 *
 *   PYTHONPATH=tools/vendor ./tools/tracephysics.py
 *   ./tools/matchphysics.js [--verbose] [--scenario jmeno]
 *
 * `tracephysics.py` nahraje běhy originálu v simulátoru a u každého **kroku
 * Sabremana** zapíše jeho 12bajtový záznam na vstupu i na výstupu
 * (`$9702`, vzorkuje se na `$99D0`/`$99F0`). Tenhle nástroj vezme vstupní
 * záznam, pustí na něj `app/sabremanPhysics.js` – tedy kód, který jde do
 * prohlížeče – a porovná výsledek s tím, co vyšlo originálu. Čeká se **nula
 * rozdílů**; každý rozdíl se vypíše po bajtech.
 *
 * Konstanty bere replika z `data/physics.json` (`tools/dumpphysics.py`), kulisu
 * a svět z `data/rooms.json`, `data/scenery.json` a `data/world.json`, takže se
 * kontroluje i to, že kolize v prohlížeči čte tatáž data jako originál.
 *
 * Dvě věci se replice **předávají z trasy**, protože je originál bere z míst,
 * která remake nemá:
 *
 * - `$5C78` (`FRAMES`, počítadlo ULA) – na něm visí fáze chůze,
 * - `$9695` (`Rand8`) – z něj je fáze seku mečem; originál ji míchá
 *   z obnovovacího registru Z80, takže se tik po tiku reprodukovat nedá.
 *
 * Obdoba `matchrooms.js` pro fyziku (`sources/docs/disasm_notes.md` §14).
 */
'use strict';
const fs = require('fs');
const path = require('path');
const loadClassicScript = require(path.join(__dirname, '../app/svision/tools/classicScript.cjs'));

const ROOT = path.join(__dirname, '..');
const SabremanPhysics = loadClassicScript(path.join(ROOT, 'app/sabremanPhysics.js'));
const R = SabremanPhysics.RECORD;

// ★ klávesy originálu: Q vlevo, W vpravo, **E nahoru, R dolů** (obráceně,
// než píšou originální instrukce – změřeno, viz disasm_notes.md §14), T meč
const KEYMAP = {Q: 'left', W: 'right', E: 'up', R: 'down', T: 'sword'};

const FIELDS = ['sprite', 'room', 'state', 'x', 'y', 'attr', 'dx', 'dy',
                '+8', '+9', '+10', '+11'];

function parse(hex) {
  const out = new Uint8Array(hex.length/2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(hex.substr(i*2, 2), 16);
  }
  return out;
} // parse

function hexs(record) {
  let out = '';
  for (let i = 0; i < record.length; i++) {
    out += ('0'+record[i].toString(16).toUpperCase()).slice(-2);
  }
  return out;
} // hexs

function load(name) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, name), 'utf8'));
} // load

function main() {
  const verbose = process.argv.includes('--verbose');
  const only = process.argv.indexOf('--scenario');
  const wanted = only >= 0 ? process.argv[only+1] : null;
  const tracePath = path.join(ROOT, 'build/physics-traces.json');
  if (!fs.existsSync(tracePath)) {
    console.error('chybi %s – spust nejdriv:\n'
                  + '  PYTHONPATH=tools/vendor ./tools/tracephysics.py',
                  path.relative(ROOT, tracePath));
    process.exit(1);
  }
  const traces = load('build/physics-traces.json');
  const physics = new SabremanPhysics(load('data/physics.json'),
                                      load('data/world.json'),
                                      load('data/rooms.json'),
                                      load('data/scenery.json'));

  let steps = 0, bad = 0, skipped = 0;
  const perField = {};
  for (const scenario of traces.scenarios) {
    if (wanted && scenario.name !== wanted) {
      continue;
    }
    let mine = 0, differ = 0;
    for (const step of scenario.steps) {
      if (!step.recOut) {
        skipped++;                  // obsluha skoncila jinudy (game over)
        continue;
      }
      const record = parse(step.rec);
      const expected = parse(step.recOut);
      const input = {left: false, right: false, up: false, down: false,
                     sword: false};
      for (const key of step.keys) {
        if (KEYMAP[key]) {
          input[KEYMAP[key]] = true;
        }
      }
      physics.step(record, input, {frames: step.ula, rand: step.rand,
                                   lives: step.lives});
      steps++;
      mine++;
      let same = true;
      for (let i = 0; i < expected.length; i++) {
        if (record[i] !== expected[i]) {
          same = false;
          perField[FIELDS[i]] = (perField[FIELDS[i]] || 0)+1;
        }
      }
      if (!same) {
        differ++;
        bad++;
        if (verbose || differ <= 3) {
          console.log('  %s krok %d (klavesy %s, snimku %d)',
                      scenario.name, step.frame,
                      step.keys.join('+') || '-', step.frames);
          console.log('    vstup     %s', step.rec);
          console.log('    original  %s', step.recOut);
          console.log('    remake    %s', hexs(record));
        }
      }
    }
    console.log('%s %s kroku, %s rozdilu   (%s)',
                scenario.name.padEnd(13), String(mine).padStart(4),
                String(differ).padStart(3), scenario.note.split(':')[0]);
  }

  console.log('');
  if (bad) {
    console.log('bajty, ve kterych se to lisi: %s',
                Object.keys(perField).map((k) => k+' '+perField[k]).join(', '));
    console.log('%d z %d kroku se LISI – fyzika remaku neni fyzika originalu',
                bad, steps);
    console.log('(rozdil se hleda po bajtech zaznamu: '
                + FIELDS.slice(0, 8).join(' ')+')');
    process.exit(1);
  }
  console.log('%d kroku Sabremana ve %d scenarich, 12 B zaznamu na krok: '
              + 'NULA ROZDILU%s', steps, traces.scenarios.length,
              skipped ? ' ('+skipped+' kroku bez vystupu preskoceno)' : '');
} // main

main();
