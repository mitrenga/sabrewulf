# Nástroje

Nic z toho se neinstaluje do systému – všechno běží z tohoto adresáře.

| skript | co dělá |
|---|---|
| `mksnapshot.sh` | z kazety v `sources/tape/` udělá `build/sabrewulf.z80` a surový obraz RAM `build/sabrewulf.bin` (`$4000–$FFFF`, 49 152 B); ověří, že loading screen v paměti souhlasí s `sources/media/screens/loading_screen.scr`, a hned zavolá `mkruntime.py` |
| `mkruntime.py` | **runtime** obraz RAM `build/sabrewulf-run.bin`. Hra je na kazetě zašifrovaná (`CPL` od `$6000` výš) a dešifruje se až za běhu, takže kazetový obraz neobsahuje instrukce. Nástroj nechá hru v simulátoru doběhnout do titulní obrazovky a teprve pak opíše paměť; zkontroluje, že na `$6000` je `F3 31 00 60 C3` a na `$6007` text copyrightu, jinak skončí chybou. **Tenhle obraz je jediný správný pro disassembly a extrakci dat** (viz `sources/docs/disasm_notes.md` §1) |
| `playtrace.py` | spustí hru v simulátoru, odsimuluje stisky kláves (po půlřádcích jako na skutečném Spectru) a uloží snímky obrazovky (PNG + `.scr`) a mapu pokrytí kódu (`--map`). Skript kláves je nahoře v souboru v `SCRIPT`; výchozí projde menu (1 hráč, klávesnice, start) a kus chůze doprava |
| `scr2png.py` | ZX `.scr` (6912 B) → PNG; implementuje nelineární adresování obrazovky |
| `mkroom.py` | **statická startovní obrazovka ze skutečných pixelů**: hra běží v simulátoru, Sabreman ji projde do všech čtyř směrů a ze 131 vzorků (snímky 480–1000 po čtyřech) se po bajtech vybere nejčastější hodnota – co se hýbe, tím většinovým hlasem neprojde. Výstup `data/room000.json` + náhled `build/room000.png`; `--diff-frame N,M` uloží snímky a vypíše mapu měnících se buněk (tím se hledají sprity). Od M2 to není zdroj obrázku, ale **nezávislá kontrola formátu místnosti** – a rovnou odměří, ★ **která z 256 obrazovek je startovní** (`$9703`, sloupec 8 řádek 10) |
| `mkscreen.py` | ZX `.scr` → datový soubor remaku (`data/loading.json`), celá videopaměť tak, jak leží v paměti stroje. **Řezat z ní kusy kulisy neumí schválně**: džungle je v `data/scenery.json` z ROM a předlohy říkají, kde který kus leží |
| `mkspritegfx.mjs` | sprity z pole `sprites` datového souboru (videopaměť) → mřížka znaků a paleta do pole `graphics`, **nekomprimovaně** a rovnou v tom tvaru, který bere `SpriteEntity.setGraphicsData()` (týž, jaký vrací `SpriteTool.decode()`). Mřížku kontroluje **druhým, nezávislým čtením barev** (`ZXColor.penAttrColor`/`bkAttrColor` proti bitové aritmetice nad atributem) – čeká **nulu rozdílů**. Každá barva ZX má svůj znak (`+` zelená, `$` jasně zelená, `^` žlutá, `*` jasně červená …), **černá je průhledná a píše se mezerou** (`--opaque` ji nechá jako barvu), `--dump jmeno` vypíše mřížku. ★ **Na kulisu se nepoužívá** – místnosti skládá `roomComposer.js` do videopaměti a zápis natvrdo se s průhledným spritem rozejde (v šesti předlohách ze 48 o 844 pixelů); tenhle tvar je pro dekoraci mimo simulaci. Dnes ho nic v datech nepoužívá |
| `mksprite.py` | vyřízne sprite ze snímku proti statické obrazovce; `--raw` neodečítá pozadí (panel). Zatím z něj vzniká jen ikonka života (`UDG_Life`, `$B814`) |
| `mkworld.py` | mřížka světa 16 × 16 z `Layout` (`$6066`) a 48 ukazatelů `RoomTable`; kontroluje, že platí, co o té tabulce víme (45 použitých předloh, nepoužité `$01`/`$13`/`$24`), jinak spadne. Od M2 je to **druhé, nezávislé přečtení mřížky** – píše do `build/world-m1.json`, aby data remaku nepřepsalo; `data/world.json` dělá `dumpworld.py` |
| `mkglobal.py` | změřené konstanty → `data/global.json`: výchozí síň slávy z `$B304`, `GameDelayTimer`, cyklus překlápění menu. S `--verify` odsimuluje start hry a **ověří počet životů** |
| `roomlib.py` | **formát místnosti a kulisy na jednom místě**: čte 41 kusů kulisy, 48 předloh a mřížku světa a umí **věrně překreslit** místnost – replika `DrawRoom` (`$BBF7`) včetně inverze pixelů, přepisování natvrdo a osmibitových přetečení adresování. Není to nástroj, je to knihovna pro všechny `dump*` a `match*` (`../sources/docs/disasm_notes.md` §12) |
| `dumpgfx.py` | **41 kusů kulisy** (`$70BC`–`$9691`) → `data/scenery.json` + náhledy `build/gfx/pieceXX.png`. Kusy prochází podle jejich vlastních hlaviček a spadne, když blok neskončí přesně na `$9692` nebo když některý kus nepoužívá žádná předloha |
| `dumprooms.py` | **48 předloh místností** z `RoomTable` (`$6166`) → `data/rooms.json`; kontroluje, že konec jedné předlohy je začátek další. K tomu **49. předloha `Room_Special_MainMenu` (`$61C6`)** do pole `mainMenu` – džungle pod hlavním menu, týž formát, jen mimo `RoomTable`; kontroluje se, že končí přesně tam, kde začíná `Room_00`. Náhledy `build/rooms/templateXX.png` **kreslí originál v simulátoru**, ne nástroj |
| `dumpworld.py` | mřížka světa, ★ **startovní obrazovka** (z `$AC77`, sloupec 8 řádek 10) a **mapa přechodů** → `data/world.json`. Od M3 se počítá z **kolizního pravidla originálu** (`$B873`: obálky kusů kulisy proti obálce Sabremana 14 × 22 px) a hranice je průchodná, když je volno z obou stran; pixelová metoda M2 zůstala jako druhá cesta a nástroj vypíše, ve kolika hranicích se rozcházejí (jsou to 4 z 960) |
| `dumpsprites.py` | **196 ID a 153 snímků** ze `SpritesTable` (`$BF84`) → `data/spriteframes.json` + náhledy `build/sprites/spriteXX.png`. Jména snímků jsou z veřejné disassembly a tak jsou i označená |
| `mapworld.py` | mapa světa z dat remaku: text do konzole, schéma `build/worldmap.png`, `--mosaic` mozaika všech 256 skutečných obrazovek. **`--check` ji porovná s dobovou mapou** (`../sources/media/maps/map_07.png`) – svisle 240/240, vodorovně 211/240, a těch 29 rozdílů vypíše i s tím, že je M3 rozhodl ve prospěch dat (§15) |
| `mapwalk.py` | **průchodnost světa z kolizního pravidla – a její ověření na originálu** (M3). `--check` porovná s dobovou mapou a `--verify [--all]` spustí originál v simulátoru, postaví Sabremana k hranici a drží směrovou klávesu: ★ **904 hranic, 904 se chová přesně tak, jak pravidlo říká** (628 otevřených prošlo, 276 zazděných ne) – včetně všech 29 sporných. Tím je uzavřená otevřená otázka M2 (§13 → §15) |
| `dumpphysics.py` | **fyzika Sabremana** → `data/physics.json` (M3): 69 konstant, každá přečtená jako **operand skutečné instrukce** (okolní bajty se kontrolují, jinak nástroj spadne) – zrychlení, strop rychlosti, tlumení, kolizní obálka, přechody obrazovek, 48bajtová tabulka vstupních x na `$6036`, pózy, smrt a respawn. `--png` uloží náhledový list póz do `build/gfx/sabreman-poses.png` |
| `physlog.py` | knihovna i nástroj: **vzorkuje záznam Sabremana krok po kroku, ne snímek po snímku**. Zastavuje se na `$99D0` (vstup kroku ze smyčky entit) a `$99F0` (výstup) a filtruje podle `IX`, protože týmiž adresami procházejí i ostatní entity. Spuštěný přímo vypíše, které bajty záznamu se v okně měnily – tím se hledá, který offset je x, y a fáze |
| `tracephysics.py` | **referenční běhy originálu** → `build/physics-traces.json` (M3): třináct scénářů (stání, chůze do všech směrů, úhlopříčka, meč, přechody obrazovek, dvě smrti) a u každého kroku 12 B záznamu na vstupu i výstupu, klávesy, `Rand8`, `FRAMES`, životy a **kolik snímků krok trval** |
| `matchphysics.js` | **fyzika remaku proti fyzice originálu, krok po kroku**: vezme vstupní záznam z trasy, pustí na něj `app/sabremanPhysics.js` – tedy kód, který jde do prohlížeče – a porovná s tím, co vyšlo originálu. ★ **2 323 kroků ve 13 scénářích, 12 B na krok, nula rozdílů** |
| `matchscreen.py` | **obrazovky remaku proti originálu, bajt po bajtu**: runtime obraz se nahraje do simulátoru, do volné paměti se položí `CALL ClearPlayArea` / `LD HL,předloha` / `CALL DrawRoom` a co po nich zůstane ve videopaměti, je skutečná obrazovka originálu. Proti tomu se pustí replika (`roomlib.py`): **48 předloh + 256 obrazovek + místnost pod menu = 305 obrazovek**, cíl **nula rozdílů**. `--dump` uloží referenci pro `matchrooms.js` (**49** obrazovek: 48 předloh a za nimi místnost pod menu) |
| `matchrooms.js` | totéž, ale **skutečným kódem, který jde do prohlížeče** (`app/roomComposer.js`) nad `data/scenery.json` a `data/rooms.json`. Hlídá dvě věci naráz: shodu s originálem a to, že se `roomComposer.js` a `roomlib.py` nerozešly. Kromě 48 předloh a 256 obrazovek měří i **místnost pod hlavním menu**, kterou skládá titulní obrazovka |
| `pngread.py` | minimální čtečka PNG (jen `zlib`), aby `mapworld.py --check` mohl dobovou mapu porovnat strojově, ne od oka |
| `matchpanel.py` | **panel remaku proti třem snímkům originálu, bajt po bajtu** – nezávislou implementací v pythonu. Staví ho z tabulky fontu svision (= ROM font ZX Spectra, kterým hra tiskne) a z ikonky života; cíl **nula rozdílů**. Je to zároveň důkaz nálezu, že hra vlastní znakovou sadu nemá |
| `matchpanel.js` | totéž, ale **skutečným kódem, který jde do prohlížeče** (`app/screenComposer.js`, `panelMemory()`). Hlídá tedy dvě věci naráz: shodu s originálem a to, že se render a python replika nerozešly |
| `dumpentities.py` | **svět z originálu** → `data/entities.json` (M4): 104 konstant, každá jako **operand skutečné instrukce**, a k tomu tabulky – 25 slotů tabulky entit, 11 nesmrtelných entit z `$AC77`, orchidej každé předlohy (stav, pozice, barvy, **pět účinků**), čtyři pozice předmětů v předloze a 16 druhů, **osm hotových sad amuletu** a předpočítaná tabulka procent. U každé tabulky se navíc kontroluje, že **končí přesně tam, kde začíná něco jiného, co je pojmenované nezávisle** (`ObjectLocation` končí na mapě předmětů, `TableOrchidPositions` na snímku spritu `$0D`, sady amuletu na rutině `$A2BD`) – dohromady **106 kontrol** |
| `traceentities.py` | **referenční běhy světa**: nechá **originál spočítat sám sebe** – do volné paměti mu položí `LD IX,záznam` / `LD BC,obálka` / `CALL rutina` a opíše, co po ní zůstalo v „game status bufferu". Disciplína `matchscreen.py`, ne `tracephysics.py`, a proto se dají projít **všechny** vstupy: 256 obrazovek, 48 předloh, 256 hodnot `Rand8`, 260 počtů procent, 900 zavolání kvetení za sebou, 7 680 kombinací přímky s amuletem. K simulátoru se přitom nahraje i **ROM Spectra**, kterou přiváží SkoolKit – hra z ní bere mapu předmětů |
| `matchentities.js` | **svět remaku proti světu originálu** – kódem, který jde do prohlížeče (`app/worldEntities.js`). Cíl **nula rozdílů**; dosaženo: **21 444 kontrol ve třinácti případech**. Z trasy se replice předávají `FRAMES` a počítadlo průchodů smyčkou entit (na nich visí kvetení a blikání) a bajty ROM; **druh předmětu** se hlásí jako nereprodukovatelný, protože je z `Rand8` míchaného obnovovacím registrem Z80 |
| `dumpmonsters.py` | **nepřátelé z originálu** → `data/monsters.json` (M5): 148 konstant jako **operandy skutečných instrukcí** a k tomu tabulky – ★ celá `JumpTable` (`$9B3E`, 196 sprite ID → obsluha, končí přesně na `PrintRoomsVisited`), ze které vyjde **rozdělení na zničitelné a nezničitelné**, šestnáct druhů zvířat (`SpriteReference`), rychlosti zvířat, koule i domorodců, jedenáct nesmrtelných entit s rolí a **body za nepřítele**. Dohromady **166 kontrol** |
| `tracemonsters.py` | **referenční běhy nepřátel**: tatáž disciplína jako `traceentities.py` – originál si to spočítá sám. Šestnáct případů: body za všech 196 sprite ID, kontakt po mřížce póz a poloh, odraz od okrajů, stěhování po 6 364 kombinacích obrazovek, zhmotnění pro všechny počty kusů amuletu, průchod po průchodu u zvířete, naháněče, nosorožce, hrocha, domorodce, Sabre Wulfa, strážce i koule, dosazování zvířat a **střídání hráčů, na kterém je vidět ta dobově vytýkaná chyba** |
| `matchmonsters.js` | **nepřátelé remaku proti originálu** – kódem, který jde do prohlížeče (`app/worldMonsters.js`, k tomu `sabremanPhysics.js` na kulisu a `worldEntities.js` na ukazování k amuletu). Cíl **nula rozdílů**; dosaženo: **29 817 kontrol v šestnácti případech**. Nereprodukovatelná je jediná hodnota – svislá rychlost ohnivé koule v losovaném směru, protože `$9E24` je `LD A,R` |
| `dumpsound.py` | **zvukové efekty z originálu** → `data/sounds.json` (M6): 30 konstant jako **operandy skutečných instrukcí**. ★ Celý zvuk hry stojí na dvou rutinách – `PlaySquareWave` (`$BF74`) udělá jeden kmit délky `B`, `PlayWaveSequence` (`$BF6D`) jich udělá `C` – takže každý z deseti efektů je dvojice `(B, C)` nebo smyčka, která `B` mění. ★ Najde i rutinu `$BEC6`, která leží **uvnitř tabulky not**, a napíše, že sebrání kusu amuletu je **němé** |
| `dumpmusic.py` | **hudba z originálu** → `data/music.json` (M6): tabulka `MusicData` (`$BDD2`) a čtyři skladby. ★ Spočítá z půlperiod, že je to **rovnoměrně temperovaná chromatická stupnice**, a **zkontroluje to** – kdyby to neplatilo, spadne. ★ Konec tabulky drží rutina `$BEC6` (61 položek, ne 64) a ★ položka 18 je **kopie 17**, takže v řadě chybí půltón. `--abc` vypíše skladby jako noty |
| `dumptext.py` | **texty a obrazovka básně** → `data/text.json` (M6): čtyři sloky, obrazovka po dohrání, `GAME OVER` a ★ **obrázek amuletu** z `$C374`, kde má každý kus **dva bloky atributů**. ★ A zapíše, že `DisplayPoem` ukazuje **jednu** sloku podle počtu kusů, ne všechny předchozí |
| `tracesound.py` | **co originál pošle do reproduktoru** → `build/sound-traces.json` (M6). K simulátoru se přidá odposlech portu a zapíše se **každý `OUT ($FE),A` i s časem v T-stavech**; patnáct případů od všech 256 hodnot `B` po **všechny čtyři skladby celé**. `--wav` uloží nahrávky k poslechu |
| `matchsound.js` | **zvuk remaku proti originálu, pulz po pulzu**: pustí `app/beeper.js` – kód, který jde do prohlížeče – a porovná **každý zápis, jeho čas i celkovou délku rutiny**. Dosaženo: **63 038 kontrol v patnácti případech, nula rozdílů**. ★ Výška tónu **je** ten čas, takže chyba jednoho T-stavu v jedné instrukci se pozná jako rozdíl, ne jako trochu falešný tón |
| `tracescreen.py` | **originál nakreslí sprity sám** → `build/sprite-screens.bin` (M6): do volné paměti se položí `CALL ClearPlayArea` / `CALL DrawRoom` / `CALL DrawEntity` / `CALL $BB24` a opíše se videopaměť. Šest případů: všech 196 sprite ID, všech 256 vodorovných poloh, celá svislá, šestnáct barev proti čtyřem předlohám, nejširší sprity u pravého okraje a ★ **celá obrazovka básně** pro všech 16 kombinací kusů amuletu |
| `matchsprites.js` | **obraz remaku proti originálu, buňku po buňce** – kódem, který jde do prohlížeče (`app/screenComposer.js`, `app/roomComposer.js`). Porovnává **celých 6912 bajtů videopaměti**, protože kreslení originálu se u okrajů nezastaví. Dosaženo: **5 336 064 kontrol na 772 obrazovkách, nula rozdílů** |
| `runworker.js` | celá smyčka `app/gameWorker.js` bez prohlížeče (node, atrapa workeru): `init`, `controls` se dvěma směry naráz, `tick`, `pause`/`continue`, `reset` – a od M3 i to, že Sabreman **začíná tam, kde začíná originál**, že `GameDelayTimer` drží ovládání vypnuté prvních `$80` snímků a že se pak s drženým `right` rozejde do změřené rychlosti. Od M4 k tomu, že se na startovní obrazovce objeví **orchidej té předlohy**, že se obrazovka označí jako navštívená a že amulet leží v jedné z osmi sad, a od M5, že se do 400 průchodů dosadí nepřítel a že se **odpočet do ohnivé koule** (`$96B4`) opravdu ubírá |

## `vendor/` – SkoolKit 10.1

Na tomhle stroji není `pip` ani `python3-venv`, takže je SkoolKit **rozbalený z wheelu**
do `tools/vendor/` a spouští se přes `PYTHONPATH`:

```sh
PYTHONPATH=tools/vendor python3 tools/vendor/skoolkit-10.1.data/scripts/tap2sna.py --help
```

Do gitu nepatří – viz `.gitignore`.

Užitečné skripty SkoolKitu pro tenhle projekt:
`tap2sna.py` (kazeta → snapshot, umí Speedlock), `trace.py` (běh se záznamem instrukcí
a pokrytím), `sna2skool.py` / `sna2ctl.py` (disassembly), `snapinfo.py --find` (hledání
v paměti), `sna2img.py` (obrazovka → PNG), `tapinfo.py`, `rzxplay.py`.

## Co teprve vznikne

Podle `../MILNIKY.md` – pojmenované po vzoru underwurlde, aby se daly porovnávat:

- **M0**: `swdis.py` (disassembler rozsahu runtime obrazu), `memtrace.py`
  (trasování s pořadím instrukcí a přístupy do paměti). ~~`dumpfont.py`~~ **nebude**:
  hra vlastní znakovou sadu nemá, tiskne ROM fontem ZX Spectra
  (`../sources/docs/disasm_notes.md` §8)
- **M3**: ~~`dumpphysics.py`, `tracephysics.py`, `matchphysics.js`~~ **hotovo**
  (k tomu `physlog.py` a `mapwalk.py`); `renderframe.js` nevznikl – náhled
  obrazovky se spritem se dá vyrobit přímo `app/screenComposer.js` v node
- **M4**: ~~`dumpentities.py`, `traceentities.py`, `matchentities.js`~~ **hotovo**;
  `checkworld.py` nevznikl – kontrolu světa dělá `matchentities.js` tím, že
  projde **všech 256 obrazovek a 48 předloh**, takže by nekontroloval nic
  navíc
- **M5**: ~~`dumpmonsters.py`, `tracemonsters.py`, `matchmonsters.js`~~ **hotovo**
- **M6**: ~~`dumpsound.py`, `tracesound.py`, `matchsound.js`, `tracescreen.py`,
  `matchsprites.js`, `dumpmusic.py`~~ **hotovo**, a k tomu `dumptext.py`
  (sloky básně, obrázek amuletu a hlášky konce hry) – texty se ukázaly být
  data jako každá jiná, takže mají svůj `dump*`. `renderframe.js` nevznikl ani
  tady: náhled obrazovky vyrobí `tracescreen.py --png` přímo z toho, co
  nakreslil originál

Pravidlo, které se osvědčilo u underwurlde a platí i tady: **`dump*` čte konstanty
jako operandy skutečných instrukcí** (okolní bajty se kontrolují, jinak nástroj
spadne), **`trace*` nahrává, co dělá originál**, a **`match*` proti tomu pouští kód,
který jde do prohlížeče**. Cíl je vždycky nula rozdílů.

K tomu **`mk*` bylo provizorium milníku M1**: bralo z originálu to, co bylo
potřeba, aby aplikace běžela, ale o formátu dat netvrdilo nic. M2 je vyměnil –
`data/world.json` píše `dumpworld.py` místo `mkworld.py` a obrazovka se skládá
z předlohy a kusů kulisy místo `data/room000.json`. `mkroom.py` a `mkworld.py`
ale zůstávají: `mkroom.py` je **nezávislá kontrola** toho formátu (většinový
hlas o něm nepředpokládá nic a shodne se) a `mkworld.py` je druhé, nezávislé
přečtení mřížky.
