#!/usr/bin/env node
/**
 * Porovná panel **skutečným kódem, který jde do prohlížeče**, se snímky
 * z běžícího originálu, bajt po bajtu.
 *
 *   ./tools/matchpanel.js [--verbose]
 *
 * `matchpanel.py` staví panel vlastní, nezávislou implementací; tenhle nástroj
 * pouští `app/screenComposer.js` – tedy to, co panel doopravdy kreslí – a čeká
 * u všech tří referenčních snímků **nulu rozdílů** v 512 bajtech bitmapy
 * a 64 atributech. Dvě věci se tím hlídají naráz:
 *
 * 1. že panel remaku je bajt po bajtu panel originálu,
 * 2. že se `screenComposer.js` a `matchpanel.py` nerozešly.
 *
 * Glyfy se berou z **tabulky svision** (`app/svision/fonts/zx-rom.ch8.hex.txt`),
 * protože ★ hra vlastní znakovou sadu nemá – tiskne ROM fontem ZX Spectra
 * (`PrintScreen`, `$B589`, glyf z `CHARS` `$5C36`). Tohle porovnání je zároveň
 * důkaz toho tvrzení: s jiným fontem by se panel neshodl.
 * Viz `sources/docs/disasm_notes.md` §8.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const url = require('url');

const ROOT = path.join(__dirname, '..');
const PANEL_ROWS = 2;
// znaková sada svision začíná mezerou; ZXFonts8x8.fontsChars je tentýž seznam
const FONT_CHARS = ' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_£abcdefghijklmnopqrstuvwxyz{|}~©';

// (snímek, hodnoty, které jsou na něm vidět) – táž tabulka jako v matchpanel.py
const FRAMES = [
  ['sources/media/screens/title_menu.scr',
   {score: 0, hiScore: 102275, score2: 0, lives: null}],
  ['sources/media/screens/gameplay_start.scr',
   {score: 0, hiScore: 102275, score2: 0, lives: 4}],
  ['sources/media/screens/running_screen.scr',
   {score: 1950, hiScore: 102275, score2: 0, lives: 4}],
];

function screenOffset(y) {
  const third = y >> 6, charRow = (y >> 3) & 7, pix = y & 7;
  return (third << 11) | (pix << 8) | (charRow << 5);
}

async function main() {
  const verbose = process.argv.includes('--verbose');

  global.atob = (data) => Buffer.from(data, 'base64').toString('binary');
  // screenComposer.js teď importuje ZXVideoRAM ze svision, takže hlavička
  // potřebuje window.srcVersion — shim se musí načíst jako první (R-001)
  await import(url.pathToFileURL(path.join(ROOT, 'app/svision/tools/nodeEnv.mjs')).href);
  // app/screenComposer.js je ES modul a importuje se přímo ze zdroje (R-001)
  const { ScreenComposer } = await import(url.pathToFileURL(path.join(ROOT, 'app/screenComposer.js')).href);

  const room = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/room000.json'), 'utf8'));
  const sprites = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/sprites.json'), 'utf8'));
  const fontData = fs.readFileSync(path.join(ROOT, 'app/svision/fonts/zx-rom.ch8.hex.txt'),
                                   'utf8').trim();
  if (fontData.length !== FONT_CHARS.length*16) {
    console.error('tabulka fontu ma %d hex znaku, znaku je %d (cekam %d)',
                  fontData.length, FONT_CHARS.length, FONT_CHARS.length*16);
    process.exit(1);
  }

  const render = new ScreenComposer(room, {chars: FONT_CHARS, data: fontData}, sprites);

  let bad = 0;
  for (const [file, panel] of FRAMES) {
    const scr = fs.readFileSync(path.join(ROOT, file));
    if (scr.length !== 6912) {
      console.error('%s: cekam 6912 B .scr, mam %d', file, scr.length);
      process.exit(1);
    }
    // the original's frames carry 2UP, the remake's panel does not by default
    const memory = render.panelMemory(Object.assign({twoPlayers: true}, panel));
    const originalBitmap = Buffer.alloc(32*8*PANEL_ROWS);
    for (let y = 0; y < PANEL_ROWS*8; y++) {
      scr.copy(originalBitmap, y*32, screenOffset(y), screenOffset(y)+32);
    }
    const originalAttrs = scr.subarray(6144, 6144+32*PANEL_ROWS);

    const badBits = [];
    for (let i = 0; i < memory.bitmap.length; i++) {
      if (memory.bitmap[i] !== originalBitmap[i]) { badBits.push(i); }
    }
    const badAttrs = [];
    for (let i = 0; i < memory.attributes.length; i++) {
      if (memory.attributes[i] !== originalAttrs[i]) { badAttrs.push(i); }
    }
    console.log('%s (1UP %d, HI %d, 2UP %d, zivoty %s):', path.basename(file),
                panel.score, panel.hiScore, panel.score2, panel.lives);
    console.log('  bitmapa:  %d / %d bajtu se lisi', badBits.length, memory.bitmap.length);
    console.log('  atributy: %d / %d bajtu se lisi', badAttrs.length, memory.attributes.length);
    if (verbose || badBits.length || badAttrs.length) {
      badBits.slice(0, 16).forEach((i) => console.log(
        '    bitmapa sloupec %d, radek %d: %s != %s', i % 32, Math.floor(i/32/8),
        memory.bitmap[i].toString(16), originalBitmap[i].toString(16)));
      badAttrs.slice(0, 16).forEach((i) => console.log(
        '    atribut sloupec %d, radek %d: %s != %s', i % 32, Math.floor(i/32),
        memory.attributes[i].toString(16), originalAttrs[i].toString(16)));
    }
    if (!badBits.length && !badAttrs.length) {
      console.log('  panel souhlasi s originalem bajt po bajtu');
    }
    bad += badBits.length+badAttrs.length;
  }

  if (bad) {
    process.exit(1);
  }
  console.log('vsech %d snimku: nula rozdilu (app/screenComposer.js)', FRAMES.length);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
