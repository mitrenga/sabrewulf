<?php

require_once 'app/svision/php/abstractAboutPage.php';

/**
 * The /about page: the story of the original Sabre Wulf and of this remake.
 * M1 text; the final content comes with M7.
 */
class AboutPage extends AbstractAboutPage {

  protected function aboutData() {
    return [
      'image' => 'images/cover.png',
      'sections' => [
        [
          'heading' => 'The original game (1984)',
          'html' =>
            '<p>Sabre Wulf was released by Ultimate Play The Game in 1984 for the 48K ZX Spectrum, '.
            'the first of the four Sabreman games. Sabreman is lost in a jungle maze of 256 screens '.
            'and has to find the four pieces of an amulet, get past the keeper of the gate and escape. '.
            'Movement is eight-way, collection is automatic, and the only weapon is a sword.</p>'.
            '<p>Its two defining ideas are the orchids and the wulf. The orchids bloom for a few '.
            'seconds only, and each colour does something else to Sabreman — the inlay names Yellow '.
            'Sickness, White Cure, Red Zombie, Blue Super High Energy and Purple De-Orientation. '.
            'The Sabre Wulf itself cannot be killed at all; it simply hunts you, and so does the '.
            'keeper of the gate. Hippos, rhinos and natives can be driven off but not destroyed, and '.
            'the natives point the way to the amulet. The game keeps a percentage of the screens you '.
            'have visited, has a hall of fame of its own, plays Bach on the one-bit beeper, and can '.
            'be played by two people taking turns.</p>',
        ],
        [
          'heading' => 'This remake',
          'html' =>
            '<p>This is a faithful remake, rewritten for the web browser rather than emulated. The graphics '.
            'and the world are taken out of the original program, not redrawn, and the rules come from the '.
            'original instructions and from the disassembly of the game — where a rule cannot be shown, it '.
            'is left as an open question rather than guessed. Even the frame rate is the Spectrum\'s own '.
            '50.08 Hz, and the attribute clash of the hardware is reproduced instead of cleaned up, which '.
            'in Sabre Wulf matters more than in most games: the jungle is the most colourful screen '.
            'Ultimate ever put on a Spectrum.</p>'.
            '<p>It runs directly in your browser — nothing to install, nothing to download. Keyboard '.
            '(the original Q W E R T, or the arrow keys), touch controls and gamepads are supported.</p>'.$this->installNote(),
        ],
        [
          'heading' => 'Other games',
          'html' =>
            '<p>This remake is one of a growing collection of classic games from the 8-bit and 16-bit era '.
            '— ZX Spectrum, Commodore 64, arcade and more — rebuilt faithfully on the same library and '.
            'playable in your browser, free of charge. Browse the whole collection at '.
            '<a href="https://retrogames.free/" target="_blank" rel="noopener">retrogames.free</a>.</p>',
        ],
      ],
      'links' => [
        ['label' => 'Sabre Wulf at Spectrum Computing', 'url' => 'https://spectrumcomputing.co.uk/entry/9408/ZX-Spectrum/Sabre-Wulf'],
        ['label' => 'Sabre Wulf at World of Spectrum', 'url' => 'https://worldofspectrum.org/archive/software/games/sabre-wulf-ultimate-play-the-game'],
      ],
      'footer' =>
        '<p>An unofficial fan remake. The original game and its artwork belong to their authors '.
        '(Ultimate Play The Game, today Rare/Microsoft). '.
        'The remake\'s source code is licensed under <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noopener">CC BY-NC-SA 4.0</a>.</p>',
    ];
  } // aboutData

} // AboutPage
