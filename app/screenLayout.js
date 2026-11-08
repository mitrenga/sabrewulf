// begin code

/**
 * Geometry of the Sabre Wulf screen, measured on the running original —
 * sources/docs/screen_layout.md (the panel down to the last character cell,
 * read out of the video RAM of three independent captured frames, not off a
 * photograph; tools/matchpanel.py checks it byte for byte).
 *
 * The screen is the plain ZX Spectrum one: 256x192 pixels, attributes in 8x8
 * cells. The top two character rows are the panel, the remaining 22 rows
 * (256x176) are the room. Confirmed from the code as well: ClearPlayArea
 * ($BB5C) starts at $4040 and clears only six rows of the top third,
 * "the banner takes up two".
 */
export const ScreenLayout = {

  WIDTH: 256,
  HEIGHT: 192,

  CELL: 8,
  COLS: 32,
  ROWS: 24,

  // panel: character rows 0-1, pixels y = 0..15
  PANEL_ROWS: 2,
  PANEL_HEIGHT: 16,

  // room: character rows 2-23, pixels y = 16..191
  PLAY_Y: 16,
  PLAY_ROWS: 22,
  PLAY_WIDTH: 256,
  PLAY_HEIGHT: 176,

  // The world grid, read out of Layout ($6066) in M0: 16 x 16 bytes, one per
  // screen, each byte the number of a room template in RoomTable ($6166).
  // 256 screens out of 48 templates, 45 of them used — which is the answer to
  // the contemporary complaint that the maze repeats itself
  // (sources/docs/disasm_notes.md chap. 4, data/world.json).
  WORLD_COLS: 16,
  WORLD_ROWS: 16,

  // Attribute bytes of the panel, read from the frames (screen_layout.md
  // chap. 2). Paper is black and BRIGHT is on over the whole screen, so an
  // empty cell of row 0 is $47 rather than 0.
  ATTR_VALUE: 0x47,        // bright white on black — lives, empty cells
  ATTR_LABEL: 0x45,        // bright cyan on black — 1UP / 2UP
  ATTR_HI: 0x57,           // bright white on red — HI
  ATTR_SCORE: 0x46,        // bright yellow on black — the whole of row 1

  // 50.08 Hz — 69888 T states per frame on a 3.5 MHz Z80 (hw_notes.md).
  // The game logic hangs off the ULA interrupt, so this is the simulation step.
  // ★ How many frames make one logical step of the game is still open
  // (ZADANI chap. 7, LastFrame $9696 / FrameUpdated $9697).
  FRAME_RATE: 3500000/69888

}; // ScreenLayout
