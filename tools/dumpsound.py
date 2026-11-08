#!/usr/bin/env python3
"""Vytáhne z originálu **zvukové efekty**: rutiny beeperu a jejich konstanty → `data/sounds.json` (M6).

    PYTHONPATH=tools/vendor ./tools/dumpsound.py [--print]

Stejné pravidlo jako u `dumpmonsters.py`: **nic tady není odhad**. Každá hodnota
se čte jako **operand skutečné instrukce** v runtime obrazu hry
(`build/sabrewulf-run.bin`, `tools/mkruntime.py`) a okolní bajty té instrukce se
kontrolují. Když se obraz neshoduje, nástroj spadne, místo aby vydal číslo.

Zvuk Sabre Wulf stojí na **dvou rutinách a ničem jiném**:

* `PlaySquareWave` (`$BF74`) – jeden obdélníkový kmit: zapni reproduktor
  (bit 4 portu `$FE`), `DJNZ` `B`krát, vypni, `DJNZ` `B`krát. **Výška tónu je
  `B`**, nic víc.
* `PlayWaveSequence` (`$BF6D`) – `C` takových kmitů za sebou. **Délka je `C`.**

Každý efekt hry je tedy dvojice `(B, C)`, případně smyčka, která `B` mění.
★ **Není tu žádná obálka, žádný šum a žádná tabulka vzorků** – deset efektů,
každý pár instrukcí, a to je celý zvuk hry. Proto se dá reprodukovat přesně:
`app/beeper.js` počítá tytéž délky v T-stavech Z80 a `tools/tracesound.py`
+ `tools/matchsound.js` to porovnají **pulz po pulzu** proti originálu.

Rutiny, ze kterých se čte (runtime adresy, `sources/docs/disasm_notes.md` §18):

| efekt | rutina | čím se liší |
|---|---|---|
| `step` | `$BF4B` | ★ počítadlo `$96B3`: pípne **každý osmý krok**, střídavě `$40`/`$60`, a **pod modrozelenou orchidejí dvakrát** (`IX+$05 == $45`) |
| `fly` | `$A9F8` | `B` je fáze odletu (`IX+$02`), takže **tón s odletem stoupá** |
| `land` | `$BF2F` | rozmítání `(C XOR $55) + C` pro `C` = `$30`…`1` |
| `repel`, `keeper` | `$BF17` | rozmítání `DAA(C OR $18)` – ★ zvuk zahnání dělá **desítková korekce**, ne tabulka |
| `object`, `life` | `$BF25` | `B`=`$40`, `C`=`$30` |
| `orchid` | `$BF2A` | `B`=`$80`, `C`=`$10` – týmž zvukem hra **klapne písmenem** v síni slávy (`$B72C`) |
| `orchidEnd` | `$BEC6` | ★ rutina **schovaná uvnitř tabulky not** (`MusicData` + 61×4) – proto ji disassembly nepojmenovala |
| `explosion` | `$BEEE` | ★ 16 tónů, jejichž délky jsou **bajty ROM** na `($9693 & $1F)*256 + Rand8` |
| `materialise` | `$BF08` | `B` z **negovaného sprite ID**, takže každý druh zvířete zní jinak |
| `pointing` | `$BF3D` | ★ `B` je **vzdálenost k zakopanému kusu amuletu** (M4, `$9D41`) |
| `fireball` | `$BECC` | `B` z osmiprvkové tabulky `$BEDE` podle `$9693 & $0F` |

★ **Sebrání kusu amuletu žádný zvuk nemá** (`$A1AB` jen přičte body a nastaví
bit básně) – co se u něj slyší, je **hudba básně** (`dumpmusic.py`).

`--print` k tomu vypíše souhrn na terminál.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

IMAGE = os.path.join(HERE, '..', 'build/sabrewulf-run.bin')
OUT = os.path.join(HERE, '..', 'data/sounds.json')

# ---------------------------------------------------------------------------
# Konstanty: (jméno, adresa, bajty instrukce s None na místě operandu, komentář)
# None se přečte, ostatní bajty se ověří. Dvě None = dvoubajtový operand.
# ---------------------------------------------------------------------------
CONSTANTS = [
    # --- PlaySquareWave ($BF74) a PlayWaveSequence ($BF6D) ------------------
    ('speakerOn',        0xBF74, [0x3E, None, 0xD3, 0xFE],
     'LD A,n / OUT ($FE),A — ★ **celý zvuk hry je tenhle jeden bit**: `$10` je '
     'bit 4 portu `$FE`, reproduktor nahoru (`PlaySquareWave`, `$BF74`)'),
    ('speakerPort',      0xBF76, [0xD3, None],
     'OUT (n),A — a port, na který se to píše'),
    ('speakerOff',       0xBF7C, [0xAF, 0xD3, 0xFE, 0x78],
     'XOR A / OUT ($FE),A — dolů se jde nulou, takže **border se u zvuku '
     'srazí na černou** (to je vidět i v hudbě, $BDA1)'),
    ('squareWaveLoop',   0xBF79, [0x10, None],
     'DJNZ n — a mezi tím se jen čeká `B`krát; **výška tónu není nic než `B`**'),
    ('waveSequenceLoop', 0xBF6D, [0xCD, 0x74, 0xBF, 0x0D, 0x20, 0xFA, 0xC9],
     '`PlayWaveSequence` ($BF6D): `C` kmitů za sebou a konec — **délka tónu '
     'není nic než `C`**'),

    # --- $BEC6: rutina schovaná uvnitř tabulky not -------------------------
    ('orchidEndWave',    0xBEC6, [0x01, None, None, 0xC3, 0x6D, 0xBF],
     'LD BC,nn / JP $BF6D — ★ **pípání dohasínající orchideje** ($AF91/$AFA6). '
     'Leží **uvnitř** `MusicData` ($BDD2), za 61. položkou tabulky not — proto '
     'ji veřejná disassembly vede jako data a nepojmenovala ji'),

    # --- $BF25 / $BF2A: dva ploché tóny ------------------------------------
    ('objectWave',       0xBF25, [0x01, None, None, 0x18, 0x43],
     'LD BC,nn / JR $BF6D — sebraný předmět i **extra život** ($A323), a týmž '
     'zvukem se posouvá kurzor v síni slávy ($B74E)'),
    ('orchidWave',       0xBF2A, [0x01, None, None, 0x18, 0x3E],
     'LD BC,nn / JR $BF6D — sebraná orchidej ($A759/$A760); týmž zvukem hra '
     '**klapne písmenem**, když se zapisuje jméno do síně slávy ($B72C)'),

    # --- $BECC: ohnivá koule -----------------------------------------------
    ('fireballTable',    0xBECC, [0x01, None, None, 0x3A, 0x93, 0x96],
     'LD BC,nn — tabulka délek kmitu ohnivé koule ($BEDE)'),
    ('fireballSweeps',   0xBECF, [0x3A, None, None, 0xE6],
     'LD A,(nn) — a vybírá se z ní počítadlem průchodů smyčkou entit ($9693, M4)'),
    ('fireballMask',     0xBED2, [0xE6, None],
     'AND n — …po jeho spodních čtyřech bitech, takže tabulka má šestnáct položek'),
    ('fireballRepeats',  0xBED9, [0x0E, None, 0xC3, 0x6D, 0xBF],
     'LD C,n / JP $BF6D — a tolik kmitů se z toho zahraje'),

    # --- $BEEE: výbuch, jehož délky jsou bajty ROM -------------------------
    ('explosionRand',    0xBEEE, [0x3A, None, None, 0x6F],
     'LD A,(nn) / LD L,A — ★ **výbuch se čte z paměti**: spodní bajt adresy je '
     '`Rand8` ($9695)…'),
    ('explosionSweeps',  0xBEF2, [0x3A, None, None, 0xE6],
     'LD A,(nn) — …a horní bajt počítadlo průchodů ($9693)…'),
    ('explosionMask',    0xBEF5, [0xE6, None],
     'AND n — …oříznuté na n, tedy adresa `$0000`-`$1FFF`: **je to ROM '
     'Spectra**, stejná studna náhody jako mapa předmětů v M4 ($A2BD)'),
    ('explosionTones',   0xBEF8, [0x1E, None],
     'LD E,n — kolik tónů za sebou (šestnáct po sobě jdoucích bajtů)'),
    ('explosionByteMask', 0xBEFC, [0xE6, None],
     'AND n — z každého bajtu se bere n, tedy sedm bitů → délka kmitu'),
    ('explosionRepeats', 0xBEFF, [0x0E, None, 0xCD, 0x6D, 0xBF],
     'LD C,n / CALL $BF6D — a každý tón je jen tak krátký'),

    # --- $BF08: zhmotnění, tón podle druhu zvířete -------------------------
    ('materialiseOffset', 0xBF08, [0xDD, 0x7E, None, 0x2F],
     'LD A,(IX+n) / CPL — ★ tón zhmotnění dělá **negované sprite ID**, takže '
     'každý druh zvířete se ozve jinak'),
    ('materialiseRotate', 0xBF0C, [0x0F, 0x0F, 0x0F, 0xE6],
     'RRCA x3 — o tři bity doprava…'),
    ('materialiseMask',  0xBF0F, [0xE6, None],
     'AND n — …a nechají se horní tři bity, takže `B` je násobek `$20`'),
    ('materialiseRepeats', 0xBF12, [0x0E, None, 0xC3, 0x6D, 0xBF],
     'LD C,n / JP $BF6D — tolik kmitů'),

    # --- $BF17: zahnání mečem (a strážce brány) ----------------------------
    ('repelStart',       0xBF17, [0x0E, None, 0x79, 0xF6],
     'LD C,n — zahnání je **rozmítání**: `C` jde od n dolů k jedné a je '
     'zároveň počítadlo i zdroj výšky'),
    ('repelOrMask',      0xBF1A, [0xF6, None, 0x27, 0x47],
     'OR n / DAA — ★ a výška je `DAA(C OR n)`: **desítková korekce Z80** '
     'v roli zvukového generátoru'),

    # --- $BF2F: dopad Sabremana po smrti -----------------------------------
    ('landStart',        0xBF2F, [0x0E, None, 0x79, 0xEE],
     'LD C,n — dopad je totéž rozmítání, jen jinou aritmetikou'),
    ('landXorMask',      0xBF32, [0xEE, None, 0x81, 0x47],
     'XOR n / ADD A,C — výška je `(C XOR n) + C`'),

    # --- $A9F8: odlet po smrti ---------------------------------------------
    ('flyOffset',        0xA9F8, [0xDD, 0x46, None],
     'LD B,(IX+n) — ★ **tón odletu je fáze odletu**: `+$02` záznamu roste '
     'každý průchod, takže tón klesá, jak Sabreman letí'),
    ('flyRepeats',       0xA9FB, [0x0E, None, 0xC3, 0x6D, 0xBF],
     'LD C,n / JP $BF6D — a je krátký, protože se hraje každý průchod'),

    # --- $BF3D: domorodec ukazující k amuletu ------------------------------
    ('pointingXOffset',  0xBF3D, [0xDD, 0x86, None],
     'ADD A,(IX+n) — ★ **tón domorodce je vzdálenost k zakopanému kusu '
     'amuletu**: `$9D41` (M4) vrátí rozdíl v `A`…'),
    ('pointingYOffset',  0xBF40, [0xDD, 0x86, None],
     'ADD A,(IX+n) — …a připočte se x i y domorodce'),
    ('pointingRotate',   0xBF43, [0x07, 0x07, 0x47],
     'RLCA x2 / LD B,A — pak dvakrát doleva, takže **čím blíž, tím výš**'),
    ('pointingRepeats',  0xBF46, [0x0E, None, 0xC3, 0x6D, 0xBF],
     'LD C,n / JP $BF6D — a krátce, jednou za průchod, proto to cvrliká'),

    # --- $BF4B: krok ------------------------------------------------------
    ('stepColourOffset', 0xBF4E, [0xDD, 0x7E, None, 0xFE],
     'LD A,(IX+n) — barva Sabremana, tedy **jeho orchidej** (M4)'),
    ('stepColourFast',   0xBF51, [0xFE, None, 0xC0],
     'CP n / RET NZ — ★ a když je `$45` (modrozelená, 4 px za krok), rutina '
     '**propadne do sebe podruhé**: pod tou orchidejí kroky duní dvakrát tak '
     'často'),
    ('stepCounter',      0xBF54, [0x21, None, None, 0x34],
     'LD HL,nn / INC (HL) — počítadlo kroků ($96B3)'),
    ('stepCounterBit',   0xBF59, [0xCB, None],
     'BIT b,A — …jehož bit rozhoduje o výšce…'),
    ('stepMask',         0xBF5D, [0xE6, None],
     'AND n / RET NZ — …a spodní tři bity o tom, že se pípne **jen každý osmý '
     'krok**'),
    ('stepWaveHigh',     0xBF60, [0x01, None, None, 0x18, 0x08],
     'LD BC,nn — krok s nastaveným bitem 3'),
    ('stepWaveLow',      0xBF68, [0x01, None, None, 0x18, 0x00],
     'LD BC,nn — a bez něj; ★ chůze je tedy **osmikrokový vzor dvou tónů**'),
]

# Který zvuk hraje kdy: jméno, které posílá worker (WORKER-PROTOCOL.md), rutina
# a místo, ze kterého se volá. Nic z toho není odhad – volání jsou v obraze.
EVENTS = [
    ('step',        0xBF4B, 0xAF52,
     'krok Sabremana ($AF52 s mečem $AE2E, obojí `CALL NZ` – tedy jen když '
     'se opravdu pohnul)'),
    ('fly',         0xBF6D, 0xA9FD,
     'odlet po smrti ($A9FD), `B` je fáze odletu'),
    ('land',        0xBF2F, 0xAA0A,
     'dopad na zem ($AA0A)'),
    ('orchid',      0xBF2A, 0xA760,
     'sebraná orchidej ($A759 barevná, $A760 bílá)'),
    ('orchidEnd',   0xBEC6, 0xAF91,
     'dohasínající orchidej: posledních $2F půlsnímků bliká a pípá '
     '($AF91/$AFA6, `CALL Z`)'),
    ('object',      0xBF25, 0xA338,
     'sebraný předmět nebo extra život ($A338)'),
    ('life',        0xBF25, 0xA338,
     'a je to týž zvuk – extra život jde přes tutéž cestu ($A305 → $A323)'),
    ('explosion',   0xBEEE, 0xA4A6,
     'výbuch zvířete ($A4A6)'),
    ('materialise', 0xBF08, 0xA3DA,
     'zhmotňující se zvíře ($A3DA)'),
    ('repel',       0xBF17, 0x9EFE,
     'zahnání mečem: hroch ($9EFE), nosorožec ($AD79), domorodec ($ABB3), '
     'Sabre Wulf'),
    ('keeper',      0xBF17, 0x9F3A,
     'a strážce brány ($9F3A) – týž zvuk'),
    ('pointing',    0xBF3D, 0xABC7,
     'domorodec ukazující k amuletu ($ABC7)'),
    ('fireball',    0xBECC, 0x9E01,
     'ohnivá koule ($9E01)'),
]

# ...a co zvuk nemá, i když by ho člověk čekal
SILENT = [
    ('amulet', 0xA1AB,
     '★ **sebrání kusu amuletu je němé**: `$A1AB` jen přičte 7500 bodů a '
     'nastaví bit básně. Co se u něj slyší, je hudba básně (dumpmusic.py)'),
]


def load(path=IMAGE):
    ram = open(path, 'rb').read()
    if len(ram) != 49152:
        raise SystemExit('cekam 49152 B RAM ($4000-$FFFF), mam %d' % len(ram))
    if ram[0x6000-0x4000:0x6005-0x4000] != bytes((0xF3, 0x31, 0x00, 0x60, 0xC3)):
        raise SystemExit('%s neni runtime obraz – spust tools/mkruntime.py' % path)
    return ram


def peek(ram, addr, count=1):
    return ram[addr-0x4000:addr-0x4000+count]


def extract(ram, name, addr, pattern, note):
    """Ověří instrukci na `addr` a vrátí přečtené operandy."""
    got = peek(ram, addr, len(pattern))
    operands = []
    for i, expected in enumerate(pattern):
        if expected is None:
            operands.append(got[i])
        elif got[i] != expected:
            raise SystemExit('%s: $%04X+%d ceka %02X, v obrazu je %02X (%s)'
                             % (name, addr, i, expected, got[i], note))
    if not operands:
        return None
    if len(operands) == 2:
        return operands[0] | operands[1] << 8
    if len(operands) == 1:
        return operands[0]
    return list(operands)


def check(condition, message):
    if not condition:
        raise SystemExit(message)


def daa(value):
    """`DAA` po `OR n` – tedy s N=0, H=0 a C=0 (OR nuluje přenos i půlpřenos)."""
    result = value
    if (result & 0x0F) > 9:
        result += 0x06
    if result > 0x9F:
        result += 0x60
    return result & 0xFF


def rotate_left(value, times):
    for _ in range(times):
        value = ((value << 1) | (value >> 7)) & 0xFF
    return value


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--image', default=IMAGE)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--print', action='store_true', dest='show',
                    help='vypsat souhrn na terminál')
    args = ap.parse_args()

    ram = load(args.image)
    values, notes = {}, {}
    checked = 0
    for name, addr, pattern, note in CONSTANTS:
        value = extract(ram, name, addr, pattern, note)
        checked += 1
        if value is None:
            continue
        values[name] = value
        notes[name] = {'address': '$%04X' % addr, 'note': note}

    # `BIT b,A` nese číslo bitu v opkódu – uložit se má bit, ne opkód
    values['stepCounterBit'] = (values['stepCounterBit'] >> 3) & 0x07
    checked += 1

    # `LD BC,nn` je v paměti nízký bajt první, takže operand $A008 znamená
    # B=$A0 (délka kmitu) a C=$08 (počet kmitů). Rozložit to tady, ať replika
    # nemusí vědět, jak Z80 ukládá slovo.
    waves = {}
    for name in ('orchidEndWave', 'objectWave', 'orchidWave',
                 'stepWaveHigh', 'stepWaveLow'):
        word = values.pop(name)
        waves[name] = {'b': word >> 8, 'c': word & 0xFF}
        notes[name]['value'] = 'B=$%02X, C=$%02X' % (word >> 8, word & 0xFF)
    checked += len(waves)

    # -- tabulka délek kmitu ohnivé koule ($BEDE) ---------------------------
    table = values['fireballTable']
    size = values['fireballMask']+1
    fireball = list(peek(ram, table, size))
    check(peek(ram, table+size, 3) == bytes((0x3A, 0x95, 0x96)),
          'tabulka koule ($%04X) nekonci na rutine vybuchu $BEEE' % table)
    checked += 1
    check(table == 0xBEDE, 'tabulka koule ma byt na $BEDE, je na $%04X' % table)
    checked += 1

    # ★ Kontrola, že $BEC6 opravdu leží uvnitř tabulky not: `MusicData` začíná
    # na $BDD2 a položka je čtyřbajtová, takže $BEC6 je položka 61.
    check((0xBEC6-0xBDD2) % 4 == 0,
          '$BEC6 nelezi na hranici polozky tabulky not')
    checked += 1

    # -- efekty ------------------------------------------------------------
    effects = [
        {'name': 'squareWave', 'routine': '$BF74', 'kind': 'primitive',
         'note': 'jeden kmit: reproduktor nahoru, `DJNZ B`, dolu, `DJNZ B`. '
                 'Vyska tonu je B a nic jineho.'},
        {'name': 'waveSequence', 'routine': '$BF6D', 'kind': 'primitive',
         'note': 'C kmitu za sebou. Delka tonu je C a nic jineho.'},
        {'name': 'step', 'routine': '$BF4B', 'kind': 'step',
         'counter': values['stepCounter'], 'bit': values['stepCounterBit'],
         'mask': values['stepMask'],
         'high': waves['stepWaveHigh'], 'low': waves['stepWaveLow'],
         'colourOffset': values['stepColourOffset'],
         'colourFast': values['stepColourFast'],
         'note': 'pipne kazdy osmy krok, vyska podle bitu %d pocitadla $%04X; '
                 'pod modrozelenou orchideji ($%02X) dvakrat'
                 % (values['stepCounterBit'], values['stepCounter'],
                    values['stepColourFast'])},
        {'name': 'fly', 'routine': '$A9F8', 'kind': 'wavePhase',
         'offset': values['flyOffset'], 'c': values['flyRepeats'],
         'note': 'B je faze odletu (+$%02X zaznamu), takze tón s odletem klesa'
                 % values['flyOffset']},
        {'name': 'land', 'routine': '$BF2F', 'kind': 'sweepXor',
         'start': values['landStart'], 'xor': values['landXorMask'],
         'note': 'C od $%02X k jedne, B = (C XOR $%02X) + C'
                 % (values['landStart'], values['landXorMask'])},
        {'name': 'repel', 'routine': '$BF17', 'kind': 'sweepDaa',
         'start': values['repelStart'], 'or': values['repelOrMask'],
         'note': 'C od $%02X k jedne, B = DAA(C OR $%02X)'
                 % (values['repelStart'], values['repelOrMask'])},
        {'name': 'object', 'routine': '$BF25', 'kind': 'wave',
         'b': waves['objectWave']['b'], 'c': waves['objectWave']['c'],
         'note': 'sebrany predmet, extra zivot a posun kurzoru v sini slavy'},
        {'name': 'orchid', 'routine': '$BF2A', 'kind': 'wave',
         'b': waves['orchidWave']['b'], 'c': waves['orchidWave']['c'],
         'note': 'sebrana orchidej a klapnuti pismene v sini slavy'},
        {'name': 'orchidEnd', 'routine': '$BEC6', 'kind': 'wave',
         'b': waves['orchidEndWave']['b'], 'c': waves['orchidEndWave']['c'],
         'note': 'rutina schovana uvnitr tabulky not (polozka %d)'
                 % ((0xBEC6-0xBDD2)//4)},
        {'name': 'explosion', 'routine': '$BEEE', 'kind': 'memoryTones',
         'tones': values['explosionTones'], 'byteMask': values['explosionByteMask'],
         'c': values['explosionRepeats'],
         'randAddress': values['explosionRand'],
         'sweepsAddress': values['explosionSweeps'],
         'addressMask': values['explosionMask'],
         'note': '%d tonu, jejichz delky jsou bajty ROM na ($9693 & $%02X)*256 '
                 '+ Rand8 – stejna studna nahody jako mapa predmetu v M4'
                 % (values['explosionTones'], values['explosionMask'])},
        {'name': 'materialise', 'routine': '$BF08', 'kind': 'spriteTone',
         'offset': values['materialiseOffset'], 'rotate': 3,
         'mask': values['materialiseMask'], 'c': values['materialiseRepeats'],
         'note': 'B = ((~sprite ID) >>> 3) & $%02X, takze kazdy druh zvirete '
                 'zni jinak' % values['materialiseMask']},
        {'name': 'pointing', 'routine': '$BF3D', 'kind': 'distanceTone',
         'xOffset': values['pointingXOffset'], 'yOffset': values['pointingYOffset'],
         'rotate': 2, 'c': values['pointingRepeats'],
         'note': 'B = (vzdalenost + x + y) rotovane dvakrat doleva; cim bliz '
                 'ke kusu amuletu, tim vys'},
        {'name': 'fireball', 'routine': '$BECC', 'kind': 'tableTone',
         'table': fireball, 'mask': values['fireballMask'],
         'c': values['fireballRepeats'],
         'sweepsAddress': values['fireballSweeps'],
         'note': 'B = tabulka $%04X[$9693 & $%02X]'
                 % (table, values['fireballMask'])},
    ]

    events = []
    for name, routine, site, note in EVENTS:
        events.append({'event': name, 'routine': '$%04X' % routine,
                       'calledFrom': '$%04X' % site, 'note': note})
    silent = [{'event': name, 'routine': '$%04X' % addr, 'note': note}
              for name, addr, note in SILENT]

    data = {
        'about': 'Zvukove efekty Sabre Wulf, ctene z runtime obrazu originalu '
                 '(tools/dumpsound.py, M6). Cely zvuk hry stoji na dvou '
                 'rutinach: PlaySquareWave ($BF74) dela jeden obdelnikovy kmit '
                 'delky B a PlayWaveSequence ($BF6D) jich udela C. Kazdy efekt '
                 'je tedy dvojice (B, C) nebo smycka, ktera B meni. '
                 'app/beeper.js pocita tytez delky v T-stavech Z80, '
                 'tools/tracesound.py + tools/matchsound.js to porovnaji pulz '
                 'po pulzu proti originalu.',
        'machine': {
            'port': values['speakerPort'],
            'speakerOn': values['speakerOn'],
            'speakerOff': 0,
            'clock': 3500000,
            'note': 'bit 4 portu $%02X; dolu se jde nulou, takze zvuk srazi '
                    'border na cernou' % values['speakerPort'],
        },
        'effects': effects,
        'events': events,
        'silent': silent,
        'fireballDurations': fireball,
        'values': values,
        'source': notes,
    }

    with open(args.out, 'w') as out:
        json.dump(data, out, indent=1, sort_keys=False)
        out.write('\n')

    if args.show:
        print('reproduktor: bit $%02X portu $%02X, hodiny 3,5 MHz'
              % (values['speakerOn'], values['speakerPort']))
        print()
        print('efekty:')
        for effect in effects:
            print('  %-12s %-6s %-12s %s'
                  % (effect['name'], effect['routine'], effect['kind'],
                     effect['note']))
        print()
        print('rozmitani zahnani ($BF17), prvnich osm delek kmitu:')
        print('  ' + ' '.join('$%02X' % daa(c | values['repelOrMask'])
                              for c in range(values['repelStart'],
                                             values['repelStart']-8, -1)))
        print('rozmitani dopadu ($BF2F), prvnich osm:')
        print('  ' + ' '.join('$%02X' % (((c ^ values['landXorMask'])+c) & 0xFF)
                              for c in range(values['landStart'],
                                             values['landStart']-8, -1)))
        print('tabulka koule ($%04X): %s'
              % (table, ' '.join('$%02X' % b for b in fireball)))
        print()
        print('kdy co hraje:')
        for event in events:
            print('  %-12s %-6s %s' % (event['event'], event['routine'],
                                       event['note']))
        for entry in silent:
            print('  %-12s %-6s %s' % (entry['event'], entry['routine'],
                                       entry['note']))

    print('%s: %d hodnot, %d efektu, %d kontrol'
          % (os.path.relpath(args.out), len(values), len(effects), checked))


if __name__ == '__main__':
    main()
