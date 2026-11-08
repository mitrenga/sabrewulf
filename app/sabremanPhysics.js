// begin code

/**
 * Sabreman's physics — a transcription of the original's routines (M3).
 *
 * Nothing here is tuned by feel. Every number comes out of data/physics.json,
 * which tools/dumpphysics.py reads as the operands of the actual instructions
 * in the game's runtime image, and the control flow below is the disassembly
 * of these routines (runtime addresses, sources/docs/disasm_notes.md chap. 14):
 *
 *   $99D0  the entity loop: one step of Sabreman per frame
 *   $AECF  GamePlayEntry, $AEEF GamePlay_Start   sprites $10-$1F, under control
 *   $ADD0  PlayerMovement                        sprites $20-$2F, sword drawn
 *   $AFAC / $AFC1  the velocity and its cap, $AF66 / $B047 the decay
 *   $AFE8  the move and the four ways out of a screen ($B12F, $B187, $B19F,
 *          $B1AB)
 *   $B81C / $B873  the collision with the scenery
 *   $B053  the pose from the movement, $AE4B the pose while stabbing
 *   $A985  being killed, $A9BE the flight, $AA00 / $AA0D / $AA27 the respawn
 *   $A18C  the one place the game is won: room $88 above y=$80
 *
 * The method names are those addresses on purpose: this file is meant to be
 * read side by side with the disassembly, and tools/matchphysics.js checks it
 * **step by step against recorded runs of the original**
 * (tools/tracephysics.py) with zero differences as the target. The state it
 * works on is the game's own 12-byte entity record, so a step here and a step
 * there are directly comparable.
 *
 * Everything is in the machine's own terms: unsigned bytes, y counted
 * downwards and holding the sprite's **bottom** row, the speeds in 1/16 px
 * per step, the screen number as row<<4 | column, and one step per frame of
 * the original (50.08 Hz).
 *
 * ★ Three findings of M3 are worth having in mind while reading:
 *
 * - **E is up and R is down**, the other way round than the printed
 *   instructions say ($AF2F tests bit 3 = R and adds to y, and y grows
 *   downwards). Measured twice over — in the record and in the pixels.
 * - **The collision does not ask about pixels.** $B873 walks the very list of
 *   scenery pieces the room is drawn from and takes each piece's bounding box
 *   out of its header, so a wall is a little bigger than what is drawn. That
 *   is also what makes the map of the world computable rather than guessable
 *   (tools/mapwalk.py).
 * - **With the sword drawn Sabreman is slower**: $ADD0 writes the speed flat
 *   ($20 = 2 px a step) with no acceleration and no decay, against $30 (3 px)
 *   at the top of a normal walk. That closes an open question of ZADANI
 *   chap. 7 — and the contemporary POKEs the tips file as "walk speed"
 *   ($AE83/$AE85) are in HandlerOrchidTimer, i.e. they keep an orchid's
 *   effect from running out; the speed itself is the cap in $AFC1.
 *
 * The one thing that is NOT a transcription is the phase of the stab
 * animation: the original takes it from Rand8 ($9695), which it stirs with the
 * Z80 refresh register, so it cannot be reproduced tick for tick. The remake
 * feeds its own counter in; tools/matchphysics.js feeds the recorded value, so
 * the comparison stays exact where it can be.
 *
 * A classic script, deliberately free of DOM, Node and import syntax: the
 * worker takes it with importScripts, which cannot load an ES module, and the
 * offline tools with app/svision/tools/classicScript.cjs.
 */

var SabremanPhysics = (function () {
  'use strict';

  // the game's own record ($9702, 12 bytes, $AC6B copies 12 of them)
  var SPRITE = 0, ROOM = 1, STATE = 2, X = 3, Y = 4, ATTR = 5, DX = 6, DY = 7;
  // +$0B: which pieces of the amulet the player has, and in bit 7 the flag
  // that shows a verse of the poem ($970D, $A19F)
  var AMULET = 11;
  var RECORD_LENGTH = 12;

  /**
   * @param {Object} physics - The parsed data/physics.json (tools/dumpphysics.py).
   * @param {Object} world - The parsed data/world.json (the 16 x 16 Layout).
   * @param {Object} rooms - The parsed data/rooms.json (the 48 templates).
   * @param {Object} scenery - The parsed data/scenery.json (the 41 pieces).
   */
  function SabremanPhysics(physics, world, rooms, scenery) {
    if (!physics || !physics.values) {
      throw new Error('data/physics.json missing – run tools/dumpphysics.py');
    }
    this.v = physics.values;
    this.startRecord = physics.start;
    this.enterTopX = physics.enterTopX || null;

    // Layout ($6066): 256 bytes, one template number per screen
    this.layout = new Uint8Array(256);
    if (world && world.templates) {
      for (var row = 0; row < 16; row++) {
        for (var col = 0; col < 16; col++) {
          this.layout[row*16+col] = parseInt(world.templates[row].substr(col*2, 2), 16);
        }
      }
    }

    // the bounding boxes the collision asks about: one per piece of a template,
    // width and height straight out of the piece's own header ($B873 reads
    // them as LD A,(HL) / LD H,(HL) and turns the width in bytes into pixels)
    var sizes = {};
    if (scenery && scenery.pieces) {
      scenery.pieces.forEach(function (piece) {
        sizes[piece.id] = {height: piece.height,
                           width: rotateLeft3(piece.width) & 0xF8};
      });
    }
    this.boxes = [];
    var templates = (rooms && rooms.templates) || [];
    for (var t = 0; t < templates.length; t++) {
      var items = templates[t].items || '';
      var boxes = [];
      // three bytes per piece: its number and its X and Y in pixels — the raw
      // bytes of the template, low bits of X included (four records in the
      // game's data have an X that is not a multiple of eight and the
      // collision compares the whole byte)
      for (var i = 0; i+6 <= items.length; i += 6) {
        var size = sizes['$'+items.substring(i, i+2)];
        if (!size) {
          throw new Error('template '+t+' names a piece of scenery that is not '
                          + 'in data/scenery.json');
        }
        boxes.push({x: parseInt(items.substring(i+2, i+4), 16),
                    y: parseInt(items.substring(i+4, i+6), 16),
                    width: size.width, height: size.height});
      }
      this.boxes.push(boxes);
    }
  } // SabremanPhysics

  /** RLCA three times — an eight bit rotation, not a shift */
  function rotateLeft3(value) {
    for (var i = 0; i < 3; i++) {
      value = ((value << 1) | (value >> 7)) & 0xFF;
    }
    return value;
  } // rotateLeft3

  /** an eight bit two's complement byte as a number */
  function signed(byte) {
    return (byte & 0x80) ? byte-256 : byte;
  } // signed

  /** $B031: a signed speed in 1/16 px as whole pixels, rounded towards zero */
  function B031(speed) {
    if (!(speed & 0x80)) {
      return (speed >> 4) & 0x0F;
    }
    return -((((256-speed) & 0xFF) >> 4) & 0x0F);
  } // B031

  /**
   * The record the game starts with — the first of the 12 records $AC6B copies
   * from $AC77 into the game status buffer.
   * @returns {Uint8Array} A fresh 12 byte record.
   */
  SabremanPhysics.prototype.spawn = function () {
    var record = new Uint8Array(RECORD_LENGTH);
    var bytes = this.startRecord && this.startRecord.bytes;
    for (var i = 0; bytes && i < RECORD_LENGTH; i++) {
      record[i] = parseInt(bytes.substr(i*2, 2), 16);
    }
    return record;
  }; // spawn

  /** which of the 48 templates a screen number (row<<4 | column) is */
  SabremanPhysics.prototype.template = function (room) {
    return this.layout[room & 0xFF];
  }; // template

  /**
   * $B873 — is the box at (x, y) inside a piece of the room's scenery?
   *
   * `x` is the left edge of the box, `y` its **bottom** pixel row. Returns the
   * piece it runs into, or null. This is the whole of the game's idea of a
   * wall: no pixels are consulted, only the header of each piece.
   * @param {number} room - The screen number (row<<4 | column).
   * @param {number} x - Left edge of the box.
   * @param {number} y - Bottom row of the box.
   * @param {number} height - B of the LD BC of the caller ($16 for a walk).
   * @param {number} width - C of the same ($0E for a walk).
   * @returns {Object|null} The piece of scenery, or null when the box is free.
   */
  SabremanPhysics.prototype.collides = function (room, x, y, height, width) {
    var boxes = this.boxes[this.template(room)] || [];
    for (var i = 0; i < boxes.length; i++) {
      var box = boxes[i];
      var dx = (x-box.x) & 0xFF;                    // LD A,E / SUB (IX+$02)
      if (!(dx & 0x80)) {                           // JP P
        if (dx >= box.width) { continue; }          // CP H / JR NC
      } else if ((~dx & 0xFF) >= width) {           // CPL / CP C / JR NC
        continue;
      }
      var dy = (y-box.height-box.y) & 0xFF;         // SUB L / SUB (IX+$03)
      if (!(dy & 0x80)) {                           // JP P
        if (dy < height) { return box; }            // CP B / RET C
      } else if ((~dy & 0xFF) < box.height) {       // CPL / CP L / RET C
        return box;
      }
    }
    return null;
  }; // collides

  /**
   * $B81C — where the box ends up when the target is inside the scenery.
   *
   * The whole move is tried first; when it does not fit, each axis is tried on
   * its own and the one that does not fit either goes back to where it was.
   * ★ When both axes are free on their own and only their combination is
   * blocked, the original leaves Sabreman standing **in** the scenery. That is
   * reproduced, not fixed.
   * @param {number} room - The screen number.
   * @param {number} oldX - Where the box was.
   * @param {number} oldY - Where the box was.
   * @param {number} x - Where it wants to be.
   * @param {number} y - Where it wants to be.
   * @param {number} height - B of the caller's LD BC.
   * @param {number} width - C of the caller's LD BC.
   * @returns {Array} [x, y] after the slide.
   */
  SabremanPhysics.prototype.B81C = function (room, oldX, oldY, x, y, height, width) {
    if (this.collides(room, x, y, height, width) === null) {
      return [x, y];
    }
    if (this.collides(room, x, oldY, height, width) !== null) {
      x = oldX;
    }
    if (this.collides(room, oldX, y, height, width) !== null) {
      y = oldY;
    }
    return [x, y];
  }; // B81C

  /**
   * The nearest place in a screen where Sabreman fits — **a convenience of the
   * remake, not of the original.**
   *
   * The game only ever starts him on its own screen, where his own starting
   * position is clear. TRAINING SCREEN and PHYSICS SANDBOX can start anywhere,
   * and dropping him inside a tree would wedge him there for good: the axis
   * slide ($B81C) refuses a move whose target is blocked, so from inside the
   * scenery every direction is refused. So when the asked-for spot is taken,
   * this looks for the closest one that is not, in rings of four pixels.
   * @param {number} room - The screen number.
   * @param {number} x - Where he should stand.
   * @param {number} y - Where he should stand.
   * @returns {Array} [x, y] — the asked-for place, or the nearest free one.
   */
  SabremanPhysics.prototype.freeSpot = function (room, x, y) {
    var v = this.v;
    if (this.collides(room, x, y, v.boxHeight, v.boxWidth) === null) {
      return [x, y];
    }
    for (var radius = 4; radius <= 128; radius += 4) {
      for (var step = 0; step < 16; step++) {
        var angle = step*Math.PI/8;
        var tx = Math.round(x+radius*Math.cos(angle));
        var ty = Math.round(y+radius*Math.sin(angle));
        if (tx < 0 || tx > 0xFF-v.exitWidth
            || ty < v.exitTopY || ty >= v.exitBottomY) {
          continue;
        }
        if (this.collides(room, tx, ty, v.boxHeight, v.boxWidth) === null) {
          return [tx, ty];
        }
      }
    }
    return [x, y];
  }; // freeSpot

  /**
   * One step of Sabreman — the frame of the original's entity loop ($99D0).
   *
   * Everything the step does to the world outside the record comes back as
   * flags rather than being done here, because the worker owns the lives, the
   * sounds and the screen.
   * @param {Uint8Array} record - The 12 byte record, changed in place.
   * @param {Object} input - {left, right, up, down, sword}.
   * @param {Object} context - {frames, rand, lives} of this step.
   * @returns {Object} What happened: moved, roomChanged, sound, lifeLost,
   *                   gameOver, complete.
   */
  SabremanPhysics.prototype.step = function (record, input, context) {
    var out = {moved: false, roomChanged: false, sound: null, lifeLost: false,
               gameOver: false, complete: false, fireballDelay: 0,
               flashWhite: false, poem: 0};
    this.out = out;
    this.frames = (context && context.frames) || 0;
    this.rand = (context && context.rand) || 0;
    this.lives = (context && context.lives) || 0;
    // $96B0 OrchidEffectTimer — the world owns it (worldEntities.js sets it
    // when an orchid is taken), the step counts it down
    this.effect = (context && context.effect) || {timer: 0};
    var sprite = record[SPRITE];

    // $A18C is called first from both handlers: the one place the game is won
    if (this.A18C(record)) {
      return out;
    }
    // the jump table ($9B3E) hands each sprite number to its handler:
    // $10-$1F to $AECF, $20-$2F to $ADD0, $40 and $44 to $A9BE, $41/$42 and
    // $45/$46 to $AA0D, $43 and $47 to $A61B — Sabreman sitting down after a
    // yellow orchid.
    if (sprite === 0x40 || sprite === 0x44) {
      this.A9BE(record);
      return out;
    }
    if (sprite === 0x41 || sprite === 0x42 || sprite === 0x45 || sprite === 0x46) {
      this.AA0D(record);
      return out;
    }
    if (sprite === 0x43 || sprite === 0x47) {
      this.A61B(record);
      return out;
    }
    if (sprite >= 0x20 && sprite <= 0x2F) {
      this.ADD0(record, input);
      return out;
    }
    this.AEEF(record, input);
    return out;
  }; // step

  /**
   * $A18C — the gate: in room $88, above y=$80, the game is over and won.
   *
   * The keeper who is supposed to stop anybody without the amulet is an
   * entity, so that part is M5; this check itself asks nothing but where
   * Sabreman is. (Bit 7 of +$0B, tested right after, is what shows a verse of
   * the poem — nothing in M3 sets it, so it is left to M4.)
   * @param {Uint8Array} record - The record.
   * @returns {boolean} True when the step ends here.
   */
  SabremanPhysics.prototype.A18C = function (record) {
    if (record[ROOM] === 0x88 && record[Y] < 0x80) {
      this.out.complete = true;
      return true;
    }
    // $A19F: bit 7 of +$0B is set by picking a piece of the amulet up
    // (worldEntities.js, $A1D0). The game clears it and jumps to $A207, which
    // shows the picture of the amulet and ★ **one** verse of the poem — the
    // one that matches the number of pieces, not all the ones so far
    // (M6, tools/dumptext.py; roomModel.showPoem draws it).
    if (record[AMULET] & this.v.poemBit) {
      record[AMULET] &= ~this.v.poemBit;
      this.out.poem = record[AMULET];
    }
    return false;
  }; // A18C

  /**
   * $AE7A HandlerOrchidTimer — the effect of an orchid running out.
   *
   * ★ It only ticks on every other frame, so the $C0 an orchid hands out is
   * 384 frames, about seven and a half seconds. When it reaches zero Sabreman
   * goes back to white, which is what ends every effect at once: the speed
   * cap, the reversed controls, being untouchable and not being able to draw
   * the sword all hang off that one byte.
   * @param {Uint8Array} record - The record.
   * @returns {boolean} True while the timer has **not** just run out (Z80 NZ).
   */
  SabremanPhysics.prototype.AE7A = function (record) {
    var v = this.v;
    if (this.frames & v.effectTickEvery) {          // $AE7D: every other frame
      return true;
    }
    if (this.effect.timer === 0) {                  // $AE83: nothing running
      return false;
    }
    this.effect.timer--;
    if (this.effect.timer !== 0) {
      return true;
    }
    record[ATTR] = v.effectEndColour;               // $AE8A: back to white
    return false;
  }; // AE7A

  /**
   * $AE8F HandlerYellowOrchid — ★ the answer to what the yellow orchid does:
   * Sabreman **sits down and cannot move**.
   *
   * The pose keeps only which way he faces and the timer is written flat at
   * every step, so it never runs down here — what ends it is that the sprite
   * is no longer $1x, which sends the next step to $A61B instead.
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.AE8F = function (record) {
    var v = this.v;
    record[SPRITE] = (record[SPRITE] & v.yellowPoseMask) | v.yellowPoseBase;
    this.effect.timer = v.yellowTime;               // $AE99: $96B0 = $60
    this.A61E(record);
  }; // AE8F

  /**
   * $A61B — sitting there, and getting up again when the timer is done.
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.A61B = function (record) {
    this.A61E(record);
  }; // A61B

  /** $A61E — the shared tail of $AE8F and $A61B. */
  SabremanPhysics.prototype.A61E = function (record) {
    var v = this.v;
    if (!this.AE7A(record)) {                       // $A621: JR NZ
      record[SPRITE] = (record[SPRITE] & v.standUpMask) | v.standUpBase;
    }
    this.AF7A(record);
  }; // A61E

  /**
   * $AF7D — the last thing every controlled step does: while an orchid's
   * effect is running out, Sabreman is drawn **white every other beat** and
   * the game beeps. It is the warning that the effect is about to end.
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.AF7A = function (record) {
    var v = this.v;
    var timer = this.effect.timer;
    if (timer === 0 || timer >= v.effectFlashBelow) {
      return;
    }
    var phase = timer & v.effectFlashMask;
    if ((phase & v.effectBeepMask) === 0) {         // $AF91 / $AFA6: CALL Z
      this.out.sound = {name: 'orchidEnd'};
    }
    if (phase < v.effectFlashHalf) {                // $AF8D: JR NC
      this.out.flashWhite = true;                   // $AF98: drawn white
    }
  }; // AF7A

  /**
   * $AEEF GamePlay_Start — Sabreman under the player's control ($10-$1F).
   * @param {Uint8Array} record - The record.
   * @param {Object} input - The controls.
   */
  SabremanPhysics.prototype.AEEF = function (record, input) {
    var v = this.v;
    // $AEF5: a yellow Sabreman is a sitting Sabreman, and that is the whole
    // of the yellow orchid; $AEFC then counts any effect down
    if (record[ATTR] === v.colourYellow) {
      this.AE8F(record);
      return;
    }
    this.AE7A(record);                              // $AEFC
    this.exitWidth = v.exitWidth;                   // $AEFF: $96AD = $10
    if (record[STATE] !== 0) {                      // $AF04
      this.A985(record);
      return;
    }
    var controls = this.controls(input);
    // $AF11: ★ the magenta orchid reverses all four directions at once
    if (record[ATTR] === v.colourReverse) {
      controls ^= v.reverseMask;
    }
    this.AF1C(record, controls);
  }; // AEEF

  /**
   * $AF1C — the body of a controlled step, which $AE34 also jumps into when
   * the sword goes away in the middle of a step.
   * @param {Uint8Array} record - The record.
   * @param {number} controls - The bits of C.
   */
  SabremanPhysics.prototype.AF1C = function (record, controls) {
    var v = this.v;
    // one press is worth walkAccel of speed, and two of them can be held
    var e = 0, d = 0, b = v.walkAccel;
    if (controls & (1 << v.keyRight)) { e = (e+b) & 0xFF; }
    if (controls & (1 << v.keyLeft)) { e = (e-b) & 0xFF; }
    if (controls & (1 << v.keyDown)) { d = (d+b) & 0xFF; }
    if (controls & (1 << v.keyUp)) { d = (d-b) & 0xFF; }
    this.AFAC(record, e, d);                        // $AF3A
    var moved = this.AFE8(record);                  // $AF3D
    var target = this.B81C(record[ROOM], record[X], record[Y],
                           moved[0], moved[1], v.boxHeight, v.boxWidth);
    this.B053(record, target[0], target[1]);        // $AF46
    if (target[0] !== record[X] || target[1] !== record[Y]) {
      this.out.moved = true;                        // $AAED / $BF4B: the step
      // ★ $BF4B pípne jen každý osmý krok a pod modrozelenou orchidejí
      // dvakrát, takže barva Sabremana jde ven s ním
      this.out.sound = {name: 'step', colour: record[ATTR]};
    }
    record[X] = target[0];
    record[Y] = target[1];
    // $AF55: white Sabreman with the fire button held draws the sword — ★ so
    // under any orchid effect the sword cannot be drawn at all
    if (record[ATTR] === v.colourNormal && (controls & (1 << v.keyFire))) {
      this.ADBF(record);
    }
    this.AF66(record);                              // the decay, last
    this.AF7A(record);                              // $AF7A: the flash and beep
  }; // AEEF

  /**
   * $ADD0 PlayerMovement — Sabreman with the sword drawn ($20-$2F).
   *
   * ★ The speed is written flat here, not accumulated: no acceleration, no
   * cap, no decay, so stabbing costs a third of the walking speed.
   * @param {Uint8Array} record - The record.
   * @param {Object} input - The controls.
   */
  SabremanPhysics.prototype.ADD0 = function (record, input) {
    var v = this.v;
    this.exitWidth = v.exitWidth;                   // $ADD6: $96AD = $10
    if (record[STATE] !== 0) {                      // $ADDB
      this.A985(record);
      return;
    }
    var controls = this.controls(input);
    // $ADE8: only white Sabreman is under control, and letting go of fire
    // puts the sword away
    if (record[ATTR] !== v.colourNormal || !(controls & (1 << v.keyFire))) {
      this.AE34(record);
      this.AF1C(record, controls);                  // $AE44: JP $AF1C
      return;
    }
    var e = 0, d = 0;
    if (controls & (1 << v.keyRight)) { e = (e+v.swordSpeed) & 0xFF; }
    if (controls & (1 << v.keyLeft)) { e = (e+v.swordSpeedLeft) & 0xFF; }
    if (controls & (1 << v.keyDown)) { d = (d+v.swordSpeedDown) & 0xFF; }
    if (controls & (1 << v.keyUp)) { d = (d+v.swordSpeedUp) & 0xFF; }
    record[DX] = e;                                 // $AE13
    record[DY] = d;
    var moved = this.AFE8(record);                  // $AE19
    var target = this.B81C(record[ROOM], record[X], record[Y],
                           moved[0], moved[1], v.boxHeight, v.boxWidth);
    this.AE4B(record);                              // $AE22
    if (target[0] !== record[X] || target[1] !== record[Y]) {
      this.out.moved = true;                        // $AAED / $BF4B
      // ★ $BF4B pípne jen každý osmý krok a pod modrozelenou orchidejí
      // dvakrát, takže barva Sabremana jde ven s ním
      this.out.sound = {name: 'step', colour: record[ATTR]};
    }
    record[X] = target[0];
    record[Y] = target[1];
  }; // ADD0

  /**
   * $AE34 — putting the sword away: back to the walking pose.
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.AE34 = function (record) {
    // bit 3 of the stabbing sprite is "facing right", and $14 / $10 are the
    // first walking pose to each side
    record[SPRITE] = (record[SPRITE] & 0x08) ? 0x14 : 0x10;
    this.exitWidth = this.v.exitWidth;              // $AE3F
  }; // AE34

  /**
   * $ADBF — drawing the sword: the pose keeps the direction, the phase is lost.
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.ADBF = function (record) {
    var sprite = record[SPRITE];
    sprite = ((sprite << 1) | (sprite >> 7)) & 0xFF;    // RLCA
    record[SPRITE] = (sprite & 0x0F) | this.v.swordPoseBase;
    this.exitWidth = this.v.exitWidthSword;         // $ADCA: $96AD = $18
  }; // ADBF

  /** the controls as the bits of C in HandlerControls ($B0A3) */
  SabremanPhysics.prototype.controls = function (input) {
    var v = this.v, bits = 0;
    if (input) {
      if (input.left) { bits |= 1 << v.keyLeft; }
      if (input.right) { bits |= 1 << v.keyRight; }
      if (input.up) { bits |= 1 << v.keyUp; }
      if (input.down) { bits |= 1 << v.keyDown; }
      if (input.sword) { bits |= 1 << v.keyFire; }
    }
    return bits;
  }; // controls

  /**
   * $AFAC / $AFC1 — the speed builds up and is capped, the cap by the colour.
   * @param {Uint8Array} record - The record.
   * @param {number} e - The horizontal push of this step.
   * @param {number} d - The vertical push of this step.
   */
  SabremanPhysics.prototype.AFAC = function (record, e, d) {
    var v = this.v;
    var cap = v.speedCap;
    if (record[ATTR] === v.colourSlow) { cap = v.speedCapSlow; }
    else if (record[ATTR] === v.colourFast) { cap = v.speedCapFast; }
    record[DX] = this.AFC1((e+record[DX]) & 0xFF, cap);
    record[DY] = this.AFC1((d+record[DY]) & 0xFF, cap);
  }; // AFAC

  /** $AFC1 — |speed| clamped to the cap, sign kept */
  SabremanPhysics.prototype.AFC1 = function (speed, cap) {
    if (!(speed & 0x80)) {
      return speed < cap ? speed : cap;
    }
    var magnitude = (256-speed) & 0xFF;
    if (magnitude >= cap) { magnitude = cap; }
    return (256-magnitude) & 0xFF;
  }; // AFC1

  /** $AF66 / $B047 — every step the speed falls one step towards zero */
  SabremanPhysics.prototype.AF66 = function (record) {
    record[DX] = this.B047(record[DX], this.v.speedDecay);
    record[DY] = this.B047(record[DY], this.v.speedDecay);
  }; // AF66

  /** $B047 — |a| minus b, but never past zero */
  SabremanPhysics.prototype.B047 = function (a, b) {
    if (a & 0x80) {
      return (a+b) > 0xFF ? 0 : a+b;                // ADD A,B / RET NC / XOR A
    }
    return (a-b) >= 0 ? a-b : 0;                    // SUB B / RET NC / XOR A
  }; // B047

  /**
   * $AFE8 — the move, and the four ways out of a screen.
   *
   * Which is where the flick-screen happens: the exit is decided **before**
   * the collision (which the caller runs afterwards, already in the new
   * screen), so a screen can be left even when the place it leads to is
   * walled up — and then the slide puts Sabreman back where he was, on the
   * far side of the new screen. That quirk is the original's.
   * @param {Uint8Array} record - The record; +1 (the screen) can change.
   * @returns {Array} [x, y] the move wants, before the collision.
   */
  SabremanPhysics.prototype.AFE8 = function (record) {
    var e, d = record[Y];
    var step = B031(record[DX]);
    if (step >= 0) {
      e = (record[X]+step) & 0xFF;
      if (this.exitWidth+e > 0xFF) {                // $B002: JP C,$B19F
        return this.B19F(record, d);
      }
    } else {
      e = record[X]+step;                           // $B01A
      if (e < 0) {                                  // JP C,$B187
        return this.B187(record, d);
      }
    }
    step = B031(record[DY]);
    if (step >= 0) {
      d = (record[Y]+step) & 0xFF;
      if (d >= this.v.exitBottomY) {                // $B014: JP NC,$B12F
        return this.B12F(record, e);
      }
    } else {
      d = (record[Y]+step) & 0xFF;                  // $B027
      if (d < this.v.exitTopY) {                    // JP C,$B1AB
        return this.B1AB(record, e);
      }
    }
    return [e, d];
  }; // AFE8

  /** $B19F — out to the right: the column goes up, x starts at enterLeftX */
  SabremanPhysics.prototype.B19F = function (record, d) {
    this.B193(record, (record[ROOM]+1) & 0xFF);
    return [this.v.enterLeftX, d];
  }; // B19F

  /** $B187 — out to the left: the column goes down, x is the far right */
  SabremanPhysics.prototype.B187 = function (record, d) {
    this.B193(record, (record[ROOM]-1) & 0xFF);
    // $B187: E = -$96AD-1, so the box ends up one pixel inside the screen
    return [(-this.exitWidth-1) & 0xFF, d];
  }; // B187

  /**
   * $B193 — only the low nibble of the screen number changes.
   * ★ So the world wraps round inside its row: column 15 leads to column 0 of
   * the same row. The edges of the map are mountains, so it never happens in
   * play — but it is what the code does.
   * @param {Uint8Array} record - The record.
   * @param {number} moved - The screen number with the column already moved.
   */
  SabremanPhysics.prototype.B193 = function (record, moved) {
    record[ROOM] = (record[ROOM] & 0xF0) | (moved & this.v.roomColMask);
    this.enteredRoom(record);
  }; // B193

  /**
   * $B12F — out through the bottom: the row goes up, y starts at the top.
   *
   * ★ And x is **snapped to the passage**: the game reads it out of a 48 byte
   * table at $6036, one entry per template, which is where in that template
   * the corridor through the top is. Without it Sabreman would arrive inside
   * the jungle, because the vertical corridors are two pixels wide.
   * @param {Uint8Array} record - The record.
   * @param {number} e - The x the move had reached (thrown away).
   * @returns {Array} [x, y] in the new screen.
   */
  SabremanPhysics.prototype.B12F = function (record, e) {
    record[ROOM] = (record[ROOM]+this.v.roomStepRow) & 0xFF;
    this.enteredRoom(record);
    var x = this.enterTopX ? this.enterTopX[this.template(record[ROOM])] : e;
    return [x, this.v.enterTopY];
  }; // B12F

  /** $B1AB — out through the top: the row goes down, y starts at the bottom */
  SabremanPhysics.prototype.B1AB = function (record, e) {
    record[ROOM] = (record[ROOM]-this.v.roomStepRowUp) & 0xFF;
    this.enteredRoom(record);
    return [e, this.v.enterBottomY];
  }; // B1AB

  /**
   * $B148 — the tail of all four exits: only Sabreman redraws the screen.
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.enteredRoom = function (record) {
    var first = this.v.redrawFirstSprite;
    if (((record[SPRITE]-first) & 0xFF) >= this.v.redrawSpriteCount) {
      return;                                       // $B14F: RET NC
    }
    this.out.roomChanged = true;
    // ★ $B164 puts $96B4 back to $80 — and M5 found out what that byte is:
    // not the invulnerability M3 guessed at, but the countdown to the
    // fireball ($9ABC). So walking into a new screen buys the player time.
    this.out.fireballDelay = this.v.fireballDelay;
  }; // enteredRoom

  /**
   * $B053 — the pose out of the movement.
   *
   * The direction lives in bits 2 and 3 of the sprite number and the phase of
   * the walk in bits 0 and 1. ★ The horizontal direction is decided last, so
   * it wins: eight way movement, four poses. And the phase only moves on when
   * Sabreman does, so walking into a tree freezes the animation.
   * @param {Uint8Array} record - The record.
   * @param {number} e - The x the step ends on.
   * @param {number} d - The y the step ends on.
   */
  SabremanPhysics.prototype.B053 = function (record, e, d) {
    var v = this.v;
    this.B078(record, e, d);
    if (d !== record[Y]) {
      if (d < record[Y]) {
        record[SPRITE] = (record[SPRITE] & v.poseDirMask) | v.poseDirUp;
      } else {
        record[SPRITE] |= v.poseDirDown;
      }
    }
    if (e === record[X]) {
      return;
    }
    if (e < record[X]) {
      record[SPRITE] &= v.poseDirMask;
    } else {
      record[SPRITE] = (record[SPRITE] & v.poseDirMask) | v.poseDirRight;
    }
  }; // B053

  /** $B078 — the phase of the walk, every other frame and only when moving */
  SabremanPhysics.prototype.B078 = function (record, e, d) {
    var v = this.v;
    if (this.frames & v.posePhaseEvery) {
      return;                                       // RET NZ
    }
    if (((d ^ record[Y]) | (e ^ record[X])) === 0) {
      return;                                       // RET Z: nothing moved
    }
    record[SPRITE] = (record[SPRITE] & ~v.posePhaseMask & 0xFF)
                     | ((record[SPRITE]+1) & v.posePhaseMask);
  }; // B078

  /**
   * $AE4B — the pose while stabbing: the side from the movement, the phase
   * from Rand8 ($9695). The one thing in here that is not reproducible tick
   * for tick, because the original stirs Rand8 with the refresh register.
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.AE4B = function (record) {
    var v = this.v;
    if (record[DX] !== 0) {
      if (record[DX] & 0x80) {
        record[SPRITE] &= v.swordPoseFaceMask;      // $AE73
      } else {
        record[SPRITE] |= v.swordPoseFace;          // $AE54
      }
    }
    if (this.frames & v.swordPhaseEvery) {
      return;                                       // $AE5F: RET NZ
    }
    record[SPRITE] = (record[SPRITE] & v.swordPhaseKeep)
                     | (this.rand & v.swordPhaseMask);
  }; // AE4B

  /**
   * $A985 — being killed: Sabreman is thrown off his feet.
   *
   * What put the 1 or the 2 in +$02 is the contact test ($AB01, M5); from here
   * on it is physics. ★ Note the speeds are in **whole pixels** now, not in
   * 1/16: the flight adds them straight to the position ($A9BE).
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.A985 = function (record) {
    var v = this.v;
    var state = record[STATE];
    record[STATE] = v.deathCounter;
    if (state & 0x80) {                             // $A9AB
      record[SPRITE] = v.deathSpriteRight;
      record[DX] = 0;
      record[DY] = 4;
      record[X] = 0x78;
      return;
    }
    record[DY] = 0;
    if (state === 2) {                              // $A9A0
      record[SPRITE] = v.deathSpriteLeft;
      record[DX] = v.deathSpeedLeft;
    } else {
      record[SPRITE] = v.deathSpriteRight;
      record[DX] = v.deathSpeedRight;
    }
  }; // A985

  /**
   * $A9BE — the flight after being killed, until the scenery or the edge.
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.A9BE = function (record) {
    var v = this.v;
    var e = (record[X]+signed(record[DX])) & 0xFF;
    var d = (record[Y]+signed(record[DY])) & 0xFF;
    var target = this.B81C(record[ROOM], record[X], record[Y], e, d,
                           v.deathBoxHeight, v.deathBoxWidth);
    e = target[0];
    d = target[1];
    if ((e === record[X] && d === record[Y])        // $A9D5: nothing moved
        || e < v.deathMinX || e >= v.deathMaxX
        || d < v.deathMinY || d >= v.deathMaxY) {
      this.AA00(record);
      return;
    }
    record[X] = e;
    record[Y] = d;
    record[STATE] = (record[STATE]+1) & 0xFF;       // $A9F5
    // ★ výška tónu **je** fáze odletu ($A9F8: LD B,(IX+$02))
    this.out.sound = {name: 'fly', phase: record[STATE]};
  }; // A9BE

  /** $AA00 — the landing: the next sprite and the count down to the respawn */
  SabremanPhysics.prototype.AA00 = function (record) {
    record[SPRITE] = (record[SPRITE]+1) & 0xFF;
    record[STATE] = this.v.explodeCounter;
    this.out.sound = {name: 'land'};                // $BF2F
  }; // AA00

  /**
   * $AA0D — sitting there, counting down; on the last life he lies down.
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.AA0D = function (record) {
    record[STATE] = (record[STATE]-1) & 0xFF;
    if (record[STATE] === 0) {
      this.AA27(record);
      return;
    }
    // ★ $AA15 reads the lives **before** they are taken: with a life left
    // Sabreman only sits, and the "dead" pose ($42/$46) is the last life's
    if (this.lives !== 0) {
      return;
    }
    if (record[STATE] === this.v.explodeSecond) {
      record[SPRITE] = (record[SPRITE]+1) & 0xFF;
    }
  }; // AA0D

  /**
   * $AA27 — a life goes and Sabreman comes back **where he died**.
   * @param {Uint8Array} record - The record.
   */
  SabremanPhysics.prototype.AA27 = function (record) {
    var v = this.v;
    if (this.lives === 0) {
      this.out.gameOver = true;                     // $AAA4 / GameOver
      return;
    }
    this.out.lifeLost = true;
    record[SPRITE] = (record[SPRITE] & v.respawnSpriteMask) | v.respawnSpriteBase;
    record[ATTR] = v.respawnColour;
    // the speed of the flight is left alone on purpose: $AA27 does not touch
    // +$06, so the decay in $AF66 brings it down over the next few steps
    this.out.fireballDelay = v.fireballDelay;       // $AA52: $96B4 = $80
  }; // AA27

  SabremanPhysics.RECORD = {SPRITE: SPRITE, ROOM: ROOM, STATE: STATE, X: X,
                            Y: Y, ATTR: ATTR, DX: DX, DY: DY, AMULET: AMULET,
                            LENGTH: RECORD_LENGTH};
  SabremanPhysics.signed = signed;
  SabremanPhysics.B031 = B031;
  return SabremanPhysics;
})();

if (typeof self !== 'undefined') { self.SabremanPhysics = SabremanPhysics; }
if (typeof module !== 'undefined' && module.exports) { module.exports = SabremanPhysics; }
