const { AbstractModel } = await import('./svision/js/abstractModel.js?ver='+window.srcVersion);
const { AbstractEntity } = await import('./svision/js/abstractEntity.js?ver='+window.srcVersion);
const { BorderEntity } = await import('./borderEntity.js?ver='+window.srcVersion);
const { ZXVideoRAMEntity } = await import('./svision/js/platform/canvas2D/zx/zxVideoRAMEntity.js?ver='+window.srcVersion);
const { TextEntity } = await import('./svision/js/platform/canvas2D/textEntity.js?ver='+window.srcVersion);
const { ButtonEntity } = await import('./svision/js/platform/canvas2D/buttonEntity.js?ver='+window.srcVersion);
const { SlidingTextEntity } = await import('./svision/js/platform/canvas2D/slidingTextEntity.js?ver='+window.srcVersion);
const { RoomComposer } = await import('./roomComposer.js?ver='+window.srcVersion);
const { GameInfoEntity } = await import('./gameInfoEntity.js?ver='+window.srcVersion);
const { ZXColor } = await import('./svision/js/platform/canvas2D/zx/zxColor.js?ver='+window.srcVersion);
// begin code

/**
 * HALL OF FAME as a screen of its own — the same shape as aboutModel.js: the
 * original's game selection screen (Room_Special_MainMenu, $61C6, composed by
 * RoomComposer) with the panel above it, the table laid over the black middle
 * of the jungle frame. Until 2026-09-07 it was a dialog over the menu
 * (HallOfFameEntity). Unlike ABOUT GAME it is **silent**: no prelude, the
 * audio buses stay closed as under the menu.
 *
 * ★ **The hall of fame is the original's own**, not an addition of the remake
 * (ZADANI chap. 6): the game has HallOfFame, NewHighScore and a default table
 * of **six places** at $B304 — three BCD bytes of score and a three-letter
 * name each — under the heading ULTIMATE HALL OF FAME, kept here word for
 * word, with the places written 1ST to 6TH ($B346). The top of that
 * table, 102275 ULT, is the HI the panel shows the moment the game is switched
 * on. And the original shows it over
 * this very jungle, flipping to it from the game selection screen by itself
 * (CounterHallOfFame, $96B8); the remake shows it on demand from the menu
 * instead (menuModel.js).
 *
 * So the screen keeps the original's shape: six places, 1ST-6TH, and the
 * original's own table as the fallback when the server cannot be reached
 * (data/global.json hallOfFame.defaults). What is the remake's own is only
 * that the live scores come off a server and that a name can be longer than
 * three letters — a row is place, score and name, and a name too long for its
 * column ping-pongs (SlidingTextEntity), the way the player's name does in the
 * menu.
 *
 * CLOSE (Enter, Escape, space, GamepadOK, GamepadExit) goes back to the menu.
 */
export class HallOfFameModel extends AbstractModel {

  constructor(app) {
    super(app);
    this.id = 'HallOfFameModel';

    this.screenEntity = null;
    this.gameInfoEntity = null;
    this.titleEntity = null;
    this.subtitleEntity = null;
    this.copyrightEntity = null;
    this.tableEntity = null;
    this.rowEntities = [];
    // the names, ticked from loopModel(): a name too long for its column ping-pongs
    this.nameEntities = [];

    // the table in the black middle of the jungle frame: cells 4-27 by 5-20
    // are 192 x 128 px, 4 px kept free on either side as the menu does
    // (menuModel.js)
    this.panelX = 36;
    this.panelY = 42;
    this.panelWidth = 184;
    this.panelHeight = 126;

    // the original's places, written the way the original writes them ($B346)
    this.places = ['1ST', '2ND', '3RD', '4TH', '5TH', '6TH'];
  } // constructor

  newBorderEntity() {
    // no X in the border: CLOSE goes back to the menu
    return new BorderEntity(false, false);
  } // newBorderEntity

  init() {
    super.init();

    this.borderEntity.bkColor = ZXColor.black;
    this.desktopEntity.bkColor = ZXColor.black;

    // the data files: at once from localStorage, or from the server when
    // they are missing there (R-062)
    this.loadDataFiles(['scenery', 'rooms', 'sprites', 'spriteframes'], (files, error) => this.initData(files, error));
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
    var scenery = this.loadDataFile('scenery');
    var rooms = this.loadDataFile('rooms');
    var menu = null, composer = null;
    if (scenery && rooms) {
      try {
        composer = new RoomComposer(scenery, rooms);
        menu = composer.composeMainMenu();
      } catch (error) {
        console.error(error.message);
      }
    }
    if (menu) {
      this.screenEntity = new ZXVideoRAMEntity(this.desktopEntity, 0, 0);
      this.screenEntity.restore(menu);
      this.desktopEntity.addEntity(this.screenEntity);
      // the panel above the jungle, as on the original's game selection screen
      this.gameInfoEntity = GameInfoEntity.aboveJungle(this, composer);
      // the name of the game in the panel, where the original has 2UP, as in
      // the menu; CLOSE is the button of the panel below
      [this.titleEntity, this.subtitleEntity] = GameInfoEntity.gameTitle(this);
      // the copyright line of the original's screen, where it has it: row 22,
      // cells 9-22, bright white (sources/media/screens/title_menu.scr)
      this.copyrightEntity = new TextEntity(this.desktopEntity, this.app.fonts.zxFonts8x8Mono, 9*8, 22*8, 14*8, 8, '© 1984  A.C.G.', ZXColor.brightWhite, ZXColor.black, {align: 'center'});
      this.desktopEntity.addEntity(this.copyrightEntity);
    } else {
      this.desktopEntity.addEntity(new TextEntity(this.desktopEntity, this.app.fonts.zxFonts8x8, 0, 8*8, this.desktopWidth, 8, 'SABRE WULF', ZXColor.brightWhite, false, {align: 'center'}));
      this.desktopEntity.addEntity(new TextEntity(this.desktopEntity, this.app.fonts.fonts5x5, 8, 8*8+16, this.desktopWidth-16, 40,
        'MENU ROOM MISSING (data/rooms.json, data/scenery.json). RUN tools/dumprooms.py.', ZXColor.brightGreen, false, {align: 'center', textWrap: true}));
    }

    // the table, over the middle of the frame, all on the black of the
    // tableEntity itself: the heading, the CLOSE button and the six places
    // drawn by showTable()
    this.tableEntity = new AbstractEntity(this.desktopEntity, this.panelX, this.panelY, this.panelWidth, this.panelHeight, false, ZXColor.black);
    this.desktopEntity.addEntity(this.tableEntity);
    var w = this.panelWidth, h = this.panelHeight;
    // the heading in the title bar every panel of the game has (aboutModel.js,
    // the dialogs of menuModel.js): fonts5x5, bright red, 9 px from the top
    // with a 2 px margin, centred; the text is the original's, see above
    this.tableEntity.addEntity(new TextEntity(this.tableEntity, this.app.fonts.fonts5x5, 0, 0, w, 9, 'ULTIMATE HALL OF FAME', ZXColor.brightRed, false, {align: 'center', topMargin: 2}));
    this.tableEntity.addEntity(new ButtonEntity(this.tableEntity, this.app.fonts.fonts5x5, w-39, h-16, 36, 13, 'CLOSE', {id: 'closeHallOfFame'}, ['Enter', 'Escape', ' ', 'GamepadOK', 'GamepadExit'], ZXColor.brightWhite, ZXColor.blue, {align: 'center', margin: 4}));

    if (navigator.onLine) {
      this.fetchData('hallOfFame.db', false, {});
    } else {
      this.showTable(this.defaultTable(), true);
    }

    this.app.stack.flashState = false;
    this.sendEvent(330, {id: 'changeFlashState'});
  } // initData

  /**
   * The original's own six entries, from data/global.json.
   * @returns {Array} [{name, score}] as the game has them at $B304.
   */
  defaultTable() {
    var global = this.app.globalData;
    if (global && global.hallOfFame && global.hallOfFame.defaults) {
      return global.hallOfFame.defaults;
    }
    return [];
  } // defaultTable

  setData(data) {
    var rows = Object.keys(data.data).map((key) => data.data[key]);
    if (!rows.length) {
      // nobody has played yet: show the table the original ships with
      this.showTable(this.defaultTable(), true);
      return;
    }
    this.showTable(rows, false);
    if (rows[0]) {
      this.app.hiScore = Number(rows[0].score);
    }
  } // setData

  errorData(error) {
    this.showTable(this.defaultTable(), true);
  } // errorData

  /**
   * Draws the six places.
   * @param {Array} rows - [{name, score}] in descending order of score.
   * @param {boolean} original - True when these are the original's own entries.
   */
  showTable(rows, original) {
    this.rowEntities.forEach((entity) => entity.destroy());
    this.rowEntities = [];
    this.nameEntities = [];
    var w = this.panelWidth, h = this.panelHeight;
    // the places in pairs, from the top down in the colours of the panel:
    // white, yellow, cyan — on black; 6 px between the rows
    var colors = [ZXColor.brightWhite, ZXColor.brightWhite, ZXColor.brightYellow, ZXColor.brightYellow, ZXColor.brightCyan, ZXColor.brightCyan];
    for (var i = 0; i < this.places.length; i++) {
      var y = 22+i*14;
      var row = rows[i];
      var color = colors[i];
      var place = new TextEntity(this.tableEntity, this.app.fonts.zxFonts8x8, 4, y, 26, 8, this.places[i], color, false, {align: 'right'});
      this.tableEntity.addEntity(place);
      this.rowEntities.push(place);
      // place (right-aligned in 26 px), 8 px, the six digits of the score
      // (48 px mono), 8 px, the name flush right in what is left of the row
      var score = new TextEntity(this.tableEntity, this.app.fonts.zxFonts8x8Mono, 38, y, 48, 8, row ? String(row.score).padStart(6, '0') : '', color, false, {});
      this.tableEntity.addEntity(score);
      this.rowEntities.push(score);
      var name = new SlidingTextEntity(this.tableEntity, this.app.fonts.zxFonts8x8, 94, y, w-94-4, 8, row ? String(row.name) : '', color, false, {align: 'right', animation: 'pingPong', speed: 30});
      this.tableEntity.addEntity(name);
      this.rowEntities.push(name);
      this.nameEntities.push(name);
    }
    if (original) {
      var note = new TextEntity(this.tableEntity, this.app.fonts.fonts5x5, 4, h-16, w-48, 12,
        navigator.onLine ? 'ORIGINAL TABLE' : 'SYSTEM OFFLINE - ORIGINAL TABLE',
        ZXColor.brightRed, false, {textWrap: true, margin: 1});
      this.tableEntity.addEntity(note);
      this.rowEntities.push(note);
    }
  } // showTable

  handleEvent(event) {
    if (super.handleEvent(event)) {
      return true;
    }

    switch (event.id) {
      case 'changeFlashState':
        this.app.stack.flashState = !this.app.stack.flashState;
        this.sendEvent(330, {id: 'changeFlashState'});
        return true;

      case 'closeHallOfFame':
        this.app.setModel('MenuModel');
        return true;

    }

    return false;
  } // handleEvent

  loopModel(timestamp) {
    super.loopModel(timestamp);

    if (this.desktopEntity.modalEntity) {
      this.desktopEntity.modalEntity.loopEntity(timestamp);
    } else {
      // entities are not ticked on their own: the long names ping-pong only
      // when the model advances them, as the menu does with the player's name
      this.nameEntities.forEach((entity) => entity.loopEntity(timestamp));
    }

    this.drawModel();
  } // loopModel

} // HallOfFameModel
