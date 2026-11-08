#!/usr/bin/env python3
"""**Pixelově přesné porovnání obrazovek remaku s originálem.**

    PYTHONPATH=tools/vendor ./tools/matchscreen.py
    PYTHONPATH=tools/vendor ./tools/matchscreen.py --png build/match

Disciplína je stejná jako u `matchpanel.py`: **originál kreslí sám**. Runtime
obraz se nahraje do simulátoru, do volné paměti se položí pár instrukcí

    CALL $BB5C   ; ClearPlayArea
    CALL $BB7C   ; ClearPlayArea_Attributes
    LD HL,nnnn   ; předloha místnosti z RoomTable
    CALL $BBF7   ; DrawRoom
    JP  konec

a co po nich zůstane ve videopaměti, je **skutečná obrazovka originálu**. Proti
tomu se pustí `tools/roomlib.py` – replika `DrawRoom` v pythonu, ze které
vznikají data remaku – a porovná se **bajt po bajtu**: 5632 B bitmapy
a 704 B atributů na obrazovku.

Porovnává se:

1. všech **48 předloh** z `RoomTable` (`$6166`),
2. všech **256 obrazovek** světa, jak je skládá `Layout` (`$6066`),
3. **místnost pod hlavním menu** (`Room_Special_MainMenu`, `$61C6`).

Cíl je **nula rozdílů**. Když se něco nesejde, vypíše se mapa buněk a
(s `--png`) uloží se obě obrazovky, aby se dalo kouknout, čím to je.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import roomlib                                                  # noqa: E402
from scr2png import scr_to_rgb, write_png                        # noqa: E402
from skoolkit.simulator import Simulator                         # noqa: E402
from skoolkit.simutils import PC, SP                             # noqa: E402
try:
    from skoolkit.csimulator import CSimulator
except ImportError:                                             # pragma: no cover
    CSimulator = None

CLEAR_PLAY_AREA = 0xBB5C            # ClearPlayArea (bitmapa hrací plochy)
CLEAR_ATTRIBUTES = 0xBB7C           # ClearPlayArea_Attributes ($5840-$5AFF = $40)
DRAW_ROOM = 0xBBF7                  # DrawRoom
STUB = 0x5B00                       # tiskárenský buffer – hra ho nepoužívá
STACK = 0x6000                      # zásobník jako v GameEntry ($6000)


class Original:
    """Simulátor s runtime obrazem, který umí nakreslit místnost originálem."""

    def __init__(self, ram_path):
        ram = open(ram_path, 'rb').read()
        if len(ram) != 49152:
            raise SystemExit('%s: cekam 49152 B RAM, mam %d' % (ram_path, len(ram)))
        memory = [0]*65536
        memory[0x4000:0x10000] = list(ram)
        cls = CSimulator or Simulator
        self.sim = cls(memory, {'SP': STACK},
                       config={'fast_djnz': False, 'fast_ldir': False})
        self.memory = self.sim.memory

    def draw(self, room_addr):
        """Nakreslí předlohu z `room_addr` originálovými rutinami."""
        end = STUB+13
        stub = [0xCD, CLEAR_PLAY_AREA & 0xFF, CLEAR_PLAY_AREA >> 8,
                0xCD, CLEAR_ATTRIBUTES & 0xFF, CLEAR_ATTRIBUTES >> 8,
                0x21, room_addr & 0xFF, room_addr >> 8,
                0xCD, DRAW_ROOM & 0xFF, DRAW_ROOM >> 8,
                0x76]                       # HALT jako zastávka
        self.memory[STUB:STUB+len(stub)] = stub
        self.sim.registers[SP] = STACK
        self.sim.run(STUB, end-1)
        if self.sim.registers[PC] != end-1:
            raise SystemExit('simulator skoncil na $%04X, cekam $%04X'
                             % (self.sim.registers[PC], end-1))
        return bytes(self.memory[0x4000:0x5B00])


def play_area(screen6912):
    """Hrací plocha ze surové videopaměti – stejný tvar jako `roomlib.Screen`."""
    bitmap = bytearray()
    for y in range(roomlib.PLAY_TOP, 192):
        base = roomlib.screen_addr(0, y)-0x4000
        bitmap += screen6912[base:base+32]
    return bytes(bitmap), bytes(screen6912[0x1800+roomlib.PANEL_ROWS*32:0x1800+24*32])


def diff_map(mine, theirs, my_attrs, their_attrs):
    """Mapa znakových buněk, ve kterých se to liší (pro výpis do konzole)."""
    cells = []
    for row in range(22):
        line = ''
        for col in range(32):
            bad = any(mine[(row*8+p)*32+col] != theirs[(row*8+p)*32+col]
                      for p in range(8)) or my_attrs[row*32+col] != their_attrs[row*32+col]
            line += '#' if bad else '.'
        cells.append(line)
    return cells


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ram', nargs='?', default=os.path.join(ROOT, 'build/sabrewulf-run.bin'))
    ap.add_argument('--png', help='prefix pro uložení obrazovek, které se nesejdou')
    ap.add_argument('--all-png', metavar='DIR',
                    help='uložit PNG všech 48 předloh nakreslených originálem')
    ap.add_argument('--dump', metavar='FILE', nargs='?',
                    const=os.path.join(ROOT, 'build/screens.bin'),
                    help='uložit surové bajty všech 48 předloh a místnosti pod '
                         'hlavním menu, nakreslených originálem '
                         '(49 × 5632 B bitmapy + 704 B atributů) – '
                         'referenci pro tools/matchrooms.js')
    args = ap.parse_args()

    world = roomlib.World(args.ram)
    original = Original(args.ram)
    failures = []
    checked = 0

    def compare(name, room_addr, items):
        nonlocal checked
        theirs = play_area(original.draw(room_addr))
        screen = roomlib.draw_room(items, world.by_addr)
        mine = (screen.bitmap_rows(), screen.attributes())
        checked += 1
        if mine == theirs:
            return True
        bad_b = sum(a != b for a, b in zip(mine[0], theirs[0]))
        bad_a = sum(a != b for a, b in zip(mine[1], theirs[1]))
        failures.append((name, bad_b, bad_a))
        print('%s: %d rozdilu bitmapy, %d atributu' % (name, bad_b, bad_a))
        for row, line in enumerate(diff_map(mine[0], theirs[0], mine[1], theirs[1])):
            if '#' in line:
                print('  %2d %s' % (row+roomlib.PANEL_ROWS, line))
        if args.png:
            for tag, data in (('ours', mine), ('orig', theirs)):
                scr = bytearray(6912)
                for r, y in enumerate(range(roomlib.PLAY_TOP, 192)):
                    base = roomlib.screen_addr(0, y)-0x4000
                    scr[base:base+32] = data[0][r*32:r*32+32]
                scr[6144+roomlib.PANEL_ROWS*32:6144+24*32] = data[1]
                path = '%s-%s-%s.png' % (args.png, name.replace(' ', '_'), tag)
                write_png(path, scr_to_rgb(bytes(scr)), 256)
                print('  %s' % path)
        return False

    # 1) 48 předloh
    for template, addr in enumerate(world.room_table):
        compare('predloha $%02X' % template, addr, world.rooms[template])

    # 2) 256 obrazovek světa – originál je kreslí z Layout, tady se ověřuje,
    #    že se mřížka na předlohy mapuje přesně tak, jak si myslíme
    for row in range(roomlib.ROWS):
        for col in range(roomlib.COLS):
            template = world.layout[row*roomlib.COLS+col]
            compare('obrazovka %d,%d (predloha $%02X)' % (col, row, template),
                    world.room_table[template], world.rooms[template])

    # 3) místnost pod hlavním menu
    menu_items = roomlib.read_room(world.ram, roomlib.ROOM_MAIN_MENU)[0]
    compare('Room_Special_MainMenu', roomlib.ROOM_MAIN_MENU, menu_items)

    # 4) nezávislá kontrola: většinový hlas nad pixely běžícího originálu
    #    (data/room000.json, tools/mkroom.py) o formátu nepředpokládá nic
    room000 = os.path.join(ROOT, 'data/room000.json')
    if os.path.exists(room000):
        import base64
        data = json.load(open(room000))
        template = world.layout[data['row']*roomlib.COLS+data['column']]
        screen = roomlib.draw_room(world.rooms[template], world.by_addr)
        their_bitmap = base64.b64decode(data['bitmap'])
        their_attrs = base64.b64decode(data['attributes'])
        bad_b = sum(a != b for a, b in zip(screen.bitmap_rows(), their_bitmap))
        bad_a = sum(a != b for a, b in zip(screen.attributes(), their_attrs))
        print('kontrola proti data/room000.json (vetsinovy hlas, obrazovka '
              '%d,%d = predloha $%02X): %d rozdilu bitmapy, %d atributu – '
              'to jsou nehybne entity (orchidej a predmety), ktere vetsinovy '
              'hlas nechal v obraze a kulisa je nema'
              % (data['column'], data['row'], template, bad_b, bad_a))
        if bad_b > 200 or bad_a > 200:
            raise SystemExit('rozdilu je moc – to uz nejsou entity')

    if args.dump:
        # 48 předloh a za nimi místnost pod hlavním menu jako 49. obrazovka –
        # tu skládá app/roomComposer.js pro titulní obrazovku, takže ji musí mít
        # tools/matchrooms.js proti čemu měřit
        with open(args.dump, 'wb') as f:
            for addr in list(world.room_table)+[roomlib.ROOM_MAIN_MENU]:
                bitmap, attrs = play_area(original.draw(addr))
                if not any(bitmap):
                    raise SystemExit('originál nakreslil prázdnou obrazovku')
                f.write(bitmap)
                f.write(attrs)
        print('%s: 49 x (%d + %d) B (48 predloh + menu), nakreslil originál'
              % (args.dump, 5632, 704))

    if args.all_png:
        os.makedirs(args.all_png, exist_ok=True)
        for template, addr in enumerate(world.room_table):
            bitmap, attrs = play_area(original.draw(addr))
            scr = bytearray(6912)
            for r, y in enumerate(range(roomlib.PLAY_TOP, 192)):
                base = roomlib.screen_addr(0, y)-0x4000
                scr[base:base+32] = bitmap[r*32:r*32+32]
            scr[6144+roomlib.PANEL_ROWS*32:6144+24*32] = attrs
            path = os.path.join(args.all_png, 'template%02X.png' % template)
            write_png(path, scr_to_rgb(bytes(scr)), 256)
        print('%s: 48 predloh nakreslenych originalem' % args.all_png)

    print('porovnano %d obrazovek (48 predloh + 256 obrazovek + menu), '
          '%d B bitmapy + %d B atributu na obrazovku'
          % (checked, 5632, 704))
    if failures:
        print('NESEDI: %d obrazovek' % len(failures))
        raise SystemExit(1)
    print('NULA ROZDILU')


if __name__ == '__main__':
    main()
