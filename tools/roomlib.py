#!/usr/bin/env python3
"""Formát místnosti a kulisy Sabre Wulf – čtení a **věrné překreslení**.

Tohle je jádro milníku M2, po vzoru `roomlib.py` u underwurlde: jedno místo,
kde je popsané, jak originál skládá obrazovku, a **replika jeho vykreslovací
rutiny bajt po bajtu**. Nic tady není odhad – všechno je přečtené jako operandy
skutečných instrukcí runtime obrazu (`build/sabrewulf-run.bin`) a proti originálu
to porovnává `tools/matchscreen.py`.

★ **Předloha místnosti je seznam kusů kulisy s pozicemi.** `DrawRoom` (`$BBF7`)
čte záznamy po **čtyřech bajtech** – `DEFW` adresa kusu kulisy, `DEFB` X, `DEFB` Y
– a končí na `$0000`:

    $6200 DEFW $7C0C   ; kus kulisy
    $6202 DEFB $00,$10 ; X = 0 px, Y = 16 px (= znakový řádek 2)
    ...
    $6248 DEFW $0000   ; terminátor

X je v **pixelech, ale spodní tři bity se zahazují** (`$B8AD` dělá `RRCA` ×3
a `AND $1F`), takže se kreslí po celých bajtech; v datech se proto najdou i X
jako 21 nebo 57. Y je vždycky násobek osmi, od `$10` (hrací plocha začíná
na znakovém řádku 2).

★ **Kus kulisy** (`$70BC`–`$9691`, přesně **41 kusů**, `$01`–`$29`) je:

    DEFB height   ; výška v pixelových řádcích
    DEFB width    ; šířka v bajtech
    DEFB ...      ; height*width bajtů pixelů, **uložených znegovaně**
    DEFB attrH    ; výška v atributech (= height/8)
    DEFB attrW    ; šířka v atributech (= width)
    DEFB ...      ; attrH*attrW atributů

Pixely se při kreslení invertují (`CPL` na `$BC17`) a zapisují **natvrdo**
(`LD (HL),A`, nikoli `OR`), takže pozdější kus překryje dřívější i svými
nulami – **na pořadí záleží**. Atributy se zapisují taky natvrdo, bez inverze.

★ Adresování je originálovo, včetně **osmibitových přetečení**. `INC L` na
konci řádku není nevinné: v `L` je dolních pět bitů X v bajtech a horní tři
znakový řádek uvnitř třetiny, takže kus, který vyjede vpravo, **nepokračuje
na témže řádku, ale o osm pixelů níž** (a z posledního znakového řádku
třetiny se přetočí na její začátek). `$B8CC` (`ScreenPos1PixelBelow`) dělá
totéž na konci každého pixelového řádku. Replikuje se to tady, ne v prohlížeči.

Sekce vysvětlené v `sources/docs/disasm_notes.md` §12.
"""
import os

RUNTIME = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '..', 'build/sabrewulf-run.bin')

LAYOUT = 0x6066                 # mřížka světa 16 × 16
ROOM_TABLE = 0x6166             # 48 ukazatelů na předlohy
ROOM_TABLE_ENTRIES = 48
ROOM_MAIN_MENU = 0x61C6         # Room_Special_MainMenu
SCENERY_FIRST = 0x70BC          # Background Graphic $01
SCENERY_END = 0x9692            # = začátek „game status bufferu" ($9692)
SCENERY_COUNT = 41
SPRITES_TABLE = 0xBF84          # SpritesTable
SPRITES_COUNT = 196             # $BF84–$C10B
SPRITE_DATA_FIRST = 0xC10C
VISITED_ROOMS = 0x96BF

COLS = ROWS = 16
PANEL_ROWS = 2                  # znakové řádky panelu (0–1)
PLAY_TOP = PANEL_ROWS*8         # 16 px
PLAY_HEIGHT = 192-PLAY_TOP      # 176 px
PLAY_WIDTH = 256


class Ram:
    """Runtime obraz RAM ($4000–$FFFF) s kontrolou, že je to opravdu on."""

    def __init__(self, path=RUNTIME):
        self.path = path
        self.data = open(path, 'rb').read()
        if len(self.data) != 49152:
            raise SystemExit('%s: cekam 49152 B RAM ($4000-$FFFF), mam %d'
                             % (path, len(self.data)))
        # ★ runtime obraz pozná se podle dešifrovaného GameEntry a copyrightu
        # (disasm_notes.md §1) – kazetový obraz by tady měl znegovaný nesmysl
        if self.block(0x6000, 5) != bytes((0xF3, 0x31, 0x00, 0x60, 0xC3)):
            raise SystemExit('%s: na $6000 neni F3 31 00 60 C3 – tohle neni '
                             'runtime obraz, spust tools/mkruntime.py' % path)
        if not self.block(0x6007, 24).startswith(b'COPYRIGHT 1984 A.C.G.'):
            raise SystemExit('%s: na $6007 neni text copyrightu' % path)

    def byte(self, addr):
        return self.data[addr-0x4000]

    def word(self, addr):
        return self.byte(addr) | (self.byte(addr+1) << 8)

    def block(self, addr, length):
        return self.data[addr-0x4000:addr-0x4000+length]


# ---------------------------------------------------------------- kusy kulisy

class Scenery:
    """Jeden kus kulisy: pixely (už odnegované) a atributy."""

    def __init__(self, index, addr, ram):
        self.index, self.addr = index, addr
        self.height = ram.byte(addr)            # pixelových řádků
        self.width = ram.byte(addr+1)           # bajtů
        base = addr+2
        # ★ pixely jsou v datech znegované, hra je při kreslení invertuje (CPL)
        self.pixels = bytes(b ^ 0xFF for b in ram.block(base, self.height*self.width))
        after = base+self.height*self.width
        self.attr_height = ram.byte(after)
        self.attr_width = ram.byte(after+1)
        self.attrs = ram.block(after+2, self.attr_height*self.attr_width)
        self.size = 2+self.height*self.width+2+self.attr_height*self.attr_width
        if self.attr_width != self.width or self.attr_height*8 != self.height:
            raise SystemExit('kus kulisy $%02X ($%04X): pixely %dx%d, ale atributy '
                             '%dx%d – nesedi na sebe'
                             % (index, addr, self.width, self.height,
                                self.attr_width, self.attr_height))


def read_scenery(ram):
    """41 kusů kulisy od `$70BC`; blok musí skončit přesně na `$9692`.

    Nic se nehádá: kusy se procházejí za sebou podle vlastních hlaviček
    a když se konec nesejde s `$9692` (což je `GameOptions`, první bajt
    „game status bufferu"), nástroj spadne."""
    pieces, addr = [], SCENERY_FIRST
    for index in range(1, SCENERY_COUNT+1):
        piece = Scenery(index, addr, ram)
        pieces.append(piece)
        addr += piece.size
    if addr != SCENERY_END:
        raise SystemExit('blok kulisy skoncil na $%04X, cekam $%04X – %d kusu '
                         'je spatne' % (addr, SCENERY_END, SCENERY_COUNT))
    return pieces


# ------------------------------------------------------------------ předlohy

def read_room(ram, addr):
    """Předloha místnosti jako seznam `(adresa kusu kulisy, X, Y)`."""
    items = []
    while True:
        gfx = ram.word(addr)
        if gfx == 0:
            return items, addr+2
        items.append((gfx, ram.byte(addr+2), ram.byte(addr+3)))
        addr += 4
        if len(items) > 64:
            raise SystemExit('predloha na $%04X ma vic nez 64 kusu kulisy – '
                             'chybi terminator, format nesedi' % addr)


def read_room_table(ram):
    """48 ukazatelů `RoomTable` ($6166); kontroluje, že jsou vzestupné a že
    předlohy na sebe navazují bez děr (to je zároveň důkaz, že je formát
    přečtený správně – jinak by konec jedné nesedl na začátek další)."""
    pointers = [ram.word(ROOM_TABLE+i*2) for i in range(ROOM_TABLE_ENTRIES)]
    for i, addr in enumerate(pointers):
        items, end = read_room(ram, addr)
        if i+1 < len(pointers) and end != pointers[i+1]:
            raise SystemExit('predloha $%02X ($%04X) konci na $%04X, ale dalsi '
                             'zacina na $%04X – format nesedi'
                             % (i, addr, end, pointers[i+1]))
    return pointers


def read_layout(ram):
    """Mřížka světa 16 × 16 – každý bajt je číslo předlohy."""
    return ram.block(LAYOUT, COLS*ROWS)


# ------------------------------------------------- adresování obrazovky (originál)

def screen_addr(x, y):
    """`$B8AD`: X/Y v pixelech → adresa v obrazovce."""
    h = 0x40 | (((y >> 6) & 3) << 3) | (y & 7)
    l = ((x >> 3) & 0x1F) | (((y >> 3) & 7) << 5)
    return (h << 8) | l


def attr_addr(x, y):
    """`$B8DD` (`AttributeAddress`): X/Y v pixelech → adresa v atributech."""
    h = 0x58 | ((y >> 6) & 3)
    l = ((x >> 3) & 0x1F) | (((y >> 3) & 7) << 5)
    return (h << 8) | l


def pixel_row_below(hl):
    """`$B8CC` (`ScreenPos1PixelBelow`) – včetně přetečení mezi třetinami."""
    h, l = ((hl >> 8)+1) & 0xFF, hl & 0xFF
    if h & 7:
        return (h << 8) | l
    l = (l+0x20) & 0xFF
    if not l & 0xE0:            # ★ RET Z: přetečení do další třetiny, H zůstává
        return (h << 8) | l
    return (((h-8) & 0xFF) << 8) | l


# ------------------------------------------------------------------ kreslení

class Screen:
    """Obraz videopaměti 6912 B, aby šel výstup porovnat s originálem 1 : 1."""

    def __init__(self):
        self.data = bytearray(6912)

    def clear_play_area(self):
        """`ClearPlayArea` (`$BB5C`) + `ClearPlayArea_Attributes` (`$BB7C`).

        ★ Hrací plocha se před kreslením místnosti **vynuluje** (bitmapa od
        `$4040` dolů) a atributy od `$5840` do `$5AFF` se vyplní **`$40`** –
        bright, černý inkoust na černém papíře. Proto jsou v každé obrazovce
        originálu buňky s `$40` tam, kde žádná kulisa není."""
        for y in range(PLAY_TOP, 192):
            base = screen_addr(0, y)-0x4000
            self.data[base:base+32] = bytes(32)
        for i in range(6144+PANEL_ROWS*32, 6144+24*32):
            self.data[i] = 0x40
        return self

    def poke(self, addr, value):
        if 0x4000 <= addr < 0x5B00:
            self.data[addr-0x4000] = value
        else:                                   # pragma: no cover
            raise SystemExit('zapis mimo obrazovku: $%04X' % addr)

    def bitmap_rows(self):
        """Bitmapa hrací plochy lineárně po pixelových řádcích (5632 B)."""
        out = bytearray()
        for y in range(PLAY_TOP, 192):
            base = screen_addr(0, y)-0x4000
            out += self.data[base:base+32]
        return bytes(out)

    def attributes(self):
        """Atributy hrací plochy (704 B)."""
        return bytes(self.data[6144+PANEL_ROWS*32:6144+24*32])


def draw_item(screen, piece, x, y):
    """`DrawRoom_Process` (`$BC0B`) bajt po bajtu, včetně přetečení `INC L`."""
    hl = screen_addr(x, y)
    rows, width = piece.height, piece.width
    src = 0
    for _ in range(rows):
        h, l = hl >> 8, hl & 0xFF
        for _ in range(width):
            screen.poke((h << 8) | l, piece.pixels[src])
            src += 1
            l = (l+1) & 0xFF                    # ★ INC L: z konce řádku o 8 px níž
        l = (l-width) & 0xFF                    # LD A,L / SUB B / LD L,A
        hl = pixel_row_below((h << 8) | l)
    hl = attr_addr(x, y)
    src = 0
    for _ in range(piece.attr_height):
        l = hl & 0xFF
        for _ in range(piece.attr_width):
            screen.poke((hl & 0xFF00) | l, piece.attrs[src])
            src += 1
            l = (l+1) & 0xFF                    # ★ INC L: totéž v atributech
        hl = (hl+0x20) & 0xFFFF                 # ADD HL,$0020 (přeteče do H)


def draw_room(items, pieces_by_addr, screen=None):
    """`DrawRoom` (`$BBF7`): kusy kulisy v pořadí předlohy, jeden přes druhý."""
    screen = screen if screen is not None else Screen().clear_play_area()
    for gfx, x, y in items:
        piece = pieces_by_addr.get(gfx)
        if piece is None:
            raise SystemExit('predloha odkazuje na kus kulisy $%04X, ktery neni '
                             'v bloku $%04X-$%04X' % (gfx, SCENERY_FIRST, SCENERY_END))
        draw_item(screen, piece, x, y)
    return screen


# ------------------------------------------------------- kolize s kulisou (M3)

# ★ Kolize se **neptá na pixely, ale na obálku kusu kulisy**: `$B873` prochází
# týž seznam záznamů po čtyřech bajtech, ze kterého se místnost kreslí, a
# u každého kusu bere jeho výšku a šířku z hlavičky. Proto je zeď o něco
# větší, než co je nakreslené – a proto se dá průchodnost světa spočítat
# z týchž dat (`tools/mapwalk.py`), ne odhadovat z mezer v pixelech.
# `$B81C` k tomu přidá řešení po osách: co je zablokované ve dvou osách
# najednou, zkusí se ještě po jedné (viz `slide`).

def collides(ram, items, x, y, box_height=0x16, box_width=0x0E):
    """`$B873`: je obálka Sabremana na (x, y) v některém kusu kulisy?

    `x` je levý okraj obálky, `y` je **spodní** pixelová řádka (tak s ní
    pracuje i kreslení, `$BA7C` jde po řádcích vzhůru). `box_height` je `B`
    a `box_width` je `C` z `LD BC,$160E` na `$AF40`. Vrací záznam kusu kulisy,
    do kterého se naráží, nebo `None`.
    """
    for gfx, px, py in items:
        height = ram.byte(gfx)                  # LD A,(HL): výška v px
        width_bytes = ram.byte(gfx+1)           # LD H,(HL): šířka v bajtech
        width = rotate_left3(width_bytes) & 0xF8    # RLCA 3x / AND $F8
        dx = (x-px) & 0xFF                      # LD A,E / SUB (IX+$02)
        if dx < 0x80:                           # JP P
            if dx >= width:                     # CP H / JR NC
                continue
        elif (~dx & 0xFF) >= box_width:         # CPL / CP C / JR NC
            continue
        dy = (y-height-py) & 0xFF               # LD A,D / SUB L / SUB (IX+$03)
        if dy < 0x80:                           # JP P
            if dy < box_height:                 # CP B / RET C
                return (gfx, px, py)
        elif (~dy & 0xFF) < height:             # CPL / CP L / RET C
            return (gfx, px, py)
    return None


def rotate_left3(value):
    """`RLCA` třikrát – osmibitová rotace, ne posun."""
    for _ in range(3):
        value = ((value << 1) | (value >> 7)) & 0xFF
    return value


def slide(ram, items, old_x, old_y, x, y, box_height=0x16, box_width=0x0E):
    """`$B81C`: kam se Sabreman dostane, když je cíl v kulise.

    Nejdřív se zkusí celý posun; když nejde, zkusí se každá osa zvlášť
    a ta, která sama taky nejde, se vrátí na starou hodnotu. ★ Když jsou
    obě osy samy volné a zablokovaná je jen jejich kombinace, **originál
    nechá Sabremana v kulise** – tenhle vrtoch se reprodukuje, neopravuje.
    """
    if collides(ram, items, x, y, box_height, box_width) is None:
        return x, y
    if collides(ram, items, x, old_y, box_height, box_width) is not None:
        x = old_x
    if collides(ram, items, old_x, y, box_height, box_width) is not None:
        y = old_y
    return x, y


class World:
    """Runtime obraz načtený do všeho, co M2 potřebuje."""

    def __init__(self, path=RUNTIME):
        self.ram = Ram(path)
        self.pieces = read_scenery(self.ram)
        self.by_addr = {p.addr: p for p in self.pieces}
        self.room_table = read_room_table(self.ram)
        self.rooms = [read_room(self.ram, a)[0] for a in self.room_table]
        self.layout = read_layout(self.ram)
        used = set(self.layout)
        unknown = [t for t in used if t >= ROOM_TABLE_ENTRIES]
        if unknown:
            raise SystemExit('Layout odkazuje na predlohu %s, ale RoomTable ma jen %d'
                             % (['$%02X' % t for t in unknown], ROOM_TABLE_ENTRIES))
        # každý kus kulisy musí být někde použitý, jinak je špatně přečtený blok
        referenced = {g for items in self.rooms for g, _, _ in items}
        referenced |= {g for g, _, _ in read_room(self.ram, ROOM_MAIN_MENU)[0]}
        orphans = [p for p in self.pieces if p.addr not in referenced]
        if orphans:
            raise SystemExit('kusy kulisy %s nepouziva zadna predloha – blok je '
                             'precteny spatne'
                             % ['$%02X' % p.index for p in orphans])

    def render_template(self, template):
        return draw_room(self.rooms[template], self.by_addr)

    def render_room(self, column, row):
        return self.render_template(self.layout[row*COLS+column])


# ------------------------------------------------------------------- náhledy

PALETTE = [
    (0x00, 0x00, 0x00), (0x00, 0x00, 0xD7), (0xD7, 0x00, 0x00), (0xD7, 0x00, 0xD7),
    (0x00, 0xD7, 0x00), (0x00, 0xD7, 0xD7), (0xD7, 0xD7, 0x00), (0xD7, 0xD7, 0xD7),
    (0x00, 0x00, 0x00), (0x00, 0x00, 0xFF), (0xFF, 0x00, 0x00), (0xFF, 0x00, 0xFF),
    (0x00, 0xFF, 0x00), (0x00, 0xFF, 0xFF), (0xFF, 0xFF, 0x00), (0xFF, 0xFF, 0xFF),
]


def cells_to_rgb(pixels, attrs, width_bytes, height):
    """Bitmapa uložená lineárně po řádcích + atributy → řádky RGB pro PNG."""
    rows = []
    for y in range(height):
        row = bytearray()
        for col in range(width_bytes):
            bits = pixels[y*width_bytes+col]
            attr = attrs[(y >> 3)*width_bytes+col] if attrs else 0x47
            bright = 8 if attr & 0x40 else 0
            fg = PALETTE[(attr & 7)+bright]
            bg = PALETTE[((attr >> 3) & 7)+bright]
            for bit in range(7, -1, -1):
                row += bytes(fg if bits >> bit & 1 else bg)
        rows.append(bytes(row))
    return rows


def play_area_to_scr(bitmap, attrs):
    """Hrací plocha zpátky do obrazu 6912 B (panel černý) – kvůli náhledům."""
    scr = bytearray(6912)
    for row, y in enumerate(range(PLAY_TOP, 192)):
        base = screen_addr(0, y)-0x4000
        scr[base:base+32] = bitmap[row*32:row*32+32]
    scr[6144+PANEL_ROWS*32:6144+24*32] = attrs
    return bytes(scr)
