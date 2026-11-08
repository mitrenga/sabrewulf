// begin code

/**
 * The one-bit beeper of the ZX Spectrum, and Sabre Wulf's ten sounds and four
 * tunes on it.
 *
 * ★ **The whole of the game's audio is two routines.** PlaySquareWave ($BF74)
 * flips bit 4 of port $FE up, waits B times round a DJNZ, flips it down and
 * waits B times again — one square cycle, and the pitch is B and nothing else.
 * PlayWaveSequence ($BF6D) does C of them — and the length is C and nothing
 * else. Every sound effect in the game is a pair (B, C) or a loop that moves B;
 * there is no envelope, no sample table and no noise generator anywhere in the
 * program (data/sounds.json, tools/dumpsound.py).
 *
 * ★ And unlike Underwurlde, this game has **music**: PlayAudio ($BD6E) walks a
 * string of bytes terminated by $FF, six bits of each being a note in a table
 * of 61 (an equally tempered chromatic scale, G#1 to G6) and two bits its
 * length. It plays with interrupts disabled, so the game stands still while it
 * sounds — which is why the tunes are short and why the menu's one can be cut
 * off with a key (data/music.json, tools/dumpmusic.py).
 *
 * Because the pitch of a beeper tone is a **count of Z80 T-states**, this class
 * does not approximate the routines with oscillators: it runs them, instruction
 * by instruction, keeping the clock rather than the registers, and emits the
 * very list of speaker writes the original would make. tools/tracesound.py
 * records what the original really writes to port $FE in a simulator, and
 * tools/matchsound.js runs this file against those recordings **pulse by
 * pulse** — so a mistake of one T-state in one instruction shows up as a
 * difference rather than as a slightly wrong note.
 *
 * The output goes to the svision pulse handlers in the shape they take
 * ({fragments, pulses}), which is the same shape the machine produces: a list
 * of how long the speaker stayed where it was. Nothing is sampled.
 *
 * Deliberately free of DOM and Node dependencies, so an offline tool
 * can synthesize with the very same code.
 */

/** the Z80 in a ZX Spectrum, hw_notes.md */
const CLOCK = 3500000;

/**
 * T-states of the instructions these routines are made of. They are the
 * machine's, not the game's, so they are here rather than in a data file —
 * but they are what decides the pitch, so tools/matchsound.js checks every one
 * of them against the original pulse by pulse.
 */
const T = {
  ld_a_n: 7, ld_r_r: 4, ld_a_nn: 13, ld_rr_nn: 10, ld_a_ix: 19, add_a_ix: 19,
  ld_r_hl: 7, ld_hl_r: 7, inc_hl: 6, dec_hl: 6, inc_de: 6, dec_bc: 6,
  inc_at_hl: 11, alu_r: 4, alu_n: 7, rot_a: 4, daa: 4, cpl: 4,
  add_hl_rr: 11, push: 11, pop: 10, call: 17, ret: 10, ret_cc_taken: 11,
  ret_cc_skipped: 5, jp: 10, jr_taken: 12, jr_skipped: 7, bit_r: 8,
  out_n_a: 11, in_a_n: 11, di: 4, ei: 4,
  /** and the moment inside OUT (n),A at which the write reaches the ULA */
  out_write: 12,
  /** DJNZ: 13 T while it loops, 8 on the pass that leaves */
  djnz_taken: 13, djnz_skipped: 8
};

/** `DJNZ $` run to exhaustion from B — and B = 0 means 256, as always on a Z80 */
function djnz(b) {
  const count = b || 256;
  return T.djnz_taken*(count-1)+T.djnz_skipped;
} // djnz

/** `DAA` after `OR n`, which leaves N=0, H=0 and C=0 — so it is the plain adjust */
function daa(value) {
  let result = value;
  if ((result & 0x0F) > 9) { result += 0x06; }
  if (result > 0x9F) { result += 0x60; }
  return result & 0xFF;
} // daa

/** `RLCA` n times */
function rotateLeft(value, times) {
  let result = value;
  for (let i = 0; i < times; i++) { result = ((result << 1) | (result >> 7)) & 0xFF; }
  return result;
} // rotateLeft

/** `RRCA` n times */
function rotateRight(value, times) {
  let result = value;
  for (let i = 0; i < times; i++) { result = ((result >> 1) | (result << 7)) & 0xFF; }
  return result;
} // rotateRight

/**
 * One run of one of the original's audio routines: the clock, and the writes
 * to port $FE it made on the way.
 */
class Run {

  constructor() {
    /** T-states since the routine was entered */
    this.t = 0;
    /** every OUT ($FE),A the routine did: {t, value} */
    this.writes = [];
  } // constructor

  /** advance the clock without touching the speaker */
  wait(tstates) {
    this.t += tstates;
  } // wait

  /** `OUT ($FE),A` — the write lands part way into the instruction */
  out(value) {
    this.writes.push({t: this.t+T.out_write, value: value});
    this.t += T.out_n_a;
  } // out

} // class Run

export class Beeper {

  static get CLOCK() { return CLOCK; }

  /**
   * @param {Object} sounds - The parsed data/sounds.json (tools/dumpsound.py).
   * @param {Object} music - The parsed data/music.json (tools/dumpmusic.py).
   */
  constructor(sounds, music) {
    this.sounds = sounds;
    this.music = music;
    this.effects = {};
    (sounds && sounds.effects || []).forEach((effect) => {
      this.effects[effect.name] = effect;
    });
    this.event = {};
    (sounds && sounds.events || []).forEach((event) => {
      this.event[event.event] = event;
    });
    this.speakerOn = sounds && sounds.machine ? sounds.machine.speakerOn : 0x10;
    this.speakerOff = 0x00;
  } // constructor

  // -------------------------------------------------------------------------
  // The two routines everything else is made of
  // -------------------------------------------------------------------------

  /**
   * $BF74 PlaySquareWave — one square cycle, and the pitch is B.
   * @param {Run} run - The run being clocked.
   * @param {number} b - The duration of each half of the cycle.
   */
  squareWave(run, b) {
    run.wait(T.ld_a_n);                             // $BF74 LD A,$10
    run.out(this.speakerOn);                        // $BF76 OUT ($FE),A
    run.wait(T.ld_r_r);                             // $BF78 LD A,B
    run.wait(djnz(b));                              // $BF79 DJNZ $BF79
    run.wait(T.ld_r_r);                             // $BF7B LD B,A
    run.wait(T.alu_r);                              // $BF7C XOR A
    run.out(this.speakerOff);                       // $BF7D OUT ($FE),A
    run.wait(T.ld_r_r);                             // $BF7F LD A,B
    run.wait(djnz(b));                              // $BF80 DJNZ $BF80
    run.wait(T.ld_r_r);                             // $BF82 LD B,A
    run.wait(T.ret);                                // $BF83 RET
  } // squareWave

  /**
   * $BF6D PlayWaveSequence — C of those, and the length is C.
   * @param {Run} run - The run being clocked.
   * @param {number} b - The duration of each half cycle.
   * @param {number} c - How many cycles; 0 means 256, as on the Z80.
   */
  waveSequence(run, b, c) {
    const count = c || 256;
    for (let i = 0; i < count; i++) {
      run.wait(T.call);                             // $BF6D CALL $BF74
      this.squareWave(run, b);
      run.wait(T.alu_r);                            // $BF70 DEC C
      run.wait(i+1 < count ? T.jr_taken : T.jr_skipped);   // $BF71 JR NZ
    }
    run.wait(T.ret);                                // $BF73 RET
  } // waveSequence

  // -------------------------------------------------------------------------
  // The ten sounds
  // -------------------------------------------------------------------------

  /**
   * Runs one of the game's sound routines and returns what it wrote to the
   * speaker.
   *
   * @param {string} name - The effect's name in data/sounds.json.
   * @param {Object} [params] - What the routine reads out of the machine:
   *        `sweeps` ($9693), `rand` ($9695), `rom` (the bytes it reads),
   *        `sprite` (IX+$00), `phase` (IX+$02), `distance`, `x`, `y`,
   *        `counter` ($96B3), `colour` (IX+$05).
   * @returns {Object} {writes, tstates} — every OUT ($FE),A and how long the
   *          routine took, both counted from the moment it was entered.
   */
  effect(name, params) {
    const run = new Run();
    const values = params || {};
    let counter;
    switch (name) {
      // the two primitives on their own, so tools/matchsound.js can check them
      // against the original before anything is built on top of them
      case 'squareWave': this.squareWave(run, values.b); break;
      case 'waveSequence': this.waveSequence(run, values.b, values.c); break;
      case 'step': counter = this.stepEffect(run, values); break;
      case 'fly': this.flyEffect(run, values); break;
      case 'land': this.landEffect(run); break;
      case 'repel': case 'keeper': this.repelEffect(run); break;
      case 'object': case 'life': this.waveEffect(run, 'object', T.jr_taken); break;
      case 'orchid': this.waveEffect(run, 'orchid', T.jr_taken); break;
      case 'orchidEnd': this.waveEffect(run, 'orchidEnd', T.jp); break;
      case 'explosion': this.explosionEffect(run, values); break;
      case 'materialise': this.materialiseEffect(run, values); break;
      case 'pointing': this.pointingEffect(run, values); break;
      case 'fireball': this.fireballEffect(run, values); break;
      default: return null;
    }
    const result = {writes: run.writes, tstates: run.t};
    if (counter !== undefined) { result.counter = counter; }
    return result;
  } // effect

  /**
   * $BF25 / $BF2A / $BEC6 — a flat tone: load BC and go. The three differ only
   * in whether they get there with a JR or a JP, which is two T-states.
   * @param {Run} run - The run being clocked.
   * @param {string} name - The effect in data/sounds.json.
   * @param {number} jump - The cost of the jump into $BF6D.
   */
  waveEffect(run, name, jump) {
    const effect = this.effects[name];
    run.wait(T.ld_rr_nn);                           // LD BC,nn
    run.wait(jump);                                 // JR/JP $BF6D
    this.waveSequence(run, effect.b, effect.c);
  } // waveEffect

  /**
   * $BF4B — the footstep. ★ It beeps only every eighth step, high or low by
   * bit 3 of the counter at $96B3 — and under the cyan orchid, the one that
   * makes Sabreman fast, the routine **falls through into itself** and beeps
   * twice, so the steps rattle at double rate.
   * @param {Run} run - The run being clocked.
   * @param {Object} values - {counter, colour}.
   * @returns {number} $96B3 after the step, for the caller to hold on to.
   */
  stepEffect(run, values) {
    const effect = this.effects.step;
    let counter = (values.counter || 0) & 0xFF;
    const colour = values.colour === undefined ? 0x47 : values.colour;
    run.wait(T.call);                               // $BF4B CALL $BF54
    counter = this.stepBeep(run, effect, counter);
    run.wait(T.ld_a_ix);                            // $BF4E LD A,(IX+$05)
    run.wait(T.alu_n);                              // $BF51 CP $45
    if (colour !== effect.colourFast) {
      run.wait(T.ret_cc_taken);                     // $BF53 RET NZ
      return counter;
    }
    run.wait(T.ret_cc_skipped);
    return this.stepBeep(run, effect, counter);     // ★ and again
  } // stepEffect

  /**
   * $BF54 — the body of the footstep: count, and beep on every eighth.
   * @param {Run} run - The run being clocked.
   * @param {Object} effect - The effect out of data/sounds.json.
   * @param {number} counter - $96B3 on the way in.
   * @returns {number} And on the way out.
   */
  stepBeep(run, effect, counter) {
    const next = (counter+1) & 0xFF;
    run.wait(T.ld_rr_nn);                           // $BF54 LD HL,$96B3
    run.wait(T.inc_at_hl);                          // $BF57 INC (HL)
    run.wait(T.ld_r_hl);                            // $BF58 LD A,(HL)
    run.wait(T.bit_r);                              // $BF59 BIT 3,A
    const high = (next >> effect.bit) & 1;
    run.wait(high ? T.jr_skipped : T.jr_taken);     // $BF5B JR Z,$BF65
    run.wait(T.alu_n);                              // AND $07
    if (next & effect.mask) {
      run.wait(T.ret_cc_taken);                     // RET NZ — most steps
      return next;
    }
    run.wait(T.ret_cc_skipped);
    const wave = high ? effect.high : effect.low;
    run.wait(T.ld_rr_nn);                           // LD BC,$4004 / $6004
    run.wait(T.jr_taken);                           // JR $BF6D
    this.waveSequence(run, wave.b, wave.c);
    return next;
  } // stepBeep

  /**
   * $A9F8 — the flight after death. ★ B is the phase of the flight itself, so
   * the tone falls away as Sabreman sails off.
   * @param {Run} run - The run being clocked.
   * @param {Object} values - {phase} — +$02 of his record.
   */
  flyEffect(run, values) {
    const effect = this.effects.fly;
    run.wait(T.ld_a_ix);                            // $A9F8 LD B,(IX+$02)
    run.wait(T.ld_a_n);                             // $A9FB LD C,$04
    run.wait(T.jp);                                 // $A9FD JP $BF6D
    this.waveSequence(run, (values.phase || 0) & 0xFF, effect.c);
  } // flyEffect

  /**
   * $BF2F — the landing: C counts $30 down to 1 and the pitch is
   * (C XOR $55) + C, which wanders rather than sweeps.
   * @param {Run} run - The run being clocked.
   */
  landEffect(run) {
    const effect = this.effects.land;
    run.wait(T.ld_a_n);                             // $BF2F LD C,$30
    for (let c = effect.start; c > 0; c--) {
      run.wait(T.ld_r_r);                           // $BF31 LD A,C
      run.wait(T.alu_n);                            // $BF32 XOR $55
      run.wait(T.alu_r);                            // $BF34 ADD A,C
      run.wait(T.ld_r_r);                           // $BF35 LD B,A
      run.wait(T.call);                             // $BF36 CALL $BF74
      this.squareWave(run, (((c ^ effect.xor)+c) & 0xFF));
      run.wait(T.alu_r);                            // $BF39 DEC C
      run.wait(c > 1 ? T.jr_taken : T.jr_skipped);  // $BF3A JR NZ
    }
    run.wait(T.ret);                                // $BF3C RET
  } // landEffect

  /**
   * $BF17 — driving something off with the sword, and the keeper of the gate.
   * ★ The pitch is DAA(C OR $18): the Z80's decimal adjust used as a tone
   * generator, which is why it steps unevenly.
   * @param {Run} run - The run being clocked.
   */
  repelEffect(run) {
    const effect = this.effects.repel;
    run.wait(T.ld_a_n);                             // $BF17 LD C,$30
    for (let c = effect.start; c > 0; c--) {
      run.wait(T.ld_r_r);                           // $BF19 LD A,C
      run.wait(T.alu_n);                            // $BF1A OR $18
      run.wait(T.daa);                              // $BF1C DAA
      run.wait(T.ld_r_r);                           // $BF1D LD B,A
      run.wait(T.call);                             // $BF1E CALL $BF74
      this.squareWave(run, daa(c | effect.or));
      run.wait(T.alu_r);                            // $BF21 DEC C
      run.wait(c > 1 ? T.jr_taken : T.jr_skipped);  // $BF22 JR NZ
    }
    run.wait(T.ret);                                // $BF24 RET
  } // repelEffect

  /**
   * $BEEE — an animal blowing up. ★ The sixteen tone lengths are **bytes of
   * the Spectrum's ROM**, read at ($9693 & $1F)*256 + Rand8: the same well of
   * randomness the map of objects comes from (M4, $A2BD), and the same hole in
   * the remake, because the ROM is not ours to ship. The rule is reproduced;
   * where the bits come from is the remake's own.
   * @param {Run} run - The run being clocked.
   * @param {Object} values - {rom} — the sixteen bytes it reads.
   */
  explosionEffect(run, values) {
    const effect = this.effects.explosion;
    const rom = values.rom || [];
    run.wait(T.ld_a_nn);                            // $BEEE LD A,($9695)
    run.wait(T.ld_r_r);                             // $BEF1 LD L,A
    run.wait(T.ld_a_nn);                            // $BEF2 LD A,($9693)
    run.wait(T.alu_n);                              // $BEF5 AND $1F
    run.wait(T.ld_r_r);                             // $BEF7 LD H,A
    run.wait(T.ld_a_n);                             // $BEF8 LD E,$10
    for (let i = 0; i < effect.tones; i++) {
      run.wait(T.ld_r_hl);                          // $BEFA LD A,(HL)
      run.wait(T.inc_hl);                           // $BEFB INC HL
      run.wait(T.alu_n);                            // $BEFC AND $7F
      run.wait(T.ld_r_r);                           // $BEFE LD B,A
      run.wait(T.ld_a_n);                           // $BEFF LD C,$02
      run.wait(T.call);                             // $BF01 CALL $BF6D
      this.waveSequence(run, (rom[i] || 0) & effect.byteMask, effect.c);
      run.wait(T.alu_r);                            // $BF04 DEC E
      run.wait(i+1 < effect.tones ? T.jr_taken : T.jr_skipped);
    }
    run.wait(T.ret);                                // $BF07 RET
  } // explosionEffect

  /**
   * $BF08 — an animal materialising. ★ The pitch is the sprite number itself,
   * complemented, so every kind of animal arrives on its own note.
   * @param {Run} run - The run being clocked.
   * @param {Object} values - {sprite} — IX+$00.
   */
  materialiseEffect(run, values) {
    const effect = this.effects.materialise;
    run.wait(T.ld_a_ix);                            // $BF08 LD A,(IX+$00)
    run.wait(T.cpl);                                // $BF0B CPL
    run.wait(T.rot_a*effect.rotate);                // $BF0C RRCA x3
    run.wait(T.alu_n);                              // $BF0F AND $E0
    run.wait(T.ld_r_r);                             // $BF11 LD B,A
    run.wait(T.ld_a_n);                             // $BF12 LD C,$06
    run.wait(T.jp);                                 // $BF14 JP $BF6D
    const b = rotateRight((~(values.sprite || 0)) & 0xFF, effect.rotate) & effect.mask;
    this.waveSequence(run, b, effect.c);
  } // materialiseEffect

  /**
   * $BF3D — the native pointing at a buried piece of the amulet. ★ The pitch
   * **is the distance**: $9D41 (M4) hands over how far off the piece is and
   * the routine adds the native's own x and y to it.
   * @param {Run} run - The run being clocked.
   * @param {Object} values - {distance, x, y}.
   */
  pointingEffect(run, values) {
    const effect = this.effects.pointing;
    run.wait(T.add_a_ix);                           // $BF3D ADD A,(IX+$03)
    run.wait(T.add_a_ix);                           // $BF40 ADD A,(IX+$04)
    run.wait(T.rot_a*effect.rotate);                // $BF43 RLCA x2
    run.wait(T.ld_r_r);                             // $BF45 LD B,A
    run.wait(T.ld_a_n);                             // $BF46 LD C,$08
    run.wait(T.jp);                                 // $BF48 JP $BF6D
    const sum = ((values.distance || 0)+(values.x || 0)+(values.y || 0)) & 0xFF;
    this.waveSequence(run, rotateLeft(sum, effect.rotate), effect.c);
  } // pointingEffect

  /**
   * $BECC — the fireball, whose pitch comes out of a table of sixteen indexed
   * by the sweep counter, so it churns rather than holds a note.
   * @param {Run} run - The run being clocked.
   * @param {Object} values - {sweeps} — $9693.
   */
  fireballEffect(run, values) {
    const effect = this.effects.fireball;
    run.wait(T.ld_rr_nn);                           // $BECC LD BC,$BEDE
    run.wait(T.ld_a_nn);                            // $BECF LD A,($9693)
    run.wait(T.alu_n);                              // $BED2 AND $0F
    run.wait(T.ld_r_r);                             // $BED4 LD L,A
    run.wait(T.ld_a_n);                             // $BED5 LD H,$00
    run.wait(T.add_hl_rr);                          // $BED7 ADD HL,BC
    run.wait(T.ld_r_hl);                            // $BED8 LD B,(HL)
    run.wait(T.ld_a_n);                             // $BED9 LD C,$10
    run.wait(T.jp);                                 // $BEDB JP $BF6D
    this.waveSequence(run, effect.table[(values.sweeps || 0) & effect.mask],
                      effect.c);
  } // fireballEffect

  // -------------------------------------------------------------------------
  // The four tunes
  // -------------------------------------------------------------------------

  /**
   * Plays one of the four tunes the way PlayAudio ($BD6E) plays it.
   *
   * @param {string} name - gameComplete, gameOver, poem or gameInitialisation.
   * @param {Object} [options] - `waitKey` for the menu's variant ($BD51),
   *        which polls the keyboard between notes and is therefore a shade
   *        slower; `until` to stop after that many bytes, which is what a
   *        keypress does.
   * @returns {Object} {writes, tstates} — the same shape as effect().
   */
  tune(name, options) {
    const tune = this.music && this.music.tunes ? this.music.tunes[name] : null;
    if (!tune) { return null; }
    const settings = options || {};
    const run = new Run();
    const bytes = tune.bytes.slice(0, settings.until === undefined
                                   ? tune.bytes.length : settings.until);
    run.wait(T.di);                                 // $BD6E / $BD51 DI
    for (let i = 0; i < bytes.length; i++) {
      if (settings.waitKey) {
        run.wait(T.alu_r);                          // $BD52 XOR A
        run.wait(T.out_n_a);                        // $BD53 OUT ($FD),A — not the speaker
        run.wait(T.in_a_n);                         // $BD55 IN A,($FE)
        run.wait(T.cpl);                            // $BD57 CPL
        run.wait(T.alu_n);                          // $BD58 AND $1F
        run.wait(T.jr_taken);                       // $BD5A JR Z,$BD64 — no key
      }
      run.wait(T.ld_r_hl);                          // LD A,(DE)
      run.wait(T.alu_n);                            // CP $FF
      run.wait(T.jr_skipped);                       // JR Z — not the terminator
      run.wait(T.call);                             // CALL $BD7B
      this.playNote(run, bytes[i]);
      run.wait(T.jr_taken);                         // JR back
    }
    // the terminator, and out
    if (settings.waitKey) {
      run.wait(T.alu_r+T.out_n_a+T.in_a_n+T.cpl+T.alu_n+T.jr_taken);
    }
    run.wait(T.ld_r_hl);                            // LD A,(DE)
    run.wait(T.alu_n);                              // CP $FF
    run.wait(T.jr_taken);                           // JR Z,$BD79
    run.wait(T.ei);                                 // $BD79 EI
    run.wait(T.ret);                                // $BD7A RET
    return {writes: run.writes, tstates: run.t};
  } // tune

  /**
   * $BD7B PlayAudio_Process — one byte of a tune. Bits 0-5 are the note, bits
   * 6-7 its length as a multiple of one to four.
   * @param {Run} run - The run being clocked.
   * @param {number} byte - The byte of the tune.
   */
  playNote(run, byte) {
    const player = this.music.player;
    const index = byte & player.noteMask;
    const units = ((byte >> 6) & 3)+1;
    run.wait(T.alu_n);                              // $BD7B AND $3F
    if (index === 0) {
      run.wait(T.jr_taken);                         // $BD7D JR Z,$BDBC
      this.playRest(run, units);
      return;
    }
    run.wait(T.jr_skipped);
    const note = this.music.notes[index];
    run.wait(T.ld_r_r);                             // $BD7F LD L,A
    run.wait(T.ld_a_n);                             // $BD80 LD H,$00
    run.wait(T.add_hl_rr*2);                        // $BD82 ADD HL,HL x2
    run.wait(T.ld_rr_nn);                           // $BD84 LD BC,$BDD2
    run.wait(T.add_hl_rr);                          // $BD87 ADD HL,BC
    run.wait(T.ld_r_hl+T.inc_hl+T.ld_r_hl+T.inc_hl);        // B, C
    run.wait(T.ld_r_hl+T.inc_hl+T.ld_r_hl+T.ld_r_r);        // and the length
    run.wait(T.ld_r_hl);                            // $BD90 LD A,(DE)
    run.wait(T.rot_a*2);                            // $BD91 RLCA x2
    run.wait(T.alu_n);                              // $BD93 AND $03
    run.wait(T.alu_r);                              // $BD95 INC A
    run.wait(T.push);                               // $BD96 PUSH DE
    run.wait(T.ld_r_r*2);                           // $BD97 LD E,L / LD D,H
    for (let i = 1; i <= units; i++) {              // $BD99: HL = length * units
      run.wait(T.alu_r);                            // DEC A
      if (i === units) { run.wait(T.jr_taken); break; }
      run.wait(T.jr_skipped);
      run.wait(T.add_hl_rr);                        // ADD HL,DE
      run.wait(T.jr_taken);                         // JR $BD99
    }
    run.wait(T.pop);                                // $BD9F POP DE
    const cycles = note.cycles*units;
    const half = Beeper.delay(note.b, note.c);
    for (let cycle = 0; cycle < cycles; cycle++) {
      run.wait(T.push);                             // $BDA0 PUSH BC
      run.wait(T.alu_r);                            // $BDA1 XOR A
      run.out(this.speakerOff);                     // $BDA2 OUT ($FE),A
      run.wait(half);
      run.wait(T.pop);                              // $BDA9 POP BC
      run.wait(T.push);                             // $BDAA PUSH BC
      run.wait(T.ld_a_n);                           // $BDAB LD A,$10
      run.out(this.speakerOn);                      // $BDAD OUT ($FE),A
      run.wait(half);
      run.wait(T.pop);                              // $BDB4 POP BC
      run.wait(T.dec_hl);                           // $BDB5 DEC HL
      run.wait(T.ld_r_r*2);                         // $BDB6 LD A,H / OR L
      run.wait(cycle+1 < cycles ? T.jr_taken : T.jr_skipped);
    }
    run.wait(T.inc_de);                             // $BDBA INC DE
    run.wait(T.ret);                                // $BDBB RET
  } // playNote

  /**
   * $BDBC — a rest: the same one to four units of length, spent counting a
   * sixteen bit register down instead of flipping the speaker.
   * @param {Run} run - The run being clocked.
   * @param {number} units - One to four.
   */
  playRest(run, units) {
    const delay = this.music.player.restDelay || 65536;
    run.wait(T.ld_r_hl);                            // $BDBC LD A,(DE)
    run.wait(T.inc_de);                             // $BDBD INC DE
    run.wait(T.rot_a*2);                            // $BDBE RLCA x2
    run.wait(T.alu_n);                              // $BDC0 AND $03
    run.wait(T.alu_r);                              // $BDC2 INC A
    run.wait(T.ld_r_r);                             // $BDC3 LD L,A
    run.wait(T.ld_rr_nn);                           // $BDC4 LD BC,$430B
    for (let i = 0; i < units; i++) {
      run.wait(T.push);                             // $BDC7 PUSH BC
      // $BDC8: DEC BC / LD A,B / OR C / JR NZ
      run.wait((T.dec_bc+T.ld_r_r*2+T.jr_taken)*(delay-1)
               + T.dec_bc+T.ld_r_r*2+T.jr_skipped);
      run.wait(T.pop);                              // $BDCD POP BC
      run.wait(T.alu_r);                            // $BDCE DEC L
      run.wait(i+1 < units ? T.jr_taken : T.jr_skipped);
    }
    run.wait(T.ret);                                // $BDD1 RET
  } // playRest

  /**
   * The delay loop of the music player ($BDA4 / $BDAF), which is what sets the
   * pitch of a note.
   *
   * ★ It is not B*C: `DJNZ` runs B times only the **first** time round, because
   * B is left at zero, so every later pass is a full 256. That makes the pair
   * (B, C) a linear count of B + 256*(C-1) — and the table of 61 notes is an
   * equally tempered chromatic scale in exactly that measure.
   *
   * @param {number} b - The inner count; 0 means 256.
   * @param {number} c - The outer count; 0 means 256.
   * @returns {number} T-states.
   */
  static delay(b, c) {
    const passes = c || 256;
    let total = djnz(b)+T.alu_r;
    for (let i = 1; i < passes; i++) {
      total += T.jr_taken+djnz(0)+T.alu_r;
    }
    return total+T.jr_skipped;
  } // delay

  // -------------------------------------------------------------------------
  // From the speaker to the loudspeaker
  // -------------------------------------------------------------------------

  /**
   * Turns the writes a run made into the list of pulse lengths the svision
   * handlers play: how long the speaker stayed where it was, starting from
   * down — which is where a ZX Spectrum's speaker sits when nothing is playing.
   *
   * A write of the value the speaker already holds is not an edge and makes no
   * pulse. That happens for real: the music player writes zero at the top of
   * every cycle, and on the very first one the speaker is already at zero.
   *
   * @param {Object} run - What effect() or tune() returned.
   * @returns {Array} Pulse lengths in T-states, the first at speaker down.
   */
  static pulses(run) {
    const lengths = [];
    let level = 0;
    let last = 0;
    run.writes.forEach((write) => {
      const value = (write.value & 0x10) ? 1 : 0;
      if (value === level) { return; }
      lengths.push(write.t-last);
      last = write.t;
      level = value;
    });
    if (run.tstates > last) { lengths.push(run.tstates-last); }
    return lengths;
  } // pulses

  /**
   * And those pulse lengths in the shape the svision pulse handlers take.
   * Rounding is carried from one pulse to the next rather than done on each,
   * so a long tune does not drift away from the original's clock.
   *
   * ★ The svision processor plays the **first** fragment with the speaker up,
   * and `pulses()` begins with the speaker down: its first length is the lead
   * from the routine's entry to the first OUT. So the lead is not a fragment;
   * it only moves the clock. A run with no OUT at all — a footstep that is
   * not the eighth — is one lead and nothing else, and that is no sound:
   * played as a fragment it would be one or two samples at full volume, a
   * click on every frame Sabreman walks (audible on an iPhone speaker,
   * 2026-09-10).
   *
   * @param {Array} lengths - Pulse lengths in T-states, the first of them low.
   * @param {number} sampleRate - The audio context's sample rate.
   * @param {number} volume - Bus volume level.
   * @returns {Object|boolean} svision pulse data {fragments, pulses, volume},
   *          or false when the speaker never moves.
   */
  static audioData(lengths, sampleRate, volume) {
    if (lengths.length < 2) {
      return false;
    }
    const fragments = [];
    const index = new Map();
    const pulses = [];
    let tstates = lengths[0];
    let written = Math.round(tstates*sampleRate/CLOCK);
    for (let i = 1; i < lengths.length; i++) {
      tstates += lengths[i];
      const target = Math.round(tstates*sampleRate/CLOCK);
      const samples = Math.max(1, target-written);
      written += samples;
      if (!index.has(samples)) {
        index.set(samples, fragments.length);
        fragments.push(samples);
      }
      pulses.push(index.get(samples));
    }
    return {fragments: fragments, pulses: pulses, volume: volume};
  } // audioData


} // class Beeper
