const { AbstractAudioManager } = await import('./svision/js/audio/abstractAudioManager.js?ver='+window.srcVersion);
const { AudioWorkletHandler } = await import('./svision/js/audio/audioWorkletHandler.js?ver='+window.srcVersion);
const { AudioScriptProcessorHandler } = await import('./svision/js/audio/audioScriptProcessorHandler.js?ver='+window.srcVersion);
const { AudioSilentHandler } = await import('./svision/js/audio/audioSilentHandler.js?ver='+window.srcVersion);
const { Tool } = await import('./svision/js/tool.js?ver='+window.srcVersion);
const { ZXMachineSounds } = await import('./svision/js/platform/canvas2D/zx/zxMachineSounds.js?ver='+window.srcVersion);
const { ZXVideoRAM } = await import('./svision/js/platform/canvas2D/zx/zxVideoRAM.js?ver='+window.srcVersion);
const { Beeper } = await import('./beeper.js?ver='+window.srcVersion);
// begin code

/**
 * Audio manager. The original has a one-bit beeper on bit 4 of port $FE and no
 * sound chip, so every sound is a stream of pulse lengths played by the svision
 * pulse handlers — the same way the machine makes sound, not sampled.
 *
 * There is **one bus**, `sounds`, and the music goes over it too (decided
 * 2026-09-07). ★ Sabre Wulf really does have music (MusicData_GameInitialisation,
 * _Poem, _GameOver, _GameComplete, played by PlaySquareWave / PlayWaveSequence;
 * ZXDB names Bach, BWV 846), but a bus plays one sound at a time and the
 * original never plays a tune and a game sound together: every tune runs with
 * the interrupts disabled, while the game stands still. The remake keeps that
 * order (RoomModel holds the worker until the start-of-life tune is over), so
 * the four tunes and the game's sounds share the bus without cutting each
 * other, and the one AudioContext is one less to lose on iOS.
 *
 * ★ Since M6 the game's own audio is here, and none of it is invented: every
 * sound is one of the ten routines of the original run instruction by
 * instruction in app/beeper.js (data/sounds.json, data/music.json), and
 * tools/matchsound.js checks the pulses it produces against what the original
 * writes to port $FE — 63 038 checks, zero differences. The other bus still
 * carries the sounds of the **machine**, the tape loading show and the ROM's
 * key click and rising scale (svision ZXMachineSounds).
 *
 * A frame's sounds are played as **one** stream, laid end to end, because that
 * is what the machine does: there is one speaker and one bit, and each of the
 * game's handlers holds it for as long as it takes before the next one gets
 * it.
 */
export class AudioManager extends AbstractAudioManager {

  constructor(app) {
    super(app);
    this.id = 'AudioManager';
    this.volume = {};
    this.volume.sounds = Math.min(10, Math.max(0, Math.round(Number(Tool.readCookie('audioBusSoundsLevel', 5)))));
    this.beeper = null;
    // $96B3 — the footstep counter. It belongs to the sound and to nothing
    // else ($BF54 is the only routine that touches it), so the worker does not
    // carry it; it lives here.
    this.stepCounter = 0;
  } // constructor

  /**
   * Builds the beeper out of the data files, once they have arrived.
   * @returns {Beeper|null} The beeper, or null while there is no data.
   */
  getBeeper() {
    if (this.beeper === null) {
      // not kept while there is none: the next model may have it from the
      // server (R-062)
      var sounds = this.loadDataFile('sounds');
      var music = this.loadDataFile('music');
      this.beeper = (sounds && music) ? new Beeper(sounds, music) : null;
    }
    return this.beeper;
  } // getBeeper

  /**
   * Reads a data file delivered with appData; see {@link Tool.loadDataFile}.
   * @param {string} key - The data file name without its extension.
   * @returns {Object|null} The parsed content, or null.
   */
  loadDataFile(key) {
    // through the model: a file its loadDataFiles() had to get from the
    // server is there, not in localStorage (R-062)
    var model = this.app.model;
    return model && model.loadDataFile ? model.loadDataFile(key) : Tool.loadDataFile(key);
  } // loadDataFile

  /**
   * The tape block that carries the loading screen — the real 6912 bytes of
   * it (data/loading.json), bit by bit in the pulse format of the tape, with
   * an event after every byte and one more when the block ends.
   *
   * TapeLoadingModel writes each of those bytes into the video memory as it
   * arrives, so the picture is not an animation of a load: it **is** the load,
   * and it takes exactly as long as the sound does.
   *
   * The pulses are the ROM's own lengths, so the block takes as long as
   * 6912 bytes really take — some thirty-seven seconds. Nothing is sped up:
   * a picture that loads faster than the tape can carry it would be an
   * animation again, which is the one thing this is not.
   *
   * @param {number} sampleRate - The audio context sample rate.
   * @param {number} level - Bus volume level.
   * @returns {Object|boolean} svision pulse data, or false with no data file.
   */
  tapeScreenDataSound(sampleRate, level) {
    var loading = this.loadDataFile('loading');
    if (!loading) {
      return false;
    }
    return ZXMachineSounds.tapeData(sampleRate, level,
      ZXVideoRAM.decode(loading.videoRAM),
      {byteEvent: 'tapeByte', endEvent: 'tapeBlockEnd'});
  } // tapeScreenDataSound

  createAudioHandler(bus, options) {
    var audioHandler = false;

    var volume = 0.0;
    switch (bus) {
      case 'sounds':
      case 'extra':
        volume = this.volumeLevel(this.volume.sounds);
        break;
    }

    if (options.audioSilentHandler != 'disable' && volume == 0.0) {
      return new AudioSilentHandler(this.app);
    }

    if (this.unsupportedAudioBus == false) {
      this.unsupportedAudioBus = Tool.readCookie('unsupportedAudioBus', false);
    }

    switch (this.unsupportedAudioBus) {
      case false:
        audioHandler = new AudioWorkletHandler(this.app);
        break;
      case 'AudioWorkletHandler':
        Tool.writeCookie('unsupportedAudioBus', 'AudioWorkletHandler');
        audioHandler = new AudioScriptProcessorHandler(this.app);
        break;
      case 'AudioScriptProcessorHandler':
        Tool.writeCookie('unsupportedAudioBus', 'AudioScriptProcessorHandler');
        audioHandler = new AudioSilentHandler(this.app);
        break;
    }

    if (bus in this.restartSounds) {
      this.app.model.sendEvent(1, {id: 'playSound', bus: bus, sound: this.restartSounds[bus].sound, options: this.restartSounds[bus].options});
    }

    return audioHandler;
  } // createAudioHandler

  audioData(bus, sound, options) {
    var data = super.audioData(bus, sound, options);
    if (data !== false) {
      return data;
    }

    var sampleRate = this.getSampleRate();
    var level = this.volumeLevel(this.volume.sounds);
    switch (sound) {
      case 'tapePilotToneSound': return ZXMachineSounds.tapePilotTone(sampleRate, level);
      case 'tapeRndDataSound': return ZXMachineSounds.tapeRndData(sampleRate, level);
      case 'tapeScreenDataSound': return this.tapeScreenDataSound(sampleRate, level);
      case 'keyboardSound': return ZXMachineSounds.keyClick(sampleRate, level);
    }
    var beeper = this.getBeeper();
    if (!beeper) {
      return false;
    }
    if (sound.substring(0, 6) === 'music:') {
      var tune = beeper.tune(sound.substring(6), options || {});
      return tune ? Beeper.audioData(Beeper.pulses(tune), sampleRate, level)
                  : false;
    }
    if (sound === 'frame') {
      // built in playFrame, so that a frame with nothing to hear sends nothing
      return (options && options.audioData) || false;
    }
    return false;
  } // audioData

  /**
   * The sounds of one tick, laid end to end — one speaker, one bit, one queue.
   * @param {Beeper} beeper - The beeper.
   * @param {Array} sounds - The `sounds` of the worker's frame message.
   * @param {number} sampleRate - The audio context sample rate.
   * @param {number} level - Bus volume.
   * @returns {Object|boolean} svision pulse data, or false when nothing sounds.
   */
  frameSound(beeper, sounds, sampleRate, level) {
    var lengths = [];
    for (var i = 0; i < sounds.length; i++) {
      var event = (typeof sounds[i] === 'string') ? {name: sounds[i]} : sounds[i];
      var params = event;
      if (event.name === 'step') {
        params = {counter: this.stepCounter, colour: event.colour};
      } else if (event.name === 'explosion') {
        params = {rom: AudioManager.explosionBytes(beeper, event)};
      }
      var run = beeper.effect(event.name, params);
      if (!run) {
        continue;
      }
      if (run.counter !== undefined) {
        this.stepCounter = run.counter;
      }
      var pulses = Beeper.pulses(run);
      // the first pulse of a run is the speaker sitting where it already is,
      // so it joins the silence the run before it ended on
      if (lengths.length && pulses.length) {
        lengths[lengths.length-1] += pulses.shift();
      }
      lengths = lengths.concat(pulses);
    }
    return lengths.length ? Beeper.audioData(lengths, sampleRate, level) : false;
  } // frameSound

  /**
   * The sixteen tone lengths of an explosion.
   *
   * ★ The original reads them out of the **ZX Spectrum ROM** at
   * ($9693 & $1F) * 256 + Rand8 ($BEEE), and the ROM is not in this project's
   * sources — the same hole as the map of objects in M4 and the phase of the
   * sword swing in M3. The rule is reproduced exactly, sixteen consecutive
   * bytes from one address; where the bytes come from is ours.
   * @param {Beeper} beeper - The beeper, for the routine's own constants.
   * @param {Object} event - {sweeps, rand} out of the worker.
   * @returns {Array} Sixteen bytes.
   */
  static explosionBytes(beeper, event) {
    var effect = beeper.effects.explosion;
    var base = ((event.sweeps|0) & effect.addressMask)*256+((event.rand|0) & 0xFF);
    var bytes = [];
    for (var i = 0; i < effect.tones; i++) {
      var mixed = (base+i)*2654435761 % 4294967296;
      bytes.push((mixed >>> 13) & 0xFF);
    }
    return bytes;
  } // explosionBytes

  volumeLevel(volume) {
    var levels = [0, 0.005, 0.01, 0.02, 0.04, 0.07, 0.1, 0.14, 0.18, 0.23, 0.29];
    return levels[volume];
  } // volumeLevel

  /**
   * One worker frame: what the game did in it, as sound.
   * @param {Object} frame - The 'frame' message from the worker.
   */
  playFrame(frame) {
    if (!frame || !frame.sounds || !frame.sounds.length) {
      return;
    }
    var beeper = this.getBeeper();
    if (!beeper) {
      return;
    }
    // ★ The sound is built here and not in audioData, because a frame's events
    // do not always make a sound: a footstep runs $BF4B on every frame Sabreman
    // moves, and only every eighth one reaches the speaker. The other seven
    // must send **nothing** — a bus does not take false for an answer, and a
    // one-pulse "sound" of the routine's silent lead is a click on every frame
    // (heard on an iPhone speaker, 2026-09-10). The step counter still counts
    // on all of them, as $96B3 does.
    var data = this.frameSound(beeper, frame.sounds, this.getSampleRate(),
                               this.volumeLevel(this.volume.sounds));
    if (data === false) {
      return;
    }
    this.playSound('sounds', 'frame', {sounds: frame.sounds, audioData: data});
  } // playFrame

  /**
   * One of the four tunes of the original, on the one bus.
   * @param {string} name - gameComplete, gameOver, poem or gameInitialisation.
   * @param {Object} [options] - `waitKey` for the menu's variant ($BD51).
   */
  playMusic(name, options) {
    this.playSound('sounds', 'music:'+name, options || {});
  } // playMusic

} // AudioManager
