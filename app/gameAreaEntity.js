const { ZXVideoRAMEntity } = await import('./svision/js/platform/canvas2D/zx/zxVideoRAMEntity.js?ver='+window.srcVersion);
const { ScreenLayout } = await import('./screenLayout.js?ver='+window.srcVersion);
// begin code

/**
 * The room: 256x176 pixels below the panel, character rows 2-23
 * (sources/docs/screen_layout.md).
 *
 * The entity is svision's {@link ZXVideoRAMEntity}, so the video memory, the
 * painting and the off-screen cache are the library's (R-003); what is left
 * here is the one thing that belongs to the game — filling that memory with a
 * room and the entities standing in it, which ScreenComposer does.
 *
 * The memory is the machine's whole 6912 bytes and this entity shows the rows
 * below the panel, because the original's drawing does not stop at the edge of
 * the play area: a tall sprite near the top writes over the panel, and that is
 * reproduced rather than clipped away.
 *
 * Feed it with setFrame() from the worker 'frame' message (WORKER-PROTOCOL.md).
 */
export class GameAreaEntity extends ZXVideoRAMEntity {

  /**
   * @param {AbstractEntity} parentEntity - The parent entity.
   * @param {number} x - X position relative to the parent.
   * @param {number} y - Y position relative to the parent.
   * @param {ScreenComposer} render - The shared renderer.
   */
  constructor(parentEntity, x, y, render) {
    super(parentEntity, x, y,
          {col: 0, row: ScreenLayout.PANEL_ROWS,
           cols: ScreenLayout.COLS, rows: ScreenLayout.PLAY_ROWS});
    this.id = 'GameAreaEntity';

    this.render = render;
    this.frameState = {};
  } // constructor

  /**
   * Stores the state of the newest frame and invalidates the cache.
   * @param {Object} state - The 'frame' message of the worker.
   */
  setFrame(state) {
    this.frameState = state;
    this.invalidate();
  } // setFrame

  /**
   * Composes the room and everything standing in it into the video memory.
   * Called only when the cache is dirty, so the pixel work happens once per
   * game frame rather than once per display frame.
   */
  compose() {
    this.render.composeInto(this.videoRAM, this.frameState);
  } // compose

} // GameAreaEntity
