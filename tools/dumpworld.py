#!/usr/bin/env python3
"""**Svět 16 × 16** a **mapa přechodů** do `data/world.json`.

    ./tools/dumpworld.py

★ `Layout` (`$6066`) je **256 bajtů = mřížka 16 × 16** a každý bajt je číslo
předlohy z `RoomTable` (`$6166`). Různých čísel je **45 ze 48**; nepoužité jsou
`$01`, `$13` a `$24` a nejčastější `$11` je ve světě 21×. Tím je vysvětlená
dobová výtka, že se obrazovky opakují (`sources/docs/disasm_notes.md` §4).
Tohle je přečtené z runtime obrazu a nástroj to kontroluje.

**Mapa přechodů se od M3 počítá z kolizního pravidla originálu**, ne z pixelů.
V programu žádná tabulka průchodů není, ale **je známé, jak se hra ptá na
zeď**: `$B873` prochází tentýž seznam kusů kulisy, ze kterého se místnost
kreslí, a u každého kusu bere jeho **obálku** z jeho vlastní hlavičky – žádné
pixely. Kolizní obálka Sabremana je `LD BC,$160E` na `$AF40`, tedy 22 px svisle
a 14 px vodorovně (`sources/docs/disasm_notes.md` §14, `tools/dumpphysics.py`).

Hranice je tedy průchodná, když **existuje souřadnice, na které je volno z obou
stran** – z odcházející strany na krajní souřadnici, kterou hra ještě považuje
za „uvnitř" (`x = 255 - $96AD = 239`, `y = 191`), a z přicházející strany na
souřadnici, na kterou hra vstupuje (`x = 0`, `y = $27 = 39`). Obojí je operand
skutečné instrukce, ne odhad.

★ **Vyšlo to a je to ověřené na běžícím originálu**: `tools/mapwalk.py` do hry
v simulátoru postaví Sabremana k hranici a nechá ho jí projít. Svislé přechody
se navíc shodují **240 ze 240** s dobovou mapou; z vodorovných 211 ze 240 a
zbylých 29 je **rozhodnuto ve prospěch dat** – hra jimi projde ve všech 29
případech (`tools/mapwalk.py --check`, disasm_notes.md §15). Tím je uzavřená
otevřená otázka M2.

Odvození z **pixelových mezer** (jak to dělal M2) zůstává jako nezávislá
druhá cesta: hrany předloh se pořád měří, ukládají do `templateEdges` a
nástroj vypíše, ve kolika hranicích se obě metody rozcházejí. Práh je
**16 pixelů = šířka Sabremana**; ★ žádná mezera na hranách předloh nemá 14
ani 15 pixelů, takže práh leží v prázdném pásu.
"""
import argparse, collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import roomlib                                                  # noqa: E402

# ★ šířka Sabremana: sprite $10 je 2 bajty × 21 řádků (dumpsprites.py)
SABREMAN_WIDTH = 16
# ★ startovní stav entit: `$B21E` (nastavení životů) volá `$AC6B`, a to je
# `LD HL,$AC77 / LD DE,$9702 / LD BC,$0090 / LDIR` – 144 bajtů předpřipraveného
# „game status bufferu". První záznam je Sabreman a jeho druhý bajt je číslo
# startovní obrazovky.
START_COPY = 0xAC6B
START_COPY_CODE = bytes((0x21, 0x77, 0xAC, 0x11, 0x02, 0x97, 0x01, 0x90, 0x00,
                         0xED, 0xB0, 0xC9))
UNUSED_EXPECTED = ['$01', '$13', '$24']
# směr: (dx, dy, moje hrana, hrana souseda)
DIRECTIONS = (('up', 0, -1, 'top', 'bottom'),
              ('down', 0, 1, 'bottom', 'top'),
              ('left', -1, 0, 'left', 'right'),
              ('right', 1, 0, 'right', 'left'))
BITS = {'up': 1, 'down': 2, 'left': 4, 'right': 8}


def free_runs(bits, minimum):
    """Souvislé mezery (nenakreslené pixely) delší nebo rovné `minimum`."""
    runs, start = [], None
    for i, bit in enumerate(list(bits)+[1]):
        if not bit and start is None:
            start = i
        elif bit and start is not None:
            if i-start >= minimum:
                runs.append([start, i-start])
            start = None
    return runs


def edge_bits(bitmap):
    """Krajní pixelový řádek/sloupec hrací plochy, po jednotlivých pixelech."""
    rows, cols = roomlib.PLAY_HEIGHT, roomlib.PLAY_WIDTH
    return {
        'left': [(bitmap[y*32] >> 7) & 1 for y in range(rows)],
        'right': [bitmap[y*32+31] & 1 for y in range(rows)],
        'top': [(bitmap[(x >> 3)] >> (7-(x & 7))) & 1 for x in range(cols)],
        'bottom': [(bitmap[(rows-1)*32+(x >> 3)] >> (7-(x & 7))) & 1
                   for x in range(cols)],
    }


def overlap(a, b, minimum):
    """Průchod je tam, kde se mezery obou stran překryjí alespoň o `minimum`."""
    out = []
    for start_a, length_a in a:
        for start_b, length_b in b:
            start = max(start_a, start_b)
            end = min(start_a+length_a, start_b+length_b)
            if end-start >= minimum:
                out.append([start, end-start])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ram', nargs='?', default=os.path.join(ROOT, 'build/sabrewulf-run.bin'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'data/world.json'))
    ap.add_argument('--threshold', type=int, default=SABREMAN_WIDTH)
    args = ap.parse_args()

    world = roomlib.World(args.ram)
    layout = world.layout

    # startovní obrazovka – přečtená jako operand skutečných instrukcí
    if world.ram.block(START_COPY, len(START_COPY_CODE)) != START_COPY_CODE:
        raise SystemExit('na $%04X neni LD HL,$AC77 / LD DE,$9702 / '
                         'LD BC,$0090 / LDIR – startovni stav je jinde'
                         % START_COPY)
    state = world.ram.word(START_COPY+1)
    start_room = world.ram.byte(state+1)
    start = {
        'address': '$%04X' % state,
        'room': '$%02X' % start_room,
        'column': start_room % roomlib.COLS, 'row': start_room//roomlib.COLS,
        'template': '$%02X' % layout[start_room],
        # zbytek prvního záznamu: sprite, X, Y a atribut Sabremana. Rozbor
        # záznamu entity je M3/M4, tady je to jen doklad, odkud číslo je.
        'sabremanSprite': '$%02X' % world.ram.byte(state),
        'sabremanX': world.ram.byte(state+3),
        'sabremanY': world.ram.byte(state+4),
        'sabremanAttribute': '$%02X' % world.ram.byte(state+5),
        'confirmedBySimulation': True
    }
    used = sorted(set(layout))
    unused = ['$%02X' % t for t in range(roomlib.ROOM_TABLE_ENTRIES) if t not in used]
    if unused != UNUSED_EXPECTED:
        raise SystemExit('nepouzite predlohy jsou %s, cekam %s'
                         % (unused, UNUSED_EXPECTED))
    counts = {t: sum(1 for x in layout if x == t) for t in used}
    top = max(counts, key=lambda t: counts[t])

    # hrany všech 48 předloh + statistika, jak daleko je práh od šumu
    edges, all_runs = [], []
    for template in range(roomlib.ROOM_TABLE_ENTRIES):
        bits = edge_bits(world.render_template(template).bitmap_rows())
        edges.append({side: free_runs(bits[side], args.threshold)
                      for side in ('top', 'bottom', 'left', 'right')})
        for side in bits:
            all_runs += [length for _, length in free_runs(bits[side], 1)]
    noise = [n for n in all_runs if n < args.threshold]
    passages = [n for n in all_runs if n >= args.threshold]

    # ★ přechody z kolizního pravidla originálu ($B873): volno z obou stran
    physics = json.load(open(os.path.join(ROOT, 'data/physics.json')))
    values = physics['values']
    edge_x = 0xFF-values['exitWidth']       # největší x, které hra bere „uvnitř"
    enter_x = values['enterLeftX']
    edge_y = values['exitBottomY']-1        # největší y „uvnitř"
    enter_y = values['enterTopY']
    box = (values['boxHeight'], values['boxWidth'])

    def free(col, row, x, y):
        items = world.rooms[layout[row*roomlib.COLS+col]]
        return roomlib.collides(world.ram, items, x, y, *box) is None

    exits, one_sided, borders = bytearray(256), 0, 0
    spans = []
    for row in range(roomlib.ROWS):
        for col in range(roomlib.COLS):
            mask = 0
            for name, dx, dy, mine, theirs in DIRECTIONS:
                nc, nr = col+dx, row+dy
                if not (0 <= nc < roomlib.COLS and 0 <= nr < roomlib.ROWS):
                    continue                # za hranicí světa se nechodí
                borders += 1
                if dx:
                    # vodorovně: hledá se y, na kterém je volno u obou hran
                    leaving = edge_x if dx > 0 else enter_x
                    arriving = enter_x if dx > 0 else edge_x
                    ours = {y for y in range(values['exitTopY'], values['exitBottomY'])
                            if free(col, row, leaving, y)}
                    common = {y for y in ours if free(nc, nr, arriving, y)}
                else:
                    leaving = edge_y if dy > 0 else values['exitTopY']
                    arriving = enter_y if dy > 0 else values['enterBottomY']
                    ours = {x for x in range(0, edge_x+1)
                            if free(col, row, x, leaving)}
                    common = {x for x in ours if free(nc, nr, x, arriving)}
                if common:
                    mask |= BITS[name]
                    spans.append(len(common))
                elif ours:
                    # volno jen z naší strany: hranice se dá opustit, ale
                    # ★ vstup je v kulise, takže `$B81C` vrátí Sabremana
                    # o krok zpátky – už ale v nové obrazovce
                    one_sided += 1
            exits[row*roomlib.COLS+col] = mask

    # druhá, nezávislá cesta: pixelové mezery na hranách (metoda M2)
    pixel_exits = bytearray(256)
    for row in range(roomlib.ROWS):
        for col in range(roomlib.COLS):
            template = layout[row*roomlib.COLS+col]
            mask = 0
            for name, dx, dy, mine, theirs in DIRECTIONS:
                nc, nr = col+dx, row+dy
                if not (0 <= nc < roomlib.COLS and 0 <= nr < roomlib.ROWS):
                    continue
                if overlap(edges[template][mine], edges[layout[nr*roomlib.COLS+nc]][theirs],
                           args.threshold):
                    mask |= BITS[name]
            pixel_exits[row*roomlib.COLS+col] = mask
    pixel_diff = sum(bin(a ^ b).count('1') for a, b in zip(exits, pixel_exits))

    reachable = sum(1 for m in exits if m)
    data = {
        'note': 'M2/M3: mřížka světa z Layout ($6066) a mapa přechodů '
                'spočítaná z KOLIZNÍHO PRAVIDLA originálu ($B873 – obálky '
                'kusů kulisy, ne pixely) a ověřená na běžícím originálu '
                '(tools/mapwalk.py). Kusy kulisy jsou v data/scenery.json, '
                'předlohy v data/rooms.json; skládání je ověřené proti '
                'originálu bajt po bajtu (tools/matchscreen.py). Viz '
                'sources/docs/disasm_notes.md §12 a §15.',
        'source': os.path.basename(args.ram),
        'layoutAddress': '$%04X' % roomlib.LAYOUT,
        'roomTableAddress': '$%04X' % roomlib.ROOM_TABLE,
        'visitedRoomsAddress': '$%04X' % roomlib.VISITED_ROOMS,
        'visitedRoomsBits': 256,
        'columns': roomlib.COLS, 'rows': roomlib.ROWS,
        'roomsCount': roomlib.COLS*roomlib.ROWS,
        # ★ hra začíná na obrazovce 8,10 (Layout $A8, předloha $08) – přečteno
        # z $AC77 a nezávisle potvrzeno simulací ($9703 během hry)
        'start': start,
        'templatesCount': roomlib.ROOM_TABLE_ENTRIES,
        'templatesUsed': len(used),
        'templatesUnused': unused,
        'mostUsedTemplate': {'template': '$%02X' % top, 'rooms': counts[top]},
        'roomWidth': roomlib.PLAY_WIDTH, 'roomHeight': roomlib.PLAY_HEIGHT,
        'playAreaTop': roomlib.PLAY_TOP,
        # jeden řádek mřížky = 16 bajtů jako hex, stejně jako v M1
        'templates': [layout[r*roomlib.COLS:(r+1)*roomlib.COLS].hex().upper()
                      for r in range(roomlib.ROWS)],
        'roomTable': ['$%04X' % p for p in world.room_table],
        'passages': {
            'derived': True,
            'method': 'kolizní pravidlo originálu ($B873): obálky kusů kulisy '
                      'proti obálce Sabremana 14 x 22 px, volno musí být '
                      'z obou stran hranice – z odcházející na x=239 / y=191, '
                      'z přicházející na x=0 / y=39 (data/physics.json)',
            'verifiedOnOriginal': 'tools/mapwalk.py',
            'boxWidth': values['boxWidth'], 'boxHeight': values['boxHeight'],
            'leavingX': edge_x, 'leavingY': edge_y,
            'enteringX': enter_x, 'enteringY': enter_y,
            'smallestGap': min(spans) if spans else 0,
            'largestGap': max(spans) if spans else 0,
            # druhá cesta: pixelové mezery na hranách předloh (metoda M2)
            'pixelMethodDiffers': pixel_diff,
            'thresholdPixels': args.threshold,
            'thresholdWhy': 'šířka Sabremana (sprite $10, 2 bajty × 21 řádků)',
            'largestNonPassage': max(noise) if noise else 0,
            'smallestPassage': min(passages) if passages else 0,
            'runLengths': dict(sorted(collections.Counter(all_runs).items())),
            'bordersChecked': borders,
            'oneSidedWalls': one_sided,
            'roomsWithExits': reachable,
            # bitová maska na obrazovku: 1 = nahoru, 2 = dolů, 4 = vlevo, 8 = vpravo
            'bits': {'up': 1, 'down': 2, 'left': 4, 'right': 8},
            'exits': [exits[r*roomlib.COLS:(r+1)*roomlib.COLS].hex().upper()
                      for r in range(roomlib.ROWS)],
            # hrany předloh: mezery jako [začátek, délka] v pixelech
            'templateEdges': [{'id': '$%02X' % t, **edges[t]}
                              for t in range(roomlib.ROOM_TABLE_ENTRIES)]
        }
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print('%s (%d x %d obrazovek, %d ruznych predloh z %d, nejcastejsi $%02X %dx)'
          % (args.out, roomlib.COLS, roomlib.ROWS, len(used),
             roomlib.ROOM_TABLE_ENTRIES, top, counts[top]))
    print('pruchody z kolizniho pravidla ($B873, obalka %d x %d px): %d z %d '
          'hranic otevrenych, %d jednostrannych; nejuzsi pruchod %d px'
          % (values['boxWidth'], values['boxHeight'],
             sum(bin(m).count('1') for m in exits), borders, one_sided,
             min(spans) if spans else 0))
    print('pixelova metoda M2 (mezery na hranach) se lisi v %d hranicich '
          '(prah %d px, mezi 13 a 16 zadna mezera neexistuje)'
          % (pixel_diff, args.threshold))
    print('start: obrazovka %d,%d (Layout %s, predloha %s), Sabreman sprite %s '
          'na %d,%d' % (start['column'], start['row'], start['room'],
                        start['template'], start['sabremanSprite'],
                        start['sabremanX'], start['sabremanY']))
    print('prechody: %d hranic, %d obrazovek ma aspon jeden vychod, '
          '%d slepych zdi (mezera jen z jedne strany)'
          % (borders, reachable, one_sided))


if __name__ == '__main__':
    main()
