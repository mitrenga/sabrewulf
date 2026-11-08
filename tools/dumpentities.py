#!/usr/bin/env python3
"""Vytáhne z originálu **svět**: entity, orchideje, amulet a předměty → `data/entities.json` (M4).

    PYTHONPATH=tools/vendor ./tools/dumpentities.py [--print]

Stejné pravidlo jako u `dumpphysics.py`: **nic tady není odhad**. Každá hodnota
se čte jako **operand skutečné instrukce** v runtime obrazu hry
(`build/sabrewulf-run.bin`, `tools/mkruntime.py`), okolní bajty té instrukce se
kontrolují, a u každé tabulky se navíc kontroluje, že **končí přesně tam, kde
začíná něco jiného, co je nezávisle pojmenované**. Když se obraz neshoduje,
nástroj spadne, místo aby vydal číslo.

Rutiny, ze kterých se čte (runtime adresy, `sources/docs/disasm_notes.md` §16):

* `$99F0`/`$99FE` – délka záznamu entity a **konec tabulky entit** (`$982E`),
  z toho vyjde, že slotů je 25
* `$AC6B`/`$AC77` – předloha „game status bufferu": **12 nesmrtelných entit**
  včetně Sabremana
* `$A763` `$A79F` `$A7D4` `$A7E8` – orchidej: spawn do `$97DA`, uložení stavu
  zpátky do `TableOrchidTypes` a obě tabulky (pozice `$D6A6`, typy `$A7F8`)
* `$A680` `$A6D4` `$A70D` `$A737` – kvetení orchideje a její sebrání
* `$AE7A` `$AE8F` `$A61B` `$AEEF` `$AF11` `$AF55` `$AF7D` `$AB36` – **účinky
  pěti orchidejí**: doba trvání, žlutá (sezení), purpurová (obrácené ovládání),
  červená/modrozelená (rychlost), bílá (nic) a nedotknutelnost
* `$A33B` `$A356` `$A39C` `$A2BD` – předměty: dva sloty na obrazovku, mapa
  `$DDEC` (512 B) a její generátor
* `$A312` `$A305` `$A2F8` – sebrání předmětu, **extra život a strop 9**
* `$A255` `$A29D` `$A1AB` – amulet: **osm hotových sad po čtyřech obrazovkách**,
  blikání, sebrání a `$7500` bodů
* `$9D41` `$ABB6` – **domorodci ukazující k amuletu**: pravidlo přímky, žlutá
  a tón podle vzdálenosti
* `$9D23` `$9CC6` – `VisitedRooms` a **procento navštívených obrazovek**

`--print` k tomu vypíše souhrn na terminál.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

IMAGE = os.path.join(HERE, '..', 'build/sabrewulf-run.bin')
OUT = os.path.join(HERE, '..', 'data/entities.json')
SPRITES = os.path.join(HERE, '..', 'data/spriteframes.json')
WORLD = os.path.join(HERE, '..', 'data/world.json')

TEMPLATES = 48                  # 48 předloh místností (M2)
ROOMS = 256                     # 16 x 16 obrazovek (M0)

# ---------------------------------------------------------------------------
# Konstanty: (jméno, adresa, bajty instrukce s None na místě operandu, komentář)
# None se přečte, ostatní bajty se ověří. Dvě None = dvoubajtový operand.
# ---------------------------------------------------------------------------
CONSTANTS = [
    # --- tabulka entit ($99D0 smyčka, $99F0 posun na další záznam) ---------
    ('recordLength',      0x99F0, [0x11, None, 0x00],
     'LD DE,nn — o kolik se `IX` posune na další entitu, tedy délka záznamu'),
    ('entityTableEnd',    0x99FE, [0x11, None, None],
     'LD DE,nn — adresa, na které tabulka entit končí ($99FE/$9A02 `SBC HL,DE`)'),
    ('entityFirstPassEnd', 0x9A18, [0x11, None, None],
     'LD DE,nn — konec prvního průchodu smyčkou: v něm se obslouží **jen** '
     'Sabreman, ostatní entity až v druhém (§14)'),
    ('nastieData',        0x9A54, [0xDD, 0x21, None, None],
     'LD IX,nn — začátek `NastieData`, tedy zvířat, která se dosazují za běhu (M5)'),
    ('orchidData',        0xA766, [0xCD, 0xE8, 0xA7, 0x11, None, None],
     'LD DE,nn — záznam, do kterého se orchidej nové obrazovky spawnuje'),
    ('objectData',        0xA33B, [0x11, None, None],
     'LD DE,nn — záznam prvního ze dvou předmětů obrazovky'),
    ('objectData2',       0xA34A, [0x11, None, None],
     'LD DE,nn — a druhého ($A34A), tedy o `recordLength` dál'),
    ('amuletData',        0xA255, [0xDD, 0x21, None, None],
     'LD IX,nn — první ze čtyř kusů amuletu'),
    # --- orchidej: tabulky --------------------------------------------------
    ('orchidTypeTable',   0xA7F4, [None, None, 0x09, 0xC9],
     'LD BC,nn — `TableOrchidTypes` ($A7E8 `HandlerOrchidType`), index je '
     '**předloha**, dva bajty na předlohu'),
    ('orchidPositionTable', 0xA7E2, [0x01, None, None],
     'LD BC,nn — `TableOrchidPositions` ($A7D4 `HandlerOrchidPosition`), '
     'x a y na předlohu'),
    ('orchidColourTable', 0xA6F3, [0x01, None, None],
     'LD BC,nn — `OrchidColour` ($A6EB), 16 atributů, index `FRAMES` & $0F'),
    # --- orchidej: spawn ($A763) --------------------------------------------
    ('orchidSpriteMask',  0xA770, [0xE6, None],
     'AND n — z prvního bajtu stavu se vezme fáze kvetení'),
    ('orchidSpriteBase',  0xA772, [0xF6, None],
     'OR n — a přidá se základ sprite ID orchideje'),
    ('orchidStateMask',   0xA77C, [0xE6, None],
     'AND n — bit „zavírá se" jde do `+2` záznamu'),
    ('orchidColourMask',  0xA78B, [0xE6, None],
     'AND n — z druhého bajtu stavu se vezme barva'),
    ('orchidColourBase',  0xA78D, [0xF6, None],
     'OR n — a přidá se `BRIGHT` (atribut orchideje)'),
    ('orchidTimerLowMask', 0xA792, [0xE6, None],
     'AND n — zbytek druhého bajtu je dolní bajt časovače kvetení'),
    ('orchidTimerHighMask', 0xA79B, [0xE6, None],
     'AND n — horní půlbajt prvního bajtu je horní bajt časovače'),
    # --- orchidej: kvetení ($A680, $A6D4, $A70D) ----------------------------
    ('orchidPhaseEvery',  0xA6D7, [0xE6, None],
     'AND n — fáze kvetení se posune, když je `$9693` dělitelné n+1'),
    ('orchidPhaseMask',   0xA6E7, [0xE6, None],
     'AND n — které bity sprite ID jsou fáze kvetení'),
    ('orchidColourIndexMask', 0xA6EE, [0xE6, None],
     'AND n — index do `OrchidColour`: `FRAMES` ($5C78) & n'),
    ('orchidStateToggle', 0xA71D, [0xEE, None],
     'XOR n — přepnutí mezi „otevírá se" a „zavírá se"'),
    ('orchidDormantMask', 0xA727, [0xE6, None],
     'AND n — jak dlouho orchidej spí: `FRAMES` & n …'),
    ('orchidDormantBase', 0xA729, [0xC6, None],
     'ADD A,n — …plus n; horní bajt časovače zůstává nula'),
    ('orchidOpenWait',    0xA731, [0x21, None, None],
     'LD HL,nn — jak dlouho zůstane rozkvetlá (a jen tehdy se dá sebrat)'),
    ('orchidPickHeight',  0xA73E, [0x01, 0x0F, None],
     'LD BC,nn — `B`: svislý dosah kontaktu s orchidejí ($AB01)'),
    ('orchidPickWidth',   0xA73F, [None, 0x0F],
     'LD BC,nn — `C`: a vodorovný'),
    ('orchidEffectTime',  0xA745, [0x3E, None],
     'LD A,n → `OrchidEffectTimer` ($96B0) — na tolik se účinek nastaví'),
    ('orchidHarmless',    0xA757, [0xFE, None],
     'CP n — s touhle barvou se účinek hned vynuluje: **bílá orchidej nedělá nic**'),
    # --- orchidej: účinek a jeho odpočet ($AE7A, $AF7D) ---------------------
    ('effectTickEvery',   0xAE7D, [0xE6, None],
     'AND n — `OrchidEffectTimer` se ubírá, když je `FRAMES` dělitelné n+1'),
    ('effectEndColour',   0xAE8A, [0xDD, 0x36, 0x05, None],
     'LD (IX+$05),n — barva Sabremana, až účinek dojde (bílá = normální stav)'),
    ('effectFlashBelow',  0xAF84, [0xFE, None],
     'CP n — pod touhle hodnotou časovače Sabreman **bliká** (varování, že končí)'),
    ('effectFlashMask',   0xAF89, [0xE6, None],
     'AND n — fáze blikání z dolních bitů časovače'),
    ('effectFlashHalf',   0xAF8B, [0xFE, None],
     'CP n — v první polovině fáze se kreslí bílý, v druhé barevný'),
    ('effectBeepMask',    0xAF8F, [0xE6, None],
     'AND n — a při každém n+1 se pípne ($BEC6)'),
    # --- orchidej: pět barev a co dělají ------------------------------------
    ('colourSlow',        0xAFC5, [0xFE, None],
     'CP n — červená: strop rychlosti je `speedCapSlow` ($AFC1)'),
    ('colourFast',        0xAFC9, [0xFE, None],
     'CP n — modrozelená: strop je `speedCapFast`'),
    ('colourReverse',     0xAF14, [0xFE, None],
     'CP n — purpurová: **obrácené ovládání** ($AF11)'),
    ('reverseMask',       0xAF19, [0xEE, None],
     'XOR n — a takhle se obrací: čtyři bity směru naráz'),
    ('colourYellow',      0xAEF8, [0xFE, None],
     'CP n — žlutá: Sabreman **sedne a nehýbe se** ($AE8F)'),
    ('yellowPoseMask',    0xAE92, [0xE6, None],
     'AND n — ze sprite ID zůstane jen bit „čelem vpravo"'),
    ('yellowPoseBase',    0xAE94, [0xF6, None],
     'OR n — a základ pózy sedícího Sabremana ($43 vlevo, $47 vpravo)'),
    ('yellowTime',        0xAE99, [0x3E, None],
     'LD A,n → `$96B0` — jak dlouho sedí; nastavuje se **znovu při každém '
     'kroku**, takže odpočet začne až sprite přejde na obsluhu sezení ($A61B)'),
    ('standUpMask',       0xA626, [0xE6, None],
     'AND n — ze sprite ID sedícího zůstane fáze'),
    ('standUpBase',       0xA628, [0xF6, None],
     'OR n — a přidá se základ chůze; Sabreman vstane'),
    ('colourNormal',      0xAF58, [0xFE, None],
     'CP n — **meč se dá tasit jen v bílém stavu**: pod účinkem orchideje ne'),
    ('colourImmune',      0xAB39, [0xD6, None],
     'SUB n — a naopak: kontakt s entitou zabíjí **jen bílého** Sabremana '
     '($AB36), takže pod účinkem orchideje je nedotknutelný'),
    # --- kontakt s entitou ($AB01; tytéž tři dosahy má i data/physics.json,
    #     protože týmž obdélníkem se Sabreman zabíjí – §14) ------------------
    ('hitFirstSprite',    0xAB09, [0xD6, None],
     'SUB n — kontakt se testuje jen pro sprite ID od n výš…'),
    ('hitSpriteCount',    0xAB0B, [0xFE, None],
     'CP n — …a nejvýš o tolik dál, tedy jen pro Sabremana ($10–$2F)'),
    ('hitSwordFrom',      0xAB11, [0xFE, None],
     'CP n — od téhle hodnoty (už po odečtení) platí dosah s taseným mečem'),
    ('hitReachDown',      0xAB0E, [0x21, 0x0C, None],
     'LD HL,nn — `H`: dosah dolů, tedy když je Sabreman **pod** entitou'),
    ('hitReachRight',     0xAB0F, [None, 0x0F],
     'LD HL,nn — `L`: dosah vpravo, tedy když je **vlevo** od entity'),
    ('hitReachRightSword', 0xAB16, [None, 0x0F],
     'LD HL,nn — `L`: a totéž s taseným mečem ($AB15), skoro trojnásobek'),
    # --- předměty: mapa a rozmístění ($A33B, $A356, $A39C) -----------------
    ('objectMap',         0xA3A2, [0x01, None, None],
     'LD BC,nn — mapa předmětů, **dva bajty na obrazovku** ($A39C `ADD HL,HL`)'),
    ('objectLocationTable', 0xA37C, [0x11, None, None],
     'LD DE,nn — `ObjectLocation`: **čtyři pozice na předlohu**'),
    ('objectTypeMask',    0xA358, [0xE6, None],
     'AND n — dolní bity bajtu mapy jsou druh předmětu'),
    ('objectSpriteBase',  0xA35A, [0xC6, None],
     'ADD A,n — a přidá se základ sprite ID předmětů'),
    ('objectSlotMask',    0xA376, [0xE6, None],
     'AND n — horní dva bity bajtu mapy vyberou jednu ze čtyř pozic '
     '(`RLCA` 3x je posune na bity 1-2, tedy krok po dvou bajtech)'),
    ('objectColourTable', 0xA38E, [0x21, None, None],
     'LD HL,nn — barva předmětu podle druhu, 16 atributů'),
    ('objectPickHeight',  0xA312, [0x01, 0x0C, None],
     'LD BC,nn — `B`: svislý dosah sebrání předmětu'),
    ('objectPickWidth',   0xA313, [None, 0x0C],
     'LD BC,nn — `C`: a vodorovný'),
    ('objectScore',       0xA332, [0x01, None, None],
     'LD BC,nn → `AddPointsToScore` ($B5A9) — **BCD**, tedy body za předmět; '
     'je to jedno číslo pro všechny druhy'),
    # --- předměty: generátor mapy ($A2BD) ----------------------------------
    ('objectMapDest',     0xA2BD, [0x21, None, None],
     'LD HL,nn — kam se mapa předmětů generuje (a `$B248` ji pak umí prohodit '
     'mezi dvěma hráči)'),
    ('objectMapSeedMask', 0xA2C7, [0xE6, None],
     'AND n — horní bajt zdroje: `$9693` (počítadlo snímků) & n, tedy '
     '**$0000-$1FFF: ROM Spectra**'),
    ('objectMapCount',    0xA2CA, [0x01, None, None],
     'LD BC,nn — kolik bajtů mapy se vygeneruje (2 x 256 obrazovek)'),
    ('objectMapThreshold', 0xA2CF, [0xFE, None],
     'CP n — bajt zdroje pod n znamená „na téhle obrazovce předmět je"'),
    ('objectMapTypeMask', 0xA2E6, [0xE6, None],
     'AND n — druh předmětu z `Rand8` ($9695)'),
    ('objectMapSlotMask', 0xA2E0, [0xE6, None],
     'AND n — a pozice z dolního bajtu počítadla smyčky (`RRCA` 2x)'),
    ('objectMapCopy',     0xB24B, [0x11, None, None],
     'LD DE,nn — mapa druhého hráče ($B235 `ChangePlayer` obě prohodí)'),
    # --- extra život ($A305, $A2F8) ----------------------------------------
    ('lifeMax',           0xA2FB, [0xFE, None],
     'CP n — **strop životů**: `RET NC` nad ním život nepřidá (uzavřená otázka '
     'ZADANI §7)'),
    ('lifePickHeight',    0xA305, [0x01, 0x0C, None],
     'LD BC,nn — `B`: dosah sebrání předmětu „život"'),
    ('lifePickWidth',     0xA306, [None, 0x0C],
     'LD BC,nn — `C`: a vodorovný'),
    # --- amulet ($A255 PlaceAmuletPieces) ----------------------------------
    ('amuletSetMask',     0xA25C, [0xE6, None],
     'AND n — `Rand8` & n vybere jednu z hotových sad rozmístění'),
    ('amuletSetTable',    0xA263, [0x01, None, None],
     'LD BC,nn — `Initialisation_Amulet`: sady po čtyřech obrazovkách'),
    ('amuletPieces',      0xA268, [0x06, None],
     'LD B,n — kolik kusů amuletu se rozmístí'),
    ('amuletSpriteBase',  0xA26C, [0xC6, None],
     'ADD A,n — sprite ID kusu je n + číslo kusu, tedy $93 … $90'),
    ('amuletLocationTable', 0xA283, [0x01, None, None],
     'LD BC,nn — pozice v obrazovce se bere z **`ObjectLocation`, slot 0**'),
    ('amuletColour',      0xA290, [0xDD, 0x36, 0x05, None],
     'LD (IX+$05),n — atribut kusu amuletu při položení'),
    # --- amulet: blikání a sebrání ($A1AB) ---------------------------------
    ('amuletFlashEvery',  0xA1B8, [0xE6, None],
     'AND n — barva se mění, když je `$9693` dělitelné n+1'),
    ('amuletFlashMask',   0xA1C0, [0xE6, None],
     'AND n — barva cyklí přes n+1 hodnot'),
    ('amuletFlashBase',   0xA1C2, [0xF6, None],
     'OR n — a začíná tady ($44 zelená … $47 bílá)'),
    ('amuletPickHeight',  0xA1B2, [0x01, 0x0C, None],
     'LD BC,nn — `B`: svislý dosah sebrání kusu amuletu'),
    ('amuletPickWidth',   0xA1B3, [None, 0x0C],
     'LD BC,nn — `C`: a vodorovný'),
    ('amuletBitsAddress', 0xA1CD, [0x3A, None, None],
     'LD A,(nn) — kde se drží, které kusy amuletu už hráč má; je to **`+$0B` '
     'Sabremanova záznamu** ($9702+11)'),
    ('amuletPoemBit',     0xA1D0, [0xF6, None],
     'OR n — a bit 7 téhož bajtu znamená „ukaž sloku básně" ($A18C, M6)'),
    ('amuletFirstSprite', 0xA1D6, [0xD6, None],
     'SUB n — sprite ID prvního kusu; rozdíl vybírá bit v `amuletBits`'),
    ('amuletScore',       0xA1ED, [0x01, None, None],
     'LD BC,nn → `AddPointsToScore` — **BCD**, body za kus amuletu'),
    # --- domorodci ukazující k amuletu ($9D41, $ABB6) ----------------------
    ('pointStride',       0x9D41, [0x11, None, 0x00],
     'LD DE,nn — o kolik se posunout na další kus amuletu (11 + `INC HL`)'),
    ('pointPieces',       0x9D47, [0x06, None],
     'LD B,n — kolik kusů se zkouší'),
    ('pointColumnMask',   0x9D4F, [0xE6, None],
     'AND n — sloupec obrazovky z čísla obrazovky'),
    ('pointRowMask',      0x9D5B, [0xE6, None],
     'AND n — a řádek'),
    ('pointRange',        0x9D78, [0xFE, None],
     'CP n — domorodec „ukazuje", když je v témže sloupci světa a jeho x se '
     'od x kusu liší o méně než n (a obdobně po řádcích, `$9D8C`)'),
    ('pointRangeRow',     0x9D8C, [0xFE, None],
     'CP n — totéž pro řádek a y'),
    ('pointColour',       0xABCE, [0xDD, 0x36, 0x05, None],
     'LD (IX+$05),n — a takhle se přitom nakreslí: **zežloutne** ($ABB6)'),
    # --- VisitedRooms a procento ($9D23, $9CC6) ----------------------------
    ('visitedRooms',      0x9D3A, [0x01, None, None],
     'LD BC,nn — `VisitedRooms`, jeden bit na obrazovku'),
    ('visitedByteMask',   0x9D2A, [0xE6, None],
     'AND n — index bajtu je `obrazovka >> 3` & n, tedy `řádek*2 + sloupec>>3`'),
    ('visitedBitMask',    0x9D33, [0xE6, None],
     'AND n — a bit je `sloupec & 7`; `$9D37` si tím **přepíše vlastní '
     'instrukci** `SET 0,(HL)` na `SET n,(HL)`'),
    ('percentBits',       0x9CC9, [0x01, None, None],
     'LD BC,nn — `B`: bitů v bajtu, `C`: kolik bajtů `VisitedRooms` má'),
    ('percentAmuletBits', 0x9CDF, [0x06, None],
     'LD B,n — ★ a k obrazovkám se přičtou **kusy amuletu**, takže do procenta '
     'vstupují taky'),
    ('percentStep',       0x9CE7, [0x01, None, None],
     'LD BC,nn — 100/260 v pevné řádové čárce: každý přenos přes 16 bitů '
     'znamená jedno procento'),
    ('percentRound',      0x9CFC, [0x01, None, None],
     'LD BC,nn — a nakonec se přičte tohle, aby 260 dalo přesně 100'),
    ('percentPosition',   0x9D0E, [0x21, None, None],
     'LD HL,nn — kam se procento tiskne (adresa bitmapy obrazovky)'),
]

# skupiny záznamů v tabulce entit; adresy se ověřují proti `CONSTANTS`
GROUPS = [
    ('immortal', 0x9702, 'nesmrtelné entity a Sabreman – jediná skupina, '
     'kterou hra při startu kopíruje hotovou z $AC77'),
    ('nastie', 0x9792, 'zvířata, která se dosazují za běhu podle obrazovky (M5)'),
    ('orchid', 0x97DA, 'orchidej té obrazovky, na které Sabreman je'),
    ('object', 0x97E6, 'dva předměty té obrazovky'),
    ('amulet', 0x97FE, 'čtyři kusy amuletu – ty leží ve světě celou hru'),
]

START_TABLE = 0xAC77            # předloha „game status bufferu" ($AC6B)


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


def check(condition, message):
    if not condition:
        raise SystemExit(message)


def bcd(value):
    """Trojbajtové BCD skóre jako číslo (skóre hry je BCD, §9)."""
    return int('%06X' % value)


def percent_table(step, round_add, total):
    """`PrintRoomsVisited` ($9CC6) – procento, jak ho počítá originál.

    Není to dělení: hra `total`-krát přičte `step` do šestnáctibitového `HL`
    a každý přenos zvýší **BCD** počítadlo procent. `step` je 100/260 v pevné
    řádové čárce, `round_add` je oprava, aby 260 dalo přesně 100.
    """
    out = []
    for count in range(total+1):
        hl, percent = 0, 0
        for _ in range(count):
            hl += step
            if hl > 0xFFFF:
                hl &= 0xFFFF
                percent += 1
        hl += round_add
        if hl > 0xFFFF:
            percent += 1
        out.append(percent)
    return out


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

    # skóre je BCD, takže operand $0150 znamená 150 bodů – pro remake se
    # ukládá i v desítkové podobě, aby si ho nemusel převádět sám
    values['objectScoreDecimal'] = bcd(values['objectScore'])
    notes['objectScoreDecimal'] = dict(notes['objectScore'])
    values['amuletScoreDecimal'] = bcd(values['amuletScore'])
    notes['amuletScoreDecimal'] = dict(notes['amuletScore'])

    sprites = json.load(open(SPRITES))
    world = json.load(open(WORLD))
    frame_at = {}
    for entry in sprites['sprites']:
        frame_at[int(entry['id'][1:], 16)] = entry

    def sprite_name(sprite):
        entry = frame_at.get(sprite)
        return entry['name'] if entry else None

    # -- tabulka entit: 25 slotů, a to není odhad ---------------------------
    # `$99F0` posouvá `IX` o 12 a `$9A02` porovnává s `$982E`; z toho vyjde
    # počet slotů. Skupiny se pak musí sejít bajt na bajt.
    reclen = values['recordLength']
    table_end = values['entityTableEnd']
    first = GROUPS[0][1]
    check((table_end-first) % reclen == 0,
          'tabulka entit ($%04X-$%04X) neni delitelna %d'
          % (first, table_end, reclen))
    slots = (table_end-first)//reclen
    groups, at = [], first
    for index, (name, addr, note) in enumerate(GROUPS):
        check(addr == at, 'skupina %s ma zacit na $%04X, disassembly rika $%04X'
              % (name, at, addr))
        end = GROUPS[index+1][1] if index+1 < len(GROUPS) else table_end
        count = (end-addr)//reclen
        check((end-addr) % reclen == 0,
              'skupina %s neni delitelna delkou zaznamu' % name)
        groups.append({'name': name, 'address': '$%04X' % addr,
                       'firstSlot': (addr-first)//reclen, 'count': count,
                       'note': note})
        at = end
    # adresy, které se čtou jako operandy, musí sedět na skupiny
    check(values['nastieData'] == 0x9792, 'NastieData nesedi')
    check(values['orchidData'] == 0x97DA, 'OrchidData nesedi')
    check(values['objectData'] == 0x97E6, 'ObjectData nesedi')
    check(values['objectData2'] == values['objectData']+reclen,
          'druhy predmet nelezi o zaznam dal')
    check(values['amuletData'] == 0x97FE, 'AmuletData nesedi')
    check(values['entityFirstPassEnd'] == first+reclen,
          'prvni pruchod smyckou nekonci za Sabremanem')
    check(values['amuletBitsAddress'] == first+11,
          'bity amuletu nelezi v +$0B Sabremanova zaznamu')

    # -- 12 nesmrtelných entit z $AC77 --------------------------------------
    if peek(ram, 0xAC6B, 9) != bytes((0x21, 0x77, 0xAC, 0x11, 0x02, 0x97,
                                      0x01, 0x90, 0x00)):
        raise SystemExit('$AC6B neni LD HL,$AC77 / LD DE,$9702 / LD BC,$0090')
    checked += 1
    immortal_count = groups[0]['count']
    check(immortal_count*reclen == 0x90,
          '$AC6B kopiruje %d B, skupina immortal ma %d zaznamu'
          % (0x90, immortal_count))
    immortal = []
    for i in range(immortal_count):
        rec = list(peek(ram, START_TABLE+i*reclen, reclen))
        immortal.append({
            'slot': i, 'sprite': rec[0], 'name': sprite_name(rec[0]),
            'room': rec[1], 'column': rec[1] & 0x0F, 'row': rec[1] >> 4,
            'state': rec[2], 'x': rec[3], 'y': rec[4], 'colour': rec[5],
            'dx': signed(rec[6]), 'dy': signed(rec[7]),
            'bytes': ''.join('%02X' % b for b in rec),
        })

    # -- orchidej ------------------------------------------------------------
    # `TableOrchidTypes` končí přesně tam, kde začíná obsluha spritů $50-$57,
    # na kterou ukazuje `JumpTable` – tím je délka 48 x 2 dokázaná, ne odhadnutá.
    orchid_types_at = values['orchidTypeTable']
    orchid_types_end = orchid_types_at+TEMPLATES*2
    jump_table = 0x9B3E
    check(peek(ram, 0x99DE, 3) == bytes((0x01, jump_table & 0xFF, jump_table >> 8)),
          '$99DE neni LD BC,$9B3E (JumpTable)')
    checked += 1
    handler_50 = peek(ram, jump_table+2*0x50, 2)
    check(handler_50[0] | handler_50[1] << 8 == orchid_types_end,
          'TableOrchidTypes ($%04X + 48*2 = $%04X) nekonci tam, kde zacina '
          'obsluha spritu $50 ($%04X)'
          % (orchid_types_at, orchid_types_end,
             handler_50[0] | handler_50[1] << 8))
    orchid_types = [list(peek(ram, orchid_types_at+t*2, 2)) for t in range(TEMPLATES)]

    # `TableOrchidPositions` končí přesně tam, kde začíná snímek spritu $0D
    orchid_pos_at = values['orchidPositionTable']
    orchid_pos_end = orchid_pos_at+TEMPLATES*2
    check(int(frame_at[0x0D]['frame'][1:], 16) == orchid_pos_end,
          'TableOrchidPositions ($%04X + 48*2 = $%04X) nekonci tam, kde zacina '
          'snimek spritu $0D (%s)'
          % (orchid_pos_at, orchid_pos_end, frame_at[0x0D]['frame']))
    orchid_positions = [list(peek(ram, orchid_pos_at+t*2, 2)) for t in range(TEMPLATES)]

    # `OrchidColour` končí přesně tam, kde začíná rutina $A70D
    orchid_colour_at = values['orchidColourTable']
    check(orchid_colour_at+16 == 0xA70D,
          'OrchidColour ($%04X + 16) nekonci na $A70D' % orchid_colour_at)
    orchid_colours = list(peek(ram, orchid_colour_at, 16))

    # jak se z dvou bajtů stavu poskládá záznam orchideje ($A763)
    orchid_spawn = []
    for t in range(TEMPLATES):
        low, high = orchid_types[t]
        x, y = orchid_positions[t]
        orchid_spawn.append({
            'template': '$%02X' % t,
            'sprite': (low & values['orchidSpriteMask']) | values['orchidSpriteBase'],
            'state': low & values['orchidStateMask'],
            'x': x, 'y': y,
            'colour': (high & values['orchidColourMask']) | values['orchidColourBase'],
            'timer': ((high & values['orchidTimerLowMask'])
                      | ((low >> 4) & values['orchidTimerHighMask']) << 8),
        })

    # ★ pět barev a co dělají – všechno operandy skutečných instrukcí výše
    effects = [
        {'colour': values['colourSlow'], 'name': 'slow',
         'note': 'strop rychlosti `speedCapSlow` ($20 = 2 px za krok) misto '
                 '`speedCap` ($30); $AFC5'},
        {'colour': values['colourReverse'], 'name': 'reverse',
         'note': 'obracene ovladani: $AF19 udela `XOR $0F` na ctyrech bitech '
                 'smeru, takze vlevo je vpravo a nahoru dolu'},
        {'colour': values['colourFast'], 'name': 'fast',
         'note': 'strop rychlosti `speedCapFast` ($40 = 4 px za krok); $AFC9'},
        {'colour': values['colourYellow'], 'name': 'sit',
         'note': '★ Sabreman sedne ($43/$47) a nehybe se; obsluha sezeni '
                 '($A61B) odpocitava `yellowTime` a pak ho postavi. O zlute '
                 'orchideji dobove tipy mlci – tohle je odpoved'},
        {'colour': values['effectEndColour'], 'name': 'none',
         'note': 'bila: $A75C vynuluje `OrchidEffectTimer`, takze bila '
                 'orchidej **nedela nic**. Je to i normalni barva Sabremana'},
    ]

    # -- předměty ------------------------------------------------------------
    # `ObjectLocation` končí přesně tam, kde začíná mapa předmětů, na kterou
    # ukazuje `$A39C` – 48 předloh x 4 pozice x 2 bajty = 384 B.
    object_loc_at = values['objectLocationTable']
    check(object_loc_at+TEMPLATES*4*2 == values['objectMap'],
          'ObjectLocation ($%04X + 48*4*2 = $%04X) nekonci tam, kde zacina mapa '
          'predmetu ($%04X)'
          % (object_loc_at, object_loc_at+TEMPLATES*8, values['objectMap']))
    object_locations = []
    for t in range(TEMPLATES):
        slotsxy = []
        for s in range(4):
            x, y = peek(ram, object_loc_at+t*8+s*2, 2)
            slotsxy.append([x, y])
        object_locations.append(slotsxy)
    check(values['objectMapCount'] == ROOMS*2,
          'generator mapy predmetu neresi 2 bajty na 256 obrazovek')
    check(values['objectMapCopy'] == values['objectMap']+values['objectMapCount'],
          'mapa druheho hrace nelezi hned za mapou prvniho')

    # barvy předmětů končí přesně tam, kde začíná rutina $A3B7
    object_colour_at = values['objectColourTable']
    check(object_colour_at+16 == 0xA3B7,
          'tabulka barev predmetu ($%04X + 16) nekonci na $A3B7' % object_colour_at)
    object_colours = list(peek(ram, object_colour_at, 16))

    # druhy předmětů: sprite ID a jméno snímku (data/spriteframes.json, M2).
    # ★ Který druh je „život", se nečte z obrázku, ale z `JumpTable`: jediné
    # sprite ID předmětů, které nejde na $A312, jde na $A305 – a to je ten,
    # co přidává život.
    object_handlers = {}
    for t in range(16):
        sprite = values['objectSpriteBase']+t
        addr = peek(ram, jump_table+2*sprite, 2)
        object_handlers[t] = addr[0] | addr[1] << 8
    common = max(set(object_handlers.values()), key=list(object_handlers.values()).count)
    life_types = [t for t, h in object_handlers.items() if h != common]
    check(len(life_types) == 1,
          'ceka se jediny druh predmetu s jinou obsluhou, je jich %d' % len(life_types))
    life_type = life_types[0]
    check(object_handlers[life_type] == 0xA305,
          'obsluha predmetu „zivot" ma byt $A305, je $%04X' % object_handlers[life_type])
    checked += 1
    objects = []
    for t in range(16):
        sprite = values['objectSpriteBase']+t
        objects.append({'type': t, 'sprite': sprite, 'name': sprite_name(sprite),
                        'colour': object_colours[t],
                        'handler': '$%04X' % object_handlers[t],
                        'extraLife': t == life_type})

    # -- amulet --------------------------------------------------------------
    # sady rozmístění končí přesně tam, kde začíná generátor mapy předmětů,
    # na který `$B232` skáče – 8 sad x 4 obrazovky.
    sets_at = values['amuletSetTable']
    set_count = values['amuletSetMask']+1
    pieces = values['amuletPieces']
    check(sets_at+set_count*pieces == 0xA2BD and
          peek(ram, 0xB232, 3) == bytes((0xC3, 0xBD, 0xA2)),
          'tabulka sad amuletu ($%04X + %d*%d) nekonci tam, kde zacina rutina '
          '$A2BD, na kterou $B232 skace' % (sets_at, set_count, pieces))
    checked += 1
    check(values['amuletLocationTable'] == object_loc_at,
          'amulet se neklade do `ObjectLocation`')
    amulet_sets = []
    for s in range(set_count):
        rooms = list(peek(ram, sets_at+s*pieces, pieces))
        entry = []
        for i, room in enumerate(rooms):
            # $A26C: sprite = (kolik kusů zbývá) + base, tedy $93, $92, $91, $90
            sprite = (values['amuletSpriteBase']+pieces-i) & 0xFF
            template = int(world['templates'][room >> 4][(room & 0x0F)*2:
                                                         (room & 0x0F)*2+2], 16)
            x, y = object_locations[template][0]
            entry.append({'piece': i, 'sprite': sprite, 'name': sprite_name(sprite),
                          'room': room, 'column': room & 0x0F, 'row': room >> 4,
                          'template': '$%02X' % template, 'x': x, 'y': y,
                          'colour': values['amuletColour']})
        amulet_sets.append({'set': s, 'rooms': rooms, 'pieces': entry})
    amulet_flash = [(values['amuletFlashBase'] | ((i+1) & values['amuletFlashMask']))
                    for i in range(values['amuletFlashMask']+1)]

    # -- VisitedRooms a procento --------------------------------------------
    check(values['visitedRooms'] == int(world['visitedRoomsAddress'][1:], 16),
          'VisitedRooms nesedi s data/world.json')
    percent_bits = values['percentBits']
    visited_bytes, visited_bits = percent_bits & 0xFF, percent_bits >> 8
    check(visited_bytes*visited_bits == ROOMS,
          '$9CC9 necte %d bitu VisitedRooms' % ROOMS)
    percent_total = ROOMS+values['percentAmuletBits']
    percents = percent_table(values['percentStep'], values['percentRound'],
                             percent_total)
    check(percents[percent_total] == 100 and percents[0] == 0,
          'procento pro %d obrazovek+kusu neni 100 (je %d)'
          % (percent_total, percents[percent_total]))

    out = {
        'note': ('M4: svet Sabre Wulf vytazeny z originalu '
                 '(tools/dumpentities.py). Kazda hodnota je operand skutecne '
                 'instrukce v build/sabrewulf-run.bin, adresa je v "source"; '
                 'u kazde tabulky se navic kontroluje, ze konci presne tam, '
                 'kde zacina neco jineho, co je pojmenovane nezavisle. '
                 'Popis rutin: sources/docs/disasm_notes.md 16.'),
        'table': {
            'address': '$%04X' % first,
            'end': '$%04X' % table_end,
            'recordLength': reclen,
            'slots': slots,
            'groups': groups,
            'note': ('$99F0 posouva IX o recordLength a $9A02 porovnava s end, '
                     'takze slotu je (end-address)/recordLength. Prvni pruchod '
                     'smyckou obslouzi jen Sabremana ($9A18), ostatni entity '
                     'az druhy.'),
        },
        'immortal': immortal,
        'immortalNote': ('12 zaznamu, ktere $AC6B kopiruje z $AC77 na $9702 '
                         'pri kazdem startu hrace. Slot 0 je Sabreman; zbytek '
                         'jsou entity, ktere ve svete lezi celou hru a nedaji '
                         'se zabit – nosorozci, tri domorodci, Sabre Wulf, '
                         'hroch a straz brany na obrazovce $88. Jejich chovani '
                         'je M5, tady je jen rozmisteni.'),
        'orchid': {
            'typeTable': '$%04X' % orchid_types_at,
            'positionTable': '$%04X' % orchid_pos_at,
            'colourTable': '$%04X' % orchid_colour_at,
            'types': orchid_types,
            'positions': orchid_positions,
            'colours': orchid_colours,
            'spawn': orchid_spawn,
            'effects': effects,
            'note': ('★ Stav orchideje se drzi **na predlohu, ne na obrazovku**: '
                     '$A7E8 indexuje TableOrchidTypes cislem predlohy z Layout, '
                     'takze vsech 21 obrazovek predlohy $11 ma jednu orchidej. '
                     'Dva bajty na predlohu: faze kvetení, bit "zavira se", '
                     'barva a 12bitovy casovac. $A79F je pri odchodu z '
                     'obrazovky zapise zpatky, $A763 je pri prichodu rozbali '
                     'do zaznamu na $97DA.'),
            'bloomNote': ('Cyklus ($A680, $A6D4, $A70D): casovac tikaci dolu '
                          'kazdy krok; na nule se kazdy druhy snimek posune '
                          'faze. Otevirani jde $48 -> $4F, na $4F se prepne '
                          'stav a casovac na orchidOpenWait – jen v tom okne '
                          'se orchidej da sebrat ($A737 zada sprite $4F). '
                          'Zavirani jde $4F -> $48 a na $48 se **vybere nova '
                          'barva** z OrchidColour[FRAMES & 15] a casovac na '
                          'orchidDormantBase + FRAMES & orchidDormantMask.'),
        },
        'objects': {
            'mapAddress': '$%04X' % values['objectMap'],
            'mapAddress2UP': '$%04X' % values['objectMapCopy'],
            'locationTable': '$%04X' % object_loc_at,
            'colourTable': '$%04X' % object_colour_at,
            'slotsPerRoom': 2,
            'locations': object_locations,
            'types': objects,
            'note': ('Dva bajty mapy na obrazovku, tedy dva predmety. V bajtu '
                     'jsou dolni ctyri bity druh a horni dva bity ktera ze '
                     'ctyr pozic predlohy ($A356, $A39C). Nula = zadny '
                     'predmet. Sebrani vynuluje bajt mapy, takze predmet je '
                     'sebrany navzdy – a kazdy hraci ma vlastni mapu ($B248 '
                     'je prohazuje).'),
            'mapNote': ('★ Mapa se **generuje pri startu hrace** ($A2BD) a '
                        'zdroj "nahody" je **ROM Spectra**: DE = ($9693 & $1F)'
                        '*256 + FRAMES, tedy adresa v $0000-$20FF. Bajt ROM '
                        'pod objectMapThreshold znamena "tady predmet je", '
                        'druh se vezme z Rand8 a pozice z dolniho bajtu '
                        'pocitadla smycky. Runtime obraz ROM neobsahuje '
                        '($4000-$FFFF), takze tohle je jedine misto M4, ktere '
                        'remake nema jak zopakovat bajt na bajt – stejne jako '
                        'faze seku mecem v M3.'),
        },
        'amulet': {
            'setTable': '$%04X' % sets_at,
            'sets': amulet_sets,
            'flashColours': amulet_flash,
            'bitsAddress': '$%04X' % values['amuletBitsAddress'],
            'note': ('★ Rozmisteni amuletu **neni nahodne mistem, jen volbou '
                     'sady**: $A25C vezme Rand8 & 7 a tim vybere jednu z osmi '
                     'hotovych sad po ctyrech obrazovkach ($A29D). Pozice v '
                     'obrazovce je pak dana predlohou – slot 0 tabulky '
                     'ObjectLocation. Sebrani nastavi bit v +$0B Sabremanova '
                     'zaznamu a k tomu bit 7, ktery znamena "ukaz sloku '
                     'basne" ($A18C -> $A207, M6).'),
            'pointNote': ('★ Domorodci ukazuji k zakopanemu kusu: $9D41 projde '
                          'ctyri kusy a hlasi "v primce", kdyz je entita ve '
                          'tremze sloupci sveta a jeji x se od x kusu lisi o '
                          'mene nez pointRange, nebo v temze radku a y. '
                          '$ABB6 pak domorodce nakresli **zlute** a pipne '
                          'tonem, jehoz vyska je ta vzdalenost ($BF3D).'),
        },
        'visited': {
            'address': '$%04X' % values['visitedRooms'],
            'bytes': visited_bytes,
            'bits': visited_bits,
            'total': percent_total,
            'percent': percents,
            'note': ('$9D23 VisitRoom: bajt = radek*2 + sloupec>>3, bit = '
                     'sloupec & 7 (rutina si prepisuje vlastni instrukci SET). '
                     'Vola se z $B148, tedy pri kazdem prechodu obrazovky, '
                     'ktery udela Sabreman.'),
            'percentNote': ('$9CC6 PrintRoomsVisited: secte 256 bitu '
                            'VisitedRooms **a ctyri bity amuletu**, takze '
                            'celek je %d. Procento nepocita delenim: '
                            '%d-krat pricte percentStep do 16 bitu a kazdy '
                            'prenos je jedno procento (BCD), nakonec pricte '
                            'percentRound. "percent" je ta tabulka '
                            'predpocitana, aby ji remake nemusel pocitat '
                            'stejnou smyckou.' % (percent_total, percent_total)),
        },
        'values': values,
        'source': notes,
    }
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1, sort_keys=False)
        f.write('\n')

    print('zkontrolovano instrukci a tabulek: %d' % checked)
    print('konstant do %s: %d' % (os.path.relpath(args.out), len(values)))
    print('tabulka entit: $%04X-$%04X, %d slotu po %d B'
          % (first, table_end, slots, reclen))
    for group in groups:
        print('  %-9s %s  slot %2d, %d zaznamu'
              % (group['name'], group['address'], group['firstSlot'],
                 group['count']))
    print('orchidej: %d predloh, barvy %s'
          % (TEMPLATES, ' '.join('%02X' % c for c in orchid_colours)))
    print('  ucinky: %s' % ', '.join('$%02X %s' % (e['colour'], e['name'])
                                     for e in effects))
    print('  ucinek trva $%02X pulsnimku, zluta $%02X'
          % (values['orchidEffectTime'], values['yellowTime']))
    print('predmety: %d druhu, %d bodu za kus, extra zivot je druh %d (%s), '
          'strop zivotu %d'
          % (len(objects), bcd(values['objectScore']), life_type,
             objects[life_type]['name'], values['lifeMax']))
    print('amulet: %d sad po %d kusech, %d bodu za kus'
          % (set_count, pieces, bcd(values['amuletScore'])))
    for entry in amulet_sets:
        print('  sada %d: %s' % (entry['set'],
              ' '.join('$%02X (%d,%d)' % (p['room'], p['column'], p['row'])
                       for p in entry['pieces'])))
    print('procento: %d obrazovek + %d kusu amuletu = %d, tedy 1 kus = %d %%'
          % (ROOMS, values['percentAmuletBits'], percent_total, percents[1]))

    if args.show:
        print('\npredlohy: orchidej (typ, pozice) a pozice predmetu')
        for t in range(TEMPLATES):
            spawn = orchid_spawn[t]
            print('  $%02X  orchidej sprite $%02X barva $%02X na %3d,%3d   '
                  'predmety %s'
                  % (t, spawn['sprite'], spawn['colour'], spawn['x'], spawn['y'],
                     ' '.join('%3d,%3d' % (p[0], p[1]) for p in object_locations[t])))
        print('\nnesmrtelne entity:')
        for e in immortal:
            print('  slot %2d  sprite $%02X %-24s obrazovka $%02X (%2d,%2d)  '
                  'x=%3d y=%3d attr $%02X  dx=%d dy=%d'
                  % (e['slot'], e['sprite'], e['name'] or '-', e['room'],
                     e['column'], e['row'], e['x'], e['y'], e['colour'],
                     e['dx'], e['dy']))


if __name__ == '__main__':
    main()
