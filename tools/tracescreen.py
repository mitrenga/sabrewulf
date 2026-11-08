#!/usr/bin/env python3
"""Nechá **originál nakreslit sprity do videopaměti** a opíše, co po něm zůstalo (M6).

    PYTHONPATH=tools/vendor ./tools/tracescreen.py [--out build/sprite-screens.bin]
                                                   [--case jmeno] [--png adresar]

Disciplína je stejná jako u `matchscreen.py`: **originál kreslí sám**. Runtime
obraz se nahraje do simulátoru, do volné paměti se položí

    CALL $BB5C   ; ClearPlayArea
    CALL $BB7C   ; ClearPlayArea_Attributes
    LD HL,předloha / CALL $BBF7    ; DrawRoom – džungle, do které se kreslí
    LD IX,záznam / CALL $B919      ; DrawEntity – pixely spritu
    CALL $BB24                     ; a jeho atribut
    HALT

a co po tom zůstane ve videopaměti (`$4000`-`$5AFF`), je **skutečný obraz
originálu i s attribute clashem**. `tools/matchsprites.js` proti tomu pustí
`app/screenComposer.js` – kód, který jde do prohlížeče – a porovná **buňku po
buňce**.

M2 tím samým způsobem uzavřel místnost (305 obrazovek, nula rozdílů); tohle je
druhá půlka obrazu, kterou M2 ještě neuměl zkontrolovat, protože sprity se
tehdy nekreslily.

Nahrávají se tyhle případy:

| případ | co se zkouší |
|---|---|
| `frames` | **všech 196 sprite ID** na jednom místě jedné předlohy |
| `x` | Sabreman na **všech 256 vodorovných polohách** – tedy všech osm posunů i oba okraje |
| `y` | a na všech svislých polohách hrací plochy, tedy všech osm řádků v buňce |
| `colours` | šestnáct barev proti čtyřem předlohám: ★ atribut se píše **jen do buněk s černým papírem** (`$BB47`), a na tom stojí celý vzhled hry |
| `wide` | nejširší sprity u pravého okraje, kde se adresování přetáčí |
| `poem` | ★ **celá obrazovka básně** pro všech 16 kombinací kusů amuletu: obrázek amuletu z `$C374` i sloka textu, kterou k tomu `DisplayPoem` vybere |

Referenci (`build/sprite-screens.bin`) i rejstřík (`build/sprite-cases.json`)
do gitu nedáváme; vyrobí se z kazety kdykoli znovu. `--png` uloží obrázky, aby
se dalo kouknout, co se vlastně porovnává.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import roomlib                                                   # noqa: E402
from scr2png import scr_to_rgb, write_png                        # noqa: E402
from skoolkit.simulator import Simulator                         # noqa: E402
from skoolkit.simutils import PC, SP, ROM48                      # noqa: E402
try:
    from skoolkit.csimulator import CSimulator
except ImportError:                                             # pragma: no cover
    CSimulator = None

IMAGE = os.path.join(ROOT, 'build/sabrewulf-run.bin')
OUT = os.path.join(ROOT, 'build/sprite-screens.bin')
INDEX = os.path.join(ROOT, 'build/sprite-cases.json')
ROOMS = os.path.join(ROOT, 'data/rooms.json')
FRAMES = os.path.join(ROOT, 'data/spriteframes.json')

CLEAR_PLAY_AREA = 0xBB5C
CLEAR_ATTRIBUTES = 0xBB7C
DRAW_ROOM = 0xBBF7
DRAW_ENTITY = 0xB919            # DrawEntity – pixely
DRAW_ATTRIBUTES = 0xBB24        # a atribut
STUB = 0x5B00
STACK = 0x6000
RECORD = 0x9792                 # NastieData[0] – volný záznam entity na pokusy
PLAYER = 0x9702                 # a Sabremanův záznam, ze kterého bere báseň
AMULET_BITS = 0x970D            # +$0B: které kusy amuletu hráč má
POEM_SCREEN = 0xA207            # smaže plochu, nakreslí amulet a vytiskne sloku
POEM_MUSIC = 0xA237             # a tady začíná hudba – tu do obrazu nechceme

SCREEN = 6912
SABREMAN = 0x10                 # sprite ID Sabremana stojícího čelem


class Original:
    """Simulátor s runtime obrazem, který umí nakreslit místnost i sprite."""

    def __init__(self, ram_path=IMAGE):
        ram = open(ram_path, 'rb').read()
        if len(ram) != 49152:
            raise SystemExit('%s: cekam 49152 B RAM, mam %d' % (ram_path, len(ram)))
        if ram[0x6000-0x4000:0x6005-0x4000] != bytes((0xF3, 0x31, 0x00, 0x60, 0xC3)):
            raise SystemExit('%s neni runtime obraz – spust tools/mkruntime.py'
                             % ram_path)
        memory = [0]*65536
        # ★ ROM Spectra tady není kosmetika: text básně se tiskne **jejím
        # fontem** – `PrintScreen` ($B589) bere glyf z `CHARS` ($5C36), a ta
        # systémová proměnná ukazuje do ROM (M1, disasm_notes §8). Bez ní by
        # obrazovka básně vyšla němá.
        memory[0:0x4000] = list(open(ROM48, 'rb').read())
        memory[0x4000:0x10000] = list(ram)
        cls = CSimulator or Simulator
        self.sim = cls(memory, {'SP': STACK},
                       config={'fast_djnz': False, 'fast_ldir': False})
        self.memory = self.sim.memory
        # ★ Tabulku předposunutých bajtů ($F000-$FFFF, `$B902`) runtime obraz
        # už má hotovou – zkontrolovat to, protože bez ní by se nakreslilo
        # něco jiného a nikdo by nepoznal proč.
        if any(self.memory[0xFF00+i] != i for i in range(256)) \
                or any(self.memory[0xFE00+i] for i in range(256)):
            raise SystemExit('tabulka posunu na $FF00 v obrazu nesedi')

    def run(self, stub):
        # ★ Celá videopaměť na nulu, ne jen hrací plocha: `ClearPlayArea` panel
        # nemaže a sprity u pravého okraje se do něj **přetáčejí** (osmibitové
        # `INC L`), takže bez tohohle by jeden případ špinil další.
        self.memory[0x4000:0x4000+SCREEN] = [0]*SCREEN
        self.memory[STUB:STUB+len(stub)] = stub
        end = STUB+len(stub)-1
        self.sim.registers[SP] = STACK
        self.sim.run(STUB, end)
        if self.sim.registers[PC] != end:
            raise SystemExit('simulator skoncil na $%04X, cekam $%04X'
                             % (self.sim.registers[PC], end))
        return bytes(self.memory[0x4000:0x4000+SCREEN])

    def draw(self, template, sprite, x, y, colour):
        """Nakreslí místnost a do ní jednu entitu – rutinami originálu."""
        self.memory[RECORD+0x00] = sprite
        self.memory[RECORD+0x03] = x
        self.memory[RECORD+0x04] = y
        self.memory[RECORD+0x05] = colour
        return self.run([
            0xCD, CLEAR_PLAY_AREA & 0xFF, CLEAR_PLAY_AREA >> 8,
            0xCD, CLEAR_ATTRIBUTES & 0xFF, CLEAR_ATTRIBUTES >> 8,
            0x21, template & 0xFF, template >> 8,
            0xCD, DRAW_ROOM & 0xFF, DRAW_ROOM >> 8,
            0xDD, 0x21, RECORD & 0xFF, RECORD >> 8,
            0xCD, DRAW_ENTITY & 0xFF, DRAW_ENTITY >> 8,
            0xCD, DRAW_ATTRIBUTES & 0xFF, DRAW_ATTRIBUTES >> 8,
            0x76])

    def poem(self, pieces):
        """Celá obrazovka básně pro daný počet kusů amuletu.

        `$A207` smaže hrací plochu, nakreslí obrázek amuletu a propadne do
        `$A234`, který vytiskne sloku a **pustí hudbu**. Hudba by trvala osm
        vteřin a nic by do obrazu nepřidala, takže se na její první instrukci
        ($A237) na dobu měření položí `RET`.
        """
        self.memory[AMULET_BITS] = pieces
        saved = self.memory[POEM_MUSIC]
        self.memory[POEM_MUSIC] = 0xC9              # RET
        try:
            return self.run([
                0xDD, 0x21, PLAYER & 0xFF, PLAYER >> 8,
                0xCD, POEM_SCREEN & 0xFF, POEM_SCREEN >> 8,
                0x76])
        finally:
            self.memory[POEM_MUSIC] = saved

    def room(self, template):
        """A samotná místnost, aby se dalo poznat, co do ní přidal sprite."""
        return self.run([
            0xCD, CLEAR_PLAY_AREA & 0xFF, CLEAR_PLAY_AREA >> 8,
            0xCD, CLEAR_ATTRIBUTES & 0xFF, CLEAR_ATTRIBUTES >> 8,
            0x21, template & 0xFF, template >> 8,
            0xCD, DRAW_ROOM & 0xFF, DRAW_ROOM >> 8,
            0x76])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--image', default=IMAGE)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--index', default=INDEX)
    ap.add_argument('--case', action='append')
    ap.add_argument('--png', help='ulozit obrazky do tohohle adresare')
    args = ap.parse_args()

    rooms = json.load(open(ROOMS))
    frames = json.load(open(FRAMES))
    templates = [int(entry['address'][1:], 16) for entry in rooms['templates']]
    if len(templates) != 48:
        raise SystemExit('cekam 48 predloh, mam %d' % len(templates))

    original = Original(args.image)
    cases, blobs = [], []

    def want(name):
        return not args.case or name in args.case

    def add(case, template, sprite, x, y, colour):
        screen = original.draw(templates[template], sprite, x, y, colour)
        cases.append({'case': case, 'index': len(cases), 'template': template,
                      'sprite': sprite, 'x': x, 'y': y, 'colour': colour})
        blobs.append(screen)

    # -- všech 196 sprite ID na jednom místě --------------------------------
    if want('frames'):
        for sprite in range(len(frames['sprites'])):
            add('frames', 0x08, sprite, 0x44, 0x80, 0x45)

    # -- všech 256 vodorovných poloh: osm posunů a oba okraje ---------------
    if want('x'):
        for x in range(256):
            add('x', 0x08, SABREMAN, x, 0x80, 0x45)

    # -- a svislé polohy hrací plochy ---------------------------------------
    if want('y'):
        for y in range(0x10, 0xC0):
            add('y', 0x08, SABREMAN, 0x44, y, 0x45)

    # -- ★ atribut se píše jen do buněk s černým papírem --------------------
    if want('colours'):
        for template in (0x00, 0x08, 0x11, 0x2F):
            for colour in (0x42, 0x43, 0x45, 0x46, 0x47, 0x07, 0x00, 0x78):
                add('colours', template, SABREMAN, 0x50, 0x60, colour)

    # -- nejširší sprity u pravého okraje -----------------------------------
    if want('wide'):
        width_at = {frame['address']: frame['width'] for frame in frames['frameData']}
        widest = sorted(range(len(frames['sprites'])),
                        key=lambda s: -width_at.get(frames['sprites'][s]['frame'], 0))[:4]
        for sprite in widest:
            for x in range(0xD0, 0x100, 2):
                add('wide', 0x08, sprite, x, 0x80, 0x46)

    # -- ★ celá obrazovka básně pro všech 16 kombinací kusů -----------------
    if want('poem'):
        for pieces in range(16):
            cases.append({'case': 'poem', 'index': len(cases), 'pieces': pieces})
            blobs.append(original.poem(pieces))

    with open(args.out, 'wb') as out:
        for blob in blobs:
            out.write(blob)

    # k rejstříku patří i **prázdná místnost** každé použité předlohy: bez ní
    # by se nedalo poznat, co je kulisa a co sprite
    used = sorted({case['template'] for case in cases if 'template' in case})
    rooms_out = {}
    for template in used:
        rooms_out['%d' % template] = original.room(templates[template]).hex()

    with open(args.index, 'w') as out:
        json.dump({
            'about': 'Rejstrik k build/sprite-screens.bin (tools/tracescreen.py, '
                     'M6). Kazdy pripad je 6912 B videopameti, tedy bitmapa '
                     '$4000-$57FF a atributy $5800-$5AFF, jak je nechal '
                     'original. tools/matchsprites.js proti tomu pousti '
                     'app/screenComposer.js.',
            'screenBytes': SCREEN,
            'cases': cases,
            'rooms': rooms_out,
        }, out)
        out.write('\n')

    if args.png:
        os.makedirs(args.png, exist_ok=True)
        step = max(1, len(cases)//24)
        for case in cases[::step]:
            path = os.path.join(args.png, '%s-%04d.png'
                                % (case['case'], case['index']))
            write_png(path, scr_to_rgb(blobs[case['index']]), 256, 2)
        print('%s: %d obrazku' % (os.path.relpath(args.png), len(cases[::step])))

    counts = {}
    for case in cases:
        counts[case['case']] = counts.get(case['case'], 0)+1
    print('%s: %d obrazovek (%s), %d B'
          % (os.path.relpath(args.out), len(cases),
             ', '.join('%s %d' % item for item in sorted(counts.items())),
             len(cases)*SCREEN))


if __name__ == '__main__':
    main()
