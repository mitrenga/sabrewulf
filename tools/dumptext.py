#!/usr/bin/env python3
"""Vytáhne z originálu **texty a obrazovku básně** → `data/text.json` (M6).

    PYTHONPATH=tools/vendor ./tools/dumptext.py [--print]

Stejné pravidlo jako u ostatních `dump*`: adresy i konstanty se čtou jako
**operandy skutečných instrukcí** v runtime obrazu a u každého bloku se
kontroluje, že **končí přesně tam, kde začíná něco jiného, co je nezávisle
pojmenované**. Nic se neopisuje z veřejné disassembly a nic se nepřepisuje
ručně.

Jak hra tiskne text (`PrintStringColour`, `$B53D`): záznam je
`x`, `y`, **atribut** a pak znaky, poslední s **nastaveným bitem 7**. Znaková
sada je ROM fontu ZX Spectra (M1, `disasm_notes.md` §8), takže se tady vytahují
jen bajty textu, ne písmena.

★ **Báseň se neukazuje po slokách, ale jednou slokou.** `DisplayPoem` (`$A01B`)
spočítá bity `+$0B` Sabremanova záznamu (kolik kusů amuletu hráč má) a skočí na
**tu jednu sloku, která tomu počtu odpovídá** – ne na všechny předchozí. Za
první kus je vidět sloka 1, za čtvrtý sloka 4 a nic jiného.

★ **A není to jen text.** `$A207` nejdřív smaže hrací plochu a nakreslí do ní
**obrázek amuletu**: čtyři kusy z tabulky `$C374`, každý svou grafikou, a
`$96B2` rozhoduje, jestli se kus vykreslí **posbíraný, nebo ne** – kreslicí
rutina `$BC0B` má u každého kusu **dva bloky atributů** a ten příznak vybírá
který. Teprve pak přijde sloka, hudba (`MusicData_Poem`) a prodleva na čtení.

Bloky, které se čtou:

| blok | adresa | co to je |
|---|---|---|
| `poem1`–`poem4` | `$A055`, `$A0A7`, `$A0F4`, `$A13B` | čtyři sloky po čtyřech řádcích |
| `gameComplete` | `$9F91` | šest řádků obrazovky po dohrání |
| `gameOver` | `$AAC1` | `GAME OVER PLAYER n` – ★ číslo hráče se **přepisuje v datech** (`$AA6C`) |
| `adventureCompleted` | `$AAD4` | druhý řádek téže obrazovky |
| `amulet` | `$C374` | čtyři kusy amuletu, jejich grafika a pozice |

`--print` vypíše texty na terminál, aby se dalo zkontrolovat, že to jsou
opravdu ony.
"""
import argparse, base64, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

IMAGE = os.path.join(HERE, '..', 'build/sabrewulf-run.bin')
OUT = os.path.join(HERE, '..', 'data/text.json')

CONSTANTS = [
    ('poemPieces',      0xA01E, [0x01, 0x00, None],
     'LD BC,nn — `B`: kolik bitů `+$0B` se počítá, tedy **kolik kusů amulet má** '
     '(`DisplayPoem`, $A01B)'),
    ('poemLines',       0xA034, [0x06, None],
     'LD B,n — a kolik řádků má sloka'),
    ('poem1',           0xA046, [0x11, None, None],
     'LD DE,nn — sloka za **jeden** kus amuletu'),
    ('poem2',           0xA04B, [0x11, None, None],
     'LD DE,nn — za dva'),
    ('poem3',           0xA050, [0x11, None, None],
     'LD DE,nn — za tři'),
    ('poem4',           0xA031, [0x11, None, None],
     'LD DE,nn — a za všechny čtyři'),
    ('poemMusic',       0xA23A, [0x11, None, None],
     'LD DE,nn / CALL $BD6E — `MusicData_Poem` ($BD33), viz dumpmusic.py'),
    ('poemPause',       0xA240, [0x06, None, 0xCD, 0xFF, 0xA1],
     'LD B,n / CALL $A1FF — ★ a po hudbě **prodleva na čtení**: n × 65536 kol '
     'smyčky `$A1FF`, tedy zhruba půl vteřiny na kolo'),
    ('amuletTable',     0xA211, [0x21, None, None],
     'LD HL,nn — tabulka kusů amuletu na obrazovce básně ($C374)'),
    ('amuletFlag',      0xA220, [0x3E, 0x01, 0x32, None, None],
     'LD A,1 → nn — ★ příznak „tenhle kus už hráč má" ($96B2); `$BC0B` podle '
     'něj bere **druhý blok atributů** té grafiky'),
    ('gameCompleteCopy', 0x9F76, [0x11, None, None],
     'LD DE,nn — obrazovka po dohrání ($9F91)'),
    ('gameCompleteLines', 0x9F79, [0x06, None],
     'LD B,n — a kolik má řádků'),
    ('gameCompleteMusic', 0x9F7E, [0x11, None, None],
     'LD DE,nn / CALL $BD6E — `MusicData_GameComplete` ($BC67)'),
    ('gameOverText',    0xAA7E, [0x11, None, None],
     'LD DE,nn — `GAME OVER PLAYER n` ($AAC1)'),
    ('gameOverPosition', 0xAA81, [0x21, None, None],
     'LD HL,nn — a kde se tiskne: `L` je x, `H` je y'),
    ('gameOverPlayerAt', 0xAA6C, [0x32, None, None],
     'LD (nn),A — ★ číslo hráče se **přepisuje přímo v textu** ($AAD3), '
     'takže „PLAYER 1" a „PLAYER 2" je jeden řetězec'),
    ('adventureText',   0xAA75, [0x11, None, None],
     'LD DE,nn — druhý řádek obrazovky konce ($AAD4) – ★ tiskne se **první**, '
     'nad „GAME OVER"'),
    ('adventurePosition', 0xAA78, [0x21, None, None],
     'LD HL,nn — a jeho pozice'),
    ('gameOverMusic',   0xAA8A, [0x11, None, None],
     'LD DE,nn / CALL $BD6E — `MusicData_GameOver` ($BD28)'),
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


def read_string(ram, addr):
    """Znaky až po ten s bitem 7 – zarážka je vlastnost textu, ne fontu."""
    out, at = bytearray(), addr
    while True:
        byte = peek(ram, at)[0]
        at += 1
        out.append(byte & 0x7F)
        if byte & 0x80:
            return out.decode('ascii'), at
        check(at-addr < 64, 'retezec na $%04X nema zarazku' % addr)


def read_line(ram, addr):
    """Záznam `PrintStringColour`: x, y, atribut a text."""
    x, y, attr = peek(ram, addr, 3)
    text, end = read_string(ram, addr+3)
    return {'x': x, 'y': y, 'column': x >> 3, 'row': y >> 3,
            'attribute': attr, 'text': text}, end


def read_block(ram, addr, count, ends_at, what):
    lines, at = [], addr
    for _ in range(count):
        line, at = read_line(ram, at)
        lines.append(line)
    check(at == ends_at,
          '%s ($%04X) konci na $%04X, ceka se $%04X' % (what, addr, at, ends_at))
    return lines


def read_graphic(ram, addr):
    """Grafika ve formátu kusu kulisy ($BC0B): hlavička, znegované pixely
    a **dva** bloky atributů – matný a jasný, mezi kterými vybírá $96B2."""
    height, width = peek(ram, addr, 2)
    pixels = bytes(b ^ 0xFF for b in peek(ram, addr+2, height*width))
    at = addr+2+height*width
    rows, cols = peek(ram, at, 2)
    at += 2
    first = peek(ram, at, rows*cols)
    at += rows*cols
    second = peek(ram, at, rows*cols)
    at += rows*cols
    return {'address': '$%04X' % addr, 'width': width, 'height': height,
            'widthPixels': width*8, 'attrRows': rows, 'attrCols': cols,
            'bitmap': base64.b64encode(pixels).decode(),
            'attributes': base64.b64encode(bytes(second)).decode(),
            'attributesDull': base64.b64encode(bytes(first)).decode()}, at


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--image', default=IMAGE)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--print', action='store_true', dest='show')
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

    check(values['poemPieces'] == 4 and values['poemLines'] == 4,
          'ceka se ctyri kusy amuletu a ctyri radky na sloku, ctu %d a %d'
          % (values['poemPieces'], values['poemLines']))
    checked += 1

    # ★ Sloky leží za sebou, takže konec jedné je začátek další – a poslední
    # končí přesně na rutině $A18C, která bit básně čte. To je kontrola, že se
    # čte, co si myslíme.
    starts = [values['poem1'], values['poem2'], values['poem3'], values['poem4']]
    check(starts == sorted(starts), 'sloky nejsou v obrazu za sebou: %s' % starts)
    checked += 1
    ends = starts[1:]+[0xA18C]
    stanzas = []
    for index, (start, end) in enumerate(zip(starts, ends)):
        lines = read_block(ram, start, values['poemLines'], end,
                           'sloka %d' % (index+1))
        stanzas.append({'pieces': index+1, 'address': '$%04X' % start,
                        'lines': lines})
        checked += 1

    # obrazovka po dohrání končí přesně na `DisplayPoem`
    complete = read_block(ram, values['gameCompleteCopy'],
                          values['gameCompleteLines'], 0xA01B,
                          'obrazovka po dohrani')
    checked += 1

    # GAME OVER: atribut a text, pozice z volajícího
    over_attr = peek(ram, values['gameOverText'])[0]
    over_text, over_end = read_string(ram, values['gameOverText']+1)
    check(over_end == values['adventureText'],
          'GAME OVER ($%04X) nekonci na $%04X' % (values['gameOverText'],
                                                  values['adventureText']))
    checked += 1
    adventure_attr = peek(ram, values['adventureText'])[0]
    adventure_text, adventure_end = read_string(ram, values['adventureText']+1)
    checked += 1
    player_at = values['gameOverPlayerAt']-values['gameOverText']-1

    # ★ obrázek amuletu na obrazovce básně: čtyři kusy, terminátor $0000
    table, graphics, at = [], {}, values['amuletTable']
    while True:
        graphic = peek(ram, at)[0] | peek(ram, at+1)[0] << 8
        if graphic == 0:
            at += 2
            break
        x = peek(ram, at+2)[0]
        y = peek(ram, at+3)[0]
        table.append({'piece': len(table), 'graphic': '$%04X' % graphic,
                      'x': x, 'y': y})
        at += 4
        check(len(table) <= 8, 'tabulka amuletu ($%04X) nema terminator'
              % values['amuletTable'])
    check(len(table) == values['poemPieces'],
          'tabulka amuletu ma %d kusu, amulet jich ma %d'
          % (len(table), values['poemPieces']))
    checked += 1
    for entry in table:
        addr = int(entry['graphic'][1:], 16)
        graphic, end = read_graphic(ram, addr)
        graphics[entry['graphic']] = graphic
        entry['width'] = graphic['width']
        entry['height'] = graphic['height']
        checked += 1

    data = {
        'about': 'Texty a obrazovka basne, ctene z runtime obrazu originalu '
                 '(tools/dumptext.py, M6). Zaznam textu je x, y, atribut a pak '
                 'znaky, posledni s bitem 7 ($B53D). Font je ROM fontu ZX '
                 'Spectra, takze tady jsou jen bajty textu.',
        'format': {
            'record': ['x', 'y', 'attribute', 'text'],
            'terminator': 'bit 7 posledniho znaku',
            'routine': '$B53D',
            'font': 'ROM ZX Spectra ($3C00, CHARS $5C36) – M1, disasm_notes §8',
        },
        'poem': {
            'routine': '$A01B',
            'screenRoutine': '$A207',
            'handler': '$A234',
            'pieces': values['poemPieces'],
            'linesPerStanza': values['poemLines'],
            'music': 'poem',
            'pauseRounds': values['poemPause'],
            'pauseFrames': round(values['poemPause']*65536*26/69888),
            'stanzas': stanzas,
            'note': '★ Ukaze se **jedna** sloka, ta, ktera odpovida poctu kusu '
                    'amuletu – ne vsechny predchozi. $A01B secte bity +$0B '
                    'a skoci na jednu ze ctyr adres. Pred ni $A207 smaze hraci '
                    'plochu a nakresli obrazek amuletu, po ni se hraje '
                    'MusicData_Poem a ceka se %d x 65536 kol smycky $A1FF '
                    '(asi %.1f s pri 50,08 Hz).'
                    % (values['poemPause'],
                       values['poemPause']*65536*26/3500000),
        },
        'amulet': {
            'table': '$%04X' % values['amuletTable'],
            'flagAddress': '$%04X' % values['amuletFlag'],
            'drawRoutine': '$BC0B',
            'pieces': table,
            'graphics': graphics,
            'note': '★ Kazda grafika kusu ma **dva bloky atributu**: prvni pro '
                    'kus, ktery hrac jeste nema, druhy pro sebrany. $BC0B '
                    'vybira podle $96B2 ($A220). Format je tentyz jako u kusu '
                    'kulisy (M2): hlavicka vyska/sirka a znegovane pixely, '
                    'takze to nakresli app/roomComposer.js drawPiece().',
        },
        'gameComplete': {
            'address': '$%04X' % values['gameCompleteCopy'],
            'music': 'gameComplete',
            'lines': complete,
        },
        'gameOver': {
            'address': '$%04X' % values['gameOverText'],
            'x': values['gameOverPosition'] & 0xFF,
            'y': values['gameOverPosition'] >> 8,
            'attribute': over_attr,
            'text': over_text,
            'playerDigitAt': player_at,
            'music': 'gameOver',
            'note': '★ cislo hrace se prepisuje primo v textu ($AA6C), takze '
                    '„PLAYER 1" a „PLAYER 2" je jeden retezec; znak je na '
                    'pozici %d' % player_at,
        },
        'adventureCompleted': {
            'address': '$%04X' % values['adventureText'],
            'x': values['adventurePosition'] & 0xFF,
            'y': values['adventurePosition'] >> 8,
            'attribute': adventure_attr,
            'text': adventure_text,
        },
        'values': values,
        'source': notes,
    }

    with open(args.out, 'w') as out:
        json.dump(data, out, indent=1, sort_keys=False)
        out.write('\n')

    if args.show:
        for stanza in stanzas:
            print('sloka za %d kus(y) amuletu (%s):'
                  % (stanza['pieces'], stanza['address']))
            for line in stanza['lines']:
                print('  %2d,%2d  $%02X  %s'
                      % (line['column'], line['row'], line['attribute'],
                         line['text']))
        print()
        print('obrazovka po dohrani (%s):' % data['gameComplete']['address'])
        for line in complete:
            print('  %2d,%2d  $%02X  %s'
                  % (line['column'], line['row'], line['attribute'], line['text']))
        print()
        print('konec hry: $%02X  %s' % (over_attr, over_text))
        print('           $%02X  %s' % (adventure_attr, adventure_text))
        print()
        print('obrazek amuletu (%s):' % data['amulet']['table'])
        for entry in table:
            print('  kus %d  grafika %s  %d x %d px  na x=%d y=%d'
                  % (entry['piece'], entry['graphic'], entry['width']*8,
                     entry['height'], entry['x'], entry['y']))

    print('%s: %d slok, %d radku, %d kusu amuletu, %d kontrol'
          % (os.path.relpath(args.out), len(stanzas),
             sum(len(s['lines']) for s in stanzas)+len(complete)+2,
             len(table), checked))


if __name__ == '__main__':
    main()
