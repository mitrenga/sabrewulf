#!/usr/bin/env python3
"""Porovná panel remaku se snímky z běžícího originálu, bajt po bajtu.

    ./tools/matchpanel.py
    ./tools/matchpanel.py build/frame01000.scr --p1 535 --lives 3

Bez argumentů projede **tři referenční snímky** (naše dva z `playtrace.py`
a `.scr` ze Spectrum Computing) s hodnotami, které jsou na nich vidět, a
u každého čeká **nulu rozdílů** v bitmapě i v atributech znakových řádků 0–1.

Panel se staví přesně tak, jak ho staví `app/screenComposer.js`:

- rozvržení z `sources/docs/screen_layout.md` §2 (`1UP` 2–4, životy 8, ikonka 9,
  `HI` 15–16, `2UP` 27–29; tři šestimístná skóre na 1–6, 13–18, 25–30),
- atributy `$47` / `$45` / `$57` na řádku 0 a `$46` na celém řádku 1,
- **glyfy ze svision** (`app/svision/fonts/zx-rom.ch8.hex.txt`) – ★ hra
  vlastní znakovou sadu nemá, tiskne přes `PrintScreen` (`$B589`), a ta si
  adresu glyfu spočítá z `CHARS` (`$5C36`), tedy z ROM fontu ZX Spectra.
  Tohle porovnání je zároveň **důkaz toho tvrzení**: kdyby hra měla vlastní
  font, panel by se s ROM tabulkou neshodl.
- ikonka života z `data/sprites.json` (`tools/mksprite.py`; těch osm bajtů je
  v runtime obrazu na `$B814`, `UDG_Life`).

Je to panelová obdoba `matchscreen.py`, který v M2 porovná celou místnost.
"""
import argparse, base64, json, os, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PANEL_ROWS = 2
FONT_FILE = 'app/svision/fonts/zx-rom.ch8.hex.txt'
FONT_FIRST = 0x20               # první znak tabulky svision je mezera

# rozvržení odměřené na běžícím originálu (screen_layout.md §2)
ATTR_VALUE = 0x47               # jasná bílá na černé – „prázdná" buňka řádku 0
ATTR_LABEL = 0x45               # jasná azurová – 1UP / 2UP
ATTR_HI = 0x57                  # jasná bílá na červené – HI
ATTR_SCORE = 0x46               # jasná žlutá na černé – celý řádek 1
COL_1UP, COL_LIVES, COL_LIFE_ICON, COL_HI, COL_2UP = 2, 8, 9, 15, 27
COL_SCORE_1UP, COL_SCORE_HI, COL_SCORE_2UP = 1, 13, 25
SCORE_DIGITS = 6

# (snímek, {skóre 1UP, HI, 2UP, životy nebo None, když se nekreslí})
FRAMES = [
    ('sources/media/screens/title_menu.scr',
     {'p1': 0, 'hi': 102275, 'p2': 0, 'lives': None}),
    ('sources/media/screens/gameplay_start.scr',
     {'p1': 0, 'hi': 102275, 'p2': 0, 'lives': 4}),
    ('sources/media/screens/running_screen.scr',
     {'p1': 1950, 'hi': 102275, 'p2': 0, 'lives': 4}),
]


def screen_offset(y):
    third, char_row, pix = y >> 6, (y >> 3) & 7, y & 7
    return (third << 11) | (pix << 8) | (char_row << 5)


def load_font():
    """Glyfy z tabulky svision: {znak: 8 bajtů}."""
    hexdata = open(os.path.join(ROOT, FONT_FILE)).read().strip()
    if len(hexdata) % 16:
        raise SystemExit('%s: %d hex znaku neni delitelne 16' % (FONT_FILE, len(hexdata)))
    glyphs = {}
    for index in range(len(hexdata)//16):
        glyphs[chr(FONT_FIRST+index)] = bytes.fromhex(hexdata[index*16:index*16+16])
    return glyphs


def load_life_icon():
    sprites = json.load(open(os.path.join(ROOT, 'data/sprites.json')))
    icon = sprites['panel']['frames']['life']
    return base64.b64decode(icon['bitmap']), base64.b64decode(icon['attributes'])


def build_panel(values):
    """Panel remaku: (bitmapa 512 B, atributy 64 B) pro znakové řádky 0–1."""
    glyphs = load_font()
    icon_bits, icon_attrs = load_life_icon()

    bitmap = bytearray(32*8*PANEL_ROWS)
    attrs = bytearray(32*PANEL_ROWS)
    # celé řádky se obarví jedním průchodem, jako v GameInitialisation
    # ($996F atribut $47, $997C atribut $46)
    for col in range(32):
        attrs[col] = ATTR_VALUE
        attrs[32+col] = ATTR_SCORE

    def write(row, col, text, attr):
        for i, char in enumerate(text):
            glyph = glyphs[char]
            for pixel in range(8):
                bitmap[(row*8+pixel)*32+col+i] = glyph[pixel]
            attrs[row*32+col+i] = attr

    write(0, COL_1UP, '1UP', ATTR_LABEL)
    write(0, COL_HI, 'HI', ATTR_HI)
    write(0, COL_2UP, '2UP', ATTR_LABEL)
    if values['lives'] is not None:
        write(0, COL_LIVES, str(values['lives']), ATTR_VALUE)
        for pixel in range(8):
            bitmap[pixel*32+COL_LIFE_ICON] = icon_bits[pixel]
        attrs[COL_LIFE_ICON] = icon_attrs[0]
    write(1, COL_SCORE_1UP, str(values['p1']).rjust(SCORE_DIGITS, '0'), ATTR_SCORE)
    write(1, COL_SCORE_HI, str(values['hi']).rjust(SCORE_DIGITS, '0'), ATTR_SCORE)
    write(1, COL_SCORE_2UP, str(values['p2']).rjust(SCORE_DIGITS, '0'), ATTR_SCORE)
    return bitmap, attrs


def compare(path, values):
    """Porovná postavený panel se snímkem. Vrací počet rozdílů."""
    bitmap, attrs = build_panel(values)
    scr = open(os.path.join(ROOT, path), 'rb').read()
    if len(scr) != 6912:
        raise SystemExit('%s: cekam 6912 B .scr, mam %d' % (path, len(scr)))
    original = bytearray()
    for y in range(PANEL_ROWS*8):
        original += scr[screen_offset(y):screen_offset(y)+32]
    original_attrs = scr[6144:6144+32*PANEL_ROWS]

    bad_bits = [i for i in range(len(bitmap)) if bitmap[i] != original[i]]
    bad_attrs = [i for i in range(len(attrs)) if attrs[i] != original_attrs[i]]
    print('%s (1UP %d, HI %d, 2UP %d, zivoty %s):'
          % (os.path.basename(path), values['p1'], values['hi'], values['p2'],
             values['lives']))
    print('  bitmapa:  %d / %d bajtu se lisi' % (len(bad_bits), len(bitmap)))
    print('  atributy: %d / %d bajtu se lisi' % (len(bad_attrs), len(attrs)))
    for i in bad_bits[:16]:
        print('    bitmapa sloupec %d, radek %d: %02X != %02X'
              % (i % 32, i//32//8, bitmap[i], original[i]))
    for i in bad_attrs[:16]:
        print('    atribut sloupec %d, radek %d: %02X != %02X'
              % (i % 32, i//32, attrs[i], original_attrs[i]))
    if not bad_bits and not bad_attrs:
        print('  panel souhlasi s originalem bajt po bajtu')
    return len(bad_bits)+len(bad_attrs)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('frame', nargs='?', help='snímek k porovnání; bez něj se '
                    'projedou všechny referenční snímky')
    ap.add_argument('--p1', type=int, default=0, help='skóre 1. hráče')
    ap.add_argument('--hi', type=int, default=102275, help='nejvyšší skóre')
    ap.add_argument('--p2', type=int, default=0, help='skóre 2. hráče')
    ap.add_argument('--lives', type=int, default=None, help='počet životů; '
                    'bez něj se životy nekreslí (jako v menu)')
    args = ap.parse_args()

    if args.frame:
        cases = [(args.frame, {'p1': args.p1, 'hi': args.hi, 'p2': args.p2,
                               'lives': args.lives})]
    else:
        cases = FRAMES

    bad = 0
    for path, values in cases:
        bad += compare(path, values)
    if bad:
        sys.exit(1)
    print('vsech %d snimku: nula rozdilu' % len(cases))


if __name__ == '__main__':
    main()
