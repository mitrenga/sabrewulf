![](/images/app-icon-256x256.png)

SABRE WULF
=====================
The legendary 8-bit classic, reborn for modern web browsers.

## About
Originally written in 1984 by Ultimate Play The Game. This is a faithful remake based on the original ZX Spectrum version — not an emulator or a binary copy.

Supported:
- keyboard
- mouse (menus and buttons; the game itself is played with the keyboard, a gamepad or the touchscreen)
- gamepad
- touchscreen
- PWA application

The story of the remake — what was measured on the original, how, and with what result — is in [MAKING-OF.md](MAKING-OF.md), together with the full sequence of tools that take the data out of the original tape.


## Play now
https://sabrewulf.remake.free


## Requirements
- PHP 8.1+
- nginx
- MySQL / MariaDB
- Node.js + terser, for building the bundle (`npm i -g terser`)
- es-check, for the ES2018 compatibility gate in `svtool verify` (`npm i -g es-check`)
- Python 3, only for the tools that extract and verify the data of the original (see `tools/README.md`)


## Install
(`~/` below refers to the project root, not your home directory.)
- clone this repository
- clone library repository https://github.com/mitrenga/svision
- check symlink ~/app/svision
- configure nginx (example: ~/config/nginx.conf)
- create path ~/js with permissions 0777
- create database (script: ~/config/createDB.sql)
- create configuration file ~/config/config.php (example: ~/config/config.php.sample)
- build the production bundle: ~/app/svision/tools/svtool build bundle

The data of the game (`data/`) is part of the repository. The original tape image is copyrighted and is **not** — it is needed only to regenerate that data, see `sources/tape/README.md`.


## Developer mode
Developer mode is switched in `~/config/config.php` (both settings are optional; without them the app runs in production mode):

```php
$devMode = true;
$devModeName = '.{\"penColor\":\"#000000\",\"bkColor\":\"#fefe00\",\"width\":185}◢◤ ◢◤ ◢◤ ◢◤  DEVELOPER MODE ◢◤ ◢◤ ◢◤ ◢◤';
```

`$devMode` values:
- `true` — development: JS sources are served directly instead of the bundle and the service worker is unregistered/bypassed
- `['serviceWorker' => true]` — development, but the service worker stays enabled (for testing SW behavior against a built `js/` deploy)
- `false` or not set — production: minified bundle + service worker

`$devModeName` is a label rendered in the top border of the game screen, so a development instance is recognizable at a glance. Set it to `false` (or leave it empty) to hide the label. The value is either plain text, or text prefixed with `.{...}` — a JSON object whose properties are applied to the label's TextEntity, typically:
- `penColor` — text color
- `bkColor` — background color
- `width` — label width in game pixels (the text is centered inside it)

The config is written into a double-quoted JavaScript string, so quotes inside the JSON prefix must be escaped as `\"` (see the example above).


## Build & tooling
The `svtool` CLI (`~/app/svision/tools/svtool`) builds and checks the deploy. Run it from the project root:
- `svtool build bundle` — minified production bundle `js/bundle.<version>.min.js` (requires terser)
- `svtool build debug-bundle` — the same concatenation left unminified, `js/bundle.<version>.js`, for debugging on a device whose console cannot be opened
- `svtool verify` — check the `js/` deploy is complete, matches the current sources, and stays within ES2018 (authoritative via es-check if installed, otherwise a heuristic scan)
- `svtool info` — show the app version, deploy state and the most recent database records
- `svtool clean` — remove everything generated from `js/`

Optional — run `svtool` from anywhere and enable bash completion (adjust the path to your svision clone):
- `sudo ln -s /path/to/svision/tools/svtool /usr/bin/svtool`
- `sudo ln -s /path/to/svision/tools/svtool-completion.bash /etc/bash_completion.d/svtool`

Open a new shell afterwards, then run `svtool <command>` from any project root.

Production serves the bundle; in development, with no bundle built, the sources under `app/` are served and loaded one by one through dynamic `import()`.


## License
See the [LICENSE](LICENSE) file.
