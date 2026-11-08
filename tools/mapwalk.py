#!/usr/bin/env python3
"""**Průchodnost světa z kolizního pravidla** – a její ověření na originálu (M3).

    ./tools/mapwalk.py
    ./tools/mapwalk.py --check
    PYTHONPATH=tools/vendor ./tools/mapwalk.py --verify [--samples N] [--all]

M2 odvozoval mapu přechodů z **pixelových mezer** na hranách předloh a v 31
vodorovných hranicích se rozešel s dobovou mapou od Einara Saukase. Byla to
otevřená otázka a M2 ji nechal otevřenou: „buď má hra pravidlo průchodnosti,
které jsme neodměřili, nebo je ta mapa stylizovaná."

M3 to pravidlo zná: ★ **kolize se neptá na pixely.** `$B873` prochází tentýž
seznam kusů kulisy, ze kterého se místnost kreslí, a u každého kusu si vezme
jeho **obálku** z jeho vlastní hlavičky; obálka Sabremana je `LD BC,$160E`
(`$AF40`), tedy 22 px svisle a 14 px vodorovně. Hranice je průchodná, když
existuje souřadnice, na které je volno z obou stran – z odcházející strany na
krajní souřadnici „uvnitř" (x = 239, y = 191) a z přicházející na souřadnici
vstupu (x = 0, y = 39). Všechna ta čísla jsou operandy skutečných instrukcí
(`data/physics.json`, `tools/dumpphysics.py`), takže se nic nehádá.

Odtud počítá `tools/dumpworld.py` `passages` v `data/world.json`. **Tenhle
nástroj to ověřuje**, a to dvěma způsoby:

* `--check` proti dobové mapě a proti pixelové metodě M2,
* `--verify` **proti běžícímu originálu**: hra se spustí v simulátoru, Sabreman
  se postaví k hranici a drží se směrová klávesa. Rozhoduje hra, ne mapa.

★ Výsledek je v `sources/docs/disasm_notes.md` §15: **hra prošla všemi 29
hranicemi, kde odvození říká „otevřeno" a dobová mapa „zavřeno"**. Otevřená
otázka M2 je tím uzavřená ve prospěch dat – ta mapa je v těch místech
stylizovaná.
"""
import argparse, io, json, os, sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import roomlib                                                  # noqa: E402
from mapworld import reference_openness, REFERENCE_MAP           # noqa: E402

UP, DOWN, LEFT, RIGHT = 1, 2, 4, 8
DIRECTIONS = (('right', RIGHT, 1, 0, 'W'), ('left', LEFT, -1, 0, 'Q'),
              ('down', DOWN, 0, 1, 'R'), ('up', UP, 0, -1, 'E'))
SLOT = 90                       # kolik snímků má jedna zkoušená hranice
# Otevřená hranice se zkouší **z krajní souřadnice, na které je podle pravidla
# volno** – tam stačí pár snímků a přechod přijde hned; kdyby se držela
# klávesa dál, Sabreman by prošel i další obrazovkou. Zavřená se zkouší ze
# středu obrazovky a klávesa se drží, dokud je čas: pravidlo tvrdí, že se
# k hraně nedá dojít, a tohle mu dává celou obrazovku na to, aby se zmýlilo.
# Na konci každé hranice zůstane pás bez kláves: přechod obrazovky trvá
# v originálu šest až osm snímků (překresluje se celá plocha) a bez té pauzy
# by se zápis polohy z předchozí hranice potkal s postavením na tu další.
POKE = 10                       # a tolik snímků na začátku se poloha zapisuje
PRESS_OPEN, PRESS_CLOSED = 20, SLOT-POKE-24


class Walk:
    """Průchodnost světa spočítaná z kolizního pravidla originálu."""

    def __init__(self):
        self.world = roomlib.World()
        self.physics = json.load(open(os.path.join(ROOT, 'data/physics.json')))
        v = self.physics['values']
        self.box = (v['boxHeight'], v['boxWidth'])
        self.edge_x = 0xFF-v['exitWidth']
        self.enter_x = v['enterLeftX']
        self.edge_y = v['exitBottomY']-1
        self.enter_y = v['enterTopY']
        self.bottom_y = v['enterBottomY']
        self.top_y = v['exitTopY']
        self.layout = self.world.layout

    def free(self, col, row, x, y):
        items = self.world.rooms[self.layout[row*16+col]]
        return roomlib.collides(self.world.ram, items, x, y, *self.box) is None

    def gap(self, col, row, dx, dy):
        """Souřadnice, na kterých se z (col,row) dá projít hranicí; a k tomu
        souřadnice, na kterých je volno aspoň z naší strany."""
        nc, nr = col+dx, row+dy
        if not (0 <= nc < 16 and 0 <= nr < 16):
            return [], []
        if dx:
            leaving = self.edge_x if dx > 0 else self.enter_x
            arriving = self.enter_x if dx > 0 else self.edge_x
            ours = [y for y in range(self.top_y, self.edge_y+1)
                    if self.free(col, row, leaving, y)]
            return [y for y in ours if self.free(nc, nr, arriving, y)], ours
        leaving = self.edge_y if dy > 0 else self.top_y
        arriving = self.enter_y if dy > 0 else self.bottom_y
        ours = [x for x in range(0, self.edge_x+1)
                if self.free(col, row, x, leaving)]
        return [x for x in ours if self.free(nc, nr, x, arriving)], ours

    def exits(self):
        """Bitová maska východů pro všech 256 obrazovek."""
        out = bytearray(256)
        for row in range(16):
            for col in range(16):
                mask = 0
                for name, bit, dx, dy, key in DIRECTIONS:
                    common, _ = self.gap(col, row, dx, dy)
                    if common:
                        mask |= bit
                out[row*16+col] = mask
        return bytes(out)


def stored_exits():
    """Průchody, jak je uložil `tools/dumpworld.py` do `data/world.json`."""
    world = json.load(open(os.path.join(ROOT, 'data/world.json')))
    rows = world['passages']['exits']
    return b''.join(bytes.fromhex(row) for row in rows)


def horizontal_vertical(exits):
    """Množiny otevřených hranic ve tvaru, ve kterém je čte dobová mapa."""
    horizontal = {(col, row) for row in range(16) for col in range(15)
                  if exits[row*16+col] & RIGHT}
    vertical = {(col, row) for row in range(15) for col in range(16)
                if exits[row*16+col] & DOWN}
    return horizontal, vertical


def check(walk):
    """Porovná průchodnost s dobovou mapou a s pixelovou metodou M2."""
    mine = walk.exits()
    stored = stored_exits()
    if mine != stored:
        print('POZOR: data/world.json nesedi s prepoctem – spust '
              'tools/dumpworld.py')
    horizontal, vertical = horizontal_vertical(mine)
    ref_h, ref_v = reference_openness(REFERENCE_MAP)
    print('kontrola proti %s' % os.path.relpath(REFERENCE_MAP, ROOT))
    print('  svisle:    %3d/240 souhlasi (moje %d otevrenych, mapa %d)'
          % (240-len(vertical ^ ref_v), len(vertical), len(ref_v)))
    print('  vodorovne: %3d/240 souhlasi (moje %d otevrenych, mapa %d)'
          % (240-len(horizontal ^ ref_h), len(horizontal), len(ref_h)))
    disputed = sorted(horizontal ^ ref_h)
    for col, row in disputed:
        print('     %2d,%-2d  predlohy $%02X -> $%02X: my %s, mapa %s'
              % (col, row, walk.layout[row*16+col], walk.layout[row*16+col+1],
                 'otevreno' if (col, row) in horizontal else 'zavreno',
                 'otevreno' if (col, row) in ref_h else 'zavreno'))
    if disputed:
        print('  ★ tyhle hranice ROZHODUJE HRA, ne mapa: '
              './tools/mapwalk.py --verify je zkusi projit v originalu')
    return disputed


def verify(walk, samples, everything, disputed):
    """Zkusí hranice projít **v běžícím originálu** – ten rozhoduje."""
    from skoolkit.snapshot import Snapshot
    from skoolkit.simulator import Simulator
    from skoolkit.simutils import from_snapshot
    try:
        from skoolkit.csimulator import CSimulator
    except ImportError:
        CSimulator = None
    import physlog

    # co se zkouší: (sloupec, řádek, směr, souřadnice, čekáme přechod?)
    cases, seen = [], set()
    DIRS = {name: (dx, dy) for name, bit, dx, dy, key in DIRECTIONS}

    GATE_ROOM, GATE_Y = 0x88, 0x80

    def add(col, row, direction, coord, expected):
        key = (col, row, direction)
        if key in seen:
            return
        # ★ obrazovka $88 nad y=$80 je **brána**: `$A18C` tam hru rovnou
        # dohraje ($9F6A GameComplete) a do herní smyčky se už nevrátí, takže
        # by tam běh zkoušení skončil. Hranice, které by Sabremana postavily
        # nebo přivedly do brány, se proto nezkoušejí.
        room, arriving = (row << 4) | col, ((row+DIRS[direction][1]) << 4)             | (col+DIRS[direction][0])
        vertical = DIRS[direction][1] != 0
        if not vertical and coord < GATE_Y and GATE_ROOM in (room, arriving):
            return
        if vertical and room == GATE_ROOM and direction == 'up':
            return
        seen.add(key)
        cases.append((col, row, direction, coord, expected))

    # nejdřív ty, o kterých se vede spor s dobovou mapou
    for col, row in disputed:
        common, _ = walk.gap(col, row, 1, 0)
        if common:
            add(col, row, 'right', common[len(common)//2], True)

    # a pak vzorek ze všech čtyř směrů: otevřené (má projít) i takové, kde je
    # zeď na naší straně (nesmí projít)
    for name, bit, dx, dy, key in DIRECTIONS:
        opened, closed = [], []
        for row in range(16):
            for col in range(16):
                common, ours = walk.gap(col, row, dx, dy)
                if common:
                    opened.append((col, row, common[len(common)//2]))
                elif not ours and 0 <= col+dx < 16 and 0 <= row+dy < 16:
                    middle = 0x78 if dy else (walk.top_y+walk.edge_y)//2
                    closed.append((col, row, middle))
        for group, expected in ((opened, True), (closed, False)):
            take = group if everything else group[::max(1, len(group)//samples)]
            for col, row, coord in take:
                add(col, row, name, coord, expected)

    print('zkousi se %d hranic v originalu (%d snimku na hranici)'
          % (len(cases), SLOT))
    wrong = run_cases(walk, cases)
    if wrong:
        # ★ Přechod obrazovky trvá v originálu šest až osm snímků a hlavní
        # smyčka při něm nestíhá; když jich několik přijde za sebou, může
        # dobíhající přechod sežrat celý pás kláves té další hranice. Takové
        # hranice se zkusí ještě raz, každá s čistým začátkem – teprve co
        # neprojde dvakrát, je rozdíl.
        print('  %d hranic se zkousi znovu (dobihal prechod z predchozi)'
              % len(wrong))
        retry = [(c[0], c[1], c[2], c[3], c[4]) for c in wrong]
        wrong = run_cases(walk, retry)
    opened = sum(1 for c in cases if c[4])
    print('  otevrenych hranic zkouseno %d, hra presla %d'
          % (opened, opened-sum(1 for w in wrong if w[4])))
    print('  zavrenych hranic zkouseno %d, hra nepresla %d'
          % (len(cases)-opened,
             len(cases)-opened-sum(1 for w in wrong if not w[4])))
    for col, row, direction, coord, expected, room, x, y in wrong:
        print('  ROZDIL %2d,%-2d %-5s souradnice %d: cekam %s, obrazovka '
              'skoncila na $%s (x=%s y=%s)'
              % (col, row, direction, coord,
                 'prechod' if expected else 'zeď',
                 '%02X' % room if room is not None else '??', x, y))
    if wrong:
        print('  ★ %d z %d hranic se chova jinak, nez pravidlo rika – '
              'pravidlo je spatne, ne hra' % (len(wrong), len(cases)))
        return False
    print('  ★ vsech %d zkousenych hranic se v ORIGINALU chova presne tak, '
          'jak rika kolizni pravidlo' % len(cases))
    return True


def run_cases(walk, cases):
    """Odsimuluje jeden běh originálu se seznamem hranic; vrátí ty, které se
    zachovaly jinak, než pravidlo říká."""
    from skoolkit.snapshot import Snapshot
    from skoolkit.simulator import Simulator
    from skoolkit.simutils import from_snapshot
    try:
        from skoolkit.csimulator import CSimulator
    except ImportError:
        CSimulator = None
    import physlog

    snapshot = Snapshot.get(os.path.join(ROOT, 'build/sabrewulf.z80'))
    if snapshot is None:
        raise SystemExit('nelze nacist build/sabrewulf.z80 – spust mksnapshot.sh')
    cls = CSimulator or Simulator
    sim = from_snapshot(cls, snapshot, {}, {'ay': [None]*16},
                        {'fast_djnz': False, 'fast_ldir': False}, None)
    tracer = physlog.StepTracer(sim, snapshot.border, snapshot.out7ffd,
                                snapshot.outfffd, list(snapshot.ay),
                                snapshot.outfe, True)
    sim.set_tracer(tracer)
    mem = sim.memory
    start = physlog.FIRST_FRAME+20
    results = {}
    keys = {name: key for name, bit, dx, dy, key in DIRECTIONS}
    # otevřená hranice: postav ho na krajní souřadnici, o které pravidlo
    # tvrdí, že je volná; zavřená: doprostřed obrazovky, ať má kam jít
    edge = {'right': lambda c: (walk.edge_x, c),
            'left': lambda c: (walk.enter_x, c),
            'down': lambda c: (c, walk.edge_y),
            'up': lambda c: (c, walk.top_y)}
    middle = {'right': lambda c: (0x40, c), 'left': lambda c: (0xC0, c),
              'down': lambda c: (c, 0x50), 'up': lambda c: (c, 0xB0)}
    # a kde má po přechodu skončit: u vstupní hrany, ne zaražený u té, ze
    # které vyšel (`$B81C` ho vrátí, když je vstup v kulise – ale číslo
    # obrazovky se změní tak jako tak, takže se musí kontrolovat i pozice).
    # Čte se `AFTER` snímků po změně obrazovky, protože sám přechod trvá šest
    # až osm snímků a poloha se zapíše až po překreslení plochy.
    landed = {'right': lambda x, y: x < 0x50, 'left': lambda x, y: x > 0xB0,
              'down': lambda x, y: y < 0x70, 'up': lambda x, y: y > 0x90}
    AFTER = 12
    changed = {}

    def draw(scr, frame, border, keyboard):
        for i in range(8):
            keyboard[i] = 0
        for begin, end, key in physlog.MENU:
            if begin <= frame < end:
                r, b = physlog.KEYS[key]
                keyboard[r] |= 1 << b
        if frame < start:
            return True
        index = (frame-start)//SLOT
        if index >= len(cases):
            return False
        col, row, direction, coord, expected = cases[index]
        phase = (frame-start) % SLOT
        # Postavení se zapíše několik snímků po sobě: přechod obrazovky
        # z předchozí hranice může být ještě v běhu a zapsal by polohu
        # zpátky. Tohle ho přepíše, takže je každá hranice na té předchozí
        # nezávislá.
        if phase <= POKE:
            x, y = (edge if expected else middle)[direction](coord)
            mem[0x9702] = 0x10                  # Sabreman pod kontrolou hráče
            mem[0x9703] = (row << 4) | col
            mem[0x9704] = 0                     # živ
            mem[0x9705], mem[0x9706] = x, y
            mem[0x9707] = 0x47                  # bílý, tedy ovladatelný
            mem[0x9708] = mem[0x9709] = 0       # rychlosti na nulu
            mem[0x970A] = mem[0x970B] = 0       # a zbytek záznamu taky
            changed[index] = None
            return True
        if phase <= POKE+(PRESS_OPEN if expected else PRESS_CLOSED):
            r, b = physlog.KEYS[keys[direction]]
            keyboard[r] |= 1 << b
        if changed.get(index) is None and mem[0x9703] != ((row << 4) | col):
            changed[index] = phase
        arrived = changed.get(index)
        if arrived is not None and phase == arrived+AFTER:
            results[index] = (mem[0x9703], mem[0x9705], mem[0x9706])
        elif phase == SLOT-1 and index not in results:
            results[index] = (mem[0x9703], mem[0x9705], mem[0x9706])
        return True

    with redirect_stdout(io.StringIO()):
        tracer.run(snapshot.pc, -1, 0, 0, True, draw, None, None, None,
                   '$', '04X', '04X')

    wrong = []
    for index, (col, row, direction, coord, expected) in enumerate(cases):
        room, x, y = results.get(index, (None, None, None))
        dx, dy = next((d, e) for n, b, d, e, k in DIRECTIONS if n == direction)
        want = ((row+dy) << 4) | (col+dx)
        crossed = (room == want
                   and (not expected or landed[direction](x, y)))
        if crossed != expected:
            wrong.append((col, row, direction, coord, expected, room, x, y))
    return wrong


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true',
                    help='porovnat s dobovou mapou')
    ap.add_argument('--verify', action='store_true',
                    help='zkusit hranice projit v běžícím originálu')
    ap.add_argument('--samples', type=int, default=12,
                    help='kolik hranic na směr a druh při --verify (výchozí 12)')
    ap.add_argument('--all', action='store_true',
                    help='při --verify zkusit všechny hranice, ne vzorek')
    args = ap.parse_args()

    walk = Walk()
    exits = walk.exits()
    opened = sum(bin(m).count('1') for m in exits)
    print('pruchodnost z kolizniho pravidla ($B873, obalka %d x %d px):'
          % (walk.box[1], walk.box[0]))
    print('  %d z 960 vnitrnich hranic je otevrenych, %d obrazovek ma aspon '
          'jeden vychod' % (opened, sum(1 for m in exits if m)))
    narrow = min((len(walk.gap(col, row, dx, dy)[0]) or 999)
                 for row in range(16) for col in range(16)
                 for n, b, dx, dy, k in DIRECTIONS)
    print('  nejuzsi pruchod je %d px siroky (svisle chodby jsou 2 px!)' % narrow)

    disputed = []
    if args.check or args.verify:
        disputed = check(walk)
    if args.verify:
        if not verify(walk, args.samples, args.all, disputed):
            raise SystemExit(1)


if __name__ == '__main__':
    main()
