#!/usr/bin/env python3
"""Převede ZX `.scr` (6912 B) na datový soubor remaku.

    ./tools/mkscreen.py <vstup.scr> [data/loading.json] [--name "LOADING SCREEN"]

Uloží obrazovku **tak, jak leží v paměti stroje** – 6912 B od `$4000` do
`$5AFF`, tedy 6144 B bitmapy v nelineárním adresování ULA a 768 B atributů za
ní, base64. Přesně to, co je v `.scr`, a přesně to, co jde po kazetě: přehazovat
pixelové řádky do lineárního pořadí by znamenalo je v prohlížeči zase rozházet
zpátky, protože `ZXVideoRAM` drží paměť v pořadí stroje a `ZXMachineSounds`
posílá bajty datovým blokem v pořadí adres.

Použité na loading screen originálu:

- `data/loading.json` z `sources/media/screens/loading_screen.scr` – loading
  screen z kazety (★ shoduje se bajt po bajtu s tím, co nahraje kazeta, viz
  `sources/docs/disasm_notes.md` §2). Nahrává ho `tapeLoadingModel` – doopravdy,
  bajt po bajtu, jak je přehraje datový blok.

Titulní obrazovka (`title_menu.scr`, menu `1 PLAYER GAME` … přes místnost
`$61C6`) se do dat nepřevádí: remake po kazetě jde rovnou do vlastního menu a
džungli pod ním skládá z předlohy `$61C6` (`data/rooms.json` → `mainMenu`).

★ Řezat z těchhle obrázků kusy kulisy nemá smysl a nástroj to schválně neumí:
džungle je v `data/scenery.json` vytažená z ROM a předlohy říkají, kde který kus
leží. Výřez z obrazovky je proti tomu horší v obou směrech – nese, co přes něj
originál zrovna natiskl, a neví, kde končí jeden kus a začíná druhý.
"""
import argparse, base64, json, os

SCREEN_BYTES = 6912


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src')
    ap.add_argument('dst', nargs='?', default='data/loading.json')
    ap.add_argument('--name', default='LOADING SCREEN')
    args = ap.parse_args()

    scr = open(args.src, 'rb').read()
    if len(scr) != SCREEN_BYTES:
        raise SystemExit('cekam %d B .scr, mam %d' % (SCREEN_BYTES, len(scr)))

    data = {
        'note': 'obrazovka z originálu (tools/mkscreen.py), videopaměť '
                '$4000-$5AFF tak, jak ji drží stroj',
        'name': args.name,
        'source': os.path.basename(args.src),
        'width': 256, 'height': 192,
        'videoRAM': base64.b64encode(scr).decode('ascii')
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)
    with open(args.dst, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print('%s -> %s' % (args.src, args.dst))


if __name__ == '__main__':
    main()
