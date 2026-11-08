#!/usr/bin/env python3
"""**Sprity** z runtime obrazu do `data/spriteframes.json`.

    ./tools/dumpsprites.py [--png build/sprites]

★ `SpritesTable` (`$BF84`) je tabulka **196 ukazatelů** (ID `$00`–`$C3`), ze
které bere `GetSpriteAddress` (`$B928`) adresu snímku: `HL = $BF84 + ID*2`.
Různých snímků je jen **153** – hodně ID ukazuje na tentýž obrázek, protože
animace se přehrávají tam a zpátky (`Disappearing` má šest snímků z čtyř
obrázků) a některá ID jsou prázdný sprite `$C10C` (šířka 0, výška 0).

Formát snímku – **pozor, obráceně než u kusů kulisy**:

    DEFB šířka v bajtech
    DEFB výška v pixelových řádcích
    DEFB pixely (šířka × výška), **neznegované**, bez masky a bez atributů

Že je to takhle, není odhad: snímky leží v paměti za sebou a konec jednoho je
začátek dalšího (nástroj to kontroluje a jinak spadne), všech 153 má šířku
1–8 bajtů a výšku do 64 řádků. **Barvu si sprite nenese** – atributy pod ním
řeší hra jinde, což je M4/M5.

Jména snímků jsou z veřejné disassembly (`#SPRITENAME`, `sabrewulf.ref`) –
jsou to **jména z druhé ruky**, ne měření, a nástroj to tak i označí. Rozměry,
adresy a pixely jsou z runtime obrazu.
"""
import argparse, base64, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import roomlib                                                  # noqa: E402
from scr2png import write_png                                    # noqa: E402

REF = os.path.join(ROOT, 'sources/asm/pobtastic-skoolkit/sabrewulf.ref')
MAX_WIDTH, MAX_HEIGHT = 8, 64


def sprite_names(path=REF):
    """Jména snímků z makra `#SPRITENAME` veřejné disassembly (z druhé ruky)."""
    if not os.path.exists(path):
        return {}
    text = open(path, encoding='utf-8', errors='replace').read()
    block = text.split('#DEF(#SPRITENAME(id)', 1)
    if len(block) < 2:
        return {}
    return {int(i): name for i, name in
            re.findall(r'^\s*(\d+):"([^"]*)",?\s*$', block[1], re.M)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ram', nargs='?', default=os.path.join(ROOT, 'build/sabrewulf-run.bin'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'data/spriteframes.json'))
    ap.add_argument('--png', default=os.path.join(ROOT, 'build/sprites'))
    args = ap.parse_args()

    ram = roomlib.Ram(args.ram)
    names = sprite_names()
    table = [ram.word(roomlib.SPRITES_TABLE+i*2) for i in range(roomlib.SPRITES_COUNT)]
    if min(table) != roomlib.SPRITE_DATA_FIRST:
        raise SystemExit('nejnizsi ukazatel SpritesTable je $%04X, cekam $%04X'
                         % (min(table), roomlib.SPRITE_DATA_FIRST))

    frames, order = {}, []
    for addr in sorted(set(table)):
        width, height = ram.byte(addr), ram.byte(addr+1)
        if not (0 <= width <= MAX_WIDTH and 0 <= height <= MAX_HEIGHT):
            raise SystemExit('sprite $%04X ma rozmery %dx%d – to neni sprite, '
                             'format nesedi' % (addr, width, height))
        frames[addr] = {'address': '$%04X' % addr,
                        'width': width, 'widthPixels': width*8, 'height': height,
                        'bitmap': base64.b64encode(
                            ram.block(addr+2, width*height)).decode('ascii')}
        order.append(addr)

    # ★ snímky leží v paměti za sebou; kde na sebe nenavazují, je mezi nimi
    # jiná data (např. seznam grafik básně na $C374). Když by nenavazoval
    # kterýkoli jiný, byl by špatně přečtený formát – proto se to počítá.
    contiguous = sum(1 for i, addr in enumerate(order[:-1])
                     if addr+2+frames[addr]['width']*frames[addr]['height'] == order[i+1])

    sprites = []
    for sprite_id, addr in enumerate(table):
        sprites.append({'id': '$%02X' % sprite_id,
                        'frame': '$%04X' % addr,
                        # jméno je z veřejné disassembly, ne změřené
                        'name': names.get(sprite_id, '')})

    data = {
        'note': 'M2: sprity z runtime obrazu – SpritesTable ($BF84), 196 ID '
                'a 153 různých snímků. Šířka je v bajtech, výška v pixelech, '
                'pixely bez masky a bez atributů; barvu sprite nenese. '
                'Jména jsou z veřejné disassembly, ne změřená. Pózy chůze '
                'a meče se rozeberou v M3, entity v M4/M5 '
                '(tools/dumpsprites.py).',
        'source': os.path.basename(args.ram),
        'tableAddress': '$%04X' % roomlib.SPRITES_TABLE,
        'ids': len(sprites),
        'frames': len(frames),
        'framesContiguous': contiguous,
        'namesFrom': 'sources/asm/pobtastic-skoolkit/sabrewulf.ref (#SPRITENAME) '
                     '– zdroj z druhé ruky',
        'sprites': sprites,
        'frameData': [frames[a] for a in order]
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print('%s (%d ID, %d snimku, %d navazuje na sebe, %d B pixelu)'
          % (args.out, len(sprites), len(frames), contiguous,
             sum(f['width']*f['height'] for f in frames.values())))

    if args.png:
        os.makedirs(args.png, exist_ok=True)
        for sprite_id, addr in enumerate(table):
            frame = frames[addr]
            if frame['width'] == 0 or frame['height'] == 0:
                continue
            pixels = base64.b64decode(frame['bitmap'])
            rows = roomlib.cells_to_rgb(pixels, None, frame['width'], frame['height'])
            write_png(os.path.join(args.png, 'sprite%02X.png' % sprite_id),
                      rows, frame['width']*8, 3)
        print('nahledy: %s/spriteXX.png' % args.png)


if __name__ == '__main__':
    main()
