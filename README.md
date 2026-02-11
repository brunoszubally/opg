# OPG Sync Service

NAV Online Penztargep (OPG) es Online Szamla szinkronizacios szolgaltatas.
Adalo CMS-be szinkronizalja a felhasznalok NAV penztargep naplofajljait es online szamla adatait.

## Attekintes

Ez a szolgaltatas ket NAV rendszerbol gyujt adatokat es tarolja oket Adalo-ban:

1. **OPG (Online Penztargep)**: Penztargep naplofajlok letoltese, XML feldolgozas, napi bevetel aggregalas
2. **Online Szamla (OSZ)**: Szamla adatok lekerdezese, havi osszesites, KATA szazalek szamitas

A szolgaltatas Flask API-kent fut Render.com-on, es REST endpointokon keresztul erheto el.

---

## Architektura

```
                         +------------------+
                         |   Adalo Mobile   |
                         |       App        |
                         +--------+---------+
                                  |
                                  v
+----------------+       +------------------+       +------------------+
|  Render Cron   | ----> |    web_api.py    | ----> |  adalo_client.py |
|  (02:00 UTC)   |       |   Flask REST API |       |  Adalo REST API  |
+----------------+       +--------+---------+       +------------------+
                                  |
                         +--------+---------+
                         |                  |
                    +----v-----+     +------v---------+
                    |sync_     |     |online_invoice_ |
                    |service.py|     |sync_service.py |
                    +----+-----+     +------+---------+
                         |                  |
                    +----v-----+     +------v---------+
                    |  opg.py  |     |nav_online_     |
                    | NAV OPG  |     |invoice.py      |
                    | SOAP API |     | NAV OSZ v3 API |
                    +----------+     +----------------+
                         |
                    +----v-----+
                    |sftp_     |
                    |uploader.py|
                    | FTP backup|
                    +----------+
```

---

## API Endpointok

### `GET /health`

Health check endpoint. Nem igenyel autentikaciót.

**Valasz:**
```json
{
  "status": "healthy",
  "service": "opg-sync-service",
  "timestamp": "2026-01-15T10:30:00.000000"
}
```

**Pelda:**
```bash
curl https://opg-sync-api.onrender.com/health
```

---

### `POST /api/sync/all`

Osszes felhasznalo szinkronizalasa, akiknel 10+ napja nem tortent szinkronizalas.

**Auth:** `Authorization: Bearer {API_KEY}`

**Request body (opcionalis):**
```json
{
  "days_threshold": 10,
  "current_year": 2026
}
```

**Valasz (200):**
```json
{
  "success": true,
  "timestamp": "2026-01-15T02:00:00.000000",
  "total_users": 3,
  "successful": 3,
  "failed": 0,
  "skipped": 2,
  "user_results": [
    {
      "user_id": 146,
      "user_name": "Bela",
      "user_email": "bela@example.com",
      "success": true,
      "message": "Synced 5 files, created 5 daily revenue records",
      "files_synced": 5,
      "revenues_created": 5
    }
  ]
}
```

**Pelda:**
```bash
curl -X POST "https://opg-sync-api.onrender.com/api/sync/all" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"days_threshold": 10}'
```

---

### `POST /api/sync/<user_id>`

Egyetlen felhasznalo manualis szinkronizalasa (csak OPG).

**Auth:** `Authorization: Bearer {API_KEY}`

**URL parameter:** `user_id` — Adalo user ID (int)

**Request body (opcionalis):**
```json
{
  "current_year": 2026
}
```

**Valasz (200):**
```json
{
  "timestamp": "2026-01-15T10:30:00.000000",
  "user_id": 146,
  "user_name": "Bela",
  "user_email": "bela@example.com",
  "success": true,
  "message": "Synced 5 files, created 5 daily revenue records",
  "files_synced": 5,
  "revenues_created": 5
}
```

**Hibak:** `404` ha a user nem letezik, `500` ha a szinkronizalas sikertelen.

**Pelda:**
```bash
curl -X POST "https://opg-sync-api.onrender.com/api/sync/146" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### `GET /api/status`

Osszes OPG felhasznalo szinkronizacios allapota.

**Auth:** `Authorization: Bearer {API_KEY}`

**Valasz (200):**
```json
{
  "success": true,
  "timestamp": "2026-01-15T10:30:00.000000",
  "total_users": 5,
  "users": [
    {
      "user_id": 146,
      "user_name": "Bela",
      "user_email": "bela@example.com",
      "ap_number": "A29200455",
      "last_sync": "2026-01-14T02:00:00+00:00",
      "last_file_number": "1169"
    }
  ]
}
```

**Pelda:**
```bash
curl "https://opg-sync-api.onrender.com/api/status" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### `POST /api/full-sync/<user_id>`

Teljes szinkronizalas: OPG + Online Szamla egyutt.

**Auth:** `Authorization: Bearer {API_KEY}`

**URL parameter:** `user_id` — Adalo user ID (int)

**Request body (opcionalis):**
```json
{
  "current_year": 2026
}
```

**Valasz (200):**
```json
{
  "success": true,
  "user_id": 146,
  "user_name": "Bela",
  "user_email": "bela@example.com",
  "timestamp": "2026-01-15T10:30:00.000000",
  "opg_sync": {
    "success": true,
    "message": "Synced 5 files, created 5 daily revenue records",
    "files_synced": 5,
    "revenues_created": 5
  },
  "online_invoice_sync": {
    "success": true,
    "message": "Synced 42 online invoices (5200000 Ft) + OPG (800000 Ft) = Total: 6000000 Ft, KATA: 33%",
    "total_invoices": 42,
    "online_invoice_net": 5200000,
    "opg_net": 800000,
    "combined_net": 6000000,
    "total_kata_percent": 33
  }
}
```

**Pelda:**
```bash
curl -X POST "https://opg-sync-api.onrender.com/api/full-sync/146" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### `GET|POST /api/online-invoice/query`

NAV Online Szamla adatok kozvetlen lekerdezese. Harom mod tamogatott:

1. **Normal**: Osszes szamla visszaadasa (`invoices` lista)
2. **Summary**: Havi aggregacio (`summary` objektum)
3. **Yearly**: 12 honap aggregacio (`yearlySummary` objektum)

**Auth:** `X-API-Key` header vagy `apiKey` query parameter.
Ervenyes kulcs: `aXJ2b2x0YXNlY3VyZWFwaWtleTIwMjQ=`

**Parameterek (POST JSON vagy GET query):**

| Parameter     | Kotelezo | Leiras                                          |
|---------------|----------|-------------------------------------------------|
| `login`       | igen     | NAV technikai felhasznalo login                  |
| `password`    | igen     | NAV technikai felhasznalo jelszo                 |
| `taxNumber`   | igen     | Adoszam (8 szamjegy, HU prefix opcionalis)       |
| `signKey`     | igen     | Alairas kulcs                                    |
| `exchangeKey` | igen     | Csere kulcs                                      |
| `dateFrom`    | igen     | Kezdo datum (YYYY-MM-DD)                         |
| `dateTo`      | igen     | Zaro datum (YYYY-MM-DD)                          |
| `summary`     | nem      | `"true"` — havi osszesites mod                   |
| `yearly`      | nem      | `"true"` — eves osszesites mod (12 honap)        |

**Pelda (eves osszesites):**
```bash
curl -X POST "https://opg-sync-api.onrender.com/api/online-invoice/query" \
  -H "X-API-Key: aXJ2b2x0YXNlY3VyZWFwaWtleTIwMjQ=" \
  -H "Content-Type: application/json" \
  -d '{
    "login": "tech_user",
    "password": "tech_pass",
    "taxNumber": "12345678",
    "signKey": "sign-key-here",
    "exchangeKey": "exchange-key-here",
    "dateFrom": "2026-01-01",
    "dateTo": "2026-12-31",
    "yearly": "true"
  }'
```

---

## Modulok leirasa

### `web_api.py`
Flask alkalmazas. Definiálja az osszes REST endpointot, API key autentikaciót (`Authorization: Bearer` header), es hiba kezelest. A `gunicorn` WSGI szerveren fut produkcios kornyezetben.

### `adalo_client.py`
Adalo Collections REST API wrapper. Kezeli a rate limitinget (5 req/sec), paginaciót, es a kovetkezo muveleteket:
- Felhasznalok lekerdezese es frissitese
- Napi bevetel rekordok letrehozasa
- Szinkronizacios statusz kezeles
- Online Szamla aggregalt adatok frissitese

### `sync_service.py`
OPG szinkronizacios logika. Fobb funkciok:
- NAV OPG statusz lekerdezes (elerheto fajlok min/max szama)
- Naplofajlok letoltese (ZIP + P7B + XML kinyeres)
- XML feldolgozas: nyugtak kinyerese, datum es osszeg parszolas
- Napi bevetel aggregalas fajlonkent
- Adalo rekordok letrehozasa es szinkronizacios statusz frissites
- Opcionalis FTP feltoltes

### `online_invoice_api.py`
Flask endpoint handler a NAV Online Szamla lekerdezesekhez. Harom modot tamogat:
- **Normal**: Osszes szamla visszaadasa
- **Summary**: Havi aggregacio (netto osszeg, storno, modositott szamlak)
- **Yearly**: 12 honapos aggregacio honapokra bontva

Kezeli a cross-year storno szamlakat (elozo evi teljesitesi datumu stornok kihagyasa).

### `online_invoice_sync_service.py`
Online Szamla adatok szinkronizalasa Adalo felhasznalo rekordokba. Fobb funkciok:
- 12 honap szamla lekerdezes es aggregalas
- KATA szazalek szamitas (havi es eves szinten)
- Evkozben kezdett vallalkozasok aranyos limit szamitasa
- OPG + Online Szamla osszesitett bevetel szamitas
- Adalo mezo frissites (havonkenti netto, szamlaszam, KATA %)

### `nav_online_invoice.py`
NAV Online Szamla API v3 Python kliens. Implementalja:
- XML keres epites (header, user autentikacio, software blokk)
- SHA-512 jelszo hash es SHA3-512 keres alairas
- `queryInvoiceDigest` endpoint hivasa paginacioval
- XML valasz feldolgozas dict-be
- Adoszam normalizalas (HU prefix, kotojel kezeles)

### `sftp_uploader.py`
FTP feltolto modul XML fajlok biztonsagi mentesere. Konyvtarstruktura:
`{base_path}/{ap_number}/{year}/` (pl. `users/opg_bizonylatok/A29200455/2026/`)

### `opg.py`
NAV OPG SOAP API kliens. CLI eszkoz es modul:
- `status` — Penztargep statusz lekerdezes (elerheto fajl tartomany)
- `files` — Naplofajlok letoltese adott tartomanybol
- `download-all` — Osszes elerheto fajl letoltese, ZIP kibontas, P7B → XML konverzio

SOAP/MTOM kommunikacio a NAV OPG vegponttal (`api-onlinepenztargep.nav.gov.hu`).

### `cron_sync.py`
Napi automatikus szinkronizacio script. A Render.com cron job hivja naponta 02:00 UTC-kor.
HTTP POST keressel hivja a web service `/api/sync/all` endpointjat.

---

## Adatfolyamok

### OPG Sync Flow

```
1. Adalo-bol lekerdezi a felhasznalokat (onlinepenztargep=true, 10+ napos threshold)
2. Minden felhasznalora:
   a. NAV OPG status query -> elerheto fajlok (min-max fileNumber)
   b. Utolso szinkronizalt fajl utan ujak letoltese
   c. NAV valasz: MTOM multipart -> ZIP mellekletek
   d. ZIP kibontas -> P7B fajlok
   e. P7B -> XML konverzio (OpenSSL CMS vagy regex)
   f. XML feldolgozas: NYN (nyugta) elemek, SUM (osszeg), CNC (sztorno)
   g. Aggregalas fajlonkent: datum, nyugtaszam, osszbevetel
   h. Adalo-ba iras: revenues collection (1 rekord / fajl)
   i. Opcionalis: XML fajlok FTP feltoltese
   j. User sync statusz frissites (lastbizonylatszinkron, lastbizonylatletoltve)
```

### Online Invoice Sync Flow

```
1. NAV Online Szamla API-n 12 honap lekerdezese (queryInvoiceDigest)
2. Honaponkent:
   a. Szamlak lekerdezese paginacioval
   b. Aggregalas: netto osszeg, storno, modositott
   c. Cross-year stornok szurese
   d. OPG havi bevetel hozzaadasa (revenues collection-bol)
   e. KATA szazalek szamitas: (OPG + Online Szamla) / havi limit * 100
3. Eves szinten:
   a. Osszes honap osszegzese
   b. Evkozben kezdett vallalkozas: aranyos eves limit
   c. Eves KATA %: osszesitett bevetel / eves limit * 100
4. Adalo user rekord frissitese (havi netto, szamlaszam, KATA %, stb.)
```

### Full Sync Flow

```
1. User letoltese Adalo-bol
2. OPG sync (ha van apnumber + navlogin + navpassword)
3. Online Invoice sync (ha van navlogin + navpassword + signKey + exchangeKey + taxNumber)
4. Osszesitett eredmeny visszaadasa
```

---

## Kornyezeti valtozok

### Kotelezo

| Valtozo                          | Leiras                                      |
|----------------------------------|---------------------------------------------|
| `ADALO_APP_ID`                   | Adalo alkalmazas ID                          |
| `ADALO_API_KEY`                  | Adalo API Bearer token (titkos)              |
| `ADALO_USERS_COLLECTION_ID`     | Users collection ID                          |
| `ADALO_REVENUES_COLLECTION_ID`  | Revenues (napi bevetel) collection ID        |
| `API_KEY`                        | API autentikacio kulcs a sync endpointokhoz  |

### Opcionalis

| Valtozo              | Alapertelmezett                        | Leiras                               |
|----------------------|----------------------------------------|---------------------------------------|
| `FTP_HOST`           | —                                      | FTP szerver hostname                  |
| `FTP_USER`           | —                                      | FTP felhasznalonev                    |
| `FTP_PASSWORD`       | —                                      | FTP jelszo                            |
| `FTP_PORT`           | `21`                                   | FTP port                              |
| `FTP_BASE_PATH`      | `users/opg_bizonylatok`               | FTP base konyvtar                     |
| `WEB_SERVICE_URL`    | `https://opg-sync-api.onrender.com`   | Web service URL (cron job szamara)    |
| `PORT`               | `5000`                                 | Lokalis fejlesztesi port              |

---

## Deployment (Render.com)

### Build es start

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web_api:app`
- **Health check:** `GET /health`

### Cron job

A `cron_sync.py` naponta 02:00 UTC-kor fut es hivja a `/api/sync/all` endpointot.
A `render.yaml` tartalmazza a cron job konfiguraciót.

### render.yaml struktura

```yaml
services:
  # Web service - Flask API
  - type: web
    name: opg-sync-api
    env: python
    region: frankfurt
    startCommand: gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web_api:app

  # Cron job - Daily sync
  - type: cron
    name: opg-daily-sync
    env: python
    region: frankfurt
    schedule: "0 2 * * *"
    startCommand: python cron_sync.py
```

### Deploy lepesei

1. GitHub repository csatlakoztatasa Render.com-on
2. **New -> Blueprint** — Render automatikusan felismeri a `render.yaml`-t
3. Environment valtozok beallitasa a Render Dashboard-on (titkos kulcsok)
4. Deploy es teszteles: `curl https://opg-sync-api.onrender.com/health`

---

## Adalo mezok

### Users collection

| Mezo                       | Tipus    | Leiras                                    |
|----------------------------|----------|-------------------------------------------|
| `Email`                    | string   | Felhasznalo email                          |
| `first_name`               | string   | Nev                                        |
| `onlinepenztargep`         | boolean  | OPG szinkronizalas engedelyezve             |
| `navlogin`                 | string   | NAV technikai user login                   |
| `navpassword`              | string   | NAV technikai user jelszo                  |
| `signKey`                  | string   | NAV alairas kulcs                          |
| `exchangeKey`              | string   | NAV csere kulcs                            |
| `taxNumber`                | string   | Adoszam (pl. 69785346-1-29)                |
| `apnumber`                 | string   | Penztargep AP szam (pl. A29200455)          |
| `lastbizonylatszinkron`    | datetime | Utolso OPG szinkronizalas idopontja         |
| `lastbizonylatletoltve`    | string   | Utolso letoltott fajl sorszama              |
| `evkozbenkezdte`           | boolean  | Evkozben kezdett vallalkozas               |
| `evkozbenkezdtedatum`      | datetime | Evkozben kezdes datuma                     |
| `jannet` .. `decnet`       | number   | Havi netto online szamla osszeg            |
| `janinvoices` .. `decinvoices` | number | Havi szamlaszam                        |
| `novincoices`              | number   | Novemberi szamlaszam (typo az Adalo-ban!)   |
| `jankatapercent` .. `deckatapercent` | number | Havi KATA szazalek            |
| `totalnet`                 | number   | Eves osszes online szamla netto             |
| `allinvoices`              | number   | Eves osszes szamlaszam                     |
| `totalkatapercent`         | number   | Eves osszesitett KATA szazalek             |
| `userkerete`               | number   | KATA eves keret (aranyos, ezer Ft-ra kerekitett) |
| `currentMonth_name`        | string   | Aktualis honap neve (magyarul)             |
| `currentMonth_amount`      | number   | Aktualis honap netto osszege                |
| `lastupdate`               | datetime | Utolso Online Szamla frissites idopontja    |

### Revenues collection

| Mezo                | Tipus    | Leiras                                    |
|---------------------|----------|-------------------------------------------|
| `user_adoszama`     | string   | Felhasznalo adoszama                       |
| `user_opginvoice`   | relation | Kapcsolat a Users collection-nel (user ID) |
| `fajl_sorszama`     | string   | NAV naplofajl sorszama                     |
| `volt_tranzakcio`   | string   | Tranzakciok (nyugtak) szama                 |
| `bizonylatsummary`  | string   | Napi osszbevetel (Ft)                      |
| `fajldatuma`        | date     | Fajl datuma (YYYY-MM-DD)                   |

---

## NAV API-k

### OPG API (Online Penztargep)

- **Base URL:** `https://api-onlinepenztargep.nav.gov.hu`
- **Protokoll:** SOAP 1.2 (application/soap+xml)
- **Endpointok:**
  - `/queryCashRegisterFile/v1/queryCashRegisterStatus` — Penztargep statusz
  - `/queryCashRegisterFile/v1/queryCashRegisterFile` — Naplofajlok letoltese
- **Valasz formatum:** MTOM/multipart (ZIP mellekletek)
- **Autentikacio:** Technikai user (login + SHA-512 password hash + SHA3-512 request signature)
- **Namespace-ek:**
  - API: `http://schemas.nav.gov.hu/OPF/1.0/api`
  - Common: `http://schemas.nav.gov.hu/NTCA/1.0/common`

### Online Szamla API v3

- **Prod URL:** `https://api.onlineszamla.nav.gov.hu/invoiceService/v3`
- **Test URL:** `https://api-test.onlineszamla.nav.gov.hu/invoiceService/v3`
- **Protokoll:** REST XML
- **Fo endpoint:** `/queryInvoiceDigest` — Szamla osszesitok lekerdezese
- **Autentikacio:** Technikai user (login + SHA-512 password hash + SHA3-512 request signature)
- **Namespace-ek:**
  - API: `http://schemas.nav.gov.hu/OSA/3.0/api`
  - Common: `http://schemas.nav.gov.hu/NTCA/1.0/common`
- **Paginacio:** `page` parameter (1-tol indulva), `availablePage` a valaszban

---

## Lokalis fejlesztes

### Elofeltetelek

- Python 3.11+
- OpenSSL (P7B -> XML konverziohoz)

### Telepites

```bash
# Virtualis kornyezet letrehozasa
python3 -m venv venv
source venv/bin/activate

# Fuggosegek telepitese
pip install -r requirements.txt

# Kornyezeti valtozok masolasa
cp .env.example .env
# Szerkeszd a .env fajlt a valos ertekekkel
```

### Futtatas

```bash
# Fejlesztoi szerver
python web_api.py

# Vagy gunicorn-nal (produkcios mod)
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 web_api:app
```

### Teszteles

```bash
# Health check
curl http://localhost:5000/health

# Sync all
curl -X POST http://localhost:5000/api/sync/all \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json"

# Egyedi user sync
curl -X POST http://localhost:5000/api/sync/146 \
  -H "Authorization: Bearer YOUR_API_KEY"

# Full sync (OPG + Online Szamla)
curl -X POST http://localhost:5000/api/full-sync/146 \
  -H "Authorization: Bearer YOUR_API_KEY"
```
