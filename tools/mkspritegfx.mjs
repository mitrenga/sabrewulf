#!/usr/bin/env node
/**
 * Převede sprity uložené jako videopaměť (bitmapa + atributy) na grafická data
 * pro `SpriteEntity`.
 *
 *     ./tools/mkspritegfx.mjs <datovy-soubor.json> [--opaque] [--dump jmeno]
 *
 * Data remaku drží grafiku **tak, jak leží v paměti stroje** – bajt na osm
 * pixelů a atribut na buňku. `SpriteEntity` ale ze ZX bitmapy nekreslí, chce
 * **mřížku znaků**, jeden znak na pixel, plus paletu, která znaky mapuje na
 * barvy. Tenhle nástroj vezme každou položku pole `sprites` daného souboru
 * (`bitmap`, `attributes`, `cols`, `rows`, `width`, `height`) a přeloží ji do
 * pole `graphics` u téhož spritu, **nekomprimovaně** – přesně v tom tvaru,
 * který `SpriteEntity` bere:
 *
 * ```js
 * var entity = new SpriteEntity(parent, x, y, false, false, 0, 0);
 * entity.setGraphicsData(data.sprites.<jmeno>.graphics);
 * ```
 *
 * Je to týž tvar, jaký vrací `SpriteTool.decode()`, takže když se to jednou
 * bude chtít zabalit (`b90`, `braille`), volající se nezmění.
 *
 * Každá barva ZX má svůj **znak** – `+` zelená, `$` jasně zelená, `^` žlutá,
 * `*` jasně červená … (tabulka `CODE_CHARS` níž; tmavá polovina palety má řídké
 * znaky, jasná husté). Mřížka se tím dá číst očima a `--dump jmeno` ji vypíše.
 * **Černá je průhledná** a píše se **mezerou**, aby v mřížce byla vidět díra;
 * kus džungle se pak dá položit na cokoli. `--opaque` z ní udělá normální barvu
 * (znak `.`, jasná `_`) a sprite bude plný obdélník.
 *
 * Hotová mřížka se kontroluje **druhým, nezávislým čtením barev**: `toGrid`
 * skládá index barvy bitovou aritmetikou nad atributem, kontrola se ptá
 * `ZXColor.penAttrColor()` / `bkAttrColor()`. Musí vyjít táž barva na každém
 * pixelu, jinak nástroj spadne.
 *
 * ★ **Kulisu tímhle nepřevádět.** Místnosti skládá `app/roomComposer.js`
 * replikou `DrawRoom` do videopaměti a kus se zapisuje natvrdo, takže pozdější
 * překryje dřívější i svými nulami; `SpriteEntity` s průhledným pozadím by ho
 * jen složila přes sebe a v šesti předlohách ze 48 by se to rozešlo o 844
 * pixelů. K tomu by nebyla mřížka atributů, na které stojí attribute clash,
 * a `matchrooms.js` by neměl co měřit. Tenhle tvar je pro dekoraci mimo
 * simulaci, ne pro to, co se porovnává s originálem.
 *
 * Nástroj soubor přepisuje, takže se pouští **až po** tom, který ho vyrábí.
 */
import path from 'node:path';
import fs from 'node:fs';
import url from 'node:url';

const ROOT = path.join(path.dirname(url.fileURLToPath(import.meta.url)), '..');

/** znak průhledného pixelu: mezera, aby v mřížce byla vidět díra */
const TRANSPARENT_CHAR = ' ';

/**
 * Znak palety pro každý ze šestnácti indexů barev ZX. Tmavá polovina dostala
 * řídké znaky, jasná husté, takže mřížka jde číst očima: `+` je zelená, `$`
 * jasně zelená, `.` černá. Žádný z nich se nemusí v JSONu escapovat a `:`
 * (výchozí `maskChar` SpriteEntity) se schválně nepoužívá. Černé znaky se
 * uplatní jen s `--opaque`, jinak je černá průhledná a bere TRANSPARENT_CHAR.
 */
const CODE_CHARS = [
  '.',  //  0 black          8 brightBlack   '_'
  ',',  //  1 blue           9 brightBlue    '!'
  '~',  //  2 red           10 brightRed     '*'
  '-',  //  3 magenta       11 brightMagenta '&'
  '+',  //  4 green         12 brightGreen   '$'
  '=',  //  5 cyan          13 brightCyan    '@'
  '^',  //  6 yellow        14 brightYellow  '?'
  '%',  //  7 white         15 brightWhite   '#'
  '_', '!', '*', '&', '$', '@', '?', '#'
];

/**
 * Je ten index barvy průhledný? Bez `--opaque` je to obojí černá, 0 i 8.
 * @param {number} color - Index barvy ZX, 0-15.
 * @param {boolean} opaque - Nechat černou jako barvu.
 * @returns {boolean} True, když se pixel nekreslí.
 */
function isTransparent(color, opaque) {
  return !opaque && (color & 7) === 0;
}

/**
 * Znak, kterým se index barvy zapíše do mřížky.
 * @param {number} color - Index barvy ZX, 0-15.
 * @param {boolean} opaque - Nechat černou jako barvu.
 * @returns {string} Jeden znak.
 */
function charOf(color, opaque) {
  return isTransparent(color, opaque) ? TRANSPARENT_CHAR : CODE_CHARS[color];
}

/**
 * Rozloží sprite uložený jako videopaměť na mřížku znaků a paletu.
 * @param {Object} sprite - Položka z pole `sprites` datového souboru.
 * @param {Object} zxColor - Třída ZXColor ze svision.
 * @param {boolean} opaque - Nechat černou jako barvu místo průhledné.
 * @returns {Object} Grafická data pro SpriteEntity.setGraphicsData().
 */
function toGrid(sprite, zxColor, opaque) {
  const bitmap = Buffer.from(sprite.bitmap, 'base64');
  const attributes = Buffer.from(sprite.attributes, 'base64');
  const cols = sprite.cols;
  if (bitmap.length !== cols*sprite.height || attributes.length !== cols*sprite.rows) {
    throw new Error(`bitmapa ${bitmap.length} B, atributy ${attributes.length} B `
                    + `– nesedí na ${cols} sloupců a ${sprite.height} řádků`);
  }
  const used = new Set();
  const grid = [];
  for (let line = 0; line < sprite.height; line++) {
    let row = '';
    for (let col = 0; col < cols; col++) {
      const byte = bitmap[line*cols+col];
      const attr = attributes[(line >> 3)*cols+col];
      const bright = (attr & 64) ? 8 : 0;
      const ink = (attr & 7) | bright;
      const paper = ((attr >> 3) & 7) | bright;
      for (let bit = 0; bit < 8; bit++) {
        const color = (byte >> (7-bit)) & 1 ? ink : paper;
        used.add(color);
        row += charOf(color, opaque);
      }
    }
    grid.push(row);
  }
  const colors = {};
  for (const color of [...used].sort((a, b) => a-b)) {
    // false je v paletě SpriteEntity dohodnutá značka pro "nekreslit"; obě
    // černé (0 i 8) na ni padnou týmž znakem, protože se stejně nekreslí
    colors[charOf(color, opaque)] = isTransparent(color, opaque)
                                  ? false : zxColor.color(color);
  }
  return {
    width: sprite.width, height: sprite.height,
    frames: 1, directions: 1,
    colors: colors,
    sprite: [{grid: grid}]
  };
}

/**
 * Přečte barvy spritu podruhé, jinou cestou, a porovná je s mřížkou.
 * @param {Object} sprite - Položka z pole `sprites`.
 * @param {Object} graphics - Co vyrobil toGrid().
 * @param {Object} zxColor - Třída ZXColor ze svision.
 * @param {boolean} opaque - Táž volba, se kterou se mřížka stavěla.
 * @returns {number} Počet pixelů, které nesedí.
 */
function countDifferences(sprite, graphics, zxColor, opaque) {
  const bitmap = Buffer.from(sprite.bitmap, 'base64');
  const attributes = Buffer.from(sprite.attributes, 'base64');
  const cols = sprite.cols;
  const grid = graphics.sprite[0].grid;
  let differences = 0;
  for (let line = 0; line < sprite.height; line++) {
    for (let col = 0; col < cols; col++) {
      const byte = bitmap[line*cols+col];
      const attr = attributes[(line >> 3)*cols+col];
      for (let bit = 0; bit < 8; bit++) {
        const set = (byte >> (7-bit)) & 1;
        // druhé čtení: hex barvy rovnou z atributu, bez skládání indexu
        let expected = set ? zxColor.penAttrColor(attr) : zxColor.bkAttrColor(attr);
        if (!opaque && expected === zxColor.black) {
          expected = false;
        }
        if (graphics.colors[grid[line][col*8+bit]] !== expected) {
          differences++;
        }
      }
    }
  }
  return differences;
}

async function main() {
  const args = process.argv.slice(2);
  const opaque = args.includes('--opaque');
  const dumpAt = args.indexOf('--dump');
  const dump = dumpAt >= 0 ? args[dumpAt+1] : null;
  // pozor: bez --dump je dumpAt -1, takže se nesmí vyloučit index 0
  const dumpValueAt = dumpAt >= 0 ? dumpAt+1 : -1;
  const positional = args.filter((a, i) => !a.startsWith('--') && i !== dumpValueAt);
  if (!positional[0]) {
    throw new Error('cekam cestu k datovemu souboru s polem sprites, '
                    + 'napr. ./tools/mkspritegfx.mjs data/neco.json');
  }
  const dst = path.resolve(ROOT, positional[0]);

  await import(url.pathToFileURL(path.join(ROOT, 'app/svision/tools/nodeEnv.mjs')).href);
  const { ZXColor } = await import(url.pathToFileURL(
    path.join(ROOT, 'app/svision/js/platform/canvas2D/zx/zxColor.js')).href);

  const data = JSON.parse(fs.readFileSync(dst, 'utf8'));
  if (!data.sprites) {
    throw new Error(`${path.relative(ROOT, dst)} nemá pole sprites`);
  }

  let checks = 0;
  for (const [name, sprite] of Object.entries(data.sprites)) {
    let graphics;
    try {
      graphics = toGrid(sprite, ZXColor, opaque);
    } catch (err) {
      throw new Error(`${name}: ${err.message}`);
    }
    const differences = countDifferences(sprite, graphics, ZXColor, opaque);
    if (differences) {
      throw new Error(`${name}: ${differences} pixelů nesedí na druhé čtení atributů`);
    }
    checks += sprite.width*sprite.height;

    // SpriteEntity si šířku bere z nejpravějšího kresleného pixelu, ne
    // z width – když je pravý sloupec celý průhledný, entita bude užší
    const grid = graphics.sprite[0].grid;
    let painted = 0;
    for (const row of grid) {
      for (let x = 0; x < row.length; x++) {
        if (graphics.colors[row[x]] !== false && x+1 > painted) {
          painted = x+1;
        }
      }
    }
    if (painted !== sprite.width) {
      console.warn('  ! %s: pravých %d sloupců je průhledných, SpriteEntity '
                   + 'bude %d px široká místo %d', name, sprite.width-painted,
                   painted, sprite.width);
    }

    if (dump === name) {
      for (const row of graphics.sprite[0].grid) {
        console.log(row);
      }
    }
    sprite.graphics = graphics;
    console.log('  %s: %dx%d, %d barev%s, %d pixelů zkontrolováno, 0 rozdílů',
                name, sprite.width, sprite.height, Object.keys(graphics.colors).length,
                opaque ? '' : ' (černá průhledná)', sprite.width*sprite.height);
  }

  data.spritesNote = 'bitmap/attributes = videopaměť originálu (tools/mkscreen.py '
                   + '--sprite); graphics = totéž jako mřížka znaků a paleta pro '
                   + 'SpriteEntity.setGraphicsData() (tools/mkspritegfx.mjs), '
                   + 'nekomprimované';
  fs.writeFileSync(dst, JSON.stringify(data, null, 2)+'\n');
  console.log('%s: %d spritů, %d kontrol, 0 rozdílů',
              path.relative(ROOT, dst), Object.keys(data.sprites).length, checks);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
