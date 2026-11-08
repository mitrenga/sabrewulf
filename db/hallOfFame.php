<?php

class DataCommand {
   
   public function execute($postData) {
      $mysqli = new mysqli($GLOBALS['dbHostname'], $GLOBALS['dbUser'], $GLOBALS['dbPassword'], $GLOBALS['dbName']);
      $data = $mysqli->query('SELECT `name`, MAX(`score`) as score FROM `rg_sw_hallOfFame` GROUP BY `name` ORDER BY score DESC LIMIT 6');
      $mysqli->close();
      return $data;
   } // execute

} // class DataCommand

