#!/usr/bin/env node
/**
 * Projde celou smyčku workeru bez prohlížeče (M1, od M3 i s fyzikou).
 *
 *   ./tools/runworker.js [--frames N] [--verbose]
 *
 * `app/gameWorker.js` se spustí v atrapě prostředí workeru (postMessage,
 * setTimeout, importScripts) v režimu `headless`, kde tiká na vyžádání,
 * a projde se celý protokol z `app/WORKER-PROTOCOL.md`: `init`, `controls`,
 * `tick`, `pause`, `continue` a `reset`.
 *
 * Kontroluje se:
 *
 * - worker odpoví na `init` snímkem a drží hodnoty změřené na originálu
 *   (`data/global.json`: 4 životy, `HI` 102275),
 * - tik posouvá počítadlo snímků o jeden,
 * - stav ovládání dorazí celý, včetně **dvou směrů naráz** – osmisměrný pohyb
 *   znamená, že úhlopříčka není konflikt,
 * - `pause` zastaví a `continue` rozjede, `reset` zahodí stav,
 * - **Sabreman začíná tam, kde začíná originál** (obrazovka `$A8`, x 120,
 *   y 112, sprite `$10` – záznam z `$AC77`) a `GameDelayTimer` drží ovládání
 *   vypnuté prvních `$80` snímků, jako v originálu,
 * - a po prodlevě se s drženým `right` **rozejde**, do rychlosti, kterou
 *   změřila `tools/dumpphysics.py`. Že je ta chůze chůzí originálu krok po
 *   kroku, hlídá `tools/matchphysics.js`; tady se kontroluje, že celá cesta
 *   od zprávy `controls` až po záznam v `sabreman` drží.
 *
 * Tik je 50,08 Hz i tady, takže `--frames 50` je jedna sekunda hry.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..');

function loadDataFile(name) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, 'data', name+'.json'), 'utf8'));
}

/** spustí gameWorker.js v atrapě workeru a vrátí jeho rozhraní */
function startWorker(onMessage) {
  const sandbox = {
    console,
    performance: {now: () => Date.now()},
    setTimeout: () => 0,
    clearTimeout: () => {},
    postMessage: onMessage,
    importScripts(name) {
      const file = name.split('?')[0];
      vm.runInContext(fs.readFileSync(path.join(ROOT, 'app', file), 'utf8'), context,
                      {filename: file});
    },
  };
  sandbox.self = sandbox;
  sandbox.location = {search: ''};
  const context = vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(ROOT, 'app/gameWorker.js'), 'utf8'), context,
                  {filename: 'gameWorker.js'});
  return {
    send(message) { sandbox.onmessage({data: message}); },
    context: sandbox,
  };
}

function main() {
  const args = process.argv.slice(2);
  const frames = args.includes('--frames')
    ? parseInt(args[args.indexOf('--frames')+1], 10) : 100;
  const verbose = args.includes('--verbose');

  const global = loadDataFile('global');
  const messages = [];
  const worker = startWorker((message) => {
    messages.push(message);
    if (verbose) {
      console.log(JSON.stringify(message));
    }
  });

  const problems = [];
  const check = (condition, text) => {
    if (!condition) {
      problems.push(text);
    }
  };
  const last = () => messages[messages.length-1];

  // 1. init
  worker.send({id: 'init', initData: {
    headless: true, players: 2, lives: global.lives, hiScore: global.hiScore,
    scene: {room: global.initRoom, column: null, row: null},
    physics: loadDataFile('physics'), world: loadDataFile('world'),
    rooms: loadDataFile('rooms'), scenery: loadDataFile('scenery'),
    entities: loadDataFile('entities'),
    monsters: loadDataFile('monsters'), seed: 0x1234
  }});
  check(messages.length === 1 && last().id === 'frame', 'init neodpovedel snimkem');
  check(last().lives === global.lives,
        'zivoty: '+last().lives+' != '+global.lives+' z data/global.json');
  check(last().hiScore === global.hiScore,
        'HI: '+last().hiScore+' != '+global.hiScore+' z data/global.json');
  check(last().players === 2, 'players: '+last().players+' != 2');
  check(last().player === 1, 'player: '+last().player+' != 1');
  check(last().score === 0 && last().score2 === 0, 'skore nezacina na nule');
  // ★ startovní záznam originálu: sprite $10 na obrazovce $A8, x 120, y 112
  const start = last().sabreman;
  check(!!start, 'sabreman je null – chybi data/physics.json?');
  check(start && start.sprite === 0x10 && start.room === 0xA8
        && start.x === 120 && start.y === 112,
        'startovni zaznam: '+JSON.stringify(start));

  // 2. controls: dva směry naráz (osmisměrný pohyb) a meč
  worker.send({id: 'controls', left: true, up: true, sword: true,
               right: false, down: false});
  worker.send({id: 'tick'});
  const held = last().controls;
  check(held.left && held.up && held.sword && !held.right && !held.down,
        'ovladani nedoslo cele: '+JSON.stringify(held));

  // 3. tik posouvá počítadlo snímků
  const before = last().frame;
  for (let i = 0; i < frames; i++) {
    worker.send({id: 'tick'});
  }
  check(last().frame === before+frames,
        'snimky: '+last().frame+' != '+(before+frames));

  // 4. pause / continue: v headless režimu tiká jen `tick`, takže se kontroluje,
  //    že se stav neztratí
  worker.send({id: 'pause'});
  worker.send({id: 'continue'});
  worker.send({id: 'tick'});
  check(last().frame === before+frames+1, 'pause/continue ztratilo snimky');

  // 5. reset
  const count = messages.length;
  worker.send({id: 'reset'});
  worker.send({id: 'tick'});
  check(messages.length === count,
        'po resetu worker jeste tikal – tick po resetu nesmi nic poslat');

  // 6. fyzika: po prodlevě se Sabreman s drženým `right` rozejde
  worker.send({id: 'reset'});
  worker.send({id: 'init', initData: {
    headless: true, players: 1, lives: global.lives, hiScore: global.hiScore,
    scene: {room: global.initRoom, column: null, row: null},
    physics: loadDataFile('physics'), world: loadDataFile('world'),
    rooms: loadDataFile('rooms'), scenery: loadDataFile('scenery'),
    entities: loadDataFile('entities'),
    monsters: loadDataFile('monsters'), seed: 0x1234
  }});
  worker.send({id: 'controls', right: true, left: false, up: false,
               down: false, sword: false});
  const startX = last().sabreman.x;
  for (let i = 0; i < 0x80; i++) {
    worker.send({id: 'tick'});
  }
  check(last().sabreman.x === startX,
        'GameDelayTimer nedrzi: Sabreman se rozesel driv nez po $80 snimcich');
  for (let i = 0; i < 20; i++) {
    worker.send({id: 'tick'});
  }
  const walked = last().sabreman;
  check(walked.x > startX, 'Sabreman se nerozesel: x '+startX+' -> '+walked.x);
  check(walked.sprite >= 0x14 && walked.sprite <= 0x17,
        'poza chuze vpravo ma byt $14-$17, je '+walked.sprite.toString(16));
  check(walked.dx > 0, 'rychlost vpravo neni kladna: '+walked.dx);

  // 7. M4: svět. Amulet je rozmístěný do jedné z osmi sad, startovní obrazovka
  //    má orchidej podle své předlohy a je označená jako navštívená, takže
  //    procento už není nula.
  const entities = loadDataFile('entities');
  const sets = entities.amulet.sets;
  const world4 = last().entities;
  check(Array.isArray(world4), 'entities neni seznam');
  const orchids = world4.filter((e) => e.sprite >= 0x48 && e.sprite <= 0x4F);
  check(orchids.length === 1,
        'na startovni obrazovce ma byt jedna orchidej, je jich '+orchids.length);
  const startTemplate = 0x08;               // predloha obrazovky $A8 (M2)
  const wanted = entities.orchid.positions[startTemplate];
  check(orchids.length === 1 && orchids[0].x === wanted[0]
        && orchids[0].y === wanted[1],
        'orchidej ma byt na '+wanted+', je na '
        + (orchids[0] ? [orchids[0].x, orchids[0].y] : '-'));
  check(last().percent === entities.visited.percent[1],
        'procento po jedne navstivene obrazovce: '+last().percent
        + ' != '+entities.visited.percent[1]);
  check(last().amulet === 0, 'amulet nezacina prazdny: '+last().amulet);
  // amulet leží ve světě, takže se v seznamu objeví jen na svých čtyřech
  // obrazovkách – a startovní mezi nimi (skoro) nikdy není
  const pieces = world4.filter((e) => e.sprite >= 0x90 && e.sprite <= 0x93);
  check(pieces.length <= 4, 'kusu amuletu je vic nez ctyri');
  const scored = sets.some((set) => set.pieces.length === 4);
  check(scored, 'sady amuletu nemaji ctyri kusy');

  // 8. M5: nepratele. Do 400 pruchodu se musi na startovni obrazovce dosadit
  //    zvire ($9A3C, sest slotu a tri na obrazovku) a odpocet do ohnive koule
  //    ($96B4) se musi ubirat pruchod po pruchodu. Ze koule opravdu prijde,
  //    kontroluje tools/matchmonsters.js proti originalu; tady jde o to, ze
  //    to worker vubec pousti.
  const monstersData = loadDataFile('monsters');
  check(monstersData && monstersData.jumpTable,
        'chybi data/monsters.json – spust tools/dumpmonsters.py');
  worker.send({id: 'controls', right: false, left: false, up: false,
               down: false, sword: false});
  const roleOf = (sprite) => monstersData.jumpTable.handlers[sprite].role;
  const enemyRoles = ['materialise', 'materialiseDone', 'nastie', 'chaser',
                      'fireball'];
  let sawAnimal = false, counted = 0, previous = null;
  // ★ průchod smyčkou entit je každý druhý tik (disasm_notes §16, měřeno
  // 0,496 průchodu na snímek), takže 400 průchodů je 800 tiků
  for (let i = 0; i < 800; i++) {
    worker.send({id: 'tick'});
    const frame = last();
    if (!frame.sabreman) { break; }
    for (const entity of frame.entities) {
      if (enemyRoles.indexOf(roleOf(entity.sprite)) >= 0) { sawAnimal = true; }
    }
    const timer = frame.sabreman.fireballDelay;
    if (previous !== null && timer === previous-1) { counted++; }
    previous = timer;
  }
  check(sawAnimal, 'do 400 pruchodu se nedosadil zadny nepritel ($9A3C)');
  check(previous !== undefined && previous !== null,
        'snimek nenese sabreman.fireballDelay ($96B4)');
  check(counted > 100,
        'odpocet do ohnive koule se neubira: jen '+counted+' pruchodu ze 400');
  console.log('  nepratele: nepritel se objevil do 400 pruchodu, odpocet '
              + '$96B4 se ubral %dx (konci na %d)', counted, previous);

  // stojící Sabreman těch 800 tiků nepřežije, poslední zpráva je gameOver
  const lastFrame = messages.filter((m) => m.id === 'frame').pop();
  console.log('  svet: %d entit na startovni obrazovce (orchidej $%s na %d,%d), '
              + 'procento %d %%',
              world4.length,
              orchids.length ? orchids[0].sprite.toString(16).toUpperCase() : '-',
              wanted[0], wanted[1], lastFrame.percent);

  console.log('runworker: %d zprav, %d snimku, tik %s ms',
              messages.length, frames+2, (1000*69888/3500000).toFixed(4));
  console.log('  Sabreman: start x %d -> po 20 krocich x %d (sprite $%s, dx %d)',
              startX, walked.x, walked.sprite.toString(16).toUpperCase(),
              walked.dx);
  if (problems.length) {
    problems.forEach((text) => console.error('  CHYBA: '+text));
    process.exit(1);
  }
  console.log('  cely protokol v poradku (app/WORKER-PROTOCOL.md)');
}

main();
