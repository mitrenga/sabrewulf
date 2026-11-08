#!/usr/bin/env python3
"""Nahraje **referenční běhy originálu** pro kontrolu fyziky remaku (M3).

    PYTHONPATH=tools/vendor ./tools/tracephysics.py [--out build/physics-traces.json]
                                                    [--scenario jmeno] [--print]

Každý scénář je krátký skript kláves (u smrti k tomu jeden zápis do paměti,
který udělá to, co v hotové hře udělá zvíře – to je M5). **Krok po kroku**
Sabremana, ne snímek po snímku (`tools/physlog.py`), se zapisuje:

* 12 B záznamu Sabremana (`$9702`) na **vstupu** kroku i na jeho **výstupu**
* `$96AD` (šířka pro odchod vpravo), `$96AC` (naposledy přečtené ovládání),
* `$96B4` (nedotknutelnost po respawnu), `$96B5` (`GameDelayTimer`),
* `$96BD` (životy), `$9695` (`Rand8` – z něj je fáze seku), `$5C78` (`FRAMES`)
* které klávesy jsou v tom kroku stisknuté a kolik snímků krok trval

`tools/matchphysics.js` proti tomu pustí `app/sabremanPhysics.js` a hlásí
každý rozdíl – obdoba `matchscreen.py` pro fyziku. Trasy se do gitu nedávají
(jsou v `build/`), vyrobí se z kazety kdykoli znovu.

★ Proč krok a ne snímek: **přechod mezi obrazovkami trvá jeden krok Sabremana,
ale šest snímků ULA** (hra při něm překresluje celou hrací plochu). To je
časování Z80, ne pravidlo hry; remake má jeden krok na tik a rozdíl patří
k porovnání s emulátorem v M7. Kolik snímků který krok trval, je proto
v trase zapsané (`frames`).
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'vendor'))
sys.path.insert(0, HERE)

import physlog                                                   # noqa: E402

OUT = os.path.join(HERE, '..', 'build/physics-traces.json')

PLAYER = physlog.PLAYER
WIDTH = (0x96AD, 1)            # o kolik dřív než na x=256 se odchází vpravo
CONTROLS = (0x96AC, 1)         # co naposledy přečetl HandlerControls
UNTOUCHABLE = (0x96B4, 1)      # $80 po respawnu i po přechodu obrazovky
DELAY = (0x96B5, 1)            # GameDelayTimer
LIVES = (0x96BD, 1)
RAND = (0x9695, 1)             # Rand8 – fáze seku mečem
FRAMES = (0x5C78, 2)           # počítadlo ULA, na kterém visí fáze chůze

WATCH = [WIDTH, CONTROLS, UNTOUCHABLE, DELAY, LIVES, RAND, FRAMES]

STATE = PLAYER+2               # +2: 0 = živ, jinak odpočet smrti


def kill(state):
    """Zabije Sabremana tak, jak to udělá kontakt s entitou (`$AB5E`).

    `$AB65` zapíše do `+2` jedničku nebo dvojku podle toho, ze které strany
    kontakt přišel, a obsluha `$A985` z toho udělá odlet doprava, nebo doleva.
    V hotové hře to dělá zvíře nebo domorodec (M5); tady se to zapíše rovnou,
    protože smrt a respawn jsou fyzika, a ta je M3.
    """
    def poke(mem):
        mem[STATE] = state
    return poke


# scénáře: jméno, poznámka, kolik snímků, skript kláves, (příprava, snímek)
SCENARIOS = [
    ('stand', 'stání na startovní obrazovce – nic se nemá hýbat', 700, [], None),
    ('walkRight', 'chůze vpravo: zrychlení po 7/16 px, strop $30 a zaražení '
     'o kulisu na x=$C1', 780, ['620:780:W'], None),
    ('walkLeft', 'chůze vlevo přes celou obrazovku', 800, ['620:800:Q'], None),
    ('walkUp', 'chůze vzhůru (klávesa E!) až za horní hranu – přechod do '
     'obrazovky nad a vstup na y=$BF', 800, ['620:800:E'], None),
    ('walkDown', 'chůze dolů (klávesa R!) až na kulisu na y=$86',
     780, ['620:780:R'], None),
    ('diagonal', 'osmisměrná chůze: obě osy zrychlují zvlášť, ale póza se bere '
     'z vodorovného směru', 780, ['620:780:W+E'], None),
    ('sword', 'tasený meč na místě: sprity $20–$2F a náhodná fáze z Rand8',
     760, ['620:760:T'], None),
    ('swordWalk', 'chůze vpravo s taseným mečem – rychlost natvrdo $20, tedy '
     '2 px za krok proti 3 px bez meče', 780, ['620:780:T', '620:780:W'], None),
    ('swordRelease', 'puštění meče v běhu: zpátky na pózu chůze a znovu '
     'zrychlování', 800, ['620:800:W', '620:700:T'], None),
    ('crossRight', 'nahoru do obrazovky 8,9 a z ní vpravo – přechod vpravo '
     'a vstup na x=$00', 860, ['620:700:E', '720:860:W'], None),
    ('crossDown', 'nahoru do obrazovky 8,9 a zpátky dolů – přechod dolů '
     'a vstup na y=$27', 900, ['620:700:E', '760:900:R'], None),
    ('death', 'zabití vpravo: odlet ($40), dosednutí ($41), smrt ($42), '
     'ubrání života a respawn na místě', 840, ['620:660:W'], (kill(1), 660)),
    ('deathLeft', 'zabití vlevo: odlet ($44) na druhou stranu',
     840, [], (kill(2), 660)),
]


def hexs(data):
    return ''.join('%02X' % b for b in data)


def run_scenario(name, note, frames, keys, setup):
    keyscript = physlog.parse_keys(keys)
    poke, poke_frame = setup if setup else (None, physlog.FIRST_FRAME)
    log = physlog.run_steps(frames, keyscript, WATCH, setup=poke,
                            setup_frame=poke_frame)
    out, prev_frame = [], None
    for frame, rec, extra, _, out_rec, out_extra in log:
        if frame < physlog.FIRST_FRAME:
            continue
        width, controls, untouchable, delay, lives, rand, ula = extra
        pressed = []
        for start, end, group in keyscript:
            if start <= frame < end:
                pressed += group
        if out:
            out[-1]['frames'] = frame-prev_frame
        prev_frame = frame
        out.append({
            'frame': frame,
            'frames': 1,
            'keys': pressed,
            'rec': hexs(rec),
            'recOut': hexs(out_rec) if out_rec else None,
            'width': width[0],
            'controls': controls[0],
            'untouchable': untouchable[0],
            'delay': delay[0],
            'lives': lives[0],
            # ★ Rand8 i FRAMES se berou z **výstupu** kroku: `$99D0` míchá
            # `Rand8` z obnovovacího registru Z80 hned na začátku kroku, takže
            # hodnota z jeho vstupu je ještě ta předchozí
            'rand': out_extra[5][0] if out_extra else rand[0],
            'ula': (out_extra[6][0] | out_extra[6][1] << 8) if out_extra
                   else (ula[0] | ula[1] << 8),
            'ulaIn': ula[0] | ula[1] << 8,
        })
    return {'name': name, 'note': note, 'firstFrame': physlog.FIRST_FRAME,
            'keys': keys, 'kill': setup[0].__doc__ if setup else None,
            'steps': out}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--scenario', action='append', help='jen tyhle scénáře')
    ap.add_argument('--print', action='store_true', dest='show',
                    help='vypsat záznamy na terminál')
    args = ap.parse_args()

    wanted = set(args.scenario or [])
    scenarios = []
    for name, note, frames, keys, setup in SCENARIOS:
        if wanted and name not in wanted:
            continue
        scenario = run_scenario(name, note, frames, keys, setup)
        scenarios.append(scenario)
        rows = scenario['steps']
        changed = sum(1 for i, r in enumerate(rows) if i and r['rec'] != rows[i-1]['rec'])
        slow = [r['frame'] for r in rows if r['frames'] > 1]
        print('%-13s %4d kroku, %3d zmen zaznamu, %d kroku delsich nez snimek  (%s)'
              % (name, len(rows), changed, len(slow), note.split(' – ')[0][:48]))
        if args.show:
            for r in rows:
                print('   %4d %s -> %s  %s' % (r['frame'], r['rec'],
                                               r['recOut'], ','.join(r['keys'])))

    if scenarios:
        steps = sum(len(s['steps']) for s in scenarios)
        slow = sum(1 for s in scenarios for r in s['steps'] if r['frames'] > 1)
        longest = max((r['frames'] for s in scenarios for r in s['steps']), default=0)
        print('kroku dohromady %d, z toho %d delsich nez jeden snimek '
              '(nejdelsi %d snimku – to je prekresleni obrazovky pri prechodu)'
              % (steps, slow, longest))

    if wanted:
        return
    out = {
        'note': ('M3: referencni behy originalu pro kontrolu fyziky remaku '
                 '(tools/tracephysics.py). Porovnava se tools/matchphysics.js. '
                 'Vzorkuje se na krok Sabremana ($99D0/$99F0), ne na snimek.'),
        'player': '$%04X' % PLAYER,
        'watch': ['$96AD width', '$96AC controls', '$96B4 untouchable',
                  '$96B5 delay', '$96BD lives', '$9695 rand', '$5C78 frames'],
        'scenarios': scenarios,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w') as f:
        json.dump(out, f)
        f.write('\n')
    print('ulozeno %s (%d kB)' % (os.path.relpath(args.out),
                                  os.path.getsize(args.out)//1024))


if __name__ == '__main__':
    main()
