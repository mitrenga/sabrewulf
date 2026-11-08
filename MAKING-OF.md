SABRE WULF — MAKING OF
=====================
Faithful browser remake of the 1984 Ultimate Play The Game ZX Spectrum classic — work in progress.

## About
Released by Ultimate Play The Game in mid-1984 for the 48K ZX Spectrum, the first part of the
Sabreman series — the one that Underwurlde, Knight Lore, Pentagram and Mire Mare follow.
Sabreman is dropped into a jungle maze of 256 flick-screens and has to find the four pieces of
the ACG amulet, get past the guardian of the gate and escape, while the unkillable Sabre Wulf
prowls the paths. Its defining ideas are the maze itself — 256 screens built from only 48
templates — and the orchids, which bloom for a few seconds and change what Sabreman is: faster,
slower but invulnerable, or unable to tell left from right. The original game logic is being
rewritten in JavaScript from the original instructions and the disassembly of the game (not
emulated) — see `ZADANI.md` for the design and `MILNIKY.md` for the plan. Sibling projects:
Underwurlde (same hero, same hardware, same discipline), Manic Miner, Jet Set Willy,
Nodes of Yesod, Cheeky Mouse, Stinger, Pleiads.

Status: **M6** — the game can be played from beginning to end, and now it looks
and sounds like the original. Sabreman walks the original's step
for step (2 323 steps of recorded play, zero differences), the orchids bloom and do to him what
they do in the original, the amulet lies in one of the eight sets the game hides it in, and now
the jungle is inhabited: the animals materialise and can be cut down, the rhinos, natives and
hippos can only be driven off, Sabre Wulf charges down the row of the world you are standing in,
and the keeper of the gate steps aside for four pieces of the amulet and kills for three. 29 817
checks against the original, zero differences.

M6 gave it a voice and finished the picture: every sound is one of the ten
routines of the original run instruction by instruction, the four tunes play —
including the Bach prelude that sits under the main menu — the verses of the
poem appear over the picture of the amulet, and the sprites are drawn through
the machine's own screen addressing, wrap and all. 63 038 checks of the sound
pulse by pulse and 5 336 064 checks of the picture byte by byte, zero
differences in both.

The interesting part of M0 was getting to a readable image of the game at all. Sabre Wulf ships
**encrypted**: everything from `$6000` up is stored on tape with every byte complemented, and a
21-byte routine at `$5B80` walks over it before the game starts. A snapshot taken from the tape
is therefore not the game — `tools/mkruntime.py` lets the original decrypt itself in a simulator
and takes the memory afterwards. With that in hand, three things fell out of the data at once:
the world is a **16 × 16 grid of 256 bytes** at `$6066`, each byte naming one of **48 room
templates** — of which only **45** are ever used, which is the answer to the contemporary
complaint that screens repeat; the panel is two character rows carrying **1UP, lives, HI and
2UP** with three six-digit scores, so two-player play and the hall of fame are *fidelity* here,
not additions the way they were in Underwurlde; and the game really does count the **percentage
of rooms visited** (`PrintRoomsVisited`, 256 bits at `$96BF`), which Underwurlde, despite what
the magazines wrote, never did.

Unlike Underwurlde, a usable public disassembly exists — pobtastic/ultimate has 321 named
labels for Sabre Wulf against 8 for Underwurlde. It says *where* things are, rarely *what they
do*, so the open questions in `ZADANI.md` §7 still have to be measured; but the map is good.

M1 built the application on svision — menu, tape loading show, title screen, game screen,
pause, hall of fame, about, settings, and keyboard, gamepad **and touch** controls, the
last of those in M1 rather than at the end, which is the lesson of Underwurlde. The game screen
is one **real screen of the original**: `tools/mkroom.py` runs the game in a simulator, walks
Sabreman around the starting screen and takes the byte-wise majority over 131 sampled frames, so
whatever moves does not survive the vote and what is left is the jungle as the original drew it.
Sabreman was deliberately **not** drawn until his physics had been measured — inventing a walk
would be the one thing this project does not do. M3 measured it, so he walks.

Four things got measured on the way, and one of them was an open question that turned out to
have a surprising answer. **Sabre Wulf has no character set of its own**: `PrintScreen` (`$B589`)
works the address of a glyph out of `CHARS` (`$5C36`), so the game prints with the **ZX Spectrum
ROM font**. That is why no character set is named in the disassembly and why none can be found
anywhere in the runtime image — it is in the ROM, outside it. `tools/matchpanel.py` proves it by
rebuilding the panel from that font and comparing it with three captured frames byte for byte:
512 bytes of bitmap and 64 attributes, **zero differences**. The other three: the player starts
with **four lives** (`$96BD` is set to 5 and the first Sabreman spends one); the game's own
**hall of fame has six places** with three-letter names, its default table sits at `$B304`, and
its top entry `102275 ULT` is the `HI` the panel shows the moment you switch on; and the menu
**flips over to that hall of fame every sixteen seconds** and back (823 / 802 frames, measured
over 20 000 of them). All four are written up in `sources/docs/disasm_notes.md` §8–§10.

M2 took the graphics and the world out of the program. ★ **A room in Sabre Wulf is not a picture,
it is a list of pieces of scenery with positions**: `DrawRoom` (`$BBF7`) reads four-byte records —
the address of a piece, then X and Y — until it hits `$0000`, and one of the **41 pieces of
scenery** is a header (height in pixels, width in bytes), its pixels stored **complemented**, and
a block of attributes. That is why 256 screens fit in a few kilobytes: `world.json`,
`scenery.json` and `rooms.json` together are under **60 kB for all 256 screens**, about what
seven of them would cost as finished pixels. The plan from M1 to deliver scenery on demand turned
out to be unnecessary, so `appData` simply sends the lot.

It is checked the way the panel was, only bigger. `tools/matchscreen.py` loads the runtime image
into a simulator, drops `CALL ClearPlayArea` / `LD HL,template` / `CALL DrawRoom` into spare
memory and copies out whatever the **original itself** left in video memory; against that it runs
the python replica the data is made with. **48 templates + all 256 screens of the world + the
room under the main menu = 305 screens, 5632 bytes of bitmap and 704 attributes each, zero
differences.** `tools/matchrooms.js` then repeats it with `app/roomComposer.js` — the code that
actually goes to the browser — for zero differences again, so the replica and the browser cannot
drift apart. And M1's majority vote, which assumed nothing at all about the format, agrees with
composed template `$08` to within 35 bytes: exactly the standing entities the scenery does not
contain.

Two more things got measured. ★ **The game starts on column 8, row 10** — `$B21E` copies 144
bytes from `$AC77` into the game status buffer and the second byte of the first record is the
room, `$A8`; the simulator confirms it independently. And the sprites: `SpritesTable` (`$BF84`)
holds **196 IDs pointing at 153 different frames**, stored the other way round from the scenery
(width in bytes, then height), with no mask and no colour of their own.

The one thing M2 could not settle it said so about: there is no table of passages in the program,
so the map of transitions was **derived** from gaps at the edges of the drawn screens and checked
against Einar Saukas's map of 2012. Every one of the 240 vertical borders agreed; only 209 of the
240 horizontal ones did, and the 31 that did not were determined by the pair of templates but
*not* by the geometry of their edges — two templates with a byte-identical right edge behaved
differently. **M3 settled it**, see below.

M3 is Sabreman's physics, and the thing that made the rest of it fall into place is how the game
asks about a wall. ★ **It does not look at pixels.** `$B873` walks the very list of scenery
pieces the room is drawn from and takes each piece's **bounding box** out of its own header;
Sabreman's box is `LD BC,$160E` — 14 pixels across, 22 down, with `x` his left edge and `y` his
**bottom** row. A wall is therefore slightly bigger than what is drawn, which is precisely the
rule that could not be read out of the pixels. The rest of the walk is in the same spirit:
`$07` of speed per pressed direction per frame, capped at `$30` (3 px a step) and decaying by
`$01`, the two axes independent — so a diagonal is √2 faster — and ★ **with the sword drawn
Sabreman is slower**, because `$ADD0` writes the speed flat at `$20` (2 px) with no acceleration
and no decay at all. That closes an open question, and it also disposes of a contemporary POKE:
the addresses the tips files list as "walk speed" (`$AE83`, `$AE85`) are in `HandlerOrchidTimer`
and mean "an orchid's effect never runs out".

Three findings were surprises. ★ **`E` is up and `R` is down** — the other way round from the
printed instructions, measured both in the record and in the pixels of a running original.
★ **Eight-way movement has four poses**: the horizontal direction is decided last in `$B053`
and overwrites the vertical, so a diagonal looks like walking sideways. And ★ **the game is won
in exactly one place**: `$A18C`, at the top of every step, compares the screen with `$88` and
`y` with `$80`; the keeper who is supposed to stop anybody without the amulet is an entity, not
part of that test.

It is checked the way everything else here is checked. `tools/tracephysics.py` records runs of
the original **step by step rather than frame by frame** — it stops in the entity loop at `$99D0`
and `$99F0`, because a screen transition is one step of Sabreman but six to eight frames of the
original's main loop — and `tools/matchphysics.js` runs `app/sabremanPhysics.js`, the code that
goes to the browser, against those recordings: **2 323 steps in thirteen scenarios, 12 bytes of
record each, zero differences.**

★ And that rule settled M2's open question. Passability is now **computed** from the collision
rule instead of guessed from pixels, and `tools/mapwalk.py --verify --all` starts the original in
a simulator, puts Sabreman next to each border and holds the key: **904 borders, all 904 behave
exactly as the rule says** — 628 open ones crossed, 276 walled ones did not — and the game
crosses **all 29** of the borders the contemporary map draws closed. So the map is stylised in
those places, and the derived one is right. Two things came out of the same measurement: the
narrowest passage in the world is **2 pixels** wide, which is why the game keeps a 48-byte table
at `$6036` of the x to snap to when entering a screen from above; and 51 borders are one-sided —
you can leave the screen but the way in is inside the scenery, so `$B81C` puts Sabreman back a
step, in the new screen already.

M4 is the world: what lies in it and what it does to Sabreman. Almost all of it hangs off one
byte. ★ **Taking an orchid writes the orchid's own colour into Sabreman's attribute** (`$A754`),
and that single byte is the whole of the effect: `$42` red makes him slower (2 px a step), `$43`
magenta **reverses all four directions**, `$45` cyan makes him faster (4 px), `$46` yellow ★ **sits
him down and he cannot move** — which is the answer to what the yellow orchid does, a thing the
contemporary tips files are silent about — and `$47` white does nothing at all. Two consequences
fall out of the same byte and are in none of the tips: while any effect runs, the sword **cannot
be drawn** (`$AF55` only lets a white Sabreman draw it), and he is **untouchable**, because
`$AB36` compares the colour with `$47` and returns without killing him for anything else. That is
where the contemporary POKE "invincibility to jungle animals" comes from. An effect lasts `$C0`
half-frames — 384 frames, 7.7 seconds — and flashes white and beeps for the last `$2F`.

★ **An orchid's state is kept per template, not per screen.** `HandlerOrchidType` indexes
`TableOrchidTypes` with the template out of `Layout`, so all 21 screens of template `$11` share
one orchid: it goes on blooming while Sabreman is elsewhere, and the colour of the next bloom is
drawn from `OrchidColour` when it closes — a table of sixteen in which **four are white**, so one
bloom in four is worth nothing.

★ **The amulet is not hidden at random.** `Rand8 & 7` picks one of **eight ready-made sets** of
four screens (`$A29D`), and where in the screen a piece lies is decided by the template. A piece
is worth 7500 and reveals a verse of the poem. The natives that point at a buried piece work by
a rule as plain as it is clever: ★ in the same **column** of the world as a piece and within 16
pixels of its x, or the same **row** and its y, and then the native is drawn **yellow** for that
one pass — which is why it flickers — and beeps a tone **whose pitch is the distance**.

Two more measurements were needed to get any of it right. ★ **`$9693` is not a frame counter but
a counter of sweeps of the entity loop** — the loop resumes where the interrupt left it, and a
sweep takes about two frames (0.508 sweeps per frame, measured) — and the orchid's phase and the
amulet's flash hang off it, so the remake does one sweep per tick and the comparison is sweep
against sweep. And ★ **the map of objects is generated out of the Spectrum ROM**: `$A2BD` reads
512 bytes from `($9693 & $1F)*256 + FRAMES`, and a byte under `$80` means "there is an object on
this screen". The ROM is not in our sources at all, so that — along with the object's kind, which
comes from `Rand8` stirred by the Z80 refresh register — is the one thing in M4 the remake cannot
repeat byte for byte, the same kind of hole as the phase of the sword swing in M3. The rule and
the density are reproduced; the source of the bits is ours.

Odds and ends the same pass settled: an object is worth **150 points whatever kind it is**, one
kind (`$85`) is a life instead, ★ **lives cap at nine**, and ★ the percentage the game prints
counts the four pieces of the amulet in, so the whole is **260** and a single screen is worth
less than half a percent.

The verification is in the discipline of `matchscreen.py` rather than `matchphysics.js`: the
**original computes it itself**. `tools/traceentities.py` puts `LD IX,record` / `LD BC,box` /
`CALL routine` into free memory and copies out what the routine left in the game status buffer,
and `tools/matchentities.js` runs `app/worldEntities.js` — the code that goes to the browser —
against that. Because the original does the work, every input can be walked instead of a sample:
**21 444 checks in thirteen cases, zero differences** — 256 screens, 48 templates, all 256 values
of `Rand8`, all 260 counts of the percentage, 900 consecutive calls of the bloom, and 7 680
combinations of a native standing in line with the amulet.

M5 is everything that can kill you — and the thing that made it fall into place is one table.
★ **Which entity is which is not a matter of opinion or of looking at sprites.** The game
dispatches every entity through `JumpTable` (`$9B3E`): the handler is `JumpTable[sprite ID]`, 196
entries ending exactly on `PrintRoomsVisited`. Read it and the open question of what can be
killed answers itself: **only what the game puts into the world itself** — the sixteen animals of
`SpriteReference`, three of which are chasers that add `$08` a sweep towards Sabreman up to his
own top speed. The rhinos, the natives, the hippos, Sabre Wulf and the keeper are **driven off**,
never killed, and always in the direction Sabreman happens to be facing.

★ **The game gets harder as you collect the amulet, and nothing says so.** `$A3E0` counts the
pieces in `$970D` and only lets the draw reach `pieces*2 + 8` of the sixteen kinds, so with
nothing collected the first eight can turn up and with the whole amulet all sixteen.

★ **Sabre Wulf does not hunt — he waits for your row.** `$A922` leaves him standing until
Sabreman is in the same **row of the world**, and then he charges straight along it at 4 px a
step, faster than Sabreman can run. The sword drives him off, and `$A964` brings him back with
`$20` more speed than he had: drive him off often enough and you build an unstoppable wolf.

★ **`$96B4` is not what M3 took it for.** M3 wrote it down as the invulnerability after a
respawn; the only routine that reads that byte is `$9ABC`, and what it does on zero is put a
**fireball** on the screen. `$B148` sets it back to `$80` on every screen change, so the
contemporary claim that standing still in a room earns you a fireball is exactly right — and the
other half of that claim, a big bonus for surviving ~30 s, is **not in the code at all**. The
fireball gets a slot of its own among the immortal entities: `$9762`, the one M4 found empty.
★ Its homing has a bug that is reproduced here: `$9E4E` writes the **horizontal** speed where it
means the vertical one, so the fireball never comes up at Sabreman from below.

★ **The keeper kills through an orchid.** Every other entity goes through `$AB36`, which refuses
anything but a white Sabreman — that is what makes an orchid protect him. The keeper calls
`$AB3D`, one step below that test.

★ **And the two-player bug the 1984 reviews complained about is one instruction.** When a player
dies in a two player game, `$AA5A` hands over to `$B205`, which swaps the two players' entire
state (`$B235`: lives, visited rooms, the map of objects and the whole entity table) and **then**
calls `$B1B7` — and `$B1B7` is where the `DEC (HL)` on the life counter is. So the life comes off
the player who is arriving, not the one who died. Measured on the running original: 5/3, swapped
to 3/5, and after `$B1B7` **2/5**. In a one player game `$AA27` takes the other road, which is
why it never shows. It is reproduced, because that is the rule of this project.

Odds and ends the same pass settled: an enemy is worth **165 or 185 points** (`$A4B3` builds the
number out of bits 1-2 of the sprite ID), the percentage of the world seen **does not enter the
score** at all, walking into an animal without the sword kills Sabreman **and** blows the animal
up, an animal is never placed inside the scenery — a `RET C` on a discarded call to `$B81C` does
the work of a test nobody wrote — and `GameDelayTimer` is `$80` for one player and for two, not
`$FF` as the public disassembly's comment claims.

The verification is M4's discipline: `tools/tracemonsters.py` has the original run one entity
handler after another and `tools/matchmonsters.js` runs `app/worldMonsters.js` — the code that
goes to the browser — against it. **29 817 checks in sixteen cases, zero differences**, and
eighteen values reported as unreproducible: the fireball's vertical speed in its random direction
comes out of the Z80 refresh register (`$9E24` `LD A,R`), the same kind of hole as the phase of
the sword swing in M3 and the kind of an object in M4.

M6 is what the game looks and sounds like. ★ **The whole of its audio is two
routines.** PlaySquareWave ($BF74) flips bit 4 of port $FE up, waits B times
round a DJNZ, flips it down and waits B times again — one square cycle, and the
pitch is B and nothing else — and PlayWaveSequence ($BF6D) does C of them, so
the length is C and nothing else. There is no envelope, no sample table and no
noise generator anywhere in the program: each of the ten sounds is a pair
(B, C) or a short loop that moves B. ★ The one for driving an animal off makes
its pitch with **`DAA`** — the Z80's decimal adjust used as a tone generator —
★ the native's pitch **is the distance** to the buried piece of the amulet that
M4 measured, ★ the tone of Sabreman's death flight **is the phase of the
flight**, and ★ the sixteen tone lengths of an explosion are **bytes of the
Spectrum's ROM**, the same well of randomness the map of objects comes from and
the same hole in the remake.

Because the pitch of a beeper tone is a **count of Z80 T-states**, `app/beeper.js`
does not approximate those routines with oscillators: it runs them instruction
by instruction, keeping the clock rather than the registers, and emits the very
list of speaker writes the original would make. `tools/tracesound.py` puts a
port tap on the simulator and records every `OUT ($FE),A` the original really
does, with its time; `tools/matchsound.js` compares the two **pulse by pulse**:
**63 038 checks in fifteen cases, zero differences**, thirty seconds of music
among them. A mistake of one T-state in one instruction shows up as a
difference rather than as a slightly wrong note.

★ **And the music is where Sabre Wulf differs from Underwurlde**, which had
none. The table at $BDD2 turns out to be an **equally tempered chromatic scale**
from about G#1 to G6 — provable, because the delay loop is not B*C: `DJNZ` runs
B times only the first time round, so the pair (B, C) is a linear count of
B + 256*(C-1), and in that measure the neighbouring entries are semitones to
within a few cents. ★ It has **61 entries and not 64**, because a **routine is
hidden inside it**: past the last entry sits `LD BC,$A008` / `JP $BF6D`, the
beep of an orchid running out, which is why the public disassembly lists it as
data and never named it. ★ And **one rung of the ladder is broken**: entry 18 is
a byte-for-byte copy of entry 17, so a semitone is missing from the scale —
none of the four tunes plays that note, which is probably why nobody noticed.
★ The last surprise is where the Bach is: `HandlerGameMenu` ($B3EC) plays
MusicData_GameComplete through PlayAudio_WaitKey, the variant that reads the
keyboard between notes, so the prelude is **the first thing you hear from Sabre
Wulf** and stops the moment you touch the controls.

The picture got the same treatment. M2 settled the room; M6 is its other half,
the sprites. ★ **The attribute clash does not come from the scenery, it comes
from `$BB47`**, which writes an entity's colour only into cells whose paper is
black: the jungle keeps its colours and the figure takes the black between
them, and since one attribute covers eight pixels by eight, a sixteen pixel
wide Sabreman repaints two cells or three. ★ **And the drawing does not stop at
the edges.** It addresses with `INC L` inside a page, so a sprite that runs off
the right hand side comes back on the left eight pixels lower, and the only
write the original guards is the **last one of a row** ($BAEE), which is why a
sprite at the very edge loses its last byte instead of wrapping it; a 32 pixel
tall keeper of the gate near the top of the play area writes over the panel.
Both happen in the game, so both are reproduced rather than clipped, and
`tools/matchsprites.js` therefore compares **all 6912 bytes of video memory**
against what the original left there: **5 336 064 checks on 772 screens, zero
differences**.

★ **The verses of the poem show one at a time, and M4 had that wrong.**
DisplayPoem ($A01B) counts the pieces in $970D and jumps to the single verse
that matches — one piece, one verse — not to all the ones so far. And it is not
only text: $A207 clears the play area and draws the **picture of the amulet**
out of a table at $C374, where each of the four pieces carries **two blocks of
attributes** and $96B2 picks the bright one for a piece already found. Then the
verse, MusicData_Poem, and eight rounds of a delay loop so the player can read
it. All sixteen combinations of pieces are in `tracescreen.py`, and all sixteen
match byte for byte.

Two more things the same pass settled. ★ **The border is black for the whole
game** — $9963 clears it at GameInitialisation and no other write of a colour
to that port exists in the program, the sound routines only knocking it back to
black — and the single exception is the **pause**, where $AC40 adds $04 to a
counter every frame and makes the colour out of bit 7, so the border alternates
blue and magenta every 32 frames until SPACE is pressed again. That closes the
last open question of ZADANI chap. 7. ★ And taking a piece of the amulet is
**silent**: $A1AB only adds 7500 points and sets the poem bit, so what you hear
at that moment is the poem's music.

## Getting the sources

The tape image is copyrighted and is **not in the repository**. See `sources/tape/README.md`
for where to get it and how to verify it, then:

```sh
./tools/mksnapshot.sh                                    # tape -> snapshot + runtime image
PYTHONPATH=tools/vendor ./tools/playtrace.py --map build/coverage.txt

PYTHONPATH=tools/vendor ./tools/dumpgfx.py               # the 41 pieces of scenery
PYTHONPATH=tools/vendor ./tools/dumprooms.py             # the 48 room templates
PYTHONPATH=tools/vendor ./tools/dumpworld.py             # the world grid and the transitions
PYTHONPATH=tools/vendor ./tools/dumpsprites.py           # 196 sprite IDs, 153 frames
PYTHONPATH=tools/vendor ./tools/dumpphysics.py --png     # Sabreman's physics, and a pose sheet
PYTHONPATH=tools/vendor ./tools/dumpsound.py --print     # the ten sounds, as (B, C)
PYTHONPATH=tools/vendor ./tools/dumpmusic.py --print --abc  # the scale of 61 notes and four tunes
PYTHONPATH=tools/vendor ./tools/dumptext.py --print      # the poem, the amulet picture, the endings
PYTHONPATH=tools/vendor ./tools/mkroom.py                # the starting screen, real pixels
PYTHONPATH=tools/vendor ./tools/mkglobal.py --verify     # measured constants
./tools/mkworld.py                                       # the 16 x 16 world grid
./tools/mkscreen.py sources/media/screens/loading_screen.scr data/loading.json
./tools/mksprite.py sources/media/screens/gameplay_start.scr 9 0 1 1 --group panel --name life --raw
(cd images && ../app/svision/tools/make-app-icons && ../app/svision/tools/make-favicon)  # icon PNG set + favicon from app-icon.svg
```

Then check it against the original and build:

```sh
./tools/matchpanel.py        # the panel vs three captured frames, byte for byte
./tools/matchpanel.js        # the same, with the code that goes to the browser
PYTHONPATH=tools/vendor ./tools/matchscreen.py   # 305 screens vs the original's own DrawRoom
./tools/matchrooms.js        # the same, with the code that goes to the browser
PYTHONPATH=tools/vendor ./tools/tracephysics.py  # record runs of the original, step by step
./tools/matchphysics.js      # the remake's physics vs those runs, step by step
PYTHONPATH=tools/vendor ./tools/mapwalk.py --verify --all   # walk every border in the original
PYTHONPATH=tools/vendor ./tools/tracesound.py    # what the original sends to the speaker
./tools/matchsound.js        # the remake's beeper vs those pulses, pulse by pulse
PYTHONPATH=tools/vendor ./tools/tracescreen.py   # the original draws the sprites itself
./tools/matchsprites.js      # the remake's picture vs that video memory, byte by byte
./tools/runworker.js         # the whole worker loop, headless

cp config/config.php.sample config/config.php && $EDITOR config/config.php
mysql < config/createDB.sql
svtool build bundle          # or: svtool build debug-bundle
svtool verify
```

## Layout

| | |
|---|---|
| `ZADANI.md` | design of the remake, rules, open questions |
| `MILNIKY.md` | milestones M0–M7 |
| `app/` | the application (svision), `app/WORKER-PROTOCOL.md` for the game worker |
| `data/` | data extracted from the original (index in `data/README.md`) |
| `config/`, `db/` | server side: build list, nginx, database commands |
| `sources/` | everything gathered from the original (index in `sources/README.md`) |
| `tools/` | extraction and verification tools (index in `tools/README.md`) |
| `build/`, `js/` | generated, not in git |

## License
Code: CC BY-NC-SA 4.0 (see `LICENSE`). Sabre Wulf, its graphics, sounds and design are the
property of their rightful owners (Ashby Computers & Graphics Ltd. / Rare / Microsoft);
nothing copyrighted is redistributed here.
