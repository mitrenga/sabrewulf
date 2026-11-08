#!/bin/sh
# Z kazety udělá snapshot a surový obraz RAM. Potřebuje sources/tape/*.tzx
# (do gitu nepatří, viz sources/tape/README.md) a vendorovaný SkoolKit v tools/vendor.
#
# Pozor: hra je na kazetě **zašifrovaná** (CPL přes $8000–$FBFF) a dešifruje se
# až za běhu. Snapshot z tap2sna.py je proto ten správný obraz – dešifrování
# udělá sama hra před tím, než se zastaví na --start. Viz sources/asm/README.md.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SK="$ROOT/tools/vendor"
TZX="$ROOT/sources/tape/Sabre Wulf (1984)(Ultimate Play The Game).tzx"
mkdir -p "$ROOT/build"
[ -f "$TZX" ] || { echo "chybi $TZX – viz sources/tape/README.md"; exit 1; }
PYTHONPATH="$SK" python3 "$SK/skoolkit-10.1.data/scripts/tap2sna.py" \
    --sim-load-config accelerator=speedlock \
    "$TZX" "$ROOT/build/sabrewulf.z80"
PYTHONPATH="$SK" python3 - "$ROOT" <<'PY'
import sys
from skoolkit.snapshot import Snapshot
root = sys.argv[1]
ram = bytes(Snapshot.get(root + '/build/sabrewulf.z80').ram(-1))
open(root + '/build/sabrewulf.bin', 'wb').write(ram)
scr = open(root + '/sources/media/screens/loading_screen.scr', 'rb').read()
print('RAM $4000-$FFFF: %d B; loading screen souhlasi s .scr: %s'
      % (len(ram), ram[:6912] == scr))
PY
# Hra je zašifrovaná – runtime obraz udělá až mkruntime.py (nechá ji doběhnout do menu).
PYTHONPATH="$SK" python3 "$ROOT/tools/mkruntime.py"
