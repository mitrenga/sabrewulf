const { ZXVideoRAM } = await import('./svision/js/platform/canvas2D/zx/zxVideoRAM.js?ver='+window.srcVersion);
// begin code

/**
 * Renders the Sabre Wulf screen into a raw RGBA buffer.
 *
 * What the machine is — the 6912 bytes of video memory, the ULA's interleaved
 * addressing, `poke`/`peek` and the turning of bytes plus attributes into
 * pixels — is svision's ZXVideoRAM (R-003). What is left here is what belongs
 * to the game: how a room is composed, how an entity is blitted into it and
 * what the panel says.
 *
 * Everything it draws comes out of the original: the room is composed the way
 * the game composes it — a template out of RoomTable ($6166) built from the 41
 * pieces of scenery, see roomComposer.js and tools/matchscreen.py — the life
 * icon in the panel is the game's own UDG from $B814 (data/sprites.json) and
 * the panel is set in the character set the game prints with.
 *
 * ★ And that character set is **not the game's own**: PrintScreen ($B589)
 * works out the address of a glyph as ($5C36) + code*8, i.e. out of CHARS —
 * the system variable the ROM points at $3C00, so the glyph of a space sits at
 * $3D00. Sabre Wulf prints with the **ZX Spectrum ROM font**. That is why no
 * character set is named in the public disassembly and why none can be found
 * anywhere in the runtime image: it is in the ROM, outside it. svision carries
 * that same ROM font as the default table of ZXFonts8x8
 * (svision/fonts/zx-rom.ch8.hex.txt), so the panel takes its glyphs from there
 * rather than from a data file of ours — and tools/matchpanel.py proves the
 * claim by rebuilding the panel from that table and comparing it with three
 * captured frames byte for byte.
 *
 * It works the way the machine does — a bitmap of 8 pixels per byte plus one
 * attribute byte per 8x8 cell — so the attribute clash is reproduced rather
 * than removed (ZADANI chap. 1). In Sabre Wulf that is the single most
 * noticeable property of the picture, the jungle being the most colourful
 * screen Ultimate ever put on a Spectrum.
 *
 * ★ And M6 found where it comes from: not from the scenery, but from $BB47,
 * which writes an entity's colour **only into cells whose paper is black**. The
 * jungle keeps its colours, the figure takes the black between them, and since
 * one attribute covers eight pixels by eight, a sixteen pixel wide Sabreman
 * repaints two cells or three. Everything this file draws is checked against
 * what the original left in video memory by tools/matchsprites.js — all 6912
 * bytes of it, 772 screens, zero differences.
 *
 * Free of DOM dependencies, so an offline tool can render with the very same
 * code; ZXVideoRAM is free of them too (R-001).
 */

export class ScreenComposer {

  /** the panel takes the first two character rows, so the play area starts here */
  static get PANEL_LINES() { return 16; }
  // $47 – bright white, Sabreman's normal colour and the one $AF7D flashes him
  // in while an orchid's effect runs out ($AF98)
  static get FLASH_COLOUR() { return 0x47; }

  // The panel, measured character by character on the running original
  // (screen_layout.md chap. 2) and checked byte for byte by
  // tools/matchpanel.py. Row 0 carries the labels and the lives, row 1 the
  // three six-digit scores — the game is built for two players whether one is
  // playing or not.
  static get PANEL() {
    return {
      label1UP: {row: 0, col: 2, attr: 0x45},
      lives: {row: 0, col: 8, attr: 0x47},
      lifeIcon: {row: 0, col: 9, attr: 0x47},
      labelHI: {row: 0, col: 15, attr: 0x57},
      label2UP: {row: 0, col: 27, attr: 0x45},
      score1UP: {row: 1, col: 1, attr: 0x46},
      scoreHI: {row: 1, col: 13, attr: 0x46},
      score2UP: {row: 1, col: 25, attr: 0x46},
      digits: 6
    };
  } // PANEL

  /**
   * @param {Object} room - The play area as {width, height, bitmap,
   *        attributes} — either composed by roomComposer.js or read from a
   *        data file, where the two blocks are base64.
   * @param {Object} [font] - {chars, data}: the character list and the hex
   *        glyph table of svision's ZXFonts8x8, i.e. the ROM font the game
   *        prints with. Without it the panel stays empty.
   * @param {Object} [sprites] - The parsed data/sprites.json; without it the
   *        life icon is simply not drawn.
   * @param {Object} [spriteFrames] - The parsed data/spriteframes.json (the
   *        153 frames of SpritesTable, tools/dumpsprites.py); without it
   *        nobody is drawn into the room.
   */
  constructor(room, font, sprites, spriteFrames) {
    if (!room || !room.bitmap || !room.attributes) {
      throw new Error('room data missing or incomplete');
    }
    this.room = {
      width: room.width || 256,
      height: room.height || 176,
      bitmap: ZXVideoRAM.decode(room.bitmap),
      attributes: ZXVideoRAM.decode(room.attributes)
    };
    this.roomAsVideoRAM = null;
    this.font = {};
    if (font && font.chars && font.data) {
      for (var index = 0; index < font.chars.length; index++) {
        this.font[font.chars.charAt(index)] =
          ZXVideoRAM.hexToBytes(font.data.substr(index*16, 16));
      }
    }
    this.sprites = {};
    if (sprites) {
      Object.keys(sprites).forEach((group) => {
        var frames = sprites[group] && sprites[group].frames;
        if (!frames) {
          return;
        }
        Object.keys(frames).forEach((name) => {
          this.sprites[group+'.'+name] = {
            cols: frames[name].cols,
            rows: frames[name].rows,
            width: frames[name].width,
            height: frames[name].height,
            bitmap: ZXVideoRAM.decode(frames[name].bitmap),
            attributes: ZXVideoRAM.decode(frames[name].attributes)
          };
        });
      });
    }
    // the frames of SpritesTable ($BF84) by sprite number: 196 numbers point
    // at 153 different pictures, because the animations play back and forth
    this.spriteFrames = {};
    if (spriteFrames && spriteFrames.sprites && spriteFrames.frameData) {
      var byAddress = {};
      spriteFrames.frameData.forEach(function (frame) {
        byAddress[frame.address] = {
          width: frame.width, height: frame.height,
          bitmap: ZXVideoRAM.decode(frame.bitmap)
        };
      });
      spriteFrames.sprites.forEach(function (sprite, id) {
        if (sprite && byAddress[sprite.frame]) {
          this.spriteFrames[id] = byAddress[sprite.frame];
        }
      }, this);
    }
  } // constructor

  /**
   * Swaps the room image — this is what the flick-screen transitions of the
   * original call (roomModel.setRoom), and the 256 screens composed out of
   * 45 templates are ready in the data (roomComposer.js).
   * @param {Object} room - {width, height, bitmap, attributes}.
   */
  setRoom(room) {
    this.room = {
      width: room.width || 256,
      height: room.height || 176,
      bitmap: ZXVideoRAM.decode(room.bitmap),
      attributes: ZXVideoRAM.decode(room.attributes)
    };
    this.roomAsVideoRAM = null;
  } // setRoom

  /**
   * A byte as two hex digits, the way the disassembly writes it — the sandbox
   * of M3 prints Sabreman's record with it.
   * @param {number} byte - The value.
   * @returns {string} Two upper case hex digits.
   */
  static hex(byte) {
    return '$'+('0'+(byte & 0xFF).toString(16).toUpperCase()).slice(-2);
  } // hex

  /**
   * The rectangle of the screen the room occupies: everything below the panel.
   * @returns {Object} {col, row, cols, rows} in character cells.
   */
  playArea() {
    return {
      col: 0, row: ScreenComposer.PANEL_LINES/ZXVideoRAM.CELL,
      cols: ZXVideoRAM.COLS, rows: this.room.height/ZXVideoRAM.CELL
    };
  } // playArea

  /**
   * And the same thing as the **whole 6912 bytes of video memory**, which is
   * what the machine really has.
   *
   * It has to be the whole screen and not just the play area, because the
   * original's own drawing does not stop at the edge of the play area: it
   * writes through the machine's addressing, `INC L` and all, so a sprite at
   * the right hand edge carries on eight pixels lower and a tall one near the
   * top writes over the panel. Both happen in the game — the keeper of the
   * gate is 32 pixels tall and the play area starts at y = $28 — so both are
   * reproduced rather than clipped away, and tools/matchsprites.js checks all
   * 6912 bytes against what the original left in video memory.
   *
   * @param {Object} [state] - The 'frame' message of the worker.
   * @returns {ZXVideoRAM} A fresh copy — the cached room stays untouched.
   */
  composeVideoRAM(state) {
    return this.composeInto(new ZXVideoRAM(), state);
  } // composeVideoRAM

  /**
   * The whole screen as plain bytes, which is the shape the offline tools
   * compare: 6912 bytes, $4000-$57FF then $5800-$5AFF.
   * @param {Object} [state] - The 'frame' message of the worker.
   * @returns {Uint8Array} A fresh copy every time.
   */
  composeScreen(state) {
    return this.composeVideoRAM(state).bytes;
  } // composeScreen

  /**
   * Composes the frame into video memory that is already there, so that the
   * per-frame path does not allocate 6912 bytes it is only going to throw
   * away. The memory starts from the clean room and everything is drawn on
   * top of it — the original rubs its sprites out by XORing them again, this
   * remake simply starts afresh (a difference in method, not in picture).
   * @param {ZXVideoRAM} videoRAM - The memory to compose into.
   * @param {Object} [state] - The 'frame' message of the worker.
   * @returns {ZXVideoRAM} The same memory, for chaining.
   */
  composeInto(videoRAM, state) {
    videoRAM.restore(this.roomVideoRAM());
    var entities = (state && state.entities) || [];
    for (var i = 0; i < entities.length; i++) {
      this.drawEntity(videoRAM, entities[i]);
    }
    // $AECF: while the changeover delay runs his handler draws nothing, so
    // the man is not on the screen until the game lets him move
    if (state && state.sabreman && !state.sabreman.hidden) {
      this.drawEntity(videoRAM, state.sabreman);
    }
    // and the lines of text the game prints over the play area: the verse of
    // the poem, GAME OVER, the closing screen (data/text.json)
    var texts = (state && state.texts) || [];
    for (var t = 0; t < texts.length; t++) {
      this.printString(videoRAM, texts[t]);
    }
    return videoRAM;
  } // composeInto

  /**
   * One line of the game's own text, printed the way PrintStringColour
   * ($B53D) prints it: the position is in **pixels**, the attribute goes into
   * one cell per character, and the glyphs come out of the ZX Spectrum ROM
   * font, because ★ the game has no character set of its own (M1, $B589).
   *
   * A glyph is eight `INC H` down from the top of its cell with no crossing of
   * the thirds, and the column steps with `INC L` inside the page — so a line
   * that runs off the right hand edge comes back on the left, exactly as a
   * sprite does.
   * @param {ZXVideoRAM} videoRAM - Video memory, changed in place.
   * @param {Object} line - {x, y, attribute, text} out of data/text.json.
   */
  printString(videoRAM, line) {
    var at = ZXVideoRAM.addressOf(line.x, line.y);
    var l = at.l;
    var h = at.h;
    var cell = ZXVideoRAM.attributeAddressOf(line.x, line.y);
    var text = String(line.text || '');
    for (var i = 0; i < text.length; i++) {
      var glyph = this.font[text.charAt(i)];
      if (glyph) {
        for (var row = 0; row < 8; row++) {         // $B599: eight INC H
          videoRAM.poke(h+row, l, glyph[row]);
        }
      }
      l = (l+1) & 0xFF;                             // $B5A7: INC L
      videoRAM.pokeAddress(cell, line.attribute);   // $B555
      cell = (cell & 0xFF00) | ((cell+1) & 0xFF);   // $B556: INC L
    }
  } // printString

  /**
   * The room as a whole screen, ready for the entities to be drawn into. The
   * conversion is cached, because between two flick-screens the room does not
   * change and a frame would otherwise pay for it twice.
   * @returns {ZXVideoRAM} The cache itself — copy it before drawing into it.
   */
  roomVideoRAM() {
    if (!this.roomAsVideoRAM) {
      this.roomAsVideoRAM = new ZXVideoRAM()
        .setLinear(this.playArea(), this.room.bitmap, this.room.attributes);
    }
    return this.roomAsVideoRAM;
  } // roomVideoRAM

  /**
   * Draws one entity the way the game draws it — $B969 works out the address
   * and the shift, $BA8C lays the rows in and $BB24 writes the attribute.
   *
   * Four details of the original are reproduced here because all four are
   * visible on screen:
   *
   * - the pixels are **XORed** in, not ORed, so two entities on the same spot
   *   cut holes in each other (that is also how the game erases them: it
   *   draws the same frame at the old place again);
   * - the frame is drawn **upwards** from its y ($BAFB does DEC H), because y
   *   is the sprite's bottom row — and the rows of the frame are stored
   *   bottom first, which is why they are read forwards while the screen goes
   *   up;
   * - ★ the address arithmetic is the **machine's**, `INC L` inside a page and
   *   all: a sprite that runs off the right hand edge does not stop, it comes
   *   back on the left eight pixels lower. The one write the original does
   *   guard is the **last** one of a row ($BAEE: AND $1F / JR Z), which is why
   *   a sprite at the very edge loses its last byte instead of wrapping it;
   * - the attribute is written **only into cells whose paper is black**
   *   ($BB47: AND %00111000 / JR NZ), so an entity does not repaint the
   *   jungle it walks past. That, with one attribute for a 16 pixel wide
   *   figure, is where the colour clash of Sabre Wulf comes from.
   *
   * Checked byte for byte against the original by tools/matchsprites.js.
   * @param {ZXVideoRAM} videoRAM - Video memory, changed in place.
   * @param {Object} entity - {sprite, x, y, colour, flash} out of the worker.
   */
  drawEntity(videoRAM, entity) {
    var frame = this.spriteFrames[entity.sprite];
    if (!frame) {
      return;
    }
    var x = entity.x & 0xFF;
    var shift = x & 7;
    // $B8AD: the screen address of (x, y), the ULA's own layout
    var at = ZXVideoRAM.addressOf(x, entity.y);
    var l = at.l;
    var h = at.h;
    for (var row = 0; row < frame.height; row++) {
      l = this.drawRow(videoRAM, frame, row, h, l, shift);
      // $BAFB: one pixel line up, and across a character row L drops by $20 —
      // and when that borrows, the original returns without putting H back,
      // so the next row lands wherever the arithmetic left it
      h = (h-1) & 0xFF;
      if ((h & 7) === 7) {
        var stepped = l-0x20;
        l = stepped & 0xFF;
        if (stepped >= 0) {
          h = (h+8) & 0xFF;
        }
      }
    }
    this.drawAttributes(videoRAM, frame, entity);
  } // drawEntity

  /**
   * One row of a frame ($BA8C and the unrolled blitter behind it).
   *
   * The game keeps a table of pre-shifted words at $F000-$FFFF ($B902) and
   * writes each source byte as two halves, the high one where the byte starts
   * and the low one in the next column, which is also where the next byte's
   * high half goes. With the sprite on a character boundary the high half is
   * zero, and the routine jumps six bytes further in to skip its INC L — which
   * is why an aligned sprite lands one column to the left of a shifted one.
   *
   * @param {ZXVideoRAM} videoRAM - Video memory, changed in place.
   * @param {Object} frame - The sprite frame.
   * @param {number} row - Which row of it.
   * @param {number} h - The high half of the screen address.
   * @param {number} l - And the low half.
   * @param {number} shift - x & 7.
   * @returns {number} L where the row started, for the caller to step on.
   */
  drawRow(videoRAM, frame, row, h, l, shift) {
    var start = l;
    for (var i = 0; i < frame.width; i++) {
      var source = frame.bitmap[row*frame.width+i];
      var high = shift ? (source >> shift) : 0;
      var low = shift ? ((source << (8-shift)) & 0xFF) : source;
      if (i || shift) {
        videoRAM.poke(h, l, high, 'xor');
        l = (l+1) & 0xFF;
      }
      // $BAEE: the last write of a row is the only one that is guarded
      if (i+1 < frame.width || (l & 0x1F) !== 0) {
        videoRAM.poke(h, l, low, 'xor');
      }
    }
    return start;
  } // drawRow

  /**
   * $BB24 — the entity's attribute, from the character row of its y upwards.
   *
   * ★ And only into cells whose paper is black, which is the rule the whole
   * look of the game hangs on: the jungle keeps its colours and the figure
   * takes the black between them.
   * @param {ZXVideoRAM} videoRAM - Video memory, changed in place.
   * @param {Object} frame - The sprite frame.
   * @param {Object} entity - {x, y, colour, flash}.
   */
  drawAttributes(videoRAM, frame, entity) {
    var x = entity.x & 0xFF;
    var y = entity.y & 0xFF;
    // $96A6 ($B97A): the frame's width in cells, one more when it is shifted
    var cols = (frame.width+((x & 7) ? 1 : 0)) || 256;
    // $BB31: as many rows as the frame reaches into, from the row of y up
    var rows = (((frame.height+((~y) & 7)+8) >> 3) & 0x1F) || 256;
    // $B8DD: the attribute address of (x, y)
    var at = ZXVideoRAM.attributeAddressOf(x, y);
    var colour = entity.flash ? ScreenComposer.FLASH_COLOUR : entity.colour;
    for (var r = 0; r < rows; r++) {
      var h = (at >> 8) & 0xFF;
      var l = at & 0xFF;
      for (var c = 0; c < cols; c++) {
        var cell = ((h << 8) | l)-ZXVideoRAM.BASE;
        // $BB47: AND %00111000 / JR NZ — black paper only
        if (cell >= ZXVideoRAM.ATTRIBUTES_OFFSET && cell < ZXVideoRAM.BYTES
            && !(videoRAM.peekOffset(cell) & 0x38)) {
          videoRAM.pokeOffset(cell, colour);
        }
        l = (l+1) & 0xFF;                           // $BB4D: INC L, in the page
      }
      at = (at-0x20) & 0xFFFF;                      // $BB55: SBC HL,BC — a row up
    }
  } // drawAttributes

  /**
   * Renders the panel (256x16) in the character set the game prints with.
   *
   * The layout is the measured one (screen_layout.md chap. 2): 1UP, the lives
   * and the life icon, HI and 2UP on row 0, three six-digit scores on row 1.
   * Both rows get their attribute in one pass, the way GameInitialisation does
   * it ($996F sets the whole of row 0 to $47, $997C the whole of row 1 to $46)
   * — which is why an empty cell of row 0 is $47 and not zero.
   * @param {Uint8ClampedArray} rgba - Target buffer, 256*16*4 bytes.
   * @param {Object} panel - {score, hiScore, score2, lives, player}.
   *        `lives` of null draws no lives at all, the way the menu shows them.
   */
  renderPanel(rgba, panel, flashState) {
    var memory = this.panelMemory(panel);
    ZXVideoRAM.paintLinear(rgba, memory.bitmap, memory.attributes,
                           ZXVideoRAM.COLS, 2, flashState);
  } // renderPanel

  /**
   * The video memory of the panel — 512 bytes of bitmap and 64 attributes,
   * before it becomes pixels. This is what the machine holds, so it is also
   * what tools/matchpanel.js compares against captured frames of the original
   * byte for byte (and tools/matchpanel.py checks the same thing with an
   * independent implementation, so a divergence between the two shows up as
   * well).
   * @param {Object} panel - {score, hiScore, score2, lives, player, labelFlash,
   *        twoPlayers}: `twoPlayers` prints 2UP and its score as the original does;
   *        `labelFlash` puts the FLASH bit on the three cells of `player`'s
   *        score label, which is what $AEA1 does while the changeover delay
   *        runs and $AEBD undoes when it is over.
   * @returns {Object} {bitmap, attributes}.
   */
  panelMemory(panel) {
    var cols = ZXVideoRAM.COLS;
    var layout = ScreenComposer.PANEL;
    var bitmap = new Uint8Array(cols*16);
    var attributes = new Uint8Array(cols*2);
    for (var col = 0; col < cols; col++) {
      attributes[col] = 0x47;
      attributes[cols+col] = 0x46;
    }
    this.writeText(bitmap, attributes, cols, layout.label1UP.row,
                   layout.label1UP.col, '1UP', layout.label1UP.attr);
    this.writeText(bitmap, attributes, cols, layout.labelHI.row,
                   layout.labelHI.col, 'HI', layout.labelHI.attr);
    // ★ the original prints 2UP and its score whether one plays or two; the
    // remake offers one player only (2026-09-07, ZADANI chap. 2) and leaves
    // them out unless asked — tools/matchpanel.js asks, to compare with the
    // original's frames byte for byte
    if (panel.twoPlayers) {
      this.writeText(bitmap, attributes, cols, layout.label2UP.row,
                     layout.label2UP.col, '2UP', layout.label2UP.attr);
    }
    if (panel.labelFlash) {
      var label = (panel.player === 2) ? layout.label2UP : layout.label1UP;
      for (var cell = 0; cell < 3; cell++) {             // $AEB5: OR $80
        attributes[label.row*cols+label.col+cell] |= 0x80;
      }
    }
    if (panel.lives !== null && panel.lives !== undefined) {
      // one digit only — that is all the panel has room for, and it is what
      // makes the contemporary claim of a ceiling of nine lives plausible
      // (unconfirmed, ZADANI chap. 7)
      this.writeText(bitmap, attributes, cols, layout.lives.row,
                     layout.lives.col,
                     String(Math.max(0, Math.min(9, panel.lives))),
                     layout.lives.attr);
      var icon = this.sprites['panel.life'];
      if (icon) {
        for (var pixel = 0; pixel < 8; pixel++) {
          bitmap[pixel*cols+layout.lifeIcon.col] = icon.bitmap[pixel*icon.cols];
        }
        attributes[layout.lifeIcon.col] = icon.attributes[0];
      }
    }
    this.writeText(bitmap, attributes, cols, layout.score1UP.row,
                   layout.score1UP.col, ScreenComposer.score(panel.score),
                   layout.score1UP.attr);
    this.writeText(bitmap, attributes, cols, layout.scoreHI.row,
                   layout.scoreHI.col, ScreenComposer.score(panel.hiScore),
                   layout.scoreHI.attr);
    if (panel.twoPlayers) {
      this.writeText(bitmap, attributes, cols, layout.score2UP.row,
                     layout.score2UP.col, ScreenComposer.score(panel.score2),
                     layout.score2UP.attr);
    }
    return {bitmap: bitmap, attributes: attributes};
  } // panelMemory

  /**
   * A score as the six digits the original's panel prints (three BCD bytes,
   * $9698 and $969B).
   * @param {number} value - The score.
   * @returns {string} Six characters.
   */
  static score(value) {
    var text = String(Math.max(0, Math.floor(value || 0)));
    if (text.length > ScreenComposer.PANEL.digits) {
      text = text.slice(-ScreenComposer.PANEL.digits);
    }
    while (text.length < ScreenComposer.PANEL.digits) {
      text = '0'+text;
    }
    return text;
  } // score

  /**
   * Writes a string with the game's character set into a bitmap.
   * @param {Uint8Array} bitmap - Target bitmap.
   * @param {Uint8Array} attributes - Target attributes.
   * @param {number} cols - Width of the target in cells.
   * @param {number} row - Character row.
   * @param {number} col - First character column.
   * @param {string} text - The text.
   * @param {number} attr - The attribute byte given to every cell written.
   */
  writeText(bitmap, attributes, cols, row, col, text, attr) {
    for (var i = 0; i < text.length; i++) {
      var target = col+i;
      if (target < 0 || target >= cols) {
        continue;
      }
      var glyph = this.font[text.charAt(i)];
      for (var pixel = 0; pixel < 8; pixel++) {
        bitmap[(row*8+pixel)*cols+target] = glyph ? glyph[pixel] : 0;
      }
      attributes[row*cols+target] = attr;
    }
  } // writeText

} // ScreenComposer
