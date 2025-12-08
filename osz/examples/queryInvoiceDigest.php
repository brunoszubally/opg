<?php

include("config.php");


try {
    $config = new NavOnlineInvoice\Config($apiUrl, $userData, $softwareData);
    $reporter = new NavOnlineInvoice\Reporter($config);

    $invoiceQueryParams = [
        "mandatoryQueryParams" => [
            "invoiceIssueDate" => [
                "dateFrom" => "2025-04-01",
                "dateTo" => "2025-04-30",
            ],
        ],
  
    ];

    $page = 1;

    $invoiceDigestResult = $reporter->queryInvoiceDigest($invoiceQueryParams, $page, "OUTBOUND");

    print "Query results XML elem:\n";
    var_dump($invoiceDigestResult);

    // Request XML for debugging:
    // $data = $reporter->getLastRequestData();
    // $requestXml = $data['requestBody'];
    // var_dump($requestXml);

} catch(Exception $ex) {
    print get_class($ex) . ": " . $ex->getMessage();
}
