#!/usr/bin/env python3
"""Vytáhne z originálu **fyziku Sabremana** → `data/physics.json` (M3).

    PYTHONPATH=tools/vendor ./tools/dumpphysics.py [--png]

Nic tady není odhad ani „doladěno": každá hodnota se čte jako **operand
skutečné instrukce** v runtime obrazu hry (`build/sabrewulf-run.bin`,
`tools/mkruntime.py`) a okolní bajty té instrukce se kontrolují. Když se
obraz neshoduje, nástroj spadne, místo aby vydal číslo.

Rutiny, ze kterých se čte (runtime adresy, `sources/docs/disasm_notes.md` §14):

* `$AECF` `GamePlayEntry` a `$AEEF` `GamePlay_Start` – Sabreman pod kontrolou
  hráče (sprity `$10`–`$1F`): zrychlení, strop rychlosti, tlumení
* `$ADD0` `PlayerMovement` – Sabreman **s taseným mečem** (sprity `$20`–`$2F`):
  rychlost natvrdo, bez zrychlení a bez tlumení
* `$AFE8` posun pozice, `$B031` dělení rychlosti na pixely
* `$B81C`/`$B873` kolize s kulisou (obálky kusů kulisy, ne pixely)
* `$B12F`, `$B187`, `$B19F`, `$B1AB` přechody mezi obrazovkami
* `$B053` volba pózy z pohybu, `$AE4B` póza při seku mečem
* `$A985`, `$A9BE`, `$AA00`, `$AA0D`, `$AA27` smrt, výbuch a respawn

`--png` k tomu uloží náhledový list póz (`build/gfx/sabreman-poses.png`),
aby šlo očima zkontrolovat, že sprite ID odpovídají tomu, co se v běhu
naměřilo (`tools/tracephysics.py`).
"""
import argparse, base64, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

IMAGE = os.path.join(HERE, '..', 'build/sabrewulf-run.bin')
OUT = os.path.join(HERE, '..', 'data/physics.json')
SPRITES = os.path.join(HERE, '..', 'data/spriteframes.json')

# ---------------------------------------------------------------------------
# Konstanty: (jméno, adresa, bajty instrukce s None na místě operandu, komentář)
# None se přečte, ostatní bajty se ověří. Víc None = dvoubajtový operand.
# ---------------------------------------------------------------------------
CONSTANTS = [
    # --- chůze pod kontrolou hráče ($AEEF GamePlay_Start) ------------------
    ('walkAccel',        0xAF21, [0x06, None],
     'LD B,n — o kolik se za snímek změní rychlost ve stisknutém směru (1/16 px)'),
    ('speedCap',         0xAFCD, [0x06, None],
     'LD B,n — strop rychlosti v 1/16 px za snímek ($AFC1, běžný stav)'),
    ('speedCapSlow',     0xAFE0, [0x06, None],
     'LD B,n — strop, když je Sabreman v barvě `colourSlow` (orchidej, M4)'),
    ('speedCapFast',     0xAFE4, [0x06, None],
     'LD B,n — strop, když je Sabreman v barvě `colourFast` (orchidej, M4)'),
    ('colourSlow',       0xAFC5, [0xFE, None],
     'CP n — atribut, při kterém platí `speedCapSlow`'),
    ('colourFast',       0xAFC9, [0xFE, None],
     'CP n — atribut, při kterém platí `speedCapFast`'),
    ('speedDecay',       0xAF69, [0x06, None],
     'LD B,n — o kolik rychlost každý snímek klesá k nule ($B047)'),
    ('velocityMask',     0xB040, [0x0F, 0x0F, 0x0F, 0x0F, 0xE6, None],
     'RRCA 4x / AND n — posun v pixelech = rychlost/16 (zaokrouhleno k nule)'),
    ('colourNormal',     0xADEB, [0xFE, None],
     'CP n — barva Sabremana pod kontrolou hráče (bílá); jinak ovládání nefunguje'),
    # --- chůze s taseným mečem ($ADD0 PlayerMovement) ---------------------
    ('swordSpeed',       0xADF7, [0x7B, 0xC6, None],
     'ADD A,n — rychlost vpravo s taseným mečem, nastavená natvrdo (1/16 px)'),
    ('swordSpeedLeft',   0xADFF, [0x7B, 0xD6, None],
     'SUB n — a totéž vlevo'),
    ('swordSpeedUp',     0xAE07, [0x7A, 0xD6, None],
     'SUB n — svisle vzhůru (klávesa `keyUp`)'),
    ('swordSpeedDown',   0xAE0F, [0x7A, 0xC6, None],
     'ADD A,n — svisle dolů (klávesa `keyDown`)'),
    # --- kolizní obálka a šířka pro odchod z obrazovky --------------------
    ('boxHeight',        0xAF40, [0x01, 0x0E, None],
     'LD BC,nn — `B`: svislý rozměr obálky Sabremana v px ($B873 `CP B`)'),
    ('boxWidth',         0xAF41, [None, 0x16],
     'LD BC,nn — `C`: vodorovný rozměr obálky Sabremana v px ($B873 `CP C`)'),
    ('exitWidth',        0xAEFF, [0x3E, None],
     'LD A,n → $96AD — o kolik dřív než na x=256 se odchází vpravo'),
    ('exitWidthSword',   0xADCA, [0x3E, None],
     'LD A,n → $96AD — a totéž s taseným mečem ($ADBF)'),
    # --- meze hrací plochy a přechody mezi obrazovkami --------------------
    ('exitBottomY',      0xB014, [0xFE, None],
     'CP n — na téhle y a níž se odchází do obrazovky pod ($B12F)'),
    ('enterTopY',        0xB12F, [0x16, None],
     'LD D,n — a vstupuje se na téhle y'),
    ('exitTopY',         0xB02B, [0xFE, None],
     'CP n — pod touhle y se odchází do obrazovky nad ($B1AB)'),
    ('enterBottomY',     0xB1AB, [0x16, None],
     'LD D,n — a vstupuje se na téhle y'),
    ('enterLeftX',       0xB19F, [0x1E, None],
     'LD E,n — vstupní x při odchodu vpravo'),
    ('roomStepRow',      0xB131, [0xDD, 0x7E, 0x01, 0xC6, None],
     'ADD A,n — o kolik se změní číslo obrazovky při odchodu dolů (řádek +1)'),
    ('roomStepRowUp',    0xB1AD, [0xDD, 0x7E, 0x01, 0xD6, None],
     'SUB n — a při odchodu nahoru (řádek -1)'),
    ('roomColMask',      0xB193, [0xE6, None],
     'AND n — sloupec se mění jen v dolních čtyřech bitech (svět se nepřetáčí '
     'do dalšího řádku)'),
    ('redrawFirstSprite', 0xB148, [0xDD, 0x7E, 0x00, 0xD6, None],
     'SUB n — obrazovku překreslí jen entita se sprite ID od tohohle'),
    ('redrawSpriteCount', 0xB14D, [0xFE, None],
     'CP n — …a nejvýš o tolik výš, tedy jen Sabreman ($10–$2F)'),
    # --- pózy -------------------------------------------------------------
    ('poseBase',         0xB20E, [0xDD, 0x7E, 0x00, 0xE6, 0x07, 0xF6, None],
     'OR n — základ sprite ID Sabremana pod kontrolou hráče'),
    ('poseDirDown',      0xB061, [0xF6, None],
     'OR n — bity směru „dolů" ($B053)'),
    ('poseDirUp',        0xB09B, [0xF6, None],
     'OR n — bity směru „nahoru"'),
    ('poseDirRight',     0xB072, [0xF6, None],
     'OR n — bity směru „vpravo"; vlevo je nula (`poseDirMask` vynuluje)'),
    ('poseDirMask',      0xB070, [0xE6, None],
     'AND n — maska, která bity směru zahodí'),
    ('posePhaseMask',    0xB08E, [0xE6, None],
     'AND n — fáze chůze cyklí v dolních bitech sprite ID'),
    ('posePhaseEvery',   0xB07B, [0xE6, None],
     'AND n — fáze se mění, když je `FRAMES` ($5C78) dělitelné n+1'),
    ('swordPoseBase',    0xADC3, [0xE6, 0x0F, 0xF6, None],
     'OR n — základ sprite ID s taseným mečem ($ADBF)'),
    ('swordPoseFace',    0xAE57, [0xF6, None],
     'OR n — bit „čelem vpravo" při seku ($AE4B)'),
    ('swordPoseFaceMask', 0xAE76, [0xE6, None],
     'AND n — a jeho zhasnutí, když jde Sabreman vlevo'),
    ('swordPhaseMask',   0xAE68, [0xE6, None],
     'AND n — fáze seku se bere z `Rand8` ($9695), ne z počítadla'),
    ('swordPhaseEvery',  0xAE5F, [0xE6, None],
     'AND n — a mění se, když je `FRAMES` dělitelné n+1'),
    ('swordPhaseKeep',   0xAE6C, [0xE6, None],
     'AND n — které bity sprite ID fáze seku nechá být'),
    # --- smrt, výbuch a respawn -------------------------------------------
    ('deathCounter',     0xA985, [0xDD, 0x36, 0x02, None],
     'LD (IX+$02),n — počítadlo, na které se nastaví odlet po zabití'),
    ('deathSpriteRight', 0xA995, [0xDD, 0x36, 0x00, None],
     'LD (IX+$00),n — sprite odletu doprava'),
    ('deathSpeedRight',  0xA999, [0xDD, 0x36, 0x06, None],
     'LD (IX+$06),n — a jeho vodorovná rychlost (celé pixely, ne 1/16)'),
    ('deathSpriteLeft',  0xA9A0, [0xDD, 0x36, 0x00, None],
     'LD (IX+$00),n — sprite odletu doleva (stav $02)'),
    ('deathSpeedLeft',   0xA9A4, [0xDD, 0x36, 0x06, None],
     'LD (IX+$06),n — a jeho vodorovná rychlost'),
    ('deathBoxHeight',   0xA9CF, [0x01, 0x0F, None],
     'LD BC,nn — `B`: svislý rozměr obálky při odletu ($A9BE)'),
    ('deathBoxWidth',    0xA9D0, [None, 0x17],
     'LD BC,nn — `C`: vodorovný rozměr obálky při odletu'),
    ('deathMinX',        0xA9DB, [0xFE, None],
     'CP n — pod touhle x odlet skončí výbuchem'),
    ('deathMaxX',        0xA9DF, [0xFE, None],
     'CP n — a nad touhle taky'),
    ('deathMinY',        0xA9E4, [0xFE, None],
     'CP n — a pod touhle y'),
    ('deathMaxY',        0xA9E8, [0xFE, None],
     'CP n — a nad touhle y'),
    ('explodeCounter',   0xAA03, [0xDD, 0x36, 0x02, None],
     'LD (IX+$02),n — počítadlo výbuchu, odkud se odpočítává k nule ($AA00)'),
    ('explodeSecond',    0xAA1E, [0xFE, None],
     'CP n — při téhle hodnotě se sprite výbuchu posune na druhou fázi'),
    ('respawnSpriteMask', 0xAA3E, [0xE6, None],
     'AND n — z čeho zůstane po respawnu fáze pózy'),
    ('respawnSpriteBase', 0xAA40, [0xF6, None],
     'OR n — a jaký je základ sprite ID po respawnu'),
    ('respawnColour',    0xAA45, [0xDD, 0x36, 0x05, None],
     'LD (IX+$05),n — barva Sabremana po respawnu'),
    ('fireballDelay',    0xAA52, [0x3E, None],
     'LD A,n → $96B4 — ★ **odpočet do ohnivé koule**, ne nedotknutelnost po '
     'respawnu, jak M3 hádal: jediná rutina, která `$96B4` čte, je `$9ABC`, '
     'a co na nule udělá, je položit na obrazovku ohnivou kouli (M5, §17). '
     'Stejné číslo píše `$B148` po každé změně obrazovky a `$B1BF` na začátku '
     'kola'),
    ('startLives',       0xB21E, [0x3E, None],
     'LD A,n → $96BD — životy při startu; první Sabreman jeden hned ubere (§9)'),
    ('gameDelay',        0xB1C4, [0x3E, None],
     'LD A,n → $96B5 — kolik snímků po startu hry ovládání ještě nereaguje'),
    # --- účinky orchidejí, které se dějí Sabremanovi v kroku (M4) ---------
    # Tytéž adresy čte i `dumpentities.py`, protože pět barev a co dělají je
    # nález M4; kód, který je provádí, je ale krok Sabremana, tedy tady.
    ('colourReverse',    0xAF14, [0xFE, None],
     'CP n — purpurová orchidej: obrácené ovládání ($AF11)'),
    ('reverseMask',      0xAF19, [0xEE, None],
     'XOR n — a takhle se obrací: čtyři bity směru naráz'),
    ('colourYellow',     0xAEF8, [0xFE, None],
     'CP n — žlutá orchidej: Sabreman sedne a nehýbe se ($AE8F)'),
    ('yellowPoseMask',   0xAE92, [0xE6, None],
     'AND n — ze sprite ID zůstane jen bit „čelem vpravo"'),
    ('yellowPoseBase',   0xAE94, [0xF6, None],
     'OR n — a základ pózy sedícího Sabremana ($43 vlevo, $47 vpravo)'),
    ('yellowTime',       0xAE99, [0x3E, None],
     'LD A,n → $96B0 — jak dlouho sedí; nastavuje se při každém kroku, takže '
     'odpočet začne až sprite přejde na obsluhu sezení ($A61B)'),
    ('standUpMask',      0xA626, [0xE6, None],
     'AND n — ze sprite ID sedícího zůstane fáze ($A61B)'),
    ('standUpBase',      0xA628, [0xF6, None],
     'OR n — a přidá se základ chůze; Sabreman vstane'),
    ('effectTickEvery',  0xAE7D, [0xE6, None],
     'AND n — `OrchidEffectTimer` ($96B0) se ubírá, když je `FRAMES` '
     'dělitelné n+1 ($AE7A)'),
    ('effectEndColour',  0xAE8A, [0xDD, 0x36, 0x05, None],
     'LD (IX+$05),n — barva Sabremana, až účinek dojde'),
    ('effectFlashBelow', 0xAF84, [0xFE, None],
     'CP n — pod touhle hodnotou časovače Sabreman bliká ($AF7D)'),
    ('effectFlashMask',  0xAF89, [0xE6, None],
     'AND n — fáze blikání z dolních bitů časovače'),
    ('effectFlashHalf',  0xAF8B, [0xFE, None],
     'CP n — v první polovině fáze se kreslí bílý, v druhé barevný'),
    ('effectBeepMask',   0xAF8F, [0xE6, None],
     'AND n — a při každém n+1 se pípne ($BEC6)'),
    ('colourImmune',     0xAB39, [0xD6, None],
     'SUB n — kontakt s entitou zabíjí **jen bílého** Sabremana ($AB36), '
     'takže pod účinkem orchideje je nedotknutelný'),
    ('poemBitOpcode',    0xA19F, [0xDD, 0xCB, 0x0B, None],
     'BIT n,(IX+$0B) — bit, který po sebrání kusu amuletu ukáže sloku '
     'básně ($A18C -> $A207); nastavuje ho M4, ukazuje ho M6. V datech je '
     'z opkódu odvozená maska `poemBit`'),
    # --- dosah meče (a stejný test i zabíjí Sabremana; M5) ----------------
    ('hitReachDown',     0xAB0E, [0x21, 0x0C, None],
     'LD HL,nn — `H`: svislý dosah kontaktu s entitou ($AB01)'),
    ('hitReachRight',    0xAB0F, [None, 0x0F],
     'LD HL,nn — `L`: dosah vpravo bez taseného meče'),
    ('hitReachRightSword', 0xAB16, [None, 0x0F],
     'LD HL,nn — `L`: dosah vpravo s taseným mečem ($AB15)'),
]

# klávesy: (jméno, adresa `BIT n,C`, komentář) – bit v C z `HandlerControls`
KEYS = [
    ('keyLeft',  0xAF28, 0, 'BIT 0,C — půlřádek $FBFE bit 0 = Q'),
    ('keyRight', 0xAF23, 1, 'BIT 1,C — půlřádek $FBFE bit 1 = W'),
    ('keyUp',    0xAF34, 2, 'BIT 2,C — půlřádek $FBFE bit 2 = E'),
    ('keyDown',  0xAF2F, 3, 'BIT 3,C — půlřádek $FBFE bit 3 = R'),
    ('keyFire',  0xAF5F, 4, 'BIT 4,A — půlřádek $FBFE bit 4 = T'),
]
KEY_PATTERN = {0: 0x41, 1: 0x49, 2: 0x51, 3: 0x59}      # BIT n,C
KEY_PATTERN_A = {4: 0x67}                               # BIT 4,A

# pózy: (stav, první sprite ID, kolik, poznámka)
POSE_GROUPS = [
    ('walkLeft',   0x10, 4, 'chůze vlevo; $10 je i stání vlevo (bity směru 00)'),
    ('walkRight',  0x14, 4, 'chůze vpravo (bit 2)'),
    ('walkUp',     0x18, 4, 'chůze vzhůru, tedy k horní hraně obrazovky (bit 3)'),
    ('walkDown',   0x1C, 4, 'chůze dolů (bity 2 a 3)'),
    ('swordLeft',  0x20, 8, 'sek mečem vlevo; fáze je náhodná (`Rand8`), ne cyklická'),
    ('swordRight', 0x28, 8, 'sek mečem vpravo (bit 3)'),
    ('deathRight', 0x40, 4, 'odlet po zabití doprava a výbuch ($40 odlet, $41–$43 výbuch)'),
    ('deathLeft',  0x44, 4, 'odlet doleva a výbuch'),
]

START_RECORD = 0xAC77           # předloha „game status bufferu" ($AC6B)
RECORD_LEN = 12                 # 144 B / 12 záznamů ($AC6B: LD BC,$0090)


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


def signed(value):
    return value-256 if value >= 128 else value


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--image', default=IMAGE)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--png', action='store_true', help='náhledový list póz')
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

    # rychlosti s mečem jsou znaménkové – v datech je jen velikost operandu
    for name in ('swordSpeedLeft', 'swordSpeedUp'):
        values[name] = -values[name]

    # klávesy: ověří se, že se testují ty bity, které tvrdí `HandlerControls`
    for name, addr, bit, note in KEYS:
        pattern = ([0xCB, KEY_PATTERN[bit]] if bit in KEY_PATTERN
                   else [0xCB, KEY_PATTERN_A[bit]])
        extract(ram, name, addr, pattern, note)
        checked += 1
        values[name] = bit
        notes[name] = {'address': '$%04X' % addr, 'note': note}

    # ★ směr svislých kláves: `keyUp` ubírá y, `keyDown` přidává, a y roste
    #   dolů (`$B8AD` bere y jako pixelový řádek od horního okraje). Proti
    #   originálním instrukcím, kde je E dolů a R nahoru, je to **obráceně**
    #   – změřeno na běhu (`tools/tracephysics.py`, scénář `walkUp`/`walkDown`).
    values['upDecreasesY'] = True
    # ★ `BIT n,(IX+$0B)` je jediná instrukce, kde je operand v opkódu, ne za
    # ním: `CB 40 + 8*n + 6`. Z přečteného opkódu se maska odvodí, aby v datech
    # nebylo číslo 7 opsané ručně.
    opcode = values.pop('poemBitOpcode')
    notes['poemBit'] = notes.pop('poemBitOpcode')
    if (opcode & 0xC7) != 0x46:
        raise SystemExit('$A1A2 neni opkod BIT n,(IX+$0B), je $%02X' % opcode)
    values['poemBit'] = 1 << ((opcode-0x46) >> 3)

    # posun pozice: RRCA 4x v $B031 je deleni sestnacti, k nule
    values['velocityShift'] = 4
    notes['velocityShift'] = {'address': '$B031, $B040',
                              'note': 'RRCA 4x / AND $0F — posun v pixelech '
                                      '= rychlost/16, zaokrouhleno k nule'}

    # ★ tabulka vstupních x při odchodu dolů: `$B143 LD BC,$6036` a
    # `LD E,(HL)` – 48 bajtů indexovaných **předlohou nové obrazovky**, tedy
    # kde v té předloze je průchod horní hranou. Bez toho by Sabreman při
    # přechodu dolů přišel do kulisy (svislé chodby jsou 2 px široké).
    if peek(ram, 0xB13C, 12) != bytes((0x01, 0x66, 0x60, 0x09, 0x6E, 0x26, 0x00,
                                       0x01, 0x36, 0x60, 0x09, 0x5E)):
        raise SystemExit('$B13C neni LD BC,$6066 / ADD HL,BC / LD L,(HL) / '
                         'LD H,$00 / LD BC,$6036 / ADD HL,BC / LD E,(HL)')
    checked += 1
    enter_top_x = list(peek(ram, 0x6036, 48))
    if peek(ram, 0x6036+48, 2) != peek(ram, 0x6066, 2):
        raise SystemExit('tabulka na $6036 nekonci tam, kde zacina Layout')

    # startovní záznam Sabremana (`$AC6B` kopíruje 144 B od `$AC77` na `$9702`)
    if peek(ram, 0xAC6B, 9) != bytes((0x21, 0x77, 0xAC, 0x11, 0x02, 0x97,
                                      0x01, 0x90, 0x00)):
        raise SystemExit('$AC6B neni LD HL,$AC77 / LD DE,$9702 / LD BC,$0090')
    checked += 1
    record = list(peek(ram, START_RECORD, RECORD_LEN))
    start = {
        'sprite': record[0], 'room': record[1], 'state': record[2],
        'x': record[3], 'y': record[4], 'colour': record[5],
        'dx': signed(record[6]), 'dy': signed(record[7]),
        'column': record[1] & 0x0F, 'row': record[1] >> 4,
        'bytes': ''.join('%02X' % b for b in record),
    }

    # sprite ID -> snímek z tabulky $BF84 (data/spriteframes.json z M2)
    sprites = json.load(open(SPRITES))
    frame_index = {f['address']: i for i, f in enumerate(sprites['frameData'])}
    poses = []
    for name, first, count, note in POSE_GROUPS:
        frames = []
        for t in range(first, first+count):
            entry = sprites['sprites'][t]
            frames.append({'sprite': '$%02X' % t, 'frame': frame_index[entry['frame']],
                           'address': entry['frame'], 'name': entry['name']})
        poses.append({'state': name, 'firstSprite': first, 'sprites': count,
                      'note': note, 'frames': frames})

    out = {
        'note': ('M3: fyzika Sabremana vytazena z originalu (tools/dumpphysics.py). '
                 'Kazda hodnota je operand skutecne instrukce v '
                 'build/sabrewulf-run.bin, adresa je v "source". Popis rutin: '
                 'sources/docs/disasm_notes.md 14.'),
        'stepRate': 'jeden herni krok = jeden snimek ULA (50,08 Hz)',
        'record': {
            'length': RECORD_LEN,
            'address': '$9702',
            'fields': ['+0 sprite ID', '+1 obrazovka (radek<<4 | sloupec)',
                       '+2 stav (0 = ziv, jinak odpocet smrti)', '+3 x',
                       '+4 y (SPODNI radka spritu)', '+5 atribut',
                       '+6 dx v 1/16 px', '+7 dy v 1/16 px', '+8..+11 nepouzite'],
        },
        'start': start,
        'enterTopX': enter_top_x,
        'enterTopXNote': ('$6036-$6065, 48 bajtu indexovanych predlohou: x, '
                          'na ktere se vstupuje horni hranou obrazovky '
                          '($B12F). Tabulka konci presne tam, kde zacina '
                          'Layout ($6066), a zacina hned za textem copyrightu; '
                          'prvni tri polozky jsou nuly, protoze predlohy '
                          '$00-$02 jsou rohy sveta, do kterych se zespodu '
                          'nevstupuje.'),
        'values': values,
        'source': notes,
        'poses': poses,
    }
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1, sort_keys=False)
        f.write('\n')
    print('zkontrolovano instrukci: %d' % checked)
    print('konstant do %s: %d' % (os.path.relpath(args.out), len(values)))
    for key in ('walkAccel', 'speedCap', 'speedDecay', 'swordSpeed', 'boxWidth',
                'boxHeight', 'exitWidth', 'exitBottomY', 'enterTopY', 'exitTopY',
                'enterBottomY', 'deathCounter', 'explodeCounter', 'startLives'):
        print('  %-16s %s' % (key, hex(values[key])))
    print('vstupni x pri prechodu dolu ($6036): %s'
          % ' '.join('%02X' % b for b in enter_top_x))
    print('startovni zaznam: %s (obrazovka $%02X = sloupec %d, radek %d)'
          % (start['bytes'], start['room'], start['column'], start['row']))

    if args.png:
        write_poses_png(sprites, poses)


def write_poses_png(sprites, poses):
    """Náhledový list póz – kontrola očima, že sprite ID jsou ta pravá."""
    from scr2png import write_png
    frames = sprites['frameData']
    cols = max(len(g['frames']) for g in poses)
    used = [frames[i['frame']] for g in poses for i in g['frames']
            if i['frame'] is not None]
    cell_w = max(f['widthPixels'] for f in used)+4
    cell_h = max(f['height'] for f in used)+4
    width, height = cols*cell_w, len(poses)*cell_h
    img = bytearray(width*height*3)
    for row, group in enumerate(poses):
        for col, item in enumerate(group['frames']):
            if item['frame'] is None:
                continue
            frame = frames[item['frame']]
            bitmap = base64.b64decode(frame['bitmap'])
            stride = frame['width']
            for y in range(frame['height']):
                for x in range(frame['widthPixels']):
                    byte = bitmap[y*stride + (x >> 3)]
                    if byte >> (7-(x & 7)) & 1:
                        px = ((row*cell_h+2+y)*width + col*cell_w+2+x)*3
                        img[px:px+3] = b'\xff\xff\xff'
    path = os.path.join(HERE, '..', 'build/gfx/sabreman-poses.png')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = [bytes(img[y*width*3:(y+1)*width*3]) for y in range(height)]
    write_png(path, rows, width)
    print('nahled poz: %s' % os.path.relpath(path))


if __name__ == '__main__':
    main()
