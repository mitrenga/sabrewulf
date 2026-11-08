#!/usr/bin/env python3
"""Nahraje **referenční běhy originálu** pro kontrolu světa remaku (M4).

    PYTHONPATH=tools/vendor ./tools/traceentities.py [--out build/entity-traces.json]
                                                     [--case jmeno] [--print]

Disciplína je stejná jako u `matchscreen.py`, ne jako u `tracephysics.py`:
**originál si to spočítá sám**. Runtime obraz se nahraje do simulátoru
(k němu ROM Spectra, kterou přiváží SkoolKit – hra z ní bere mapu předmětů),
do volné paměti se položí

    LD IX,nnnn   ; záznam entity
    LD BC,nnnn   ; obálka, pokud ji rutina bere
    CALL rutina
    LD C,A / SBC A,A   ; přenos a A do paměti
    JP  konec

a co po tom zůstane v „game status bufferu", je **skutečná odpověď originálu**.
`tools/matchentities.js` proti tomu pustí `app/worldEntities.js` – kód, který
jde do prohlížeče – a hlásí každý rozdíl.

Nahrávají se tyhle případy (a je jich dohromady pár tisíc, protože se
procházejí **všechny** obrazovky, předlohy a semínka, ne vzorek):

| případ | rutina | co se zkouší |
|---|---|---|
| `contact` | `$AB01` | kontakt Sabremana s entitou po celé mřížce poloh, bez meče i s ním |
| `orchidSpawn` | `$A763` | rozbalení stavu orchideje do záznamu, 256 obrazovek × 4 stavy |
| `orchidSave` | `$A79F` | a jeho zabalení zpátky |
| `orchidBloom` | `$A680` | **celý cyklus kvetení**, 900 zavolání za sebou |
| `orchidPick` | `$A680` | a sebrání orchideje včetně toho, co udělá s barvou Sabremana |
| `objectSpawn` | `$A33B` | dva předměty obrazovky z bajtů mapy, 256 obrazovek |
| `objectPick` | `$A312`/`$A305` | sebrání předmětu, body a **extra život se stropem** |
| `amuletPlace` | `$A255` | rozmístění amuletu pro **všech 256 hodnot `Rand8`** |
| `amuletPick` | `$A1AB` | blikání a sebrání kusu amuletu, body a bit básně |
| `pointing` | `$9D41` | domorodci v přímce s zakopaným kusem |
| `visitRoom` | `$9D23` | bit navštívené obrazovky pro všech 256 obrazovek |
| `percent` | `$9CC6` | procento pro **všechny počty 1–260** |
| `objectMap` | `$A2BD` | generátor mapy předmětů i s bajty ROM, ze kterých čte |

Trasy se do gitu nedávají (jsou v `build/`), vyrobí se z kazety kdykoli znovu.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

from skoolkit.simulator import Simulator                         # noqa: E402
from skoolkit.simutils import PC, SP, ROM48                      # noqa: E402
try:
    from skoolkit.csimulator import CSimulator
except ImportError:                                             # pragma: no cover
    CSimulator = None

OUT = os.path.join(ROOT, 'build/entity-traces.json')
IMAGE = os.path.join(ROOT, 'build/sabrewulf-run.bin')
ENTITIES = os.path.join(ROOT, 'data/entities.json')

STUB = 0x5B00                   # tiskárenský buffer – hra ho nepoužívá
RESULT = 0x5B60                 # a sem si stub odloží přenos a A
STACK = 0x6000                  # zásobník jako v GameEntry ($6000)

PLAYER = 0x9702                 # ImmortalData[0] = Sabreman
ORCHID = 0x97DA
OBJECTS = 0x97E6
AMULET = 0x97FE
RECLEN = 12

DELAY = 0x96B5                  # GameDelayTimer – při nenulovém není kontakt
EFFECT = 0x96B0                 # OrchidEffectTimer
SWEEPS = 0x9693                 # počítadlo průchodů smyčkou entit
RAND = 0x9695                   # Rand8
FRAMES = 0x5C78                 # počítadlo ULA
SCORE = 0x9698                  # 1UP_Score, 3 B BCD
LIVES = 0x96BD
AMULET_BITS = 0x970D            # +$0B Sabremanova záznamu
VISITED = 0x96BF
PERCENT = 0x96B6                # stovky a jednotky procent
ORCHID_TABLE = 0xA7F8
OBJECT_MAP = 0xDDEC


class Original:
    """Simulátor s runtime obrazem a ROM, který umí zavolat rutinu originálu."""

    def __init__(self, ram_path=IMAGE):
        ram = open(ram_path, 'rb').read()
        if len(ram) != 49152:
            raise SystemExit('%s: cekam 49152 B RAM, mam %d' % (ram_path, len(ram)))
        if ram[0x6000-0x4000:0x6005-0x4000] != bytes((0xF3, 0x31, 0x00, 0x60, 0xC3)):
            raise SystemExit('%s neni runtime obraz – spust tools/mkruntime.py'
                             % ram_path)
        memory = [0]*65536
        # ★ ROM Spectra tady není kosmetika: `$A2BD` z ní bere „náhodu" pro
        # mapu předmětů (čte $0000-$20FF). SkoolKit ji přiváží.
        memory[0:0x4000] = list(open(ROM48, 'rb').read())
        memory[0x4000:0x10000] = list(ram)
        cls = CSimulator or Simulator
        self.sim = cls(memory, {'SP': STACK},
                       config={'fast_djnz': False, 'fast_ldir': False})
        self.memory = self.sim.memory

    def poke(self, addr, data):
        self.memory[addr:addr+len(data)] = list(data)

    def peek(self, addr, count=1):
        return bytes(self.memory[addr:addr+count])

    def word(self, addr):
        return self.memory[addr] | self.memory[addr+1] << 8

    def call(self, routine, ix=None, bc=None):
        """Zavolá rutinu originálu a vrátí `(A, přenos)` z jejího návratu."""
        stub = []
        if ix is not None:
            stub += [0xDD, 0x21, ix & 0xFF, ix >> 8]        # LD IX,nn
        if bc is not None:
            stub += [0x01, bc & 0xFF, bc >> 8]              # LD BC,nn
        stub += [0xCD, routine & 0xFF, routine >> 8,        # CALL rutina
                 0x4F,                                      # LD C,A
                 0x9F,                                      # SBC A,A (0/$FF)
                 0x32, RESULT & 0xFF, RESULT >> 8,          # LD (RESULT),A
                 0x79,                                      # LD A,C
                 0x32, (RESULT+1) & 0xFF, (RESULT+1) >> 8,  # LD (RESULT+1),A
                 0x76]                                      # HALT jako zastávka
        self.poke(STUB, stub)
        end = STUB+len(stub)-1
        self.sim.registers[SP] = STACK
        self.sim.run(STUB, end)
        if self.sim.registers[PC] != end:
            raise SystemExit('simulator skoncil na $%04X, cekam $%04X (rutina $%04X)'
                             % (self.sim.registers[PC], end, routine))
        return self.memory[RESULT+1], bool(self.memory[RESULT])


def hexs(data):
    return ''.join('%02X' % b for b in data)


def sane(original):
    """Stav, ve kterém hra na začátku kola je – nic víc, nic navíc."""
    original.poke(DELAY, [0])                   # kontakt povolen
    original.poke(EFFECT, [0])
    original.poke(0x969E, [0])                  # 1UP je na tahu
    original.poke(SCORE, [0, 0, 0])
    original.poke(0x96A5, [0, 0, 0])


# ---------------------------------------------------------------------------
# jednotlivé případy
# ---------------------------------------------------------------------------

def case_contact(original, layout):
    """`$AB01` – kontakt Sabremana s entitou po celé mřížce poloh."""
    rows = []
    entity = 0x9756                             # volný záznam nesmrtelné entity
    for sprite in (0x10, 0x20):
        for box in (0x0F0F, 0x0C0C, 0x160E):
            for x in range(80, 125, 3):
                for y in range(80, 125, 3):
                    sane(original)
                    original.poke(PLAYER, [sprite, 0xA8, 0, x, y, 0x47,
                                           0, 0, 0, 0, 0, 0])
                    original.poke(entity, [0x60, 0xA8, 0, 100, 100, 0x45,
                                           0, 0, 0, 0, 0, 0])
                    a, carry = original.call(0xAB01, ix=entity, bc=box)
                    rows.append({'sprite': sprite, 'box': box, 'x': x, 'y': y,
                                 'hit': carry})
    return rows


def case_orchid_spawn(original, layout):
    """`$A763` – stav předlohy rozbalený do záznamu orchideje."""
    rows = []
    states = [(0x00, 0x02), (0x0F, 0x06), (0x37, 0xFD), (0xA5, 0x5A)]
    for room in range(256):
        template = layout[room]
        for low, high in states:
            sane(original)
            original.poke(ORCHID_TABLE+template*2, [low, high])
            original.poke(PLAYER, [0x10, room, 0, 120, 112, 0x47,
                                   0, 0, 0, 0, 0, 0])
            original.poke(ORCHID, [0xEE]*RECLEN)
            original.call(0xA763, ix=PLAYER)
            rows.append({'room': room, 'template': template,
                         'state': [low, high],
                         'record': hexs(original.peek(ORCHID, RECLEN))})
    return rows


def case_orchid_save(original, layout):
    """`$A79F` – a záznam zabalený zpátky do dvou bajtů předlohy."""
    rows = []
    records = [
        [0x4F, 0xA8, 0x08, 0x78, 0x5F, 0x42, 0x0E, 0x00, 0, 0, 0, 0],
        [0x48, 0xA8, 0x00, 0x78, 0x5F, 0x46, 0xB0, 0x00, 0, 0, 0, 0],
        [0x4B, 0x35, 0x08, 0x20, 0x7F, 0x45, 0x38, 0x0A, 0, 0, 0, 0],
        [0x4D, 0x12, 0x00, 0x40, 0x3F, 0x43, 0xF8, 0x0F, 0, 0, 0, 0],
    ]
    for room in range(0, 256, 7):
        for record in records:
            sane(original)
            template = layout[room]
            original.poke(ORCHID_TABLE+template*2, [0x00, 0x00])
            original.poke(0x96AB, [room])           # obrazovka, ze které se odešlo
            original.poke(ORCHID, record)
            original.call(0xA79F, ix=PLAYER)
            rows.append({'room': room, 'template': template,
                         'record': hexs(bytes(record)),
                         'state': list(original.peek(ORCHID_TABLE+template*2, 2))})
    return rows


def bloom(original, layout, sabreman_at, calls):
    """`$A680` zavolaná `calls`-krát za sebou – celý cyklus kvetení."""
    rows = []
    sane(original)
    room = 0xA8                                     # startovní obrazovka
    template = layout[room]
    original.poke(ORCHID_TABLE+template*2, [0x0F, 0x02])
    original.poke(PLAYER, [0x10, room, 0, sabreman_at[0], sabreman_at[1], 0x47,
                           0, 0, 0, 0, 0, 0])
    original.poke(ORCHID, [0xEE]*RECLEN)
    original.call(0xA763, ix=PLAYER)
    for i in range(calls):
        # ★ oba počítadla se do trasy zapisují, protože orchidej na nich visí:
        # `$9693` je průchod smyčkou entit (fáze kvetení) a `FRAMES` volba
        # barvy a délka spánku
        sweeps = (i+1) & 0xFFFF
        frames = (i*2+7) & 0xFFFF
        original.poke(SWEEPS, [sweeps & 0xFF, sweeps >> 8])
        original.poke(FRAMES, [frames & 0xFF, frames >> 8])
        original.call(0xA680, ix=ORCHID)
        rows.append({'sweeps': sweeps, 'frames': frames,
                     'record': hexs(original.peek(ORCHID, RECLEN)),
                     'effect': original.memory[EFFECT],
                     'colour': original.memory[PLAYER+5]})
    return rows


def case_orchid_bloom(original, layout):
    """Kvetení naprázdno: Sabreman je daleko, takže se orchidej nesebere."""
    return bloom(original, layout, (0x20, 0xB0), 900)


def case_orchid_pick(original, layout):
    """A totéž se Sabremanem, který na orchideji stojí – sebere se."""
    position = None
    entities = json.load(open(ENTITIES))
    position = entities['orchid']['positions'][8]   # předloha startovní obrazovky
    return bloom(original, layout, (position[0], position[1]), 900)


def case_object_spawn(original, layout):
    """`$A33B` – dva předměty obrazovky z jejích dvou bajtů mapy."""
    rows = []
    pairs = [(0x00, 0x00), (0x05, 0x00), (0x00, 0x8D), (0x41, 0xC7),
             (0xFF, 0x80), (0x37, 0x4A)]
    for room in range(256):
        for first, second in pairs:
            sane(original)
            original.poke(OBJECT_MAP+room*2, [first, second])
            original.poke(PLAYER, [0x10, room, 0, 120, 112, 0x47,
                                   0, 0, 0, 0, 0, 0])
            original.poke(OBJECTS, [0xEE]*(RECLEN*2))
            original.call(0xA33B, ix=PLAYER)
            rows.append({'room': room, 'template': layout[room],
                         'map': [first, second],
                         'records': hexs(original.peek(OBJECTS, RECLEN*2))})
    return rows


def case_object_pick(original, layout):
    """`$A312` a `$A305` – sebrání předmětu, body a extra život."""
    rows = []
    room = 0xA8
    for kind in range(16):
        for lives in (1, 8, 9):
            for near in (True, False):
                sane(original)
                index = room*2
                original.poke(OBJECT_MAP+index, [0xC0 | kind])
                original.poke(LIVES, [lives])
                x, y = 100, 100
                original.poke(PLAYER, [0x10, room, 0,
                                       x if near else x+60, y, 0x47,
                                       0, 0, 0, 0, 0, 0])
                original.poke(OBJECTS, [0x80+kind, room, 0, x, y, 0x42,
                                        index & 0xFF, index >> 8, 0, 0, 0, 0])
                # obsluha podle sprite ID: JumpTable ($9B3E) pošle jediné
                # sprite ID předmětů jinam a to je „život"
                handler = original.word(0x9B3E+2*(0x80+kind))
                original.call(handler, ix=OBJECTS)
                rows.append({'kind': kind, 'lives': lives, 'near': near,
                             'handler': '$%04X' % handler,
                             'record': hexs(original.peek(OBJECTS, RECLEN)),
                             'map': original.memory[OBJECT_MAP+index],
                             'score': hexs(original.peek(SCORE, 3)),
                             'livesAfter': original.memory[LIVES]})
    return rows


def case_amulet_place(original, layout):
    """`$A255` – rozmístění amuletu pro všech 256 hodnot `Rand8`."""
    rows = []
    for rand in range(256):
        sane(original)
        original.poke(RAND, [rand])
        original.poke(AMULET, [0xEE]*(RECLEN*4))
        original.call(0xA255)
        rows.append({'rand': rand,
                     'records': hexs(original.peek(AMULET, RECLEN*4))})
    return rows


def case_amulet_pick(original, layout):
    """`$A1AB` – blikání a sebrání kusu amuletu."""
    rows = []
    room = 0xA8
    for sprite in (0x90, 0x91, 0x92, 0x93):
        for sweeps in (0, 1):
            for colour in (0x44, 0x45, 0x46, 0x47):
                for near in (True, False):
                    for other in (0x00, 0x0F):
                        sane(original)
                        original.poke(SWEEPS, [sweeps, 0])
                        x, y = 100, 100
                        original.poke(PLAYER, [0x10, room, 0,
                                               x if near else x+60, y, 0x47,
                                               0, 0, 0, 0, 0, other])
                        original.poke(AMULET, [sprite, room, 0, x, y, colour,
                                               0, 0, 0, 0, 0, 0])
                        original.call(0xA1AB, ix=AMULET)
                        rows.append({'sprite': sprite, 'sweeps': sweeps,
                                     'colour': colour, 'near': near,
                                     'bits': other,
                                     'record': hexs(original.peek(AMULET, RECLEN)),
                                     'bitsAfter': original.memory[AMULET_BITS],
                                     'score': hexs(original.peek(SCORE, 3))})
    return rows


def case_pointing(original, layout):
    """`$9D41` – je entita v přímce se zakopaným kusem amuletu?"""
    rows = []
    pieces = [
        [0x93, 0x59, 0, 0x40, 0x87, 0x46, 0, 0, 0, 0, 0, 0],
        [0x92, 0xA7, 0, 0x40, 0x87, 0x46, 0, 0, 0, 0, 0, 0],
        [0x91, 0xE2, 0, 0x28, 0x5F, 0x46, 0, 0, 0, 0, 0, 0],
        [0x00, 0x91, 0, 0x20, 0x5F, 0x46, 0, 0, 0, 0, 0, 0],
    ]
    entity = 0x9756
    for room in range(256):
        for x in (0x20, 0x38, 0x40, 0x48, 0x80, 0xC0):
            for y in (0x40, 0x5F, 0x68, 0x87, 0x90):
                sane(original)
                for i, piece in enumerate(pieces):
                    original.poke(AMULET+i*RECLEN, piece)
                original.poke(entity, [0x3C, room, 0, x, y, 0x43,
                                       0, 0, 0, 0, 0, 0])
                a, carry = original.call(0x9D41, ix=entity)
                rows.append({'room': room, 'x': x, 'y': y,
                             'hit': carry, 'distance': a})
    return rows, [hexs(bytes(p)) for p in pieces]


def case_visit_room(original, layout):
    """`$9D23 VisitRoom` – který bit ve `VisitedRooms` je která obrazovka."""
    rows = []
    for room in range(256):
        sane(original)
        original.poke(VISITED, [0]*32)
        original.poke(PLAYER, [0x10, room, 0, 120, 112, 0x47, 0, 0, 0, 0, 0, 0])
        original.call(0x9D23, ix=PLAYER)
        bits = original.peek(VISITED, 32)
        index = next((i for i, b in enumerate(bits) if b), None)
        rows.append({'room': room, 'byte': index,
                     'bit': None if index is None else bits[index].bit_length()-1,
                     'ones': sum(bin(b).count('1') for b in bits)})
    return rows


def case_percent(original, layout):
    """`$9CC6 PrintRoomsVisited` – procento pro všechny počty 1 až 260."""
    rows = []
    for count in range(1, 261):
        sane(original)
        rooms = min(count, 256)
        pieces = count-rooms
        bits = bytearray(32)
        for i in range(rooms):
            bits[i >> 3] |= 1 << (i & 7)
        original.poke(VISITED, bits)
        original.poke(AMULET_BITS, [(1 << pieces)-1])
        original.poke(PERCENT, [0, 0])
        original.call(0x9CC6)
        # $96B7 jsou jednotky a desítky procent v BCD, $96B6 stovky
        low = original.memory[PERCENT+1]
        rows.append({'count': count,
                     'percent': original.memory[PERCENT]*100
                                + (low >> 4)*10+(low & 0x0F)})
    return rows


def case_object_map(original, layout):
    """`$A2BD` – generátor mapy předmětů, i s bajty ROM, ze kterých čte."""
    rows = []
    for counter, frames, rand in ((0x0000, 0x0000, 0x00), (0x1234, 0x0056, 0x9A),
                                  (0x00FF, 0x00FF, 0x55), (0x0910, 0x0037, 0xC3)):
        sane(original)
        original.poke(SWEEPS, [counter & 0xFF, counter >> 8])
        original.poke(FRAMES, [frames & 0xFF, frames >> 8])
        original.poke(RAND, [rand])
        original.poke(OBJECT_MAP, [0xEE]*512)
        source = (counter & 0x1F) << 8 | (frames & 0xFF)
        original.call(0xA2BD)
        rows.append({'counter': counter, 'frames': frames, 'rand': rand,
                     'source': '$%04X' % source,
                     'sourceBytes': hexs(original.peek(source, 512)),
                     'map': hexs(original.peek(OBJECT_MAP, 512))})
    return rows


CASES = [
    ('contact', 'kontakt Sabremana s entitou ($AB01) po mřížce poloh',
     case_contact),
    ('orchidSpawn', 'stav předlohy rozbalený do záznamu orchideje ($A763)',
     case_orchid_spawn),
    ('orchidSave', 'a zabalený zpátky ($A79F)', case_orchid_save),
    ('orchidBloom', 'celý cyklus kvetení naprázdno ($A680, 900 zavolání)',
     case_orchid_bloom),
    ('orchidPick', 'kvetení se Sabremanem na orchideji – a účinek ($A737)',
     case_orchid_pick),
    ('objectSpawn', 'dva předměty obrazovky z bajtů mapy ($A33B)',
     case_object_spawn),
    ('objectPick', 'sebrání předmětu, body a extra život ($A312/$A305/$A2F8)',
     case_object_pick),
    ('amuletPlace', 'rozmístění amuletu pro všech 256 hodnot Rand8 ($A255)',
     case_amulet_place),
    ('amuletPick', 'blikání a sebrání kusu amuletu ($A1AB)', case_amulet_pick),
    ('pointing', 'domorodec v přímce se zakopaným kusem ($9D41)', case_pointing),
    ('visitRoom', 'bit navštívené obrazovky pro 256 obrazovek ($9D23)',
     case_visit_room),
    ('percent', 'procento pro všechny počty 1–260 ($9CC6)', case_percent),
    ('objectMap', 'generátor mapy předmětů i s bajty ROM ($A2BD)',
     case_object_map),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--image', default=IMAGE)
    ap.add_argument('--case', action='append', help='jen tyhle případy')
    ap.add_argument('--print', action='store_true', dest='show',
                    help='vypsat pár řádek každého případu')
    args = ap.parse_args()

    world = json.load(open(os.path.join(ROOT, 'data/world.json')))
    layout = []
    for row in world['templates']:
        layout += [int(row[i*2:i*2+2], 16) for i in range(16)]
    if len(layout) != 256:
        raise SystemExit('data/world.json nema 256 obrazovek')

    wanted = set(args.case or [])
    cases = {}
    extra = {}
    for name, note, function in CASES:
        if wanted and name not in wanted:
            continue
        original = Original(args.image)
        result = function(original, layout)
        if isinstance(result, tuple):
            rows, side = result
            extra[name] = side
        else:
            rows = result
        cases[name] = {'name': name, 'note': note, 'rows': rows}
        print('%-12s %5d radek   (%s)' % (name, len(rows), note))
        if args.show:
            for row in rows[:4]:
                print('   %s' % json.dumps(row, ensure_ascii=False)[:150])

    if wanted:
        return
    out = {
        'note': ('M4: referencni behy originalu pro kontrolu sveta remaku '
                 '(tools/traceentities.py). Porovnava se tools/matchentities.js. '
                 'Rutiny si vysledek pocitaji same v simulatoru, jako '
                 'u tools/matchscreen.py.'),
        'addresses': {'player': '$%04X' % PLAYER, 'orchid': '$%04X' % ORCHID,
                      'objects': '$%04X' % OBJECTS, 'amulet': '$%04X' % AMULET,
                      'objectMap': '$%04X' % OBJECT_MAP,
                      'orchidTable': '$%04X' % ORCHID_TABLE},
        'pointingPieces': extra.get('pointing'),
        'cases': cases,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(out, f)
        f.write('\n')
    rows = sum(len(case['rows']) for case in cases.values())
    print('ulozeno %s (%d radek, %d kB)'
          % (os.path.relpath(args.out), rows, os.path.getsize(args.out)//1024))


if __name__ == '__main__':
    main()
