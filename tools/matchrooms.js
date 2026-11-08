#!/usr/bin/env node
/**
 * Porovná obrazovky **skutečným kódem, který jde do prohlížeče**, s bajty,
 * které nakreslil originál – bajt po bajtu.
 *
 *   PYTHONPATH=tools/vendor ./tools/matchscreen.py --dump
 *   ./tools/matchrooms.js [--verbose]
 *
 * `matchscreen.py` porovnává s originálem repliku v pythonu (`tools/roomlib.py`),
 * ze které vznikají data remaku. Tenhle nástroj pouští `app/roomComposer.js` –
 * tedy to, co obrazovku doopravdy skládá v prohlížeči – nad `data/scenery.json`
 * a `data/rooms.json` a čeká u všech **48 předloh a u místnosti pod hlavním
 * menu nulu rozdílů** v 5632 bajtech bitmapy a 704 atributech. Hlídají se tím
 * dvě věci naráz:
 *
 * 1. že obrazovka remaku je bajt po bajtu obrazovka originálu,
 * 2. že se `roomComposer.js` a `roomlib.py` nerozešly.
 *
 * Referenci (`build/screens.bin`) kreslí **originál sám** v simulátoru –
 * `matchscreen.py --dump` mu do paměti položí `CALL ClearPlayArea` /
 * `CALL DrawRoom` a opíše, co po nich zůstalo ve videopaměti. Viz
 * `sources/docs/disasm_notes.md` §12.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const url = require('url');

const ROOT = path.join(__dirname, '..');
const BITMAP_BYTES = 5632;
const ATTRIBUTE_BYTES = 704;
const TEMPLATES = 48;
/** 48 předloh a za nimi místnost pod hlavním menu ($61C6) */
const SCREENS = TEMPLATES+1;

async function main() {
  const verbose = process.argv.includes('--verbose');
  const reference = path.join(ROOT, 'build/screens.bin');
  if (!fs.existsSync(reference)) {
    console.error('chybi %s – spust nejdriv:\n'
                  + '  PYTHONPATH=tools/vendor ./tools/matchscreen.py --dump',
                  path.relative(ROOT, reference));
    process.exit(1);
  }
  const screens = fs.readFileSync(reference);
  if (screens.length !== SCREENS*(BITMAP_BYTES+ATTRIBUTE_BYTES)) {
    console.error('%s ma %d B, cekam %d – reference je stara, dumpni ji znovu:\n'
                  + '  PYTHONPATH=tools/vendor ./tools/matchscreen.py --dump',
                  reference, screens.length,
                  SCREENS*(BITMAP_BYTES+ATTRIBUTE_BYTES));
    process.exit(1);
  }

  global.atob = (data) => Buffer.from(data, 'base64').toString('binary');
  // app/roomComposer.js je ES modul a importuje se přímo ze zdroje (R-001)
  const { RoomComposer } = await import(url.pathToFileURL(path.join(ROOT, 'app/roomComposer.js')).href);

  const scenery = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/scenery.json'), 'utf8'));
  const rooms = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/rooms.json'), 'utf8'));
  const world = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/world.json'), 'utf8'));
  const composer = new RoomComposer(scenery, rooms);

  let bad = 0;
  for (let template = 0; template < TEMPLATES; template++) {
    const composed = composer.composeTemplate(template);
    if (!composed) {
      console.error('predloha $%s: nepodarilo se poskladat',
                    template.toString(16).toUpperCase().padStart(2, '0'));
      bad++;
      continue;
    }
    const base = template*(BITMAP_BYTES+ATTRIBUTE_BYTES);
    let bitmapDiff = 0, attributeDiff = 0;
    for (let i = 0; i < BITMAP_BYTES; i++) {
      if (composed.bitmap[i] !== screens[base+i]) {
        bitmapDiff++;
      }
    }
    for (let i = 0; i < ATTRIBUTE_BYTES; i++) {
      if (composed.attributes[i] !== screens[base+BITMAP_BYTES+i]) {
        attributeDiff++;
      }
    }
    if (bitmapDiff || attributeDiff) {
      bad++;
      console.error('predloha $%s: %d rozdilu bitmapy, %d atributu',
                    template.toString(16).toUpperCase().padStart(2, '0'),
                    bitmapDiff, attributeDiff);
    } else if (verbose) {
      console.log('predloha $%s: nula rozdilu',
                  template.toString(16).toUpperCase().padStart(2, '0'));
    }
  }

  // mistnost pod hlavnim menu ($61C6): 49. predloha v tomtez formatu, jen mimo
  // RoomTable. Tou se kresli dzungle pod menu, hall of fame a ABOUT GAME
  // (app/menuModel.js, hallOfFameModel.js, aboutModel.js), takze musi sedet
  // stejne jako kterakoli jina.
  if (!composer.composeMainMenu()) {
    console.error('mainMenu: nepodarilo se poskladat – chybi v data/rooms.json? '
                  + 'pust PYTHONPATH=tools/vendor ./tools/dumprooms.py');
    bad++;
  } else {
    const menu = composer.playArea();
    const menuBase = TEMPLATES*(BITMAP_BYTES+ATTRIBUTE_BYTES);
    let menuBitmapDiff = 0, menuAttributeDiff = 0;
    for (let i = 0; i < BITMAP_BYTES; i++) {
      if (menu.bitmap[i] !== screens[menuBase+i]) {
        menuBitmapDiff++;
      }
    }
    for (let i = 0; i < ATTRIBUTE_BYTES; i++) {
      if (menu.attributes[i] !== screens[menuBase+BITMAP_BYTES+i]) {
        menuAttributeDiff++;
      }
    }
    if (menuBitmapDiff || menuAttributeDiff) {
      bad++;
      console.error('mainMenu ($61C6): %d rozdilu bitmapy, %d atributu',
                    menuBitmapDiff, menuAttributeDiff);
    } else if (verbose) {
      console.log('mainMenu ($61C6): nula rozdilu');
    }
  }

  // a jeste ze mrizka sveta sedi na predlohy: vsech 256 obrazovek se poskladat
  let rooms256 = 0;
  for (let row = 0; row < world.rows; row++) {
    for (let column = 0; column < world.columns; column++) {
      if (composer.composeRoom(world, column, row)) {
        rooms256++;
      }
    }
  }
  if (rooms256 !== world.roomsCount) {
    console.error('poskladano %d obrazovek z %d', rooms256, world.roomsCount);
    bad++;
  }

  // a startovni obrazovka (8,10, predloha $08) proti tem samym bajtum
  const start = world.start;
  const startRoom = composer.composeRoom(world, start.column, start.row);
  const startBase = parseInt(start.template.substring(1), 16)*(BITMAP_BYTES+ATTRIBUTE_BYTES);
  let startDiff = 0;
  for (let i = 0; i < BITMAP_BYTES; i++) {
    if (startRoom.bitmap[i] !== screens[startBase+i]) {
      startDiff++;
    }
  }
  if (startDiff) {
    console.error('startovni obrazovka %d,%d (predloha %s): %d rozdilu',
                  start.column, start.row, start.template, startDiff);
    bad++;
  } else {
    console.log('startovni obrazovka %d,%d = predloha %s: nula rozdilu',
                start.column, start.row, start.template);
  }

  console.log('%d predloh, mistnost pod menu a %d obrazovek, %d B bitmapy + '
              + '%d B atributu na obrazovku: %s', TEMPLATES, rooms256,
              BITMAP_BYTES, ATTRIBUTE_BYTES,
              bad ? bad+' NESEDI' : 'NULA ROZDILU');
  process.exit(bad ? 1 : 0);
}

main();
