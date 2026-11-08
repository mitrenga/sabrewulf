// begin code

/**
 * The enemies of Sabre Wulf: the animals, the natives, Sabre Wulf himself,
 * the keeper of the gate and the fireball.
 *
 * This is to M5 what worldEntities.js is to M4 — a transcription of the
 * original's own routines, driven by data/monsters.json, whose every number
 * tools/dumpmonsters.py reads as the operand of an actual instruction (166
 * instructions and table ends checked). Nothing here is invented and nothing
 * is tuned: where the original does something odd, so does this.
 *
 * ★ **Which entity is which is not a guess.** The game dispatches every entity
 * through `JumpTable` ($9B3E): the handler is `JumpTable[sprite ID]`, 196
 * entries ending exactly on PrintRoomsVisited. Read it and the open question
 * of ZADANI §7 answers itself:
 *
 * - **destructible** ($A54F walkers and $A4D7 chasers, sprites $60-$7F,
 *   $98-$9F and $B0-$C3): the sixteen animals the game puts into the world as
 *   it goes. They explode, and they are worth 165 or 185 points ($A4B3).
 * - **immortal** (rhino $AD07, native $AB74, hippo $9E72, Sabre Wulf $A858,
 *   the keeper $9F16, the fireball $9D91): these are only **driven off**. The
 *   rhino and the native turn and bolt, the hippo is stunned for $0F sweeps,
 *   Sabre Wulf backs away — and comes back **faster than before** ($A964).
 *
 * The other findings of M5, in the order the sweep reaches them:
 *
 * - $9A3C keeps **six animals in the world and three on a screen**, and $A3E0
 *   picks the kind out of SpriteReference — ★ but only from the first
 *   `pieces*2 + 8` of the sixteen, so **the more of the amulet the player
 *   carries, the worse the animals get**.
 * - $9ABC is the **fireball**, and with it the answer to what $96B4 is: not
 *   the invulnerability M3 guessed, but the countdown to the fireball. $B148
 *   sets it to $80 on every screen change, so it is the reward for standing
 *   still. ★ Its homing has a bug of its own, reproduced here: $9E4E writes
 *   the **horizontal** speed where it means the vertical one, so the fireball
 *   never comes up at Sabreman from below.
 * - $A922 is why Sabre Wulf feels like he hunts: he stands still until
 *   Sabreman is in the **same row of the world**, then charges straight along
 *   it.
 * - $9F16 is the keeper: with all four pieces of the amulet he steps aside to
 *   $40 or $C0 and lets you through; without them he kills — ★ and he kills
 *   through an orchid too ($AB3D skips the colour test $AB36 makes).
 * - $A630 moves the immortal entities around the world so they stay near
 *   Sabreman's row. That is why the same rhino keeps turning up.
 *
 * The cadence is M4's: **one sweep of the entity pass per tick**, and the
 * comparison in tools/matchmonsters.js is sweep against sweep.
 */

var WorldMonsters = (function () {
  'use strict';

  // the game's own record ($9702, 12 bytes) — the same offsets as M3 and M4
  var SPRITE = 0, ROOM = 1, STATE = 2, X = 3, Y = 4, ATTR = 5, DX = 6, DY = 7,
      AGE = 8, AMULET = 11;
  var RECORD_LENGTH = 12;

  /**
   * @param {Object} monsters - The parsed data/monsters.json (tools/dumpmonsters.py).
   * @param {Object} entities - The parsed data/entities.json — the contact box
   *                            and the eleven immortal records live there (M4).
   * @param {Object} physics - A SabremanPhysics, for the scenery: $AFE8 and
   *                           $B81C are the same routines Sabreman walks with.
   * @param {Object} world - A WorldEntities, for $9D41 (the natives pointing
   *                         at a buried piece of the amulet).
   */
  function WorldMonsters(monsters, entities, physics, world) {
    if (!monsters || !monsters.values) {
      throw new Error('data/monsters.json missing – run tools/dumpmonsters.py');
    }
    this.data = monsters;
    this.v = monsters.values;
    this.e = entities.values;
    this.physics = physics;
    this.world = world;

    // JumpTable ($9B3E): sprite ID -> role. This is the whole classification.
    this.role = [];
    for (var i = 0; i < monsters.jumpTable.handlers.length; i++) {
      this.role[i] = monsters.jumpTable.handlers[i].role;
    }
    this.kinds = monsters.kinds.list.map(function (kind) { return kind.sprite; });
    this.spawnColours = monsters.speeds.spawnColours;
    this.nastieSpeeds = monsters.speeds.nastieRaw;
    this.fireballSpeeds = monsters.speeds.fireballRaw;
    this.nativeSpeeds = monsters.speeds.nativeRaw;
    this.immortalData = entities.immortal;

    this.reset();
  } // WorldMonsters

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

  /** $B031: a signed speed in 1/16 px as whole pixels, rounded towards zero */
  function B031(speed) {
    if (speed & 0x80) {
      return -((((256-speed) & 0xFF) >> 4) & 0x0F);
    }
    return (speed >> 4) & 0x0F;
  } // B031

  /** $AFD0 — clamp a signed speed to +/- cap, keeping its sign */
  function AFD0(value, cap) {
    var a = value & 0xFF;
    if (a & 0x80) {
      var magnitude = (256-a) & 0xFF;
      if (magnitude >= cap) { magnitude = cap; }
      return (-magnitude) & 0xFF;
    }
    return a < cap ? a : cap;
  } // AFD0

  /** the three bytes of a BCD score as the number the panel prints */
  function bcd(high, low) {
    return parseInt(('0'+high.toString(16)).slice(-2)
                    + ('0'+low.toString(16)).slice(-2), 10);
  } // bcd

  /**
   * Back to where a turn starts: the eleven immortal entities as $AC6B copies
   * them out of $AC77, and six empty animal slots.
   */
  WorldMonsters.prototype.reset = function () {
    var self = this;
    this.immortal = [];
    this.immortalData.forEach(function (entry) {
      if (entry.slot === 0) { return; }              // slot 0 is Sabreman (M3)
      var record = new Uint8Array(RECORD_LENGTH);
      for (var i = 0; i < RECORD_LENGTH; i++) {
        record[i] = parseInt(entry.bytes.substr(i*2, 2), 16);
      }
      self.immortal.push(record);
    });
    this.nastie = [];
    for (var slot = 0; slot < this.v.nastieSlots; slot++) {
      this.nastie.push(new Uint8Array(RECORD_LENGTH));
    }
    this.spawnTimer = this.v.spawnDelay;             // $96B1
    this.fireballTimer = this.v.fireballDelay;       // $96B4
    this.width = 0x10;                               // $96AD, whatever ran last
  }; // reset

  /** The record of the fireball — the one immortal slot that starts empty. */
  WorldMonsters.prototype.fireball = function () {
    return this.immortal[this.fireballIndex()];
  }; // fireball

  WorldMonsters.prototype.fireballIndex = function () {
    var slot = (this.v.fireballSlot-0x9702)/RECORD_LENGTH;
    return slot-1;                                   // the list has no slot 0
  }; // fireballIndex

  /**
   * ★ $B148 — every screen change puts the fireball countdown back to $80.
   *
   * This is the one M3 called "the delay you cannot die in after a respawn".
   * It is not: $9ABC is the only routine that reads $96B4, and what it does
   * on zero is put a fireball on the screen. So the rule is simply **keep
   * walking or you get one**.
   */
  WorldMonsters.prototype.roomChanged = function () {
    this.fireballTimer = this.v.fireballDelay;
  }; // roomChanged

  /**
   * One sweep of the entity pass, slots 1-17: the eleven immortal entities
   * and the six animals, then the two things $9A1D does at the end of a
   * sweep — $9A3C puts an animal into the world and $9ABC a fireball.
   * @param {Uint8Array} sabreman - Sabreman's record ($9702).
   * @param {Object} context - {frames, sweeps, delay, rand, refresh, nextRand}.
   * @returns {Object} What happened: points, sounds, killed.
   */
  WorldMonsters.prototype.step = function (sabreman, context) {
    var out = this.begin(sabreman, context);
    var i;
    for (i = 0; i < this.immortal.length; i++) {
      this.stir();
      this.handle(this.immortal[i]);
    }
    for (i = 0; i < this.nastie.length; i++) {
      this.stir();
      this.handle(this.nastie[i]);
    }
    // $9A1D runs with Rand8 as the last entity left it: no stir here
    this.A9A3C();                                    // $9A3C: a new animal
    this.A9ABC();                                    // $9ABC: the fireball
    return out;
  }; // step

  /**
   * ★ $99D0 — `LD A,R / ADC A,(Rand8)`: the original stirs Rand8 with the Z80
   * refresh register **before every entity**, so each of them draws from a
   * different byte. Without that, every animal stopping in the same sweep
   * sets off at the same speed in the same direction, and two rhinos moved
   * by $A630 in the same sweep always land on the same screen and the same
   * spot (measured 2026-09-07). The browser has no refresh register, so the
   * worker hands over its own source (`context.nextRand`); tools/matchmonsters.js
   * hands over the recorded byte in `context.rand` instead and does not set
   * `nextRand`, so a handler under test sees exactly what the trace saw.
   */
  WorldMonsters.prototype.stir = function () {
    if (this.nextRand) {
      this.rand = this.nextRand() & 0xFF;
      this.refresh = this.rand;
    }
  }; // stir

  /**
   * The clock of one sweep, on its own — the handlers read it out of these.
   * step() calls it; tools/matchmonsters.js calls it to drive one handler at
   * a time, the way the trace calls one routine at a time.
   * @param {Uint8Array} sabreman - Sabreman's record ($9702).
   * @param {Object} context - {frames, sweeps, delay, rand, refresh}.
   * @returns {Object} The out this sweep will fill in.
   */
  WorldMonsters.prototype.begin = function (sabreman, context) {
    this.out = {points: 0, sounds: [], killed: 0, spawned: 0, pointing: null};
    this.sabreman = sabreman;
    this.frames = context.frames|0;                  // $5C78 FRAMES
    this.sweeps = context.sweeps|0;                  // $9693
    this.delay = context.delay|0;                    // $96B5 GameDelayTimer
    this.rand = context.rand|0;                      // $9695 Rand8
    this.nextRand = context.nextRand || null;        // $99D0, see stir()
    // ★ the one byte of M5 that cannot be reproduced: $9E0E takes the
    // fireball's vertical speed from the Z80 refresh register. The trace
    // hands it over; in the browser Rand8 stands in, exactly as M3 does for
    // the phase of the sword.
    this.refresh = (context.refresh === undefined) ? this.rand : context.refresh|0;
    return this.out;
  }; // begin

  /**
   * $B1B7 — the start of a player's turn.
   *
   * ★ And with it the **bug two player games have been reviewed for since
   * 1984**. When a player dies, $AA27 hands over to $B205, which swaps the
   * two players' state ($B235) and **then** comes here — so the life is taken
   * off the player who is arriving, not the one who died. In a one player
   * game $AA27 takes the other road and decrements it itself, so nothing
   * shows. Measured in tools/tracemonsters.py (`twoPlayer`), and reproduced.
   * @param {number} lives - The arriving player's lives.
   * @returns {Object} {lives, delay} — and the two timers are reset here.
   */
  WorldMonsters.prototype.startTurn = function (lives) {
    this.spawnTimer = this.v.spawnDelay;             // $96B1
    this.fireballTimer = this.v.fireballDelay;       // $96B4
    return {lives: (lives-1) & 0xFF, delay: this.v.gameDelay};
  }; // startTurn

  /** $99E1 — the dispatch: the handler of an entity is JumpTable[sprite ID]. */
  WorldMonsters.prototype.handle = function (record) {
    switch (this.role[record[SPRITE]]) {
      case 'materialise':     this.A3C5(record); break;
      case 'materialiseDone': this.A3E0(record); break;
      case 'explosion':       this.A42A(record); break;
      case 'explosionEnd':    this.A43B(record); break;
      case 'nastie':          this.A54F(record); break;
      case 'chaser':          this.A4D7(record); break;
      case 'rhino':           this.AD07(record); break;
      case 'hippo':           this.A9E72(record); break;
      case 'hippoRoam':       this.A9EB3(record); break;
      case 'native':          this.AB74(record); break;
      case 'wulf':            this.A858(record); break;
      case 'wulfWard':        this.A8F5(record); break;
      case 'wulfReturn':      this.A964(record); break;
      case 'keeper':          this.A9F16(record); break;
      case 'fireball':        this.A9D91(record); break;
      default: break;                  // Sabreman, the orchid, the objects,
    }                                  // the amulet and the unused IDs
  }; // handle

  // -------------------------------------------------------------------------
  // contact: who kills whom ($AB01, $AB36, $AB3D)
  // -------------------------------------------------------------------------

  /**
   * $AB0E — the box test itself, without any of the guards around it.
   *
   * The reach is Sabreman's ($0F0C, or $0F1C with the sword) and which of the
   * two applies depends on which side of the entity he is.
   * @param {Uint8Array} record - The entity's record.
   * @param {number} height - B of the caller's LD BC.
   * @param {number} width - C of the same.
   * @param {number} a - What the caller left in A: below $10 means no sword.
   * @returns {boolean} True on contact.
   */
  WorldMonsters.prototype.AB0E = function (record, height, width, a) {
    var e = this.e;
    var reachDown = e.hitReachDown, reachRight = e.hitReachRight;
    if (a >= e.hitSwordFrom) {                       // $AB11: CP $10
      reachRight = e.hitReachRightSword;
    }
    var dx = this.sabreman[X]-record[X];
    if (dx < 0) {
      if (((-dx) & 0xFF) >= reachRight) { return false; }
    } else if (dx >= width) {
      return false;
    }
    var dy = this.sabreman[Y]-record[Y];
    if (dy < 0) {
      return ((-dy) & 0xFF) < height;
    }
    return dy < reachDown;
  }; // AB0E

  /** $AB01 — the same test, but only while the game is running and he lives. */
  WorldMonsters.prototype.AB01 = function (record, height, width) {
    var e = this.e;
    if (this.delay !== 0) { return false; }          // $AB05: RET NZ
    var a = (this.sabreman[SPRITE]-e.hitFirstSprite) & 0xFF;
    if (a >= e.hitSpriteCount) { return false; }     // only $10-$2F
    return this.AB0E(record, height, width, a);
  }; // AB01

  /**
   * $AB36 / $AB3D — contact, and what it costs.
   *
   * ★ Two things come out of this one routine. First, an orchid makes
   * Sabreman untouchable ($AB36 refuses anything but the white attribute) —
   * but the keeper of the gate calls $AB3D **below** that test, so the orchid
   * does not save you from him. Second, whether the sword works is decided by
   * **which side Sabreman is on**: bit 3 of his sprite says which way he is
   * swinging, and the entity only dies when he is on that side. Either way
   * the routine reports contact, so an animal walked into without the sword
   * kills Sabreman **and** blows up.
   * @param {Uint8Array} record - The entity's record.
   * @param {number} height - B of the caller's LD BC.
   * @param {number} width - C of the same.
   * @param {number} d - What the caller left in D: bit 0 picks which way
   *                     Sabreman is thrown ($AB5E).
   * @param {boolean} skipColour - True for the keeper, which enters at $AB3D.
   * @returns {boolean} True on contact — the caller's carry flag.
   */
  WorldMonsters.prototype.AB36 = function (record, height, width, d, skipColour) {
    var e = this.e, v = this.v;
    if (!skipColour && this.sabreman[ATTR] !== e.colourImmune) {
      return false;                                  // $AB3B: RET NZ
    }
    if (this.sabreman[ROOM] !== record[ROOM]) { return false; }
    if (!this.AB01(record, height, width)) { return false; }
    var a = (this.sabreman[SPRITE]-v.killSwordFrom) & 0xFF;
    var dies = true;                                 // does Sabreman die?
    if (a >= v.killSwordCount) {                     // $AB4E: he has the sword
      var side = this.sabreman[X]-record[X];
      if (a & (1 << v.killSwordSide)) {              // $AB52: BIT 3,A
        dies = !(side < 0);                          // $AB6A: JR C
      } else {
        dies = side < 0;                             // $AB56: JR NC
      }
    }
    if (dies) {
      this.out.killed = (d & 1) ? 1 : 2;             // $AB5E
    }
    return true;                                     // $AB68: SCF
  }; // AB36

  /** $AAED — did the entity actually move? (Z means it did not.) */
  function AAED(record, x, y) {
    return record[X] === x && record[Y] === y;
  } // AAED

  // -------------------------------------------------------------------------
  // moving about ($A44B, $AFE8, $B81C)
  // -------------------------------------------------------------------------

  /**
   * $A44B — the move of an animal, which **bounces off the edges** instead of
   * leaving the screen. ★ And when it bounces sideways it returns straight
   * away, so that sweep has no vertical move at all.
   * @param {Uint8Array} record - The entity's record.
   * @returns {Object} {x, y, bounceX, bounceY}.
   */
  WorldMonsters.prototype.A44B = function (record) {
    var v = this.v;
    var width = this.width;
    var step = B031(record[DX]);
    var e;
    if (step >= 0) {
      e = (record[X]+step) & 0xFF;
      if (e+width > 0xFF) {                          // $A45E: ADD A,C / JR C
        return {x: (-width) & 0xFF, y: record[Y], bounceX: true, bounceY: false};
      }
    } else {
      var sum = (step & 0xFF)+record[X];
      e = sum & 0xFF;
      if (sum < 0x100) {                             // $A481: JR C means no borrow
        return {x: 0, y: record[Y], bounceX: true, bounceY: false};
      }
    }
    step = B031(record[DY]);
    var d;
    if (step >= 0) {
      d = (record[Y]+step) & 0xFF;
      if (d >= v.bounceMaxY) {                       // $A46E: CP $BF / RET C
        return {x: e, y: v.bounceMaxY, bounceX: false, bounceY: true};
      }
    } else {
      d = ((step & 0xFF)+record[Y]) & 0xFF;
      if (d < v.bounceMinY) {                        // $A48C: CP $27 / RET NC
        return {x: e, y: v.bounceMinY, bounceX: false, bounceY: true};
      }
    }
    return {x: e, y: d, bounceX: false, bounceY: false};
  }; // A44B

  /** $AFE8 — the move of an entity that **may leave the screen** (M3's own). */
  WorldMonsters.prototype.AFE8 = function (record) {
    this.physics.exitWidth = this.width;             // $96AD
    return this.physics.AFE8(record);
  }; // AFE8

  /** $B81C — the slide along the scenery (M3's own, box from the caller). */
  WorldMonsters.prototype.B81C = function (record, x, y, height, width) {
    return this.physics.B81C(record[ROOM], record[X], record[Y], x, y,
                             height, width);
  }; // B81C

  /**
   * The carry $B81C comes back with, which is all $9B0D and $9AE9 want of it:
   * the place the record already holds is inside the scenery.
   * @param {Uint8Array} record - The entity's record.
   * @param {number} height - B of the caller's LD BC.
   * @param {number} width - C of the same.
   * @returns {boolean} True when it is blocked.
   */
  WorldMonsters.prototype.blocked = function (record, height, width) {
    return this.physics.collides(record[ROOM], record[X], record[Y],
                                 height, width) !== null;
  }; // blocked

  /** $A5A9 — turn round horizontally: negate the speed and flip the pose. */
  function A5A9(record) {
    record[DX] = (-record[DX]) & 0xFF;
    record[SPRITE] ^= 0x02;
  } // A5A9

  /** $A5BA — and vertically, which does not touch the pose. */
  function A5BA(record) {
    record[DY] = (-record[DY]) & 0xFF;
  } // A5BA

  /** $ADA2 — the immortals turn round the other way: bit 1 of the pose. */
  function ADA2(record) {
    record[SPRITE] ^= 0x02;
    record[DX] = (-record[DX]) & 0xFF;
  } // ADA2

  /** $ADB3 — and Sabre Wulf uses bit 2 for it. */
  function ADB3(record) {
    record[SPRITE] ^= 0x04;
    record[DX] = (-record[DX]) & 0xFF;
  } // ADB3

  /** $AD93 — two frames of a walk, one step of it every other sweep. */
  WorldMonsters.prototype.AD93 = function (record) {
    if ((this.sweeps & this.v.animateEvery) === 0) {
      record[SPRITE] ^= 0x01;
    }
  }; // AD93

  /** $AC0E — four frames of a walk, in bits 0-1 of the sprite ID. */
  WorldMonsters.prototype.AC0E = function (record) {
    if ((this.sweeps & 1) !== 0) { return; }
    record[SPRITE] = (record[SPRITE] & 0xFC) | ((record[SPRITE]+1) & 0x03);
  }; // AC0E

  /** $A493 — an animal left behind on another screen ages out and vanishes. */
  WorldMonsters.prototype.A493 = function (record) {
    record[AGE] = (record[AGE]+1) & 0xFF;
    if (record[AGE] >= this.v.despawnAge) {
      record[SPRITE] = 0;
    }
  }; // A493

  /**
   * $A4A6 / $A4B3 — the explosion, and ★ **what an enemy is worth**.
   *
   * Not one number: `RLCA` three times takes bits 1-2 of the sprite ID into
   * bits 4-5, and $65 is added, so the score is 165, 175, 185 or 195. Of the
   * sixteen kinds the game actually uses, only 165 and 185 ever come up.
   * @param {Uint8Array} record - The entity's record.
   */
  WorldMonsters.prototype.A4A6 = function (record) {
    var v = this.v;
    // ★ Délky šestnácti tónů výbuchu čte originál z **ROM Spectra** na
    // ($9693 & $1F)*256 + Rand8 ($BEEE). ROM v našich zdrojích není, takže se
    // – jako u mapy předmětů v M4 – reprodukuje pravidlo a zdroj těch bajtů je
    // náš; ta adresa jde ven a beeper.js si z ní bajty vyrobí sám.
    this.out.sounds.push({name: 'explosion',
                          sweeps: this.sweeps, rand: this.rand});
    var low = (rotateLeft(record[SPRITE], 3) & v.enemyScoreMask) + v.enemyScoreBase;
    this.out.points += bcd(v.enemyScoreHigh, low);
    record[SPRITE] = v.explodeSprite;
  }; // A4A6

  // -------------------------------------------------------------------------
  // becoming, and stopping being ($A3C5, $A3E0, $A42A, $A43B)
  // -------------------------------------------------------------------------

  /** $A3C5 — an animal materialising: one frame of it per sweep. */
  WorldMonsters.prototype.A3C5 = function (record) {
    if (this.sabreman[ROOM] !== record[ROOM]) { return this.A493(record); }
    // $A3B7: while it is still a shimmer only a **drawn sword** touches it
    var v = this.v;
    var a = (this.sabreman[SPRITE]-v.shimmerSwordFrom) & 0xFF;
    if (a < v.shimmerSwordCount
        && this.AB01(record, v.shimmerHitHeight, v.shimmerHitWidth)) {
      return this.A4A6(record);
    }
    record[SPRITE] = (record[SPRITE]+1) & 0xFF;
    this.out.sounds.push({name: 'materialise', sprite: record[SPRITE]});
  }; // A3C5

  /**
   * $A3E0 — the last frame of the shimmer picks the animal.
   *
   * ★ And this is where the game gets harder: it counts the pieces of the
   * amulet in $970D and only lets the draw reach `pieces*2 + 8` of the sixteen
   * kinds in SpriteReference. With nothing collected the first eight can turn
   * up; with the whole amulet, all sixteen.
   * @param {Uint8Array} record - The entity's record.
   */
  WorldMonsters.prototype.A3E0 = function (record) {
    var v = this.v;
    if (this.sabreman[ROOM] !== record[ROOM]) { return this.A493(record); }
    var pieces = 0, bits = this.sabreman[AMULET];
    for (var i = 0; i < v.difficultyPieces; i++) {
      if (bits & (1 << i)) { pieces++; }
    }
    var allowed = (pieces*2+v.difficultyBase) & 0xFF;
    var index = this.sweeps & v.difficultyMask;
    if (index >= allowed) { index &= v.difficultyFallback; }
    record[SPRITE] = this.kinds[index];
    this.A5CD(record);                               // and a direction to go in
  }; // A3E0

  /** $A42A — the explosion, one frame per sweep. */
  WorldMonsters.prototype.A42A = function (record) {
    if (this.sabreman[ROOM] !== record[ROOM]) {
      record[SPRITE] = this.v.explodeClear;          // $A446
      return;
    }
    record[SPRITE] = (record[SPRITE]+1) & 0xFF;
  }; // A42A

  /** $A43B — and its last frame frees the slot. */
  WorldMonsters.prototype.A43B = function (record) {
    record[SPRITE] = this.v.explodeClear;
  }; // A43B

  // -------------------------------------------------------------------------
  // the animals the game puts into the world ($A54F, $A4D7, $A5CD)
  // -------------------------------------------------------------------------

  /**
   * $A5CD — where an animal goes next.
   *
   * Standing still it picks a speed for each axis out of eight; moving, it
   * stops instead, for `rand & 7 | 8` sweeps ($A609). So the animals go in
   * fits and starts, which is exactly how they look.
   * @param {Uint8Array} record - The entity's record.
   */
  WorldMonsters.prototype.A5CD = function (record) {
    var v = this.v;
    if (record[DX] !== 0 || record[DY] !== 0) {      // $A609
      record[DX] = 0;
      record[DY] = 0;
      record[STATE] = (this.rand & v.nastieTimerMask) | v.nastieTimerBase;
      return;
    }
    var dx = this.nastieSpeeds[this.rand & v.nastieSpeedMask];
    record[DX] = dx;
    if (dx & 0x80) {
      record[SPRITE] &= ~0x02;                       // $A5E9
    } else {
      record[SPRITE] |= 0x02;                        // $A5FB
    }
    record[DY] = this.nastieSpeeds[this.frames & v.nastieSpeedMask];
  }; // A5CD

  /** $A54F — an animal that walks about the screen. It can be killed. */
  WorldMonsters.prototype.A54F = function (record) {
    var v = this.v, e = this.e;
    if (this.sabreman[ROOM] !== record[ROOM]) { return this.A493(record); }
    this.width = v.nastieWidth;                      // $96AD
    var alive = (this.sabreman[SPRITE]-v.aliveFirstSprite) & 0xFF;
    if (alive >= v.aliveSpriteCount) {               // $A567: Sabreman is down
      return this.A4A6(record);                      // and the animals go with him
    }
    record[STATE] = (record[STATE]-1) & 0xFF;
    if (record[STATE] === 0) { this.A5CD(record); }
    var d = record[Y];
    if (record[DX] !== 0 || record[DY] !== 0) {
      var move = this.A44B(record);
      if (move.bounceX) { A5A9(record); }
      else if (move.bounceY) { A5BA(record); }
      var slid = this.B81C(record, move.x, move.y,
                           v.nastieBoxHeight, v.nastieBoxWidth);
      if (AAED(record, slid[0], slid[1])) {          // walked into the scenery
        this.A5CD(record);
      }
      record[SPRITE] ^= 0x01;
      record[X] = slid[0];
      record[Y] = slid[1];
      d = slid[1];                                   // what $B81C left in D
    }
    if (this.AB36(record, v.nastieHitHeight, v.nastieHitWidth, d)) {
      this.A4A6(record);
    }
  }; // A54F

  /**
   * $A4D7 — an animal that **chases**: every sweep it adds $08 to its speed
   * towards Sabreman, up to $30 (3 px a step, his own top speed).
   * @param {Uint8Array} record - The entity's record.
   */
  WorldMonsters.prototype.A4D7 = function (record) {
    var v = this.v;
    if (this.sabreman[ROOM] !== record[ROOM]) { return this.A493(record); }
    this.width = v.chaserWidth;
    var alive = (this.sabreman[SPRITE]-v.aliveFirstSprite) & 0xFF;
    if (alive >= v.aliveSpriteCount) { return this.A4A6(record); }
    record[DX] = this.chase(this.sabreman[X], record[X], record[DX]);
    record[DY] = this.chase(this.sabreman[Y], record[Y], record[DY]);
    // $A4C3: the pose out of the direction — and bit 0 and bit 1 both flip,
    // so a chaser flickers as it comes
    var facing = (record[DX] & 0x80) ? 0x02 : 0x00;
    record[SPRITE] = (((record[SPRITE] & 0xFD) | facing) ^ 0x03) & 0xFF;
    var move = this.A44B(record);
    if (move.bounceX) { A5A9(record); }
    else if (move.bounceY) { A5BA(record); }
    var slid = this.B81C(record, move.x, move.y,
                         v.nastieBoxHeight, v.nastieBoxWidth);
    record[X] = slid[0];
    record[Y] = slid[1];
    if (this.AB36(record, v.nastieHitHeight, v.nastieHitWidth, slid[1])) {
      this.A4A6(record);
    }
  }; // A4D7

  /** one axis of $A4D7: nothing when level, otherwise a push and a cap */
  WorldMonsters.prototype.chase = function (target, here, speed) {
    if (target === here) { return 0; }               // $A4F9: JR Z with A = 0
    var step = (target-here < 0) ? (-this.v.chaserAccel) & 0xFF : this.v.chaserAccel;
    return AFD0((step+speed) & 0xFF, this.v.chaserCap);
  }; // chase

  // -------------------------------------------------------------------------
  // the immortals ($AD07 rhino, $9E72 hippo, $AB74 native, $A630 roaming)
  // -------------------------------------------------------------------------

  /**
   * $A630 — how an immortal entity follows Sabreman around the world.
   *
   * ★ Not by walking there: when it is more than one row away it is simply
   * **moved to a screen next to his row**, keeping the bottom two bits of its
   * own column, and put down where that template's orchid would be. Which is
   * why the same rhino keeps turning up wherever you go.
   * @param {Uint8Array} record - The entity's record.
   */
  WorldMonsters.prototype.A630 = function (record) {
    var v = this.v;
    var here = this.sabreman[ROOM];
    if (here === record[ROOM]) { return; }
    var rows = ((record[ROOM] >> 4) & 0x0F)-((here >> 4) & 0x0F);
    if (rows < 0) { rows = -rows; }
    if (rows < v.roamRowGap) { return; }
    // ★ $A65B: a row that would carry out of the world falls back to
    // Sabreman's own screen number — which is why the entities in the top and
    // bottom rows behave differently from the rest
    var room = (this.rand & 1) ? here+v.roamRowStep : here-v.roamRowStepUp;
    if (room > 0xFF || room < 0) { room = here; }    // $A65B: JR C,$A67D
    room &= 0xFF;
    room = (room & v.roamColumnKeep) | (record[ROOM] & v.roamColumnMask);
    if (room === here) { return; }
    record[ROOM] = room;
    // $A7D4 HandlerOrchidPosition: where that template puts its orchid
    var position = this.world.orchidPositions[this.world.template(room)];
    record[X] = position[0];
    record[Y] = position[1];
  }; // A630

  /**
   * $AD07 — the rhino. ★ It cannot be killed: hit it and it turns and bolts
   * the way Sabreman is facing, at $A0 or $60, faster than it was walking.
   * @param {Uint8Array} record - The entity's record.
   */
  WorldMonsters.prototype.AD07 = function (record) {
    var v = this.v;
    this.AD93(record);
    this.width = v.rhinoWidth;
    var move = this.AFE8(record);                    // it walks off the screen
    var slid = this.B81C(record, move[0], move[1],
                         v.rhinoBoxHeight, v.rhinoBoxWidth);
    if (AAED(record, slid[0], slid[1])) {            // $AD1E: stopped by a tree
      this.AD86(record, v.rhinoTurnSpeed);
      ADA2(record);
    }
    record[X] = slid[0];
    record[Y] = slid[1];
    this.AD28(record, v.rhinoHitHeight, v.rhinoHitWidth);
  }; // AD07

  /** $AD28 — the tail the rhino and the hippo share: contact, then repel. */
  WorldMonsters.prototype.AD28 = function (record, height, width) {
    var d = (record[SPRITE] >> 1) & 1;
    if (!this.AB36(record, height, width, d)) { return; }
    if (this.sabreman[STATE] !== 0) {                // he is already dying
      ADA2(record);
      return;
    }
    this.AD69(record);
  }; // AD28

  /** $AD69 — driven off: which way depends on which way Sabreman faces. */
  WorldMonsters.prototype.AD69 = function (record) {
    var v = this.v;
    if (this.sabreman[SPRITE] & (1 << v.rhinoFacingBit)) {
      record[SPRITE] |= 0x02;                        // $AD7E
      record[DX] = v.rhinoRepelRight;
    } else {
      record[SPRITE] &= ~0x02;                       // $AD70
      record[DX] = v.rhinoRepelLeft;
    }
    this.out.sounds.push({name: 'repel'});                   // $BF17
  }; // AD69

  /** $AD86 — set the speed to a size, keeping the direction it had. */
  WorldMonsters.prototype.AD86 = function (record, speed) {
    record[DX] = (record[DX] & 0x80) ? ((-speed) & 0xFF) : speed;
  }; // AD86

  /** $9E72 — the hippo: also only driven off, and then stunned for $0F. */
  WorldMonsters.prototype.A9E72 = function (record) {
    var v = this.v;
    this.AD93(record);
    this.width = v.hippoWidth;
    if (record[STATE] !== 0) {                       // $9E99: stunned, no move
      record[STATE] = (record[STATE]-1) & 0xFF;
      this.AB36(record, v.hippoHitHeight, v.hippoHitWidth,
                (record[SPRITE] >> 1) & 1);
      return;
    }
    var move = this.AFE8(record);
    var slid = this.B81C(record, move[0], move[1],
                         v.hippoBoxHeight, v.hippoBoxWidth);
    if (AAED(record, slid[0], slid[1])) {
      // ★ stopped by the scenery, the hippo changes to the handler that
      // moves it to another screen altogether ($9EB3)
      record[SPRITE] |= (1 << v.hippoRoamBit);
      return;
    }
    record[X] = slid[0];
    record[Y] = slid[1];
    this.AD28(record, v.hippoHitHeight, v.hippoHitWidth);
  }; // A9E72

  /** $9EB3 — the hippo on its way somewhere else. */
  WorldMonsters.prototype.A9EB3 = function (record) {
    var v = this.v;
    var was = record[ROOM];
    this.A630(record);
    if (record[ROOM] !== was) {                      // $9F06: a new pose
      record[SPRITE] = (record[SPRITE] & 0xF3) | (this.rand & 0x08);
    }
    if (this.sabreman[ROOM] !== record[ROOM]) { return; }
    this.width = v.hippoWidth;
    var d = (record[SPRITE] >> 1) & 1;
    var hit;
    if (this.delay !== 0) {                          // $9EDF: JR NZ,$9F01
      hit = this.AB0E(record, v.hippoHitHeight, v.hippoHitWidth, this.delay);
    } else {
      var alive = (this.sabreman[SPRITE]-v.aliveFirstSprite) & 0xFF;
      if (alive >= v.aliveSpriteCount) {
        hit = this.AB0E(record, v.hippoHitHeight, v.hippoHitWidth, alive);
      } else {
        hit = this.AB36(record, v.hippoHitHeight, v.hippoHitWidth, d);
      }
    }
    if (!hit) { return; }
    record[SPRITE] &= ~(1 << v.hippoRoamBit);
    ADA2(record);
    record[STATE] = v.hippoStun;
    this.out.sounds.push({name: 'repel'});                   // $BF17
  }; // A9EB3

  /**
   * $AB74 — the native: driven off like the rest, and ★ the one that **points
   * at the amulet** ($9D41, measured in M4): in line with a buried piece he
   * is drawn yellow for that one sweep and beeps at a pitch that is the
   * distance.
   * @param {Uint8Array} record - The entity's record.
   */
  WorldMonsters.prototype.AB74 = function (record) {
    var v = this.v;
    this.A630(record);
    this.width = v.nativeWidth;
    var move = this.AFE8(record);
    var slid = this.B81C(record, move[0], move[1],
                         v.nativeBoxHeight, v.nativeBoxWidth);
    if (AAED(record, slid[0], slid[1])) {            // $ABDE: pick a new way
      this.ABEF(record, this.nativeSpeeds[this.rand & v.nativeSpeedMask]);
    }
    record[X] = slid[0];
    record[Y] = slid[1];
    this.AC0E(record);
    var d = (record[SPRITE] >> 2) & 1;
    if (this.AB36(record, v.nativeHitHeight, v.nativeHitWidth, d)) {
      this.ABEF(record,
                (this.sabreman[SPRITE] & v.nativeFacingBit)
                  ? v.nativeRepelRight : v.nativeRepelLeft);
      this.out.sounds.push({name: 'repel'});          // $BF17
    }
    // $ABB6: and the pointing, which is M4's rule
    var pointing = this.world ? this.world.A9D41(record) : null;
    if (pointing && this.sabreman[ROOM] === record[ROOM]) {
      this.out.pointing = pointing;
      // ★ výška tónu **je** ta vzdálenost ($BF3D: A + x + y, dvakrát doleva)
      this.out.sounds.push({name: 'pointing', distance: pointing.distance|0,
                            x: record[X], y: record[Y]});
    }
  }; // AB74

  /** $ABEF — take a horizontal speed, set the pose from it, draw a vertical. */
  WorldMonsters.prototype.ABEF = function (record, dx) {
    record[DX] = dx;
    if (dx & 0x80) {
      record[SPRITE] &= ~0x04;                       // $AC08
    } else {
      record[SPRITE] |= 0x04;                        // $ABF6
    }
    record[DY] = this.nativeSpeeds[this.frames & this.v.nativeSpeedMask];
  }; // ABEF

  // -------------------------------------------------------------------------
  // Sabre Wulf ($A858, $A922, $A8B2, $A8F5, $A964)
  // -------------------------------------------------------------------------

  /**
   * $A858 — Sabre Wulf himself.
   *
   * ★ He does not wander and he does not track: $A922 waits until Sabreman is
   * in the **same row of the world**, and then he charges straight down it at
   * $40 (4 px a step, faster than Sabreman can run). Touching him kills; the
   * sword only makes him back off.
   * @param {Uint8Array} record - His record.
   */
  WorldMonsters.prototype.A858 = function (record) {
    var v = this.v;
    this.width = v.wulfWidth;
    this.AC0E(record);
    this.A922(record);
    this.A8B2(record);
    this.A869(record);
  }; // A858

  /** $A869 — the move he shares with both of his backing-off states. */
  WorldMonsters.prototype.A869 = function (record) {
    var v = this.v;
    var move = this.AFE8(record);
    var slid = this.B81C(record, move[0], move[1],
                         v.wulfBoxHeight, v.wulfBoxWidth);
    if (AAED(record, slid[0], slid[1])) { ADB3(record); }
    record[X] = slid[0];
    record[Y] = slid[1];
    this.A880(record);
  }; // A869

  /** $A880 — and the contact, which is his alone: he kills, he does not die. */
  WorldMonsters.prototype.A880 = function (record) {
    var v = this.v, e = this.e;
    if (this.sabreman[ATTR] !== e.colourImmune) { return; }
    if (this.sabreman[ROOM] !== record[ROOM]) { return; }
    if (!this.AB01(record, v.wulfHitHeight, v.wulfHitWidth)) { return; }
    // $A897: which way Sabreman is thrown comes out of Wulf's own pose
    this.out.killed = ((((~record[SPRITE]) & 0xFF) >> 2) & 1)+1;
    var a = (this.sabreman[SPRITE]-v.wulfSwordRightFrom) & 0xFF;
    if (a >= 0x10) { ADB3(record); }                 // $A8A8: CP $10
  }; // A880

  /** $A922 — stand still, unless Sabreman is in this row of the world. */
  WorldMonsters.prototype.A922 = function (record) {
    var v = this.v;
    var here = this.sabreman[ROOM];
    if ((here & v.wulfRowMask) !== (record[ROOM] & v.wulfRowMask)) {
      record[STATE] = 0;
      return;
    }
    if (record[STATE] !== 0) { return; }
    record[STATE] = 1;
    var right;
    if (here === record[ROOM]) {
      right = this.sabreman[X] >= record[X];         // $A95A
    } else {
      right = here > record[ROOM];                   // $A946: JR NC
    }
    if (right) {
      record[DX] = v.wulfChargeRight;                // $A951
      record[SPRITE] |= 0x04;
    } else {
      record[DX] = v.wulfChargeLeft;                 // $A948
      record[SPRITE] &= ~0x04;
    }
  }; // A922

  /** $A8B2 — the sword, and the only thing that stops him. */
  WorldMonsters.prototype.A8B2 = function (record) {
    var v = this.v;
    if (this.sabreman[ROOM] !== record[ROOM]) { return; }
    if ((record[STATE] & 0xF0) !== 0) { return; }
    var a;
    if (record[DX] & 0x80) {                         // coming from the right
      if (this.sabreman[X] >= record[X]) { return; }
      a = (this.sabreman[SPRITE]-v.wulfSwordLeftFrom) & 0xFF;
    } else {
      if (this.sabreman[X] < record[X]) { return; }
      a = (this.sabreman[SPRITE]-v.wulfSwordRightFrom) & 0xFF;
    }
    if (a >= v.wulfSwordCount) { return; }
    record[SPRITE] = (record[SPRITE] & 0xFC) | v.wulfWardSprite;
    record[STATE] = v.wulfWardTimer;
  }; // A8B2

  /** $A8F5 — backing off, and staying backed off while the sword is on him. */
  WorldMonsters.prototype.A8F5 = function (record) {
    var v = this.v;
    var hold = false;
    if (this.sabreman[ROOM] === record[ROOM]) {
      var a = (this.sabreman[SPRITE]-v.wulfSwordRightFrom) & 0xFF;
      if (a < 0x10) {
        var bit = ((a >> 1) | (a << 7)) & 0x04;      // RRCA / AND %00000100
        hold = ((bit ^ record[SPRITE]) & 0x04) !== 0;
      }
    }
    if (!hold) {
      record[STATE] = (record[STATE]-1) & 0xFF;
      if (record[STATE] === 0) {
        record[SPRITE] = (record[SPRITE]+1) & 0xFF;
        record[STATE] = v.wulfRecoilTimer;
      }
    }
    this.A880(record);
  }; // A8F5

  /**
   * $A964 — and coming back. ★ With $20 more speed than he had, in whichever
   * direction he had it: **every time he is driven off he returns faster**.
   * @param {Uint8Array} record - His record.
   */
  WorldMonsters.prototype.A964 = function (record) {
    var v = this.v;
    record[STATE] = (record[STATE]-1) & 0xFF;
    if (record[STATE] === 0) {
      record[SPRITE] &= ~0x08;
      record[STATE] = v.wulfReturnTimer;
      var speed = record[DX];
      if (speed & 0x80) { speed = (speed-v.wulfSpeedUpNeg) & 0xFF; }
      record[DX] = (speed+v.wulfSpeedUp) & 0xFF;
    }
    this.A869(record);
  }; // A964

  // -------------------------------------------------------------------------
  // the keeper of the gate ($9F16)
  // -------------------------------------------------------------------------

  /**
   * $9F16 — the keeper.
   *
   * ★ Without the whole amulet he kills on contact, and he does it through
   * $AB3D, **below** the test that makes an orchid protect Sabreman — so the
   * one entity in the game an orchid does not save you from is this one. He
   * also writes $80 into +$02 rather than 1 or 2, which is the other death
   * animation ($A9AB). With all four pieces he simply steps aside, to $40 or
   * to $C0, whichever is away from Sabreman.
   * @param {Uint8Array} record - His record.
   */
  WorldMonsters.prototype.A9F16 = function (record) {
    var v = this.v;
    if (this.sabreman[ROOM] !== record[ROOM]) { return; }
    if ((this.sabreman[AMULET] & v.keeperAmuletMask) !== v.keeperAmuletAll) {
      this.AD93(record);
      if (this.AB36(record, v.keeperHitHeight, v.keeperHitWidth, 0, true)) {
        this.out.killed = v.keeperKill;              // $9F35: $80, not 1 or 2
        this.out.sounds.push({name: 'keeper'});       // $BF17
      }
      return;
    }
    // ★ he never writes $96AD, so the move uses whatever width the entity
    // before him left there — the original's own carelessness, kept
    if (this.sabreman[X] & (1 << v.keeperSideBit)) {
      record[DX] = v.keeperStepLeft;
      var left = this.AFE8(record);
      if (left[0] < v.keeperLimitLeft) { return; }
      record[X] = left[0];
    } else {
      record[DX] = v.keeperStepRight;
      var right = this.AFE8(record);
      if (right[0] >= v.keeperLimitRight) { return; }
      record[X] = right[0];
    }
    this.AD93(record);
  }; // A9F16

  // -------------------------------------------------------------------------
  // the fireball ($9ABC, $9AE9, $9D91, $9E0E)
  // -------------------------------------------------------------------------

  /**
   * $9D91 — the fireball, once it is on the screen.
   *
   * It lives 256 sweeps ($9DAC counts +$08 down from zero) and then blows
   * itself up, which is worth 185 points like any other enemy. It changes
   * direction every $40 sweeps, and ★ **every other time it aims at
   * Sabreman** — except that $9E4E writes the horizontal speed where it
   * means the vertical one, so it never aims upwards. That is the original's
   * bug and it is reproduced.
   * @param {Uint8Array} record - Its record.
   */
  WorldMonsters.prototype.A9D91 = function (record) {
    var v = this.v, e = this.e;
    if (this.sabreman[ROOM] !== record[ROOM]) { return this.A493(record); }
    this.width = v.fireballWidth;
    var alive = (this.sabreman[SPRITE]-v.aliveFirstSprite) & 0xFF;
    if (alive >= v.aliveSpriteCount) { return this.A4A6(record); }
    record[AGE] = (record[AGE]-1) & 0xFF;
    if (record[AGE] === 0) {                         // $A4A1: its time is up
      this.fireballTimer = v.fireballRespawn;
      return this.A4A6(record);
    }
    record[STATE] = (record[STATE]-1) & 0xFF;
    if (record[STATE] === 0) { this.A9E0E(record); }
    var move = this.A44B(record);
    if (move.bounceX) { A5A9(record); }
    else if (move.bounceY) { A5BA(record); }
    var slid = this.B81C(record, move.x, move.y,
                         v.fireballBoxHeight, v.fireballBoxWidth);
    if (AAED(record, slid[0], slid[1])) { this.A9E0E(record); }
    record[SPRITE] = (this.rand & v.fireballFlickerMask) | v.fireballFlickerBase;
    record[ATTR] = this.A9E64();
    record[X] = slid[0];
    record[Y] = slid[1];
    if (this.sabreman[ATTR] === e.colourImmune) {    // $9DE8: only the white one
      if (this.AB01(record, v.fireballHitHeight, v.fireballHitWidth)) {
        this.out.killed = (rotateLeft(this.sabreman[X], 1) & 1)+1;
      }
    }
    this.out.sounds.push({name: 'fireball', sweeps: this.sweeps});   // $BECC
  }; // A9D91

  /** $9E0E — a new direction: at Sabreman, or out of the table. */
  WorldMonsters.prototype.A9E0E = function (record) {
    var v = this.v;
    record[STATE] = v.fireballTurnEvery;
    if ((this.sweeps & v.fireballHomeMask) !== 0) {  // $9E2F: aim at him
      if (this.sabreman[X] < record[X]) {
        record[DX] = v.fireballHomeLeft;
      } else {
        record[DX] = v.fireballHomeRight;
      }
      if (this.sabreman[Y] < record[Y]) {
        // ★ $9E4E: `LD (IX+$06),$40` where it should be `(IX+$07)`. The
        // fireball cannot come up at him, it swerves right instead.
        record[DX] = v.fireballHomeUp;
      } else {
        record[DY] = v.fireballHomeDown;
      }
      return;
    }
    record[DX] = this.fireballSpeeds[this.rand & v.fireballSpeedMask];
    // $9E24: LD A,R — the refresh register, which nothing can reproduce
    record[DY] = (this.sweeps+this.refresh) & 0xFF;
  }; // A9E0E

  /** $9E64 — and the colour it flickers in. */
  WorldMonsters.prototype.A9E64 = function () {
    var v = this.v;
    var a = this.rand & v.fireballColourMask;
    if (a < v.fireballColourMin) { a |= v.fireballColourFill; }
    return a | v.fireballColourBase;
  }; // A9E64

  // -------------------------------------------------------------------------
  // the two things $9A1D does at the end of every sweep
  // -------------------------------------------------------------------------

  /**
   * $9A3C — put an animal into the world.
   *
   * Six slots in all, three to a screen ($96BE), and never while the changeover
   * delay runs or Sabreman is off his feet. The place is `Rand8 & $7F + $30`
   * by `FRAMES & $7F + $30`, and it is refused if it lands on Sabreman.
   *
   * ★ It is refused **inside the scenery** too, and by a back door: $9B33
   * calls the slide $B81C and throws its answer away — but not its carry
   * flag, and $9A8D returns on it. Since the record already holds the new
   * place, the slide compares that place with itself, so its carry is simply
   * "this is in a tree". One `RET C` doing the work of a test that was never
   * written.
   */
  WorldMonsters.prototype.A9A3C = function () {
    var v = this.v;
    if (this.delay !== 0) { return; }
    if (this.spawnTimer !== 0) {
      this.spawnTimer = (this.spawnTimer-1) & 0xFF;
      return;
    }
    var alive = (this.sabreman[SPRITE]-v.aliveFirstSprite) & 0xFF;
    if (alive >= v.aliveSpriteCount) { return; }
    var free = -1, here = 0, i;
    for (i = 0; i < this.nastie.length; i++) {
      if (this.nastie[i][SPRITE] === 0) { free = i; break; }
    }
    if (free < 0) { return; }
    for (i = 0; i < this.nastie.length; i++) {       // $9A68: how many are here
      if (this.nastie[i][SPRITE] !== 0
          && this.nastie[i][ROOM] === this.sabreman[ROOM]) {
        here++;
      }
    }
    if (here === v.nastiePerRoom) { return; }
    var record = this.nastie[free];
    record[X] = (this.rand & v.spawnRandMask)+v.spawnBase;
    record[Y] = (this.frames & v.spawnFramesMask)+v.spawnBase;
    record[ROOM] = this.sabreman[ROOM];
    if (this.AB01(record, v.spawnBoxHeight, v.spawnBoxWidth)) {
      return;                                        // $9B2F: too near him
    }
    if (this.blocked(record, v.spawnBoxHeight, v.spawnBoxWidth)) {
      return;                                        // $9B33: or in a tree
    }
    record[ATTR] = this.spawnColours[this.sweeps & v.spawnColourMask];
    record[SPRITE] = v.spawnSprite;                  // the shimmer, $01
    record[STATE] = 0;
    record[DX] = 0;
    record[DY] = 0;
    record[AGE] = 0;
    record[9] = 0;
    record[10] = 0;
    record[AMULET] = 0;
    this.out.spawned++;
  }; // A9A3C

  /**
   * $9ABC — and the fireball, for standing still.
   *
   * $96B4 counts down a sweep at a time and every screen change puts it back
   * to $80 ($B148), so it only ever reaches zero for a player who stays put.
   * Blow the fireball up and it is back in $10 sweeps, not $80.
   */
  WorldMonsters.prototype.A9ABC = function () {
    var v = this.v;
    var alive = (this.sabreman[SPRITE]-v.aliveFirstSprite) & 0xFF;
    if (alive >= v.aliveSpriteCount) { return; }
    if (this.delay !== 0) { return; }
    var record = this.fireball();
    if (record[SPRITE] !== 0) { return; }            // there is one already
    if (this.fireballTimer !== 0) {
      this.fireballTimer = (this.fireballTimer-1) & 0xFF;
      if (this.fireballTimer !== 0) { return; }
    }
    // $9AE9: in line with Sabreman on one axis, at random on the other
    if ((this.sweeps & v.fireballAlignMask) === 0) {
      record[X] = this.sabreman[X];
      record[Y] = (this.frames & v.spawnFramesMask)+v.spawnBase;
    } else {
      record[Y] = this.sabreman[Y];
      record[X] = (this.rand & v.spawnRandMask)+v.spawnBase;
    }
    record[ROOM] = this.sabreman[ROOM];
    if (this.AB01(record, v.spawnBoxHeight, v.spawnBoxWidth)) { return; }
    if (this.blocked(record, v.spawnBoxHeight, v.spawnBoxWidth)) { return; }
    record[SPRITE] = v.fireballSprite;
    record[ATTR] = v.fireballColour;
    record[STATE] = 0;
    record[DX] = 0;
    record[DY] = 0;
    record[AGE] = 0;
    record[9] = 0;
    record[10] = 0;
    record[AMULET] = 0;
  }; // A9ABC

  /** The M5 entities of the current screen, for the worker's frame message. */
  WorldMonsters.prototype.visible = function (room) {
    var list = [];
    function add(record) {
      if (record[SPRITE] && record[ROOM] === room) {
        list.push({sprite: record[SPRITE], room: record[ROOM],
                   x: record[X], y: record[Y], colour: record[ATTR]});
      }
    }
    this.immortal.forEach(add);
    this.nastie.forEach(add);
    return list;
  }; // visible

  WorldMonsters.RECORD = {SPRITE: SPRITE, ROOM: ROOM, STATE: STATE, X: X,
                          Y: Y, ATTR: ATTR, DX: DX, DY: DY, AGE: AGE,
                          AMULET: AMULET, LENGTH: RECORD_LENGTH};
  WorldMonsters.signed = signed;
  WorldMonsters.B031 = B031;
  WorldMonsters.AFD0 = AFD0;
  return WorldMonsters;
})();

if (typeof self !== 'undefined') { self.WorldMonsters = WorldMonsters; }
if (typeof module !== 'undefined' && module.exports) { module.exports = WorldMonsters; }
