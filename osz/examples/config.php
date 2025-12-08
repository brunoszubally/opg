<?php

header("Content-Type: text/html; charset=utf-8");

define("TEST_DATA_DIR", __DIR__ . "/../tests/testdata/");

include("../autoload.php");


$apiUrl = NavOnlineInvoice\Config::PROD_URL; // https://api-test.onlineszamla.nav.gov.hu/invoiceService/v3

$userData = array(
    "login" => "as3cj8iherbtmtx",
    "password" => "Sanyika1472",
    "taxNumber" => "32654732",
    "signKey" => "09-8ad7-1e2dbdbea46d4YVJVJWONT9D",
    "exchangeKey" => "7e004YVJVJWOMRAN"
);

$softwareData = array(
    "softwareId" => "123456789123456789",
    "softwareName" => "string",
    "softwareOperation" => "ONLINE_SERVICE",
    "softwareMainVersion" => "string",
    "softwareDevName" => "string",
    "softwareDevContact" => "string",
    "softwareDevCountryCode" => "HU",
    "softwareDevTaxNumber" => "string",
);
