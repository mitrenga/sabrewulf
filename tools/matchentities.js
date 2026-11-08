#!/usr/bin/env node
/**
 * Porovná **svět remaku se světem originálu, případ po případu**.
 *
 *   PYTHONPATH=tools/vendor ./tools/traceentities.py
 *   ./tools/matchentities.js [--verbose] [--case jmeno]
 *
 * `traceentities.py` nechá **originál v simulátoru spočítat sám sebe**: pro
 * každý případ položí do volné paměti `CALL rutina` a opíše, co po ní zůstalo
 * v „game status bufferu". Tenhle nástroj vezme tytéž vstupy, pustí na ně
 * `app/worldEntities.js` – tedy kód, který jde do prohlížeče – a porovná
 * výsledek. Čeká se **nula rozdílů**.
 *
 * Konstanty bere replika z `data/entities.json` (`tools/dumpentities.py`)
 * a mřížku světa z `data/world.json`, takže se kontroluje i to, že svět
 * v prohlížeči čte tatáž data jako originál.
 *
 * Dvě věci se replice **předávají z trasy**, protože je originál bere z míst,
 * která remake nemá:
 *
 * - `$5C78` (`FRAMES`) a `$9693` (počítadlo průchodů smyčkou entit) – na nich
 *   visí fáze kvetení orchideje, volba její barvy a blikání amuletu,
 * - **bajty ROM Spectra**, ze kterých `$A2BD` staví mapu předmětů. Z těch se
 *   dá zkontrolovat, kde předmět je a která ze čtyř pozic to je; **druh** se
 *   bere z `Rand8` míchaného obnovovacím registrem Z80, takže se nedá
 *   reprodukovat – přesně jako fáze seku mečem v M3, a stejně se to hlásí.
 *
 * Obdoba `matchphysics.js` pro svět (`sources/docs/disasm_notes.md` §16).
 */
'use strict';
const fs = require('fs');
const path = require('path');
const loadClassicScript = require(path.join(__dirname, '../app/svision/tools/classicScript.cjs'));

const ROOT = path.join(__dirname, '..');
const WorldEntities = loadClassicScript(path.join(ROOT, 'app/worldEntities.js'));
const R = WorldEntities.RECORD;

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

/** the three bytes of a BCD score as the number the panel prints */
function score(hex) {
  return parseInt(hex, 10);
} // score

function main() {
  const verbose = process.argv.includes('--verbose');
  const only = process.argv.indexOf('--case');
  const wanted = only >= 0 ? process.argv[only+1] : null;
  const tracePath = path.join(ROOT, 'build/entity-traces.json');
  if (!fs.existsSync(tracePath)) {
    console.error('chybi %s – spust nejdriv:\n'
                  + '  PYTHONPATH=tools/vendor ./tools/traceentities.py',
                  path.relative(ROOT, tracePath));
    process.exit(1);
  }
  const traces = load('build/entity-traces.json');
  const entities = load('data/entities.json');
  const worldData = load('data/world.json');
  const v = entities.values;

  const results = [];
  let total = 0, bad = 0, notes = [];

  /** a fresh world, so no case can leak state into the next */
  const fresh = () => {
    const world = new WorldEntities(entities, worldData);
    world.attach(new Uint8Array(R.LENGTH));
    return world;
  };

  /**
   * One comparison. `got` and `want` are compared as strings so a record and
   * a number are reported the same way.
   */
  const compare = (name, key, got, want, detail) => {
    total++;
    if (String(got) === String(want)) {
      return true;
    }
    bad++;
    if (bad <= 25 || verbose) {
      console.log('  %s %s: remake %s, original %s%s', name, key, got, want,
                  detail ? '   ('+detail+')' : '');
      if (String(got).length === 24 && String(want).length === 24) {
        const mine = parse(String(got)), theirs = parse(String(want));
        for (let i = 0; i < mine.length; i++) {
          if (mine[i] !== theirs[i]) {
            console.log('      '+FIELDS[i].padEnd(6)+' '+hexs([mine[i]])
                        + ' != '+hexs([theirs[i]]));
          }
        }
      }
    }
    return false;
  };

  const cases = traces.cases;
  const run = (name, body) => {
    if (!cases[name] || (wanted && wanted !== name)) {
      return;
    }
    const before = {total, bad};
    body(cases[name].rows);
    results.push({name: name, rows: cases[name].rows.length,
                  checks: total-before.total, bad: bad-before.bad,
                  note: cases[name].note});
  };

  // -- $AB01: kontakt Sabremana s entitou ------------------------------------
  run('contact', (rows) => {
    const world = fresh();
    rows.forEach((row) => {
      const entity = new Uint8Array(R.LENGTH);
      entity[R.SPRITE] = 0x60;
      entity[R.ROOM] = 0xA8;
      entity[R.X] = 100;
      entity[R.Y] = 100;
      world.sabreman = new Uint8Array(R.LENGTH);
      world.sabreman[R.SPRITE] = row.sprite;
      world.sabreman[R.ROOM] = 0xA8;
      world.sabreman[R.X] = row.x;
      world.sabreman[R.Y] = row.y;
      world.delay = 0;
      const hit = world.AB01(entity, row.box >> 8, row.box & 0xFF);
      compare('contact', 'sprite $'+row.sprite.toString(16)
              + ' box $'+row.box.toString(16)+' at '+row.x+','+row.y,
              hit, row.hit);
    });
  });

  // -- $A763: stav předlohy rozbalený do záznamu orchideje -------------------
  run('orchidSpawn', (rows) => {
    const world = fresh();
    rows.forEach((row) => {
      world.orchidState[row.template] = row.state.slice();
      world.orchid = new Uint8Array(R.LENGTH);
      world.spawnOrchid(row.room);
      // ★ `$A763` zapisuje **osm bajtů** záznamu (+0 až +7) a +8..+11 nechává
      // na tom, co v paměti bylo – trasa je proto předplní $EE a porovnává se
      // jen to, co rutina skutečně zapíše
      compare('orchidSpawn', 'room $'+row.room.toString(16)
              + ' state '+row.state, hexs(world.orchid.subarray(0, 8)),
              row.record.substr(0, 16));
    });
  });

  // -- $A79F: a zabalený zpátky ---------------------------------------------
  run('orchidSave', (rows) => {
    const world = fresh();
    rows.forEach((row) => {
      world.orchid = parse(row.record);
      world.orchidState[row.template] = [0, 0];
      world.saveOrchid(row.room);
      compare('orchidSave', 'room $'+row.room.toString(16)
              + ' record '+row.record,
              world.orchidState[row.template].join(','), row.state.join(','));
    });
  });

  // -- $A680: celý cyklus kvetení a sebrání orchideje ------------------------
  const bloom = (name, rows, sabremanAt) => {
    const world = fresh();
    const template = world.template(0xA8);
    world.orchidState[template] = [0x0F, 0x02];
    world.spawnOrchid(0xA8);
    const sabreman = new Uint8Array(R.LENGTH);
    sabreman[R.SPRITE] = 0x10;
    sabreman[R.ROOM] = 0xA8;
    sabreman[R.X] = sabremanAt[0];
    sabreman[R.Y] = sabremanAt[1];
    sabreman[R.ATTR] = 0x47;
    world.attach(sabreman);
    rows.forEach((row, index) => {
      world.out = {sounds: [], points: 0, extraLife: false, picked: [],
                   effect: null, poem: 0};
      world.sabreman = sabreman;
      world.frames = row.frames;
      world.sweeps = row.sweeps;
      world.delay = 0;
      world.lives = 4;
      world.A680();
      // jako u `orchidSpawn`: rutina píše osm bajtů, +8..+11 nechává být
      const ok = compare(name, 'call '+index+' (sweeps '+row.sweeps+')',
                         hexs(world.orchid.subarray(0, 8)),
                         row.record.substr(0, 16));
      compare(name, 'call '+index+' effect', world.effect.timer, row.effect);
      compare(name, 'call '+index+' colour', sabreman[R.ATTR], row.colour);
      if (!ok) {
        // po prvním rozdílu by se stav rozešel a všechno další by byl šum,
        // takže se replika srovná na to, co má originál
        world.orchid = parse(row.record);
        world.effect.timer = row.effect;
        sabreman[R.ATTR] = row.colour;
      }
    });
  };
  run('orchidBloom', (rows) => bloom('orchidBloom', rows, [0x20, 0xB0]));
  run('orchidPick', (rows) => bloom('orchidPick', rows,
                                    entities.orchid.positions[8]));

  // -- $A33B: dva předměty obrazovky z bajtů mapy ---------------------------
  run('objectSpawn', (rows) => {
    const world = fresh();
    rows.forEach((row) => {
      world.objectMap[row.room*2] = row.map[0];
      world.objectMap[row.room*2+1] = row.map[1];
      world.objects = [new Uint8Array(R.LENGTH), new Uint8Array(R.LENGTH)];
      world.spawnObjects(row.room);
      // ★ `$A356` nechává +2 a +8..+11 na tom, co v záznamu bylo; originál má
      // v těch bajtech zbytek minulé entity, remake nulu, takže se porovnává
      // to, co rutina skutečně zapisuje
      const written = [R.SPRITE, R.ROOM, R.X, R.Y, R.ATTR, R.DX, R.DY];
      [0, 1].forEach((slot) => {
        const theirs = parse(row.records.substr(slot*24, 24));
        const mine = world.objects[slot];
        const pick = (record) => written.map((i) => (record[R.SPRITE] || i === R.SPRITE)
                                             ? record[i] : 0).join(',');
        compare('objectSpawn', 'room $'+row.room.toString(16)
                + ' map '+row.map+' slot '+slot, pick(mine), pick(theirs));
      });
    });
  });

  // -- $A312 / $A305: sebrání předmětu, body a extra život ------------------
  run('objectPick', (rows) => {
    rows.forEach((row) => {
      const world = fresh();
      const room = 0xA8, index = room*2;
      world.objectMap[index] = 0xC0 | row.kind;
      const sabreman = new Uint8Array(R.LENGTH);
      sabreman[R.SPRITE] = 0x10;
      sabreman[R.ROOM] = room;
      sabreman[R.X] = row.near ? 100 : 160;
      sabreman[R.Y] = 100;
      sabreman[R.ATTR] = 0x47;
      world.attach(sabreman);
      const record = world.objects[0];
      record[R.SPRITE] = 0x80+row.kind;
      record[R.ROOM] = room;
      record[R.X] = 100;
      record[R.Y] = 100;
      record[R.ATTR] = 0x42;
      record[R.DX] = index & 0xFF;
      record[R.DY] = index >> 8;
      const turn = world.step(sabreman, {frames: 0, sweeps: 0, delay: 0,
                                         lives: row.lives});
      compare('objectPick', 'kind '+row.kind+' lives '+row.lives
              + (row.near ? ' near' : ' far'), record[R.SPRITE],
              parse(row.record)[R.SPRITE]);
      compare('objectPick', 'kind '+row.kind+' map byte',
              world.objectMap[index], row.map);
      compare('objectPick', 'kind '+row.kind+' score', turn.points,
              score(row.score));
      compare('objectPick', 'kind '+row.kind+' lives '+row.lives+' after',
              row.lives+(turn.extraLife ? 1 : 0), row.livesAfter);
    });
  });

  // -- $A255: rozmístění amuletu pro všech 256 hodnot Rand8 -----------------
  run('amuletPlace', (rows) => {
    const world = fresh();
    rows.forEach((row) => {
      world.placeAmulet(row.rand);
      // originál nechává +2 a +8..+11 na tom, co v paměti bylo; porovnávají
      // se bajty, které `$A255` zapisuje
      let mine = '', theirs = '';
      for (let piece = 0; piece < 4; piece++) {
        const want = parse(row.records.substr(piece*24, 24));
        const got = world.amulet[piece];
        [R.SPRITE, R.ROOM, R.X, R.Y, R.ATTR].forEach((i) => {
          mine += hexs([got[i]]);
          theirs += hexs([want[i]]);
        });
      }
      compare('amuletPlace', 'rand $'+row.rand.toString(16), mine, theirs);
    });
  });

  // -- $A1AB: blikání a sebrání kusu amuletu --------------------------------
  run('amuletPick', (rows) => {
    rows.forEach((row) => {
      const world = fresh();
      const room = 0xA8;
      const sabreman = new Uint8Array(R.LENGTH);
      sabreman[R.SPRITE] = 0x10;
      sabreman[R.ROOM] = room;
      sabreman[R.X] = row.near ? 100 : 160;
      sabreman[R.Y] = 100;
      sabreman[R.ATTR] = 0x47;
      sabreman[R.AMULET] = row.bits;
      world.attach(sabreman);
      world.amulet.forEach((record) => { record[R.SPRITE] = 0; });
      const record = world.amulet[0];
      record[R.SPRITE] = row.sprite;
      record[R.ROOM] = room;
      record[R.X] = 100;
      record[R.Y] = 100;
      record[R.ATTR] = row.colour;
      const turn = world.step(sabreman, {frames: 0, sweeps: row.sweeps,
                                         delay: 0, lives: 4});
      const want = parse(row.record);
      const key = 'sprite $'+row.sprite.toString(16)+' sweeps '+row.sweeps
                  + ' colour $'+row.colour.toString(16)
                  + (row.near ? ' near' : ' far')+' bits '+row.bits;
      compare('amuletPick', key+' sprite', record[R.SPRITE], want[R.SPRITE]);
      compare('amuletPick', key+' colour', record[R.ATTR], want[R.ATTR]);
      compare('amuletPick', key+' bits', sabreman[R.AMULET], row.bitsAfter);
      compare('amuletPick', key+' score', turn.points, score(row.score));
    });
  });

  // -- $9D41: domorodec v přímce se zakopaným kusem -------------------------
  run('pointing', (rows) => {
    const world = fresh();
    traces.pointingPieces.forEach((hex, i) => {
      world.amulet[i] = parse(hex);
    });
    rows.forEach((row) => {
      const entity = new Uint8Array(R.LENGTH);
      entity[R.SPRITE] = 0x3C;
      entity[R.ROOM] = row.room;
      entity[R.X] = row.x;
      entity[R.Y] = row.y;
      const point = world.A9D41(entity);
      compare('pointing', 'room $'+row.room.toString(16)
              + ' at '+row.x+','+row.y, !!point, row.hit);
      if (row.hit) {
        compare('pointing', 'room $'+row.room.toString(16)
                + ' at '+row.x+','+row.y+' distance',
                point ? point.distance : -1, row.distance);
      }
    });
  });

  // -- $9D23: bit navštívené obrazovky --------------------------------------
  run('visitRoom', (rows) => {
    rows.forEach((row) => {
      const world = fresh();
      world.visitRoom(row.room);
      let index = -1, bit = -1, ones = 0;
      for (let i = 0; i < world.visited.length; i++) {
        for (let b = 0; b < 8; b++) {
          if (world.visited[i] >> b & 1) {
            ones++;
            if (index < 0) { index = i; bit = b; }
          }
        }
      }
      compare('visitRoom', 'room $'+row.room.toString(16),
              index+':'+bit+':'+ones, row.byte+':'+row.bit+':'+row.ones);
    });
  });

  // -- $9CC6: procento navštívených obrazovek -------------------------------
  run('percent', (rows) => {
    const world = fresh();
    rows.forEach((row) => {
      compare('percent', 'count '+row.count,
              entities.visited.percent[row.count], row.percent);
    });
  });

  // -- $A2BD: generátor mapy předmětů ---------------------------------------
  run('objectMap', (rows) => {
    rows.forEach((row) => {
      const world = fresh();
      const source = parse(row.sourceBytes);
      world.generateObjectMap((i) => source[i], {value: row.rand});
      const theirs = parse(row.map);
      let places = 0, slots = 0, kinds = 0, unknown = 0;
      for (let i = 0; i < theirs.length; i++) {
        const mine = world.objectMap[i];
        const wanted = source[i] < v.objectMapThreshold;
        if (!wanted) {
          // bajt ROM nad prahem: na téhle obrazovce předmět není
          if (theirs[i] !== 0 || mine !== 0) { places++; }
          continue;
        }
        // ★ pozice se bere z dolního bajtu počítadla smyčky, takže je
        // reprodukovatelná; druh z `Rand8`, takže není
        if ((theirs[i] & 0xC0) !== (mine & 0xC0)) { slots++; }
        if ((mine & 0xC0) === 0) {
          // pozice 0 a druh 0 dají bajt $00, který je od „žádný předmět"
          // k nerozeznání – a druh je z Rand8, takže tady se ani nedá říct,
          // jestli tam předmět je
          unknown++;
          continue;
        }
        if (theirs[i] === 0) { places++; }
        if ((theirs[i] & 0x0F) !== (mine & 0x0F)) { kinds++; }
      }
      compare('objectMap', 'source '+row.source+' kde je predmet', places, 0);
      compare('objectMap', 'source '+row.source+' ktera pozice', slots, 0);
      const filled = theirs.reduce((n, b) => n+(b ? 1 : 0), 0);
      notes.push('objectMap '+row.source+': '+filled+' z '+theirs.length
                 + ' slotu plnych ('+(100*filled/theirs.length).toFixed(1)+' %); '
                 + 'druh predmetu se rozchazi v '+kinds+' a v '+unknown
                 + ' slotech na pozici 0 nejde rict ani to, jestli tam predmet '
                 + 'je – ★ druh se bere z Rand8 michaneho obnovovacim '
                 + 'registrem Z80 (nereprodukovatelne, jako faze seku mecem v M3)');
    });
  });

  console.log('');
  results.forEach((result) => {
    console.log('  '+result.name.padEnd(13)
                + String(result.rows).padStart(5)+' radek, '
                + String(result.checks).padStart(6)+' kontrol, '
                + result.bad+' rozdilu   ('+result.note+')');
  });
  notes.forEach((note) => console.log('  %s', note));
  console.log('');
  if (bad) {
    console.log(total+' KONTROL, '+bad+' ROZDILU');
    process.exit(1);
  }
  console.log(total+' kontrol proti originalu ve '+results.length
              + ' pripadech: NULA ROZDILU');
} // main

main();
