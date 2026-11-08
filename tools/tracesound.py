#!/usr/bin/env python3
"""Nahraje **co originál doopravdy pošle do reproduktoru** – pulz po pulzu (M6).

    PYTHONPATH=tools/vendor ./tools/tracesound.py [--out build/sound-traces.json]
                                                  [--case jmeno] [--wav adresar]

Disciplína je stejná jako u `traceentities.py` a `tracemonsters.py`: **originál
si to zahraje sám**. Runtime obraz se nahraje do simulátoru, do volné paměti se
položí

    LD IX,záznam / LD DE,skladba / …
    CALL rutina
    HALT

a k simulátoru se přidá **odposlech portu**: každý `OUT ($FE),A`, který rutina
udělá, se zapíše i s časem v **T-stavech Z80**. Výška tónu na jednobitovém
beeperu **není nic než ten čas**, takže tahle nahrávka je zvuk originálu úplně –
nic se z ní neztratí, protože v ní nic jiného není.

`tools/matchsound.js` proti tomu pustí `app/beeper.js` – kód, který jde do
prohlížeče – a hlásí každý rozdíl. Chyba jednoho T-stavu v jedné instrukci se
tím pozná jako rozdíl, ne jako trochu falešný tón.

Nahrávají se tyhle případy:

| případ | rutina | co se zkouší |
|---|---|---|
| `squareWave` | `$BF74` | **všech 256 hodnot `B`**, tedy celý rozsah výšky tónu |
| `waveSequence` | `$BF6D` | mřížka `B` × `C` |
| `step` | `$BF4B` | **všech 256 stavů počítadla** `$96B3`, obojí barvou Sabremana |
| `fly` | `$A9F8` | všech 256 fází odletu |
| `land` | `$BF2F` | dopad |
| `repel` | `$BF17` | zahnání mečem (a strážce brány) |
| `object` | `$BF25` | předmět a extra život |
| `orchid` | `$BF2A` | orchidej a klapnutí písmene v síni slávy |
| `orchidEnd` | `$BEC6` | dohasínající orchidej |
| `materialise` | `$BF08` | všech 256 sprite ID |
| `pointing` | `$BF3D` | mřížka vzdálenost × x × y |
| `fireball` | `$BECC` | všech 16 stavů počítadla průchodů |
| `explosion` | `$BEEE` | mřížka `$9693` × `Rand8`, a k tomu **bajty ROM**, ze kterých rutina čte |
| `music` | `$BD6E` | **všechny čtyři skladby**, nota po notě |
| `menu` | `$BD51` | a `gameComplete` ještě jednou tou variantou, kterou hraje hlavní menu |

`--wav` uloží nahrávku i jako `.wav` (přes `skoolkit.audio`), takže se dá
poslechnout, co se vlastně porovnává. Trasy se do gitu nedávají (jsou
v `build/`), vyrobí se z kazety kdykoli znovu.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

from traceentities import Original, STUB, STACK, SWEEPS, RAND       # noqa: E402
from skoolkit.simutils import PC, SP, T                            # noqa: E402

OUT = os.path.join(ROOT, 'build/sound-traces.json')
SOUNDS = os.path.join(ROOT, 'data/sounds.json')
MUSIC = os.path.join(ROOT, 'data/music.json')

RECORD = 0x9792                 # NastieData[0] – volný záznam entity na pokusy
STEP_COUNTER = 0x96B3           # počítadlo kroků, na kterém visí výška kroku
PORT = 0xFE                     # a port, na kterém je reproduktor

# T-stavy předehry stubu, aby se časy daly počítat od vstupu do rutiny
T_CALL = 17
T_LD_B_N = 7
T_LD_BC_NN = 10
T_LD_DE_NN = 10
T_LD_IX_NN = 14
T_LD_A_N = 7


class Speaker:
    """Odposlech portu: `OUT ($FE),A` s časem, a klávesnice, na které nikdo nedrží."""

    def __init__(self):
        self.log = []

    def write_port(self, registers, port, value, tstates):
        if port & 0xFF == PORT:
            self.log.append((registers[T]+tstates, value))

    def read_port(self, registers, port):
        # nic se nemačká: $FF po `CPL` a `AND $1F` dá nulu, takže
        # PlayAudio_WaitKey ($BD51) hraje dál
        return 0xFF


def record(original, speaker, prelude, prelude_t, routine):
    """Zavolá rutinu a vrátí, co poslala do reproduktoru, od svého vstupu."""
    stub = list(prelude)+[0xCD, routine & 0xFF, routine >> 8, 0x76]
    original.poke(STUB, stub)
    end = STUB+len(stub)-1
    original.sim.registers[SP] = STACK
    original.sim.registers[T] = 0
    speaker.log = []
    original.sim.run(STUB, end)
    if original.sim.registers[PC] != end:
        raise SystemExit('simulator skoncil na $%04X, cekam $%04X (rutina $%04X)'
                         % (original.sim.registers[PC], end, routine))
    entry = prelude_t+T_CALL
    deltas, values, last = [], [], entry
    for at, value in speaker.log:
        deltas.append(at-last)
        values.append(1 if value & 0x10 else 0)
        last = at
    return {'deltas': deltas, 'values': values,
            'tstates': original.sim.registers[T]-entry}


def pulses(trace):
    """Nahrávka jako délky pulzů: jak dlouho reproduktor zůstal, kde byl."""
    lengths, level, at, last = [], 0, 0, 0
    for delta, value in zip(trace['deltas'], trace['values']):
        at += delta
        if value == level:
            continue
        lengths.append(at-last)
        last = at
        level = value
    if trace['tstates'] > last:
        lengths.append(trace['tstates']-last)
    return lengths


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--case', action='append', help='nahrat jen tyhle pripady')
    ap.add_argument('--wav', help='ulozit nahravky i jako .wav do tohohle adresare')
    ap.add_argument('--print', action='store_true', dest='show')
    args = ap.parse_args()

    sounds = json.load(open(SOUNDS))
    music = json.load(open(MUSIC))
    tunes = music['tunes']

    original = Original()
    speaker = Speaker()
    original.sim.set_tracer(speaker)

    def call(routine, prelude=(), prelude_t=0):
        return record(original, speaker, prelude, prelude_t, routine)

    def ix(record_bytes):
        """Položí záznam entity do volné paměti a vrátí předehru `LD IX,nn`."""
        for offset, value in record_bytes.items():
            original.poke(RECORD+offset, [value])
        return [0xDD, 0x21, RECORD & 0xFF, RECORD >> 8], T_LD_IX_NN

    cases = {}

    def want(name):
        return not args.case or name in args.case

    # -- $BF74: celý rozsah výšky tónu --------------------------------------
    if want('squareWave'):
        runs = []
        for b in range(256):
            trace = call(0xBF74, [0x06, b], T_LD_B_N)      # LD B,n
            trace['b'] = b
            runs.append(trace)
        cases['squareWave'] = {'routine': '$BF74', 'runs': runs,
                               'note': 'vsech 256 hodnot B'}

    # -- $BF6D: mřížka B × C ------------------------------------------------
    if want('waveSequence'):
        runs = []
        for b in (0x01, 0x08, 0x20, 0x40, 0x80, 0xC0, 0xFF, 0x00):
            for c in (0x01, 0x02, 0x04, 0x08, 0x10, 0x30):
                trace = call(0xBF6D, [0x01, c, b], T_LD_BC_NN)   # LD BC,nn
                trace['b'], trace['c'] = b, c
                runs.append(trace)
        cases['waveSequence'] = {'routine': '$BF6D', 'runs': runs,
                                 'note': 'mrizka B x C'}

    # -- $BF4B: krok, všech 256 stavů počítadla, obě barvy -------------------
    if want('step'):
        runs = []
        for colour in (0x47, 0x45):
            for counter in range(256):
                original.poke(STEP_COUNTER, [counter])
                prelude, prelude_t = ix({0x05: colour})
                trace = call(0xBF4B, prelude, prelude_t)
                trace['counter'] = counter
                trace['colour'] = colour
                trace['counterAfter'] = original.peek(STEP_COUNTER)[0]
                runs.append(trace)
        cases['step'] = {'routine': '$BF4B', 'runs': runs,
                         'note': 'vsech 256 stavu $96B3 pro bilého i modrozeleného '
                                 'Sabremana – pod $45 rutina propadne do sebe podruhe'}

    # -- $A9F8: odlet po smrti ----------------------------------------------
    if want('fly'):
        runs = []
        for phase in range(256):
            prelude, prelude_t = ix({0x02: phase})
            trace = call(0xA9F8, prelude, prelude_t)
            trace['phase'] = phase
            runs.append(trace)
        cases['fly'] = {'routine': '$A9F8', 'runs': runs,
                        'note': 'vsech 256 fazi odletu'}

    # -- ploché tóny a rozmítání --------------------------------------------
    for name, routine, note in (('land', 0xBF2F, 'dopad na zem'),
                                ('repel', 0xBF17, 'zahnani mecem a strazce brany'),
                                ('object', 0xBF25, 'predmet a extra zivot'),
                                ('orchid', 0xBF2A, 'orchidej a klapnuti pismene'),
                                ('orchidEnd', 0xBEC6, 'dohasinajici orchidej')):
        if want(name):
            cases[name] = {'routine': '$%04X' % routine, 'runs': [call(routine)],
                           'note': note}

    # -- $BF08: zhmotnění pro všech 256 sprite ID ---------------------------
    if want('materialise'):
        runs = []
        for sprite in range(256):
            prelude, prelude_t = ix({0x00: sprite})
            trace = call(0xBF08, prelude, prelude_t)
            trace['sprite'] = sprite
            runs.append(trace)
        cases['materialise'] = {'routine': '$BF08', 'runs': runs,
                                'note': 'vsech 256 sprite ID'}

    # -- $BF3D: domorodec ukazující k amuletu -------------------------------
    if want('pointing'):
        runs = []
        for distance in (0x00, 0x01, 0x08, 0x10, 0x3F, 0x40, 0x80, 0xC0, 0xFF):
            for x in (0x00, 0x20, 0x7F, 0xE0):
                for y in (0x00, 0x30, 0x90, 0xF0):
                    prelude, prelude_t = ix({0x03: x, 0x04: y})
                    prelude = prelude+[0x3E, distance]      # LD A,n
                    trace = call(0xBF3D, prelude, prelude_t+T_LD_A_N)
                    trace['distance'], trace['x'], trace['y'] = distance, x, y
                    runs.append(trace)
        cases['pointing'] = {'routine': '$BF3D', 'runs': runs,
                             'note': 'mrizka vzdalenost x x x y'}

    # -- $BECC: ohnivá koule, všech 16 stavů počítadla ----------------------
    if want('fireball'):
        runs = []
        for sweeps in range(16):
            original.poke(SWEEPS, [sweeps])
            trace = call(0xBECC)
            trace['sweeps'] = sweeps
            runs.append(trace)
        cases['fireball'] = {'routine': '$BECC', 'runs': runs,
                             'note': 'vsech 16 stavu $9693'}

    # -- $BEEE: výbuch, jehož délky jsou bajty ROM --------------------------
    if want('explosion'):
        runs = []
        for sweeps in (0x00, 0x05, 0x1F, 0x20, 0x77, 0xFF):
            for rand in (0x00, 0x40, 0x9C, 0xF0, 0xFF):
                original.poke(SWEEPS, [sweeps])
                original.poke(RAND, [rand])
                trace = call(0xBEEE)
                base = (sweeps & 0x1F)*256+rand
                trace['sweeps'], trace['rand'] = sweeps, rand
                # ★ a s nahrávkou jdou i bajty, ze kterých rutina četla: ROM
                # v našich zdrojích není, takže bez nich by se to porovnat
                # nedalo (stejná díra jako mapa předmětů v M4)
                trace['rom'] = [original.memory[(base+i) & 0xFFFF]
                                for i in range(16)]
                runs.append(trace)
        cases['explosion'] = {'routine': '$BEEE', 'runs': runs,
                              'note': 'mrizka $9693 x Rand8; delky tonu jsou '
                                      'bajty ROM Spectra a nahravaji se s tim'}

    # -- hudba: čtyři skladby, nota po notě ---------------------------------
    if want('music'):
        runs = []
        for name in ('gameInitialisation', 'poem', 'gameOver', 'gameComplete'):
            addr = int(tunes[name]['address'][1:], 16)
            trace = call(0xBD6E, [0x11, addr & 0xFF, addr >> 8], T_LD_DE_NN)
            trace['tune'] = name
            runs.append(trace)
        cases['music'] = {'routine': '$BD6E', 'runs': runs,
                          'note': 'vsechny ctyri skladby cele'}

    if want('menu'):
        addr = int(tunes['gameComplete']['address'][1:], 16)
        trace = call(0xBD51, [0x11, addr & 0xFF, addr >> 8], T_LD_DE_NN)
        trace['tune'] = 'gameComplete'
        trace['waitKey'] = True
        cases['menu'] = {'routine': '$BD51', 'runs': [trace],
                         'note': 'gameComplete variantou hlavniho menu, ktera '
                                 'mezi notami cte klavesnici'}

    data = {
        'about': 'Co originál poslal do reproduktoru, nahrane v simulatoru '
                 '(tools/tracesound.py, M6). U kazdeho behu je seznam zapisu '
                 'na port $FE: `deltas` jsou rozestupy v T-stavech Z80 od '
                 'vstupu do rutiny a `values` hodnota bitu 4. '
                 'tools/matchsound.js proti tomu pousti app/beeper.js.',
        'clock': sounds['machine']['clock'],
        'port': PORT,
        'cases': cases,
    }
    with open(args.out, 'w') as out:
        json.dump(data, out, separators=(',', ':'))
        out.write('\n')

    total_runs = sum(len(case['runs']) for case in cases.values())
    total_writes = sum(len(run['deltas'])
                       for case in cases.values() for run in case['runs'])

    if args.wav:
        from skoolkit.audio import write_wav
        from skoolkit.audio import moving_average_filter
        os.makedirs(args.wav, exist_ok=True)
        rate = 44100
        for name, case in cases.items():
            lengths = []
            for run in case['runs']:
                lengths += pulses(run)
                lengths.append(rate and 3500000//5)      # pětina vteřiny ticha
            options = {'ClockSpeed': 3500000, 'SampleRate': rate}
            samples = moving_average_filter(lengths, options, 0.5)
            path = os.path.join(args.wav, name+'.wav')
            with open(path, 'wb') as wav:
                write_wav(wav, samples, rate)
            print('%s: %.1f s' % (os.path.relpath(path), len(samples)/rate))

    if args.show:
        for name, case in sorted(cases.items()):
            run = case['runs'][0]
            print('%-12s %-6s %4d behu, prvni: %5d zapisu, %9d T (%.3f s)'
                  % (name, case['routine'], len(case['runs']),
                     len(run['deltas']), run['tstates'], run['tstates']/3500000))

    print('%s: %d pripadu, %d behu, %d zapisu do reproduktoru'
          % (os.path.relpath(args.out), len(cases), total_runs, total_writes))


if __name__ == '__main__':
    main()
