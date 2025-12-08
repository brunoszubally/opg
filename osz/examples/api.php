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

// --- Segédfüggvények ---

/**
 * Biztonságos rövid log: jelszavakat/érzékeny adatokat maszkolunk.
 */
function safe_log_request(array $data): string {
    $copy = $data;
    if (isset($copy['password'])) {
        $copy['password'] = '***MASKED***';
    }
    return print_r($copy, true);
}

/**
 * Adószám normalizálása:
 * - HU prefix eltávolítása (ha van)
 * - első 8 egymást követő számjegy visszaadása
 * - ha ilyen nincs, akkor az összes számjegy összefűzése és első 8 karakter
 * - ha összesen < 8 számjegy érhető el: null (hibára futhat a hívó)
 */
function normalizeTaxNumber(string $rawTaxNumber): ?string {
    $s = strtoupper(trim($rawTaxNumber));

    // HU prefix levétele (PHP 7 kompatibilis)
    if (substr($s, 0, 2) === 'HU') {
        $s = substr($s, 2);
    }

    // első 8 egymást követő számjegy
    if (preg_match('/(\d{8})/', $s, $m)) {
        return $m[1];
    }

    // minden nem szám törlése, első 8 számjegy
    $onlyDigits = preg_replace('/\D+/', '', $s);
    if (strlen($onlyDigits) >= 8) {
        return substr($onlyDigits, 0, 8);
    }

    // nincs legalább 8 számjegy
    return null;
}

// API kulcs ellenőrzése
$validApiKeys = [
    'aXJ2b2x0YXNlY3VyZWFwaWtleTIwMjQ=' => [
        'name' => 'Default Client',
        'rate_limit' => 100
    ]
];

// Először fejlécekben keressük az API kulcsot
$apiKey = $_SERVER['HTTP_X_API_KEY'] ?? null;

// Ha nincs a fejlécekben, megnézzük az URL paraméterek között
if (!$apiKey) {
    $apiKey = $_GET['apiKey'] ?? null;
}

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

    // Debug információk (jelszó maszkolása)
    error_log("Raw POST data length: " . strlen((string)$rawData));
    error_log("Decoded POST data (safe): " . safe_log_request($requestData));
} else {
    // GET kérés esetén az URL paramétereket használjuk
    $requestData = $_GET;

    // Debug információk (jelszó maszkolása)
    error_log("GET parameters (safe): " . safe_log_request($requestData));
}

// Debug információk
error_log("Request method: " . $_SERVER['REQUEST_METHOD']);
error_log("Final request data (safe): " . safe_log_request($requestData));

/**
 * --- TAXNUMBER NORMALIZÁLÁSA ---
 * Ezt a kötelező paraméterek ellenőrzése ELŐTT végezzük el,
 * így ha a user "HU12345678-1-23" formátumot küld, a rendszer
 * már a tisztított 8 számjeggyel dolgozik.
 */
if (isset($requestData['taxNumber'])) {
    $normalizedTax = normalizeTaxNumber((string)$requestData['taxNumber']);
    if ($normalizedTax === null) {
        http_response_code(400);
        echo json_encode([
            'error' => 'Érvénytelen adószám formátum. Legalább 8 egymást követő számjegyet várunk a taxNumber-ben.'
        ]);
        error_log("ERROR: Invalid taxNumber provided: " . $requestData['taxNumber']);
        exit;
    }
    $requestData['taxNumber'] = $normalizedTax;
    error_log("INFO: Normalized taxNumber to: " . $normalizedTax);
}

// Query paraméterek ellenőrzése
$requiredParams = ['login', 'password', 'taxNumber', 'signKey', 'exchangeKey', 'dateFrom', 'dateTo'];
$missingParams = [];

foreach ($requiredParams as $param) {
    if (!isset($requestData[$param]) || $requestData[$param] === '') {
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
        "taxNumber" => $requestData['taxNumber'], // <- ez már normalizált, 8 számjegy
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
            'crossYearStornos' => 0,
            'crossYearModified' => 0
        ];

        // Végigmegyünk az év minden hónapján
        for ($month = 1; $month <= 12; $month++) {
            $dateFrom = sprintf('%d-%02d-01', $year, $month);
            $dateTo = date('Y-m-t', strtotime($dateFrom));
            // Hónap nevének beszerzése a kulcshoz
            $monthName = strtolower(date('F', mktime(0, 0, 0, $month, 1)));

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
                $monthlyTotalAmount = 0;
                $monthlyStornoAmount = 0;
                $monthlyModifiedAmount = 0;
                $monthlyValidInvoices = 0;
                $monthlyStornoInvoices = 0;
                $monthlyModifiedInvoices = 0;
                $monthlyTotalInvoices = count($monthlyInvoices);

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

                    if (!$isCrossYear) {
                        switch ($invoice->invoiceOperation) {
                            case 'STORNO':
                                $monthlyStornoAmount += abs($amount);
                                $monthlyStornoInvoices++;
                                break;
                            case 'MODIFY':
                                $monthlyModifiedAmount += $amount;
                                $monthlyModifiedInvoices++;
                                break;
                            case 'CREATE':
                                $monthlyTotalAmount += $amount;
                                $monthlyValidInvoices++;
                                break;
                        }
                    } else {
                        // cross-year darabszám jelölés az éves összesítőben
                        switch ($invoice->invoiceOperation) {
                            case 'STORNO':
                                $yearlySummary['crossYearStornos']++;
                                break;
                            case 'MODIFY':
                                $yearlySummary['crossYearModified']++;
                                break;
                        }
                    }
                }

                // Havi adatok hozzáadása az éves összesítéshez
                $yearlySummary[$monthName . 'TotalAmount']     = $monthlyTotalAmount;
                $yearlySummary[$monthName . 'StornoAmount']    = $monthlyStornoAmount;
                $yearlySummary[$monthName . 'ModifiedAmount']  = $monthlyModifiedAmount;
                $yearlySummary[$monthName . 'NetAmount']       = $monthlyTotalAmount + $monthlyModifiedAmount - $monthlyStornoAmount;
                $yearlySummary[$monthName . 'ValidInvoices']   = $monthlyValidInvoices;
                $yearlySummary[$monthName . 'StornoInvoices']  = $monthlyStornoInvoices;
                $yearlySummary[$monthName . 'ModifiedInvoices']= $monthlyModifiedInvoices;
                $yearlySummary[$monthName . 'TotalInvoices']   = $monthlyTotalInvoices;

                // Éves összesítés frissítése
                $yearlySummary['totalAmount']    += $monthlyTotalAmount;
                $yearlySummary['stornoAmount']   += $monthlyStornoAmount;
                $yearlySummary['modifiedAmount'] += $monthlyModifiedAmount;
                $yearlySummary['netAmount']      += ($monthlyTotalAmount + $monthlyModifiedAmount - $monthlyStornoAmount);
                $yearlySummary['validInvoices']  += $monthlyValidInvoices;
                $yearlySummary['stornoInvoices'] += $monthlyStornoInvoices;
                $yearlySummary['modifiedInvoices'] += $monthlyModifiedInvoices;
                $yearlySummary['totalInvoices']  += $monthlyTotalInvoices;

            } catch (Exception $ex) {
                $monthlyError = 'Error querying month ' . $month . ': ' . $ex->getMessage();
                error_log("ERROR: " . $monthlyError);
                $yearlySummary[$monthName . 'Error'] = $monthlyError;
            }
        }

        // Magyar hónapnevek
        $hungarianMonths = [
            1 => 'Január', 2 => 'Február', 3 => 'Március', 4 => 'Április',
            5 => 'Május', 6 => 'Június', 7 => 'Július', 8 => 'Augusztus',
            9 => 'Szeptember', 10 => 'Október', 11 => 'November', 12 => 'December'
        ];

        // Angol hónapnevek a kulcsokhoz
        $englishMonths = [
            1 => 'january', 2 => 'february', 3 => 'march', 4 => 'april',
            5 => 'may', 6 => 'june', 7 => 'july', 8 => 'august',
            9 => 'september', 10 => 'october', 11 => 'november', 12 => 'december'
        ];

        // Az aktuális hónap meghatározása
        $currentMonth = (int)date('n');
        $currentMonthName = $hungarianMonths[$currentMonth];
        $currentMonthKey = $englishMonths[$currentMonth];

        error_log("INFO: Finished yearly processing. Total invoices: " . $yearlySummary['totalInvoices']);

        $response = [
            'success' => true,
            'yearlySummary' => $yearlySummary,
            'currentMonth' => [
                'name' => $currentMonthName,
                'netAmount' => $yearlySummary[$currentMonthKey . 'NetAmount'] ?? 0
            ],
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

            // Magyar hónapnevek
            $hungarianMonths = [
                1 => 'Január', 2 => 'Február', 3 => 'Március', 4 => 'Április',
                5 => 'Május', 6 => 'Június', 7 => 'Július', 8 => 'Augusztus',
                9 => 'Szeptember', 10 => 'Október', 11 => 'November', 12 => 'December'
            ];

            // Az aktuális lekérdezési időszak évének és hónapjának meghatározása dateFrom alapján
            $currentYear = (int)date('Y', strtotime($requestData['dateFrom']));
            $currentMonth = (int)date('n', strtotime($requestData['dateFrom']));
            $currentMonthName = $hungarianMonths[$currentMonth];

            foreach ($allInvoices as $invoice) {
                $amount = (float)$invoice->invoiceNetAmountHUF;
                $isCrossYear = false;

                if (($invoice->invoiceOperation === 'STORNO' || $invoice->invoiceOperation === 'MODIFY') &&
                    isset($invoice->invoiceDeliveryDate)) {
                    $deliveryYear = (int)date('Y', strtotime($invoice->invoiceDeliveryDate));
                    if ($deliveryYear < $currentYear) {
                        $isCrossYear = true;
                        if ($invoice->invoiceOperation === 'STORNO') {
                            $crossYearStornos++;
                        } elseif ($invoice->invoiceOperation === 'MODIFY') {
                            $crossYearModified++;
                        }
                    }
                }

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
                    // cross-year darabszámok beleszámolása
                    switch ($invoice->invoiceOperation) {
                        case 'STORNO':
                            $stornoInvoices++;
                            break;
                        case 'MODIFY':
                            $modifiedInvoices++;
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
                    'totalInvoices' => count($allInvoices),
                    'crossYearStornos' => $crossYearStornos,
                    'crossYearModified' => $crossYearModified,
                    'currentMonth' => [
                        'name' => $currentMonthName,
                        'netAmount' => $totalAmount + $modifiedAmount - $stornoAmount
                    ]
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
