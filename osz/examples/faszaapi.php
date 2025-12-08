<?php
ob_start(); // Explicit output buffering indítása

ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST');
header('Access-Control-Allow-Headers: Content-Type, X-API-Key');

error_log("INFO: Script started.");

include("../autoload.php");

// API kulcs ellenőrzése
$validApiKeys = [
    'aXJ2b2x0YXNlY3VyZWFwaWtleTIwMjQ=' => [
        'name' => 'Default Client',
        'rate_limit' => 100
    ]
];

$apiKey = $_SERVER['HTTP_X_API_KEY'] ?? null;
if (!$apiKey || !isset($validApiKeys[$apiKey])) {
    http_response_code(401);
    echo json_encode(['error' => 'Érvénytelen API kulcs']);
    exit;
}

// Adatok beolvasása (POST vagy GET)
$requestData = [];
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $rawData = file_get_contents('php://input');
    $requestData = json_decode($rawData, true) ?? [];
    
    // Debug információk
    error_log("Raw POST data: " . $rawData);
    error_log("Decoded POST data: " . print_r($requestData, true));
} else {
    $requestData = $_GET;
}

// Debug információk
error_log("Request method: " . $_SERVER['REQUEST_METHOD']);
error_log("Final request data: " . print_r($requestData, true));

// Query paraméterek ellenőrzése
$requiredParams = ['login', 'password', 'taxNumber', 'signKey', 'exchangeKey', 'dateFrom', 'dateTo'];
$missingParams = [];

foreach ($requiredParams as $param) {
    if (!isset($requestData[$param])) {
        $missingParams[] = $param;
    }
}

if (!empty($missingParams)) {
    http_response_code(400);
    echo json_encode([
        'error' => 'Hiányzó paraméterek',
        'missing' => $missingParams
    ]);
    exit;
}

try {
    // Felhasználói adatok összeállítása
    $userData = [
        "login" => $requestData['login'],
        "password" => $requestData['password'],
        "taxNumber" => $requestData['taxNumber'],
        "signKey" => $requestData['signKey'],
        "exchangeKey" => $requestData['exchangeKey']
    ];

    // Szoftver adatok (ezek fixek lehetnek)
    $softwareData = [
        "softwareId" => "123456789123456789",
        "softwareName" => "string",
        "softwareOperation" => "ONLINE_SERVICE",
        "softwareMainVersion" => "string",
        "softwareDevName" => "string",
        "softwareDevContact" => "string",
        "softwareDevCountryCode" => "HU",
        "softwareDevTaxNumber" => "string"
    ];

    $config = new NavOnlineInvoice\Config(NavOnlineInvoice\Config::PROD_URL, $userData, $softwareData);
    $reporter = new NavOnlineInvoice\Reporter($config);

    // Éves összesítés kezelése
    if (isset($requestData['yearly']) && $requestData['yearly'] === 'true') {
        error_log("INFO: Yearly summary requested2.");
        $year = date('Y', strtotime($requestData['dateFrom']));
        $yearlySummary = [
            'totalAmount' => 0,
            'stornoAmount' => 0,
            'modifiedAmount' => 0,
            'netAmount' => 0,
            'validInvoices' => 0,
            'stornoInvoices' => 0,
            'modifiedInvoices' => 0,
            'totalInvoices' => 0,
            'monthlyData' => [],
            'crossYearStornos' => 0,
            'crossYearModified' => 0
        ];

        // Végigmegyünk az év minden hónapján
        for ($month = 1; $month <= 12; $month++) {
            $dateFrom = sprintf('%d-%02d-01', $year, $month);
            $dateTo = date('Y-m-t', strtotime($dateFrom));

            error_log("INFO: Querying month " . $month . " from " . $dateFrom . " to " . $dateTo);

            $invoiceQueryParams = [
                "mandatoryQueryParams" => [
                    "invoiceIssueDate" => [
                        "dateFrom" => $dateFrom,
                        "dateTo" => $dateTo,
                    ],
                ],
            ];

            $page = 1;
            $monthlyInvoices = [];
            $maxPages = 100;
            $monthlyError = null;

            try {
                do {
                    error_log("INFO: Querying page " . $page);
                    $invoiceDigestResult = $reporter->queryInvoiceDigest($invoiceQueryParams, $page, "OUTBOUND");

                    if (isset($invoiceDigestResult->invoiceDigest)) {
                        error_log("INFO: Found " . count($invoiceDigestResult->invoiceDigest) . " invoices on page " . $page);
                        foreach ($invoiceDigestResult->invoiceDigest as $invoice) {
                            $monthlyInvoices[] = $invoice;
                        }
                    }

                    $availablePages = (int)$invoiceDigestResult->availablePage;
                    error_log("INFO: Available pages for month " . $month . ": " . $availablePages);
                    $page++;
                } while ($page <= $availablePages && $page <= $maxPages);

                error_log("INFO: Finished querying month " . $month . ". Total invoices for month: " . count($monthlyInvoices));

                // Havi összesítés számítása
                $monthlySummary = [
                    'totalAmount' => 0,
                    'stornoAmount' => 0,
                    'modifiedAmount' => 0,
                    'netAmount' => 0,
                    'validInvoices' => 0,
                    'stornoInvoices' => 0,
                    'modifiedInvoices' => 0,
                    'totalInvoices' => count($monthlyInvoices),
                    'crossYearStornos' => 0,
                    'crossYearModified' => 0
                ];

                // Aktuális év meghatározása a hónap dateFrom alapján
                $currentYear = (int)date('Y', strtotime($dateFrom));

                foreach ($monthlyInvoices as $invoice) {
                    $amount = (float)$invoice->invoiceNetAmountHUF;
                    $isCrossYear = false;

                    // Ellenőrizzük, hogy a sztornó/módosítás korábbi évre vonatkozik-e (delivery date alapján)
                    if (($invoice->invoiceOperation === 'STORNO' || $invoice->invoiceOperation === 'MODIFY') && 
                        isset($invoice->invoiceDeliveryDate)) {
                        $deliveryYear = (int)date('Y', strtotime($invoice->invoiceDeliveryDate));
                        if ($deliveryYear < $currentYear) {
                            $isCrossYear = true;
                        }
                    }

                    // Az összeget és a darabszámot is csak akkor adjuk hozzá a havi összesítéshez, ha nem cross-year
                    if (!$isCrossYear) {
                        switch ($invoice->invoiceOperation) {
                            case 'STORNO':
                                $monthlySummary['stornoAmount'] += abs($amount);
                                $monthlySummary['stornoInvoices']++;
                                break;
                            case 'MODIFY':
                                $monthlySummary['modifiedAmount'] += $amount;
                                $monthlySummary['modifiedInvoices']++;
                                break;
                            case 'CREATE':
                                $monthlySummary['totalAmount'] += $amount;
                                $monthlySummary['validInvoices']++;
                                break;
                        }
                    } else {
                         // Ha cross-year, az összeget nem számoljuk, de a cross-year számlálót növeljük.
                         switch ($invoice->invoiceOperation) {
                            case 'STORNO':
                                $yearlySummary['crossYearStornos']++; // Frissítjük az éves cross-year sztornó számlálót
                                break;
                            case 'MODIFY':
                                $yearlySummary['crossYearModified']++; // Frissítjük az éves cross-year módosítás számlálót
                                break;
                         }
                    }

                }

                $monthlySummary['totalInvoices'] = $monthlySummary['validInvoices'] + $monthlySummary['stornoInvoices'] + $monthlySummary['modifiedInvoices']; // Összes számla száma ebben a hónapban

                $monthlySummary['netAmount'] = $monthlySummary['totalAmount'] + 
                                             $monthlySummary['modifiedAmount'] - 
                                             $monthlySummary['stornoAmount'];
                                                 
                // Havi adatok hozzáadása az éves összesítéshez
                $yearlySummary['monthlyData'][$month] = $monthlySummary;
                
                // Éves összesítés frissítése (összegeket és darabszámokat a havi summary-ból vesszük)
                $yearlySummary['totalAmount'] += $monthlySummary['totalAmount'];
                $yearlySummary['stornoAmount'] += $monthlySummary['stornoAmount'];
                $yearlySummary['modifiedAmount'] += $monthlySummary['modifiedAmount'];
                $yearlySummary['netAmount'] += $monthlySummary['netAmount']; // Nettó összeget közvetlenül hozzáadjuk
                $yearlySummary['validInvoices'] += $monthlySummary['validInvoices'];
                $yearlySummary['stornoInvoices'] += $monthlySummary['stornoInvoices'];
                $yearlySummary['modifiedInvoices'] += $monthlySummary['modifiedInvoices'];
                $yearlySummary['totalInvoices'] += $monthlySummary['totalInvoices'];
                // A crossYear számlálókat már fentebb frissítettük direktben az éves summában

            } catch (Exception $ex) {
                $monthlyError = 'Error querying month ' . $month . ': ' . $ex->getMessage();
                error_log("ERROR: " . $monthlyError);
                $yearlySummary['monthlyData'][$month] = ['error' => $monthlyError];
                // Folytatjuk a következő hónappal
            }
        }

        error_log("INFO: Finished yearly processing. Total invoices: " . $yearlySummary['totalInvoices']);

        $yearlySummary['netAmount'] = $yearlySummary['totalAmount'] + 
                                    $yearlySummary['modifiedAmount'] - 
                                    $yearlySummary['stornoAmount'];

        error_log("INFO: Setting response for yearly summary.");

        $response = [
            'success' => true,
            'yearlySummary' => $yearlySummary,
            'cached' => false
        ];
    } else {
        // Eredeti havi lekérdezés logikája
        error_log("INFO: Monthly or non-summary request.");
        $invoiceQueryParams = [
            "mandatoryQueryParams" => [
                "invoiceIssueDate" => [
                    "dateFrom" => $requestData['dateFrom'],
                    "dateTo" => $requestData['dateTo'],
                ],
            ],
        ];

        $page = 1;
        $allInvoices = [];
        $maxPages = 100; // Maximum oldalszám korlátozás

        do {
            $invoiceDigestResult = $reporter->queryInvoiceDigest($invoiceQueryParams, $page, "OUTBOUND");

            if (isset($invoiceDigestResult->invoiceDigest)) {
                foreach ($invoiceDigestResult->invoiceDigest as $invoice) {
                    $allInvoices[] = $invoice;
                }
            }

            $availablePages = (int)$invoiceDigestResult->availablePage;
            $page++;
        } while ($page <= $availablePages && $page <= $maxPages);

        // Válasz cache-elése
        $cacheKey = md5(json_encode($requestData));
        $cacheFile = __DIR__ . '/cache/' . $cacheKey . '.json';
        $cacheTime = 300; // 5 perc

        if (!is_dir(__DIR__ . '/cache')) {
            mkdir(__DIR__ . '/cache', 0755, true);
        }

        // Ha csak az összeget kérjük
        if (isset($requestData['summary']) && $requestData['summary'] === 'true') {
            $totalAmount = 0;
            $stornoAmount = 0;
            $validInvoices = 0;
            $stornoInvoices = 0;
            $modifiedInvoices = 0;
            $modifiedAmount = 0;
            $crossYearStornos = 0;
            $crossYearModified = 0;

            // Az aktuális lekérdezési időszak évének meghatározása dateFrom alapján
            $currentYear = (int)date('Y', strtotime($requestData['dateFrom']));

            foreach ($allInvoices as $invoice) {
                $amount = (float)$invoice->invoiceNetAmountHUF;
                $isCrossYear = false;

                // Ellenőrizzük, hogy a sztornó/módosítás korábbi évre vonatkozik-e (delivery date alapján)
                if (($invoice->invoiceOperation === 'STORNO' || $invoice->invoiceOperation === 'MODIFY') && 
                    isset($invoice->invoiceDeliveryDate)) {
                    $deliveryYear = (int)date('Y', strtotime($invoice->invoiceDeliveryDate));
                    if ($deliveryYear < $currentYear) {
                        $isCrossYear = true;
                        // Cross-year számlálók frissítése (havi summary esetén)
                        if ($invoice->invoiceOperation === 'STORNO') {
                            $crossYearStornos++;
                        } elseif ($invoice->invoiceOperation === 'MODIFY') {
                            $crossYearModified++;
                        }
                    }
                }

                // Az összeget csak akkor adjuk hozzá a havi összesítéshez, ha nem cross-year sztornó/módosítás
                if (!$isCrossYear) {
                    switch ($invoice->invoiceOperation) {
                        case 'STORNO':
                            $stornoAmount += abs($amount);
                            $stornoInvoices++;
                            break;
                        case 'MODIFY':
                            $modifiedAmount += $amount;
                            $modifiedInvoices++;
                            break;
                        case 'CREATE':
                            $totalAmount += $amount;
                            $validInvoices++;
                            break;
                    }
                } else {
                    // Ha cross-year, akkor csak a számlát számoljuk be a teljes darabszámba, az összeget nem
                     switch ($invoice->invoiceOperation) {
                        case 'STORNO':
                            $stornoInvoices++; // Megszámoljuk a sztornók között
                            break;
                        case 'MODIFY':
                            $modifiedInvoices++; // Megszámoljuk a módosítások között
                            break;
                     }
                }
            }

            $response = [
                'success' => true,
                'summary' => [
                    'totalAmount' => $totalAmount,
                    'stornoAmount' => $stornoAmount,
                    'modifiedAmount' => $modifiedAmount,
                    'netAmount' => $totalAmount + $modifiedAmount - $stornoAmount,
                    'validInvoices' => $validInvoices,
                    'stornoInvoices' => $stornoInvoices,
                    'modifiedInvoices' => $modifiedInvoices,
                    'totalInvoices' => count($allInvoices), // Összes számla száma ebben a hónapban
                    'crossYearStornos' => $crossYearStornos,
                    'crossYearModified' => $crossYearModified
                ],
                'cached' => false
            ];
        } else {
            $response = [
                'success' => true,
                'count' => count($allInvoices),
                'invoices' => $allInvoices,
                'cached' => false
            ];
        }

        // Cache mentése (átmenetileg kikapcsolva)
        // error_log("INFO: Saving response to cache.");
        // file_put_contents($cacheFile, json_encode([
        //     'data' => $response,
        //     'timestamp' => time()
        // ]));

    }

    error_log("INFO: Preparing JSON response.");
    $jsonResponse = json_encode($response);

    if ($jsonResponse === false) {
        error_log("ERROR: json_encode failed. Error: " . json_last_error_msg());
        // Fallback response
        echo json_encode(['success' => false, 'error' => 'Internal error during JSON encoding.']);
    } else {
        error_log("INFO: JSON response length: " . strlen($jsonResponse));
        error_log("INFO: Echoing JSON response.");
        echo "DEBUG_OUTPUT_START\n"; // Teszt sor
        echo $jsonResponse;
    }

    ob_end_flush(); // Puffer ürítése és kikapcsolása

    die();

} catch (Exception $ex) {
    error_log("ERROR: Exception caught: " . $ex->getMessage() . " Type: " . get_class($ex));
    http_response_code(500);
    echo json_encode([
        'error' => $ex->getMessage(),
        'type' => get_class($ex)
    ]);
} 