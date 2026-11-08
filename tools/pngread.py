#!/usr/bin/env python3
"""Minimální čtečka PNG (bez závislostí, jen `zlib`) – opak `scr2png.write_png`.

Vznikla proto, aby `tools/mapworld.py` mohl **porovnat mapu světa z dat remaku
s dohledanou mapou** (`sources/media/maps/map_07.png`) strojově, ne od oka.
Umí jen to, co je k tomu potřeba: neprokládané PNG, hloubka 1/2/4/8 bitů,
paleta i šedá i truecolor. Nic víc.
"""
import struct, zlib


def read_png(path):
    """Vrátí `(šířka, výška, pole řádků s (R, G, B))`."""
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise SystemExit('%s: neni to PNG' % path)
    pos, idat, palette, header = 8, b'', None, None
    while pos < len(data):
        length, tag = struct.unpack('>I4s', data[pos:pos+8])
        payload = data[pos+8:pos+8+length]
        pos += 12+length
        if tag == b'IHDR':
            header = struct.unpack('>IIBBBBB', payload)
        elif tag == b'PLTE':
            palette = payload
        elif tag == b'IDAT':
            idat += payload
        elif tag == b'IEND':
            break
    width, height, depth, colour, _, _, interlace = header
    if interlace:
        raise SystemExit('%s: prokladane PNG neumim' % path)
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour]
    step = max(1, (depth*channels)//8)
    stride = (width*depth*channels+7)//8
    raw = zlib.decompress(idat)
    lines, previous, offset = [], bytearray(stride), 0
    for _ in range(height):
        filt = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset+stride])
        offset += stride
        if filt == 1:
            for i in range(step, stride):
                line[i] = (line[i]+line[i-step]) & 0xFF
        elif filt == 2:
            for i in range(stride):
                line[i] = (line[i]+previous[i]) & 0xFF
        elif filt == 3:
            for i in range(stride):
                left = line[i-step] if i >= step else 0
                line[i] = (line[i]+((left+previous[i]) >> 1)) & 0xFF
        elif filt == 4:
            for i in range(stride):
                a = line[i-step] if i >= step else 0
                b = previous[i]
                c = previous[i-step] if i >= step else 0
                p = a+b-c
                pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                line[i] = (line[i]+(a if pa <= pb and pa <= pc
                                    else (b if pb <= pc else c))) & 0xFF
        lines.append(line)
        previous = line

    def sample(line, x):
        if depth == 8:
            return line[x*channels:x*channels+channels]
        per = 8//depth
        shift = 8-depth*((x % per)+1)
        return [(line[x//per] >> shift) & ((1 << depth)-1)]

    pixels = []
    for line in lines:
        row = []
        for x in range(width):
            value = sample(line, x)
            if colour == 3:
                row.append(tuple(palette[value[0]*3:value[0]*3+3]))
            elif colour in (0, 4):
                grey = value[0]*(255//((1 << depth)-1))
                row.append((grey, grey, grey))
            else:
                row.append(tuple(value[:3]))
        pixels.append(row)
    return width, height, pixels
