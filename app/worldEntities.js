// begin code

/**
 * The world of Sabre Wulf: orchids, objects, the amulet and the rooms visited.
 *
 * This is to M4 what sabremanPhysics.js is to M3 — a transcription of the
 * original's own routines, driven by data/entities.json, whose every number
 * tools/dumpentities.py reads as the operand of an actual instruction (100
 * instructions and table ends checked). Nothing here is invented and nothing
 * is tuned: where the original does something odd, so does this.
 *
 * The routines, in the order the game reaches them:
 *
 * - $A2BD generates the **map of objects**, two bytes per screen, at the start
 *   of every player's turn, and $A255 PlaceAmuletPieces picks one of **eight
 *   ready-made sets** of four screens for the amulet.
 * - $A763 / $A79F unpack and pack the **orchid** of a screen. ★ Its state is
 *   held **per template, not per screen** — the game indexes TableOrchidTypes
 *   with the template out of Layout, so all 21 screens of template $11 share
 *   one orchid.
 * - $A33B / $A356 spawn the **two objects** of a screen out of the map byte and
 *   the template's own four positions (ObjectLocation, $DC6C).
 * - $A680 / $A6D4 / $A70D bloom the orchid and $A737 hands out its effect;
 *   $A312 and $A305 pick objects up (and $A2F8 adds a life, ★ up to nine);
 *   $A1AB picks up a piece of the amulet, which is worth 7500 and reveals a
 *   verse of the poem.
 * - $9D23 marks a screen visited and $9CC6 turns that into the percentage —
 *   ★ counting the four pieces of the amulet in, so the whole is 260.
 * - $9D41 is the rule behind the natives who point at a buried piece.
 *
 * ★ One thing about the cadence. The original's main loop gives Sabreman a
 * step every frame, but the other entities are handled by a second pass that
 * resumes where the interrupt left it ($99F0 keeps the place in $96A9), and
 * $9693 — the counter the orchid and the amulet flash on — advances once per
 * **sweep** of that pass, not once per frame. Measured on the running
 * original: a sweep takes about two frames (0.508 sweeps per frame over 800
 * frames; 0.496 over 1065 frames when re-measured for M7, one sweep taking 1
 * to 6 frames). That is Z80 timing, not a rule of the game, so the remake does
 * not simulate the load: gameWorker.js runs **one sweep every other tick**
 * (until 2026-09-07 it ran one every tick, and every enemy moved twice as
 * fast). tools/matchentities.js compares **sweep against sweep**, the same
 * discipline M3 used for steps.
 */

var WorldEntities = (function () {
  'use strict';

  // the game's own record ($9702, 12 bytes) — the same offsets as the physics
  var SPRITE = 0, ROOM = 1, STATE = 2, X = 3, Y = 4, ATTR = 5, DX = 6, DY = 7;
  // ★ +$0B of **Sabreman's** record is where the game keeps which pieces of
  // the amulet the player has ($970D, read by $A1CD and $9CDC); bit 7 of the
  // same byte is the "show a verse of the poem" flag $A18C looks at.
  var AMULET = 11;
  var RECORD_LENGTH = 12;

  /**
   * @param {Object} entities - The parsed data/entities.json (tools/dumpentities.py).
   * @param {Object} world - The parsed data/world.json (the 16 x 16 Layout).
   */
  function WorldEntities(entities, world) {
    if (!entities || !entities.values) {
      throw new Error('data/entities.json missing – run tools/dumpentities.py');
    }
    this.v = entities.values;
    this.data = entities;

    // Layout ($6066): one template number per screen
    this.layout = new Uint8Array(256);
    if (world && world.templates) {
      for (var row = 0; row < 16; row++) {
        for (var col = 0; col < 16; col++) {
          this.layout[row*16+col] = parseInt(world.templates[row].substr(col*2, 2), 16);
        }
      }
    }

    this.orchidPositions = entities.orchid.positions;
    this.orchidColours = entities.orchid.colours;
    this.objectLocations = entities.objects.locations;
    this.objectColours = entities.objects.types.map(function (type) {
      return type.colour;
    });
    this.objectLife = entities.objects.types.reduce(function (found, type) {
      return type.extraLife ? type.type : found;
    }, -1);
    this.amuletSets = entities.amulet.sets;
    this.percent = entities.visited.percent;

    this.reset();
  } // WorldEntities

  /** an eight bit two's complement byte as a number */
  function signed(byte) {
    return (byte & 0x80) ? byte-256 : byte;
  } // signed

  /** RLCA — an eight bit rotation, not a shift */
  function rotateLeft(value, times) {
    for (var i = 0; i < times; i++) {
      value = ((value << 1) | (value >> 7)) & 0xFF;
    }
    return value;
  } // rotateLeft

  /** RRCA */
  function rotateRight(value, times) {
    for (var i = 0; i < times; i++) {
      value = ((value >> 1) | (value << 7)) & 0xFF;
    }
    return value;
  } // rotateRight

  /** the game's scores are BCD ($B5A9 does ADD/ADC and DAA) */
  function addBCD(score, points) {
    return (score+points) % 1000000;
  } // addBCD

  WorldEntities.prototype.reset = function () {
    var v = this.v;
    // two bytes of orchid state per template ($A7F8), starting from the
    // table the game ships
    this.orchidState = this.data.orchid.types.map(function (pair) {
      return pair.slice();
    });
    this.objectMap = new Uint8Array(v.objectMapCount);      // $DDEC, 2 per room
    this.visited = new Uint8Array(this.data.visited.bytes); // $96BF, 256 bits
    this.amuletSet = 0;
    this.record = null;                                     // Sabreman's record
    // the records the game keeps: one orchid, two objects, four amulet pieces
    this.orchid = new Uint8Array(RECORD_LENGTH);
    this.objects = [new Uint8Array(RECORD_LENGTH), new Uint8Array(RECORD_LENGTH)];
    this.amulet = [];
    for (var i = 0; i < v.amuletPieces; i++) {
      this.amulet.push(new Uint8Array(RECORD_LENGTH));
    }
    this.effect = {timer: 0};                               // $96B0
    this.room = null;
    this.sweeps = 0;                                        // $9693
  }; // reset

  /**
   * The record M4 shares with the physics: Sabreman's own, because +$0B of it
   * is where the pieces of the amulet are kept.
   * @param {Uint8Array} record - Sabreman's 12 byte record.
   */
  WorldEntities.prototype.attach = function (record) {
    this.record = record;
  }; // attach

  /** Which pieces of the amulet the player has ($970D, bits 0-3). */
  WorldEntities.prototype.amuletBits = function () {
    return this.record ? this.record[AMULET] : 0;
  }; // amuletBits

  /** which of the 48 templates a screen number (row<<4 | column) is */
  WorldEntities.prototype.template = function (room) {
    return this.layout[room & 0xFF];
  }; // template

  // -------------------------------------------------------------------------
  // the start of a player's turn ($B21E: PlaceAmuletPieces then $A2BD)
  // -------------------------------------------------------------------------

  /**
   * $A255 PlaceAmuletPieces — four pieces into one of eight ready-made sets.
   *
   * ★ The place is not random: only the **choice of set** is. `Rand8 & 7`
   * ($A25C) picks a row of four screens out of $A29D, and where in the screen
   * a piece lies is decided by the template — slot 0 of its ObjectLocation.
   * @param {number} rand - Rand8 ($9695) at the moment of the call.
   */
  WorldEntities.prototype.placeAmulet = function (rand) {
    var v = this.v;
    this.amuletSet = rand & v.amuletSetMask;
    var set = this.amuletSets[this.amuletSet];
    for (var i = 0; i < v.amuletPieces; i++) {
      var piece = set.pieces[i];
      var record = this.amulet[i];
      record[SPRITE] = piece.sprite;                    // $A26C: B + $8F
      record[ROOM] = piece.room;
      record[STATE] = 0;
      record[X] = piece.x;
      record[Y] = piece.y;
      record[ATTR] = v.amuletColour;                    // $A290: $46
      record[DX] = 0;
      record[DY] = 0;
    }
    if (this.record) {
      this.record[AMULET] = 0;
    }
  }; // placeAmulet

  /**
   * $A2BD — the map of objects, two bytes per screen.
   *
   * ★ The original seeds this from the **ZX ROM**: DE is
   * (counter & $1F) * 256 + FRAMES, so it reads 512 bytes from somewhere in
   * $0000-$20FF, and a byte under $80 means "there is an object here". The
   * runtime image is $4000-$FFFF, so the ROM is not in our sources at all —
   * this is the one place in M4 the remake cannot repeat byte for byte, the
   * same kind of hole as the phase of the sword swing in M3. The rule itself
   * is reproduced exactly; only the source of the bits is ours.
   * @param {Function} source - source(i) -> the byte the original would read.
   * @param {Object} rand - {value} — Rand8, stirred as the loop goes.
   */
  WorldEntities.prototype.generateObjectMap = function (source, rand) {
    var v = this.v;
    var count = v.objectMapCount;
    for (var i = 0; i < count; i++) {
      var byte = source(i) & 0xFF;
      if (byte >= v.objectMapThreshold) {               // $A2CF: CP $80
        this.objectMap[i] = 0;
        continue;
      }
      // $A2DD: the slot comes out of the low byte of the loop counter, which
      // counts down from objectMapCount
      var counter = (count-i) & 0xFF;
      var slot = rotateRight(counter, 2) & v.objectMapSlotMask;
      this.objectMap[i] = slot | (rand.value & v.objectMapTypeMask);
      // $A2EB stirs Rand8 with the Z80 refresh register (LD A,R / ADC): the
      // register cannot be reproduced, so the stir is the loop index instead —
      // the mixer and the thresholds stay the original's (CLAUDE.md, Nahoda)
      rand.value = (rand.value+i+1) & 0xFF;
    }
  }; // generateObjectMap

  // -------------------------------------------------------------------------
  // entering a screen ($BBAE, called from $B148 and $B1D4)
  // -------------------------------------------------------------------------

  /**
   * $BBAE — what the game does when the play area has been redrawn: puts the
   * orchid of the screen it left back into the table, unpacks the orchid of
   * the new one and spawns its two objects.
   * @param {number} room - The screen number, row<<4 | column.
   * @param {number|null} previous - The screen left behind ($96AB), or null.
   */
  WorldEntities.prototype.enterRoom = function (room, previous) {
    if (previous !== null && previous !== undefined) {
      this.saveOrchid(previous);                        // $A79F
    }
    this.room = room & 0xFF;
    this.spawnOrchid(this.room);                        // $A763
    this.spawnObjects(this.room);                       // $A33B
  }; // enterRoom

  /**
   * $A763 — the two bytes of the template's orchid state unpacked into a record.
   * @param {number} room - The screen number.
   */
  WorldEntities.prototype.spawnOrchid = function (room) {
    var v = this.v;
    var template = this.template(room);
    var pair = this.orchidState[template];
    var low = pair[0], high = pair[1];
    var position = this.orchidPositions[template];
    var record = this.orchid;
    record[SPRITE] = (low & v.orchidSpriteMask) | v.orchidSpriteBase;
    record[ROOM] = room;
    record[STATE] = low & v.orchidStateMask;
    record[X] = position[0];
    record[Y] = position[1];
    record[ATTR] = (high & v.orchidColourMask) | v.orchidColourBase;
    record[DX] = high & v.orchidTimerLowMask;           // the 12 bit timer,
    record[DY] = (low >> 4) & v.orchidTimerHighMask;    // low byte then high
  }; // spawnOrchid

  /**
   * $A79F — and packed back, so the orchid goes on blooming while Sabreman is
   * somewhere else. ★ It is written back under the **template of the screen he
   * left**, which is why one orchid is shared by every screen of a template.
   * @param {number} room - The screen the orchid belongs to ($96AB).
   */
  WorldEntities.prototype.saveOrchid = function (room) {
    var v = this.v;
    var record = this.orchid;
    var pair = this.orchidState[this.template(room)];
    pair[0] = (record[SPRITE] & v.orchidSpriteMask)
              | (record[STATE] & v.orchidStateMask)
              | ((rotateLeft(record[DY], 4)) & 0xF0);
    pair[1] = (record[ATTR] & v.orchidColourMask)
              | (record[DX] & v.orchidTimerLowMask);
  }; // saveOrchid

  /**
   * $A33B / $A356 — the two objects of a screen out of its two map bytes.
   *
   * The byte holds the kind in its low four bits and which of the template's
   * four positions in its top two; zero means there is no object. The record
   * keeps the address of its own map byte in +$06/+$07, which is how picking
   * an object up removes it for good.
   * @param {number} room - The screen number.
   */
  WorldEntities.prototype.spawnObjects = function (room) {
    var v = this.v;
    for (var slot = 0; slot < 2; slot++) {
      var record = this.objects[slot];
      record[SPRITE] = 0;                               // $A33E: XOR A / LD (DE),A
      var index = (room & 0xFF)*2+slot;                 // $A39C: ADD HL,HL
      var byte = this.objectMap[index];
      if (!byte) {
        continue;
      }
      var type = byte & v.objectTypeMask;
      var place = rotateLeft(byte, 3) & v.objectSlotMask;
      var position = this.objectLocations[this.template(room)][place >> 1];
      record[SPRITE] = (type+v.objectSpriteBase) & 0xFF;
      record[ROOM] = room;
      record[X] = position[0];
      record[Y] = position[1];
      record[ATTR] = this.objectColours[type];
      // +$06/+$07 keep the **address** of the map byte, which is how $A323
      // removes the object from the whole game and not just from the screen
      var pointer = (v.objectMap+index) & 0xFFFF;
      record[DX] = pointer & 0xFF;
      record[DY] = pointer >> 8;
    }
  }; // spawnObjects

  // -------------------------------------------------------------------------
  // one sweep of the entity pass
  // -------------------------------------------------------------------------

  /**
   * All the M4 entities of the screen Sabreman is on, one handler call each.
   *
   * @param {Uint8Array} sabreman - Sabreman's record ($9702).
   * @param {Object} context - {frames, sweeps, delay, lives, score}.
   * @returns {Object} What happened: sounds, points, lives, verses of the poem.
   */
  WorldEntities.prototype.step = function (sabreman, context) {
    var out = {sounds: [], points: 0, extraLife: false, picked: [],
               effect: null, poem: 0};
    this.out = out;
    this.sabreman = sabreman;
    this.frames = context.frames|0;                     // $5C78 FRAMES
    this.sweeps = (context.sweeps === undefined) ? this.sweeps : context.sweeps|0;
    this.delay = context.delay|0;                       // $96B5 GameDelayTimer
    this.lives = context.lives|0;
    this.A680();                                        // the orchid
    for (var i = 0; i < this.objects.length; i++) {
      this.A312(i);                                     // the two objects
    }
    for (var p = 0; p < this.amulet.length; p++) {
      this.A1AB(p);                                     // the four pieces
    }
    return out;
  }; // step

  /**
   * $AB01 — contact between Sabreman and an entity.
   *
   * The box is the caller's (BC), the reach is Sabreman's ($0F0C, or $0F1C
   * with the sword drawn), and which of the two applies depends on **which
   * side** he is on. This is the very test that kills him when the entity is
   * an animal, which is why the sword only works in the direction he faces.
   * @param {Uint8Array} record - The entity's record.
   * @param {number} height - B of the caller's LD BC.
   * @param {number} width - C of the same.
   * @returns {boolean} True on contact.
   */
  WorldEntities.prototype.AB01 = function (record, height, width) {
    var v = this.v;
    if (this.delay !== 0) {                             // $AB01: no contact
      return false;                                     // during the changeover
    }
    var sprite = (this.sabreman[SPRITE]-v.hitFirstSprite) & 0xFF;
    if (sprite >= v.hitSpriteCount) {                   // only $10-$2F
      return false;
    }
    var reachDown = v.hitReachDown, reachRight = v.hitReachRight;
    if (sprite >= v.hitSwordFrom) {                     // $AB11: with the sword
      reachRight = v.hitReachRightSword;
    }
    var dx = (this.sabreman[X]-record[X]) & 0xFF;
    if (this.sabreman[X]-record[X] < 0) {               // $AB1E: JR C
      if (((256-dx) & 0xFF) >= reachRight) { return false; }
    } else if (dx >= width) {
      return false;
    }
    var dy = (this.sabreman[Y]-record[Y]) & 0xFF;
    if (this.sabreman[Y]-record[Y] < 0) {               // $AB28: JR C
      return ((256-dy) & 0xFF) < height;
    }
    return dy < reachDown;
  }; // AB01

  // -------------------------------------------------------------------------
  // the orchid ($A680, $A6D4, $A70D, $A737)
  // -------------------------------------------------------------------------

  /** $A680 — the orchid's handler: run the timer down, or bloom. */
  WorldEntities.prototype.A680 = function () {
    var v = this.v;
    var record = this.orchid;
    var timer = record[DX] | record[DY] << 8;
    if (timer === 0) {
      this.A6D4();
      return;
    }
    // $A68D: the timer only runs while Sabreman is his own man ($10-$2F) and
    // the changeover delay is over
    var sprite = (this.sabreman[SPRITE]-v.hitFirstSprite) & 0xFF;
    if (sprite < v.hitSpriteCount && this.delay === 0) {
      timer = (timer-1) & 0xFFFF;
    }
    record[DX] = timer & 0xFF;
    record[DY] = timer >> 8;
    this.A737();
  }; // A680

  /** $A6D4 / $A70D — one step of the bloom, every other sweep. */
  WorldEntities.prototype.A6D4 = function () {
    var v = this.v;
    var record = this.orchid;
    if (this.sweeps & v.orchidPhaseEvery) {             // $A6D7
      return;
    }
    if (record[STATE] !== 0) {                          // closing: $4F -> $48
      record[SPRITE] = (record[SPRITE]-1) & 0xFF;
      if (record[SPRITE] & v.orchidPhaseMask) {
        return;
      }
      // ★ back to $48, and this is where the **next colour** is drawn:
      // OrchidColour has twelve of the four working colours and four whites,
      // so one bloom in four does nothing at all
      record[ATTR] = this.orchidColours[this.frames & v.orchidColourIndexMask];
    } else {                                            // opening: $48 -> $4F
      record[SPRITE] = (record[SPRITE]+1) & 0xFF;
      if ((~record[SPRITE]) & v.orchidPhaseMask) {
        return;
      }
    }
    this.A71A();
  }; // A6D4

  /** $A71A — turn round: open for orchidOpenWait, or sleep for a while. */
  WorldEntities.prototype.A71A = function () {
    var v = this.v;
    var record = this.orchid;
    record[STATE] ^= v.orchidStateToggle;
    var timer;
    if (record[STATE] !== 0) {
      timer = v.orchidOpenWait;                         // $A731: fully open
    } else {
      timer = ((this.frames & v.orchidDormantMask)+v.orchidDormantBase) & 0xFF;
    }
    record[DX] = timer & 0xFF;
    record[DY] = timer >> 8;
    this.A737();
  }; // A71A

  /**
   * $A737 — the orchid can only be taken while it is **fully open** ($4F).
   *
   * ★ And what it does is one line: it writes its own colour into Sabreman's
   * record. Everything else — slower, faster, reversed controls, sitting down,
   * being untouchable, not being able to draw the sword — hangs off that one
   * byte, which is why the effects live in sabremanPhysics.js and not here.
   * White is the exception the code makes explicit: $A75C sets the timer back
   * to zero, so a white orchid does nothing.
   */
  WorldEntities.prototype.A737 = function () {
    var v = this.v;
    var record = this.orchid;
    if ((~record[SPRITE]) & v.orchidPhaseMask) {        // $A737: only $4F
      return;
    }
    if (!this.AB01(record, v.orchidPickHeight, v.orchidPickWidth)) {
      return;
    }
    this.effect.timer = v.orchidEffectTime;             // $96B0 = $C0
    record[DX] = 0;
    record[DY] = 0;
    this.sabreman[ATTR] = record[ATTR];                 // $A754: $9707
    if (record[ATTR] === v.orchidHarmless) {
      this.effect.timer = 0;
    }
    this.out.effect = {colour: record[ATTR], timer: this.effect.timer};
    this.out.sounds.push({name: 'orchid'});
  }; // A737

  // -------------------------------------------------------------------------
  // objects ($A312, $A305, $A323, $A2F8)
  // -------------------------------------------------------------------------

  /**
   * $A312 (and $A305 for the one kind that is a life) — pick an object up.
   * @param {number} slot - 0 or 1.
   */
  WorldEntities.prototype.A312 = function (slot) {
    var v = this.v;
    var record = this.objects[slot];
    if (!record[SPRITE]) {
      return;
    }
    var type = record[SPRITE] & v.objectTypeMask;
    var life = (type === this.objectLife);
    var height = life ? v.lifePickHeight : v.objectPickHeight;
    var width = life ? v.lifePickWidth : v.objectPickWidth;
    if (!this.AB01(record, height, width)) {
      return;
    }
    if (life) {
      this.A2F8();                                      // $A30D
    }
    // $A323: the map byte goes to zero through the pointer in +$06/+$07, so
    // the object is gone from the whole game, not just from the screen
    this.objectMap[(record[DX] | record[DY] << 8)-v.objectMap] = 0;
    record[SPRITE] = 0;
    this.out.points += v.objectScoreDecimal;            // $A332: BCD $0150
    this.out.picked.push({kind: 'object', type: type, slot: slot});
    this.out.sounds.push({name: 'object'});
  }; // A312

  /** $A2F8 — a life, and ★ never more than lifeMax of them. */
  WorldEntities.prototype.A2F8 = function () {
    if (this.lives >= this.v.lifeMax) {                 // $A2FB: CP $09 / RET NC
      return;
    }
    this.lives++;
    this.out.extraLife = true;
    this.out.sounds.push({name: 'life'});
  }; // A2F8

  // -------------------------------------------------------------------------
  // the amulet ($A1AB) and the natives who point at it ($9D41)
  // -------------------------------------------------------------------------

  /**
   * $A1AB — a piece of the amulet: it flashes through four colours and is
   * worth 7500, and taking it sets both its own bit and bit 7, which is what
   * makes the game show a verse of the poem ($A18C -> $A207, M6).
   * @param {number} index - 0 to 3.
   */
  WorldEntities.prototype.A1AB = function (index) {
    var v = this.v;
    var record = this.amulet[index];
    if (!record[SPRITE]) {
      return;
    }
    if (this.sabreman[ROOM] !== record[ROOM]) {         // $A1AB: another screen
      return;
    }
    if (!(this.sweeps & v.amuletFlashEvery)) {          // $A1B8
      record[ATTR] = ((record[ATTR]+1) & v.amuletFlashMask) | v.amuletFlashBase;
    }
    if (!this.AB01(record, v.amuletPickHeight, v.amuletPickWidth)) {
      return;
    }
    var which = (record[SPRITE]-v.amuletFirstSprite) & 0xFF;
    var bit = (which < 3) ? which : 3;                  // $A1D3: $90, $91, $92,
    this.sabreman[AMULET] |= (1 << bit) | v.amuletPoemBit;  // else -> bit 3
    record[SPRITE] = 0;
    this.out.points += v.amuletScoreDecimal;            // $A1ED: BCD $7500
    this.out.poem = this.sabreman[AMULET];
    this.out.picked.push({kind: 'amulet', piece: index, bit: bit});
    // ★ a **žádný zvuk**: $A1AB jen přičte body a nastaví bit básně. Co je
    // u kusu amuletu slyšet, je hudba básně, která přijde hned po něm
    // (data/sounds.json, oddíl `silent`).
  }; // A1AB

  /**
   * $9D41 — is this entity **in line** with a buried piece of the amulet?
   *
   * ★ This is the rule behind the natives: in the same column of the world as
   * a piece and within pointRange pixels of its x, or in the same row and
   * within range of its y. $ABB6 then draws the native **yellow** and beeps a
   * tone whose pitch is that distance — so the closer the native is to a
   * piece, the higher the note.
   * @param {Uint8Array} record - The entity's record (a native, in the game).
   * @returns {Object|null} {piece, axis, distance}, or null.
   */
  WorldEntities.prototype.A9D41 = function (record) {
    var v = this.v;
    for (var i = 0; i < this.amulet.length; i++) {
      var piece = this.amulet[i];
      if (!piece[SPRITE]) {
        continue;                                       // $9D4B: taken already
      }
      if ((piece[ROOM] & v.pointColumnMask) === (record[ROOM] & v.pointColumnMask)) {
        var dx = Math.abs(piece[X]-record[X]);
        if (dx < v.pointRange) {
          return {piece: i, axis: 'column', distance: dx};
        }
      }
      if ((piece[ROOM] & v.pointRowMask) === (record[ROOM] & v.pointRowMask)) {
        var dy = Math.abs(piece[Y]-record[Y]);
        if (dy < v.pointRangeRow) {
          return {piece: i, axis: 'row', distance: dy};
        }
      }
    }
    return null;
  }; // A9D41

  // -------------------------------------------------------------------------
  // rooms visited ($9D23) and the percentage ($9CC6)
  // -------------------------------------------------------------------------

  /**
   * $9D23 VisitRoom — one bit per screen: the byte is row*2 + column>>3 and
   * the bit is column & 7 (the routine gets there by **rewriting its own
   * SET instruction**, which is the same trick Atic Atac uses).
   * @param {number} room - The screen number, row<<4 | column.
   */
  WorldEntities.prototype.visitRoom = function (room) {
    var v = this.v;
    var index = rotateRight(room & 0xFF, 3) & v.visitedByteMask;
    var bit = (rotateLeft(room & 0xFF, 3) & v.visitedBitMask) >> 3;
    this.visited[index] |= 1 << bit;
  }; // visitRoom

  /** @returns {number} How many screens have been visited. */
  WorldEntities.prototype.visitedCount = function () {
    var count = 0;
    for (var i = 0; i < this.visited.length; i++) {
      for (var bit = 0; bit < 8; bit++) {
        if (this.visited[i] >> bit & 1) { count++; }
      }
    }
    return count;
  }; // visitedCount

  /**
   * $9CC6 PrintRoomsVisited — "ADVENTURE COMPLETED nn%".
   *
   * ★ The pieces of the amulet count towards it, so the whole is 260, not
   * 256. The original does not divide: it adds a fixed 100/260 into a 16 bit
   * register once per screen and counts the carries in BCD. The table that
   * comes out of that loop is in data/entities.json, so the remake looks the
   * answer up instead of repeating the loop.
   * @returns {number} The percentage, exactly as the original prints it.
   */
  WorldEntities.prototype.percentComplete = function () {
    var count = this.visitedCount();
    var bits = this.amuletBits();
    for (var bit = 0; bit < this.v.percentAmuletBits; bit++) {
      if (bits >> bit & 1) { count++; }
    }
    return this.percent[Math.min(count, this.percent.length-1)];
  }; // percentComplete

  /** The M4 entities of the current screen, for the worker's frame message. */
  WorldEntities.prototype.visible = function (room) {
    var list = [];
    function add(record) {
      if (record[SPRITE] && record[ROOM] === room) {
        list.push({sprite: record[SPRITE], room: record[ROOM],
                   x: record[X], y: record[Y], colour: record[ATTR]});
      }
    }
    add(this.orchid);
    this.objects.forEach(add);
    this.amulet.forEach(add);
    return list;
  }; // visible

  WorldEntities.RECORD = {SPRITE: SPRITE, ROOM: ROOM, STATE: STATE, X: X,
                          Y: Y, ATTR: ATTR, DX: DX, DY: DY, AMULET: AMULET,
                          LENGTH: RECORD_LENGTH};
  WorldEntities.signed = signed;
  WorldEntities.addBCD = addBCD;
  return WorldEntities;
})();

if (typeof self !== 'undefined') { self.WorldEntities = WorldEntities; }
if (typeof module !== 'undefined' && module.exports) { module.exports = WorldEntities; }
