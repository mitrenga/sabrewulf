const { AbstractEntity } = await import('./svision/js/abstractEntity.js?ver='+window.srcVersion);
const { TextEntity } = await import('./svision/js/platform/canvas2D/textEntity.js?ver='+window.srcVersion);
const { ButtonEntity } = await import('./svision/js/platform/canvas2D/buttonEntity.js?ver='+window.srcVersion);
const { MenuEntity } = await import('./svision/js/platform/canvas2D/menuEntity.js?ver='+window.srcVersion);
const { ZXColor } = await import('./svision/js/platform/canvas2D/zx/zxColor.js?ver='+window.srcVersion);
// begin code

/**
 * The pause panel. ★ The original pauses too — "Continuous Pause" on the
 * inlay, on CAPS SHIFT or SPACE/BREAK (ZADANI chap. 3) — but it has no menu
 * behind it; RESUME / SOUNDS / MUSIC / EXIT is the remake's own, like the main
 * menu itself.
 *
 * ★ Since 2026-09-07 there is one switch, SOUNDS, and one bus the music goes
 * over too; the MUSIC item went with the menu's MUSIC slider (ZADANI chap. 1).
 * Sabre Wulf **has** music, unlike Underwurlde: the
 * program carries MusicData_GameInitialisation, _Poem, _GameOver and
 * _GameComplete, and PlaySquareWave / PlayWaveSequence to play them (ZXDB
 * names Bach, BWV 846, as the source). Since M6 those four tunes really play,
 * out of the note table at $BDD2 and the routines that read it
 * (app/beeper.js), so the slider controls something the game actually has.
 *
 * ★ And while the pause is up, the border does what the original's does: $AC40
 * alternates it blue and magenta every 32 frames — the one and only thing
 * Sabre Wulf ever does with the border (roomModel.startPauseBorder).
 */
export class PauseGameEntity extends AbstractEntity {

  constructor(parentEntity, x, y, width, height, title, exitModel) {
    super(parentEntity, x, y, width, height, false, false);
    this.id = 'PauseGameEntity';

    this.title = title;
    this.exitModel = exitModel;
    this.menuItems = [
      {t1: 'RESUME GAME', event: {id: 'closePauseGame'}},
      {t1: 'SOUNDS', event: {id: 'changeSoundsState'}},
      {t1: 'EXIT GAME', event: {id: 'exitGame'}}
    ];
    this.menuOptions = {
      fonts: this.app.fonts.zxFonts8x8,
      leftMargin: 9,
      rightMargin: 9,
      topMargin: 8,
      itemHeight: 12,
      t1LeftMargin: 3,
      t1TopMargin: 2, 
      t2Width: 114,
      t2RightMargin: 3,
      t2TopMargin: 2, 
      textColor: ZXColor.black,
      selectionTextColor: ZXColor.black,
      selectionBarColor: '#dbdbdbff',
      hoverColor: '#0000001e',
      selectionHoverColor: '#efefefff',
      clickColor: '#0000002e',
      selectionClickColor: '#ffffffff'
    }
  } // constructor

  init() {
    super.init();
    this.addEntity(new AbstractEntity(this, 0, 0, this.width, this.height, false, ZXColor.brightWhite));
    this.addEntity(new TextEntity(this, this.app.fonts.fonts5x5, 0, 0, this.width, 9, this.title, ZXColor.brightBlack, false, {align: 'center', margin: 2}));
    this.addEntity(new MenuEntity(this, 1, 8, this.width-2, this.height-9, ZXColor.yellow, this.menuOptions, this, this.getMenuData));
  } // init

  getMenuData(self, key, row) {
    switch (key) {
      
      case 'numberOfItems':
        return self.menuItems.length;

      case 't2':
        switch (row) {
          case 1:
            return self.app.muted.sounds ? 'MUTE' : 'ON';
        }
        break;

      default:
        if (key in self.menuItems[row]) {
          return self.menuItems[row][key];
        }
        break;

    }
    return '';
  } // getMenuData

  handleEvent(event) {
    if (super.handleEvent(event)) {
      return true;
    }

    switch (event.id) {

      case 'keyPress':
        switch (event.key) {
          case 'Escape':
            this.sendEvent(-1, 1, {id: 'continueGame'});
            this.destroy();
            return true;
        }
        break;

      case 'closePauseGame':
        this.sendEvent(-1, 1, {id: 'continueGame'});
        this.destroy();
        return true;
        
      case 'changeSoundsState':
        this.app.muted.sounds = !this.app.muted.sounds;
        this.sendEvent(0, 0, {id: 'muteAudioBus', bus: 'sounds', muted: this.app.muted.sounds});
        this.sendEvent(1, 0, {id: 'refreshMenu'});
        return true;

      case 'exitGame':
        this.app.setModel(this.exitModel);
        return true;
    }

    return false;
  } // handleEvent

} // PauseGameEntity
