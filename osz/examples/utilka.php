<?php

//echo utolsoNap($argv[1]);
// phonap utolso napját adja vissza 2020-08-01
function utolsoNap($dateToTest){

$lastday = date('t',strtotime($dateToTest));
//echo $lastday;
return (substr($dateToTest,0,8).$lastday);
}
?>