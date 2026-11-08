#!/usr/bin/env python3
"""Zaznamená stav záznamu Sabremana **krok po kroku** – základ měření fyziky (M3).

    PYTHONPATH=tools/vendor ./tools/physlog.py --keys 620:700:W --frames 800
    PYTHONPATH=tools/vendor ./tools/physlog.py --watch 96B5:1 --changed-only

Hra běží v C simulátoru (rychlý), menu se odklikne samo (`1 PLAYER GAME`,
`KEYBOARD`, `START GAME`). Po každém **kroku Sabremana** se opíše 12 bajtů
jeho záznamu (`$9702`) a případně další sledované adresy (`--watch ADR[:N]`).
Na konci se vypíše, které offsety záznamu se v okně vůbec měnily – z toho
se pozná, který bajt je x, y, fáze animace atd.

★ **Kde je „krok Sabremana"**: `FrameUpdate` (`$99BC`) nastaví `IX` na `$9702`
a smyčka na `$99D0` skočí přes `JumpTable` (`$9B3E`) na obsluhu podle sprite ID;
obsluha se vrací na `$99F0`, kde se `IX` posune o 12 bajtů na další entitu.
Vzorkuje se tedy na `$99D0` (vstup kroku) a na `$99F0` (výstup) a filtruje se
podle `IX`, protože týmiž adresami procházejí i všechny ostatní entity.

Proč krok a ne snímek: **přechod mezi obrazovkami trvá jeden krok, ale šest
snímků** (hra při něm překresluje celou plochu a hlavní smyčka nestíhá).
Porovnávat se má krok proti kroku – snímek proti snímku by tam vyrobil rozdíl,
který není pravidlo hry, ale časování Z80.
"""
import argparse, io, os, sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
sys.path.insert(0, HERE)

from skoolkit.snapshot import Snapshot                          # noqa: E402
from skoolkit.simulator import Simulator                        # noqa: E402
from skoolkit.simutils import from_snapshot                     # noqa: E402
from skoolkit.trace import Tracer                               # noqa: E402
try:
    from skoolkit.csimulator import CSimulator
except ImportError:                                             # pragma: no cover
    CSimulator = None

SNAPSHOT = os.path.join(HERE, '..', 'build/sabrewulf.z80')
PLAYER = 0x9702                 # ImmortalData[0] = Sabreman
RECLEN = 12                     # $AC6B kopiruje 144 B = 12 zaznamu po 12 B

STEP_IN = 0x99D0                # smycka entit: skok pres JumpTable
STEP_OUT = 0x99F0               # obsluha se vraci sem (IX += 12)
STEP_IN_LEN = 2                 # $99D0 je LD A,R (ED 5F)

# menu originálu: 1 PLAYER GAME / KEYBOARD / START GAME
MENU = [(260, 270, '1'), (300, 310, '3'), (340, 350, '0')]
# hra se rozjede kolem snímku 470 a `GameDelayTimer` ($96B5 = $80) drží
# ovládání vypnuté do snímku ~620 (změřeno)
FIRST_FRAME = 620

KEYS = {  # klávesa -> (půlřádek, bit), viz hw_notes.md §6
    'CAPS': (0, 0), 'Z': (0, 1), 'X': (0, 2), 'C': (0, 3), 'V': (0, 4),
    'A': (1, 0), 'S': (1, 1), 'D': (1, 2), 'F': (1, 3), 'G': (1, 4),
    'Q': (2, 0), 'W': (2, 1), 'E': (2, 2), 'R': (2, 3), 'T': (2, 4),
    '1': (3, 0), '2': (3, 1), '3': (3, 2), '4': (3, 3), '5': (3, 4),
    '0': (4, 0), '9': (4, 1), '8': (4, 2), '7': (4, 3), '6': (4, 4),
    'P': (5, 0), 'O': (5, 1), 'I': (5, 2), 'U': (5, 3), 'Y': (5, 4),
    'ENTER': (6, 0), 'L': (6, 1), 'K': (6, 2), 'J': (6, 3), 'H': (6, 4),
    'SPACE': (7, 0), 'SYMSHIFT': (7, 1), 'M': (7, 2), 'N': (7, 3), 'B': (7, 4),
}


def parse_keys(specs):
    out = []
    for spec in specs or []:
        start, end, keys = spec.split(':')
        out.append((int(start), int(end), keys.upper().split('+')))
    return out


class StepTracer(Tracer):
    """Tracer, kterému krátké běhy nemažou stav klávesnice.

    `Tracer.run()` si při každém volání zakládá nové pole kláves, což u běhů
    kratších než snímek (zastávka na každém kroku Sabremana) znamená, že hra
    vždycky vidí všechno puštěné. Tady je pole jedno pro celý běh.
    """

    def __init__(self, *args, **kwargs):
        self._keys = [0]*8
        super().__init__(*args, **kwargs)

    @property
    def keyboard(self):
        return self._keys

    @keyboard.setter
    def keyboard(self, value):
        pass                    # drží se vlastní pole


def run_steps(frames, keyscript, watch=(), record=PLAYER, reclen=RECLEN,
              snapshot_path=SNAPSHOT, setup=None, setup_frame=FIRST_FRAME,
              sample=None):
    """Vzorkuje stav **na každý krok Sabremana**, ne na snímek.

    Vrací seznam `(snímek, vstupní záznam, vstupní watch, vzorek, výstupní
    záznam, výstupní watch)`. `setup(mem)` se zavolá jednou, až hra dojde do
    snímku `setup_frame` – tím se dá Sabreman postavit jinam nebo zabít.
    """
    snapshot = Snapshot.get(snapshot_path)
    if snapshot is None:
        raise SystemExit('nelze nacist snapshot %s' % snapshot_path)
    cls = CSimulator or Simulator
    sim = from_snapshot(cls, snapshot, {}, {'ay': [None]*16},
                        {'fast_djnz': False, 'fast_ldir': False}, None)
    tracer = StepTracer(sim, snapshot.border, snapshot.out7ffd, snapshot.outfffd,
                        list(snapshot.ay), snapshot.outfe, True)
    sim.set_tracer(tracer)
    mem, reg = sim.memory, sim.registers
    keyboard = tracer.keyboard
    log = []
    done_setup = False
    pc = snapshot.pc

    def frame_now():
        return reg[25]//sim.frame_duration

    def set_keys(frame):
        for i in range(8):
            keyboard[i] = 0
        for start, end, key in MENU:
            if start <= frame < end:
                r, b = KEYS[key]
                keyboard[r] |= 1 << b
        for start, end, group in keyscript:
            if start <= frame < end:
                for key in group:
                    r, b = KEYS[key]
                    keyboard[r] |= 1 << b

    def keys_per_frame(scr, frame, border, kb):
        """Drží klávesy i mezi zastávkami – běhy jsou kratší než snímek."""
        set_keys(frame)
        return frame < frames+2

    with redirect_stdout(io.StringIO()):
        while True:
            frame = frame_now()
            if frame >= frames:
                break
            set_keys(frame)
            if setup and not done_setup and frame >= setup_frame:
                setup(mem)
                done_setup = True
            tracer.run(pc, STEP_IN, 0, 0, True, keys_per_frame, None, None,
                       None, '$', '04X', '04X')
            pc = reg[24]
            if pc != STEP_IN:
                break
            if (reg[8] << 8 | reg[9]) != record:        # IX = záznam Sabremana
                sim.run(pc, pc+STEP_IN_LEN, False)
                pc = reg[24]
                continue
            frame = frame_now()
            entry = bytes(mem[record:record+reclen])
            entry_watch = tuple(bytes(mem[a:a+n]) for a, n in watch)
            entry_sample = sample(mem) if sample else None
            sim.run(pc, pc+STEP_IN_LEN, False)
            pc = reg[24]
            tracer.run(pc, STEP_OUT, 400000, 0, True, keys_per_frame, None,
                       None, None, '$', '04X', '04X')
            pc = reg[24]
            if pc == STEP_OUT:
                out = bytes(mem[record:record+reclen])
                out_watch = tuple(bytes(mem[a:a+n]) for a, n in watch)
            else:
                out, out_watch = None, None     # obsluha skončila jinudy
            log.append((frame, entry, entry_watch, entry_sample, out, out_watch))
    return log


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--frames', type=int, default=800)
    ap.add_argument('--from-frame', type=int, default=FIRST_FRAME,
                    help='od kterého snímku tisknout')
    ap.add_argument('--keys', action='append', help='od:do:KLAVESA[+KLAVESA]')
    ap.add_argument('--record', default='%X' % PLAYER, help='adresa záznamu (hex)')
    ap.add_argument('--len', type=int, default=RECLEN)
    ap.add_argument('--watch', action='append', default=[],
                    help='ADR[:N] další sledovaná adresa')
    ap.add_argument('--changed-only', action='store_true',
                    help='tisknout jen kroky, ve kterých se něco změnilo')
    args = ap.parse_args()

    watch = []
    for w in args.watch:
        parts = w.split(':')
        watch.append((int(parts[0], 16), int(parts[1]) if len(parts) > 1 else 1))

    log = run_steps(args.frames, parse_keys(args.keys), watch,
                    record=int(args.record, 16), reclen=args.len)

    prev = None
    for frame, rec, extra, _, out, _ in log:
        if frame < args.from_frame:
            continue
        line = ' '.join('%02X' % b for b in rec)
        if out:
            line += '  ->  ' + ' '.join('%02X' % b for b in out)
        if extra:
            line += '  |  ' + '  '.join(' '.join('%02X' % b for b in e) for e in extra)
        if args.changed_only and (rec, extra) == prev:
            continue
        prev = (rec, extra)
        print('%5d  %s' % (frame, line))

    window = [r for f, r, e, s, o, ow in log if f >= args.from_frame]
    if window:
        varying = [i for i in range(len(window[0]))
                   if len({r[i] for r in window}) > 1]
        print('\nmenici se offsety zaznamu: ' + ', '.join('+%d' % i for i in varying))
        for i in varying:
            vals = sorted({r[i] for r in window})
            print('  +%-2d  %d hodnot: %s' % (i, len(vals),
                  ' '.join('%02X' % v for v in vals[:24]) + (' ...' if len(vals) > 24 else '')))
        print('kroku: %d, snimku: %d' % (len(window), log[-1][0]-log[0][0]+1))


if __name__ == '__main__':
    main()
