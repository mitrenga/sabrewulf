# Data remaku

Stav M6. Všechno tady je **vytažené z originálu** – nic dokresleného.

| soubor | co je uvnitř | čím vzniklo |
|---|---|---|
| `global.json` | konstanty změřené na běhu: 50,08 Hz, **4 životy**, 1/2 hráči, rozvržení panelu, **výchozí síň slávy o šesti místech** a odměřený cyklus překlápění menu | `tools/mkglobal.py --verify` |
| `world.json` | **mřížka světa 16 × 16** z `Layout` (`$6066`), 48 ukazatelů `RoomTable`, **mapa přechodů spočítaná z kolizního pravidla hry** a ★ **startovní obrazovka 8,10** | `tools/dumpworld.py` |
| `scenery.json` | **41 kusů kulisy** (`Background Graphic $01`–`$29`, `$70BC`–`$9691`), pixely už odnegované + atributy | `tools/dumpgfx.py` |
| `rooms.json` | **48 předloh místností** – seznam kusů kulisy s pozicemi, jak je čte `DrawRoom` (`$BBF7`); X a Y jsou **surové bajty předlohy v pixelech**, protože kolize dolní bity X nezahazuje (M3) | `tools/dumprooms.py` |
| `physics.json` | **fyzika Sabremana** (M3): 69 konstant přečtených jako operandy skutečných instrukcí – zrychlení, strop rychlosti, tlumení, kolizní obálka, přechody obrazovek, tabulka vstupních x na `$6036`, pózy, smrt a respawn, a startovní záznam z `$AC77` | `tools/dumpphysics.py` |
| `entities.json` | **svět** (M4): 104 konstant přečtených jako operandy skutečných instrukcí a k nim tabulky – **25 slotů tabulky entit**, 11 nesmrtelných entit z `$AC77`, orchidej každé předlohy (stav, pozice, 16 barev, **pět účinků**), čtyři pozice předmětů v každé předloze a 16 druhů, **osm hotových sad amuletu** a předpočítaná tabulka **procent navštívených obrazovek** | `tools/dumpentities.py` |
| `monsters.json` | **nepřátelé** (M5): 148 konstant přečtených jako operandy skutečných instrukcí a k nim tabulky – ★ celá `JumpTable` (`$9B3E`, 196 sprite ID → obsluha), ze které vyjde **kdo je zničitelný a kdo se dá jen zahnat**, **šestnáct druhů zvířat** a jejich body, rychlosti zvířat, ohnivé koule i domorodců, jedenáct nesmrtelných entit s rolí, ohnivá koule a **dva hráči** | `tools/dumpmonsters.py` |
| `sounds.json` | **zvukové efekty** (M6): 30 konstant přečtených jako operandy skutečných instrukcí – ★ **celý zvuk hry jsou dvě rutiny**, `PlaySquareWave` (`$BF74`, jeden kmit délky `B`) a `PlayWaveSequence` (`$BF6D`, `C` kmitů), takže každý z deseti efektů je dvojice `(B, C)` nebo krátká smyčka, která `B` mění; k tomu tabulka délek ohnivé koule (`$BEDE`) a **kdy se který efekt volá** | `tools/dumpsound.py` |
| `music.json` | **hudba** (M6): tabulka not `MusicData` (`$BDD2`) – ★ **rovnoměrně temperovaná chromatická stupnice G#1–G6 o 61 položkách**, u každé půlperioda v T-stavech a frekvence, a **čtyři skladby** (`$BC67`, `$BD28`, `$BD33`, `$BD45`) jako surové bajty. ★ Položka 18 je kopie 17, takže v řadě chybí půltón – žádná skladba ho nehraje | `tools/dumpmusic.py` |
| `text.json` | **texty a obrazovka básně** (M6): **čtyři sloky** (`$A055`, `$A0A7`, `$A0F4`, `$A13B`) jako `x`, `y`, atribut a text, obrazovka po dohrání, `GAME OVER PLAYER n` a ★ **obrázek amuletu** – čtyři kusy z `$C374`, každý se **dvěma bloky atributů** (nalezený a ne) ve formátu kusu kulisy | `tools/dumptext.py` |
| `spriteframes.json` | **196 ID spritů a 153 různých snímků** ze `SpritesTable` (`$BF84`): Sabreman, zvířata, domorodci, orchideje, předměty, amulet, Sabre Wulf, strážce | `tools/dumpsprites.py` |
| `loading.json` | loading screen z originální kazety, celá obrazovka 256 × 192 | `tools/mkscreen.py` |
| `room000.json` | startovní obrazovka jako **skutečné bajty videopaměti**, vytažená většinovým hlasem z běhu originálu. Od M2 už to není zdroj obrázku, ale **nezávislá kontrola formátu** – viz níž | `tools/mkroom.py` |
| `sprites.json` | ikonka života z panelu (`UDG_Life`, osm bajtů, v runtime obrazu na `$B814`) | `tools/mksprite.py --raw` |

Bitmapy i atributy jsou base64 skutečných bajtů videopaměti. Celé obrazovky
(`loading`, `title`) jsou v jednom poli `videoRAM`: **6912 B tak, jak leží
v paměti stroje** od `$4000` do `$5AFF`, tedy včetně nelineárního adresování
ULA – přesně obsah `.scr` a přesně pořadí, ve kterém jdou po kazetě. Nic se
nikde nerozplétá: `ZXVideoRAM` drží paměť stejně a `tapeLoadingModel` do ní
bajty z datového bloku jen zapisuje. U kusů kulisy a spritů je bitmapa uložená
tak, jak je v paměti hry (řádek po řádku, šířka v bajtech), protože se z nich
obrazovka **skládá**, a to už umí `app/roomComposer.js`; `room000.json` má
kvůli tomu vlastní tvar (viz níž).

## Formát světa – proč takhle

Otázka byla stejná jako u underwurlde: jak uložit 256 obrazovek. Odpověď
z originálu je překvapivě malá a M2 ji celou ověřil:

- **Obrazovka je v hře popsaná jediným bajtem.** `Layout` (`$6066`) je
  256 bajtů, mřížka 16 × 16, a bajt je číslo předlohy v `RoomTable` (`$6166`).
- **Různých předloh je jen 48 a použitých 45** – nepoužité jsou `$01`, `$13`
  a `$24`, nejčastější `$11` je ve světě 21×. Tím je vysvětlená dobová výtka,
  že se obrazovky opakují.
- ★ **Předloha není obrázek, je to seznam kusů kulisy s pozicemi**: záznamy
  po čtyřech bajtech (adresa kusu, X, Y), terminátor `$0000`. Dohromady
  919 kusů na 48 předloh.
- ★ **Kus kulisy** je hlavička (výška v pixelech, šířka v bajtech), pixely
  **uložené znegovaně** a k tomu blok atributů.

Proto **žádných 256 souborů** a proto se všechno pošle rovnou v `appData`:

| soubor | velikost |
|---|---|
| `world.json` | ~24 kB |
| `scenery.json` | ~23 kB |
| `rooms.json` | ~12 kB |

Necelých **60 kB na všech 256 obrazovek**. Původní plán z M1 byl posílat kulisu
a předlohy „na vyžádání"; po odměření se ukázalo, že to není potřeba – jedna
jediná obrazovka jako hotové pixely (`room000.json`) je 9 kB, takže celý svět
stojí zhruba jako **sedm** hotových obrazovek z 256. `db/appData.php` je proto
posílá hned při startu.

Od M3 k tomu jdou **sprity** (`spriteframes.json`, ~48 kB), protože už je čím
hýbat, a **fyzika** (`physics.json`, ~18 kB); od M4 **svět**
(`entities.json`, ~53 kB) a od M5 **nepřátelé** (`monsters.json`, ~70 kB –
skoro celý je to `JumpTable` rozepsaná po jedné položce, aby si ji replika
nemusela dekódovat). Kulisu a předlohy k tomu potřebuje
kromě kreslení i worker: ★ **kolize se ptá na tentýž seznam kusů kulisy**, ze
kterého se místnost kreslí (`$B873`), takže fyzika chodí v týchž datech, ze
kterých je obrázek – a nemají jak se rozejít.

## Jak je to ověřené

Pixelově, ne od oka, a dvakrát nezávisle:

1. `tools/matchscreen.py` nahraje runtime obraz do simulátoru, položí do volné
   paměti `CALL ClearPlayArea` / `LD HL,předloha` / `CALL DrawRoom` a opíše, co
   po nich zůstalo ve videopaměti – tedy **obrazovku, kterou nakreslil
   originál**. Proti tomu pustí repliku v pythonu (`tools/roomlib.py`, ze které
   tahle data vznikají): **48 předloh + všech 256 obrazovek + místnost pod
   hlavním menu = 305 obrazovek, 5632 B bitmapy a 704 B atributů na obrazovku,
   nula rozdílů.**
2. `tools/matchrooms.js` zopakuje totéž s `app/roomComposer.js`, tedy
   **s kódem, který jde do prohlížeče** – taky nula rozdílů. Hlídá se tím
   i to, že se replika a prohlížeč nerozešly.

A do třetice `room000.json`: většinový hlas nad 131 snímky běžícího originálu
o formátu nepředpokládá **nic** a přesto se od poskládané předlohy `$08` liší
jen v 35 bajtech bitmapy a 114 atributech – a to jsou právě ty nehybné entity
(orchidej, předměty), které v kulise nejsou a **od M4 je kreslí worker**. Proto
ten soubor zůstává.

A od M4 k tomu přišla čtvrtá kontrola, na svět: `tools/traceentities.py`
nechá **originál spočítat sám sebe** – do volné paměti mu položí `LD IX,záznam`
/ `LD BC,obálka` / `CALL rutina` a opíše, co po ní zůstalo v „game status
bufferu" – a `tools/matchentities.js` proti tomu pustí `app/worldEntities.js`,
tedy zase kód, který jde do prohlížeče. Protože si originál počítá sám, dají se
projít **všechny** vstupy, ne vzorek: **21 444 kontrol ve třinácti případech,
nula rozdílů** (256 obrazovek, 48 předloh, 256 hodnot `Rand8`, 260 počtů
procent, 900 zavolání kvetení za sebou, 7 680 kombinací přímky s amuletem).

A od M5 pátá, na nepřátele, ve stejné disciplíně: `tools/tracemonsters.py`
nechá originál odbavit jednu obsluhu entity za druhou a `tools/matchmonsters.js`
proti tomu pustí `app/worldMonsters.js` – **29 817 kontrol v šestnácti
případech, nula rozdílů**, a k tomu **osmnáct hodnot hlášených jako
nereprodukovatelné** (svislá rychlost ohnivé koule v losovaném směru pochází
z obnovovacího registru Z80, `$9E24` `LD A,R`).

## Co tady vědomě není

**Znaková sada.** ★ A není to díra, je to nález: Sabre Wulf vlastní znakovou
sadu nemá. `PrintScreen` (`$B589`) spočítá adresu glyfu jako `($5C36) + kód*8`,
tedy z **`CHARS`** – systémové proměnné, kterou ROM nastavuje na `$3C00`, takže
glyf mezery leží na `$3D00`. Hra tiskne **ROM fontem ZX Spectra**. Proto
v `sources/asm/pobtastic-skoolkit/` žádná pojmenovaná není a proto se nedá
najít nikde v runtime obrazu (`$4000–$FFFF`) – je v ROM, mimo něj.

Ten font už svision má jako výchozí tabulku `ZXFonts8x8`
(`svision/fonts/zx-rom.ch8.hex.txt`), takže si ho panel bere odtud a datový
soubor pro něj nevzniká. A protože „je to ROM font" je tvrzení jako každé jiné,
dokazuje ho `tools/matchpanel.py`: postaví panel z té tabulky a porovná ho se
**třemi** snímky originálu bajt po bajtu – 512 bajtů bitmapy a 64 atributů,
**nula rozdílů**. Kdyby hra měla vlastní font, neshodlo by se to. Tím je
položka „`dumpfont.py` → `data/font.json`" z M2 uzavřená: **nevzniká**, a je to
odpověď, ne dluh.

**Mapa předmětů.** ★ Ta v datech není a nebude, protože ji originál **negeneruje
z dat, ale z ROM Spectra**: `$A2BD` čte 512 bajtů z adresy
`($9693 & $1F)*256 + FRAMES`, tedy z `$0000`–`$20FF`, a bajt pod `$80` znamená
„na téhle obrazovce předmět je". Runtime obraz je `$4000`–`$FFFF`, takže ROM
v našich podkladech vůbec není – a i kdyby byla, hra si adresu vybírá z běhových
počítadel. Remake proto reprodukuje **pravidlo i hustotu** (originál plní 55 %
až 79 % slotů podle toho, kde v ROM začne; jeden běh hry dal 358 z 512), ale
zdroj bitů je jeho vlastní. `matchentities.js` kontroluje **kde předmět je**
a **která ze čtyř pozic to je** proti bajtům ROM, které trasa zapisuje, a druh
předmětu hlásí jako nereprodukovatelný – bere se z `Rand8` míchaného obnovovacím
registrem Z80, přesně jako fáze seku mečem v M3
(`sources/docs/disasm_notes.md` §16).

**Mapa přechodů je spočítaná, ne přečtená – ale spočítaná z pravidla hry.**
V programu žádná tabulka průchodů není: ★ co je zeď, plyne z **obálek kusů
kulisy** (`$B873` prochází tentýž seznam, ze kterého se místnost kreslí,
a obálka Sabremana je 14 × 22 px). Od M3 z toho `dumpworld.py` počítá
`passages.exits` a `tools/mapwalk.py --verify --all` to **zkusil v běžícím
originálu: 904 hranic, 904 se chová přesně tak, jak pravidlo říká.** Proti
dobové mapě to dává svisle 240/240 a vodorovně 211/240 – a těmi 29 hranicemi,
které mapa kreslí zavřené, **hra projde**, takže je ta mapa stylizovaná
(`sources/docs/disasm_notes.md` §15). Pixelová metoda M2 zůstala jako druhá
cesta a rozchází se jen ve 4 hranicích z 960.

**Zvuk není nahraný, je spočítaný.** ★ Výška tónu na jednobitovém beeperu **je
počet T-stavů Z80**, takže `sounds.json` a `music.json` nenesou vzorky, ale
operandy instrukcí – `app/beeper.js` z nich rutiny originálu projde instrukci po
instrukci a vydá tentýž seznam zápisů do portu `$FE`. `tools/tracesound.py` +
`tools/matchsound.js` to porovnají **pulz po pulzu**: 63 038 kontrol
v patnácti případech, nula rozdílů, z toho 30 vteřin Bacha nota po notě.

**Délky tónů výbuchu tady nejsou a nebudou** – z téhož důvodu jako mapa
předmětů: `$BEEE` je čte z **ROM Spectra** na `($9693 & $1F)*256 + Rand8`.
Reprodukuje se pravidlo (šestnáct po sobě jdoucích bajtů z jedné adresy),
zdroj bitů je remaku vlastní (`app/audioManager.js`).

**Co v datech schválně není:** obrazy 256 místností (skládají se z kulisy),
mapa předmětů, znaková sada (je to ROM font ZX Spectra) a jakýkoli zvuk jako
vzorek. Všechno ostatní, čím hra vypadá a zní, tady je – a je změřené.
