const { AbstractModel } = await import('./svision/js/abstractModel.js?ver='+window.srcVersion);
const { BorderEntity } = await import('./borderEntity.js?ver='+window.srcVersion);
const { TextEntity } = await import('./svision/js/platform/canvas2D/textEntity.js?ver='+window.srcVersion);
const { PauseGameEntity } = await import('./pauseGameEntity.js?ver='+window.srcVersion);
const { ZXColor } = await import('./svision/js/platform/canvas2D/zx/zxColor.js?ver='+window.srcVersion);
const { ScreenLayout } = await import('./screenLayout.js?ver='+window.srcVersion);
const { ScreenComposer } = await import('./screenComposer.js?ver='+window.srcVersion);
const { GameAreaEntity } = await import('./gameAreaEntity.js?ver='+window.srcVersion);
const { GameInfoEntity } = await import('./gameInfoEntity.js?ver='+window.srcVersion);
const { RoomComposer } = await import('./roomComposer.js?ver='+window.srcVersion);
// begin code

/**
 * The game screen: the panel on character rows 0-1 and one screen of the
 * jungle below it, the flick-screen layout of the original
 * (sources/docs/screen_layout.md).
 *
 * Since M2 the screen is **composed the way the game composes it**: the place
 * in the 16 x 16 grid picks a template out of Layout ($6066) and the template
 * is built from the 41 pieces of scenery (roomComposer.js, data/world.json,
 * data/rooms.json, data/scenery.json). That composition is byte for byte the
 * original's — tools/matchscreen.py checks all 256 screens against the game's
 * own DrawRoom running in a simulator, and tools/matchrooms.js checks this
 * very code against the same bytes. The panel is set in the character set the
 * game prints with. The worker (gameWorker.js, WORKER-PROTOCOL.md) ticks at
 * the original's 50.08 Hz and this model routes the controls to it and draws
 * what comes back.
 *
 * ★ The screen it starts on is measured, not chosen: $B21E copies 144 bytes
 * from $AC77 into the game status buffer at $9702 and the second byte of the
 * first record is the room — $A8, i.e. **column 8, row 10** of the grid. The
 * simulator confirms it independently ($9703 while playing).
 *
 * Since M3 **Sabreman walks in it**. The worker steps him with
 * sabremanPhysics.js — a transcription of the original's routines checked step
 * by step against recorded runs, 2 323 steps with zero differences — and sends
 * over the game's own entity record; this model routes the controls to it,
 * draws what comes back, and when the screen number in the record changes it
 * composes the new screen (setRoom). ★ The transitions are the original's,
 * including the one that snaps x to the corridor when leaving through the
 * bottom, because the vertical corridors are two pixels wide.
 *
 * In dev mode the held directions are printed in the top right corner, and
 * PHYSICS SANDBOX prints Sabreman's whole record along the bottom, so the
 * numbers the physics works in can be read while walking.
 */
export class RoomModel extends AbstractModel {

  constructor(app) {
    super(app);
    this.id = 'RoomModel';

    this.gameOver = false;
    // ms the worker waits after init() for the start-of-life tune (initScreen)
    this.holdForTune = 0;
    this.controlsState = {left: false, right: false, up: false, down: false,
                          sword: false};
    this.worker = null;
    this.render = null;
    this.roomData = null;
    this.worldData = null;
    this.sceneryData = null;
    this.roomsData = null;
    this.physicsData = null;
    this.entitiesData = null;
    this.monstersData = null;
    this.composer = null;
    this.currentRoom = null;
    this.recordEntity = null;
    this.place = null;
    this.gameAreaEntity = null;
    this.gameInfoEntity = null;
    this.pauseButtonEntity = null;
    this.fpsEntity = null;
    this.inputEntity = null;
    // display frames, worker messages and worker **ticks** (from the frame
    // counter the worker posts) per second; the ticks are the game's clock
    this.fps = {frames: 0, workerFrames: 0, ticks: 0, lastFrame: false, since: false};
    this.heldTaps = {};
  } // constructor

  newBorderEntity() {
    // no X in the border: the pause menu opens from the panel (pauseButton)
    return new BorderEntity(false, this.app.controls.touchscreen.supported);
  } // newBorderEntity

  init() {
    super.init();

    // ★ GameInitialisation ($9963) does XOR A / OUT ($FE),A, so the border is
    // black when the game starts. Whether it changes during play is still open
    // (ZADANI chap. 7).
    this.borderEntity.bkColor = ZXColor.black;
    this.desktopEntity.bkColor = ZXColor.black;

    // ★ the bus first, the screen after: initScreen() plays the start-of-life
    // tune, and playSound on a bus that is not open yet is dropped without a
    // word. The menu closes all buses (menuModel.js), and since 2026-09-07 the
    // game starts straight from the menu — the title screen that used to open
    // the bus on the way is gone.
    this.sendEvent(0, {id: 'openAudioBus', bus: 'sounds', options: {muted: this.app.muted.sounds}});

    // the data files: at once from localStorage, or from the server when
    // they are missing there (R-062)
    this.loadDataFiles(['world', 'scenery', 'rooms', 'physics', 'entities', 'monsters', 'text', 'music', 'sounds', 'sprites', 'spriteframes'].concat(this.app.roomName ? [this.app.roomName] : []), (files, error) => this.initData(files, error));
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
    if (!this.initScreen()) {
      this.desktopEntity.addEntity(new TextEntity(this.desktopEntity, this.app.fonts.zxFonts8x8, 0, 8*8, this.desktopWidth, 8, 'SABRE WULF', ZXColor.brightWhite, false, {align: 'center'}));
      this.desktopEntity.addEntity(new TextEntity(this.desktopEntity, this.app.fonts.fonts5x5, 8, 8*8+16, this.desktopWidth-16, 40,
        'SCREEN DATA MISSING (data/world.json, data/rooms.json, data/scenery.json). RUN tools/dumpworld.py, tools/dumprooms.py AND tools/dumpgfx.py.', ZXColor.brightGreen, false, {align: 'center', textWrap: true}));
      return;
    }

    if (this.app.devModeName !== false) {
      this.fpsEntity = new TextEntity(this.desktopEntity, this.app.fonts.fonts3x3, 16*8, 2, 10*8, 4, '', ZXColor.brightGreen, false, {align: 'right'});
      this.desktopEntity.addEntity(this.fpsEntity);
      this.inputEntity = new TextEntity(this.desktopEntity, this.app.fonts.fonts3x3, 16*8, 8, 10*8, 4, '', ZXColor.brightCyan, false, {align: 'right'});
      this.desktopEntity.addEntity(this.inputEntity);
    }
    // PHYSICS SANDBOX (M3): Sabreman's own record over the screen, so the
    // numbers the physics works in can be read while walking — the same
    // twelve bytes tools/physlog.py prints out of the original
    if (this.app.sandbox) {
      this.recordEntity = new TextEntity(this.desktopEntity, this.app.fonts.fonts5x5, 0, ScreenLayout.PLAY_Y+ScreenLayout.PLAY_HEIGHT-6, this.desktopWidth, 6, '', ZXColor.brightYellow, false, {align: 'center'});
      this.desktopEntity.addEntity(this.recordEntity);
    }

    this.showTouchIcons();

    this.worker = this.app.worker;
    this.app.inputEventsManager.sendEventsActiveKeys('Press');
    this.sendWorkerMessage({
      id: 'init',
      initData: {
        headless: false,
        players: this.app.players,
        lives: this.app.lives,
        hiScore: this.app.hiScore,
        scene: this.buildScene(),
        // the physics walks in the same data the screen is composed from,
        // because the collision asks the very list of pieces of scenery the
        // room is drawn from ($B873) — the four files are under 60 kB for all
        // 256 screens, so they go over whole rather than on demand
        physics: this.physicsData,
        // M4: the world — the orchid of every template, the four positions
        // objects can take in it, the eight ready-made sets the amulet is
        // hidden in and the table the percentage is read out of
        entities: this.entitiesData,
        // M5: nepřátelé – JumpTable, šestnáct druhů zvířat, jedenáct
        // nesmrtelných entit a bodování za ně
        monsters: this.monstersData,
        world: this.worldData,
        rooms: this.roomsData,
        scenery: this.sceneryData,
        // ★ the original seeds a turn from its own frame counter and from the
        // ZX ROM ($A2BD); the remake has neither, so the seed is where its
        // pseudo-random source starts. It is what makes the amulet lie
        // somewhere else in the next game.
        seed: (Date.now() & 0xFFFF)
      }
    });
    if (this.holdForTune) {
      // the original plays the start-of-life tune before the game loop begins
      this.sendWorkerMessage({id: 'pause'});
      this.sendEvent(this.holdForTune, {id: 'startAfterTune'});
    }

    this.app.stack.flashState = false;
    this.sendEvent(330, {id: 'changeFlashState'});
  } // initData

  shutdown() {
    super.shutdown();
    this.sendWorkerMessage({id: 'reset'});
    this.sendEvent(0, {id: 'stopAllAudioBuses'});
  } // shutdown


  /**
   * Builds the renderer and adds the panel and the screen.
   * @returns {boolean} True when the screen was created.
   */
  initScreen() {
    this.worldData = this.loadDataFile('world');
    this.sceneryData = this.loadDataFile('scenery');
    this.roomsData = this.loadDataFile('rooms');
    this.physicsData = this.loadDataFile('physics');
    this.entitiesData = this.loadDataFile('entities');
    this.monstersData = this.loadDataFile('monsters');
    var scenery = this.sceneryData, rooms = this.roomsData;
    if (this.worldData && scenery && rooms) {
      try {
        this.composer = new RoomComposer(scenery, rooms);
      } catch (error) {
        console.error(error.message);
      }
    }
    this.poemUntil = false;
    this.pauseBorder = false;
    this.textData = this.loadDataFile('text');
    this.musicData = this.loadDataFile('music');
    this.place = this.startPlace();
    this.roomData = this.composer && this.place
      ? this.composer.composeRoom(this.worldData, this.place.column, this.place.row)
      : null;
    if (!this.roomData) {
      // fallback: the single screen M1 pulled out of a running original by
      // majority vote (data/room000.json, tools/mkroom.py). It is the same
      // screen — template $08 — which is how the composition was first
      // cross-checked, so it is worth keeping as a spare.
      this.roomData = this.loadDataFile(this.app.roomName);
    }
    if (!this.roomData) {
      return false;
    }
    try {
      // the glyphs come out of svision's ZXFonts8x8, whose default table is
      // the ZX ROM font — which is the font the game prints with
      // (screenComposer.js, tools/matchpanel.py)
      var fonts = this.app.fonts.zxFonts8x8Mono;
      this.render = new ScreenComposer(this.roomData,
                                     {chars: fonts.fontsChars, data: fonts.fontsData},
                                     this.loadDataFile('sprites'),
                                     this.loadDataFile('spriteframes'));
    } catch (error) {
      console.error(error.message);
      return false;
    }
    this.gameInfoEntity = new GameInfoEntity(this.desktopEntity, 0, 0, this.render);
    this.desktopEntity.addEntity(this.gameInfoEntity);
    // the pause menu opens from the panel, where the original has 2UP
    this.pauseButtonEntity = GameInfoEntity.pauseButton(this);
    this.gameAreaEntity = new GameAreaEntity(this.desktopEntity, 0, ScreenLayout.PLAY_Y, this.render);
    this.desktopEntity.addEntity(this.gameAreaEntity);
    this.gameInfoEntity.setPanel({score: this.app.score, score2: this.app.score2,
                                  hiScore: this.app.hiScore, lives: this.app.lives});
    this.currentRoom = this.place ? ((this.place.row << 4) | this.place.column) : null;
    // ★ a hudba, kterou originál pouští na začátku kola: $99A1 pošle
    // MusicData_GameInitialisation do PlayAudio ($BD6E) – jedenáct not, 2,4 s,
    // a hraje se se zakázaným přerušením, takže hra při ní stojí – a teprve
    // **po ní** začne smyčka s GameDelayTimer a jejím ťukáním. Worker se proto
    // po init() drží pozastavený a rozjede se událostí startAfterTune, až
    // melodie dohraje (data/music.json, app/beeper.js). Do 2026-09-07 hrála
    // melodie a prodleva naráz, na jedné sběrnici by ťuknutí melodii uřízlo.
    if (this.app.audioManager) {
      this.app.audioManager.playMusic('gameInitialisation');
    }
    var tune = this.musicData && this.musicData.tunes
      ? this.musicData.tunes.gameInitialisation.duration : 2.363;
    this.holdForTune = Math.round(tune*1000);
    return true;
  } // initScreen

  /**
   * ★ The screen a piece of the amulet buys: the picture of the amulet with
   * the pieces already found lit up, one verse of the poem, and the music.
   *
   * All three are the original's. $A207 clears the play area and draws the
   * four pieces out of the table at $C374 — each has **two blocks of
   * attributes** and $96B2 picks the bright one for a piece already found —
   * and $A234 prints the verse, plays MusicData_Poem and waits eight rounds
   * of $A1FF so the player can read it (data/text.json, tools/dumptext.py).
   *
   * ★ And it is **one** verse, not all the ones so far: DisplayPoem ($A01B)
   * counts the pieces and jumps to the single verse that matches, which is a
   * correction of what M4 wrote down.
   * @param {number} pieces - The amulet bits, $970D.
   */
  showPoem(pieces) {
    var text = this.textData;
    if (!text || !text.poem || !this.composer || !this.render) {
      return;
    }
    this.sendWorkerMessage({id: 'pause'});
    this.poemReturnRoom = this.currentRoom;
    this.composer.clear();
    text.amulet.pieces.forEach((entry, index) => {
      var graphic = text.amulet.graphics[entry.graphic];
      var found = (pieces >> index) & 1;
      this.composer.drawPiece({
        width: graphic.width, height: graphic.height,
        attrRows: graphic.attrRows, attrCols: graphic.attrCols,
        bitmap: RoomComposer.decode(graphic.bitmap),
        attributes: RoomComposer.decode(found ? graphic.attributes
                                              : graphic.attributesDull)
      }, entry.x, entry.y);
    });
    this.render.setRoom(this.composer.playArea());
    this.currentRoom = null;                    // the room has to be redrawn
    var count = 0;
    for (var bit = 0; bit < text.poem.pieces; bit++) {
      count += (pieces >> bit) & 1;
    }
    // $A028: the chain of DEC A / JR Z does not catch zero, so no pieces at
    // all would get the fourth verse — it cannot happen in play, but that is
    // what the code says
    var stanza = text.poem.stanzas[(count >= 1 && count <= 3)
                                   ? count-1 : text.poem.stanzas.length-1];
    if (this.gameAreaEntity) {
      this.gameAreaEntity.setFrame({texts: stanza.lines});
    }
    if (this.app.audioManager) {
      this.app.audioManager.playMusic('poem');
    }
    var tune = this.musicData && this.musicData.tunes
      ? this.musicData.tunes.poem.duration : 4.3;
    var wait = Math.round((tune+text.poem.pauseRounds*65536*26/3500000)*1000);
    this.poemUntil = true;
    this.cancelEvent('endPoem');
    this.sendEvent(wait, {id: 'endPoem'});
  } // showPoem

  /**
   * Swaps the screen after a flick-screen transition.
   *
   * ★ The transition itself is the original's: walking off an edge changes the
   * screen number and puts Sabreman on the far side of the new one, and going
   * out through the bottom even snaps his x to where the corridor through the
   * top of the new screen is (a 48 byte table at $6036 — the vertical
   * corridors are two pixels wide). All of that is in sabremanPhysics.js and
   * checked against the original; this only redraws.
   * @param {number} room - The screen number, row<<4 | column.
   */
  setRoom(room) {
    if (!this.composer || !this.render || room === this.currentRoom) {
      return;
    }
    var composed = this.composer.composeRoom(this.worldData, room & 0x0F, room >> 4);
    if (!composed) {
      return;
    }
    this.currentRoom = room;
    this.render.setRoom(composed);
    if (this.gameAreaEntity) {
      this.gameAreaEntity.cleanCache();
    }
  } // setRoom

  /**
   * Where in the 16 x 16 grid to start: the place picked on the map when there
   * is one, otherwise the game's own starting screen out of data/world.json
   * (★ column 8, row 10, read from $AC77 and confirmed by simulation).
   * @returns {Object|null} {column, row}.
   */
  startPlace() {
    var pick = this.app.trainingRoom;
    if (pick && typeof pick.column === 'number' && typeof pick.row === 'number') {
      return {column: pick.column, row: pick.row};
    }
    var start = this.worldData && this.worldData.start;
    return start ? {column: start.column, row: start.row} : null;
  } // startPlace

  /**
   * Which screen the game starts on.
   * @returns {Object} The scene block of the init message.
   */
  buildScene() {
    return {
      room: this.app.roomName,
      column: this.place ? this.place.column : null,
      row: this.place ? this.place.row : null
    };
  } // buildScene

  sendWorkerMessage(event) {
    if (this.worker) {
      this.worker.postMessage(event);
    }
  } // sendWorkerMessage

  /**
   * Sets one control and sends the whole state to the worker when it changed.
   * Eight-way movement means two directions can be held at once, so the whole
   * state goes over rather than the change ("Full 8 Way Movement" on the box).
   * @param {string} action - The control action.
   * @param {boolean} value - Pressed or released.
   */
  setControl(action, value) {
    if (!(action in this.controlsState) || this.controlsState[action] === value) {
      return;
    }
    this.controlsState[action] = value;
    this.sendWorkerMessage(Object.assign({id: 'controls'}, this.controlsState));
  } // setControl

  handleWorkerMessage(event) {
    var data = event.data;
    switch (data.id) {
      case 'frame':
        this.fps.workerFrames++;
        if (this.fps.lastFrame !== false && data.frame > this.fps.lastFrame) {
          this.fps.ticks += data.frame-this.fps.lastFrame;
        }
        this.fps.lastFrame = data.frame;
        this.app.score = data.score;
        this.app.score2 = data.score2;
        this.app.hiScore = data.hiScore;
        this.app.lives = data.lives;
        this.app.player = data.player;
        // M4: the percentage GAME OVER prints, and which pieces of the amulet
        // the player has
        this.app.percent = data.percent || 0;
        this.app.amulet = data.amulet || 0;
        if (data.sabreman) {
          this.setRoom(data.sabreman.room);
        }
        if (this.gameAreaEntity) {
          this.gameAreaEntity.setFrame(data);
        }
        if (this.recordEntity && data.sabreman) {
          var who = data.sabreman;
          this.recordEntity.setText(
            'SPR ' + ScreenComposer.hex(who.sprite)
            + '  SCR ' + ScreenComposer.hex(who.room)
            + ' (' + who.column + ',' + who.row + ')'
            + '  X ' + who.x + ' Y ' + who.y
            + '  DX ' + who.dx + ' DY ' + who.dy
            + (who.state ? '  STATE ' + ScreenComposer.hex(who.state) : '')
            // M4: barva je účinek orchideje, `EFF` je jeho odpočet ($96B0),
            // `AMU` sebrané kusy amuletu a `%` procento obrazovek
            + '  COL ' + ScreenComposer.hex(who.colour)
            + (data.effect ? ' EFF ' + ScreenComposer.hex(data.effect) : '')
            + '  AMU ' + (data.amulet || 0)
            + '  ' + (data.percent || 0) + '%');
        }
        if (this.gameInfoEntity) {
          this.gameInfoEntity.setPanel({score: data.score, score2: data.score2,
                                        hiScore: data.hiScore, lives: data.lives,
                                        player: data.player, labelFlash: !!data.labelFlash});
        }
        if (this.inputEntity && data.controls) {
          var held = Object.keys(data.controls).filter((key) => data.controls[key]);
          this.inputEntity.setText(held.length ? held.join(' ').toUpperCase() : '-');
        }
        if (data.sounds && data.sounds.length && this.app.audioManager) {
          this.app.audioManager.playFrame(data);
        }
        // ★ a kus amuletu otevře **sloku básně**: $A18C skočí na $A207, ten
        // smaže plochu, nakreslí obrázek amuletu a $A234 vytiskne sloku,
        // pustí MusicData_Poem a nechá to chvíli být
        if (data.poem && !this.poemUntil) {
          this.showPoem(data.poem);
        }
        break;
      case 'gameOver':
        if (!this.gameOver) {
          this.gameOver = true;
          this.app.score = data.score;
          this.app.complete = !!data.complete;
          this.app.setModel('GameOverModel');
        }
        break;
      case 'error':
        console.error(data.message);
        break;
    }
  } // handleWorkerMessage

  /**
   * Maps a key or gamepad event onto a control action.
   *
   * The keyboard keys are **only** the configured ones (`app.controls.keyboard`
   * — arrows and SPACE by default, remapped from SETTINGS); nothing is
   * accepted beside them, so a remapped key never keeps a hidden second
   * meaning. The gamepad keys are the fixed names the library gives its
   * buttons. The mouse is not a game control here — it serves the buttons and
   * the menu. The original is played on Q W E R T — Q left, W right, E up,
   * R down, T the combat button (ZADANI chap. 1); whoever wants that sets it.
   * @param {string} key - The event key.
   * @returns {string|false} The action, or false.
   */
  controlAction(key) {
    var kb = this.app.controls.keyboard;
    switch (key) {
      case kb.left: case 'GamepadLeft': return 'left';
      case kb.right: case 'GamepadRight': return 'right';
      case kb.up: case 'GamepadUp': case 'GamepadJump': return 'up';
      case kb.down: case 'GamepadDown': return 'down';
      case kb.sword: case 'GamepadFire': case 'GamepadOK': return 'sword';
    }
    return false;
  } // controlAction

  handleEvent(event) {
    if (super.handleEvent(event)) {
      return true;
    }

    switch (event.id) {

      case 'changeFlashState':
        this.app.stack.flashState = !this.app.stack.flashState;
        this.sendEvent(330, {id: 'changeFlashState'});
        return true;

      case 'exitGame':
        this.app.setModel('MenuModel');
        return true;

      case 'blurWindow':
        this.pauseGame();
        return true;

      case 'endPoem':
        // $A248: the play area is cleared and the room drawn again, the way
        // the game comes back from the poem
        this.poemUntil = false;
        if (this.gameAreaEntity) {
          this.gameAreaEntity.setFrame({});
        }
        if (this.poemReturnRoom !== null && this.poemReturnRoom !== undefined) {
          this.setRoom(this.poemReturnRoom);
        }
        this.sendWorkerMessage({id: 'continue'});
        return true;

      case 'startAfterTune':
        // the start-of-life tune is over: the game may begin — unless the
        // player has paused it meanwhile, then the pause panel starts it
        this.holdForTune = 0;
        if (!this.desktopEntity.modalEntity && !this.gameOver) {
          this.sendWorkerMessage({id: 'continue'});
        }
        return true;

      case 'continueGame':
        this.stopPauseBorder();
        this.sendWorkerMessage({id: 'continue'});
        this.sendEvent(0, {id: 'continueAllAudioBuses'});
        return true;

      case 'pauseBorder':
        if (!this.pauseBorder) {
          return true;
        }
        if (this.borderEntity) {
          this.borderEntity.bkColor =
            ZXColor.color(this.pauseBorder.colours[this.pauseBorder.phase]);
        }
        this.pauseBorder.phase = 1-this.pauseBorder.phase;
        this.sendEvent(Math.round(this.pauseBorder.frames*1000/50.08),
                       {id: 'pauseBorder'});
        return true;

      case 'releaseTouchAction':
        if (this.heldTaps[event.action]) {
          this.heldTaps[event.action]--;
        }
        this.releaseTouchAction(event.action);
        return true;

      case 'keyPress':
        var key = event.key;
        if (key.length == 1) {
          key = key.toUpperCase();
        }
        switch (key) {
          // ★ The original pauses on CAPS SHIFT or SPACE/BREAK ("Continuous
          // Pause" on the inlay), but the remake's pause panel is bound to
          // Escape, as in the sibling remakes.
          case 'Escape':
          case 'GamepadExit':
            this.pauseGame();
            return true;
          case 'Touch':
            if (this.borderEntity.leftControlEntity && this.borderEntity.leftControlEntity.pointOnEntity(event)) {
              this.app.inputEventsManager.touchesMap[event.identifier] = this.borderEntity.leftControlEntity;
              this.touchStart(event, 'left', this.borderEntity.leftControlEntity);
              return true;
            }
            if (this.borderEntity.rightControlEntity && this.borderEntity.rightControlEntity.pointOnEntity(event)) {
              this.app.inputEventsManager.touchesMap[event.identifier] = this.borderEntity.rightControlEntity;
              this.touchStart(event, 'right', this.borderEntity.rightControlEntity);
              return true;
            }
            break;
          case 'RetryTouch':
            this.setControl(event.action, true);
            return true;
          case this.app.controls.keyboard.sounds:
            this.app.muted.sounds = !this.app.muted.sounds;
            this.sendEvent(0, {id: 'muteAudioBus', bus: 'sounds', muted: this.app.muted.sounds});
            return true;
        }
        var action = this.controlAction(key);
        if (action !== false) {
          this.setControl(action, true);
          return true;
        }
        break;

      case 'keyRelease':
        var releasedKey = event.key;
        if (releasedKey.length == 1) {
          releasedKey = releasedKey.toUpperCase();
        }
        if (releasedKey == 'Touch') {
          this.touchEnd(event);
          return true;
        }
        var releasedAction = this.controlAction(releasedKey);
        if (releasedAction !== false) {
          this.setControl(releasedAction, false);
          return true;
        }
        break;

      case 'keyMove':
        if (event.key == 'Touch') {
          this.touchMove(event);
          return true;
        }
        break;

      case 'errorAudioBus':
        this.app.showErrorMessage(event.error, 'reopen');
        return true;
    }

    return false;
  } // handleEvent

  /** pauses the worker and opens the pause menu */
  pauseGame() {
    if (this.desktopEntity.modalEntity || this.gameOver) {
      return;
    }
    this.sendWorkerMessage({id: 'pause'});
    this.sendEvent(0, {id: 'pauseAllAudioBuses'});
    this.desktopEntity.addModalEntity(new PauseGameEntity(this.desktopEntity, 52, 34, 153, 97, 'PAUSE GAME', 'MenuModel'));
    this.startPauseBorder();
  } // pauseGame

  /**
   * ★ The one thing Sabre Wulf does with the border — and M6 measured it.
   *
   * The border is black for the whole game ($9963 does XOR A / OUT ($FE),A at
   * GameInitialisation and nothing ever writes a colour to that port again;
   * the sound routines only knock it back to black). The single exception is
   * the **pause**: $AC40 adds $04 to a counter every frame and makes the
   * colour out of bit 7 of it, so the border alternates blue and magenta every
   * 32 frames until SPACE is pressed again, and $AC67 puts it back to black
   * (data/global.json `border`, tools/mkglobal.py).
   */
  startPauseBorder() {
    var border = (this.app.globalData && this.app.globalData.border) || {};
    this.pauseBorder = {
      colours: border.pauseColours || [1, 3],
      frames: border.pauseFrames || 32,
      phase: 0
    };
    this.handleEvent({id: 'pauseBorder'});
  } // startPauseBorder

  /** and back to black, the way $AC67 does it */
  stopPauseBorder() {
    if (!this.pauseBorder) {
      return;
    }
    this.pauseBorder = false;
    this.cancelEvent('pauseBorder');
    if (this.borderEntity) {
      this.borderEntity.bkColor = ZXColor.black;
    }
  } // stopPauseBorder

  // -------------------------------------------------------- touch controls

  /**
   * What this half of the screen does: an eight-way stick or the sword
   * (controlsOptions.touchscreen.halves). Which half is which is the
   * left-handed / right-handed choice in SETTINGS.
   * @param {string} side - 'left' or 'right'.
   * @returns {Object} {icon, zones}
   */
  touchHalf(side) {
    var ts = this.app.controlsOptions.touchscreen;
    return ts.halves[ts.types[this.app.controls.touchscreen.type][side].half];
  } // touchHalf

  /**
   * Icons into the border: what each half of the screen does. The border draws
   * them only where there is room for them outside the play area.
   */
  showTouchIcons() {
    if (!this.app.controls.touchscreen.supported || !this.borderEntity) {
      return;
    }
    var icons = this.app.controlsOptions.touchscreen.icons;
    this.borderEntity.setGameControlIcons(icons[this.touchHalf('left').icon],
                                          icons[this.touchHalf('right').icon]);
  } // showTouchIcons

  /**
   * The zone of the layout under the finger. `rect` is a fraction of the half,
   * so it is worked out from where on that half the finger is, not from pixels.
   * @param {Object} event - The touch event (x, y).
   * @param {string} side - 'left' or 'right'.
   * @param {Object} entity - The half of the screen (borderEntity).
   * @returns {Object|false} The zone, or false.
   */
  touchZone(event, side, entity) {
    var half = this.touchHalf(side);
    var width = Math.max(entity.width, 1), height = Math.max(entity.height, 1);
    var rx = (event.x-(entity.parentX+entity.x))/width;
    var ry = (event.y-(entity.parentY+entity.y))/height;
    for (var z = 0; z < half.zones.length; z++) {
      var r = half.zones[z].rect;
      if (rx >= r[0] && rx <= r[0]+r[2] && ry >= r[1] && ry <= r[1]+r[3]) {
        return half.zones[z];
      }
    }
    return false;
  } // touchZone

  /**
   * A new touch on a half of the screen. There can be several at once: each
   * keeps its own record in `touchesGameControls` and the control state is
   * their sum, so walking and swinging the sword go together — and so do two
   * directions at once, which is what eight-way movement means.
   * @param {Object} event - The touch event.
   * @param {string} side - 'left' or 'right'.
   * @param {Object} entity - The half of the screen.
   */
  touchStart(event, side, entity) {
    var zone = this.touchZone(event, side, entity);
    var control = {side: side, entity: entity, action: false,
                   type: zone === false ? 'none' : zone.type,
                   control: zone === false ? false : zone.control,
                   actions: zone === false ? false : zone.actions,
                   tap: zone !== false && zone.type == 'button' && !!zone.tap,
                   since: this.app.now,
                   origin: {x: event.x, y: event.y},
                   at: {x: event.x, y: event.y}};
    this.app.inputEventsManager.touchesGameControls[event.identifier] = control;
    // A button holds its action from the moment the finger lands; the stick
    // does nothing until the finger moves, so a tap on it sends nothing.
    if (zone !== false && zone.type == 'button') {
      control.action = zone.action;
      this.setControl(zone.action, true);
    }
  } // touchStart

  /**
   * The finger came up. A short tap has to be **held**: the worker reads the
   * controls once per pass of the main loop (50.08 Hz), so a tap shorter than
   * one pass would never be seen at all.
   * @param {Object} event - The touch event.
   */
  touchEnd(event) {
    var controls = this.app.inputEventsManager.touchesGameControls;
    var control = controls[event.identifier];
    if (control === undefined) {
      return;
    }
    delete controls[event.identifier];
    if (control.action === false) {
      return;
    }
    var rest = this.app.controlsOptions.touchscreen.tapHoldTime-(this.app.now-control.since);
    if (control.tap && rest > 0) {
      this.heldTaps[control.action] = (this.heldTaps[control.action] || 0)+1;
      this.sendEvent(rest, {id: 'releaseTouchAction', action: control.action});
      return;
    }
    [].concat(control.action).forEach((action) => this.releaseTouchAction(action));
  } // touchEnd

  /**
   * Releases an action, but only when no other finger is still holding it —
   * two fingers on the same action must not cancel each other.
   * @param {string} action - The control action.
   */
  releaseTouchAction(action) {
    if (this.heldTaps[action]) {
      return;
    }
    var controls = this.app.inputEventsManager.touchesGameControls;
    var held = Object.keys(controls).some((id) => controls[id].action !== false
                                                  && [].concat(controls[id].action).indexOf(action) !== -1);
    if (!held) {
      this.setControl(action, false);
    }
  } // releaseTouchAction

  /**
   * The finger moved. The stick is **absolute**: the direction is where the
   * finger has moved to from where it landed, with a dead zone of
   * `joystickStep` in the middle. It holds two directions at once, because
   * the original walks in eight directions and a diagonal is two of them.
   * @param {Object} event - The touch event.
   */
  touchMove(event) {
    var controls = this.app.inputEventsManager.touchesGameControls;
    var control = controls[event.identifier];
    if (control === undefined || control.type != 'joystick') {
      return;
    }
    control.at = {x: event.x, y: event.y};
    var step = this.app.controlsOptions.touchscreen.joystickStep;
    var axis = {x: false, y: false};
    if (control.control == 'horizontal' || control.control == 'both') {
      if (event.x-control.origin.x < -step) { axis.x = control.actions.left; }
      if (event.x-control.origin.x > step) { axis.x = control.actions.right; }
    }
    if (control.control == 'vertical' || control.control == 'both') {
      if (event.y-control.origin.y < -step) { axis.y = control.actions.up; }
      if (event.y-control.origin.y > step) { axis.y = control.actions.down; }
    }
    var next = [axis.x, axis.y].filter((action) => action !== false);
    var previous = control.action === false ? [] : [].concat(control.action);
    if (previous.length == next.length && previous.every((action) => next.indexOf(action) !== -1)) {
      return;
    }
    control.action = next.length == 0 ? false : (next.length == 1 ? next[0] : next);
    previous.forEach((action) => {
      if (next.indexOf(action) === -1) {
        this.releaseTouchAction(action);
      }
    });
    next.forEach((action) => this.setControl(action, true));
  } // touchMove

  updateFps(timestamp) {
    if (!this.fpsEntity) {
      return;
    }
    this.fps.frames++;
    if (this.fps.since === false) {
      this.fps.since = timestamp;
      return;
    }
    var elapsed = timestamp-this.fps.since;
    if (elapsed >= 1000) {
      this.fpsEntity.setText(Math.round(this.fps.frames*1000/elapsed)+'/'+Math.round(this.fps.workerFrames*1000/elapsed)+'/'+Math.round(this.fps.ticks*1000/elapsed)+' FPS');
      this.fps.frames = 0;
      this.fps.workerFrames = 0;
      this.fps.ticks = 0;
      this.fps.since = timestamp;
    }
  } // updateFps

  loopModel(timestamp) {
    super.loopModel(timestamp);

    if (this.desktopEntity.modalEntity) {
      this.desktopEntity.modalEntity.loopEntity(timestamp);
    }

    this.updateFps(timestamp);
    this.drawModel();
  } // loopModel

} // RoomModel
