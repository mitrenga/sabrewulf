<?php
  $appName = 'SABRE WULF';
  $appDescription = 'Play SABRE WULF online for free in your browser. Faithful remake of the 1984 Ultimate Play The Game ZX Spectrum classic, no download required.';
  $appPrefix = 'sw';
  $appNoscript =
    '<h1>SABRE WULF</h1>'.
    '<p>Sabre Wulf is the 1984 ZX Spectrum game by Ultimate Play The Game, the first of the '.
    'Sabreman series. Sabreman is lost in a jungle maze of 256 screens and has to collect the '.
    'four pieces of an amulet, get past the keeper of the gate and escape. Orchids bloom for a '.
    'few seconds and change what he can do; the Sabre Wulf itself cannot be killed.</p>'.
    '<p>This is a faithful remake that runs directly in your web browser. '.
    'There is nothing to install and nothing to download — just open the page and play. '.
    'Please enable JavaScript to start the game.</p>'.
    '<p><a href="about">More about Sabre Wulf and this remake</a></p>';
  $appOpenGraph = [
    'image' => 'images/poster.png',
  ];
  $appJsonLd = [
    'genre' => 'Action-adventure game',
    'isBasedOn' => [
      '@type' => 'VideoGame',
      'name' => 'Sabre Wulf',
      'publisher' => [
        ['@type' => 'Organization', 'name' => 'Ultimate Play The Game'],
      ],
      'datePublished' => '1984',
      'gamePlatform' => 'ZX Spectrum',
    ],
  ];
  require_once 'config/config.php';
  require_once 'app/svision/php/main.php';
