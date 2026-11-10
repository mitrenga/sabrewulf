const { Version } = await import('./version.js?ver='+window.srcVersion);
const { AbstractApp } = await import('./svision/js/abstractApp.js?ver='+window.srcVersion);
const { AudioManager } = await import('./audioManager.js?ver='+window.srcVersion);
const { ZXFonts8x8 } = await import('./svision/js/platform/canvas2D/zx/zxFonts8x8.js?ver='+window.srcVersion);
const { Fonts5x5 } = await import('./svision/js/platform/canvas2D/fonts5x5.js?ver='+window.srcVersion);
const { Fonts3x3 } = await import('./svision/js/platform/canvas2D/fonts3x3.js?ver='+window.srcVersion);
const { ZXResetModel } = await import('./svision/js/platform/canvas2D/zx/zxResetModel.js?ver='+window.srcVersion);
const { MenuModel } = await import('./menuModel.js?ver='+window.srcVersion);
const { AboutModel } = await import('./aboutModel.js?ver='+window.srcVersion);
const { HallOfFameModel } = await import('./hallOfFameModel.js?ver='+window.srcVersion);
const { RoomModel } = await import('./roomModel.js?ver='+window.srcVersion);
const { GameOverModel } = await import('./gameOverModel.js?ver='+window.srcVersion);
const { TapeLoadingModel } = await import('./tapeLoadingModel.js?ver='+window.srcVersion);
const { ZXErrorEntity } = await import('./svision/js/platform/canvas2D/zx/zxErrorEntity.js?ver='+window.srcVersion);
const { Tool } = await import('./svision/js/tool.js?ver='+window.srcVersion);
const { ZXColor } = await import('./svision/js/platform/canvas2D/zx/zxColor.js?ver='+window.srcVersion);
// begin code

/**
 * Sabre Wulf application shell (M1 skeleton, built on the Underwurlde one —
 * the closest sibling: the same company, the same hero, the same year, the
 * same machine and a ZX game with rooms on ZXPlatform).
 * LoadingModel -> MenuModel -> RoomModel (the game) -> GameOverModel, plus
 * TapeLoadingModel, HallOfFameModel and AboutModel off the menu.
 *
 * ★ There is no title screen of its own since 2026-09-07: the original's game
 * selection screen (Room_Special_MainMenu, $61C6) is the jungle the menu sits
 * in, so START GAME goes straight into the game (startRoom). The jungle and
 * the panel of that screen live on under the hall of fame and ABOUT GAME
 * (hallOfFameModel.js, aboutModel.js), its prelude under ABOUT GAME only.
 *
 * Two things are different from Underwurlde, and both because they are in
 * the original rather than because they are nice to have:
 *
 * - **Two players in the program.** GameOptions ($9692) is 0 for one player
 *   and 1 for two, the panel carries 1UP and 2UP always, and there are two
 *   life counters and two scores in memory. The worker and setPlayers() keep
 *   both, but ★ since 2026-09-07 (ZADANI chap. 6) the remake **offers one
 *   player only**: the menu has START GAME, the panel shows 1UP and HI.
 * - **Music.** The program has four MusicData_* blocks and the routines to
 *   play them. Underwurlde had neither, because it has no music at all. The
 *   tunes go over the one `sounds` bus, so there is one volume (SOUNDS).
 *
 * The game state kept here is the measured one: four lives and a starting HI
 * of 102275, both read off the running original (data/global.json,
 * tools/mkglobal.py). The scoring table, the amulet and the world come later.
 */
export class GameApp extends AbstractApp {

  /** the original's own choice: 1UP or 2UP (GameOptions, $9692) */
  static get PLAYERS() { return [1, 2]; }

  constructor(platform, importPath, wsURL, devModeName, appIconSprite) {
    super(platform, 'bodyApp', importPath, wsURL);

    this.worker = new Worker(this.importPath+'/gameWorker.js?ver='+window.srcVersion);
    this.worker.onmessage = (event) => {
      if (this.model) {
        this.model.handleWorkerMessage(event);
      }
    };

    this.version = Version;
    this.devModeName = devModeName;
    this.appIconSprite = appIconSprite;

    this.audioManager = new AudioManager(this);
    // one switch for both buses: the music follows the sounds (menuModel.js)
    this.muted = {sounds: false};

    // ★ No game font is loaded into any of these, and that is the finding, not
    // an omission: Sabre Wulf prints with the **ZX Spectrum ROM font** —
    // PrintScreen ($B589) takes the glyph out of CHARS ($5C36) — and that ROM
    // font is exactly what svision's ZXFonts8x8 carries as its default table
    // (svision/fonts/zx-rom.ch8.hex.txt). See screenComposer.js and
    // tools/matchpanel.py, which proves it against three captured frames.
    this.fonts = {
      zxFonts8x8Mono: new ZXFonts8x8(this, false),
      zxFonts8x8: new ZXFonts8x8(this, true),
      zxFonts8x8Keys: new ZXFonts8x8(this, false),
      zxFonts8x8Title: new ZXFonts8x8(this, true),
      fonts5x5: new Fonts5x5(this),
      fonts3x3: new Fonts3x3(this)
    };
    // the name of the game in the panel (GameInfoEntity.gameTitle): the font
    // of Cimmerjan (1993, Sindicato del Software), svision/fonts/cimmerjan.ch8.hex.txt
    this.fonts.zxFonts8x8Title.setFontsData('0000000000000000181818181800180000363624000000000000000000000000000000000000000000626408102646000038603762623C000018306000000000000C181818180C000030181818183000000000000000000000000000000000000000000000181830000000007E00000000000000000030300000000000000000003C6E6E76763C000018381818183C00003C660E3C707E00003C660C06663C00000C1C2C4C7E0C00007C607C06663C00003C607C66663C00007E060C0C181800003C663C66663C00003C66663E063C00000018180018180000001818001818300000000000000000000000047E0400000000000000000000003C660C1800180000000000000000005C7666667E667600DC76667C6676DC000E3240C0C2E67C00E070686C6666FC00FE60FC60607AC600C67A6060FC6060000E3060C6CEF66E00C0606C7E7666C2003818181818183C007618189898D87000E66870786C64F6007030303030323E0044EEFED6D6D64400CCD6D6E6C4C8DE001C3666C6C67C3800F86C66766C60F0003E6CCCDC6C0C1E00EE72666C786CE6003C66603C86C67C00EE3C7060666C3800F62646CED6D66600E6646868707060003462C2CADA7E2400C66C3838386CC600CCCE4E3606CC78007E460C1830627E000018001818181818DFCCD3E3C6C8D6000018001830663C00000000000000000000000000000000FF0000000000000000003E6646464E3600006E76647C667C00003E626060623E00780C3E6666663C00003C666C7E603E00006E726060F86060003A6E663E26663C00606C7666646E000C00381818181C00003E0606664E3C0000666468786C66003030303030303C00005A756D696A6B00005C766262646E0000003E6363633E00006C7666667C606000366E666E3E0606006C76666C786E00003C603C06663C000030FE6060623C0000662666466E36000076366262663C0000EB6BCBDBD36D0000663C18183C660000666426361C7800007E060C18307E00309F3FFF00FFFFFF3E5C766262646E0066006626466E360000000000000000003C429DB1B19D423C');
    // the keycap font of the on-screen keyboard (ZXPlayerNameEntity), the same
    // glyphs as in the other games
    this.fonts.zxFonts8x8Keys.setFontsData('00000000000000000010101010001000002424000000000014147E28FC505000107C507C14547C1042A44810244A8400001028102A443A00000810000000000000182020202018000030080808083000000014083E081400000008083E0808000000000000080810000000003E00000000000000001818000204081020408000007C4C5454647C000018280808083E00007C440438407C00007C441804447C00001828487E081C00007C407C04447C00007C407C44447C00007C440810101000007C443844447C00007C44447C047C000000001000001000000010000010102000000408100804000000003E003E00000000100804081000007C441C100010003C42BD85BDA5BE78003C42427E42E70000FC427C4242FC00007E424040427E0000FE42424242FE0000FE42784042FE0000FE42784040E000007E42404E427E0000E7427E4242E700007C101010107C00007E08080848780000E648705844E60000E040404242FE0000C3665A4242E70000C762524A46E700007E424242427E0000FE42427E40E000007E424242527E0800FE42427E44E700007E407E02427E0000FE92101010380000CE444444447E0000E742424224180000D7929292926C0000EE44382844EE0000EE442810103800007E440810227E001C10101010101C0000004020100804003808080808083800001038541010100000000000000000FF003C247020207C0000007C047C447E00C0407C4444447C0000007C4440407C000C047C4444447E0000007C447C407C003C2470202020700000007C44447C047CC0407C444444E6001000701010107C000800380808084878C0404C506058CC007010101010107C000000FC545454D6000000FC444444E60000007C4444447C0000007E22223E207000007C44447C040600007C242020700000007C407C04FC0000207820202038000000CC4444447E000000CE44442838000000D65454547E000000C6281028C6000000CC44447C047C00007E4418227E00000E083008080E0000080808080808000070100C1010700000142800000000003C4299A1A199423C');
    // Extra glyphs + hard/short spaces live in the game (svision core fonts are ASCII + normal space).
    this.fonts.fonts5x5.addGlyphs({
      'Ⓥ': {width: 3, data: [[0,2,1,1], [0,3,1,1], [1,4,1,1], [2,3,1,1], [2,2,1,1]]},
      // devModeName banner decoration
      '◢': {width: 4, data: [[4,0,1,1], [3,1,2,1], [2,2,3,1], [1,3,4,1], [0,4,5,1]]},
      '◤': {width: 4, data: [[0,0,5,1], [0,1,4,1], [0,2,3,1], [0,3,2,1], [0,4,1,1]]}
    });
    this.fonts.fonts5x5.addSpace('␣', {width: 2, breaking: false, stretch: true});

    this.fonts.zxFonts8x8.addGlyphs('‗⋅', '000000000000F8F80000000030000000');
    // the 16 x 16 close cross of the panel button (GameInfoEntity.pauseButton):
    // a bold X, symmetric about both axes, in four 8 x 8 quarters — top left,
    // top right, bottom left, bottom right — set as two lines of two glyphs
    this.fonts.zxFonts8x8Mono.addGlyphs('◰◳◱◲', '3078FC7E3F1F0F070C1E3F7EFCF8F0E0070F1F3F7EFC7830E0F0F8FC7E3F1E0C');
    this.fonts.zxFonts8x8.addSpace('␣', {width: 3, breaking: false, stretch: false});
    this.fonts.zxFonts8x8.addSpace('▭', {width: 4, breaking: false, stretch: false});

    // The original is played on Q W E R T — Q left, W right, E down, R up and
    // T the combat button — with CAPS SHIFT or SPACE/BREAK for the pause
    // ("Continuous Pause" on the inlay, ZADANI chap. 1). Movement is **eight
    // way**: "Full 8 Way Movement" on the box, so two directions held at once
    // are a diagonal, not a conflict. The remake's defaults are the arrow keys
    // and SPACE for the sword, as in the sibling remakes (getControls()), and
    // **every key comes from SETTINGS** — nothing is accepted beside the
    // configured keys, so the remap dialog always tells the truth. The mouse
    // is not offered for the game: it serves the buttons and the menu.
    this.controlsOptions = {
      keyboard: {
        device: 'keyboard',
        keys: [
          {action: 'left', label: 'WALK LEFT'},
          {action: 'right', label: 'WALK RIGHT'},
          {action: 'up', label: 'WALK UP'},
          {action: 'down', label: 'WALK DOWN'},
          {action: 'sword', label: 'SWORD'},
          {action: 'sounds', label: 'MUTE SOUNDS'}
        ]
      },
      gamepads: {
        device: 'gamepads',
        keys: [
          {action: 'left', label: 'WALK LEFT', eventKey: 'GamepadLeft'},
          {action: 'right', label: 'WALK RIGHT', eventKey: 'GamepadRight'},
          {action: 'up', label: 'WALK UP', eventKey: 'GamepadUp'},
          {action: 'down', label: 'WALK DOWN', eventKey: 'GamepadDown'},
          {action: 'sword', label: 'SWORD', eventKey: 'GamepadFire'},
          // the buttons of the menu, the dialogs and the tape loading listen
          // to GamepadOK (like manicminer, jetsetwilly); in the game it swings
          // the sword as well (roomModel.js)
          {action: 'ok', label: 'OK', eventKey: 'GamepadOK'},
          {action: 'exit', label: 'EXIT', eventKey: 'GamepadExit'}
        ]
      },
      // ★ Touch controls are part of M1, not of a later milestone. That is the
      // lesson of Underwurlde, where they were put off and left a hole (M5b);
      // here there are few actions — eight directions, the sword and the pause
      // — so there is no reason to wait.
      //
      // One half of the screen is an **eight-way stick** (the original's own
      // movement, so the stick has to hold two directions at once), the other
      // a **sword button**. Which half is which is the left-handed /
      // right-handed choice in SETTINGS; that is all `types` says.
      touchscreen: {
        device: 'touchscreen',
        types: {
          // ★ default is the sword on the left and the stick on the right
          // (2026-09-11); the first key is also the fallback for a broken cookie
          keys: [
            'leftSword',
            'rightSword'
          ],
          rightSword: {
            left: {half: 'stick', sprite: 'stick'},
            right: {half: 'sword', sprite: 'sword'}
          },
          leftSword: {
            left: {half: 'sword', sprite: 'sword'},
            right: {half: 'stick', sprite: 'stick'}
          }
        },
        // What each half does. `rect` is a fraction of that half
        // ([x, y, width, height]), so the layout does not depend on how big
        // the half happens to be — a phone gets the same thing upright and on
        // its side.
        halves: {
          stick: {
            icon: 'stick',
            zones: [
              {rect: [0, 0, 1, 1], type: 'joystick', control: 'both',
               actions: {left: 'left', right: 'right', up: 'up', down: 'down'}}
            ]
          },
          sword: {
            icon: 'sword',
            zones: [
              // the sword is **held**, like the T key; how long a swing lasts
              // and how narrow the window of a hit is comes in M3
              {rect: [0, 0, 1, 1], type: 'button', action: 'sword'}
            ]
          }
        },
        // A short tap has to be seen by the worker: it reads the controls once
        // per pass of the main loop (50.08 Hz), so even the briefest tap is
        // held at least this long.
        tapHoldTime: 120,
        // how far the finger has to move before the stick changes direction
        joystickStep: 10,
        icons: {
          // the four arrows for the stick are a control glyph of the svision
          // family (the same one the sibling remakes use); the sword is the
          // game's own
          stick: {
            compressedSpriteData: 'lP101300N0E2P0111030Z051012320B0P020N0601234561718191AB9BCDB1BDCB9BA19181716543210'
          },
          sword: {
            // ★ the game's own Sword ($87, frame $DA87, 16x16): entity
            // "Sword" in data/entities.json, rows in screen order, centred on
            // the 39x23 canvas of the stick glyph so both icons take the same
            // room in the border; a readable grid, `-` transparent, `#` pen
            // colour (setGameControlIcons takes this shape as well as
            // compressedSpriteData)
            width: 39, height: 23, frames: 1, directions: 1,
            sprite: [[
              '---------------------------------------',
              '---------------------------------------',
              '---------------------------------------',
              '--------------------------#------------',
              '-------------------------#-------------',
              '------------------------#--------------',
              '----------------------##---------------',
              '---------------------###---------------',
              '--------------------###----------------',
              '-------------------###-----------------',
              '-----------------####------------------',
              '----------------####-------------------',
              '-------------#-#####-------------------',
              '-------------##-###--------------------',
              '--------------##-#---------------------',
              '-------------#-##----------------------',
              '------------###-##---------------------',
              '-----------###-------------------------',
              '-----------##--------------------------',
              '---------------------------------------',
              '---------------------------------------',
              '---------------------------------------',
              '---------------------------------------'
            ]]
          }
        }
      }
    };

    this.controls = {
      keyboard: this.getControls('keyboard'),
      touchscreen: this.getControls('touchscreen'),
      gamepads: this.getControls('gamepads')
    };

    // measured on the running original (data/global.json, tools/mkglobal.py):
    // four lives on the panel at the start and a preset HI of 102275, which is
    // the top of the game's own hall of fame table ($B304)
    this.players = GameApp.PLAYERS[0];
    this.lives = 4;
    this.score = 0;
    this.score2 = 0;
    this.hiScore = 0;
    this.player = 1;
    // M4: ★ the percentage of the world seen is a real rule of the game, not
    // a reviewer's impression — PrintRoomsVisited ($9CC6) counts the 256 bits
    // of VisitedRooms **and the four pieces of the amulet**, so the whole is
    // 260, and the original prints it as ADVENTURE COMPLETED nn% ($AAD4)
    this.percent = 0;
    this.amulet = 0;
    this.roomName = 'room000';
    this.trainingRoom = null;
    this.sandbox = false;
    this.playerName = Tool.readCookie('playerName', '');
    this.globalData = false;
    this.id = 'GameApp';
    this.fetchDataId = '';
    this.setModel('LoadingModel');
    this.loadAppData();
  } // constructor

  getControls(device) {
    var result = {};

    switch (device) {
      case 'keyboard':
        // The defaults of the remake: the arrows and SPACE, as in the sibling
        // remakes. The original is played on Q W E R T — Q left, W right,
        // T sword — and ★ **E up, R down**, which is the other way round than
        // the printed instructions say. Measured in M3 twice over: $AF2F tests
        // bit 3 of the keyboard half-row $FBFE (that is R) and adds to y,
        // y grows downwards, and a screenshot of the original with E held
        // shows Sabreman at the top of the screen (disasm_notes.md chap. 14).
        // Anyone who wants the original's letters sets them in SETTINGS.
        result = {left: 'ArrowLeft', right: 'ArrowRight', up: 'ArrowUp',
                  down: 'ArrowDown', sword: ' ', sounds: 'S'};
        break;
      case 'touchscreen':
        result = {supported: false, type: 'leftSword'};
        break;
      case 'gamepads':
        result = {supported: false, devices: {}};
        break;
    }

    switch (device) {
      case 'keyboard':
      case 'touchscreen':
        var cfgString = Tool.readCookie(device, false);
        if (cfgString !== false) {
          try {
            var cfg = JSON.parse(cfgString);
            Object.keys(cfg).forEach((item) => {
              result[item] = cfg[item];
              if (device == 'touchscreen' && !(result[item] in this.controlsOptions.touchscreen.types)) {
                result[item] = this.controlsOptions.touchscreen.types.keys[0];
              }
            });
          } catch (error) {
            console.error(error.message);
          }
        }
        break;
      case 'gamepads':
        var devicesString = Tool.readCookie('gamepads', false);
        if (devicesString !== false) {
          try {
            var devices = JSON.parse(devicesString);
          } catch (error) {
            console.error(error.message);
          } finally {
            if (Array.isArray(devices)) {
              devices.forEach((id) => {
                var deviceString = Tool.readCookie(id, false);
                if (deviceString !== false) {
                  try {
                    var device = JSON.parse(deviceString);
                  } catch (error) {
                    console.error(error.message);
                  } finally {
                    result.devices[id] = device;
                  }
                }
              });
            }
          }
        }
        break;
    }
    return result;
  } // getControls

  setModel(model) {
    if (model == 'MenuModel' && this.globalData === false) {
      // the fetch may still be pending or has failed: as a last resort try the
      // data cached in localStorage before bothering the user
      if (!this.loadGlobalDataFromStorage()) {
        this.showErrorMessage('Game data could not be loaded.', 'retry');
        return;
      }
    }
    var needResizeApp = false;
    var selectionItem = 0;
    if (this.model) {
      // where to put the menu cursor on the way back (menuModel.menuItems)
      if (this.model.id == 'TapeLoadingModel') {
        selectionItem = 5;
      } else if (this.model.id == 'AboutModel') {
        selectionItem = 6;
      } else if (this.model.id == 'HallOfFameModel') {
        selectionItem = 2;
      }
      this.model.shutdown();
      needResizeApp = true;
    }
    switch (model) {
      case 'LoadingModel':
        this.model = new ZXResetModel(this);
        break;
      case 'MenuModel':
        this.model = new MenuModel(this, selectionItem);
        break;
      case 'AboutModel':
        this.model = new AboutModel(this);
        break;
      case 'HallOfFameModel':
        this.model = new HallOfFameModel(this);
        break;
      case 'RoomModel':
        this.model = new RoomModel(this);
        break;
      case 'GameOverModel':
        this.model = new GameOverModel(this, 'MenuModel');
        break;
      case 'TapeLoadingModel':
        this.model = new TapeLoadingModel(this);
        break;
    } // switch
    this.model.init();
    if (needResizeApp) {
      this.resizeApp();
    }
  } // setModel

  /**
   * How many players the game runs with. Anything that is not one of
   * GameApp.PLAYERS is ignored, so a missing parameter keeps the current
   * choice — the same shape the original keeps in GameOptions ($9692).
   * @param {number} [players] - 1 or 2.
   * @returns {number} The number of players in force.
   */
  setPlayers(players) {
    if (GameApp.PLAYERS.indexOf(players) >= 0) {
      this.players = players;
    }
    return this.players;
  } // setPlayers

  /**
   * Starts a new game in the initial room.
   * @param {Object} [trainingRoom] - {column, row} picked on the map: start in
   *        that room instead of the game's own start room. A convenience of
   *        the remake, not of the original (ZADANI chap. 5).
   * @param {number} [players] - 1 or 2; without it the menu's choice stays.
   * @param {boolean} [sandbox] - PHYSICS SANDBOX: show Sabreman's own record
   *        on the screen while he walks (M3).
   */
  startRoom(trainingRoom, players, sandbox) {
    this.sandbox = !!sandbox;
    this.setPlayers(players);
    this.score = 0;
    this.score2 = 0;
    this.percent = 0;
    this.amulet = 0;
    this.player = 1;
    this.lives = (this.globalData && this.globalData.lives) || 4;
    this.roomName = (this.globalData && this.globalData.initRoom) || 'room000';
    this.trainingRoom = trainingRoom || null;
    this.setModel('RoomModel');
  } // startRoom

  applyGlobalData(global) {
    this.globalData = global;
    this.lives = global.lives || this.lives;
    this.roomName = global.initRoom || this.roomName;
    // the game's own preset HI: the top of its hall of fame table ($B304)
    if (global.hiScore && !this.hiScore) {
      this.hiScore = global.hiScore;
    }
  } // applyGlobalData

  setGlobalData(data) {
    this.applyGlobalData(data.data.global);

    var files = {};
    Object.keys(data.data).forEach((key) => {
      if (key == 'hiScore') {
        // the server's hall of fame wins over the game's preset one, but only
        // when somebody has actually beaten it
        this.hiScore = Math.max(this.hiScore || 0, data.data[key] || 0);
      } else if (key != 'global') {
        files[key] = data.data[key];
      }
    });
    // global goes last; a full localStorage is cleared and tried once more
    // (R-062)
    this.saveAppDataToStorage(files, data.data.global);
  } // setGlobalData

  // Load the application data: from the server when online (which also refreshes
  // localStorage), or rehydrate the global data from localStorage when offline.
  loadAppData() {
    if (navigator.onLine) {
      this.fetchDataId = this.fetchData('appData.db', false, {}, this, 2000);
    } else {
      this.loadGlobalDataFromStorage();
    }
  } // loadAppData

  loadGlobalDataFromStorage() {
    var stored = localStorage.getItem(window.appPrefix+'.global');
    if (stored !== null) {
      try {
        this.applyGlobalData(JSON.parse(stored));
        return true;
      } catch (error) {
        console.error(error.message);
      }
    }
    return false;
  } // loadGlobalDataFromStorage

  setData(data) {
    this.setGlobalData(data);
  } // setData

  errorData(error) {
    // The network request failed (offline, unreachable server, or the fetch
    // timeout). Fall back to the data cached in localStorage; if none exists,
    // log it and let the MenuModel guard surface the error to the user.
    if (!this.loadGlobalDataFromStorage()) {
      console.error(error.message ? error.message : error);
      return;
    }
    if (this.model && this.model.id == 'ZXResetModel'
        && !this.model.events.some((queued) => queued.id == 'setMenuModel')
        && !this.model.desktopEntity.modalEntity) {
      this.setModel('MenuModel');
    }
  } // errorData

  showErrorMessage(message, action) {
    var topModalEntity = this.model.desktopEntity.topModalEntity();
    topModalEntity.addModalEntity(
      new ZXErrorEntity(
        topModalEntity,
        -topModalEntity.absoluteX(),
        -topModalEntity.absoluteY(),
        this.fonts.zxFonts8x8,
        message,
        action,
        ZXColor.white,
        ZXColor.red
      )
    );
  } // showErrorMessage

} // GameApp
