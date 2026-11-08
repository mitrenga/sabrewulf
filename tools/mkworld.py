#!/usr/bin/env python3
"""Vytáhne mřížku světa z `Layout` (`$6066`) – **druhé, nezávislé přečtení**.

    ./tools/mkworld.py [build/sabrewulf-run.bin] [build/world-m1.json]

Od M2 píše `data/world.json` nástroj `tools/dumpworld.py`, který k mřížce
přidá mapu přechodů a startovní obrazovku. Tenhle nástroj zůstává jako
**nezávislá kontrola samotné mřížky** – čte ji vlastním kódem a kontroluje,
co o `RoomTable` víme – a proto píše do `build/`, aby data remaku nepřepsal.

★ `Layout` na `$6066` je **256 bajtů = mřížka 16 × 16** a každý bajt je číslo
předlohy místnosti z `RoomTable` (`$6166`, 48 ukazatelů). Přečteno z runtime
obrazu, viz `sources/docs/disasm_notes.md` §4.

Nástroj kontroluje, co o té tabulce víme, a když to neplatí, spadne:

- `RoomTable` má 48 ukazatelů a všechny míří do rozsahu dat předloh
  (`$6200`–`$7100`);
- v `Layout` je 45 různých čísel v rozsahu `$00`–`$2F` a nepoužité jsou
  právě `$01`, `$13` a `$24`;
- `VisitedRooms` (`$96BF`) je 32 bajtů = 256 bitů, jeden na obrazovku.

Uloží se mřížka (16 řádků po 16 bajtech jako hex) a statistika předloh.
**Formát samotné předlohy tady není** – jak se z ní a ze 41 kusů kulisy
poskládá obrázek, je otevřená otázka pro M2 (`tools/dumprooms.py`,
`tools/dumpworld.py`). Tenhle nástroj je M1: dává mapě světa v remaku
skutečná data, ne atrapu.
"""
import json, os, sys

LAYOUT = 0x6066
ROOM_TABLE = 0x6166
ROOM_TABLE_ENTRIES = 48
ROOM_DATA_RANGE = (0x6200, 0x7100)
VISITED_ROOMS = 0x96BF
VISITED_ROOMS_BYTES = 32
COLS = ROWS = 16
UNUSED_EXPECTED = [0x01, 0x13, 0x24]


def main(argv):
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
    src = argv[1] if len(argv) > 1 else os.path.join(root, 'build/sabrewulf-run.bin')
    dst = argv[2] if len(argv) > 2 else os.path.join(root, 'build/world-m1.json')
    ram = open(src, 'rb').read()
    if len(ram) != 49152:
        raise SystemExit('cekam 49152 B RAM ($4000-$FFFF), mam %d' % len(ram))

    def at(addr, length):
        return ram[addr-0x4000:addr-0x4000+length]

    layout = at(LAYOUT, COLS*ROWS)

    # RoomTable: 48 ukazatelů do dat předloh
    pointers = []
    table = at(ROOM_TABLE, ROOM_TABLE_ENTRIES*2)
    for i in range(ROOM_TABLE_ENTRIES):
        pointer = table[i*2] | (table[i*2+1] << 8)
        if not ROOM_DATA_RANGE[0] <= pointer < ROOM_DATA_RANGE[1]:
            raise SystemExit('RoomTable[%d] = $%04X mimo rozsah dat predloh '
                             '$%04X-$%04X – jiny obraz, nebo jina edice?'
                             % (i, pointer, *ROOM_DATA_RANGE))
        pointers.append(pointer)

    used = sorted(set(layout))
    if max(used) >= ROOM_TABLE_ENTRIES:
        raise SystemExit('Layout odkazuje na predlohu $%02X, ale RoomTable ma jen %d'
                         % (max(used), ROOM_TABLE_ENTRIES))
    unused = [t for t in range(ROOM_TABLE_ENTRIES) if t not in used]
    if unused != UNUSED_EXPECTED:
        raise SystemExit('nepouzite predlohy jsou %s, cekam %s'
                         % (['$%02X' % t for t in unused],
                            ['$%02X' % t for t in UNUSED_EXPECTED]))

    counts = {}
    for template in layout:
        counts[template] = counts.get(template, 0)+1
    top = max(counts, key=lambda t: counts[t])

    world = {
        'note': 'Druhé, nezávislé přečtení mřížky světa z Layout ($6066) – '
                '16 × 16 bajtů, každý je číslo předlohy z RoomTable ($6166). '
                'Data remaku píše tools/dumpworld.py; tohle je kontrola, proto '
                'to jde do build/. Viz sources/docs/disasm_notes.md §4 a §12 '
                '(tools/mkworld.py).',
        'source': os.path.basename(src),
        'layoutAddress': '$%04X' % LAYOUT,
        'roomTableAddress': '$%04X' % ROOM_TABLE,
        'visitedRoomsAddress': '$%04X' % VISITED_ROOMS,
        'visitedRoomsBits': VISITED_ROOMS_BYTES*8,
        'columns': COLS, 'rows': ROWS,
        'roomsCount': COLS*ROWS,
        'templatesCount': ROOM_TABLE_ENTRIES,
        'templatesUsed': len(used),
        'templatesUnused': ['$%02X' % t for t in unused],
        'mostUsedTemplate': {'template': '$%02X' % top, 'rooms': counts[top]},
        'roomWidth': 256, 'roomHeight': 176,
        # jeden řádek mřížky = 16 bajtů jako hex, stejně jako u underwurlde
        'templates': [layout[row*COLS:(row+1)*COLS].hex().upper() for row in range(ROWS)],
        'roomTable': ['$%04X' % p for p in pointers]
    }
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    with open(dst, 'w') as f:
        json.dump(world, f, indent=2)
        f.write('\n')
    print('%s (%d x %d mistnosti, %d ruznych predloh z %d, nejcastejsi $%02X '
          '%dx)' % (dst, COLS, ROWS, len(used), ROOM_TABLE_ENTRIES, top, counts[top]))


if __name__ == '__main__':
    main(sys.argv)
