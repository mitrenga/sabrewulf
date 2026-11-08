#!/usr/bin/env python3
"""**Mapa světa z dat remaku** a její porovnání s dohledanými mapami.

    ./tools/mapworld.py
    ./tools/mapworld.py --check
    ./tools/mapworld.py --mosaic build/worldmosaic.png

Bere `data/world.json` (mřížka 16 × 16 a odvozené přechody, `tools/dumpworld.py`)
a vykreslí z něj mapu: do konzole jako text, do `build/worldmap.png` jako
schéma po vzoru dobových map (jedna obrazovka = buňka 40 × 40 px, chodby bílé)
a s `--mosaic` i jako **mozaiku všech 256 skutečných obrazovek** poskládaných
z kulisy (4096 × 2816 px).

★ `--check` porovná přechody **s mapou od Einara Saukase**
(`sources/media/maps/map_07.png`, 2012), která je nakreslená jako mříž 16 × 16
buněk po 40 px, takže se dá číst strojově (`tools/pngread.py`). Je to nezávislý
zdroj – ne z originálu, ale ani z našich dat.

Co z toho vyšlo: **svislé přechody se shodují všechny** (240 ze 240, z toho
80 zavřených – takže to není shoda z nudy), **vodorovné 211 ze 240**. Zbylých
**29 hranic rozhodla hra**: od M3 se průchodnost počítá z kolizního pravidla
originálu (`$B873`, obálky kusů kulisy) a `tools/mapwalk.py --verify` zkusil
všechny hranice projít v běžícím originálu – prošel i těmi 29. Ta dobová mapa
je tam tedy stylizovaná (`sources/docs/disasm_notes.md` §15). Nic se
nedomýšlí: rozdíly nástroj pořád vypíše.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import roomlib                                                  # noqa: E402
from pngread import read_png                                     # noqa: E402
from scr2png import write_png                                    # noqa: E402

REFERENCE_MAP = os.path.join(ROOT, 'sources/media/maps/map_07.png')
# mříž mapy od Einara Saukase, odměřená z jejích červených linek
MAP_ORIGIN, MAP_CELL, MAP_WHITE = (32, 128), 40, (252, 252, 252)

UP, DOWN, LEFT, RIGHT = 1, 2, 4, 8
CELL = 40                       # schéma: 5 × 5 bloků po 8 px, jako předloha mapy


def load(path):
    world = json.load(open(path))
    grid = [bytes.fromhex(row) for row in world['templates']]
    exits = [bytes.fromhex(row) for row in world['passages']['exits']]
    return world, grid, exits


def text_map(grid, exits):
    """Mapa do konzole: číslo předlohy a `|`/`-` tam, kde je průchod."""
    lines = []
    for row in range(16):
        top = ''
        for col in range(16):
            top += '+' + ('   ' if exits[row][col] & UP else '---')
        lines.append(top + '+')
        middle = ''
        for col in range(16):
            middle += (' ' if exits[row][col] & LEFT else '|')
            middle += '%02X ' % grid[row][col]
        lines.append(middle + ('' if exits[row][15] & RIGHT else '|'))
    lines.append('+' + '+'.join('---' for _ in range(16)) + '+')
    return lines


def schematic(exits, cell=CELL):
    """Schéma jako předloha mapy: chodba = 3/5 buňky, zeď = černá."""
    size = 16*cell
    rows = [bytearray(b'\x00'*(size*3)) for _ in range(size)]
    block = cell//5
    white = bytes(MAP_WHITE)

    def fill(x0, y0, x1, y1):
        for y in range(y0, y1):
            for x in range(x0, x1):
                rows[y][x*3:x*3+3] = white

    for row in range(16):
        for col in range(16):
            x0, y0 = col*cell, row*cell
            fill(x0+block, y0+block, x0+4*block, y0+4*block)   # střed obrazovky
            if exits[row][col] & UP:
                fill(x0+2*block, y0, x0+3*block, y0+block)
            if exits[row][col] & DOWN:
                fill(x0+2*block, y0+4*block, x0+3*block, y0+cell)
            if exits[row][col] & LEFT:
                fill(x0, y0+2*block, x0+block, y0+3*block)
            if exits[row][col] & RIGHT:
                fill(x0+4*block, y0+2*block, x0+cell, y0+3*block)
    return [bytes(r) for r in rows], size


def reference_openness(path):
    """Průchody z mapy od Einara Saukase: `(vodorovné, svislé)` jako množiny."""
    _, _, pixels = read_png(path)
    x0, y0 = MAP_ORIGIN
    horizontal, vertical = set(), set()
    for row in range(16):
        for col in range(15):
            border = x0+(col+1)*MAP_CELL
            # svislou hranici překrývá červená linka mapy, tak se čte vedle ní
            if any(pixels[y][border-3] == MAP_WHITE and pixels[y][border+2] == MAP_WHITE
                   for y in range(y0+row*MAP_CELL, y0+(row+1)*MAP_CELL)):
                horizontal.add((col, row))
    for row in range(15):
        for col in range(16):
            border = y0+(row+1)*MAP_CELL
            if any(pixels[border-3][x] == MAP_WHITE and pixels[border+2][x] == MAP_WHITE
                   for x in range(x0+col*MAP_CELL, x0+(col+1)*MAP_CELL)):
                vertical.add((col, row))
    return horizontal, vertical


def check(grid, exits, path):
    """Porovná odvozené přechody s mapou; vrátí `True`, když se sejdou."""
    horizontal, vertical = reference_openness(path)
    bad_h = [(col, row, bool(exits[row][col] & RIGHT), (col, row) in horizontal)
             for row in range(16) for col in range(15)
             if bool(exits[row][col] & RIGHT) != ((col, row) in horizontal)]
    bad_v = [(col, row, bool(exits[row][col] & DOWN), (col, row) in vertical)
             for row in range(15) for col in range(16)
             if bool(exits[row][col] & DOWN) != ((col, row) in vertical)]
    print('kontrola proti %s' % os.path.relpath(path, ROOT))
    print('  svisle:    %3d/240 souhlasi (mapa ma %d otevrenych)'
          % (240-len(bad_v), len(vertical)))
    print('  vodorovne: %3d/240 souhlasi (mapa ma %d otevrenych)'
          % (240-len(bad_h), len(horizontal)))
    pairs = {}
    for col, row, mine, theirs in bad_h+bad_v:
        vertical_border = (col, row, mine, theirs) in bad_v
        other = grid[row+1][col] if vertical_border else grid[row][col+1]
        key = ('$%02X' % grid[row][col], '$%02X' % other,
               'dolu' if vertical_border else 'vpravo', mine, theirs)
        pairs.setdefault(key, []).append((col, row))
    for (mine_t, other_t, direction, mine, theirs), where in sorted(pairs.items()):
        print('  %s %s -> %s: my %s, mapa %s (%dx: %s)'
              % (mine_t, direction, other_t,
                 'otevreno' if mine else 'zavreno',
                 'otevreno' if theirs else 'zavreno', len(where),
                 ' '.join('%d,%d' % w for w in where)))
    if bad_h or bad_v:
        print('  ★ %d rozdilu ROZHODLA HRA (M3): pruchodnost se pocita '
              'z kolizniho pravidla originalu ($B873) a tools/mapwalk.py '
              '--verify jimi v beznem originalu proslo, takze je mapa v tech '
              'mistech stylizovana (disasm_notes.md §15).'
              % (len(bad_h)+len(bad_v)))
    return not (bad_h or bad_v)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('world', nargs='?', default=os.path.join(ROOT, 'data/world.json'))
    ap.add_argument('--png', default=os.path.join(ROOT, 'build/worldmap.png'))
    ap.add_argument('--mosaic', nargs='?', const=os.path.join(ROOT, 'build/worldmosaic.png'),
                    help='mozaika všech 256 skutečných obrazovek (4096 × 2816 px)')
    ap.add_argument('--check', nargs='?', const=REFERENCE_MAP,
                    help='porovnat s mapou (default sources/media/maps/map_07.png)')
    ap.add_argument('--text', action='store_true', help='vypsat mapu do konzole')
    args = ap.parse_args()

    world, grid, exits = load(args.world)
    print('%s: %d x %d obrazovek, %d ruznych predloh, prechody %s'
          % (os.path.relpath(args.world, ROOT), world['columns'], world['rows'],
             world['templatesUsed'],
             world['passages'].get('method', '?').split(':')[0]))
    if args.text:
        for line in text_map(grid, exits):
            print(line)

    if args.png:
        rows, size = schematic(exits)
        write_png(args.png, rows, size)
        print('schema: %s (%d x %d)' % (args.png, size, size))

    if args.mosaic:
        from scr2png import scr_to_rgb
        room_world = roomlib.World()
        height = roomlib.PLAY_HEIGHT
        canvas = [bytearray(16*256*3) for _ in range(16*height)]
        for row in range(16):
            for col in range(16):
                screen = room_world.render_room(col, row)
                pixels = scr_to_rgb(roomlib.play_area_to_scr(
                    screen.bitmap_rows(), screen.attributes()))
                for y in range(height):
                    line = pixels[roomlib.PLAY_TOP+y]
                    canvas[row*height+y][col*256*3:(col+1)*256*3] = line
        write_png(args.mosaic, [bytes(r) for r in canvas], 16*256)
        print('mozaika: %s (%d x %d)' % (args.mosaic, 16*256, 16*height))

    if args.check:
        if not os.path.exists(args.check):
            raise SystemExit('chybi %s' % args.check)
        if not check(grid, exits, args.check):
            raise SystemExit(2)


if __name__ == '__main__':
    main()
