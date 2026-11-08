#!/usr/bin/env python3
"""**41 kusů kulisy** z runtime obrazu do `data/scenery.json`.

    ./tools/dumpgfx.py [--png build/gfx]

★ Kusy kulisy (`Background Graphic $01`–`$29`) leží za sebou od **`$70BC`**
a blok končí přesně na **`$9692`**, což je první bajt „game status bufferu"
(`GameOptions`). Nic se nehledá heuristikou: nástroj kusy prochází podle jejich
vlastních hlaviček a když se konec nesejde s `$9692` nebo když některý kus
nepoužívá žádná předloha, **spadne**.

Formát jednoho kusu (`tools/roomlib.py`, `sources/docs/disasm_notes.md` §12):

    DEFB výška v pixelech, šířka v bajtech
    DEFB pixely (výška × šířka), **znegované** – hra je při kreslení invertuje
    DEFB výška v atributech (= výška/8), šířka v atributech (= šířka)
    DEFB atributy

Do `data/scenery.json` se ukládají pixely **už odnegované** (aby prohlížeč
nemusel nic invertovat) jako base64 skutečných bajtů, a atributy taky. Nic
se nepřekresluje.
"""
import argparse, base64, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import roomlib                                                  # noqa: E402
from scr2png import write_png                                    # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ram', nargs='?', default=os.path.join(ROOT, 'build/sabrewulf-run.bin'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'data/scenery.json'))
    ap.add_argument('--png', default=os.path.join(ROOT, 'build/gfx'),
                    help='kam uložit náhledy jednotlivých kusů (default build/gfx)')
    args = ap.parse_args()

    world = roomlib.World(args.ram)
    counts = {}
    for items in world.rooms:
        for gfx, _, _ in items:
            counts[gfx] = counts.get(gfx, 0)+1

    pieces = []
    for piece in world.pieces:
        pieces.append({
            'id': '$%02X' % piece.index,
            'address': '$%04X' % piece.addr,
            'width': piece.width, 'widthPixels': piece.width*8,
            'height': piece.height,
            'attrRows': piece.attr_height, 'attrCols': piece.attr_width,
            'usedByTemplates': counts.get(piece.addr, 0),
            'bitmap': base64.b64encode(piece.pixels).decode('ascii'),
            'attributes': base64.b64encode(piece.attrs).decode('ascii')
        })

    data = {
        'note': 'M2: 41 kusů kulisy ze runtime obrazu ($70BC–$9691), pixely už '
                'odnegované. Předlohy místností je skládají podle pozic '
                '(data/rooms.json); ověřeno proti originálu bajt po bajtu '
                'nástrojem tools/matchscreen.py (tools/dumpgfx.py).',
        'source': os.path.basename(args.ram),
        'firstAddress': '$%04X' % roomlib.SCENERY_FIRST,
        'endAddress': '$%04X' % roomlib.SCENERY_END,
        'count': len(pieces),
        # ★ pixely kusu jsou v datech znegované, hra je invertuje (CPL, $BC17);
        # tady jsou už odnegované, aby prohlížeč nemusel nic dělat
        'pixelsInverted': False,
        # ★ kus se zapisuje natvrdo (LD (HL),A), ne přes OR – pozdější kus
        # překryje dřívější i svými nulami, takže na pořadí záleží
        'drawMode': 'overwrite',
        'pieces': pieces
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    total = sum(len(p.pixels)+len(p.attrs) for p in world.pieces)
    print('%s (%d kusu, %d B pixelu + atributu)' % (args.out, len(pieces), total))

    if args.png:
        os.makedirs(args.png, exist_ok=True)
        for piece in world.pieces:
            rows = roomlib.cells_to_rgb(piece.pixels, piece.attrs,
                                        piece.width, piece.height)
            write_png(os.path.join(args.png, 'piece%02X.png' % piece.index),
                      rows, piece.width*8, 2)
        print('nahledy: %s/piece01.png .. piece%02X.png'
              % (args.png, roomlib.SCENERY_COUNT))


if __name__ == '__main__':
    main()
