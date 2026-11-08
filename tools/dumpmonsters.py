#!/usr/bin/env python3
"""Vytáhne z originálu **nepřátele**: zvířata, Sabre Wulfa, strážce brány, ohnivou kouli a bodování → `data/monsters.json` (M5).

    PYTHONPATH=tools/vendor ./tools/dumpmonsters.py [--print]

Stejné pravidlo jako u `dumpentities.py`: **nic tady není odhad**. Každá hodnota
se čte jako **operand skutečné instrukce** v runtime obrazu hry
(`build/sabrewulf-run.bin`, `tools/mkruntime.py`), okolní bajty té instrukce se
kontrolují, a u každé tabulky se navíc kontroluje, že **končí přesně tam, kde
začíná něco jiného, co je nezávisle pojmenované**. Když se obraz neshoduje,
nástroj spadne, místo aby vydal číslo.

Klíč k celému M5 je `JumpTable` (`$9B3E`): hra pro každou entitu skočí na
adresu `JumpTable[sprite ID]`, takže **kdo je co, se nehádá – je to v tabulce**.
Tabulka má 196 položek a končí přesně na `PrintRoomsVisited` (`$9CC6`), což je
kontrola jejího konce.

Rutiny, ze kterých se čte (runtime adresy, `sources/docs/disasm_notes.md` §17):

* `$9B3E` – `JumpTable`, 196 sprite ID → obsluha; z ní vyjde **rozdělení na
  zničitelné a nezničitelné**
* `$9A3C` `$9A68` `$9B0D` `$9AB8` – dosazování zvířat: **šest slotů, tři na
  obrazovku**, poloha z `Rand8`/`FRAMES` a barva ze čtyř
* `$A3C5` `$A3E0` `$A41A` `$A42A` `$A43B` – zhmotnění a výbuch; ★ `SpriteReference`
  je **šestnáct druhů a vybírá se podle toho, kolik kusů amuletu hráč má**
* `$A44B` `$A5CD` `$A54F` `$A4D7` – pohyb zvířat: odraz od okrajů, náhodný směr
  a **naháněč**, který zrychluje k Sabremanovi
* `$A4A6` `$A4B3` `$B5A9` – výbuch a **body za nepřítele**
* `$AB36` `$AB3D` – kdo koho zabije: **meč rozhoduje stranou, ze které Sabreman
  přichází**
* `$9ABC` `$9AE9` `$9D91` `$9E0E` `$9E53` `$9E64` `$A4A1` `$B164` – **ohnivá
  koule**: kdy se objeví, jak se drží Sabremana a jak dlouho žije
* `$AD07` `$AD69` `$AD86` – nosorožec, `$9E72` `$9EB3` – hroch, `$AB74` `$ABDE`
  – domorodec: nezničitelní, jen **zahánění**
* `$A630` – putování nesmrtelných entit za Sabremanovým řádkem
* `$A858` `$A8B2` `$A8F5` `$A964` `$A922` – **Sabre Wulf**: běží po řádku,
  mečem se dá odehnat a po každém odehnání je **rychlejší**
* `$9F16` – **strážce brány**: bez amuletu zabíjí, s amuletem uhne
* `$B1B7` `$B21E` `$B205` `$B235` `$AA27` – dva hráči, `GameDelayTimer`
  a **ta chyba**, kterou zmiňují dobové recenze

`--print` k tomu vypíše souhrn na terminál.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

IMAGE = os.path.join(HERE, '..', 'build/sabrewulf-run.bin')
OUT = os.path.join(HERE, '..', 'data/monsters.json')
SPRITES = os.path.join(HERE, '..', 'data/spriteframes.json')
ENTITIES = os.path.join(HERE, '..', 'data/entities.json')

# ---------------------------------------------------------------------------
# Konstanty: (jméno, adresa, bajty instrukce s None na místě operandu, komentář)
# None se přečte, ostatní bajty se ověří. Dvě None = dvoubajtový operand.
# ---------------------------------------------------------------------------
CONSTANTS = [
    # --- JumpTable: kdo je co ----------------------------------------------
    ('jumpTable',         0x99DE, [0x01, None, None],
     'LD BC,nn — `JumpTable` ($99DE): obsluha entity je `JumpTable[sprite ID]`, '
     'takže **rozdělení entit není odhad, ale tabulka**'),
    ('jumpTableEnd',      0x9CC6, [0x11, 0x00, 0x00],
     'a končí přesně tady, na `PrintRoomsVisited` ($9CC6) – kontrola konce tabulky'),

    # --- dosazování zvířat ($9A3C, $9A68, $9B0D) ---------------------------
    ('nastieSlots',       0x9A5B, [0x06, None],
     'LD B,n — kolik slotů `NastieData` má, tedy **kolik zvířat může být ve '
     'světě naráz**'),
    ('nastieStride',      0x9A58, [0x11, None, 0x00],
     'LD DE,nn — a o kolik se mezi nimi skáče (délka záznamu)'),
    ('spawnDelayAddress', 0x9A41, [0x3A, None, None],
     'LD A,(nn) — prodleva, než se začnou dosazovat zvířata ($96B1)'),
    ('spawnDelay',        0xAA4D, [0x3E, None, 0x32, 0xB1, 0x96],
     'LD A,n → $96B1 — na tolik průchodů se dosazování zastaví po smrti '
     '($AA4D) i na začátku kola ($B1BA)'),
    ('spawnDelayStart',   0xB1BA, [0x3E, None, 0x32, 0xB1, 0x96],
     'LD A,n → $96B1 — a totéž na začátku kola; musí to být totéž číslo'),
    ('aliveFirstSprite',  0x9A4F, [0xD6, None],
     'SUB n — zvířata se dosazují, jen když je Sabremanovo sprite ID od n výš…'),
    ('aliveSpriteCount',  0x9A51, [0xFE, None],
     '…a nejvýš o tolik dál ($10–$2F), tedy když je **naživu a na nohou**'),
    ('nastiePerRoomAddress', 0x9A85, [0x3A, None, None],
     'LD A,(nn) — kolik zvířat smí být na obrazovce ($96BE); víc se nedosadí'),
    ('nastiePerRoom',     0xB223, [0x3E, None, 0x32, 0xBE, 0x96],
     'LD A,n → $96BE — ★ a je to **tři** ($B21E, na začátku každého kola)'),
    ('spawnRandMask',     0x9B10, [0xE6, None],
     'AND n — x nového zvířete: `Rand8` ($9695) & n…'),
    ('spawnBase',         0x9B12, [0xC6, None],
     'ADD A,n — …plus n; y stejně z `FRAMES` ($9B18)'),
    ('spawnFramesMask',   0x9B1B, [0xE6, None],
     'AND n — a y z `FRAMES` ($5C78) & n'),
    ('spawnBoxHeight',    0x9B29, [0x01, 0x17, None],
     'LD BC,nn — `B`: obálka, kterou se hlídá, že zvíře nevznikne na Sabremanovi'),
    ('spawnBoxWidth',     0x9B29, [0x01, None, 0x17],
     'LD BC,nn — `C`: a její šířka; totéž pak jde do `$B81C` proti kulise'),
    ('spawnColourTable',  0x9A96, [0x01, None, None],
     'LD BC,nn — `ColourBytes` ($9AB8): čtyři barvy, index `$9693` & 3'),
    ('spawnColourMask',   0x9A91, [0xE6, None],
     'AND n — a takhle se z počítadla průchodů vybírá'),
    ('spawnSprite',       0x9A9E, [0xDD, 0x36, 0x00, None],
     'LD (IX+$00),n — nové zvíře začíná **zhmotňováním**, ne rovnou sebou'),

    # --- zhmotnění a druh ($A3C5, $A3E0, $A41A) ----------------------------
    ('materialiseStep',   0xA3D7, [0xDD, 0x34, None],
     'INC (IX+n) — fáze zhmotnění je prostě sprite ID o jedna dál ($A3C5)'),
    ('difficultyPieces',  0xA3F1, [0x06, None],
     'LD B,n — kolik bitů `$970D` (kusů amuletu) se počítá ($A3E0)'),
    ('difficultyBase',    0xA3FC, [0xC6, None],
     'ADD A,n — ★ **z kolika druhů se losuje**: `kusy*2 + n`, takže bez amuletu '
     'osm a se čtyřmi kusy všech šestnáct'),
    ('difficultyMask',    0xA402, [0xE6, None],
     'AND n — losuje se z `$9693` & n…'),
    ('difficultyFallback', 0xA407, [0xE6, None],
     '…a když padne víc, než je dovoleno, ořízne se na n'),
    ('kindTable',         0xA40C, [0x21, None, None],
     'LD HL,nn — `SpriteReference` ($A41A): šestnáct druhů zvířat'),
    ('kindTableEnd',      0xA42A, [0x3A, 0x03, 0x97],
     'a končí přesně na rutině `$A42A` – kontrola konce tabulky'),

    # --- zhmotňující se zvíře se dá seknout ($A3B7) -------------------------
    ('shimmerSwordFrom',  0xA3BA, [0xD6, None],
     'SUB n — zhmotňující se zvíře jde zabít, ale **jen taseným mečem**: '
     'sprite ID Sabremana od n…'),
    ('shimmerSwordCount', 0xA3BC, [0xFE, None],
     'CP n — …a o tolik dál ($A3B7)'),
    ('shimmerHitHeight',  0xA3BF, [0x01, 0x10, None],
     'LD BC,nn — `B`: obálka toho seku'),
    ('shimmerHitWidth',   0xA3BF, [0x01, None, 0x0C],
     'LD BC,nn — `C`: a její šířka'),

    # --- výbuch, body a zmizení ($A42A, $A43B, $A493, $A4A6, $A4B3) --------
    ('explodeSprite',     0xA4AC, [0xDD, 0x36, 0x00, None],
     'LD (IX+$00),n — sprite ID prvního snímku výbuchu'),
    ('explodeClear',      0xA446, [0xDD, 0x36, 0x00, None],
     'LD (IX+$00),n — a čím výbuch skončí: slot je volný'),
    ('despawnAge',        0xA499, [0xFE, None],
     'CP n — zvíře, které zůstalo na jiné obrazovce, po n průchodech zmizí ($A493)'),
    ('enemyScoreMask',    0xA4B9, [0xE6, None],
     'AND n — ★ **body za nepřítele nejsou jedno číslo**: ze sprite ID se '
     '`RLCA` 3x a n vybere krok'),
    ('enemyScoreBase',    0xA4BB, [0xC6, None],
     'ADD A,n — …a přičte se základ, takže dolní bajt je $65/$75/$85/$95'),
    ('enemyScoreHigh',    0xA4BE, [0x06, None],
     'LD B,n → `AddPointsToScore` ($B5A9) — horní bajt **BCD**: 165 až 195 bodů'),

    # --- pohyb zvířat: odraz od okrajů ($A44B) -----------------------------
    ('bounceWidthAddress', 0xA44D, [0x3A, None, None],
     'LD A,(nn) — šířka entity ($96AD), kterou si každá obsluha nastaví sama'),
    ('bounceMaxY',        0xA46E, [0xFE, None],
     'CP n — dolní okraj hrací plochy, od kterého se zvíře odrazí'),
    ('bounceMinY',        0xA48C, [0xFE, None],
     'CP n — a horní; ★ zvíře **nikdy neopustí obrazovku** (na rozdíl od '
     'nesmrtelných entit, které jdou přes `$AFE8`)'),

    # --- zvíře, které jen chodí ($A54F, $A5CD) -----------------------------
    ('nastieWidth',       0xA558, [0x3E, None, 0x32, 0xAD, 0x96],
     'LD A,n → $96AD — šířka chodícího zvířete'),
    ('nastieBoxHeight',   0xA52D, [0x01, 0x17, None],
     'LD BC,nn — `B`: obálka proti kulise'),
    ('nastieBoxWidth',    0xA52D, [0x01, None, 0x17],
     'LD BC,nn — `C`: a její šířka'),
    ('nastieHitHeight',   0xA539, [0x01, 0x13, None],
     'LD BC,nn — `B`: obálka kontaktu se Sabremanem ($AB36)'),
    ('nastieHitWidth',    0xA539, [0x01, None, 0x13],
     'LD BC,nn — `C`: a její šířka'),
    ('nastieSpeedTable',  0xA5DD, [0x01, None, None],
     'LD BC,nn — osm rychlostí, ze kterých si zvíře losuje směr ($A601)'),
    ('nastieSpeedMask',   0xA5D8, [0xE6, None],
     'AND n — vodorovná z `Rand8` & n, svislá z `FRAMES` & n ($A5F0)'),
    ('nastieTimerMask',   0xA613, [0xE6, None],
     'AND n — jak dlouho zvíře stojí, než se zase rozejde ($A609)…'),
    ('nastieTimerBase',   0xA615, [0xF6, None],
     'OR n — …nejméně tolik průchodů'),

    # --- zvíře, které nahání ($A4D7) ---------------------------------------
    ('chaserWidth',       0xA4DF, [0x3E, None, 0x32, 0xAD, 0x96],
     'LD A,n → $96AD — šířka naháněče'),
    ('chaserAccel',       0xA4F0, [0x01, None, 0x30],
     'LD BC,nn — `C`: ★ o kolik naháněč **přidá k rychlosti** ke Sabremanovi '
     'každý průchod'),
    ('chaserCap',         0xA4F0, [0x01, 0x08, None],
     'LD BC,nn — `B`: a strop té rychlosti ($AFD0)'),

    # --- kdo koho zabije ($AB36, $AB3D) ------------------------------------
    ('killSwordFrom',     0xAB4C, [0xD6, None],
     'SUB n — kontakt: pod tímhle sprite ID Sabreman meč nemá ($AB49)…'),
    ('killSwordCount',    0xAB4E, [0xFE, None],
     'CP n — …a o tolik dál začíná meč, tedy $20–$2F'),
    ('killSwordSide',     0xAB52, [0xCB, None],
     'BIT b,A — ★ a **který bit rozhoduje, na kterou stranu meč platí**: '
     'zvíře zemře jen tehdy, když je Sabreman na správné straně'),
    ('killStateAddress',  0xAB65, [0x32, None, None],
     'LD (nn),A — kam se zapíše, že Sabreman umírá (`+2` jeho záznamu, $9704)'),

    # --- ohnivá koule ($9ABC, $9AE9, $9D91) --------------------------------
    ('fireballSlot',      0x9AC9, [0x11, None, None],
     'LD DE,nn — ★ ohnivá koule má **vlastní slot mezi nesmrtelnými entitami** '
     '($9762, slot 8) – to je ten prázdný, který M4 našel'),
    ('fireballTimerAddress', 0x9ACF, [0x21, None, None],
     'LD HL,nn — ★ `$96B4` **není nedotknutelnost po respawnu, jak M3 hádal, '
     'ale odpočet do ohnivé koule**: $9ABC ho ubírá a na nule kouli položí'),
    ('fireballDelay',     0xB164, [0x3E, None, 0x32, 0xB4, 0x96],
     'LD A,n → $96B4 — ★ a **při každé změně obrazovky se nastaví znovu** '
     '($B148), takže kdo chodí, kouli nedostane'),
    ('fireballDelayStart', 0xB1BF, [0x3E, None, 0x32, 0xB4, 0x96],
     'LD A,n → $96B4 — totéž na začátku kola ($B1BF) a po smrti ($AA52)'),
    ('fireballRespawn',   0xA4A1, [0x3E, None, 0x32, 0xB4, 0x96],
     'LD A,n → $96B4 — ★ a **když kouli sebere čas, vrátí se mnohem dřív**'),
    ('fireballSprite',    0x9ADF, [0xDD, 0x36, 0x00, None],
     'LD (IX+$00),n — sprite ID koule při položení'),
    ('fireballColour',    0x9AE3, [0xDD, 0x36, 0x05, None],
     'LD (IX+$05),n — a její barva'),
    ('fireballAlignMask', 0x9AEC, [0xE6, None],
     'AND n — ★ koule se pokládá **do přímky se Sabremanem**: podle `$9693` & n '
     'buď na jeho x, nebo na jeho y ($9AE9)'),
    ('fireballWidth',     0x9D9A, [0x3E, None, 0x32, 0xAD, 0x96],
     'LD A,n → $96AD — šířka koule'),
    ('fireballBoxHeight', 0x9DC3, [0x01, 0x0F, None],
     'LD BC,nn — `B`: obálka proti kulise'),
    ('fireballBoxWidth',  0x9DC3, [0x01, None, 0x17],
     'LD BC,nn — `C`: a její šířka'),
    ('fireballHitHeight', 0x9DEC, [0x01, 0x0F, None],
     'LD BC,nn — `B`: obálka, kterou koule zabíjí'),
    ('fireballHitWidth',  0x9DEC, [0x01, None, 0x13],
     'LD BC,nn — `C`: a její šířka'),
    ('fireballLife',      0x9DAC, [0xDD, 0x35, None],
     'DEC (IX+n) — ★ koule má **omezený život**: `+8` se ubírá od nuly, takže '
     'vydrží 256 průchodů a pak sama vybuchne'),
    ('fireballTurnEvery', 0x9E0E, [0xDD, 0x36, 0x02, None],
     'LD (IX+$02),n — po tolika průchodech koule změní směr'),
    ('fireballHomeMask',  0x9E15, [0xE6, None],
     'AND n — ★ a **střídá se v tom**: při `$9693` & n míří na Sabremana, '
     'jinak si losuje'),
    ('fireballSpeedTable', 0x9E53, [0x01, None, None],
     'LD BC,nn — osm rychlostí pro losovaný směr ($9E5C)'),
    ('fireballSpeedMask', 0x9E1C, [0xE6, None],
     'AND n — index z `Rand8` & n'),
    ('fireballHomeRight', 0x9E37, [0xDD, 0x36, 0x06, None],
     'LD (IX+$06),n — když je Sabreman vpravo, koule jede doprava…'),
    ('fireballHomeLeft',  0x9E48, [0xDD, 0x36, 0x06, None],
     'LD (IX+$06),n — …a doleva, když vlevo'),
    ('fireballHomeDown',  0x9E43, [0xDD, 0x36, 0x07, None],
     'LD (IX+$07),n — a když je Sabreman **pod** koulí, jede dolů'),
    ('fireballHomeUpOffset', 0x9E4E, [0xDD, 0x36, None, 0x40],
     'LD (IX+n),$40 — ★ ale když je Sabreman **nad** koulí, zapíše hra do '
     '`+6` místo do `+7`, tedy do **vodorovné** rychlosti. Koule tím nahoru '
     'nikdy nemíří a místo toho se rozjede doprava. **Chyba originálu, '
     'a reprodukuje se**'),
    ('fireballHomeUp',    0x9E4E, [0xDD, 0x36, 0x06, None],
     'LD (IX+$06),n — a tohle je ta hodnota, kterou tam zapíše'),
    ('fireballFlickerMask', 0x9DD2, [0xE6, None],
     'AND n — snímek koule z `Rand8` & n…'),
    ('fireballFlickerBase', 0x9DD4, [0xF6, None],
     'OR n — …plus základ sprite ID'),
    ('fireballColourMask', 0x9E67, [0xE6, None],
     'AND n — barva koule z `Rand8` & n ($9E64)…'),
    ('fireballColourMin', 0x9E69, [0xFE, None],
     'CP n — …pod n se doplní…'),
    ('fireballColourFill', 0x9E6D, [0xF6, None],
     'OR n — …tímhle…'),
    ('fireballColourBase', 0x9E6F, [0xF6, None],
     'OR n — …a nakonec se přidá `BRIGHT`'),

    # --- nosorožec ($AD07, $AD69, $AD86) -----------------------------------
    ('rhinoWidth',        0xAD0D, [0x3E, None, 0x32, 0xAD, 0x96],
     'LD A,n → $96AD — šířka nosorožce'),
    ('rhinoBoxHeight',    0xAD15, [0x01, 0x1F, None],
     'LD BC,nn — `B`: obálka proti kulise'),
    ('rhinoBoxWidth',     0xAD15, [0x01, None, 0x17],
     'LD BC,nn — `C`: a její šířka'),
    ('rhinoHitHeight',    0xAD35, [0x01, 0x1C, None],
     'LD BC,nn — `B`: obálka kontaktu'),
    ('rhinoHitWidth',     0xAD35, [0x01, None, 0x0F],
     'LD BC,nn — `C`: a její šířka'),
    ('rhinoTurnSpeed',    0xAD20, [0x3E, None],
     'LD A,n — do čeho se nosorožec zabrzdí o kulisu a otočí se ($AD86)'),
    ('rhinoRepelLeft',    0xAD74, [0x3E, None],
     'LD A,n — ★ nosorožec **se nedá zabít, jen zahnat**: podle toho, kam '
     'Sabreman kouká, se rozjede doleva…'),
    ('rhinoRepelRight',   0xAD82, [0x3E, None],
     'LD A,n — …nebo doprava, a to **rychleji, než chodil**'),
    ('rhinoFacingBit',    0xAD6C, [0xCB, None],
     'BIT b,A — a rozhoduje o tom tenhle bit Sabremanova sprite ID'),
    ('animateEvery',      0xAD96, [0xE6, None],
     'AND n — snímek chůze se přepne, když je `$9693` dělitelné n+1 ($AD93)'),

    # --- hroch ($9E72, $9EB3) ----------------------------------------------
    ('hippoWidth',        0x9E78, [0x3E, None, 0x32, 0xAD, 0x96],
     'LD A,n → $96AD — šířka hrocha'),
    ('hippoBoxHeight',    0x9E86, [0x01, 0x1F, None],
     'LD BC,nn — `B`: obálka proti kulise'),
    ('hippoBoxWidth',     0x9E86, [0x01, None, 0x17],
     'LD BC,nn — `C`: a její šířka'),
    ('hippoHitHeight',    0x9ED8, [0x01, 0x1C, None],
     'LD BC,nn — `B`: obálka kontaktu'),
    ('hippoHitWidth',     0x9ED8, [0x01, None, 0x0F],
     'LD BC,nn — `C`: a její šířka'),
    ('hippoStun',         0x9EF7, [0xDD, 0x36, 0x02, None],
     'LD (IX+$02),n — ★ hroch se taky **jen zažene**: na tolik průchodů se '
     'zastaví a nehýbe se'),
    ('hippoRoamBit',      0x9E92, [0xDD, 0xCB, 0x00, None],
     'SET b,(IX+$00) — ★ a když ho zastaví kulisa, **přepne se na obsluhu, '
     'která ho odstěhuje na jinou obrazovku** ($9EB3 → $A630)'),

    # --- putování nesmrtelných entit ($A630) -------------------------------
    ('roamRowGap',        0xA64E, [0xFE, None],
     'CP n — ★ nesmrtelná entita se za Sabremanem **stěhuje po světě**: když '
     'je od jeho řádku dál než n, přeskočí…'),
    ('roamRowStep',       0xA679, [0xC6, None],
     'ADD A,n — …o řádek pod něj…'),
    ('roamRowStepUp',     0xA659, [0xD6, None],
     'SUB n — …nebo nad něj (`Rand8` bit 0 rozhodne)…'),
    ('roamColumnKeep',    0xA65D, [0xE6, None],
     'AND n — …a ze sloupce si nechá Sabremanovy horní bity…'),
    ('roamColumnMask',    0xA663, [0xE6, None],
     'AND n — …a své vlastní dolní, takže skončí ve stejné čtvrtině řádku'),

    # --- domorodec ($AB74, $ABDE) ------------------------------------------
    ('nativeWidth',       0xAB7A, [0x3E, None, 0x32, 0xAD, 0x96],
     'LD A,n → $96AD — šířka domorodce'),
    ('nativeBoxHeight',   0xAB82, [0x01, 0x0F, None],
     'LD BC,nn — `B`: obálka proti kulise'),
    ('nativeBoxWidth',    0xAB82, [0x01, None, 0x17],
     'LD BC,nn — `C`: a její šířka'),
    ('nativeHitHeight',   0xAB9C, [0x01, 0x0C, None],
     'LD BC,nn — `B`: obálka kontaktu'),
    ('nativeHitWidth',    0xAB9C, [0x01, None, 0x0F],
     'LD BC,nn — `C`: a její šířka'),
    ('nativeSpeedTable',  0xABE2, [0x01, None, None],
     'LD BC,nn — čtyři rychlosti ($AC24), ze kterých si domorodec losuje směr'),
    ('nativeSpeedMask',   0xABE8, [0xE6, None],
     'AND n — vodorovná z `Rand8` & n, svislá z `FRAMES` & n ($ABFD)'),
    ('nativeRepelRight',  0xABAB, [0x3E, None],
     'LD A,n — ★ domorodec se **jen zahání**: doprava…'),
    ('nativeRepelLeft',   0xABDA, [0x3E, None],
     'LD A,n — …nebo doleva, podle toho, kam Sabreman kouká'),
    ('nativeFacingBit',   0xABA7, [0xE6, None],
     'AND n — a rozhoduje o tom tenhle bit Sabremanova sprite ID'),

    # --- Sabre Wulf ($A858, $A8B2, $A8F5, $A964, $A922) --------------------
    ('wulfWidth',         0xA85B, [0x3E, None, 0x32, 0xAD, 0x96],
     'LD A,n → $96AD — šířka Sabre Wulfa'),
    ('wulfBoxHeight',     0xA86C, [0x01, 0x1F, None],
     'LD BC,nn — `B`: obálka proti kulise'),
    ('wulfBoxWidth',      0xA86C, [0x01, None, 0x17],
     'LD BC,nn — `C`: a její šířka'),
    ('wulfHitHeight',     0xA88F, [0x01, 0x1C, None],
     'LD BC,nn — `B`: obálka, kterou zabíjí'),
    ('wulfHitWidth',      0xA88F, [0x01, None, 0x0F],
     'LD BC,nn — `C`: a její šířka'),
    ('wulfRowMask',       0xA925, [0xE6, None],
     'AND n — ★ Sabre Wulf se rozjede, **jen když je Sabreman v témže řádku '
     'světa** ($A922); v jiném řádku stojí'),
    ('wulfChargeLeft',    0xA948, [0xDD, 0x36, 0x06, None],
     'LD (IX+$06),n — a pak se rozjede doleva…'),
    ('wulfChargeRight',   0xA951, [0xDD, 0x36, 0x06, None],
     'LD (IX+$06),n — …nebo doprava, přímo na něj'),
    ('wulfSwordLeftFrom', 0xA8D0, [0xD6, None],
     'SUB n — ★ **mečem se dá odehnat**: když jede doleva, platí sprite ID od n…'),
    ('wulfSwordRightFrom', 0xA8EE, [0xD6, None],
     'SUB n — …a když doprava, od n'),
    ('wulfSwordCount',    0xA8D2, [0xFE, None],
     'CP n — a v obou případech o tolik dál (osm póz seku)'),
    ('wulfWardSprite',    0xA8DA, [0xF6, None],
     'OR n — odehnaný Sabre Wulf přejde na sprite ID s tímhle bitem…'),
    ('wulfWardTimer',     0xA8DF, [0xDD, 0x36, 0x02, None],
     'LD (IX+$02),n — …a couvá tolik průchodů ($A8F5)'),
    ('wulfRecoilTimer',   0xA91B, [0xDD, 0x36, 0x02, None],
     'LD (IX+$02),n — pak přejde do druhé fáze na tolik průchodů ($A964)'),
    ('wulfReturnTimer',   0xA970, [0xDD, 0x36, 0x02, None],
     'LD (IX+$02),n — a nakonec se vrátí zpátky'),
    ('wulfSpeedUp',       0xA97D, [0xC6, None],
     'ADD A,n — ★ a **po každém odehnání je rychlejší** ($A964): kladné '
     'rychlosti se přičte n…'),
    ('wulfSpeedUpNeg',    0xA97B, [0xD6, None],
     'SUB n — …a záporné se n odečte, takže roste v obou směrech'),

    # --- strážce brány ($9F16) ---------------------------------------------
    ('keeperAmuletMask',  0x9F23, [0xE6, None],
     'AND n — ★ strážce se dívá na **kusy amuletu** v `$970D`…'),
    ('keeperAmuletAll',   0x9F25, [0xFE, None],
     'CP n — …a uhne, jen když je má hráč všechny čtyři'),
    ('keeperHitHeight',   0x9F2C, [0x01, 0x0F, None],
     'LD BC,nn — `B`: obálka, kterou bez amuletu zabíjí'),
    ('keeperHitWidth',    0x9F2C, [0x01, None, 0x17],
     'LD BC,nn — `C`: a její šířka'),
    ('keeperKill',        0x9F35, [0x3E, None, 0x32, 0x04, 0x97],
     'LD A,n → $9704 — ★ a je to **jiná smrt než od zvířat**: do `+2` '
     'Sabremanova záznamu jde n, ne 1 nebo 2'),
    ('keeperStepLeft',    0x9F47, [0xDD, 0x36, 0x06, None],
     'LD (IX+$06),n — s amuletem strážce ustupuje doleva…'),
    ('keeperLimitLeft',   0x9F4F, [0xFE, None],
     'CP n — …dokud nedojde sem'),
    ('keeperStepRight',   0x9F5D, [0xDD, 0x36, 0x06, None],
     'LD (IX+$06),n — nebo doprava…'),
    ('keeperLimitRight',  0x9F65, [0xFE, None],
     'CP n — …a tam se zastaví; kudy uhne, rozhoduje **bit 7 Sabremanova x**'),
    ('keeperSideBit',     0x9F43, [0xCB, None],
     'BIT b,A — a to je ten bit ($9705)'),

    # --- dva hráči ($B1B7, $B21E, $AA27) -----------------------------------
    ('gameDelay',         0xB1C4, [0x3E, None, 0x32, 0xB5, 0x96],
     'LD A,n → `GameDelayTimer` ($96B5) — ★ **a je to jediné místo, kde se '
     'nastavuje**: $80 pro jednoho i pro dva hráče, ne $FF, jak říká '
     'veřejná disassembly'),
    ('livesStart',        0xB21E, [0x3E, None, 0x32, 0xBD, 0x96],
     'LD A,n → `ActivePlayer_Lives` — na začátku kola…'),
    ('livesDecOnTurn',    0xB1CD, [0x21, 0xBD, 0x96, 0x35],
     'LD HL,nn / DEC (HL) — ★ …a **jeden se hned odebere tomu, kdo jde na '
     'tah** ($B1B7). Odtud „čtyři životy" – a odtud i chyba v režimu dvou '
     'hráčů: po smrti se hráči prohodí ($B205 → $B235) a **teprve pak** se '
     'život odebere, takže ho zaplatí ten druhý'),
    ('twoPlayerBit',      0xAA2A, [0xE6, None],
     'AND n — `GameOptions` ($9692) bit 0: jeden hráč, nebo dva ($AA27)'),
    ('inactiveLivesAddress', 0xAA5A, [0x3A, None, None],
     'LD A,(nn) — životy druhého hráče ($96E0); když je nemá, střídání se '
     'přeskočí a hraje se dál jako jeden hráč'),
    ('swapStates',        0xB242, [0x01, None, None],
     'LD BC,nn — `ChangePlayer` ($B235) prohodí tolik bajtů stavu hráče '
     '($96BC: hráč, životy, počet zvířat a `VisitedRooms`)'),
    ('swapMapBytes',      0xB24E, [0x01, None, None],
     'LD BC,nn — …celou mapu předmětů ($DDEC ↔ $DFEC)…'),
    ('swapEntityBytes',   0xB25A, [0x01, None, None],
     'LD BC,nn — …a celou tabulku entit ($9702 ↔ $982E), takže **každý hráč '
     'má svá zvířata i svého Sabre Wulfa**'),
]

# Jména obsluh z `JumpTable`: adresa → (jméno, role, poznámka).
# Role je to, co remake potřebuje vědět; jméno je z veřejné disassembly.
HANDLERS = {
    0xADBD: ('Nothing', 'none',
             'RET – sprite ID, které hra nepoužívá'),
    0xA3C5: ('Materialise', 'materialise',
             'zhmotňování nového zvířete: sprite ID o jedna dál každý průchod'),
    0xA3E0: ('MaterialiseDone', 'materialiseDone',
             'poslední snímek zhmotnění vybere druh zvířete ze `SpriteReference`'),
    0xA42A: ('Explosion', 'explosion',
             'výbuch: sprite ID o jedna dál každý průchod'),
    0xA43B: ('ExplosionEnd', 'explosionEnd',
             'poslední snímek výbuchu uvolní slot'),
    0xAECF: ('PlayerDelay', 'player',
             'Sabreman, dokud běží `GameDelayTimer` (M3)'),
    0xADD0: ('PlayerMovement', 'player',
             'Sabreman s taseným mečem (M3)'),
    0xAD07: ('Rhino', 'rhino',
             '★ nosorožec: chodí po světě, **nedá se zabít, jen zahnat** '
             '– a to rychleji, než chodil'),
    0x9D91: ('Fireball', 'fireball',
             '★ ohnivá koule: objeví se tomu, kdo stojí v místnosti, drží se '
             'ho a po 256 průchodech sama vybuchne'),
    0xAB74: ('Native', 'native',
             '★ domorodec: nedá se zabít, jen zahnat, a **zežloutne a pípne, '
             'když je v přímce se zakopaným kusem amuletu** (M4)'),
    0xA9BE: ('PlayerDeathFlight', 'player',
             'Sabreman odletí po smrti (M3)'),
    0xAA0D: ('PlayerDeathWait', 'player',
             'a sedí, než ho hra postaví zpátky (M3)'),
    0xA61B: ('PlayerStandUp', 'player',
             'vstávání po žluté orchideji (M4)'),
    0xA680: ('Orchid', 'orchid',
             'orchidej (M4)'),
    0xA858: ('SabreWulf', 'wulf',
             '★ Sabre Wulf: stojí, dokud není Sabreman v témže **řádku '
             'světa**, pak se rozjede přímo na něj; zabíjí dotekem, '
             'mečem se dá odehnat a **po každém odehnání je rychlejší**'),
    0xA8F5: ('SabreWulfWard', 'wulfWard',
             'odehnaný Sabre Wulf couvá, dokud na něj Sabreman míří mečem'),
    0xA964: ('SabreWulfReturn', 'wulfReturn',
             'a pak se vrací – s vyšší rychlostí, než měl'),
    0xA54F: ('Nastie', 'nastie',
             'zvíře, které si chodí po obrazovce a **dá se zabít**'),
    0xA4D7: ('NastieChaser', 'chaser',
             '★ zvíře, které Sabremana **nahání**: každý průchod přidá k '
             'rychlosti jeho směrem; taky se dá zabít'),
    0xA312: ('Object', 'object',
             'předmět (M4)'),
    0xA305: ('ObjectLife', 'life',
             'předmět „život" (M4)'),
    0xA1AB: ('AmuletPiece', 'amulet',
             'kus amuletu (M4)'),
    0x9F16: ('Keeper', 'keeper',
             '★ strážce brány: bez amuletu zabíjí dotekem, se všemi čtyřmi '
             'kusy **ustoupí na kraj obrazovky a pustí**'),
    0x9E72: ('Hippo', 'hippo',
             '★ hroch: nedá se zabít, jen zahnat a na chvíli omráčit'),
    0x9EB3: ('HippoRoam', 'hippoRoam',
             'a když ho zastaví kulisa, odstěhuje se za Sabremanem na jinou '
             'obrazovku ($A630)'),
}

# Které role jsou nepřítel a jak s nimi je
ROLE_NOTES = {
    'rhino': ('immortal', 'nosorožec'),
    'native': ('immortal', 'domorodec'),
    'hippo': ('immortal', 'hroch'),
    'hippoRoam': ('immortal', 'hroch na cestě'),
    'wulf': ('immortal', 'Sabre Wulf'),
    'wulfWard': ('immortal', 'Sabre Wulf odehnaný'),
    'wulfReturn': ('immortal', 'Sabre Wulf na návratu'),
    'keeper': ('immortal', 'strážce brány'),
    'fireball': ('immortal', 'ohnivá koule'),
    'nastie': ('destructable', 'zvíře'),
    'chaser': ('destructable', 'zvíře, které nahání'),
}


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


def rotate_left(value, times):
    for _ in range(times):
        value = ((value << 1) | (value >> 7)) & 0xFF
    return value


def enemy_score(sprite, values):
    """`$A4B3` – kolik bodů dá zničený nepřítel s tímhle sprite ID.

    ★ Není to jedno číslo: `RLCA` 3x, maska a základ udělají z bitů 1-2 sprite
    ID krok po deseti bodech. `AddPointsToScore` sčítá **BCD**, takže operand
    `$0165` znamená rovnou 165.
    """
    low = (rotate_left(sprite, 3) & values['enemyScoreMask']) + values['enemyScoreBase']
    return int('%02X%02X' % (values['enemyScoreHigh'], low))


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

    # `BIT b,A` a `SET b,(IX+d)` nesou číslo bitu v opkódu – uložit se má bit,
    # ne opkód, jinak by si ho replika musela dekódovat sama
    for name in ('killSwordSide', 'rhinoFacingBit', 'keeperSideBit',
                 'hippoRoamBit'):
        values[name] = (values[name] >> 3) & 0x07
        checked += 1

    # dvě čísla, která se v obraze vyskytují dvakrát a musí souhlasit – to je
    # sama o sobě kontrola, že čteme, co si myslíme
    check(values['spawnDelay'] == values['spawnDelayStart'],
          'prodleva dosazovani zvirat: $AA4D rika %d, $B1BA %d'
          % (values['spawnDelay'], values['spawnDelayStart']))
    checked += 1
    check(values['fireballDelay'] == values['fireballDelayStart'],
          'odpocet do ohnive koule: $B164 rika %d, $B1BF %d'
          % (values['fireballDelay'], values['fireballDelayStart']))
    checked += 1
    # ★ a tohle je ta chyba v ohnivé kouli: „nahoru" se zapisuje do vodorovné
    # rychlosti, ne do svislé
    check(values['fireballHomeUpOffset'] == 6,
          'ohniva koule: $9E4E ma psat do +6 (chyba originalu), pise do +%d'
          % values['fireballHomeUpOffset'])
    checked += 1

    sprites = json.load(open(SPRITES))
    entities = json.load(open(ENTITIES))
    frame_at = {}
    for entry in sprites['sprites']:
        frame_at[int(entry['id'][1:], 16)] = entry

    def sprite_name(sprite):
        entry = frame_at.get(sprite)
        return entry['name'] if entry else None

    # -- JumpTable: kdo je co, a není to odhad ------------------------------
    table = values['jumpTable']
    end = values['jumpTableEnd'] if 'jumpTableEnd' in values else 0x9CC6
    end = 0x9CC6                        # konec je adresa instrukce, ne operand
    check((end-table) % 2 == 0,
          'JumpTable ($%04X-$%04X) nema sudou delku' % (table, end))
    count = (end-table)//2
    jump, unknown = [], set()
    for sprite in range(count):
        addr = peek(ram, table+sprite*2)[0] | peek(ram, table+sprite*2+1)[0] << 8
        if addr not in HANDLERS:
            unknown.add(addr)
        name, role, note = HANDLERS.get(addr, ('?', 'unknown', ''))
        jump.append({'sprite': sprite, 'handler': '$%04X' % addr,
                     'name': name, 'role': role,
                     'spriteName': sprite_name(sprite)})
    check(not unknown,
          'JumpTable ukazuje na neznamou obsluhu: %s'
          % ', '.join('$%04X' % a for a in sorted(unknown)))
    checked += 1

    # role → souvislé rozsahy sprite ID, ať se to dá číst
    ranges, current = [], None
    for entry in jump:
        if current and current['role'] == entry['role'] \
                and current['handler'] == entry['handler']:
            current['last'] = entry['sprite']
            continue
        current = {'role': entry['role'], 'handler': entry['handler'],
                   'name': entry['name'], 'first': entry['sprite'],
                   'last': entry['sprite']}
        ranges.append(current)
    for group in ranges:
        addr = int(group['handler'][1:], 16)
        group['note'] = HANDLERS[addr][2]
        kind, label = ROLE_NOTES.get(group['role'], (None, None))
        if kind:
            group['kind'] = kind
            group['label'] = label

    # -- šestnáct druhů zvířat ($A41A) a jejich obsluhy ---------------------
    kinds = []
    for i in range(16):
        sprite = peek(ram, values['kindTable']+i)[0]
        entry = jump[sprite]
        kinds.append({'index': i, 'sprite': sprite, 'role': entry['role'],
                      'handler': entry['handler'],
                      'spriteName': sprite_name(sprite),
                      'score': enemy_score(sprite, values)})
    check(peek(ram, values['kindTable']+16, 3) == bytes((0x3A, 0x03, 0x97)),
          'SpriteReference ($%04X) nema koncit na rutine $A42A' % values['kindTable'])
    checked += 1

    # -- tabulky rychlostí --------------------------------------------------
    def table_bytes(addr, length, end_bytes, what):
        data = list(peek(ram, addr, length))
        check(peek(ram, addr+length, len(end_bytes)) == bytes(end_bytes),
              '%s ($%04X) nekonci tam, kde ma' % (what, addr))
        return data

    spawn_colours = table_bytes(values['spawnColourTable'], 4,
                                (0x3A, 0x02, 0x97), 'ColourBytes')
    nastie_speeds = table_bytes(values['nastieSpeedTable'], 8,
                                (0xAF, 0xDD, 0x77), 'tabulka rychlosti zvirat')
    fireball_speeds = table_bytes(values['fireballSpeedTable'], 8,
                                  (0x3A, 0x95, 0x96), 'tabulka rychlosti koule')
    native_speeds = table_bytes(values['nativeSpeedTable'], 4,
                                (0xFB, 0x3E, 0x7E), 'tabulka rychlosti domorodcu')
    checked += 4

    # -- které z jedenácti nesmrtelných entit je co -------------------------
    immortal = []
    for record in entities['immortal']:
        if record['slot'] == 0:
            continue                    # slot 0 je Sabreman
        entry = jump[record['sprite']]
        immortal.append({'slot': record['slot'], 'sprite': record['sprite'],
                         'room': record['room'],
                         'column': record['column'], 'row': record['row'],
                         'role': entry['role'], 'handler': entry['handler'],
                         'label': ROLE_NOTES.get(entry['role'], (None, None))[1],
                         'spriteName': record['name']})
    empty = [r for r in immortal if r['sprite'] == 0]
    check(len(empty) == 1,
          'cekam prave jeden prazdny slot mezi nesmrtelnymi, mam %d' % len(empty))
    slot = (values['fireballSlot']-0x9702)//12
    check(empty[0]['slot'] == slot,
          'ohniva koule ma slot %d, prazdny je %d' % (slot, empty[0]['slot']))
    checked += 2
    for record in immortal:
        if record['slot'] == slot:
            record['role'] = 'fireball'
            record['label'] = 'ohnivá koule (slot je prázdný, dokud se neobjeví)'

    data = {
        'note': 'Nepratele Sabre Wulfa, jak je pocita original: obsluha kazde '
                'entity je JumpTable[sprite ID] ($9B3E), takze rozdeleni na '
                'znicitelne a nezniciteline neni odhad. %d zkontrolovanych '
                'instrukci a koncu tabulek. Replika je app/worldMonsters.js, '
                'overeni tools/tracemonsters.py + tools/matchmonsters.js.'
                % checked,
        'jumpTable': {
            'address': '$%04X' % table,
            'end': '$%04X' % end,
            'entries': count,
            'note': 'index je sprite ID; tabulka konci presne na '
                    'PrintRoomsVisited ($9CC6)',
            'ranges': ranges,
            'handlers': jump,
        },
        'kinds': {
            'address': '$%04X' % values['kindTable'],
            'note': 'SpriteReference ($A41A): sestnact druhu zvirat. Index se '
                    'losuje z $9693, ale jen do "kusy amuletu * 2 + %d", '
                    'takze cim vic amuletu hrac ma, tim horsi zvirata chodi.'
                    % values['difficultyBase'],
            'list': kinds,
        },
        'immortal': immortal,
        'speeds': {
            'spawnColours': spawn_colours,
            'nastie': [signed(v) for v in nastie_speeds],
            'nastieRaw': nastie_speeds,
            'fireball': [signed(v) for v in fireball_speeds],
            'fireballRaw': fireball_speeds,
            'native': [signed(v) for v in native_speeds],
            'nativeRaw': native_speeds,
            'note': 'rychlosti jsou v 1/16 pixelu za pruchod, jako u Sabremana '
                    '(M3): $B031 z nich dela cele pixely smerem k nule',
        },
        'score': {
            'enemy': [enemy_score(s, values) for s in (0x60, 0x62, 0x64, 0x66)],
            'note': 'AddPointsToScore ($B5A9) scita BCD. Body za neprítele '
                    'delaji bity 1-2 sprite ID: 165, 175, 185 nebo 195. '
                    'Procento navstivenych obrazovek do skore nevstupuje – '
                    '$9CC6 ho jen tiskne na obrazovce GAME OVER.',
            'percentInScore': False,
        },
        'values': values,
        'source': notes,
    }

    with open(args.out, 'w') as out:
        json.dump(data, out, indent=1, sort_keys=False)
        out.write('\n')

    if args.show:
        print('JumpTable $%04X: %d sprite ID, %d rozsahu'
              % (table, count, len(ranges)))
        for group in ranges:
            if group['role'] in ('none', 'player'):
                continue
            print('  $%02X-$%02X  %-16s %-10s %s'
                  % (group['first'], group['last'], group['name'],
                     group.get('kind', ''), group.get('label') or ''))
        print()
        print('sestnact druhu zvirat ($A41A):')
        for kind in kinds:
            print('  %2d  sprite $%02X  %-10s %4d bodu  %s'
                  % (kind['index'], kind['sprite'], kind['role'], kind['score'],
                     kind['spriteName'] or ''))
        print()
        print('jedenact nesmrtelnych entit:')
        for record in immortal:
            print('  slot %2d  sprite $%02X  obrazovka $%02X (sl %2d, r %2d)  %s'
                  % (record['slot'], record['sprite'], record['room'],
                     record['column'], record['row'], record['label'] or '?'))
        print()
        print('body za neprítele: %s' % data['score']['enemy'])
        print('%d zkontrolovanych instrukci a koncu tabulek' % checked)

    print('%s: %d hodnot, %d kontrol'
          % (os.path.relpath(args.out), len(values), checked))


if __name__ == '__main__':
    main()
