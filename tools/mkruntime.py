#!/usr/bin/env python3
"""Runtime obraz RAM: hra je na kazetě zašifrovaná, dešifruje se až za běhu.

    PYTHONPATH=tools/vendor ./tools/mkruntime.py [--frames N]

Na kazetě je celý blok od `$6000` výš uložený **znegovaný** (`CPL`); rutina
`Decryption` (`$5B80`, viz `sources/asm/README.md`) ho po nahrání projde a
teprve pak skočí do hry (`GameEntry` `$6000` → `$995A`). Kazetový obraz
z `tap2sna.py` je tedy nečitelný a disassemblovat i vytahovat data se dá jen
z **runtime** obrazu: hra se nechá doběhnout do titulní obrazovky a teprve pak
se opíše paměť.

Výstup: `build/sabrewulf-run.bin` – RAM `$4000–$FFFF`, 49 152 B.
"""
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
ROOT = os.path.dirname(HERE)

from skoolkit.snapshot import Snapshot                          # noqa: E402
from skoolkit.simulator import Simulator                        # noqa: E402
from skoolkit.simutils import from_snapshot, PC                 # noqa: E402
from skoolkit.trace import Tracer                               # noqa: E402
try:
    from skoolkit.csimulator import CSimulator
except ImportError:                                             # pragma: no cover
    CSimulator = None

# Dešifrování i rozjezd menu se stihne mnohem dřív; 250 snímků je rezerva.
FRAMES = 250


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--frames', type=int, default=FRAMES,
                    help='kolik snímků nechat hru běžet (default %d)' % FRAMES)
    args = ap.parse_args()

    src = os.path.join(ROOT, 'build/sabrewulf.z80')
    dst = os.path.join(ROOT, 'build/sabrewulf-run.bin')
    if not os.path.exists(src):
        raise SystemExit('chybi %s – spust nejdriv tools/mksnapshot.sh' % src)
    snapshot = Snapshot.get(src)
    cls = CSimulator or Simulator
    simulator = from_snapshot(cls, snapshot, {}, {'ay': [None] * 16},
                              {'fast_djnz': False, 'fast_ldir': False}, None)
    tracer = Tracer(simulator, snapshot.border, snapshot.out7ffd, snapshot.outfffd,
                    list(snapshot.ay), snapshot.outfe, True)
    simulator.set_tracer(tracer)

    def draw(scr, frame, border, keyboard):
        for i in range(8):
            keyboard[i] = 0        # v menu se nemačká nic
        return frame < args.frames

    tracer.run(snapshot.pc, -1, 0, 0, True, draw, None, None, None, '$', '04X', '04X')
    mem = simulator.memory
    ram = bytes(mem[0x4000:0x10000])
    with open(dst, 'wb') as f:
        f.write(ram)

    # Kontrola, že dešifrování skutečně proběhlo: vstupní bod a text copyrightu.
    entry = ram[0x2000:0x2005]                      # $6000
    text = bytes(ram[0x2007:0x2007 + 46])           # $6007
    ok = entry == bytes((0xF3, 0x31, 0x00, 0x60, 0xC3)) and text.startswith(b'COPYRIGHT 1984')
    print('%s: %d B, PC=$%04X' % (dst, len(ram), simulator.registers[PC]))
    print('  $6000: %s' % ' '.join('%02X' % b for b in entry))
    print('  $6007: %r' % text)
    print('  desifrovano: %s' % ('ANO' if ok else 'NE – obraz je k nicemu'))
    if not ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
