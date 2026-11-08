#!/usr/bin/env node
/**
 * Porovná **nepřátele remaku s nepřáteli originálu, případ po případu**.
 *
 *   PYTHONPATH=tools/vendor ./tools/tracemonsters.py
 *   ./tools/matchmonsters.js [--verbose] [--case jmeno]
 *
 * `tracemonsters.py` nechá **originál v simulátoru spočítat sám sebe**: pro
 * každý případ položí do volné paměti `CALL rutina` a opíše, co po ní zůstalo
 * v záznamu entity a v „game status bufferu". Tenhle nástroj vezme tytéž
 * vstupy, pustí na ně `app/worldMonsters.js` – tedy kód, který jde do
 * prohlížeče – a porovná výsledek. Čeká se **nula rozdílů**.
 *
 * Konstanty bere replika z `data/monsters.json` (`tools/dumpmonsters.py`),
 * obálku kontaktu a jedenáct nesmrtelných entit z `data/entities.json`
 * (M4) a kulisu z `data/scenery.json` přes `app/sabremanPhysics.js` (M3),
 * takže se kontroluje i to, že se M3, M4 a M5 nerozešly.
 *
 * Jedno jediné se replice **předává z trasy**, protože je originál bere
 * odjinud, než remake může dosáhnout: **svislá rychlost ohnivé koule**
 * v losovaném směru. `$9E24` je `LD A,R`, tedy obnovovací registr Z80.
 * Hlásí se to zvlášť, přesně jako druh předmětu v M4 a fáze seku v M3.
 *
 * Obdoba `matchentities.js` pro M5 (`sources/docs/disasm_notes.md` §17).
 */
'use strict';
const fs = require('fs');
const path = require('path');
const loadClassicScript = require(path.join(__dirname, '../app/svision/tools/classicScript.cjs'));

const ROOT = path.join(__dirname, '..');
const SabremanPhysics = loadClassicScript(path.join(ROOT, 'app/sabremanPhysics.js'));
const WorldEntities = loadClassicScript(path.join(ROOT, 'app/worldEntities.js'));
const WorldMonsters = loadClassicScript(path.join(ROOT, 'app/worldMonsters.js'));
const R = WorldMonsters.RECORD;

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
  const only = process.argv.indexOf('--case');
  const wanted = only >= 0 ? process.argv[only+1] : null;
  const tracePath = path.join(ROOT, 'build/monster-traces.json');
  if (!fs.existsSync(tracePath)) {
    console.error('chybi %s – spust nejdriv:\n'
                  + '  PYTHONPATH=tools/vendor ./tools/tracemonsters.py',
                  path.relative(ROOT, tracePath));
    process.exit(1);
  }
  const traces = load('build/monster-traces.json');
  const monsters = load('data/monsters.json');
  const entities = load('data/entities.json');
  const worldData = load('data/world.json');
  const v = monsters.values;

  const physics = new SabremanPhysics(load('data/physics.json'), worldData,
                                      load('data/rooms.json'),
                                      load('data/scenery.json'));

  const results = [];
  let total = 0, bad = 0, reported = 0;

  /** a fresh set of enemies, so no case can leak state into the next */
  const fresh = () => {
    const world = new WorldEntities(entities, worldData);
    world.attach(new Uint8Array(R.LENGTH));
    return new WorldMonsters(monsters, entities, physics, world);
  };

  const compare = (name, key, got, want, detail) => {
    total++;
    if (String(got) === String(want)) { return true; }
    bad++;
    if (bad <= 25 || verbose) {
      console.log('  %s %s: remake %s, original %s%s', name, key, got, want,
                  detail ? '   ('+detail+')' : '');
      if (String(got).length === 24 && String(want).length === 24) {
        const mine = parse(String(got)), theirs = parse(String(want));
        for (let i = 0; i < mine.length; i++) {
          if (mine[i] !== theirs[i]) {
            console.log('      '+FIELDS[i].padEnd(6)+' '
                        + hexs([mine[i]])+' != '+hexs([theirs[i]]));
          }
        }
      }
    }
    return false;
  };

  const cases = traces.cases;
  const run = (name, body) => {
    if (!cases[name] || (wanted && wanted !== name)) { return; }
    const before = {total, bad, reported};
    body(cases[name]);
    results.push({name, rows: cases[name].length, checks: total-before.total,
                  bad: bad-before.bad, reported: reported-before.reported});
  };

  /** Sabreman's record out of the trace's twelve bytes */
  const sabremanOf = (row, defaults) => {
    const record = new Uint8Array(R.LENGTH);
    record[R.SPRITE] = defaults.sprite;
    record[R.ROOM] = defaults.room;
    record[R.STATE] = defaults.state || 0;
    record[R.X] = defaults.x;
    record[R.Y] = defaults.y;
    record[R.ATTR] = defaults.colour;
    record[R.AMULET] = defaults.amulet || 0;
    return record;
  };

  // -- $A4B3: body za zničeného nepřítele, všech 196 sprite ID ---------------
  run('score', (rows) => {
    const m = fresh();
    rows.forEach((row) => {
      const record = new Uint8Array(R.LENGTH);
      record[R.SPRITE] = row.sprite;
      const out = m.begin(new Uint8Array(R.LENGTH), {});
      m.A4A6(record);
      compare('score', '$'+row.sprite.toString(16), out.points, row.score);
    });
  });

  // -- $AB36: kdo koho zabije ------------------------------------------------
  run('contact', (rows) => {
    const m = fresh();
    rows.forEach((row) => {
      const record = new Uint8Array(R.LENGTH);
      record[R.SPRITE] = 0x60;
      record[R.ROOM] = 0xA8;
      record[R.X] = 0x60;
      record[R.Y] = 0x60;
      const sabreman = sabremanOf(row, {sprite: row.sprite, room: 0xA8,
                                        x: row.x, y: row.y, colour: row.colour});
      const out = m.begin(sabreman, {delay: 0});
      const hit = m.AB36(record, v.nastieHitHeight, v.nastieHitWidth, row.d);
      const key = 'sprite $'+row.sprite.toString(16)+' attr $'
                  + row.colour.toString(16)+' d'+row.d
                  + ' at '+row.x+','+row.y;
      compare('contact', key+' hit', hit, row.hit);
      compare('contact', key+' killed', out.killed, row.killed);
    });
  });

  // -- $A44B: odraz od okrajů ------------------------------------------------
  run('bounce', (rows) => {
    const m = fresh();
    rows.forEach((row) => {
      const record = new Uint8Array(R.LENGTH);
      record[R.SPRITE] = 0x60;
      record[R.ROOM] = 0xA8;
      record[R.X] = row.x;
      record[R.Y] = row.y;
      record[R.DX] = row.dx;
      record[R.DY] = row.dy;
      m.begin(new Uint8Array(R.LENGTH), {});
      m.width = row.width;
      const move = m.A44B(record);
      const key = 'w'+row.width+' d'+row.dx+','+row.dy+' at '+row.x+','+row.y;
      compare('bounce', key+' x', move.x, row.outX);
      compare('bounce', key+' y', move.y, row.outY);
      compare('bounce', key+' bounce',
              (move.bounceX ? 1 : 0) | (move.bounceY ? 2 : 0), row.bounce);
    });
  });

  // -- $A630: stěhování nesmrtelné entity ------------------------------------
  run('roam', (rows) => {
    const m = fresh();
    rows.forEach((row) => {
      const record = new Uint8Array(R.LENGTH);
      record[R.SPRITE] = 0xA0;
      record[R.ROOM] = row.there;
      record[R.X] = 0x40;
      record[R.Y] = 0x50;
      record[R.ATTR] = 0x45;
      const sabreman = sabremanOf(row, {sprite: 0x10, room: row.here,
                                        x: 0x78, y: 0x70, colour: 0x47});
      m.begin(sabreman, {rand: row.rand, sweeps: 4, frames: 8});
      m.A630(record);
      compare('roam', row.here+'->'+row.there+' r'+row.rand,
              hexs(record), row.record);
    });
  });

  // -- $A3C5 / $A3E0: zhmotnění a výběr druhu --------------------------------
  run('materialise', (rows) => {
    const m = fresh();
    rows.forEach((row) => {
      const record = new Uint8Array(R.LENGTH);
      record[R.ROOM] = 0xA8;
      record[R.ATTR] = 0x45;
      let sabreman, out, key;
      if (row.shimmer === undefined) {
        record[R.SPRITE] = 0x06;
        record[R.X] = 0x40;
        record[R.Y] = 0x50;
        sabreman = sabremanOf(row, {sprite: 0x10, room: 0xA8, x: 0x78, y: 0x70,
                                    colour: 0x47, amulet: row.amulet});
        m.begin(sabreman, {sweeps: row.sweeps, frames: 7, rand: row.rand});
        m.A3E0(record);
        key = 'amulet '+row.amulet+' sweep '+row.sweeps+' r'+row.rand;
        compare('materialise', key, hexs(record), row.record);
        return;
      }
      record[R.SPRITE] = row.shimmer;
      record[R.X] = row.x;
      record[R.Y] = 0x70;
      sabreman = sabremanOf(row, {sprite: row.sabreman, room: 0xA8, x: 0x78,
                                  y: 0x70, colour: 0x47});
      out = m.begin(sabreman, {sweeps: 3, frames: 5, rand: 0x11, delay: 0});
      m.A3C5(record);
      key = 'shimmer $'+row.shimmer.toString(16)+' x'+row.x
            + ' sabreman $'+row.sabreman.toString(16);
      compare('materialise', key, hexs(record), row.record);
      compare('materialise', key+' score', out.points, row.score);
    });
  });


  /**
   * One run of a handler, sweep after sweep. The trace was written by calling
   * the routine repeatedly from a known setup; the rows carry the clock and
   * Sabreman, so the replica only has to keep the entity's own record.
   */
  const runSequence = (name, handler, setups) => {
    let current = handler;
    run(name, (rows) => {
      const m = fresh();
      let record = null, index = -1, step = 0;
      rows.forEach((row) => {
        if (row.sweeps === 1) {        // a new run of the case
          index++;
          step = 0;
          record = new Uint8Array(R.LENGTH);
          const setup = setups[index];
          current = setup._handler || handler;
          Object.keys(setup).forEach((key) => {
            if (key !== '_handler') { record[R[key]] = setup[key]; }
          });
          m.width = 0x10;              // $96AD as sane() leaves it
          m.spawnTimer = 0;
          m.fireballTimer = 0;
        }
        const sabreman = parse(row.sabreman);
        const out = m.begin(sabreman, {sweeps: row.sweeps, frames: row.frames,
                                       rand: row.rand, delay: 0});
        // ★ the fireball's vertical speed can come out of the Z80 refresh
        // register ($9E24). On an even sweep the direction is drawn, so when
        // the original's +7 moved there, it is taken from the trace and
        // reported instead of compared.
        current.call(m, record);
        const want = parse(row.record);
        if (name === 'fireball' && (row.sweeps & 1) === 0
            && record[R.DY] !== want[R.DY]) {
          record[R.DY] = want[R.DY];
          reported++;
        }
        const key = 'run '+index+' sweep '+step;
        compare(name, key, hexs(record), row.record);
        compare(name, key+' killed', out.killed, row.killed);
        compare(name, key+' score', out.points, row.score);
        compare(name, key+' width', m.width, row.width);
        step++;
      });
    });
  };

  runSequence('nastie', WorldMonsters.prototype.A54F, [
    {SPRITE: 0x60, ROOM: 0xA8, STATE: 0x0A, X: 0x40, Y: 0x50, ATTR: 0x45,
     DX: 0x30, DY: 0x20},
    {SPRITE: 0x64, ROOM: 0xA8, STATE: 0x01, X: 0x40, Y: 0x50, ATTR: 0x45},
    {SPRITE: 0x98, ROOM: 0xA8, STATE: 0x03, X: 0x40, Y: 0x50, ATTR: 0x45,
     DX: 0xD0, DY: 0xB0},
    {SPRITE: 0x60, ROOM: 0xA8, STATE: 0x0A, X: 0x40, Y: 0x50, ATTR: 0x45,
     DX: 0x20},
    {SPRITE: 0x60, ROOM: 0xA8, STATE: 0x0A, X: 0x40, Y: 0x50, ATTR: 0x45,
     DX: 0x20}
  ]);
  runSequence('chaser', WorldMonsters.prototype.A4D7, [
    {SPRITE: 0x68, ROOM: 0xA8, STATE: 0x05, X: 0x60, Y: 0x60, ATTR: 0x45},
    {SPRITE: 0x68, ROOM: 0xA8, STATE: 0x05, X: 0x60, Y: 0x60, ATTR: 0x45},
    {SPRITE: 0x68, ROOM: 0xA8, STATE: 0x05, X: 0x60, Y: 0x60, ATTR: 0x45}
  ]);
  runSequence('rhino', WorldMonsters.prototype.AD07, [
    {SPRITE: 0x30, ROOM: 0xA8, X: 0x40, Y: 0x50, ATTR: 0x45, DX: 0xD0},
    {SPRITE: 0x30, ROOM: 0xA8, X: 0x40, Y: 0x50, ATTR: 0x45, DX: 0xD0},
    {SPRITE: 0x30, ROOM: 0xA8, X: 0x40, Y: 0x50, ATTR: 0x45, DX: 0xD0}
  ]);
  runSequence('hippo', WorldMonsters.prototype.A9E72, [
    {SPRITE: 0xA0, ROOM: 0xA8, X: 0x40, Y: 0x50, ATTR: 0x45, DX: 0x20},
    {SPRITE: 0xA0, ROOM: 0xA8, X: 0x40, Y: 0x50, ATTR: 0x45, DX: 0x20},
    {SPRITE: 0xA4, ROOM: 0x88, X: 0x40, Y: 0x50, ATTR: 0x45, DX: 0x20,
     _handler: WorldMonsters.prototype.A9EB3}
  ]);
  runSequence('native', WorldMonsters.prototype.AB74, [
    {SPRITE: 0x3C, ROOM: 0xA8, X: 0x40, Y: 0x50, ATTR: 0x45, DX: 0x20, DY: 0x20},
    {SPRITE: 0x3C, ROOM: 0xA8, X: 0x40, Y: 0x50, ATTR: 0x45, DX: 0x20, DY: 0x20}
  ]);
  runSequence('wulf', WorldMonsters.prototype.A858, [
    {SPRITE: 0x50, ROOM: 0xA8, X: 0x40, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x50, ROOM: 0xA8, X: 0x40, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x50, ROOM: 0xA8, X: 0x40, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x50, ROOM: 0xA8, X: 0x40, Y: 0x70, ATTR: 0x45, DX: 0x40},
    {SPRITE: 0x50, ROOM: 0xA8, X: 0x40, Y: 0x70, ATTR: 0x45, DX: 0x40}
  ]);
  runSequence('keeper', WorldMonsters.prototype.A9F16, [
    {SPRITE: 0x94, ROOM: 0x88, X: 0x70, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x94, ROOM: 0x88, X: 0x70, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x94, ROOM: 0x88, X: 0x70, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x94, ROOM: 0x88, X: 0x70, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x94, ROOM: 0x88, X: 0x70, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x94, ROOM: 0x88, X: 0x70, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x94, ROOM: 0x88, X: 0x70, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x94, ROOM: 0x88, X: 0x70, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x94, ROOM: 0x88, X: 0x70, Y: 0x70, ATTR: 0x45},
    {SPRITE: 0x94, ROOM: 0x88, X: 0x70, Y: 0x70, ATTR: 0x45}
  ]);
  runSequence('fireball', WorldMonsters.prototype.A9D91, [
    {SPRITE: 0x34, ROOM: 0xA8, STATE: 0x03, X: 0x60, Y: 0x60, ATTR: 0x46,
     DX: 0x40, DY: 0x40, AGE: 0x20},
    {SPRITE: 0x34, ROOM: 0xA8, STATE: 0x03, X: 0x60, Y: 0x60, ATTR: 0x46,
     DX: 0x40, DY: 0x40, AGE: 0x20},
    {SPRITE: 0x34, ROOM: 0xA8, STATE: 0x03, X: 0x60, Y: 0x60, ATTR: 0x46,
     DX: 0x40, DY: 0x40, AGE: 0x20}
  ]);

  // -- $9A3C: dosazování zvířat ----------------------------------------------
  run('spawn', (rows) => {
    const m = fresh();
    m.spawnTimer = 0x10;
    m.nastie.forEach((record) => { record.fill(0); });
    rows.forEach((row) => {
      const sabreman = sabremanOf(row, {sprite: 0x10, room: 0xA8, x: 0x78,
                                        y: 0x70, colour: 0x47});
      m.begin(sabreman, {sweeps: row.sweeps, frames: row.frames,
                         rand: row.rand, delay: 0});
      m.A9A3C();
      compare('spawn', 'sweep '+row.sweeps+' delay', m.spawnTimer, row.delay);
      for (let slot = 0; slot < m.nastie.length; slot++) {
        compare('spawn', 'sweep '+row.sweeps+' slot '+slot,
                hexs(m.nastie[slot]), row.slots[slot]);
      }
    });
  });

  // -- $9ABC: ohnivá koule ---------------------------------------------------
  run('fireballSpawn', (rows) => {
    const m = fresh();
    m.fireball().fill(0);
    m.fireballTimer = 0x10;
    rows.forEach((row) => {
      const sabreman = sabremanOf(row, {sprite: 0x10, room: 0xA8, x: 0x78,
                                        y: 0x70, colour: 0x47});
      m.begin(sabreman, {sweeps: row.sweeps, frames: row.frames,
                         rand: row.rand, delay: 0});
      m.A9ABC();
      compare('fireballSpawn', 'sweep '+row.sweeps+' timer',
              m.fireballTimer, row.timer);
      compare('fireballSpawn', 'sweep '+row.sweeps,
              hexs(m.fireball()), row.record);
    });
  });

  // -- $B235 / $B1B7: střídání hráčů, a ta chyba -----------------------------
  run('twoPlayer', (rows) => {
    const m = fresh();
    rows.forEach((row) => {
      const turn = m.startTurn(row.swapped.lives);
      const key = row.before.lives+'/'+row.before.other;
      compare('twoPlayer', key+' lives', turn.lives, row.after.lives);
      compare('twoPlayer', key+' delay', turn.delay, row.after.delay);
      compare('twoPlayer', key+' spawnDelay', m.spawnTimer, row.after.spawnDelay);
      compare('twoPlayer', key+' fireball', m.fireballTimer, row.after.fireball);
      // a ★ tohle je ta chyba: život se ubere tomu, kdo přichází
      compare('twoPlayer', key+' the bug', row.after.lives,
              (row.swapped.lives-1) & 0xFF);
    });
  });

  console.log('');
  console.log('pripad'.padEnd(16)+'radku'.padStart(8)+'kontrol'.padStart(10)
              + 'rozdilu'.padStart(9)+'  nereprodukovatelne');
  results.forEach((result) => {
    console.log(result.name.padEnd(16)
                + String(result.rows).padStart(8)
                + String(result.checks).padStart(10)
                + String(result.bad).padStart(9)
                + (result.reported ? '  '+result.reported : ''));
  });
  console.log('');
  console.log('celkem %d kontrol, %d rozdilu, %d nereprodukovatelnych hodnot',
              total, bad, reported);
  if (bad) {
    console.log('CIL JE NULA ROZDILU');
    process.exit(1);
  }
  console.log('nula rozdilu');
} // main

main();
