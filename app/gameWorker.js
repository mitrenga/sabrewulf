// begin code

/**
 * Sabre Wulf game worker.
 *
 * The tick is the frame rate of the original machine: 3.5 MHz / 69888 T states
 * = 50.08 Hz, because the game logic hangs off the ULA interrupt
 * (sources/docs/hw_notes.md, ZADANI chap. 1). This file keeps the clock, the
 * protocol (WORKER-PROTOCOL.md), the control state, the panel values and the
 * two players.
 *
 * Since M3 it also **steps Sabreman**, and none of that step is invented here:
 * sabremanPhysics.js is a transcription of the original's own routines driven
 * by data/physics.json, whose every number tools/dumpphysics.py reads as the
 * operand of an actual instruction, and tools/matchphysics.js checks it step
 * by step against recorded runs of the original with zero differences
 * (2323 steps in thirteen scenarios). The state it steps is the game's own
 * 12-byte entity record, which is what goes over to the model as `sabreman`.
 *
 * One step per tick is the original's own cadence for Sabreman — with one
 * exception worth knowing about: when the original walks off a screen it
 * redraws the whole play area, and its main loop needs six to eight frames for
 * that one step. That is Z80 timing, not a rule of the game, so the remake
 * takes it in a single tick. The **other entities** are a different matter:
 * their pass completes a sweep only every other frame (measured, see tick()),
 * so the world and the enemies step on every second tick.
 *
 * ★ Two players are part of the protocol from the start, not bolted on later:
 * the original has two life counters ($96BD, $96E0) and two scores ($9698,
 * $969B), takes turns between them, and gives the pair a longer changeover
 * delay (GameDelayTimer, $96B5: $80 for one player, $FF for two). The
 * changeover rule itself — and the bug in two-player mode the contemporary
 * reviews mention — is M5, and so is everything that can kill Sabreman: the
 * physics of dying is here (his flight, the pose, the life going, the respawn
 * on the spot), but nothing in M3 starts it except the sandbox.
 */

var query = (typeof self !== 'undefined' && self.location) ? self.location.search : '';
importScripts('sabremanPhysics.js'+query);
importScripts('worldEntities.js'+query);
importScripts('worldMonsters.js'+query);

var TICK_MS = 1000*69888/3500000;     // 50.08 Hz, the ULA interrupt rate
// frames one sweep of the entity pass takes on the original (tick() explains):
// 1.9-2.3 with an empty screen, animals or the Wulf, 4.46 with the fireball
var SWEEP_FRAMES = 2;
var SWEEP_FRAMES_FIREBALL = 4.46;
var RECORD = SabremanPhysics.RECORD;

var state = null;
var physics = null;
var world = null;
var monsters = null;
// ★ $B235 ChangePlayer swaps the whole entity table, the map of objects
// and VisitedRooms between the two players, so in a two player game each
// of them really does walk his own world. The remake keeps one of these
// per player and swaps which one is live.
var sides = [null, null];
var timer = 0;
var lastTime = false;
var accumulator = 0;

function reset() {
  clearTimeout(timer);
  timer = 0;
  lastTime = false;
  accumulator = 0;
  state = {
    running: false, paused: false, headless: false,
    frame: 0,
    players: 1, player: 1,
    // measured on the running original (data/global.json): the panel shows
    // four lives at the start and a preset HI of 102275
    lives: [4, 4],
    score: [0, 0],
    hiScore: 0,
    scene: null,
    controls: {left: false, right: false, up: false, down: false, sword: false},
    sounds: [],
    // Sabreman's own record ($9702, 12 bytes) and the two counters of the
    // game status buffer the step needs
    record: null,
    room: null,
    delay: 0,
    // ★ $96B4: the countdown to the fireball, not the invulnerability M3
    // took it for. $B148 puts it back to $80 on every screen change (M5)
    fireballDelay: 0,
    rand: 0,
    randState: 0x9E3779B9,                            // nextRand()
    // M4: the percentage of the world seen, which the original prints on the
    // GAME OVER screen, and which pieces of the amulet the player has
    percent: 0,
    amulet: 0,
    poem: 0,
    // $9693, and the fraction of the next sweep already elapsed (tick())
    sweeps: 0,
    sweepPhase: 0,
    // $AEA1: FLASH on the active player's score label while the delay runs
    labelFlash: false,
    // $AECF: Sabreman is not drawn while the delay runs
    hidden: false,
    gameOverPosted: false,
    gameOverFor: 0,
    complete: false
  };
} // reset

/**
 * ★ Rand8 ($9695) stands in for the one thing in the physics that cannot be
 * reproduced tick for tick: the original stirs it with the Z80 refresh
 * register ($99D0: LD A,R / ADC A,(Rand8)), and the phase of the sword swing
 * comes out of it. A remake has no refresh register, so it counts its own
 * pseudo-random byte; tools/matchphysics.js feeds the recorded values in, so
 * the comparison with the original stays exact everywhere it can be.
 */
function nextRand(s) {
  // ★ A 32-bit LCG (Numerical Recipes) with the **top** byte taken as Rand8.
  // Until 2026-09-08 this was an 8-bit LCG (`rand*5+frame+1`), and the low
  // bits of a power-of-two LCG have a period of 2, 4, 8: the phase of the
  // sword ($AE4B, `rand & 7` every fourth frame) came out constant whenever
  // the byte was stirred an even number of times a frame — i.e. with 3 or 7
  // entities in the room the swing stood still, and every `rand & 1` choice
  // of the animals was just as lame. The top byte carries the full period.
  // (no Math.imul: 2^32 * 1664525 < 2^53, so the product is exact in a double)
  s.randState = (s.randState*1664525+1013904223) >>> 0;
  s.rand = s.randState >>> 24;
  return s.rand;
} // nextRand

/**
 * The stand-in for the source of "randomness" the original's map of objects
 * comes out of.
 *
 * ★ $A2BD reads 512 bytes out of the **ZX ROM** ($0000-$20FF) and takes every
 * byte under $80 as "there is an object on this screen". The ROM is not in our
 * sources at all — the runtime image is $4000-$FFFF — so this is the one place
 * in M4 the remake cannot repeat byte for byte, the same kind of hole as the
 * phase of the sword swing in M3. What is reproduced is the rule and the
 * **density**: measured on the running original, 358 of the 512 slots come out
 * filled (69.9 %) — it depends on where in the ROM the read starts, and
 * tools/matchentities.js sees 55 % to 79 % over four seeds — so this source
 * says yes about as often as the ROM does.
 * @param {number} seed - Where to start, so a turn is repeatable.
 * @returns {Function} source(i) -> a byte in the ROM's stead.
 */
function objectMapSource(seed) {
  var value = (seed|0) & 0xFFFF;
  return function () {
    // a plain 16 bit LCG; the threshold $80 is the original's, and 70 % of
    // 256 is 179, so the low bit pattern is skewed to match what the ROM does
    value = (value*29+113) & 0xFFFF;
    var byte = (value >> 5) & 0xFF;
    return (byte < 179) ? (byte*0x80/179)|0 : byte;
  };
} // objectMapSource

/**
 * One player's whole world: his record, the entities of M4 and the enemies of
 * M5. $B21E makes one of these at the start of a game — the amulet goes into
 * one of eight sets and the map of objects is generated — and $B235 swaps
 * them over when the players change.
 * @param {Object} initData - The init message.
 * @param {number} seed - Where this player's pseudo-random source starts.
 * @returns {Object} {record, world, monsters}.
 */
function makeSide(initData, seed) {
  var record = physics.spawn();
  var side = {record: record, world: null, monsters: null};
  if (!initData.entities) {
    return side;
  }
  side.world = new WorldEntities(initData.entities, initData.world);
  side.world.attach(record);
  // M5: the enemies, which need the scenery (through the physics) and the
  // world (the natives point at a buried piece of the amulet)
  if (initData.monsters) {
    side.monsters = new WorldMonsters(initData.monsters, initData.entities,
                                      physics, side.world);
  }
  side.world.placeAmulet(seed);                       // $A255
  side.world.generateObjectMap(objectMapSource(seed), {value: seed & 0xFF});
  return side;
} // makeSide

/** Make one of the two sides the live one — what $B235 does by copying. */
function activate(s, player) {
  var side = sides[player-1];
  s.player = player;
  s.record = side.record;
  world = side.world;
  monsters = side.monsters;
  s.amulet = world ? (world.amuletBits() & 0x0F) : 0;
  s.percent = world ? world.percentComplete() : 0;
  s.fireballDelay = monsters ? monsters.fireballTimer : 0;
} // activate

/**
 * $AA27 — what happens when Sabreman is caught.
 *
 * ★ And this is where the bug the reviews of 1984 complained about lives. In
 * a one player game $AA2E takes the life off the player who died. In a two
 * player game $AA5A hands over to $B205 instead, which swaps the players
 * **and then** calls $B1B7 — and $B1B7 is what takes a life off. So the life
 * comes off the player who is arriving, not the one who died. Measured in
 * tools/tracemonsters.py (`twoPlayer`) and reproduced, because that is the
 * rule of this project.
 * @param {Object} s - The worker state.
 * @param {Object} events - What the physics step reported.
 */
function died(s, events) {
  var other = s.lives[2-s.player];
  if (s.players === 2 && other > 0) {                 // $AA5E: JR Z,$AA2E
    if (s.lives[s.player-1] === 0) {
      // $AA64: GAME OVER for this player, but the other one plays on
      s.gameOverFor = s.player;
    }
    activate(s, 3-s.player);                          // $B205 -> $B235
    var turn = monsters ? monsters.startTurn(s.lives[s.player-1])
                        : {lives: (s.lives[s.player-1]-1) & 0xFF, delay: 0x80};
    s.lives[s.player-1] = turn.lives;                 // ★ $B1B7, the bug
    s.delay = turn.delay;                             // $96B5 = $80
    s.fireballDelay = monsters ? monsters.fireballTimer : 0;
    return;
  }
  if (events.gameOver) {                              // $AA32: JR Z,$AAA4
    s.gameOverPosted = true;
    return;
  }
  s.lives[s.player-1] = Math.max(0, s.lives[s.player-1]-1);
} // died

/** Is the fireball ($9762) on the screen Sabreman is on? */
function fireballOnScreen(s) {
  var fire = monsters.fireball();
  return fire[0] !== 0 && fire[1] === s.record[RECORD.ROOM];
}

/** one step of the original's main loop: FrameUpdate ($99BC) */
function tick() {
  var s = state;
  s.frame++;
  s.sounds.length = 0;
  // ★ Sloka básně je událost jednoho tiku, ne stav: $A18C ten bit shodí a
  // hned na to skočí na $A207. Kdyby tady nezhasla, obrazovka básně by se
  // otevírala každý tik znovu.
  s.poem = 0;
  // $AECF GamePlayEntry: while the changeover delay runs ($96B5, $80 frames
  // for one player) Sabreman's handler does three things and nothing else
  // ($AEA1): every sixteenth frame it clicks ($BF2A, the orchid's own sound),
  // it sets FLASH on the three cells of the active player's score label, and
  // it draws nothing — so the man is **not on the screen** until the delay
  // is over, while the rest of the entity pass goes on below (the orchid
  // grows; $9A3C refuses to put animals in while the timer runs). On the
  // frame the timer reaches zero the FLASH comes off ($AEBD) and the step
  // runs as usual ($AEE8 -> $AEEF).
  var waiting = false;
  if (s.delay > 0) {
    s.delay--;                                          // $AED6
    if (s.delay > 0) {                                  // $AED7 JR NZ,$AEA1
      if ((s.delay & 0x0F) === 0) {                     // $AEA2: AND $0F
        s.sounds.push({name: 'orchid'});                // $AEA4: CALL Z,$BF2A
      }
      s.labelFlash = true;                              // $AEB0
      waiting = true;
    } else {
      s.labelFlash = false;                             // $AEBD
    }
  }
  s.hidden = waiting;
  if (!physics || !s.record) {
    return;
  }
  var wasRoom = s.record[RECORD.ROOM];
  var events = waiting ? null
    : physics.step(s.record, s.controls,
                   {frames: s.frame, rand: nextRand(s),
                    lives: s.lives[s.player-1],
                    effect: world ? world.effect : null});
  if (events && events.sound) {
    s.sounds.push(events.sound);
  }
  if (events) {
    s.flashWhite = events.flashWhite;
    if (events.poem) {
      // ★ $A18C shodí ten bit a skočí na $A207: **jedna** sloka, ta, která
      // odpovídá počtu kusů amuletu (M6, tools/dumptext.py) – ne všechny
      // předchozí, jak si M4 zapsal
      s.poem = events.poem;
    }
    if (events.fireballDelay) {
      s.fireballDelay = events.fireballDelay;
      if (monsters) { monsters.roomChanged(); }        // $B164: $96B4 = $80
    }
    if (events.lifeLost || events.gameOver) {
      died(s, events);
    }
    if (events.complete) {
      // $A18C: room $88 above y=$80 and the game is won. What the original shows
      // then is the closing screen and MusicData_GameComplete (data/text.json,
      // data/music.json) — the models play it, because in the original it runs
      // with interrupts disabled, i.e. while the game stands still.
      s.complete = true;
      s.gameOverPosted = true;
    }
  } // events
  // M4: the world. Walking off a screen marks the new one visited ($9D23 out
  // of $B148) and hands the orchid of the old template back to the table
  // before unpacking the new one and spawning its objects ($BBAE).
  if (world) {
    if (s.record[RECORD.ROOM] !== wasRoom) {
      world.visitRoom(s.record[RECORD.ROOM]);
      world.enterRoom(s.record[RECORD.ROOM], wasRoom);
    }
  }
  // ★ The entity pass is **not** once a frame. Sabreman gets his step every
  // frame, but the rest of the table (slots 1-24: animals, the Wulf, the
  // fireball, orchids, objects) is handled by a second pass that resumes where
  // the interrupt left it ($99F0 keeps the place in $96A9) and $9693 counts
  // completed sweeps. Measured on the running original (2026-09-07, 1065
  // frames on the start screen, standing and walking): 0.496 sweeps a frame —
  // one sweep every two frames on average, the single sweep taking 1 to 6
  // frames depending on what is being drawn. Until then the remake ran a
  // sweep every tick and every enemy moved twice as fast as the original
  // (disasm_notes.md §16).
  //
  // ★ The load is what sets the pace, and one thing changes it a lot: the
  // **fireball**. Measured with the fireball on Sabreman's screen the sweep
  // takes 4.46 frames (it is wide, it flickers and it changes colour every
  // pass), so the fireball crawls at about a pixel a frame while Sabreman does
  // three — and everything else on that screen slows down with it. The Z80
  // itself is not simulated (a measured per-entity cost, as Highway Encounter
  // has in data/cadence.json, is the proper job and is left for M7); this is
  // the two measured cadences: SWEEP_FRAMES without the fireball,
  // SWEEP_FRAMES_FIREBALL with it, and `sweeps` is what $9693 would hold.
  var period = (monsters && s.record && fireballOnScreen(s)) ? SWEEP_FRAMES_FIREBALL : SWEEP_FRAMES;
  s.sweepPhase += 1/period;
  var sweepTick = s.sweepPhase >= 1;
  if (sweepTick) {
    s.sweepPhase -= 1;
    s.sweeps++;
  }
  var sweeps = s.sweeps;
  if (world && sweepTick) {
    var turn = world.step(s.record, {frames: s.frame, sweeps: sweeps,
                                     delay: s.delay,
                                     lives: s.lives[s.player-1]});
    if (turn.points) {
      s.score[s.player-1] = WorldEntities.addBCD(s.score[s.player-1], turn.points);
    }
    if (turn.extraLife) {
      s.lives[s.player-1]++;              // $A2F8 has already refused a tenth
    }
    // ★ turn.poem is **not** taken: $A1AB only sets bit 7 of $970D, and it is
    // $A18C in Sabreman's own handler — physics.step(), the next tick — that
    // clears the bit and opens the verse (events.poem above). Taking both put
    // the verse on the screen twice: the model paused the worker on the
    // world's flag, and the physics raised it again after the continue
    // (seen 2026-09-07 on picking up a piece of the amulet).
    for (var i = 0; i < turn.sounds.length; i++) {
      s.sounds.push(turn.sounds[i]);
    }
    s.amulet = world.amuletBits() & 0x0F;
    s.percent = world.percentComplete();
  }
  // M5: the enemies. They are slots 1-17 of the same sweep, so they run
  // between Sabreman (slot 0, above) and the world (slots 18-24), and the two
  // things $9A1D does at the end of a sweep — putting an animal into the
  // world and putting out a fireball — go with them.
  // ★ Rand8 is stirred by the Z80 refresh register **once per entity** in the
  // original ($99D0), so each of them sees a different byte. The remake has no
  // refresh register; it hands over its own source and WorldMonsters.stir()
  // draws a fresh byte before every entity (until 2026-09-07 all of them saw
  // one byte a sweep, and moved in lockstep). tools/matchmonsters.js feeds the
  // recorded values in call by call, so the comparison with the original
  // stays exact.
  if (monsters && s.record && sweepTick) {
    var hunt = monsters.step(s.record, {frames: s.frame, sweeps: sweeps,
                                        delay: s.delay, rand: s.rand,
                                        nextRand: function () { return nextRand(s); }});
    if (hunt.points) {
      s.score[s.player-1] = WorldEntities.addBCD(s.score[s.player-1],
                                                 hunt.points);
    }
    for (var h = 0; h < hunt.sounds.length; h++) {
      s.sounds.push(hunt.sounds[h]);
    }
    // ★ what an entity that catches him does is write 1, 2 or $80 into +$02
    // of his record ($9704) and nothing else; his own step picks it up on the
    // next sweep and $A985 throws him off his feet. So dying is M3's code
    // started by M5's contact, exactly as in the original.
    if (hunt.killed && s.record[RECORD.STATE] === 0) {
      s.record[RECORD.STATE] = hunt.killed;
    }
    s.fireballDelay = monsters.fireballTimer;
  }
} // tick

function postFrame() {
  var s = state;
  postMessage({
    id: 'frame',
    frame: s.frame,
    players: s.players,
    player: s.player,
    score: s.score[0],
    score2: s.score[1],
    hiScore: Math.max(s.hiScore, s.score[0], s.score[1]),
    lives: s.lives[s.player-1],
    // the machine's own coordinates: x is the left edge of the sprite and y
    // its **bottom** pixel row, counted in screen rows with the panel taking
    // the first 16 (WORKER-PROTOCOL.md)
    sabreman: s.record ? {
      sprite: s.record[RECORD.SPRITE],
      room: s.record[RECORD.ROOM],
      column: s.record[RECORD.ROOM] & 0x0F,
      row: s.record[RECORD.ROOM] >> 4,
      state: s.record[RECORD.STATE],
      x: s.record[RECORD.X],
      y: s.record[RECORD.Y],
      colour: s.record[RECORD.ATTR],
      // $AF7D draws him white while an orchid's effect runs out
      flash: s.flashWhite,
      // $AECF: not drawn at all while the changeover delay runs
      hidden: s.hidden,
      dx: SabremanPhysics.signed(s.record[RECORD.DX]),
      dy: SabremanPhysics.signed(s.record[RECORD.DY]),
      // ★ $96B4 is the countdown to the fireball (M5), not invulnerability
      fireballDelay: s.fireballDelay
    } : null,
    entities: (s.record ? (world ? world.visible(s.record[RECORD.ROOM]) : [])
                          .concat(monsters
                                  ? monsters.visible(s.record[RECORD.ROOM]) : [])
                        : []),
    // M4: the orchid effect running, the pieces of the amulet and the
    // percentage of the world seen ($9CC6 prints it on GAME OVER)
    effect: world ? world.effect.timer : 0,
    amulet: s.amulet,
    percent: s.percent,
    poem: s.poem,
    labelFlash: s.labelFlash,
    // ★ in a two player game one player can be finished while the other plays
    // on ($AA64 shows GAME OVER PLAYER x and $B205 hands over anyway)
    gameOverFor: s.gameOverFor || 0,
    controls: {left: s.controls.left, right: s.controls.right,
               up: s.controls.up, down: s.controls.down, sword: s.controls.sword},
    sounds: s.sounds.slice(),
    state: s.complete ? 'complete' : (s.gameOverPosted ? 'gameOver' : 'game')
  });
  if (s.gameOverPosted && s.running) {
    // ★ a jestli hra skončila **výhrou**: originál na to má vlastní obrazovku
    // ($9F91) a vlastní skladbu (MusicData_GameComplete), tak ať to ví i model
    postMessage({id: 'gameOver', score: s.score[s.player-1],
                 complete: s.complete});
    s.running = false;
    clearTimeout(timer);
  }
} // postFrame

function loop() {
  var now = (typeof performance !== 'undefined') ? performance.now() : Date.now();
  if (lastTime === false) {
    lastTime = now;
  }
  accumulator = Math.min(250, accumulator+now-lastTime);
  lastTime = now;
  var ticked = false;
  while (accumulator >= TICK_MS) {
    tick();
    accumulator -= TICK_MS;
    ticked = true;
  }
  if (ticked) {
    postFrame();
  }
  if (state.running && !state.paused) {
    timer = setTimeout(loop, Math.max(1, TICK_MS-accumulator));
  }
} // loop

reset();

onmessage = function (event) {
  var msg = event.data;
  switch (msg.id) {
    case 'init':
      var initData = msg.initData || {};
      reset();
      state.headless = !!initData.headless;
      state.players = (initData.players === 2) ? 2 : 1;
      var lives = (initData.lives === undefined) ? 4 : initData.lives;
      state.lives = [lives, lives];
      state.hiScore = initData.hiScore || 0;
      state.scene = initData.scene || null;
      state.running = true;
      // the physics needs the world it walks in: the constants
      // (data/physics.json), the 16 x 16 Layout, the 48 templates and the 41
      // pieces of scenery, because the collision asks the very list of pieces
      // the room is drawn from ($B873) — under 60 kB for all 256 screens
      physics = null;
      world = null;
      monsters = null;
      sides = [null, null];
      state.gameOverFor = 0;
      state.record = null;
      if (initData.physics) {
        try {
          physics = new SabremanPhysics(initData.physics, initData.world,
                                        initData.rooms, initData.scenery);
          // M4/M5: one world per player. $B1D4 builds player 2's first, then
          // player 1's, and each gets its own amulet, its own map of objects
          // and its own enemies ($B21E twice, with $B235 in between).
          var seed = initData.seed|0;
          state.randState = (seed ^ 0x9E3779B9) >>> 0;       // nextRand()
          sides[0] = makeSide(initData, seed);
          sides[1] = makeSide(initData, (seed*7+0x1D) & 0xFFFF);
          activate(state, 1);
          // TRAINING SCREEN starts somewhere else than the game does; the
          // record is otherwise the game's own ($AC77). His own starting
          // place can be inside a tree on another screen, and from inside the
          // scenery every move is refused, so the physics finds the nearest
          // spot where he fits — a convenience of the remake, not a rule
          if (state.scene && typeof state.scene.column === 'number') {
            state.record[RECORD.ROOM] = (state.scene.row << 4)
                                        | (state.scene.column & 0x0F);
            var spot = physics.freeSpot(state.record[RECORD.ROOM],
                                        state.record[RECORD.X],
                                        state.record[RECORD.Y]);
            state.record[RECORD.X] = spot[0];
            state.record[RECORD.Y] = spot[1];
          }
          if (world) {
            world.visitRoom(state.record[RECORD.ROOM]); // $9D23 out of $B1F8
            world.enterRoom(state.record[RECORD.ROOM], null);   // $BBAE
            state.percent = world.percentComplete();
          }
        } catch (error) {
          postMessage({id: 'error', message: error.message});
        }
      }
      // GameDelayTimer ($96B5): $80 frames for one player, $FF for two
      state.delay = (state.players === 2) ? 0xFF : 0x80;
      // and the man is not on the screen before the delay has run ($AECF):
      // the first frame goes out before the first tick, so it says so too
      state.hidden = state.delay > 0;
      if (!state.headless) {
        loop();
      }
      postFrame();
      break;
    case 'controls':
      Object.keys(state.controls).forEach(function (action) {
        state.controls[action] = !!msg[action];
      });
      break;
    case 'pause':
      state.paused = true;
      clearTimeout(timer);
      break;
    case 'continue':
      if (state.running) {
        state.paused = false;
        lastTime = false;
        clearTimeout(timer);
        if (!state.headless) {
          loop();
        }
      }
      break;
    case 'tick':
      if (state.running) {
        tick();
        postFrame();
      }
      break;
    case 'reset':
      reset();
      break;
  }
};
