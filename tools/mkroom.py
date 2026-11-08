#!/usr/bin/env python3
"""Vytáhne z běžícího originálu **statickou** podobu jedné místnosti.

    PYTHONPATH=tools/vendor ./tools/mkroom.py [--out data/room000.json]
    PYTHONPATH=tools/vendor ./tools/mkroom.py --diff-frame 520,700

Princip je stejný jako u underwurlde v M1: hra se spustí v simulátoru (jako
`playtrace.py`), Sabreman se skriptem kláves prochází startovní místností
a v pravidelných rozestupech se ukládá celý obraz videopaměti. Pohyblivé věci
(Sabreman, zvířata, domorodci, kvetoucí orchideje) jsou na každém místě jen
zlomek snímků, takže **většinový hlas přes bajty** vrátí to, co se nehýbe –
čistou kulisu džungle. Nic se nedokresluje, výstupem jsou skutečné bajty
videopaměti originálu.

Ukládá se **jen hrací plocha** (znakové řádky 2–23, tj. 256 × 176 px):
5632 B bitmapy + 704 B atributů, base64, bitmapa lineárně po pixelových
řádcích. Panel si remake kreslí sám (`mkfont.py`, `screen_layout.md`).

Vzniklo to jako **provizorium M1**, protože formát místnosti tehdy nebyl známý.
M2 ho zná (`tools/roomlib.py`, `tools/dumprooms.py`) a obrazovku skládá
z předlohy a kusů kulisy, takže tenhle nástroj už není zdroj obrázku – zůstává
jako **nezávislá kontrola**: většinový hlas nad pixely běžícího originálu
o formátu nepředpokládá nic, a přesto se s poskládanou předlohou `$08` shodne
až na nehybné entity (35 bajtů bitmapy a 114 atributů, což jsou právě ta
orchidej a předměty na startovní obrazovce). Tím se formát poprvé potvrdil.

★ **Která z 256 obrazovek to je, se tady rovnou odměří**: `$9703` je číslo
aktuální obrazovky (čte ho `$BBDD` jako `(IX+$01)` pro `IX = $9702`) a při
vzorkování v něm stojí `$A8`, tedy **sloupec 8, řádek 10**. Nezávisle to
potvrzuje `tools/dumpworld.py`, který totéž číslo čte staticky z `$AC77`.
"""
import argparse, base64, json, os, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
sys.path.insert(0, HERE)

from scr2png import scr_to_rgb, write_png                      # noqa: E402
from skoolkit.snapshot import Snapshot                          # noqa: E402
from skoolkit.simulator import Simulator                        # noqa: E402
from skoolkit.simutils import from_snapshot                     # noqa: E402
from skoolkit.trace import Tracer                               # noqa: E402
try:
    from skoolkit.csimulator import CSimulator
except ImportError:                                             # pragma: no cover
    CSimulator = None

# půlřádky klávesnice, stejně jako v playtrace.py (hw_notes.md §6)
ROWS = {'$FEFE': 0, '$FDFE': 1, '$FBFE': 2, '$F7FE': 3,
        '$EFFE': 4, '$DFFE': 5, '$BFFE': 6, '$7FFE': 7}
KEYS = {
    'CAPS': ('$FEFE', 0), 'Z': ('$FEFE', 1), 'X': ('$FEFE', 2), 'C': ('$FEFE', 3), 'V': ('$FEFE', 4),
    'Q': ('$FBFE', 0), 'W': ('$FBFE', 1), 'E': ('$FBFE', 2), 'R': ('$FBFE', 3), 'T': ('$FBFE', 4),
    '1': ('$F7FE', 0), '2': ('$F7FE', 1), '3': ('$F7FE', 2), '4': ('$F7FE', 3), '5': ('$F7FE', 4),
    '0': ('$EFFE', 0), '9': ('$EFFE', 1), '8': ('$EFFE', 2), '7': ('$EFFE', 3), '6': ('$EFFE', 4),
    'ENTER': ('$BFFE', 0),
    'SPACE': ('$7FFE', 0), 'SYMSHIFT': ('$7FFE', 1), 'M': ('$7FFE', 2), 'N': ('$7FFE', 3), 'B': ('$7FFE', 4),
}

# (od snímku, do snímku, klávesa): projít menu (1 hráč, klávesnice, start) a pak
# Sabremanem projít startovní místnost do všech čtyř směrů, aby na žádném místě
# nestál dost dlouho, aby vyhrál většinový hlas. Hra začíná kreslit místnost
# kolem snímku 470; do snímku 1000 se ze startovní místnosti neodejde (změřeno:
# atributy se mění plynule, žádný skok, jaký dělá flick-screen).
SCRIPT = [
    (260, 270, '1'),    # 1 PLAYER GAME
    (300, 310, '3'),    # KEYBOARD
    (340, 350, '0'),    # START GAME
    (520, 600, 'W'),    # doprava
    (620, 700, 'Q'),    # doleva
    (720, 800, 'R'),    # nahoru
    (820, 900, 'E'),    # dolů
]
SAMPLE_FROM, SAMPLE_TO, SAMPLE_STEP = 480, 1000, 4

CURRENT_ROOM = 0x9703               # číslo aktuální obrazovky za běhu hry
COLS = 16                           # mřížka světa (Layout, $6066)

PANEL_ROWS = 2                      # znakové řádky panelu (0–1)
PLAY_ROWS = 24-PANEL_ROWS           # 22 znakových řádků hrací plochy
PLAY_LINES = PLAY_ROWS*8            # 176 px


def screen_offset(y):
    """Offset pixelového řádku y (0–191) v 6912B obrazu."""
    third, char_row, pix = y >> 6, (y >> 3) & 7, y & 7
    return (third << 11) | (pix << 8) | (char_row << 5)


def play_area(scr):
    """Hrací plocha jako (bitmapa 5632 B po řádcích shora dolů, atributy 704 B)."""
    bitmap = bytearray()
    for y in range(PANEL_ROWS*8, 192):
        base = screen_offset(y)
        bitmap += scr[base:base+32]
    return bytes(bitmap), bytes(scr[6144+PANEL_ROWS*32:6144+24*32])


def majority(samples):
    """Po bajtech nejčastější hodnota – co se nehýbe, to vyhraje."""
    out = bytearray(len(samples[0]))
    for i in range(len(out)):
        out[i] = Counter(s[i] for s in samples).most_common(1)[0][0]
    return bytes(out)


def to_scr(bitmap, attrs):
    """Zpátky do 6912B obrazu (panel černý) – kvůli náhledu přes scr2png."""
    scr = bytearray(6912)
    for row, y in enumerate(range(PANEL_ROWS*8, 192)):
        scr[screen_offset(y):screen_offset(y)+32] = bitmap[row*32:row*32+32]
    scr[6144+PANEL_ROWS*32:6144+24*32] = attrs
    return bytes(scr)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('snapshot', nargs='?',
                    default=os.path.join(HERE, '..', 'build/sabrewulf.z80'))
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'data/room000.json'))
    ap.add_argument('--png', default=os.path.join(HERE, '..', 'build/room000.png'))
    ap.add_argument('--frames', type=int, default=SAMPLE_TO+10)
    ap.add_argument('--diff-frame', help='čísla snímků (oddělená čárkou): uloží je '
                    'do build/diffNNNNN.scr a vypíše mapu buněk, ve kterých se liší '
                    'od statické místnosti – tím se hledají sprity pro mksprite.py')
    args = ap.parse_args()

    snapshot = Snapshot.get(args.snapshot)
    if snapshot is None:
        raise SystemExit('nelze nacist snapshot %s' % args.snapshot)
    cls = CSimulator or Simulator
    simulator = from_snapshot(cls, snapshot, {}, {'ay': [None]*16},
                              {'fast_djnz': False, 'fast_ldir': False}, None)
    tracer = Tracer(simulator, snapshot.border, snapshot.out7ffd, snapshot.outfffd,
                    list(snapshot.ay), snapshot.outfe, True)
    simulator.set_tracer(tracer)

    samples, rooms = [], []
    diff_frames = [int(n) for n in args.diff_frame.split(',')] if args.diff_frame else []
    diff_scr = {}

    def draw(scr, frame, border, keyboard):
        for i in range(8):
            keyboard[i] = 0
        for start, end, key in SCRIPT:
            if start <= frame < end:
                row, bit = KEYS[key]
                keyboard[ROWS[row]] |= 1 << bit
        if SAMPLE_FROM <= frame <= SAMPLE_TO and (frame-SAMPLE_FROM) % SAMPLE_STEP == 0:
            samples.append(bytes(scr))
            rooms.append(simulator.memory[CURRENT_ROOM])
        if frame in diff_frames:
            diff_scr[frame] = bytes(scr)
        return frame < args.frames

    tracer.run(snapshot.pc, -1, 0, 0, True, draw, None, None, None, '$', '04X', '04X')
    if len(samples) < 20:
        raise SystemExit('malo vzorku (%d) – zkontroluj SCRIPT' % len(samples))

    if len(set(rooms)) != 1:
        raise SystemExit('behem vzorkovani se obrazovka zmenila (%s) – vzorky '
                         'nejsou z jedne mistnosti'
                         % ' '.join('$%02X' % r for r in sorted(set(rooms))))
    room_number = rooms[0]
    bitmaps, attributes = zip(*(play_area(s) for s in samples))
    bitmap, attrs = majority(bitmaps), majority(attributes)

    room = {
        'note': 'Statická podoba startovní místnosti, vytažená většinovým '
                'hlasem z běhu originálu (tools/mkroom.py). Od M2 už není '
                'zdrojem obrázku – obrazovka se skládá z předlohy a kusů '
                'kulisy (data/rooms.json, data/scenery.json) – ale zůstává '
                'jako nezávislá kontrola toho formátu.',
        'name': 'JUNGLE',
        # ★ startovní obrazovka ve mřížce 16 × 16 (Layout, $6066): odměřeno
        # z $9703 při vzorkování, po celou dobu $A8 = sloupec 8, řádek 10
        'room': '$%02X' % room_number,
        'column': room_number % COLS, 'row': room_number//COLS,
        'width': 256, 'height': PLAY_LINES,
        'samples': len(samples),
        'sampleFrames': [SAMPLE_FROM, SAMPLE_TO, SAMPLE_STEP],
        'bitmap': base64.b64encode(bitmap).decode('ascii'),
        'attributes': base64.b64encode(attrs).decode('ascii')
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(room, f, indent=2)
        f.write('\n')
    print('%s (%d vzorku, %d B bitmapy + %d B atributu, obrazovka $%02X = %d,%d)'
          % (args.out, len(samples), len(bitmap), len(attrs), room_number,
             room_number % COLS, room_number//COLS))

    for dframe in sorted(diff_scr):
        fb, fa = play_area(diff_scr[dframe])
        path = os.path.join(os.path.dirname(os.path.abspath(args.png)),
                            'diff%05d.scr' % dframe)
        with open(path, 'wb') as f:
            f.write(diff_scr[dframe])
        write_png(path[:-4]+'.png', scr_to_rgb(diff_scr[dframe]), 256)
        print('%s' % path)
        print('zmeny proti staticke mistnosti, snimek %d (cislice = inkoust '
              'menici se bunky, sloupce 0-31, znakove radky 2-23):' % dframe)
        for row in range(PLAY_ROWS):
            line = ''
            for col in range(32):
                changed = any(fb[(row*8+p)*32+col] != bitmap[(row*8+p)*32+col]
                              for p in range(8))
                if fa[row*32+col] != attrs[row*32+col]:
                    changed = True
                line += ('%X' % (fa[row*32+col] & 7)) if changed else '.'
            print('%2d %s' % (row+PANEL_ROWS, line))

    if args.png:
        write_png(args.png, scr_to_rgb(to_scr(bitmap, attrs)), 256)
        print('nahled: %s' % args.png)


if __name__ == '__main__':
    main()
