SELECT `ndx`, `name`, `score`, `created`
FROM `rg_sw_hallOfFame`
ORDER BY `ndx` DESC
LIMIT :limit
