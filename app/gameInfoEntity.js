const { RasterEntity } = await import('./svision/js/platform/canvas2D/rasterEntity.js?ver='+window.srcVersion);
const { ScreenLayout } = await import('./screenLayout.js?ver='+window.srcVersion);
const { ScreenComposer } = await import('./screenComposer.js?ver='+window.srcVersion);
const { ButtonEntity } = await import('./svision/js/platform/canvas2D/buttonEntity.js?ver='+window.srcVersion);
const { TextEntity } = await import('./svision/js/platform/canvas2D/textEntity.js?ver='+window.srcVersion);
const { ZXColor } = await import('./svision/js/platform/canvas2D/zx/zxColor.js?ver='+window.srcVersion);
// begin code

/**
 * The panel: character rows 0-1 — 1UP, the lives with the little Sabreman
 * beside them, HI and 2UP on the top row, and three six-digit scores below,
 * the layout measured character by character on the running original
 * (sources/docs/screen_layout.md chap. 2).
 *
 * ★ The panel carries **1UP and 2UP whether one player is playing or two**,
 * and the second score simply stays at zeroes. That is not decoration: two
 * players are part of the original (GameOptions, $9692) and the panel is built
 * for them, so in this remake they are fidelity rather than an addition.
 *
 * It is set in the character set the game prints with, which is the ZX
 * Spectrum ROM font — PrintScreen ($B589) takes the glyph out of CHARS
 * ($5C36); see screenComposer.js. tools/matchpanel.py compares this panel with
 * three captured frames byte for byte: zero differences.
 */
export class GameInfoEntity extends RasterEntity {

  /**
   * @param {AbstractEntity} parentEntity - The parent entity.
   * @param {number} x - X position relative to the parent.
   * @param {number} y - Y position relative to the parent.
   * @param {ScreenComposer} render - The shared renderer.
   */
  constructor(parentEntity, x, y, render) {
    super(parentEntity, x, y, ScreenLayout.WIDTH, ScreenLayout.PANEL_HEIGHT, false, false);
    this.id = 'GameInfoEntity';

    this.render = render;
    this.panel = {score: 0, score2: 0, hiScore: 0, lives: 0, player: 1, labelFlash: false,
                  twoPlayers: false};
    // the score label flashes while the changeover delay runs ($AEA1)
    this.watchFlash = true;
  } // constructor

  /**
   * The panel of the original's menu and title screens, above the jungle: the
   * same panel the game has, showing 1UP with the last score and HI and no
   * lives (sources/media/screens/title_menu.scr). The screen composer needs a
   * room to be built on, so it is built on the jungle just composed.
   * @param {AbstractModel} model - The model that owns the desktop.
   * @param {RoomComposer} composer - The composer that built the jungle.
   * @returns {GameInfoEntity|null} The panel, added to the desktop, or null.
   */
  static aboveJungle(model, composer) {
    try {
      var fonts = model.app.fonts.zxFonts8x8Mono;
      var render = new ScreenComposer(composer.playArea(),
                                      {chars: fonts.fontsChars, data: fonts.fontsData},
                                      model.loadDataFile('sprites'),
                                      model.loadDataFile('spriteframes'));
    } catch (error) {
      console.error(error.message);
      return null;
    }
    var panel = new GameInfoEntity(model.desktopEntity, 0, 0, render);
    model.desktopEntity.addEntity(panel);
    panel.setPanel({score: model.app.score, hiScore: model.app.hiScore, lives: null});
    return panel;
  } // aboveJungle

  /**
   * The name of the game in the panel, where the original has 2UP: the first
   * word on the row of the labels in their colour (1UP, $45 bright cyan), the
   * rest on the row of the scores in theirs ($46 bright yellow), both flush
   * with the right hand edge less 8 px, in the title font (zxFonts8x8Title,
   * gameApp.js). The menu, the hall of fame and the about screen carry it; the
   * game has the pause button there instead.
   * @param {AbstractModel} model - The model that owns the desktop.
   * @returns {TextEntity[]} The two lines, added to the desktop.
   */
  static gameTitle(model) {
    var words = String(window.appName).split(' ');
    var title = new TextEntity(model.desktopEntity, model.app.fonts.zxFonts8x8Title, 0, 0, model.desktopWidth-8, 8, words[0], ZXColor.brightCyan, false, {align: 'right'});
    model.desktopEntity.addEntity(title);
    var subtitle = new TextEntity(model.desktopEntity, model.app.fonts.zxFonts8x8Title, 0, 8, model.desktopWidth-12, 8, words.slice(1).join(' '), ZXColor.brightYellow, false, {align: 'right'});
    model.desktopEntity.addEntity(subtitle);
    return [title, subtitle];
  } // gameTitle

  /**
   * The button that opens the pause menu, **in the panel where the original
   * has 2UP** (rows 0-1, cells 29-30, one cell in from the right edge) — the remake shows
   * one player, so the place is free, and on a touch screen it is where a thumb
   * finds it. A bold cross of 16 x 16 px in cyan, four glyphs of the ZX font
   * added in gameApp.js (◰◳ over ◱◲). It sends the Escape key, which is what
   * the border's X used to send, so the model reacts the same way (PAUSE GAME
   * in the game).
   * @param {AbstractModel} model - The model that owns the desktop.
   * @returns {ButtonEntity} The button, added to the desktop.
   */
  static pauseButton(model) {
    var button = new ButtonEntity(model.desktopEntity, model.app.fonts.zxFonts8x8Mono, 29*8, 0, 16, 16, '◰◳\n◱◲',
                                  {id: 'keyPress', key: 'Escape'}, [], ZXColor.cyan, ZXColor.black,
                                  {align: 'center', clickColor: '#7a7a7aff'});
    model.desktopEntity.addEntity(button);
    return button;
  } // pauseButton

  /**
   * Updates the panel values, repainting only when something changed.
   * @param {Object} panel - {score, score2, hiScore, lives}.
   */
  setPanel(panel) {
    var changed = false;
    Object.keys(this.panel).forEach((key) => {
      if (key in panel && panel[key] !== this.panel[key]) {
        this.panel[key] = panel[key];
        changed = true;
      }
    });
    if (changed) {
      this.cleanCache();
    }
  } // setPanel

  /**
   * Fills the frame; RasterEntity calls it only when the cache is dirty.
   * @param {Uint8ClampedArray} data - The RGBA bytes of the frame.
   */
  paintRaster(data) {
    this.render.renderPanel(data, this.panel, this.flashState);
  } // paintRaster

} // GameInfoEntity
