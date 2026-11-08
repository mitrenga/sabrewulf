#!/usr/bin/env python3
"""Nahraje **referenční běhy originálu** pro kontrolu nepřátel remaku (M5).

    PYTHONPATH=tools/vendor ./tools/tracemonsters.py [--out build/monster-traces.json]
                                                     [--case jmeno] [--print]

Disciplína je stejná jako u `traceentities.py`: **originál si to spočítá sám**.
Runtime obraz se nahraje do simulátoru, do volné paměti se položí

    LD IX,nnnn   ; záznam entity
    LD BC,nnnn   ; obálka, pokud ji rutina bere
    CALL rutina
    …            ; přenos, A a případně DE/BC do paměti
    HALT

a co po tom zůstane v záznamu entity a v „game status bufferu", je **skutečná
odpověď originálu**. `tools/matchmonsters.js` proti tomu pustí
`app/worldMonsters.js` – kód, který jde do prohlížeče – a hlásí každý rozdíl.

Nahrávají se tyhle případy:

| případ | rutina | co se zkouší |
|---|---|---|
| `score` | `$A4B3` | body za zničeného nepřítele pro **všech 196 sprite ID** |
| `contact` | `$AB36` | kdo koho zabije: obě barvy Sabremana, osm póz, mřížka poloh |
| `bounce` | `$A44B` | odraz zvířete od okrajů obrazovky po celé mřížce rychlostí |
| `roam` | `$A630` | stěhování nesmrtelné entity za Sabremanovým řádkem, 256 × 256 |
| `materialise` | `$A3C5`/`$A3E0` | zhmotnění a **výběr druhu podle kusů amuletu** |
| `nastie` | `$A54F` | zvíře, které chodí, 300 průchodů za sebou |
| `chaser` | `$A4D7` | zvíře, které nahání |
| `rhino` | `$AD07` | nosorožec, včetně zahnání mečem |
| `hippo` | `$9E72`/`$9EB3` | hroch a jeho stěhování |
| `native` | `$AB74` | domorodec |
| `wulf` | `$A858` | Sabre Wulf: čekání, rozjezd po řádku, odehnání a návrat |
| `keeper` | `$9F16` | strážce brány s amuletem i bez něj, z obou stran |
| `fireball` | `$9D91` | ohnivá koule – ★ svislá rychlost z registru `R` se hlásí jako **nereprodukovatelná** |
| `spawn` | `$9A3C` | dosazování zvířat, 400 průchodů |
| `fireballSpawn` | `$9ABC` | odpočet `$96B4` a položení koule |
| `twoPlayer` | `$B235`/`$B1B7` | střídání hráčů a **ta chyba, kterou zmiňují dobové recenze** |

Trasy se do gitu nedávají (jsou v `build/`), vyrobí se z kazety kdykoli znovu.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

from traceentities import (Original, hexs, STUB, RESULT, STACK,      # noqa: E402
                           PLAYER, RECLEN, DELAY, SWEEPS, RAND, FRAMES,
                           SCORE, LIVES, AMULET_BITS)
from skoolkit.simutils import PC, SP                                # noqa: E402

OUT = os.path.join(ROOT, 'build/monster-traces.json')
MONSTERS = os.path.join(ROOT, 'data/monsters.json')

NASTIE = 0x9792                 # NastieData[0] – volný záznam na pokusy
IMMORTAL = 0x970E               # ImmortalData[1] – první nesmrtelná entita
FIREBALL = 0x9762               # a slot ohnivé koule (slot 8)
SPAWN_DELAY = 0x96B1            # prodleva dosazování zvířat
FIREBALL_TIMER = 0x96B4         # odpočet do ohnivé koule
WIDTH = 0x96AD                  # šířka entity, kterou si obsluha nastavuje
STATE_BYTE = 0x9704             # +2 Sabremanova záznamu: „umírá"
INACTIVE_LIVES = 0x96E0
PLAYER_FLAG = 0x969E
PER_ROOM = 0x96BE


def call_regs(original, routine, ix=None, bc=None, de=None):
    """Jako `Original.call`, ale opíše navíc `DE` a `BC` – to `$A44B` vrací."""
    stub = []
    if ix is not None:
        stub += [0xDD, 0x21, ix & 0xFF, ix >> 8]
    if bc is not None:
        stub += [0x01, bc & 0xFF, bc >> 8]
    if de is not None:
        stub += [0x11, de & 0xFF, de >> 8]
    stub += [0xCD, routine & 0xFF, routine >> 8,
             0xED, 0x53, (RESULT+2) & 0xFF, (RESULT+2) >> 8,   # LD (nn),DE
             0xED, 0x43, (RESULT+4) & 0xFF, (RESULT+4) >> 8,   # LD (nn),BC
             0x76]
    original.poke(STUB, stub)
    end = STUB+len(stub)-1
    original.sim.registers[SP] = STACK
    original.sim.run(STUB, end)
    if original.sim.registers[PC] != end:
        raise SystemExit('simulator skoncil na $%04X, cekam $%04X (rutina $%04X)'
                         % (original.sim.registers[PC], end, routine))
    return {'e': original.memory[RESULT+2], 'd': original.memory[RESULT+3],
            'c': original.memory[RESULT+4], 'b': original.memory[RESULT+5]}


def call_de(original, routine, ix, bc, de):
    """Jako `Original.call`, ale nastaví i `DE` – `$AB5E` čte bit 0 `D`."""
    stub = [0xDD, 0x21, ix & 0xFF, ix >> 8]
    if bc is not None:
        stub += [0x01, bc & 0xFF, bc >> 8]
    stub += [0x11, de & 0xFF, de >> 8,
            0xCD, routine & 0xFF, routine >> 8,
            0x4F, 0x9F, 0x32, RESULT & 0xFF, RESULT >> 8,
            0x79, 0x32, (RESULT+1) & 0xFF, (RESULT+1) >> 8,
            0x76]
    original.poke(STUB, stub)
    end = STUB+len(stub)-1
    original.sim.registers[SP] = STACK
    original.sim.run(STUB, end)
    if original.sim.registers[PC] != end:
        raise SystemExit('simulator skoncil na $%04X, cekam $%04X (rutina $%04X)'
                         % (original.sim.registers[PC], end, routine))
    return original.memory[RESULT+1], bool(original.memory[RESULT])


def call_seq(original, routine, ix):
    """Zavolá obsluhu entity s **definovaným** `DE`.

    ★ Několik rutin M5 nechává `D` (svislou souřadnici) na tom, co v registru
    zrovna zůstalo po předchozí entitě: `$A44B` se z bočního odrazu vrací bez
    toho, aby se `D` dotklo, a `$A54F` skáče na kontakt ($A59D) rovnou, když
    zvíře stojí. Reprodukovat zbytek v registru nejde a nemá smysl, tak se
    `DE` před každým voláním nastaví na **vlastní polohu entity** – což je to,
    co tam v drtivé většině průchodů opravdu je (nechal to tam `$B81C`).
    `app/worldMonsters.js` dělá totéž a je to tam takhle napsané.
    """
    x = original.memory[ix+3]
    y = original.memory[ix+4]
    return call_de(original, routine, ix, None, (y << 8) | x)


def sane(original):
    """Stav, ve kterém hra uprostřed kola je."""
    original.poke(DELAY, [0])
    original.poke(0x96B0, [0])              # OrchidEffectTimer
    original.poke(PLAYER_FLAG, [0])
    original.poke(SCORE, [0, 0, 0])
    original.poke(STATE_BYTE, [0])
    original.poke(WIDTH, [0x10])


def sabreman(original, sprite=0x10, room=0xA8, x=0x78, y=0x70, colour=0x47,
             state=0, amulet=0):
    record = [sprite, room, state, x, y, colour, 0, 0, 0, 0, 0, amulet]
    original.poke(PLAYER, record)


def entity(original, addr, sprite, room=0xA8, state=0, x=0x60, y=0x60,
           colour=0x45, dx=0, dy=0, age=0):
    original.poke(addr, [sprite, room, state, x, y, colour,
                         dx & 0xFF, dy & 0xFF, age, 0, 0, 0])


def clock(original, sweeps, frames, rand):
    original.poke(SWEEPS, [sweeps & 0xFF, sweeps >> 8])
    original.poke(FRAMES, [frames & 0xFF, frames >> 8])
    original.poke(RAND, [rand & 0xFF])


def score_of(original):
    data = original.peek(SCORE, 3)
    return int('%02X%02X%02X' % (data[0], data[1], data[2]))


# ---------------------------------------------------------------------------
# jednotlivé případy
# ---------------------------------------------------------------------------

def case_score(original, data):
    """`$A4B3` – kolik bodů dá zničený nepřítel; pro všech 196 sprite ID."""
    rows = []
    for sprite in range(data['jumpTable']['entries']):
        sane(original)
        sabreman(original)
        entity(original, NASTIE, sprite)
        original.call(0xA4B3, ix=NASTIE)
        rows.append({'sprite': sprite, 'score': score_of(original)})
    return rows


def case_contact(original, data):
    """`$AB36` – kdo koho zabije, po mřížce poloh a póz."""
    rows = []
    for colour in (0x47, 0x42):
        for sprite in (0x10, 0x14, 0x20, 0x24, 0x28, 0x2C, 0x40):
            for d in (0x00, 0x01):
                for x in range(0x50, 0x80, 5):
                    for y in range(0x50, 0x80, 5):
                        sane(original)
                        sabreman(original, sprite=sprite, x=x, y=y,
                                 colour=colour)
                        entity(original, NASTIE, 0x60, x=0x60, y=0x60)
                        a, carry = call_de(original, 0xAB36, NASTIE, 0x1313,
                                           d << 8)
                        rows.append({'colour': colour, 'sprite': sprite,
                                     'd': d, 'x': x, 'y': y, 'hit': carry,
                                     'killed': original.memory[STATE_BYTE]})
    return rows


def case_bounce(original, data):
    """`$A44B` – odraz od okrajů obrazovky."""
    rows = []
    for width in (0x10, 0x17, 0x20):
        for dx in (0x00, 0x20, 0x50, 0xB0, 0xE0):
            for dy in (0x00, 0x30, 0x80, 0xD0):
                for x in (0x00, 0x08, 0x60, 0xE0, 0xF8):
                    for y in (0x28, 0x40, 0xA0, 0xBE):
                        sane(original)
                        original.poke(WIDTH, [width])
                        sabreman(original)
                        entity(original, NASTIE, 0x60, x=x, y=y, dx=dx, dy=dy)
                        regs = call_regs(original, 0xA44B, ix=NASTIE,
                                         de=(y << 8) | x)
                        rows.append({'width': width, 'dx': dx, 'dy': dy,
                                     'x': x, 'y': y,
                                     'outX': regs['e'], 'outY': regs['d'],
                                     'bounce': regs['b']})
    return rows


def case_roam(original, data):
    """`$A630` – stěhování nesmrtelné entity za Sabremanovým řádkem."""
    rows = []
    for here in range(0, 256, 3):
        for there in range(0, 256, 7):
            for rand in (0x00, 0x01):
                sane(original)
                clock(original, 4, 8, rand)
                sabreman(original, room=here)
                entity(original, IMMORTAL, 0xA0, room=there, x=0x40, y=0x50)
                original.call(0xA630, ix=IMMORTAL)
                rows.append({'here': here, 'there': there, 'rand': rand,
                             'record': hexs(original.peek(IMMORTAL, RECLEN))})
    return rows


def case_materialise(original, data):
    """`$A3C5`/`$A3E0` – zhmotnění a výběr druhu podle kusů amuletu."""
    rows = []
    for amulet in range(16):
        for sweep in range(16):
            for rand in (0x03, 0x51):
                sane(original)
                clock(original, sweep, 7, rand)
                sabreman(original, amulet=amulet)
                entity(original, NASTIE, 0x06, x=0x40, y=0x50)
                original.call(0xA3E0, ix=NASTIE)
                rows.append({'amulet': amulet, 'sweeps': sweep, 'rand': rand,
                             'record': hexs(original.peek(NASTIE, RECLEN))})
    for sprite in range(1, 6):
        for x in (0x40, 0x74):
            for sabre in (0x10, 0x24):
                sane(original)
                clock(original, 3, 5, 0x11)
                sabreman(original, sprite=sabre)
                entity(original, NASTIE, sprite, x=x, y=0x70)
                original.call(0xA3C5, ix=NASTIE)
                rows.append({'shimmer': sprite, 'x': x, 'sabreman': sabre,
                             'record': hexs(original.peek(NASTIE, RECLEN)),
                             'score': score_of(original)})
    return rows


def sweeps_of(original, routine, addr, setup, calls, start_sweep=1):
    """Zavolá obsluhu `calls`-krát za sebou a opíše záznam po každém průchodu."""
    rows = []
    sane(original)
    setup(original)
    for i in range(calls):
        sweeps = (start_sweep+i) & 0xFFFF
        frames = (i*2+11) & 0xFFFF
        rand = (i*37+5) & 0xFF
        clock(original, sweeps, frames, rand)
        original.poke(SCORE, [0, 0, 0])
        original.poke(STATE_BYTE, [0])
        call_seq(original, routine, addr)
        rows.append({'sweeps': sweeps, 'frames': frames, 'rand': rand,
                     'record': hexs(original.peek(addr, RECLEN)),
                     'sabreman': hexs(original.peek(PLAYER, RECLEN)),
                     'width': original.memory[WIDTH],
                     'killed': original.memory[STATE_BYTE],
                     'score': score_of(original)})
    return rows


def case_nastie(original, data):
    """`$A54F` – zvíře, které si chodí po obrazovce."""
    rows = []
    for start in ((0x60, 0x0A, 0x30, 0x20), (0x64, 0x01, 0x00, 0x00),
                  (0x98, 0x03, 0xD0, 0xB0)):
        def setup(o, s=start):
            sabreman(o, x=0x78, y=0x70)
            entity(o, NASTIE, s[0], state=s[1], x=0x40, y=0x50, dx=s[2], dy=s[3])
        rows += sweeps_of(original, 0xA54F, NASTIE, setup, 120)
    # a totéž se Sabremanem, který na něm stojí – jednou bez meče, jednou s ním
    for sabre in (0x10, 0x24):
        def setup(o, sp=sabre):
            sabreman(o, sprite=sp, x=0x44, y=0x54)
            entity(o, NASTIE, 0x60, state=0x0A, x=0x40, y=0x50, dx=0x20, dy=0x00)
        rows += sweeps_of(original, 0xA54F, NASTIE, setup, 20)
    return rows


def case_chaser(original, data):
    """`$A4D7` – zvíře, které Sabremana nahání."""
    rows = []
    for at in ((0x78, 0x70), (0x20, 0x30), (0xC0, 0xB0)):
        def setup(o, p=at):
            sabreman(o, x=p[0], y=p[1])
            entity(o, NASTIE, 0x68, state=0x05, x=0x60, y=0x60)
        rows += sweeps_of(original, 0xA4D7, NASTIE, setup, 120)
    return rows


def case_rhino(original, data):
    """`$AD07` – nosorožec: chodí po světě a mečem se dá zahnat."""
    rows = []
    for sabre, x in ((0x10, 0x78), (0x18, 0x44), (0x24, 0x44)):
        def setup(o, sp=sabre, sx=x):
            sabreman(o, sprite=sp, x=sx, y=0x54)
            entity(o, IMMORTAL, 0x30, state=0, x=0x40, y=0x50, dx=0xD0)
        rows += sweeps_of(original, 0xAD07, IMMORTAL, setup, 90)
    return rows


def case_hippo(original, data):
    """`$9E72` a `$9EB3` – hroch a jeho stěhování."""
    rows = []
    for sabre, x in ((0x10, 0x78), (0x18, 0x44)):
        def setup(o, sp=sabre, sx=x):
            sabreman(o, sprite=sp, x=sx, y=0x54)
            entity(o, IMMORTAL, 0xA0, state=0, x=0x40, y=0x50, dx=0x20)
        rows += sweeps_of(original, 0x9E72, IMMORTAL, setup, 90)

    def setup_roam(o):
        sabreman(o, room=0x48, x=0x78, y=0x70)
        entity(o, IMMORTAL, 0xA4, room=0x88, x=0x40, y=0x50, dx=0x20)
    rows += sweeps_of(original, 0x9EB3, IMMORTAL, setup_roam, 60)
    return rows


def case_native(original, data):
    """`$AB74` – domorodec, včetně toho, jak ukazuje k amuletu."""
    rows = []
    for sabre, x in ((0x10, 0x78), (0x18, 0x44)):
        def setup(o, sp=sabre, sx=x):
            sabreman(o, sprite=sp, x=sx, y=0x54)
            entity(o, IMMORTAL, 0x3C, state=0, x=0x40, y=0x50, dx=0x20, dy=0x20)
        rows += sweeps_of(original, 0xAB74, IMMORTAL, setup, 90)
    return rows


def case_wulf(original, data):
    """`$A858` – Sabre Wulf: čekání mimo řádek, rozjezd, odehnání, návrat."""
    rows = []
    for room in (0xA8, 0xAF, 0x88):
        def setup(o, r=room):
            sabreman(o, room=r, x=0x78, y=0x70)
            entity(o, IMMORTAL, 0x50, room=0xA8, state=0, x=0x40, y=0x70,
                   dx=0x00)
        rows += sweeps_of(original, 0xA858, IMMORTAL, setup, 90)
    # a odehnání mečem: Sabreman stojí vpravo a seká doprava
    for sabre in (0x20, 0x28):
        def setup(o, sp=sabre):
            sabreman(o, sprite=sp, x=0x50, y=0x70)
            entity(o, IMMORTAL, 0x50, state=0, x=0x40, y=0x70, dx=0x40)
        rows += sweeps_of(original, 0xA858, IMMORTAL, setup, 60)
    return rows


def case_keeper(original, data):
    """`$9F16` – strážce brány s celým amuletem i bez něj."""
    rows = []
    for amulet in (0x00, 0x07, 0x0F):
        for x in (0x30, 0x90, 0xD0):
            def setup(o, a=amulet, sx=x):
                sabreman(o, room=0x88, x=sx, y=0x70, amulet=a)
                entity(o, IMMORTAL, 0x94, room=0x88, state=0, x=0x70, y=0x70)
            rows += sweeps_of(original, 0x9F16, IMMORTAL, setup, 40)
    # a ještě pod orchidejí: strážce zabíjí i tak ($AB3D pod barevným testem)
    def setup_orchid(o):
        sabreman(o, room=0x88, x=0x74, y=0x70, colour=0x42, amulet=0)
        entity(o, IMMORTAL, 0x94, room=0x88, state=0, x=0x70, y=0x70)
    rows += sweeps_of(original, 0x9F16, IMMORTAL, setup_orchid, 10)
    return rows


def case_fireball(original, data):
    """`$9D91` – ohnivá koule; svislá rychlost z `R` se hlásí zvlášť."""
    rows = []
    for at in ((0x78, 0x70), (0x30, 0x40), (0xB0, 0xA0)):
        def setup(o, p=at):
            sabreman(o, x=p[0], y=p[1])
            entity(o, FIREBALL, 0x34, state=0x03, x=0x60, y=0x60,
                   colour=0x46, dx=0x40, dy=0x40, age=0x20)
        rows += sweeps_of(original, 0x9D91, FIREBALL, setup, 120)
    return rows


def case_spawn(original, data):
    """`$9A3C` – dosazování zvířat, průchod po průchodu."""
    rows = []
    sane(original)
    sabreman(original)
    original.poke(SPAWN_DELAY, [0x10])
    original.poke(PER_ROOM, [data['values']['nastiePerRoom']])
    for slot in range(data['values']['nastieSlots']):
        original.poke(NASTIE+slot*RECLEN, [0]*RECLEN)
    for i in range(400):
        sweeps = (i+1) & 0xFFFF
        frames = (i*2+3) & 0xFFFF
        rand = (i*53+9) & 0xFF
        clock(original, sweeps, frames, rand)
        original.call(0x9A3C)
        slots = [hexs(original.peek(NASTIE+s*RECLEN, RECLEN))
                 for s in range(data['values']['nastieSlots'])]
        rows.append({'sweeps': sweeps, 'frames': frames, 'rand': rand,
                     'delay': original.memory[SPAWN_DELAY], 'slots': slots})
    return rows


def case_fireball_spawn(original, data):
    """`$9ABC` – odpočet `$96B4` a položení koule."""
    rows = []
    sane(original)
    sabreman(original)
    original.poke(FIREBALL, [0]*RECLEN)
    original.poke(FIREBALL_TIMER, [0x10])
    for i in range(200):
        sweeps = (i+1) & 0xFFFF
        frames = (i*3+5) & 0xFFFF
        rand = (i*29+7) & 0xFF
        clock(original, sweeps, frames, rand)
        original.call(0x9ABC)
        rows.append({'sweeps': sweeps, 'frames': frames, 'rand': rand,
                     'timer': original.memory[FIREBALL_TIMER],
                     'record': hexs(original.peek(FIREBALL, RECLEN))})
    return rows


def case_two_player(original, data):
    """`$B235` a `$B1B7` – střídání hráčů, a co se přitom stane s životy.

    ★ Tady je ta chyba, kterou zmiňují dobové recenze, a je to jedna
    instrukce: `$B1B7` ubere život **až po** prohození hráčů (`$B205` volá
    `$B235` a teprve pak `$B1F1` → `$B1B7`), takže smrt jednoho hráče zaplatí
    ten druhý. V jednom hráči se to nepozná, protože `$AA27` jde jinudy.
    """
    rows = []
    for lives, other in ((5, 3), (3, 1), (1, 1), (0, 2), (2, 0)):
        sane(original)
        original.poke(LIVES, [lives])
        original.poke(INACTIVE_LIVES, [other])
        original.poke(PLAYER_FLAG, [0])
        sabreman(original)
        before = {'lives': lives, 'other': other,
                  'flag': original.memory[PLAYER_FLAG]}
        original.call(0xB235)                       # ChangePlayer
        swapped = {'lives': original.memory[LIVES],
                   'other': original.memory[INACTIVE_LIVES],
                   'flag': original.memory[PLAYER_FLAG]}
        original.call(0xB1B7)                       # a start of the new turn
        after = {'lives': original.memory[LIVES],
                 'other': original.memory[INACTIVE_LIVES],
                 'delay': original.memory[DELAY],
                 'spawnDelay': original.memory[SPAWN_DELAY],
                 'fireball': original.memory[FIREBALL_TIMER]}
        rows.append({'before': before, 'swapped': swapped, 'after': after})
    return rows


CASES = [
    ('score', case_score),
    ('contact', case_contact),
    ('bounce', case_bounce),
    ('roam', case_roam),
    ('materialise', case_materialise),
    ('nastie', case_nastie),
    ('chaser', case_chaser),
    ('rhino', case_rhino),
    ('hippo', case_hippo),
    ('native', case_native),
    ('wulf', case_wulf),
    ('keeper', case_keeper),
    ('fireball', case_fireball),
    ('spawn', case_spawn),
    ('fireballSpawn', case_fireball_spawn),
    ('twoPlayer', case_two_player),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--case', action='append',
                    help='nahrát jen tenhle případ (dá se opakovat)')
    ap.add_argument('--print', action='store_true', dest='show')
    args = ap.parse_args()

    data = json.load(open(MONSTERS))
    original = Original()
    traces, total = {}, 0
    for name, function in CASES:
        if args.case and name not in args.case:
            continue
        rows = function(original, data)
        traces[name] = rows
        total += len(rows)
        print('%-15s %6d radku' % (name, len(rows)))
        if args.show and rows:
            print('   %s' % json.dumps(rows[0], ensure_ascii=False)[:160])

    out = {'note': 'referencni behy originalu pro M5 (tools/tracemonsters.py); '
                   'proti nim jde tools/matchmonsters.js',
           'cases': traces}
    with open(args.out, 'w') as handle:
        json.dump(out, handle)
        handle.write('\n')
    print('%s: %d radku' % (os.path.relpath(args.out), total))


if __name__ == '__main__':
    main()
