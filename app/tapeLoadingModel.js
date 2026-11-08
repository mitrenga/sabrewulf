const { AbstractModel } = await import('./svision/js/abstractModel.js?ver='+window.srcVersion);
const { BorderEntity } = await import('./borderEntity.js?ver='+window.srcVersion);
const { ZXVideoRAMEntity } = await import('./svision/js/platform/canvas2D/zx/zxVideoRAMEntity.js?ver='+window.srcVersion);
const { ZXVideoRAM } = await import('./svision/js/platform/canvas2D/zx/zxVideoRAM.js?ver='+window.srcVersion);
const { TextEntity } = await import('./svision/js/platform/canvas2D/textEntity.js?ver='+window.srcVersion);
const { ZXColor } = await import('./svision/js/platform/canvas2D/zx/zxColor.js?ver='+window.srcVersion);
// begin code

/**
 * Loading from tape, the way the original does it: LOAD "" typed on the ZX
 * keyboard, the pilot tone and data stripes in the border, the header name and
 * then the loading screen — the real one off the original tape
 * (data/loading.json, verified byte for byte against the .scr from Spectrum
 * Computing and against what the tape loads into memory,
 * sources/docs/disasm_notes.md chap. 2).
 *
 * The picture is not revealed, it is **loaded**. The block that carries it is
 * not a noise that sounds like data: it is the 6912 bytes of the picture,
 * encoded bit by bit in the pulse format of the tape (audioManager's
 * `tapeScreenDataSound`). The sound sends an event after every byte it has
 * played and the model writes that byte into the video memory, so the picture
 * appears at the speed of the sound because it *is* the sound; a further event
 * when the block ends moves the tape on, so the two cannot drift apart.
 *
 * What it looks like falls out of the machine's memory layout rather than
 * being drawn to imitate it: the three thirds of the screen fill in the ULA's
 * interleaved order, every eighth pixel line first, and the 768 attribute
 * bytes come last, which is why the picture builds up black on white and only
 * then snaps into colour. See {@link ZXVideoRAMEntity}.
 *
 * Every block has its header in front of it, the way the ROM saves things:
 * the BASIC program, the picture, and then the code. Of the code only the
 * header and a few seconds of the block are played — then the tape stops and
 * the remake goes straight to its own menu.
 *
 * The tape is Speedlock ("hyperload") and the main block is **encrypted** —
 * negated from $6000 up, and the game decrypts itself with the routine at
 * $5B80 (disasm_notes.md chap. 1) — so what the loader itself did cannot be
 * replayed here. The blocks are the ROM's, at the ROM's speed, and only the
 * one with the picture in it carries real bytes. It is a show, not a claim —
 * but the picture in it is the real one, loaded, and it takes the thirty-seven
 * seconds 6912 bytes take.
 */
export class TapeLoadingModel extends AbstractModel {

  constructor(app) {
    super(app);
    this.id = 'TapeLoadingModel';

    this.inputLineEntity = null;
    this.commandPhase = 0;
    this.command = ['K', 'LOAD L', 'LOAD "L', 'LOAD ""L', ''];
    this.programNameEntity = null;
    this.screenEntity = null;
    this.app.stack.flashState = false;
    this.tapeBreak = false;
    // the line BREAK reports: 0:1 while the BASIC program is still coming,
    // 10:7 once it runs and is the one doing the loading
    this.tapeBreakLine = '0:1';
    this.tapePhase = false;
    this.tape = [
      {id: 'pause', duration: 1000},

      // BASIC program: header, then the block
      {id: 'pilot', duration: 3000},
      {id: 'data', duration: 100},
      {id: 'pause', duration: 800, event: {id: 'setProgramName'}},
      {id: 'pilot', duration: 1500},
      {id: 'data', duration: 1400},

      // the program runs: the screen goes blank and waits for the picture
      {id: 'pause', duration: 1000, event: {id: 'showLoadingScreen'}},

      // the picture: header, then the block that carries it; the block says
      // when it is over, the duration here is only the fallback for a bus
      // that never gets to play it
      {id: 'pilot', duration: 3000},
      {id: 'data', duration: 100},
      {id: 'pause', duration: 800},
      {id: 'pilot', duration: 1500},
      {id: 'data', duration: 60000, sound: 'tapeScreenDataSound'},

      // the code: header, then a while of the block — the real one is
      // Speedlock and cannot be replayed, so this is a show, cut short
      {id: 'pause', duration: 1000},
      {id: 'pilot', duration: 3000},
      {id: 'data', duration: 100},
      {id: 'pause', duration: 800},
      {id: 'pilot', duration: 1500},
      {id: 'data', duration: 5000}
    ];
  } // constructor

  init() {
    super.init();

    this.borderEntity.bkColor = ZXColor.white;
    this.desktopEntity.bkColor = ZXColor.white;

    // the data files: at once from localStorage, or from the server when
    // they are missing there (R-062)
    this.loadDataFiles(['loading'], (files, error) => this.initData(files, error));
  } // init

  /**
   * The part of init() that needs the data files. Runs inside init() when
   * they are in localStorage, later when they had to come from the server.
   * @param {Object|null} files - The data files, or null.
   * @param {Error} [error] - Why they are missing.
   */
  initData(files, error) {
    if (this.app.model !== this) {
      return;
    }
    if (!files) {
      this.app.showErrorMessage(error ? error.message : 'Game data could not be loaded.', 'restart');
    }
    this.inputLineEntity = new TextEntity(this.desktopEntity, this.app.fonts.zxFonts8x8Mono, 0, 23*8, 32*8, 8, '© 1982 Sinclair Research Ltd', ZXColor.black, false, {align: 'left'});
    this.desktopEntity.addEntity(this.inputLineEntity);

    this.programNameEntity = new TextEntity(this.desktopEntity, this.app.fonts.zxFonts8x8, 0, 1*8, 32*8, 8, 'Program: Sabrewulf', ZXColor.black, false, {leftMargin: 1});
    this.programNameEntity.hide = true;
    this.desktopEntity.addEntity(this.programNameEntity);

    this.sendEvent(0, {id: 'openAudioBus', bus: 'sounds', options: {}});
    this.sendEvent(1000, {id: 'updateCommand'});

    this.app.stack.flashState = false;
    this.sendEvent(330, {id: 'changeFlashState'});
  } // initData

  newBorderEntity() {
    // no X in the border, like the other screens: a click or a touch anywhere
    // in the border is BREAK (handleEvent), a second one goes back to the menu,
    // and Escape or GamepadExit go back straight away
    return new BorderEntity(false, false);
  } // newBorderEntity

  shutdown() {
    super.shutdown();
    this.sendEvent(0, {id: 'closeAllAudioBuses'});
  } // shutdown


  handleEvent(event) {
    if (super.handleEvent(event)) {
      return true;
    }

    switch (event.id) {

      case 'changeFlashState':
        this.app.stack.flashState = !this.app.stack.flashState;
        this.sendEvent(330, {id: 'changeFlashState'});
        return true;

      case 'updateCommand':
        this.inputLineEntity.options.align = 'left';
        this.inputLineEntity.fonts = this.app.fonts.zxFonts8x8Mono;
        this.inputLineEntity.options.animationMode = 'flashReverseColors';
        this.inputLineEntity.setText(this.command[this.commandPhase]);
        this.inputLineEntity.options.flashMask = '';
        if (this.command[this.commandPhase].length > 0) {
          this.inputLineEntity.options.flashMask = this.inputLineEntity.options.flashMask.padStart(this.command[this.commandPhase].length-1, ' ')+'#';
        }
        this.commandPhase++;
        this.sendEvent(0, {id: 'playSound', bus: 'sounds', sound: 'keyboardSound', options: false});
        if (this.commandPhase < this.command.length) {
          this.sendEvent(800, {id: 'updateCommand'});
        } else {
          this.inputLineEntity.hide = true;
          this.tapePhase = 0;
          this.sendEvent(1, {id: 'updateTape'});
        }
        return true;

      case 'updateTape':
        switch (this.tape[this.tapePhase].id) {
          case 'pilot':
            this.sendEvent(0, {id: 'playSound', bus: 'sounds', sound: 'tapePilotToneSound', options: {repeat: true}});
            this.sendEvent(0, {id: 'setBorderAnimation', value: 'pilotTone'});
            break;
          case 'data':
            this.sendEvent(0, {id: 'playSound', bus: 'sounds',
                               sound: this.tape[this.tapePhase].sound || 'tapeRndDataSound',
                               options: false});
            this.sendEvent(0, {id: 'setBorderAnimation', value: 'dataTone'});
            break;
          case 'pause':
            this.sendEvent(0, {id: 'stopAudioBus', bus: 'sounds'});
            this.sendEvent(0, {id: 'setBorderAnimation', value: false});
            break;
        }
        if ('event' in this.tape[this.tapePhase]) {
          this.sendEvent(0, this.tape[this.tapePhase].event);
        }
        this.tapePhase++;
        if (this.tapePhase < this.tape.length) {
          this.sendEvent(this.tape[this.tapePhase-1].duration, {id: 'updateTape'});
        } else {
          this.sendEvent(this.tape[this.tapePhase-1].duration, {id: 'setMenuModel'});
        }
        return true;

      case 'setProgramName':
        this.programNameEntity.hide = false;
        return true;

      case 'tapeByte':
        // one byte off the tape, straight into the video memory; the entity
        // repaints itself on the next frame and nothing else is needed
        if (this.screenEntity && !this.tapeBreak) {
          this.screenEntity.pokeOffset(event.data.at, event.data.value);
        }
        return true;

      case 'tapeBlockEnd':
        if (!this.tapeBreak) {
          this.cancelEvent('updateTape');
          this.sendEvent(0, {id: 'updateTape'});
        }
        return true;

      case 'showLoadingScreen':
        var loading = this.loadDataFile('loading');
        if (loading) {
          this.programNameEntity.destroy();
          this.programNameEntity = null;
          // empty video memory to begin with — white paper, black ink, the
          // state the machine is in when the header has gone by; the bytes
          // themselves arrive one at a time with the block that follows
          this.screenEntity = new ZXVideoRAMEntity(this.desktopEntity, 0, 0);
          this.screenEntity.clear(0, ZXVideoRAM.BLANK_ATTRIBUTE);
          // the lower screen — the two lines BASIC keeps for itself — is
          // black on black before the picture comes
          this.screenEntity.videoRAM.fillAttributes(
            {row: ZXVideoRAM.ROWS-2, col: 0, rows: 2, cols: ZXVideoRAM.COLS}, 0);
          this.screenEntity.invalidate();
          this.desktopEntity.addEntity(this.screenEntity);
          // the input line has to print over the picture when BREAK comes
          var entities = this.desktopEntity.entities;
          entities.push(entities.splice(entities.indexOf(this.inputLineEntity), 1)[0]);
          this.tapeBreakLine = '10:7';
          // and it prints the way the running program has the lower screen
          // set: white ink on black paper
          this.inputLineEntity.setPenColor(ZXColor.white);
          this.inputLineEntity.setBkColor(ZXColor.black);
          // BORDER 0 — the program sets the border black before it loads on
          this.borderEntity.bkColor = ZXColor.black;
          this.desktopEntity.bkColor = ZXColor.black;
        }
        return true;

      case 'setMenuModel':
        this.app.setModel('MenuModel');
        return true;

      case 'keyPress':
        switch (event.key) {
          case 'Escape':
          case 'GamepadExit':
            this.app.setModel('MenuModel');
            return true;
          case ' ':
          case 'Enter':
          case 'GamepadOK':
            if (this.break()) {
              return true;
            }
            break;
          case 'Mouse1':
          case 'Mouse2':
          case 'Mouse4':
            this.app.inputEventsManager.keysMap[event.key] = this.borderEntity;
            return true;
          case 'Touch':
            this.app.inputEventsManager.touchesMap[event.identifier] = this.borderEntity;
            return true;
        }
        break;

      case 'keyRelease':
        switch (event.key) {
          case 'Mouse1':
          case 'Mouse2':
          case 'Mouse4':
            if (this.app.inputEventsManager.keysMap[event.key] === this.borderEntity && this.break()) {
              return true;
            }
            return true;
          case 'Touch':
            if (this.app.inputEventsManager.touchesMap[event.identifier] === this.borderEntity && this.break()) {
              return true;
            }
            return true;
        }
        break;

      case 'errorAudioBus':
        this.app.showErrorMessage(event.error, 'reopen');
        return true;
    }

    return false;
  } // handleEvent

  /**
   * Stops the load the way BREAK does on the real machine, or leaves when the
   * tape is already past the point of no return.
   * @returns {boolean} True when the event was consumed.
   */
  break() {
    if (this.tapeBreak) {
      this.app.setModel('MenuModel');
      return true;
    }

    if (this.tapePhase !== false) {
      this.cancelEvent('updateTape');
      this.cancelEvent('setMenuModel');
      this.sendEvent(0, {id: 'stopAudioBus', bus: 'sounds'});
      this.tapeBreak = true;
      // whatever the tape has put into the video memory stays there; the
      // report is printed over it
      this.inputLineEntity.setText('D BREAK - CONT repeats, '+this.tapeBreakLine);
      this.inputLineEntity.hide = false;
      this.sendEvent(0, {id: 'setBorderAnimation', value: false});
      this.sendEvent(5000, {id: 'setMenuModel'});
      return true;
    }
    return false;
  } // break

  loopModel(timestamp) {
    super.loopModel(timestamp);

    this.drawModel();
  } // loopModel

} // TapeLoadingModel
