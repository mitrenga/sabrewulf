#!/usr/bin/env python3
"""Vytáhne z originálu **hudbu**: tabulku not a čtyři skladby → `data/music.json` (M6).

    PYTHONPATH=tools/vendor ./tools/dumpmusic.py [--print] [--abc]

★ **A tohle je ten rozdíl proti Underwurlde**: Sabre Wulf hudbu má. Underwurlde
neměl žádnou, takže tam posuvník `MUSIC` neměl co ovládat; tady jsou čtyři
skladby a přehrávač, který je hraje na tomtéž jednom bitu jako pípání.

Stejné pravidlo jako u ostatních `dump*`: hodnoty se čtou jako **operandy
skutečných instrukcí** v runtime obrazu (`build/sabrewulf-run.bin`) a okolní
bajty se kontrolují.

Jak je hudba uložená (`PlayAudio` `$BD6E`, `PlayAudio_Process` `$BD7B`):

* skladba je **posloupnost bajtů zakončená `$FF`**, jeden bajt = jedna nota
* **bity 0-5 jsou nota** (index do tabulky `MusicData` na `$BDD2`), **bity 6-7
  délka** (`RLCA` dvakrát, `AND 3`, `INC A` → násobek 1-4)
* **nota 0 je pomlka** (`$BDBC`): odpočet `$430B` provedený 1-4krát
* položka tabulky je čtyřbajtová: `B`, `C` (dvojice, ze které vyjde půlperioda
  zpožďovací smyčky) a **16bitová délka noty v kmitech**

★ **Tabulka not je rovnoměrně temperovaná chromatická stupnice**: sousední
položky se liší přesně o půltón (poměr period 1,0595), nejnižší je kolem
G#1 a nejvyšší kolem G#6. Nástroj to spočítá a **zkontroluje** – kdyby to
neplatilo, spadne, protože pak by se četla špatná data.

★ **Tabulka má 61 položek, ne 64**, jak by z masky `AND $3F` plynulo: za
položkou 60 leží **rutina** `$BEC6` (pípání dohasínající orchideje, viz
`dumpsound.py`). Tím je konec tabulky nezávisle ověřený.

Skladby (`$BC67`, `$BD28`, `$BD33`, `$BD45`) a kde se hrají:

| skladba | kde |
|---|---|
| `gameComplete` | ★ **a taky pod hlavním menu** (`$B3EC` → `PlayAudio_WaitKey`), takže Bach je první, co je z hry slyšet |
| `gameInitialisation` | začátek kola (`$99A1`) |
| `poem` | sloka básně za každý kus amuletu (`$A23A`) |
| `gameOver` | konec hry (`$AA8A`) |

`--print` vypíše souhrn, `--abc` k tomu noty ve stupnici, aby se dalo poznat,
co to hraje (ZXDB uvádí J. S. Bach, Preludium a fuga C dur, BWV 846).
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

IMAGE = os.path.join(HERE, '..', 'build/sabrewulf-run.bin')
OUT = os.path.join(HERE, '..', 'data/music.json')

CLOCK = 3500000                 # Z80 v ZX Spectru, hw_notes.md

CONSTANTS = [
    ('noteTable',      0xBD84, [0x01, None, None, 0x09],
     'LD BC,nn / ADD HL,BC — `MusicData` ($BDD2): tabulka not, čtyři bajty na '
     'položku'),
    ('noteMask',       0xBD7B, [0xE6, None, 0x28],
     'AND n — z bajtu skladby je nota jeho spodních šest bitů…'),
    ('lengthShift',    0xBD91, [0x07, 0x07, 0xE6, 0x03, 0x3C],
     'RLCA x2 / AND 3 / INC A — …a délka jeho horní dva bity, jako násobek 1-4'),
    ('terminator',     0xBD70, [0xFE, None, 0x28],
     'CP n — skladba končí tímhle bajtem'),
    ('restDelay',      0xBDC4, [0x01, None, None],
     'LD BC,nn — pomlka je odpočet od téhle hodnoty ($BDBC)'),
    ('borderDuringMusic', 0xBDA1, [0xAF, 0xD3, 0xFE],
     'XOR A / OUT ($FE),A — ★ hudba **sráží border na černou** každou '
     'půlperiodou; border je jinak celou hru černý, takže to není vidět'),
    ('speakerOn',      0xBDAB, [0x3E, None, 0xD3, 0xFE],
     'LD A,n / OUT ($FE),A — a nahoru jde týmž bitem 4 jako pípání'),
]

# Skladby: (jméno, adresa, kde se hraje)
TUNES = [
    ('gameComplete', 0xBC67, '$9F7E (GameComplete) a ★ $B3EC (hlavní menu, '
                             'přes PlayAudio_WaitKey – dá se přerušit klávesou)'),
    ('gameOver', 0xBD28, '$AA8A (GAME OVER)'),
    ('poem', 0xBD33, '$A23A (HandlerPoems – sloka za každý kus amuletu)'),
    ('gameInitialisation', 0xBD45, '$99A1 (začátek kola)'),
]

NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


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
    return operands[0]


def check(condition, message):
    if not condition:
        raise SystemExit(message)


def djnz(count):
    """`DJNZ sem` – `count` průchodů; `B`=0 znamená 256. 13 T na kolo, 8 na konec."""
    n = count or 256
    return 13*(n-1)+8


def delay(b, c):
    """Zpožďovací smyčka `$BDA4`/`$BDAF`: `DJNZ` uvnitř, `DEC C` / `JR NZ` venku.

    Po prvním průchodu je `B` nulové, takže každý další je plných 256 kol –
    proto je z dvojice `(B, C)` lineární míra `B + 256*(C-1)`, ne součin.
    """
    passes = c or 256
    total = djnz(b)+4
    for _ in range(passes-1):
        total += 12+djnz(0)+4
    return total+7


# Jedno kolo smyčky `$BDA0`: PUSH/XOR/OUT … POP/PUSH/LD/OUT … POP/DEC HL/LD/OR/JR
CYCLE_OVERHEAD = 11+4+11 + 10+11+7+11 + 10+6+4+4+12


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--image', default=IMAGE)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--print', action='store_true', dest='show')
    ap.add_argument('--abc', action='store_true',
                    help='vypsat skladby jako noty')
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

    table = values['noteTable']
    check(table == 0xBDD2, 'tabulka not ma byt na $BDD2, je na $%04X' % table)
    checked += 1

    # ★ Konec tabulky: za poslední položkou leží rutina $BEC6 (`LD BC,$A008` /
    # `JP $BF6D`). To je nezávislá kontrola, kolik položek tabulka doopravdy má.
    check(peek(ram, 0xBEC6, 6) == bytes((0x01, 0x08, 0xA0, 0xC3, 0x6D, 0xBF)),
          'za tabulkou not nelezi rutina $BEC6 – tabulka konci jinde')
    checked += 1
    count = (0xBEC6-table)//4
    check(count == 61, 'tabulka not ma mit 61 polozek, spocital jsem %d' % count)
    checked += 1

    table_notes = []
    for index in range(count):
        b, c = peek(ram, table+index*4, 2)
        length = peek(ram, table+index*4+2)[0] | peek(ram, table+index*4+3)[0] << 8
        entry = {'index': index, 'b': b, 'c': c, 'cycles': length}
        if index:
            half = delay(b, c)
            period = 2*half+CYCLE_OVERHEAD
            freq = CLOCK/period
            entry['halfPeriodTStates'] = half
            entry['periodTStates'] = period
            entry['frequency'] = round(freq, 3)
            entry['durationTStates'] = length*period
            entry['duration'] = round(length*period/CLOCK, 4)
            semitone = 12*__import__('math').log2(freq/440.0)
            nearest = round(semitone)
            entry['note'] = '%s%d' % (NAMES[(nearest+9) % 12],
                                      4+(nearest+9)//12)
            entry['cents'] = round((semitone-nearest)*100, 1)
        table_notes.append(entry)

    # ★ Kontrola, že je to opravdu chromatická stupnice: každá další položka
    # musí být o půltón výš, s tolerancí dvaceti centů: zpožďovací smyčka umí
    # jen celá kola, takže nahoře v tabulce, kde jich na půlperiodu zbývá pár
    # desítek, se přesně netrefí (nejhorší dvojice je 85 centů, položka 58).
    # Co se nevejde, se vypíše – a musí to být přesně to jedno místo, o kterém
    # víme, jinak nástroj spadne.
    worst, anomalies = 0.0, []
    for index in range(2, count):
        ratio = table_notes[index-1]['periodTStates']/table_notes[index]['periodTStates']
        cents = 1200*__import__('math').log2(ratio)
        if abs(cents-100) >= 20:
            anomalies.append({'index': index, 'cents': round(cents, 1)})
            continue
        worst = max(worst, abs(cents-100))
    checked += count-2

    # ★ A je tam jedno: položka 18 je **bajt po bajtu kopie položky 17**
    # (`$F3,$04`), takže v chromatické řadě jeden půltón chybí. Řada od
    # položky 19 dál pokračuje, jako by ta chybějící správně byla, takže to
    # není posun celé stupnice, ale jediná vadná příčka žebříku. Žádná ze
    # čtyř skladeb tu notu nepoužívá – proto si toho asi nikdo nevšiml.
    check([a['index'] for a in anomalies] == [18, 19]
          and anomalies[0]['cents'] == 0.0
          and abs(anomalies[1]['cents']-200) < 20,
          'v tabulce not je jina odchylka, nez ta znama na polozce 18: %s'
          % anomalies)
    check(peek(ram, table+17*4, 2) == peek(ram, table+18*4, 2),
          'polozka 18 uz neni kopii polozky 17 – ctu spatna data')
    checked += 2
    ratio = (table_notes[19]['periodTStates']/table_notes[17]['periodTStates'])
    gap = 1200*__import__('math').log2(1/ratio)
    check(abs(gap-200) < 20,
          'polozka 19 nema byt dva pultony nad 17, je %.1f centu' % gap)
    checked += 1

    # -- čtyři skladby -----------------------------------------------------
    tunes, printed = {}, {}
    for name, addr, where in TUNES:
        data, at = [], addr
        while True:
            byte = peek(ram, at)[0]
            at += 1
            if byte == values['terminator']:
                break
            data.append(byte)
            check(len(data) < 512, 'skladba %s nema terminator' % name)
        played = []
        total = 0
        for byte in data:
            index = byte & values['noteMask']
            multiple = ((byte >> 6) & 3)+1
            if index == 0:
                length = values['restDelay'] or 65536
                # $BDC7: PUSH BC / (DEC BC / LD A,B / OR C / JR NZ) / POP BC / DEC L / JR NZ
                span = multiple*(11+length*26+10+4+12)
                played.append({'byte': byte, 'rest': True, 'units': multiple,
                               'duration': round(span/CLOCK, 4)})
            else:
                check(index < count,
                      'skladba %s zada notu %d, tabulka jich ma %d'
                      % (name, index, count))
                entry = table_notes[index]
                span = entry['cycles']*multiple*entry['periodTStates']
                played.append({'byte': byte, 'note': index, 'units': multiple,
                               'name': entry['note'],
                               'frequency': entry['frequency'],
                               'duration': round(span/CLOCK, 4)})
            total += span
        # Rozepsané noty jsou hezké do konzole (`--abc`), ale do prohlížeče
        # nepatří: `app/beeper.js` si je spočítá z `bytes` a tabulky not, tak
        # jako to dělá originál. Soubor by s nimi byl třikrát větší.
        tunes[name] = {'address': '$%04X' % addr, 'bytes': data,
                       'count': len(data), 'playedAt': where,
                       'duration': round(total/CLOCK, 3)}
        printed[name] = played
        checked += 1

    data = {
        'about': 'Hudba Sabre Wulf, ctena z runtime obrazu originalu '
                 '(tools/dumpmusic.py, M6). Skladba je posloupnost bajtu '
                 'zakoncena $FF: bity 0-5 jsou nota (index do tabulky $BDD2), '
                 'bity 6-7 jeji delka (1-4). Nota 0 je pomlka. Tabulka ma 61 '
                 'polozek a je to rovnomerne temperovana chromaticka stupnice; '
                 'za posledni polozkou lezi rutina $BEC6, coz je kontrola jejiho '
                 'konce. Frekvence a delky jsou dopoctene z T-stavu zpozdovaci '
                 'smycky $BDA4/$BDAF; autorita je nahravka originalu '
                 '(tools/tracesound.py) a app/beeper.js se proti ni kontroluje '
                 'pulz po pulzu (tools/matchsound.js).',
        'player': {
            'routine': '$BD6E',
            'waitKeyRoutine': '$BD51',
            'processRoutine': '$BD7B',
            'noteMask': values['noteMask'],
            'terminator': values['terminator'],
            'restDelay': values['restDelay'],
            'note': 'PlayAudio ($BD6E) zakaze preruseni a hraje az do $FF; '
                    'PlayAudio_WaitKey ($BD51) je totez, ale hlida klavesnici '
                    '– to je varianta pod hlavnim menu.',
        },
        'scale': {
            'address': '$%04X' % table,
            'count': count,
            'endsAt': '$BEC6',
            'lowest': table_notes[1]['note'],
            'highest': table_notes[count-1]['note'],
            'worstSemitoneErrorCents': round(worst, 1),
            'note': 'rovnomerne temperovana chromaticka stupnice %s-%s; '
                    'nejvetsi odchylka sousednich pultonu je %.1f centu'
                    % (table_notes[1]['note'], table_notes[count-1]['note'], worst),
            'duplicate': {
                'index': 18, 'copyOf': 17,
                'usedByAnyTune': False,
                'note': 'polozka 18 je bajt po bajtu kopie polozky 17, takze '
                        'v chromaticke rade chybi jeden pulton. Rada od '
                        'polozky 19 dal pokracuje, jako by ta chybejici byla '
                        'spravne, takze to neni posun stupnice, ale jedina '
                        'vadna pricka. Zadna ze ctyr skladeb tu notu nehraje.',
            },
        },
        'notes': table_notes,
        'tunes': tunes,
        'values': values,
        'source': notes,
    }

    with open(args.out, 'w') as out:
        json.dump(data, out, indent=1, sort_keys=False)
        out.write('\n')

    if args.show:
        print('tabulka not $%04X: %d polozek, %s (%.1f Hz) az %s (%.1f Hz)'
              % (table, count, table_notes[1]['note'], table_notes[1]['frequency'],
                 table_notes[count-1]['note'], table_notes[count-1]['frequency']))
        print('  nejvetsi odchylka sousednich pultonu: %.1f centu' % worst)
        print('  konec tabulky drzi rutina $BEC6 (pipani orchideje)')
        print()
        for name, addr, where in TUNES:
            tune = tunes[name]
            print('%-20s $%04X  %3d not  %6.2f s   %s'
                  % (name, addr, tune['count'], tune['duration'], where))
        if args.abc:
            print()
            for name, addr, where in TUNES:
                print('%s:' % name)
                line = []
                for played in printed[name]:
                    line.append('%s%s' % ('-' if played.get('rest')
                                          else played['name'],
                                          '' if played['units'] == 1
                                          else '*%d' % played['units']))
                    if len(line) == 16:
                        print('  ' + ' '.join('%-6s' % x for x in line))
                        line = []
                if line:
                    print('  ' + ' '.join('%-6s' % x for x in line))
        print()
        print('%d zkontrolovanych instrukci, koncu tabulek a pultonu' % checked)

    print('%s: %d not v tabulce, %d skladeb, %d kontrol'
          % (os.path.relpath(args.out), count, len(tunes), checked))


if __name__ == '__main__':
    main()
