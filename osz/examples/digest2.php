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
    $allInvoices = []; // Tömb az összes számla tárolására

    do {
        // Számlák lekérése az aktuális oldalra
        $invoiceDigestResult = $reporter->queryInvoiceDigest($invoiceQueryParams, $page, "OUTBOUND");

        // Az aktuális oldal számláinak hozzáadása a tömbhöz
        if (isset($invoiceDigestResult->invoiceDigest)) {
            foreach ($invoiceDigestResult->invoiceDigest as $invoice) {
                $allInvoices[] = $invoice; // Számlák gyűjtése
            }
        }

        // Elérhető oldalak számának ellenőrzése
        $availablePages = (int)$invoiceDigestResult->availablePage;

        // Következő oldal
        $page++;

        // Ciklus feltétele: addig fut, amíg van további oldal
    } while ($page <= $availablePages);

    // Összes számla kiírása (debug célból)
    print "Összes lekérdezett számla száma: " . count($allInvoices) . "\n";
    print "Összes számla XML elemei:\n";
    var_dump($allInvoices);

    // Opcionális: JSON formátumba konvertálás az Adalo számára
    $jsonData = json_encode($allInvoices);
    file_put_contents('all_invoices.json', $jsonData);

} catch (Exception $ex) {
    print get_class($ex) . ": " . $ex->getMessage();
}