<?php

class DataCommand {

  // Co se posílá při startu aplikace. Obrazy všech místností tady zámerně
  // nejsou a nebudou: obrazovka se skládá z kulisy podle předlohy, takže
  // stačí poslat 41 kusů kulisy (scenery), 48 předloh (rooms) a mřížku světa
  // (world) – dohromady necelých 60 kB na všech 256 obrazovek, místo 256
  // souborů po 9 kB (data/README.md).
  //
  // Od M3 k tomu jdou **sprity** (spriteframes, 153 snímků z SpritesTable) –
  // je čím hýbat – a **fyzika** (physics, konstanty přečtené jako operandy
  // instrukcí originálu, tools/dumpphysics.py). Kulisu a předlohy potřebuje
  // i worker, protože kolize se ptá na tentýž seznam kusů kulisy, ze kterého
  // se místnost kreslí ($B873).
  // Od M4 ještě **svět** (entities): orchidej každé předlohy, čtyři pozice
  // předmětů v ní, osm hotových sad, do kterých se schovává amulet, a tabulka
  // procent navštívených obrazovek (tools/dumpentities.py).
  // Od M5 **nepřátelé** (monsters): `JumpTable` ($9B3E), ze které vyjde, kdo
  // je zničitelný a kdo se dá jen zahnat, šestnáct druhů zvířat, rychlosti,
  // ohnivá koule a body za nepřítele (tools/dumpmonsters.py).
  // Od M6 k tomu **zvuk** (sounds: deset rutin beeperu a jejich konstanty),
  // **hudba** (music: tabulka 61 not a čtyři skladby) a **texty** (text: čtyři
  // sloky básně, obrázek amuletu a hlášky konce hry). Dohromady necelých
  // 100 kB a všechno je to vytažené z originálu (tools/dumpsound.py,
  // tools/dumpmusic.py, tools/dumptext.py).
  var $files = ['global', 'world', 'scenery', 'rooms', 'physics', 'entities',
                'monsters', 'spriteframes', 'sounds', 'music', 'text',
                'loading', 'title', 'sprites', 'room000'];

  public function execute($postData) {
    $result = [];
    foreach ($this->files as $file) {
      $fileName = 'data/'.$file.'.json';
      if (!is_file($fileName)) {
        // optional data files (those a later milestone adds) arrive as null
        $result[$file] = null;
        continue;
      }
      $dataJSON = file_get_contents($fileName);
      try {
        $result[$file] = json_decode($dataJSON, false, 512, JSON_THROW_ON_ERROR);
      }
      catch (\JsonException $exception) {
        $result[$file] = ['error' => ['message' => $exception->getMessage()]];
      }
    }

    $mysqli = new mysqli($GLOBALS['dbHostname'], $GLOBALS['dbUser'], $GLOBALS['dbPassword'], $GLOBALS['dbName']);
    $data = $mysqli->query('SELECT `score` FROM `rg_sw_hallOfFame` ORDER BY `score` DESC LIMIT 1');
    $mysqli->close();
    $result['hiScore'] = 0;
    if ($row = $data->fetch_object()) {
      $result['hiScore'] = $row->score;
    }

    return $result;
  } // execute

} // class DataCommand
