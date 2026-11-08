// begin code

/**
 * Composes one screen of the jungle out of the room data of the original.
 *
 * ★ A room in Sabre Wulf is **not a picture, it is a list of pieces of scenery
 * with positions**. Layout ($6066) is a 16 x 16 grid and every byte of it is
 * the number of a template in RoomTable ($6166); a template is a run of
 * four-byte records — a word with the address of a piece of scenery, then X and
 * Y in pixels — ending on $0000, and DrawRoom ($BBF7) walks it. That is why
 * 256 screens fit in a few kilobytes and why the same screens keep coming
 * back: there are only 45 different templates
 * (sources/docs/disasm_notes.md chap. 4 and 12).
 *
 * This class is that routine, in the shape the data files carry it:
 * data/scenery.json (the 41 pieces, tools/dumpgfx.py) and data/rooms.json (the
 * 48 templates, tools/dumprooms.py). It reproduces the original's addressing
 * rather than a tidied-up version of it, because two details of it are visible
 * on screen:
 *
 * - a piece is written **hard** (LD (HL),A, not OR), so a later piece covers an
 *   earlier one with its zeroes as well — the order inside a template matters;
 * - the writes run through the machine's own screen addressing, INC L and all,
 *   so a piece that runs off the right edge does not continue on the same line
 *   but eight pixels lower (and from the last character row of a third it wraps
 *   back to the top of that third). ★ It really does happen in the game's data.
 *
 * Before the room is drawn the play area is cleared the way the game clears it
 * (ClearPlayArea $BB5C: zero bitmap; ClearPlayArea_Attributes $BB7C: $5840 to
 * $5AFF filled with $40 — bright black on black), which is where the black of
 * the jungle floor comes from.
 *
 * The output is exactly what ScreenComposer consumes: a play-area bitmap of
 * 5632 bytes stored line by line and 704 attributes. That the two agree with
 * the original byte for byte is checked twice over — tools/matchscreen.py runs
 * a python replica against the original's own routine in a simulator across
 * all 256 screens, and tools/matchrooms.js runs **this** file against the same
 * bytes. Both want zero differences.
 *
 * Deliberately free of DOM and Node dependencies, so an offline tool
 * can compose with the very same code.
 */

const PANEL_ROWS = 2;
const PLAY_TOP = PANEL_ROWS*8;
/** attribute the game fills the play area with before drawing (ClearPlayArea_Attributes) */
const CLEAR_ATTRIBUTE = 0x40;

export class RoomComposer {

  /**
   * @param {Object} scenery - The parsed data/scenery.json.
   * @param {Object} rooms - The parsed data/rooms.json.
   */
  constructor(scenery, rooms) {
    this.pieces = {};
    for (const piece of scenery.pieces) {
      this.pieces[piece.id] = {
        width: piece.width, height: piece.height,
        attrRows: piece.attrRows, attrCols: piece.attrCols,
        bitmap: RoomComposer.decode(piece.bitmap),
        attributes: RoomComposer.decode(piece.attributes)
      };
    }
    this.templates = rooms.templates;
    /** the 49th template, the jungle under the main menu ($61C6) */
    this.mainMenu = rooms.mainMenu || null;
    // one scratch screen, reused: 6144 bytes of bitmap and 768 of attributes,
    // addressed the way the machine does it
    this.bitmap = new Uint8Array(6144);
    this.attributes = new Uint8Array(768);
  } // constructor

  /** base64 of real bytes -> Uint8Array */
  static decode(base64) {
    const raw = atob(base64);
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) {
      out[i] = raw.charCodeAt(i);
    }
    return out;
  } // decode

  /** $B8AD: X/Y in pixels -> offset in the bitmap */
  static screenOffset(x, y) {
    const high = (((y >> 6) & 3) << 3) | (y & 7);
    const low = ((x >> 3) & 0x1F) | (((y >> 3) & 7) << 5);
    return (high << 8) | low;
  } // screenOffset

  /** $B8DD (AttributeAddress): X/Y in pixels -> offset in the attributes */
  static attributeOffset(x, y) {
    return (((y >> 6) & 3) << 8) | ((x >> 3) & 0x1F) | (((y >> 3) & 7) << 5);
  } // attributeOffset

  /** $B8CC (ScreenPos1PixelBelow), including the wrap between the thirds */
  static pixelRowBelow(offset) {
    let high = ((offset >> 8)+1) & 0xFF;
    let low = offset & 0xFF;
    if (high & 7) {
      return (high << 8) | low;
    }
    low = (low+0x20) & 0xFF;
    if (!(low & 0xE0)) {          // wrapped into the next third: keep the high byte
      return (high << 8) | low;
    }
    return (((high-8) & 0xFF) << 8) | low;
  } // pixelRowBelow

  /** ClearPlayArea ($BB5C) + ClearPlayArea_Attributes ($BB7C) */
  clear() {
    for (let y = PLAY_TOP; y < 192; y++) {
      this.bitmap.fill(0, RoomComposer.screenOffset(0, y),
                       RoomComposer.screenOffset(0, y)+32);
    }
    this.attributes.fill(CLEAR_ATTRIBUTE, PANEL_ROWS*32, 24*32);
  } // clear

  /** DrawRoom_Process ($BC0B) for one piece of scenery */
  drawPiece(piece, x, y) {
    let offset = RoomComposer.screenOffset(x, y);
    let source = 0;
    for (let row = 0; row < piece.height; row++) {
      const high = offset & 0xFF00;
      let low = offset & 0xFF;
      for (let column = 0; column < piece.width; column++) {
        this.bitmap[high | low] = piece.bitmap[source++];
        low = (low+1) & 0xFF;     // ★ INC L: off the right edge is 8 pixels lower
      }
      low = (low-piece.width) & 0xFF;
      offset = RoomComposer.pixelRowBelow(high | low);
    }
    offset = RoomComposer.attributeOffset(x, y);
    source = 0;
    for (let row = 0; row < piece.attrRows; row++) {
      const high = offset & 0xFF00;
      let low = offset & 0xFF;
      for (let column = 0; column < piece.attrCols; column++) {
        this.attributes[high | low] = piece.attributes[source++];
        low = (low+1) & 0xFF;
      }
      offset = (offset+0x20) & 0xFFFF;
    }
  } // drawPiece

  /**
   * Draws the pieces of one template into the cleared screen — DrawRoom
   * ($BBF7) walking its list.
   * @param {string} items - The template's packed items.
   * @returns {boolean} False when the list names a piece that is not there.
   */
  drawItems(items) {
    // three bytes per piece: its number and its X and Y in pixels, the raw
    // bytes of the template. ★ Four records in the game's own data have an X
    // that is not a multiple of eight; the drawing throws those low bits away
    // ($B8AD does RRCA x3 / AND $1F, and screenOffset does the same), but the
    // collision does not (sabremanPhysics.js, $B873), so they are kept.
    for (let i = 0; i+6 <= items.length; i += 6) {
      const piece = this.pieces['$'+items.substring(i, i+2)];
      if (!piece) {
        return false;
      }
      this.drawPiece(piece, parseInt(items.substring(i+2, i+4), 16),
                     parseInt(items.substring(i+4, i+6), 16));
    }
    return true;
  } // drawItems

  /**
   * Composes one of the 48 templates.
   * @param {number} template - The template number, 0 to 47.
   * @returns {Object} {bitmap, attributes} of the play area.
   */
  composeTemplate(template) {
    const items = this.templates[template] && this.templates[template].items;
    if (typeof items !== 'string') {
      return null;
    }
    this.clear();
    return this.drawItems(items) ? this.playArea() : null;
  } // composeTemplate

  /**
   * Composes the jungle the original draws under the game selection menu
   * (Room_Special_MainMenu, $61C6). It is the 49th list of pieces in the very
   * same format, it just does not sit in RoomTable — so it is composed by the
   * same routine as every other room rather than taken as a picture.
   * @returns {Uint8Array|null} The whole video memory, or null without the
   *          data (an older data/rooms.json has no `mainMenu`).
   */
  composeMainMenu() {
    const items = this.mainMenu && this.mainMenu.items;
    if (typeof items !== 'string') {
      return null;
    }
    this.clear();
    return this.drawItems(items) ? this.videoRAMBytes() : null;
  } // composeMainMenu

  /**
   * The whole screen the way the machine holds it: 6144 bytes of bitmap in the
   * ULA's own order and 768 attributes behind them, which is what
   * {@link ZXVideoRAM} takes.
   * @returns {Uint8Array} 6912 bytes, $4000-$5AFF.
   */
  videoRAMBytes() {
    const bytes = new Uint8Array(6912);
    bytes.set(this.bitmap, 0);
    bytes.set(this.attributes, 6144);
    return bytes;
  } // videoRAMBytes

  /**
   * Composes the screen at a place in the 16 x 16 grid.
   * @param {Object} world - The parsed data/world.json.
   * @param {number} column - 0 to 15.
   * @param {number} row - 0 to 15.
   * @returns {Object} {bitmap, attributes} of the play area.
   */
  composeRoom(world, column, row) {
    const line = world.templates[row];
    return this.composeTemplate(parseInt(line.substring(column*2, column*2+2), 16));
  } // composeRoom

  /** the play area in the shape ScreenComposer takes: bitmap line by line */
  playArea() {
    const bitmap = new Uint8Array(32*(192-PLAY_TOP));
    for (let y = PLAY_TOP, line = 0; y < 192; y++, line++) {
      bitmap.set(this.bitmap.subarray(RoomComposer.screenOffset(0, y),
                                      RoomComposer.screenOffset(0, y)+32), line*32);
    }
    return {
      width: 256, height: 192-PLAY_TOP,
      bitmap: bitmap,
      attributes: this.attributes.slice(PANEL_ROWS*32, 24*32)
    };
  } // playArea

} // class RoomComposer
