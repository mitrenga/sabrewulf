# Protokol mezi `roomModel.js` a `gameWorker.js`

Worker drží herní stav a tiká na **50,08 Hz** – snímkové frekvenci originálu
(3,5 MHz / 69 888 T-stavů na snímek, herní logika visí na přerušení z ULA,
viz `sources/docs/hw_notes.md` a ZADANI §1). Model do něj jen posílá vstupy
a kreslí to, co dostane zpátky.

**Stav M4: worker drží celý svět.** Kromě Sabremana v něm od M4 žijí
**orchideje, předměty a kusy amuletu** – `app/worldEntities.js`, přepis rutin
originálu řízený `data/entities.json`, ověřený proti originálu na **21 444
kontrolách ve třinácti případech s nulou rozdílů** (`tools/traceentities.py`
+ `tools/matchentities.js`). Zvířata, domorodci, Sabre Wulf a strážce brány
jsou M5; kde leží, je ale změřené už teď (`entities.immortal`).

**Stav M3: worker hýbe Sabremanem.** Krok fyziky je `app/sabremanPhysics.js`,
přepis rutin originálu řízený `data/physics.json`, ověřený krok po kroku proti
nahraným běhům: **2 323 kroků ve třinácti scénářích, 12 bajtů záznamu na krok,
nula rozdílů** (`tools/tracephysics.py` + `tools/matchphysics.js`). Nic v něm
není vymyšlené – každá konstanta je operand skutečné instrukce.

**Jeden krok na tik** je kadence originálu. Jedna výjimka: přechod mezi
obrazovkami je pořád jeden krok, ale hlavní smyčka originálu na něj potřebuje
**šest až osm snímků**, protože při něm překresluje celou hrací plochu. To je
časování Z80, ne pravidlo hry – remake to udělá v jednom tiku a rozdíl patří
k porovnání s emulátorem v M7.

Kromě toho posílá worker snímek za tik i se stavem ovládání – z toho model
pozná, že klávesnice, myš, gamepad **i dotyk** dorazily (v dev režimu je
vypisuje do pravého horního rohu) – a k tomu skóre, životy, `HI` a kdo je na
tahu.

**Dva hráči jsou v protokolu od začátku**, ne přilepení potom: originál má dvě
počítadla životů (`$96BD`, `$96E0`), dvě skóre (`$9698`, `$969B`), střídá je
a dvojici dává delší prodlevu na výměnu ovladače (`GameDelayTimer`, `$96B5`:
`$80` pro jednoho, `$FF` pro dva). Samotné pravidlo střídání – a **ta chyba**
v režimu dvou hráčů, kterou zmiňují dobové recenze – je M5.

**Souřadnice jsou souřadnice stroje**, jako u underwurlde: `x` levý okraj
spritu, `y` jeho **spodní** pixelová řádka v souřadnicích obrazovky (panel
zabírá prvních 16 řádek). ★ Že je `y` spodní řádka, plyne z kreslení originálu
(`$BA7C` dělá `DEC H`, jde tedy vzhůru) a potvrzuje to kolizní obálka, která se
od `y` počítá 22 px nahoru.

## Model → worker

| zpráva | pole | význam |
|---|---|---|
| `init` | `initData: {headless, players, lives, hiScore, scene, physics, world, rooms, scenery}` | start nové hry. `headless: true` tiká jen na vyžádání zprávou `tick` (pro testy). |
| `controls` | `left`, `right`, `up`, `down`, `sword` (boolean) | úplný stav ovládání; posílá se při každé změně. Posílá se **celý**, ne jen změna, protože pohyb je osmisměrný („Full 8 Way Movement" na obalu) a dva držené směry jsou úhlopříčka, ne konflikt. `fire` je meč (`T`, „Combat Button"). |
| `pause` | – | zastaví tikání. |
| `continue` | – | pokračuje. |
| `tick` | – | jeden krok v režimu `headless`. |
| `reset` | – | zahodí stav (volá se při opuštění herní obrazovky). |

### `initData`

| klíč | obsah |
|---|---|
| `players` | 1 nebo 2 – volba z menu, v originálu `GameOptions` (`$9692`). |
| `lives` | zásoba životů. ★ Odměřeno: `ActivePlayer_Lives` (`$96BD`) se při startu nastaví na **5** a první Sabreman jeden odebere, takže panel od začátku ukazuje **4** (`data/global.json`, `tools/mkglobal.py`). |
| `hiScore` | nejvyšší skóre. ★ Originál si nese předvyplněné **102275**, což je první místo jeho vlastní síně slávy (`$B304`). |
| `physics` | `data/physics.json` – konstanty fyziky (`tools/dumpphysics.py`). Bez nich worker Sabremanem nehýbe a pošle `error`. |
| `entities` | `data/entities.json` – svět (`tools/dumpentities.py`): orchidej každé předlohy, čtyři pozice předmětů v ní, osm hotových sad amuletu a tabulka procent. Bez nich worker tiká, ale svět je prázdný. |
| `seed` | ★ Odkud se rozjede pseudonáhoda remaku. Originál si semínko bere ze svých běhových počítadel a **z ROM Spectra** (`$A2BD`), kterou remake nemá – je to jedno ze dvou míst M4, které se nedá zopakovat bajt na bajt (`sources/docs/disasm_notes.md` §16). Tohle je to, co dělá, že amulet leží v další hře jinde. |
| `world`, `rooms`, `scenery` | mřížka světa, 48 předloh a 41 kusů kulisy. Fyzika je potřebuje, protože ★ **kolize se ptá na tentýž seznam kusů kulisy, ze kterého se místnost kreslí** (`$B873`) – obálky, ne pixely. Dohromady necelých 60 kB na všech 256 obrazovek, takže se posílají celé. |
| `scene` | kde hra začíná: `{room, column, row}`. ★ **Startovní obrazovka je odměřená: sloupec 8, řádek 10** (`Layout` `$A8`, předloha `$08`). `$B21E` kopíruje 144 bajtů z `$AC77` do „game status bufferu" na `$9702` a druhý bajt prvního záznamu je číslo obrazovky; simulace to potvrzuje nezávisle (`$9703` za běhu hry, `tools/mkroom.py`). `column`/`row` je odtud, nebo z obrazovky, kterou si hráč vybral v `TRAINING SCREEN`. |

## Worker → model

| zpráva | pole | význam |
|---|---|---|
| `frame` | `frame`, `players`, `player`, `score`, `score2`, `hiScore`, `lives`, `sabreman`, `entities`, `effect`, `amulet`, `percent`, `poem`, `gameOverFor`, `controls`, `sounds`, `state` | jeden odtikaný krok. |
| `gameOver` | `score` | došly životy; model přepne na `GameOverModel`. |
| `error` | `message` | chybí data. |

### `score`, `score2`, `hiScore`

Tři šestimístná čísla, přesně jak je panel tiskne. V originálu jsou to **tři
bajty BCD na hráče** (`$9698`, `$969B`); jak se do nich přičítá
(`AddPointsToScore`) a jestli do skóre vstupuje procento navštívených
obrazovek, je otevřená otázka pro M5.

### `lives`

Životy hráče, který je na tahu. Panel má na ně **jedinou číslici**, což dělá
dobové tvrzení o stropu 9 věrohodným – změřené to ale není (ZADANI §7).

### `sabreman` a `entities`

`sabreman` je **záznam entity, jak ho drží originál** (`$9702`, 12 bajtů),
rozepsaný do polí:

| pole | co je to |
|---|---|
| `sprite` | sprite ID; v něm je i směr (bity 2–3) a fáze animace (bity 0–1) |
| `room`, `column`, `row` | obrazovka; `room` je **řádek<<4 \| sloupec**, jak ji drží hra |
| `state` | 0 = živ, jinak odpočet smrti (`$A985` až `$AA27`) |
| `x`, `y` | levý okraj a **spodní** řádka spritu |
| `colour` | atribut Sabremana; `$47` je bílý, tedy ovladatelný (`$42`/`$43`/`$45`/`$46` jsou účinky orchidejí, M4) |
| `dx`, `dy` | rychlost v **1/16 px** za krok, znaménkově (u smrti v celých px) |
| `fireballDelay` | ★ odpočet `$96B4`, který se nastaví na `$80` po respawnu i po přechodu obrazovky. M3 ho pokládal za nedotknutelnost, M5 změřil, že je to **odpočet do ohnivé koule** (`$9ABC`) – kdo stojí v místnosti, dostane ji |

Model z toho kreslí (`screenComposer.js` vezme podle `sprite` jeden ze 153
snímků) a když se `room` změní, poskládá novou obrazovku.

`entities` je od M4 **seznam entit té obrazovky, na které Sabreman je** – každá
jako `{sprite, room, x, y, colour}`, tedy stejná pětice jako u Sabremana, takže
je renderer kreslí týmž kódem. Jsou v něm **orchidej** (sprity `$48`–`$4F`),
**až dva předměty** (`$80`–`$8F`) a **kusy amuletu** (`$90`–`$93`). ★ Od M5 jdou
týmž kanálem i **nepřátelé**: zvířata (`$60`–`$7F`, `$98`–`$9F`, `$B0`–`$C3`)
a jejich zhmotňování (`$01`–`$06`) i výbuch (`$08`–`$0D`), **nosorožci**
(`$30`–`$33`), **ohnivá koule** (`$34`–`$37`), **domorodci** (`$38`–`$3F`),
**Sabre Wulf** (`$50`–`$5F`), **strážce brány** (`$94`) a **hroši**
(`$A0`–`$AF`). Kdo je co, se nehádá: rozhoduje `JumpTable` (`$9B3E`), kterou
`data/monsters.json` nese celou.

K tomu má Sabremanův záznam od M4 pole `flash`: ★ když orchideji dochází
účinek, `$AF7D` ho posledních `$2F` půlsnímků kreslí **bíle** a pípá. Barva
v `colour` přitom zůstane ta, kterou mu orchidej dala – mění se jen kreslení.

★ A od M7 pole `hidden`: `true`, dokud běží úvodní prodleva. `$AECF` v té
době Sabremanův záznam vůbec neobslouží, tedy ani nenakreslí – na obrazovce
není, každý šestnáctý snímek ťukne `$BF2A` (zvuk `orchid`, `BC=$8010`)
a ostatní entity běží dál (orchidej roste). Skladač ho s `hidden` vynechá.

### `effect`, `amulet`, `percent`, `poem`

| pole | co je to |
|---|---|
| `effect` | odpočet účinku orchideje (`OrchidEffectTimer`, `$96B0`). Ubírá se **každý druhý snímek**, takže `$C0` je 384 snímků, asi 7,7 s. |
| `amulet` | které kusy amuletu hráč má (bity 0–3 z `+$0B` Sabremanova záznamu, `$970D`). |
| `percent` | ★ **procento navštívených obrazovek** – skutečné pravidlo hry (`PrintRoomsVisited`, `$9CC6`). Do celku se počítají **i čtyři kusy amuletu**, takže je to 260, ne 256, a jedna obrazovka je méně než půl procenta. Model to ukazuje na obrazovce GAME OVER jako `ADVENTURE COMPLETED    n%` (`$AAD4`). |
| `gameOverFor` | ★ ve hře dvou hráčů číslo hráče, kterému došly životy, zatímco druhý hraje dál (`$AA64` ukáže `GAME OVER PLAYER x` a `$B205` stejně předá tah). 0 = nikomu. |
| `poem` | maska slok básně, kterou má hra ukázat. Sebrání kusu amuletu nastaví bit 7 v `+$0B` a `$A18C` ho na začátku dalšího kroku zhasne a skočí na `$A207`; kolik kusů hráč má, tolik slok se ukáže. **Zobrazení je M6**, tady se jen předává. |
| `labelFlash` | ★ `true`, dokud běží úvodní prodleva (`GameDelayTimer`, `$96B5`): `$AEA1` nasadí FLASH na tři buňky nápisu 1UP, resp. 2UP aktivního hráče, `$AEBD` ho po doběhnutí sundá. Model ho předává panelu. |

### `controls`

Stav ovládání, jak ho worker vidí. **Je to ladicí kanál**, ne herní data –
na Sabremanovi je od M3 vidět, kam jde. Zůstane, protože je to jediná odpověď
na otázku „došel ten dotek až do workeru?".

★ **Klávesy hry nejsou klávesy z instrukcí**: `Q` vlevo, `W` vpravo, `T` meč,
ale **`E` nahoru a `R` dolů** – originální instrukce tvrdí opak a mýlí se.
Změřeno v M3 dvakrát nezávisle (`sources/docs/disasm_notes.md` §14).

### `sounds`

Efekty, které v tom kroku vznikly – od M6 jako **objekty**, ne jména, protože
většina z nich má parametr, na kterém závisí výška tónu:

| jméno | rutina | parametry |
|---|---|---|
| `step` | `$BF4B` | `colour` – ★ pod modrozelenou orchidejí (`$45`) pípne rutina **dvakrát** |
| `fly` | `$A9F8` | `phase` – ★ **tón odletu je fáze odletu** |
| `land` | `$BF2F` | – |
| `orchid` | `$BF2A` | – |
| `orchidEnd` | `$BEC6` | – |
| `object`, `life` | `$BF25` | – |
| `explosion` | `$BEEE` | `sweeps`, `rand` – adresa, ze které originál čte délky tónů **z ROM** |
| `materialise` | `$BF08` | `sprite` – ★ každý druh zvířete zní jinak |
| `repel`, `keeper` | `$BF17` | – |
| `pointing` | `$BF3D` | `distance`, `x`, `y` – ★ **tón je vzdálenost ke kusu amuletu** |
| `fireball` | `$BECC` | `sweeps` |

★ **Sebrání kusu amuletu žádný zvuk nemá** (`$A1AB`), a proto tady žádné
`amulet` není; co je u něj slyšet, je hudba básně.

Počítadlo kroků (`$96B3`) worker **nevede**: patří jen zvuku, tak si ho drží
`audioManager`. Zvuky jednoho tiku se hrají **za sebou v jednom proudu**,
protože reproduktor je jeden a bit taky jeden.

Hudba (`MusicData_GameInitialisation`, `_Poem`, `_GameOver`, `_GameComplete`)
neprochází workerem vůbec – pouštějí ji modely, protože v originálu se hraje se
zakázaným přerušením, tedy když hra stojí (`audioManager.playMusic`).

### `state`

`game`, `gameOver`, nebo `complete`. ★ `complete` je jediné místo, kde hra končí
výhrou: `$A18C` na začátku každého kroku porovná obrazovku s `$88` a `y`
s `$80` a nad tou řádkou skočí na `GameComplete`.

### `poem`

Bity `$970D`, když v tom tiku hráč sebral kus amuletu – **událost jednoho
tiku**, ne stav, protože `$A18C` ten bit shodí a hned skočí na `$A207`.
★ Ukáže se **jedna** sloka, ta, která odpovídá počtu kusů (M6, `dumptext.py`),
a `roomModel` na tu dobu worker zastaví, protože originál při ní taky stojí.

## Co worker vědomě nemá

- **Nepřátelé** (M5): kdo se dá zabít a kdo jen zahnat, Sabre Wulf, strážce
  brány, ohnivá koule, bodování, střídání dvou hráčů. **Smrt Sabremana je
  hotová** (odlet, sezení, ubrání života, respawn na místě) – jen ji v M3 nemá
  co spustit, kromě sandboxu.
- **Jak co zní**: worker posílá, **co se stalo**, ne pulzy. Z čísel je zvuk
  dělá `app/beeper.js` (M6) tím, že rutiny originálu projde instrukci po
  instrukci a vede si T-stavy.
- **Náhoda**: originál míchá `Rand8` (`$9695`) obnovovacím registrem Z80 a bere
  z ní fázi seku mečem **a druh předmětu**; mapu předmětů navíc staví z bajtů
  **ROM Spectra** (`$A2BD`). Remake má vlastní počítadlo a vlastní zdroj bitů –
  jsou to jediná místa, která se tik po tiku reprodukovat nedají, a v porovnání
  se dosazují z nahrávky. Reprodukuje se **pravidlo i hustota**: originál plní
  55 % až 79 % slotů mapy podle toho, kde v ROM začne.
