#!/usr/bin/env python3
"""Vyřízne sprite ze snímku běžícího originálu proti statické místnosti.

    ./tools/mksprite.py <frame.scr> <sloupec> <radek> <sirka> <vyska> [--name stand]
                        [--room data/room000.json] [--out data/sprites.json]
    ./tools/mksprite.py <frame.scr> 8 0 2 2 --name panelLife --raw

Souřadnice jsou ve **znakových buňkách** (sloupec 0–31, řádek 0–23 celé
obrazovky). Bez `--raw` se uloží jen to, co ve snímku přibylo proti statické
místnosti (`frame & ~room`) – tedy skutečné pixely spritu, ne pozadí – plus
atributy buněk, které sprite přepisuje. S `--raw` se místnost neodečítá; to je
pro panel, který součástí místnosti není.

Nic se nedokresluje: pózy, které se z běhu nevytáhly, prostě nejsou. Úplnou
tabulku spritů dodá M2 (`tools/dumpsprites.py`) z dat hry; tohle je
provizorium M1, aby na statické obrazovce stál skutečný Sabreman z originálu.
"""
import argparse, base64, json, os

PANEL_ROWS = 2


def screen_offset(y):
    third, char_row, pix = y >> 6, (y >> 3) & 7, y & 7
    return (third << 11) | (pix << 8) | (char_row << 5)


def play_area(scr):
    bitmap = bytearray()
    for y in range(PANEL_ROWS*8, 192):
        base = screen_offset(y)
        bitmap += scr[base:base+32]
    return bytes(bitmap), bytes(scr[6144+PANEL_ROWS*32:6144+24*32])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('frame')
    ap.add_argument('col', type=int)
    ap.add_argument('row', type=int, help='znakovy radek cele obrazovky (0-23)')
    ap.add_argument('cols', type=int)
    ap.add_argument('rows', type=int)
    ap.add_argument('--name', default='stand')
    ap.add_argument('--group', default='sabreman',
                    help='skupina v data/sprites.json (sabreman, panel)')
    ap.add_argument('--room', default='data/room000.json')
    ap.add_argument('--out', default='data/sprites.json')
    ap.add_argument('--dump', action='store_true', help='vypsat sprite jako ASCII')
    ap.add_argument('--raw', action='store_true',
                    help='neodečítat místnost (pro panel, znakové řádky 0-1)')
    args = ap.parse_args()

    scr = open(args.frame, 'rb').read()
    if len(scr) != 6912:
        raise SystemExit('cekam 6912 B .scr, mam %d' % len(scr))
    if args.raw:
        frame_bitmap = bytearray()
        for y in range(192):
            frame_bitmap += scr[screen_offset(y):screen_offset(y)+32]
        frame_attrs = scr[6144:6912]
        bg = bytes(len(frame_bitmap))
        row0 = args.row
    else:
        room = json.load(open(args.room))
        bg = base64.b64decode(room['bitmap'])
        frame_bitmap, frame_attrs = play_area(scr)
        row0 = args.row-PANEL_ROWS
    bits, attrs = bytearray(), bytearray()
    for r in range(args.rows):
        for p in range(8):
            line = (row0+r)*8+p
            for c in range(args.cols):
                i = line*32+args.col+c
                bits.append(frame_bitmap[i] & ~bg[i] & 0xFF)
    for r in range(args.rows):
        for c in range(args.cols):
            attrs.append(frame_attrs[(row0+r)*32+args.col+c])

    if args.dump:
        for r in range(args.rows*8):
            print(''.join('#' if bits[r*args.cols+c] >> (7-b) & 1 else '.'
                          for c in range(args.cols) for b in range(8)))
        print('atributy:', ' '.join('%02X' % a for a in attrs))

    sprites = {}
    if os.path.exists(args.out):
        sprites = json.load(open(args.out))
    sprites['note'] = ('M1: sprity vyříznuté z běhu originálu '
                       '(tools/mksprite.py). Úplnou tabulku spritů vytáhne M2 '
                       'z dat hry (tools/dumpsprites.py).')
    sprites.setdefault(args.group, {'frames': {}})
    sprites[args.group]['frames'][args.name] = {
        'cols': args.cols, 'rows': args.rows,
        'width': args.cols*8, 'height': args.rows*8,
        'source': os.path.basename(args.frame),
        'sourceCol': args.col, 'sourceRow': args.row,
        'bitmap': base64.b64encode(bytes(bits)).decode('ascii'),
        'attributes': base64.b64encode(bytes(attrs)).decode('ascii')
    }
    with open(args.out, 'w') as f:
        json.dump(sprites, f, indent=2, sort_keys=True)
        f.write('\n')
    print('%s: %s/%s (%dx%d px)'
          % (args.out, args.group, args.name, args.cols*8, args.rows*8))


if __name__ == '__main__':
    main()
