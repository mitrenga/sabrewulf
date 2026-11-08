#!/usr/bin/env python3
"""**48 předloh místností** z runtime obrazu do `data/rooms.json`, plus místnost
pod hlavním menu.

    PYTHONPATH=tools/vendor ./tools/dumprooms.py [--png build/rooms]

★ Předloha místnosti **není obrázek, je to seznam kusů kulisy s pozicemi.**
`DrawRoom` (`$BBF7`) čte záznamy po čtyřech bajtech – `DEFW` adresa kusu kulisy,
`DEFB` X v pixelech, `DEFB` Y v pixelech – a končí na `$0000`. Předlohy leží
za sebou od `$6200` a `RoomTable` (`$6166`) na ně ukazuje 48 ukazateli; nástroj
kontroluje, že konec jedné předlohy je vždycky začátek další, jinak spadne –
tím je formát dokázaný, ne odhadnutý.

★ **`Room_Special_MainMenu` (`$61C6`) je 49. předloha v témž formátu**, jen
neleží v `RoomTable`: je to džungle pod hlavním menu a končí přesně tam, kde
začíná `Room_00`, což nástroj kontroluje. Zapisuje se do `mainMenu` vedle
`templates`, takže si ji `app/roomComposer.js` složí týmž kódem jako každou
jinou místnost, místo aby se titulní obrazovka brala jako dump videopaměti.

Z X se při kreslení použije jen horních pět bitů (`$B8AD` dělá `RRCA` ×3 a
`AND $1F`), takže se kreslí po celých bajtech; v datech se proto najdou i X
jako 21, 34 nebo 57 a v `rooms.json` je u nich `xByte`, který originál
skutečně použije. Y je vždycky násobek osmi, od `$10` (hrací plocha začíná
na znakovém řádku 2).

**Náhledy kreslí originál, ne nástroj.** S `--png` se runtime obraz nahraje
do simulátoru, zavolá se v něm `ClearPlayArea` a `DrawRoom` a uloží se to,
co po nich zůstalo ve videopaměti – takže náhledy jsou skutečné bajty
originálu, ne interpretace. Že se s nimi data remaku shodují bajt po bajtu,
hlídá `tools/matchscreen.py`.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import roomlib                                                  # noqa: E402
from scr2png import scr_to_rgb, write_png                        # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ram', nargs='?', default=os.path.join(ROOT, 'build/sabrewulf-run.bin'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'data/rooms.json'))
    ap.add_argument('--png', default=os.path.join(ROOT, 'build/rooms'),
                    help='kam uložit náhledy předloh nakreslené originálem '
                         '(default build/rooms); --png= náhledy vypne')
    args = ap.parse_args()

    world = roomlib.World(args.ram)
    index_by_addr = {p.addr: p.index for p in world.pieces}

    unaligned = []

    def pack(items, name):
        """Kusy předlohy jako hex po třech bajtech: číslo kusu, X a Y v pixelech.

        Stejná úsporná forma jako mřížka ve world.json – 48 předloh se tím
        vejde do pár kilobajtů místo stovky.
        ★ X a Y jsou **surové bajty předlohy v pixelech**, ne po bajtech
        a znakových řádcích: kreslení si dolní tři bity X samo zahodí
        (`$B8AD` dělá `RRCA` ×3 a `AND $1F`), ale **kolize je nezahazuje**
        (`$B873` porovnává `IX+$02` celé), takže se ta čtyři nezarovnaná
        X musí zachovat – jinak by remake měl zeď o pár pixelů jinde (M3).
        """
        for gfx, x, y in items:
            if x % 8:
                unaligned.append({'template': name,
                                  'piece': '$%02X' % index_by_addr[gfx],
                                  'x': x, 'xByte': (x >> 3) & 0x1F, 'y': y})
        return ''.join('%02X%02X%02X' % (index_by_addr[gfx], x, y)
                       for gfx, x, y in items)

    templates = []
    for template, addr in enumerate(world.room_table):
        items = world.rooms[template]
        packed = pack(items, '$%02X' % template)
        templates.append({
            'id': '$%02X' % template,
            'address': '$%04X' % addr,
            'rooms': sum(1 for t in world.layout if t == template),
            'count': len(items),
            'items': packed
        })

    # ★ 49. předloha: džungle pod hlavním menu. Není v RoomTable, leží těsně
    # před Room_00 a musí na něj přesně navazovat – to je tady i kontrola
    # toho, že je přečtená celá.
    menu_items, menu_end = roomlib.read_room(world.ram, roomlib.ROOM_MAIN_MENU)
    if menu_end != world.room_table[0]:
        raise SystemExit('Room_Special_MainMenu ($%04X) konci na $%04X, ale '
                         'Room_00 zacina na $%04X – format nesedi'
                         % (roomlib.ROOM_MAIN_MENU, menu_end, world.room_table[0]))
    main_menu = {
        'note': 'Room_Special_MainMenu – džungle pod hlavním menu; táž předloha '
                'v témž formátu, jen mimo RoomTable',
        'address': '$%04X' % roomlib.ROOM_MAIN_MENU,
        'count': len(menu_items),
        'items': pack(menu_items, 'mainMenu')
    }

    unused = [t for t in range(roomlib.ROOM_TABLE_ENTRIES)
              if t not in set(world.layout)]
    data = {
        'note': 'M2: 48 předloh místností z RoomTable ($6166) – seznam kusů '
                'kulisy s pozicemi, jak je čte DrawRoom ($BBF7). Kusy jsou '
                'v data/scenery.json, mřížka světa v data/world.json; ověřeno '
                'proti originálu bajt po bajtu nástrojem tools/matchscreen.py '
                '(tools/dumprooms.py).',
        'source': os.path.basename(args.ram),
        'roomTableAddress': '$%04X' % roomlib.ROOM_TABLE,
        'count': len(templates),
        'unused': ['$%02X' % t for t in unused],
        'playArea': {'x': 0, 'y': roomlib.PLAY_TOP,
                     'width': roomlib.PLAY_WIDTH, 'height': roomlib.PLAY_HEIGHT},
        # ★ hrací plocha se před kreslením vynuluje a atributy se vyplní $40
        # (ClearPlayArea $BB5C, ClearPlayArea_Attributes $BB7C)
        'clearAttribute': '$40',
        'itemFormat': 'hex po třech bajtech: kus kulisy, X v pixelech (surový bajt předlohy), Y v pixelech (16–184, vždy násobek osmi)',
        # ★ X je v datech v pixelech, ale spodní tři bity originál zahazuje
        # ($B8AD: RRCA ×3 / AND $1F). Tady jsou všechny záznamy, kde to je
        # vidět – kreslí se stejně jako by X bylo zaokrouhlené dolů.
        'unalignedX': unaligned,
        'templates': templates,
        'mainMenu': main_menu
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print('%s (%d predloh, %d kusu kulisy dohromady, nepouzite %s; '
          'k tomu mainMenu $%04X, %d kusu)'
          % (args.out, len(templates), sum(t['count'] for t in templates),
             ' '.join(data['unused']), roomlib.ROOM_MAIN_MENU, len(menu_items)))

    if args.png:
        import matchscreen                                       # noqa: E402
        original = matchscreen.Original(args.ram)
        os.makedirs(args.png, exist_ok=True)
        for template, addr in enumerate(world.room_table):
            bitmap, attrs = matchscreen.play_area(original.draw(addr))
            if not any(bitmap):
                raise SystemExit('predloha $%02X: originál nakreslil prázdnou '
                                 'obrazovku – simulátor nedojel' % template)
            write_png(os.path.join(args.png, 'template%02X.png' % template),
                      scr_to_rgb(roomlib.play_area_to_scr(bitmap, attrs)), 256)
        print('nahledy (kreslil originál v simulátoru): %s/template00.png .. '
              'template2F.png' % args.png)


if __name__ == '__main__':
    main()
