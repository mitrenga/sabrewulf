#!/usr/bin/env node
/**
 * Porovná obraz remaku s obrazem originálu **buňku po buňce** – i se sprity.
 *
 *   PYTHONPATH=tools/vendor ./tools/tracescreen.py
 *   ./tools/matchsprites.js [--verbose] [--case jmeno]
 *
 * `tracescreen.py` nechá **originál nakreslit** místnost a do ní jednu entitu
 * a opíše videopaměť. Tenhle nástroj proti tomu pustí `app/screenComposer.js` –
 * kód, který obraz doopravdy skládá v prohlížeči – nad `data/spriteframes.json`
 * a porovná **5632 B bitmapy a 704 atributů** na obrazovku. Cíl je nula
 * rozdílů.
 *
 * M2 tou samou disciplínou uzavřel místnost (`matchscreen.py` a
 * `matchrooms.js`, 305 obrazovek). Tohle je její druhá půlka: **attribute
 * clash Sabre Wulf nevzniká v kulise, ale právě tady** – `$BB47` píše atribut
 * jen do buněk, jejichž papír je černý, a jedna barva platí pro celou buňku
 * 8 × 8, takže šestnáct pixelů široká postava přebarví dvě až tři.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const url = require('url');

const ROOT = path.join(__dirname, '..');
const SCREEN = 6912;
const PANEL_LINES = 16;
const COLS = 32;
const PLAY_ROWS = 176;
const BITMAP_BYTES = COLS*PLAY_ROWS;
const ATTRIBUTE_BYTES = COLS*(PLAY_ROWS/8);
const SHOW = 4;

function fail(message) {
  console.error(message);
  process.exit(1);
}

/** adresa řádku obrazovky ZX Spectra – ta nelineární */
function screenOffset(line) {
  return ((line & 0xC0) << 5) | ((line & 0x07) << 8) | ((line & 0x38) << 2);
}

/** hrací plocha ze surové videopaměti: řádek po řádku, jak ji drží remake */
function playArea(screen, at) {
  const bitmap = new Uint8Array(BITMAP_BYTES);
  for (let line = PANEL_LINES, row = 0; line < 192; line++, row++) {
    for (let col = 0; col < COLS; col++) {
      bitmap[row*COLS+col] = screen[at+screenOffset(line)+col];
    }
  }
  const attributes = new Uint8Array(ATTRIBUTE_BYTES);
  for (let i = 0; i < ATTRIBUTE_BYTES; i++) {
    attributes[i] = screen[at+0x1800+(PANEL_LINES/8)*COLS+i];
  }
  return {width: 256, height: PLAY_ROWS, bitmap: bitmap, attributes: attributes};
}

/** mapa znakových buněk, ve kterých se to liší */
function diffMap(mine, theirs) {
  const rows = [];
  for (let row = 0; row < PLAY_ROWS/8; row++) {
    let line = '';
    for (let col = 0; col < COLS; col++) {
      let bad = mine.attributes[row*COLS+col] !== theirs.attributes[row*COLS+col];
      for (let p = 0; p < 8 && !bad; p++) {
        bad = mine.bitmap[(row*8+p)*COLS+col] !== theirs.bitmap[(row*8+p)*COLS+col];
      }
      line += bad ? '#' : '.';
    }
    rows.push(line);
  }
  return rows;
}

async function main() {
  const verbose = process.argv.includes('--verbose');
  const only = [];
  process.argv.forEach((arg, index) => {
    if (arg === '--case') { only.push(process.argv[index+1]); }
  });

  const blobPath = path.join(ROOT, 'build/sprite-screens.bin');
  const indexPath = path.join(ROOT, 'build/sprite-cases.json');
  if (!fs.existsSync(blobPath) || !fs.existsSync(indexPath)) {
    fail('chybi build/sprite-screens.bin – spust nejdriv:\n'
         + '  PYTHONPATH=tools/vendor ./tools/tracescreen.py');
  }
  const screens = fs.readFileSync(blobPath);
  const index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
  if (screens.length !== index.cases.length*SCREEN) {
    fail('build/sprite-screens.bin ma '+screens.length+' B, cekam '
         + index.cases.length*SCREEN);
  }

  global.atob = (data) => Buffer.from(data, 'base64').toString('binary');
  // screenComposer.js teď importuje ZXVideoRAM ze svision, takže hlavička
  // potřebuje window.srcVersion — shim se musí načíst jako první (R-001)
  await import(url.pathToFileURL(path.join(ROOT, 'app/svision/tools/nodeEnv.mjs')).href);
  // oba jsou ES moduly a importují se přímo ze zdroje (R-001)
  const { ScreenComposer } = await import(url.pathToFileURL(path.join(ROOT, 'app/screenComposer.js')).href);
  const { RoomComposer } = await import(url.pathToFileURL(path.join(ROOT, 'app/roomComposer.js')).href);

  const spriteFrames = JSON.parse(fs.readFileSync(
    path.join(ROOT, 'data/spriteframes.json'), 'utf8'));
  const scenery = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/scenery.json'), 'utf8'));
  const rooms = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/rooms.json'), 'utf8'));
  const texts = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/text.json'), 'utf8'));
  // znaková sada svision = ROM font ZX Spectra, kterým hra tiskne (M1)
  const FONT_CHARS = ' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                   + '[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~\u00a9';
  const fontData = fs.readFileSync(
    path.join(ROOT, 'app/svision/fonts/zx-rom.ch8.hex.txt'), 'utf8').replace(/\s+/g, '');
  const composer = new RoomComposer(scenery, rooms);

  // prázdné místnosti, do kterých originál kreslil: bereme je z nahrávky, aby
  // se tady porovnávalo **jen kreslení spritu** – že místnost sedí, hlídá
  // tools/matchrooms.js na 305 obrazovkách
  const emptyRoom = {};
  Object.keys(index.rooms).forEach((template) => {
    emptyRoom[template] = playArea(Buffer.from(index.rooms[template], 'hex'), 0);
  });

  const render = new ScreenComposer(emptyRoom[Object.keys(emptyRoom)[0]]
                                  || composer.composeTemplate(8),
                                  {chars: FONT_CHARS, data: fontData},
                                  null, spriteFrames);

  /**
   * ★ Obrazovka básně, jak ji staví $A207 a $A01B: smazaná plocha, obrázek
   * amuletu (každý kus svým blokem atributů podle toho, jestli ho hráč má)
   * a **jedna** sloka – ta, která odpovídá počtu kusů. Nula kusů dostane
   * slokou čtvrtou, protože řetěz `DEC A / JR Z` v $A028 nulu nechytí; v hře
   * to nenastane, ale reprodukuje se to.
   */
  function poemScreen(pieces) {
    composer.clear();
    texts.amulet.pieces.forEach((entry, index) => {
      const graphic = texts.amulet.graphics[entry.graphic];
      const collected = (pieces >> index) & 1;
      composer.drawPiece({
        width: graphic.width, height: graphic.height,
        attrRows: graphic.attrRows, attrCols: graphic.attrCols,
        bitmap: RoomComposer.decode(graphic.bitmap),
        attributes: RoomComposer.decode(collected ? graphic.attributes
                                                  : graphic.attributesDull)
      }, entry.x, entry.y);
    });
    render.setRoom(composer.playArea());
    let count = 0;
    for (let bit = 0; bit < texts.poem.pieces; bit++) {
      count += (pieces >> bit) & 1;
    }
    const stanza = texts.poem.stanzas[(count >= 1 && count <= 3) ? count-1
                                      : texts.poem.stanzas.length-1];
    return render.composeScreen({texts: stanza.lines});
  }

  let checks = 0, differences = 0, outside = 0;
  const counts = {};
  index.cases.forEach((entry) => {
    if (only.length && only.indexOf(entry.case) < 0) { return; }
    const at = entry.index*SCREEN;
    let got, label;
    if (entry.case === 'poem') {
      got = poemScreen(entry.pieces);
      label = 'poem['+entry.index+'] kusy=$'+entry.pieces.toString(16);
    } else {
      render.setRoom(emptyRoom[String(entry.template)]);
      got = render.composeScreen({
        sabreman: {sprite: entry.sprite, x: entry.x, y: entry.y,
                   colour: entry.colour}
      });
      label = entry.case+'['+entry.index+'] sprite=$'+entry.sprite.toString(16)
        + ' x=' + entry.x + ' y=' + entry.y
        + ' predloha=$'+entry.template.toString(16)
        + ' barva=$'+entry.colour.toString(16);
    }
    // porovnává se **celá videopaměť**, ne jen hrací plocha: originálovo
    // kreslení se u okrajů přetáčí a vysoký sprite píše i do panelu, a to obojí
    // se reprodukuje, ne ořezává
    let bad = 0;
    let spilled = false;
    for (let i = 0; i < SCREEN; i++) {
      checks++;
      if (got[i] !== screens[at+i]) { bad++; }
    }
    for (let line = 0; line < PANEL_LINES && !spilled; line++) {
      for (let col = 0; col < COLS; col++) {
        if (screens[at+screenOffset(line)+col]) { spilled = true; break; }
      }
    }
    for (let i = 0; i < 2*COLS && !spilled; i++) {
      if (screens[at+0x1800+i]) { spilled = true; }
    }
    if (spilled) { outside++; }
    counts[entry.case] = counts[entry.case] || {runs: 0, bad: 0, cases: 0};
    counts[entry.case].runs++;
    if (bad) {
      counts[entry.case].bad += bad;
      counts[entry.case].cases++;
      differences += bad;
      if (counts[entry.case].cases <= SHOW) {
        console.log('%s: %d bajtu se lisi', label, bad);
        if (verbose) {
          diffMap(playArea(got, 0), playArea(screens, at))
            .forEach((line) => console.log('  '+line));
        }
      }
    }
  });

  if (verbose) {
    Object.keys(counts).sort().forEach((name) => {
      console.log('%s %s obrazovek  %s obrazovek s rozdilem  %d bajtu',
                  name.padEnd(10), String(counts[name].runs).padStart(4),
                  String(counts[name].cases).padStart(4), counts[name].bad);
    });
  }
  if (outside) {
    console.log('%d obrazovek, na kterych original psal i do panelu – '
                + 'a remake to dela taky', outside);
  }

  console.log('%d kontrol na %d obrazovkach, %d rozdilu',
              checks, index.cases.length, differences);
  process.exit(differences ? 1 : 0);
}

main().catch((error) => { console.error(error); process.exit(1); });
