const { AbstractModel } = await import('./svision/js/abstractModel.js?ver='+window.srcVersion);
const { TextEntity } = await import('./svision/js/platform/canvas2D/textEntity.js?ver='+window.srcVersion);
const { ButtonEntity } = await import('./svision/js/platform/canvas2D/buttonEntity.js?ver='+window.srcVersion);
const { ZXColor } = await import('./svision/js/platform/canvas2D/zx/zxColor.js?ver='+window.srcVersion);
// begin code

/**
 * Game over: shows the score, stores it in the hall of fame on the server and
 * returns to the menu after a countdown. The score is shown with the six
 * digits of the original panel.
 *
 * ★ Unlike Underwurlde, Sabre Wulf **has** a hall of fame of its own
 * (HallOfFame, NewHighScore, the table at $B304 and the flip from the menu),
 * so keeping the score is fidelity here rather than an addition — what the
 * remake adds is only that the table lives on a server. The original's own
 * wording for this moment is `GAME OVER PLAYER 1` ($AAC2), and with two
 * players it says which one.
 *
 * ★ Since M4 the **percentage of the world seen** is here as well, because it
 * is a rule of the game and not a reviewer's impression: PrintRoomsVisited
 * ($9CC6) counts the 256 bits of VisitedRooms **and the four pieces of the
 * amulet**, so the whole is 260 and one screen is worth less than half a
 * percent. The original's own wording is ADVENTURE COMPLETED nn% ($AAD4) and
 * that is what is printed here, spacing included.
 */
export class GameOverModel extends AbstractModel {

  constructor(app, nextModel) {
    super(app);
    this.id = 'GameOverModel';

    this.nextModel = nextModel;
    this.countdownLength = 8;
    this.buttonEntity = null;
    this.timerEntity = null;
  } // constructor

  init() {
    super.init();

    this.desktopEntity.bkColor = ZXColor.black;
    this.borderEntity.bkColor = ZXColor.black;

    // ★ Kdo prošel branou, nevidí GAME OVER, ale to, co ukazuje originál:
    // šest řádků z $9F91 (data/text.json, tools/dumptext.py). První tři na
    // svých řádcích 4, 6 a 8, zbytek téhle obrazovky zůstává remaku vlastní.
    // the data files: at once from localStorage, or from the server when
    // they are missing there (R-062)
    this.loadDataFiles(['text', 'sounds', 'music'], (files, error) => this.initData(files, error));
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
    var complete = this.app.complete
      ? this.loadDataFile('text') : null;
    if (complete && complete.gameComplete) {
      complete.gameComplete.lines.slice(0, 3).forEach((line) => {
        this.desktopEntity.addEntity(new TextEntity(
          this.desktopEntity, this.app.fonts.zxFonts8x8Mono, 0, line.row*8,
          this.desktopWidth, 8, line.text, ZXColor.brightWhite, false,
          {align: 'center'}));
      });
    } else {
      var over = (this.app.players === 2) ? 'GAME OVER PLAYER '+this.app.player : 'GAME OVER';
      this.desktopEntity.addEntity(new TextEntity(this.desktopEntity, this.app.fonts.zxFonts8x8, 0, 10*8, this.desktopWidth, 8, over, ZXColor.brightRed, false, {align: 'center'}));
    }
    this.desktopEntity.addEntity(new TextEntity(this.desktopEntity, this.app.fonts.zxFonts8x8Mono, 0, 13*8, this.desktopWidth, 8, 'SCORE '+String(this.app.score).padStart(6, '0'), ZXColor.brightWhite, false, {align: 'center'}));
    var hiScore = Math.max(this.app.hiScore || 0, this.app.score || 0);
    var hiText = (this.app.score > 0 && this.app.score >= (this.app.hiScore || 0)) ? 'NEW HI-SCORE !' : 'HI-SCORE '+String(hiScore).padStart(6, '0');
    this.desktopEntity.addEntity(new TextEntity(this.desktopEntity, this.app.fonts.zxFonts8x8Mono, 0, 15*8, this.desktopWidth, 8, hiText, ZXColor.brightGreen, false, {align: 'center'}));
    // ADVENTURE COMPLETED    n% ($AAD4) – čtyři mezery jsou originálovy
    var completed = 'ADVENTURE COMPLETED    '+(this.app.percent || 0)+'%';
    this.desktopEntity.addEntity(new TextEntity(this.desktopEntity, this.app.fonts.zxFonts8x8Mono, 0, 17*8, this.desktopWidth, 8, completed, ZXColor.brightYellow, false, {align: 'center'}));
    this.buttonEntity = new ButtonEntity(this.desktopEntity, this.app.fonts.zxFonts8x8Mono, this.desktopWidth/2-35, 22*8-4, 70, 12, 'MENU', {id: this.nextModel}, ['Enter', 'Escape', ' ', 'GamepadOK', 'GamepadExit'], ZXColor.brightWhite, ZXColor.green, {topMargin: 2, align: 'center'});
    this.desktopEntity.addEntity(this.buttonEntity);
    this.timerEntity = new TextEntity(this.buttonEntity, this.app.fonts.fonts5x5, 8, 4, 10, 5, String(this.countdownLength), ZXColor.white, false, {align: 'center'});
    this.buttonEntity.addEntity(this.timerEntity);

    // ★ a hudba, kterou hraje originál na tomhle místě. Jsou dvě a hra mezi
    // nimi rozlišuje: kdo prohrál, slyší MusicData_GameOver ($AA8A, deset not,
    // 1,6 s), kdo **prošel branou**, dostane MusicData_GameComplete ($9F7E) –
    // třicet vteřin preludia, tedy totéž, co hraje pod hlavním menu
    // (data/music.json, app/beeper.js).
    if (this.app.audioManager) {
      this.app.audioManager.playMusic(this.app.complete ? 'gameComplete'
                                                        : 'gameOver');
    }

    if (this.app.score) {
      this.fetchData('saveGame.db', false, {name: this.app.playerName, score: this.app.score});
    }
  } // initData


  shutdown() {
    super.shutdown();
    this.sendEvent(0, {id: 'stopAllAudioBuses'});
  } // shutdown

  setData(data) {
    this.app.hiScore = data.data.hiScore;
  } // setData

  errorData(data) {
  } // errorData

  handleEvent(event) {
    if (super.handleEvent(event)) {
      return true;
    }

    switch (event.id) {
      case 'MenuModel':
        this.app.setModel('MenuModel');
        return true;
    }

    return false;
  } // handleEvent

  loopModel(timestamp) {
    super.loopModel(timestamp);

    if (this.timer === false) {
      this.timer = timestamp;
    }
    var countdown = this.countdownLength-Math.floor((timestamp-this.timer)/1000);
    if (countdown < 0) {
      this.sendEvent(1, {id: this.nextModel});
    } else {
      this.timerEntity.setText(countdown.toString());
    }

    this.drawModel();
  } // loopModel

} // GameOverModel
