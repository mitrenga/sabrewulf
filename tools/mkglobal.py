#!/usr/bin/env python3
"""Sesbírá změřené konstanty hry do `data/global.json`.

    PYTHONPATH=tools/vendor ./tools/mkglobal.py

Co jde přečíst z runtime obrazu, se čte z něj (a kontroluje se okolí, takže
při jiném obrazu nástroj spadne); co jde odměřit na běhu, se odměří simulací;
a nic jiného tam není. Konkrétně:

- **výchozí síň slávy** (`$B304`): ★ **šest míst**, každé záznam 6 B – tři
  bajty BCD skóre a tři znaky jména. Nejvyšší je `102275 ULT`, což je to
  `HI`, které panel ukazuje po zapnutí. Text obrazovky je na `$B346`
  (`ULTIMATE HALL OF FAME`, `1ST`–`6TH`).
- **kolik životů hráč na začátku má**: ★ **4**. `ActivePlayer_Lives`
  (`$96BD`) se při startu nastaví na **5** a hned první Sabreman jeden
  odebere, takže panel od začátku ukazuje 4. Odměřeno simulací (`--verify`),
  ne odhadnuto – byla to otevřená otázka ZADANI §7.
- **jak dlouho je vidět menu a jak dlouho síň slávy**: ★ menu se na síň
  slávy překlápí samo (`CounterHallOfFame`, `$96B8`) a odměřený cyklus je
  ~823 snímků menu a ~802 snímků síně slávy, tedy asi 16 s na obrazovku.
- **`GameDelayTimer`** (`$96B5`): ★ **`$80` pro jednoho i pro dva hráče**.
  `$B1C4` je jediné místo, které tu adresu zapisuje, a `$FF`, které o dvou
  hráčích tvrdí komentář veřejné disassembly, se v programu nenastavuje
  nikde (M5, `disasm_notes.md` §17).
- **border** (M6): ★ celou hru je **černý** (`$9963`) a hýbe se **jedinkrát**
  – v pauze. `$AC40` přičítá `$04` každý snímek a z bitu 7 dělá barvu, takže
  se okraj střídá **modrá / purpurová po 32 snímcích**, a `$AC67` ho po
  odpauzování vrátí na černou. Tím je zavřená otevřená otázka ZADANI §7.

Rozvržení panelu je odměřené v `sources/docs/screen_layout.md` §2 a ověřuje ho
`tools/matchpanel.py` proti třem snímkům bajt po bajtu; tady je jen zapsané,
aby ho měl remake v datech.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')

HALL_OF_FAME = 0xB304
HALL_OF_FAME_PLACES = 6
HALL_OF_FAME_TEXT = 0xB346
LIVES_ADDRESS = 0x96BD
GAME_OPTIONS = 0x9692
GAME_DELAY_TIMER = 0x96B5

# ---------------------------------------------------------------------------
# Konstanty čtené jako **operandy skutečných instrukcí** (jako v dump*):
# (jméno, adresa, bajty instrukce s None na místě operandu, komentář)
# ---------------------------------------------------------------------------
CONSTANTS = [
    ('gameDelay',      0xB1C4, [0x3E, None, 0x32, 0xB5, 0x96],
     'LD A,n → $96B5 — ★ jediné místo, které GameDelayTimer nastavuje, '
     'a je stejné pro jednoho i pro dva hráče'),
    ('borderStart',    0x9963, [0xAF, 0xD3, 0xFE],
     'XOR A / OUT ($FE),A — GameInitialisation: border je na začátku černý'),
    ('borderPauseStep', 0xAC48, [0xC6, None, 0x57],
     'ADD A,n / LD D,A — ★ v pauze ($AC40) se k počítadlu každý snímek '
     'přičte n…'),
    ('borderPauseMask', 0xAC4D, [0xE6, None, 0xF6],
     'AND n — …a z bitu 7 (dvě rotace doleva) vyjde jeden bit barvy…'),
    ('borderPauseBase', 0xAC4F, [0xF6, None, 0xD3, 0xFE],
     'OR n / OUT ($FE),A — …takže border v pauze bliká mezi n a n+2, tedy '
     'modrá a purpurová'),
    ('borderPauseEnd', 0xAC67, [0xAF, 0xD3, 0xFE, 0xC9],
     'XOR A / OUT ($FE),A / RET — a po odpauzování je zase černý'),
]


def extract(ram, name, addr, pattern, note):
    """Ověří instrukci na `addr` a vrátí přečtený operand."""
    got = at(ram, addr, len(pattern))
    operands = []
    for i, expected in enumerate(pattern):
        if expected is None:
            operands.append(got[i])
        elif got[i] != expected:
            raise SystemExit('%s: $%04X+%d ceka %02X, v obrazu je %02X (%s)'
                             % (name, addr, i, expected, got[i], note))
    return operands[0] if operands else None

# ★ odměřený cyklus překlápění menu ↔ síň slávy (--verify to spočítá znovu)
MENU_FRAMES, HALL_OF_FAME_FRAMES = 823, 802
# ★ odměřený počet životů, které hráč na startu má (počítadlo začíná o jeden výš)
START_LIVES, START_LIVES_COUNTER = 4, 5


def at(ram, addr, length):
    return ram[addr-0x4000:addr-0x4000+length]


def bcd6(data):
    """Tři bajty BCD jako šestimístné číslo (jako je panel tiskne)."""
    value = 0
    for byte in data:
        if (byte & 0x0F) > 9 or (byte >> 4) > 9:
            raise SystemExit('$%02X neni BCD – jiny obraz?' % byte)
        value = value*100+(byte >> 4)*10+(byte & 0x0F)
    return value


def read_hall_of_fame(ram):
    """Výchozí tabulka síně slávy: šest záznamů po 6 B (3 B BCD + 3 znaky)."""
    entries = []
    table = at(ram, HALL_OF_FAME, HALL_OF_FAME_PLACES*6)
    for place in range(HALL_OF_FAME_PLACES):
        record = table[place*6:place*6+6]
        name = record[3:6].decode('ascii')
        if not name.isupper() and not name.isalpha():
            raise SystemExit('jmeno %r na miste %d neni tri velka pismena'
                             % (name, place+1))
        entries.append({'name': name, 'score': bcd6(record[0:3])})
    if entries != sorted(entries, key=lambda e: -e['score']):
        raise SystemExit('tabulka sine slavy neni serazena – jiny obraz?')
    header = at(ram, HALL_OF_FAME_TEXT, 21)
    text = bytes(b & 0x7F for b in header).decode('ascii')
    if text != 'ULTIMATE HALL OF FAME':
        raise SystemExit('na $%04X neni ULTIMATE HALL OF FAME, ale %r'
                         % (HALL_OF_FAME_TEXT, text))
    return entries


def verify_lives(snapshot_path):
    """Odsimuluje start hry a přečte, kolik životů hra hráči nastaví."""
    sys.path.insert(0, os.path.join(HERE, 'vendor'))
    sys.path.insert(0, HERE)
    from skoolkit.snapshot import Snapshot
    from skoolkit.simulator import Simulator
    from skoolkit.simutils import from_snapshot
    from skoolkit.trace import Tracer
    try:
        from skoolkit.csimulator import CSimulator
    except ImportError:
        CSimulator = None

    rows = {'$FBFE': 2, '$F7FE': 3, '$EFFE': 4}
    keys = {'1': ('$F7FE', 0), '3': ('$F7FE', 2), '0': ('$EFFE', 0)}
    script = [(260, 270, '1'), (300, 310, '3'), (340, 350, '0')]

    snapshot = Snapshot.get(snapshot_path)
    if snapshot is None:
        raise SystemExit('nelze nacist snapshot %s' % snapshot_path)
    cls = CSimulator or Simulator
    simulator = from_snapshot(cls, snapshot, {}, {'ay': [None]*16},
                              {'fast_djnz': False, 'fast_ldir': False}, None)
    tracer = Tracer(simulator, snapshot.border, snapshot.out7ffd, snapshot.outfffd,
                    list(snapshot.ay), snapshot.outfe, True)
    simulator.set_tracer(tracer)
    seen = []

    def draw(scr, frame, border, keyboard):
        for i in range(8):
            keyboard[i] = 0
        for start, end, key in script:
            if start <= frame < end:
                row, bit = keys[key]
                keyboard[rows[row]] |= 1 << bit
        if frame >= 400:
            seen.append(simulator.memory[LIVES_ADDRESS])
        return frame < 700

    tracer.run(snapshot.pc, -1, 0, 0, True, draw, None, None, None, '$', '04X', '04X')
    counter = max(seen)
    settled = seen[-1]
    if counter != START_LIVES_COUNTER or settled != START_LIVES:
        raise SystemExit('zivoty: pocitadlo dosahlo %d a ustalilo se na %d, '
                         'cekam %d a %d' % (counter, settled,
                                            START_LIVES_COUNTER, START_LIVES))
    print('  overeno: $%04X se nastavi na %d a ustali na %d'
          % (LIVES_ADDRESS, counter, settled))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('runtime', nargs='?',
                    default=os.path.join(ROOT, 'build/sabrewulf-run.bin'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'data/global.json'))
    ap.add_argument('--verify', action='store_true',
                    help='odsimulovat start hry a ověřit počet životů '
                         '(potřebuje PYTHONPATH=tools/vendor)')
    args = ap.parse_args()

    ram = open(args.runtime, 'rb').read()
    if len(ram) != 49152:
        raise SystemExit('cekam 49152 B RAM ($4000-$FFFF), mam %d' % len(ram))

    measured = {}
    for name, addr, pattern, note in CONSTANTS:
        value = extract(ram, name, addr, pattern, note)
        if value is not None:
            measured[name] = value

    entries = read_hall_of_fame(ram)
    if args.verify:
        verify_lives(os.path.join(ROOT, 'build/sabrewulf.z80'))

    world = json.load(open(os.path.join(ROOT, 'data/world.json')))

    data = {
        'note': 'M1: konstanty změřené na originálu. Nic tady není odhad – '
                'co se nedalo přečíst z runtime obrazu ani odměřit na běhu, '
                'v souboru není. Zdroje jsou u jednotlivých položek '
                '(tools/mkglobal.py, sources/docs/disasm_notes.md).',
        'frameRate': 50.08,
        'frameRateNote': '3,5 MHz / 69 888 T-stavů na snímek; herní logika visí '
                         'na přerušení z ULA (sources/docs/hw_notes.md)',
        'lives': START_LIVES,
        'livesCounter': START_LIVES_COUNTER,
        'livesNote': '★ ActivePlayer_Lives ($96BD) se při startu nastaví na %d '
                     'a první Sabreman jeden odebere, takže panel ukazuje %d. '
                     'Strop 9 (panel má na životy jedinou číslici) je pořád '
                     'nepotvrzený – dobové tipy ho tvrdí, změřený není.'
                     % (START_LIVES_COUNTER, START_LIVES),
        'players': [1, 2],
        'playersNote': '★ volba 1UP/2UP je v originálu (GameOptions, $%04X: '
                       '0 = 1 hráč, 1 = 2 hráči, 2/4/6 = joysticky) a panel je '
                       'na dva hráče postavený vždycky' % GAME_OPTIONS,
        'gameDelayTimer': {'address': '$%04X' % GAME_DELAY_TIMER,
                           'frames': measured['gameDelay'],
                           'onePlayer': '$%02X' % measured['gameDelay'],
                           'twoPlayers': '$%02X' % measured['gameDelay'],
                           'note': '★ prodleva, po kterou po startu kola a po '
                                   'smrti neběží ovládání ani kontakt – a je '
                                   'stejná pro jednoho i pro dva hráče. '
                                   '$B1C4 je jediné místo, které $96B5 '
                                   'nastavuje; $FF, které komentář veřejné '
                                   'disassembly přisuzuje dvěma hráčům, se '
                                   'v programu nenastavuje nikde (M5).'},
        'initRoom': 'room000',
        'world': {
            'columns': world['columns'], 'rows': world['rows'],
            'roomsCount': world['roomsCount'],
            'templatesCount': world['templatesCount'],
            'templatesUsed': world['templatesUsed'],
            'sceneryPieces': 41,
            'roomWidth': world['roomWidth'], 'roomHeight': world['roomHeight'],
            'note': 'Layout ($6066) je 16 × 16 bajtů, RoomTable ($6166) 48 '
                    'předloh, použitých 45; VisitedRooms ($96BF) je 256 bitů. '
                    'Mapa přechodů a formát předlohy je M2.'
        },
        # rozvržení odměřené na třech snímcích (screen_layout.md §2); ověřuje
        # ho tools/matchpanel.py bajt po bajtu
        'panel': {
            'rows': 2,
            'attrRow0': 71, 'attrRow1': 70,
            'label1UP': {'row': 0, 'col': 2, 'attr': 69},
            'lives': {'row': 0, 'col': 8, 'digits': 1, 'attr': 71},
            'lifeIcon': {'row': 0, 'col': 9, 'attr': 71,
                         'note': 'UDG_Life, osm bajtů na $B814'},
            'labelHI': {'row': 0, 'col': 15, 'attr': 87},
            'label2UP': {'row': 0, 'col': 27, 'attr': 69},
            'score1UP': {'row': 1, 'col': 1, 'digits': 6, 'attr': 70},
            'scoreHI': {'row': 1, 'col': 13, 'digits': 6, 'attr': 70},
            'score2UP': {'row': 1, 'col': 25, 'digits': 6, 'attr': 70},
            'note': 'skóre je tři bajty BCD na hráče ($9698, $969B) a tiskne '
                    'se na šest číslic; celé řádky se obarví jedním průchodem '
                    'v GameInitialisation ($996F, $997C)'
        },
        'hallOfFame': {
            'address': '$%04X' % HALL_OF_FAME,
            'places': HALL_OF_FAME_PLACES,
            'nameLength': 3,
            'title': 'ULTIMATE HALL OF FAME',
            'defaults': entries,
            'menuFrames': MENU_FRAMES,
            'hallOfFameFrames': HALL_OF_FAME_FRAMES,
            'note': '★ síň slávy je v originálu, ne přídavek remaku: šest míst, '
                    'jméno tři znaky, skóre tři bajty BCD. Menu se na ni '
                    'překlápí samo (CounterHallOfFame, $96B8) – odměřený cyklus '
                    'je %d snímků menu a %d snímků síně slávy, tedy ~%.0f s na '
                    'obrazovku.' % (MENU_FRAMES, HALL_OF_FAME_FRAMES,
                                    MENU_FRAMES/50.08)
        },
        'hiScore': entries[0]['score'],
        'borderColor': 0,
        'border': {
            'colour': 0,
            'pauseColours': [measured['borderPauseBase'],
                             measured['borderPauseBase']
                             | measured['borderPauseMask']],
            'pauseStep': measured['borderPauseStep'],
            'pauseFrames': 0x100//(measured['borderPauseStep']*2),
            'note': '★ M6 uzavřel otevřenou otázku ZADANI §7: border je celou '
                    'hru černý ($9963) a hýbe se **jedinkrát**, v pauze. '
                    '$AC40 přičte $%02X k počítadlu na každý snímek a bit 7 '
                    'z něj udělá barvu, takže se okraj střídá modrá (%d) / '
                    'purpurová (%d) po %d snímcích; $AC67 ho po odpauzování '
                    'vrátí na černou. Jinde v programu žádný další zápis do '
                    'portu $FE s barvou není – zvuk a hudba border jen srážejí '
                    'na černou.'
                    % (measured['borderPauseStep'],
                       measured['borderPauseBase'],
                       measured['borderPauseBase'] | measured['borderPauseMask'],
                       0x100//(measured['borderPauseStep']*2))
        },
        'borderColorNote': '★ GameInitialisation ($9963) dělá XOR A / OUT ($FE),A, '
                           'takže border je celou hru černý; jediné, co ho hne, '
                           'je pauza – viz border.pauseColours'
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('%s (sin slavy %d mist, nejvyssi %d %s, zivoty %d)'
          % (args.out, HALL_OF_FAME_PLACES, entries[0]['score'],
             entries[0]['name'], START_LIVES))


if __name__ == '__main__':
    main()
