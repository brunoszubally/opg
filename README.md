# NAV Online Pénztárgép (OPG) API Kliens és Sync Service

Python kliens és cloud-based sync service a NAV Online Pénztárgép API-hoz.

## Két használati mód

### 1. CLI Tool (Helyi használat)
Parancssorból történő manuális letöltés és feldolgozás egyedi felhasználókhoz.

### 2. Cloud Sync Service (Multi-tenant SaaS)
Render.com-on futó automatikus szinkronizáló service, Adalo adatbázis integrációval:
- Multi-tenant: több user egyidejű kezelése
- Automatikus napi szinkronizálás (10 napos threshold)
- Manuális szinkronizálási végpont
- Napi bevételek aggregálása és tárolása Adalo-ban
- REST API endpoints

## CLI Tool Funkciók

- ✅ Pénztárgép státusz lekérdezése (elérhető fájlok száma)
- ✅ Naplófájlok (.p7b) letöltése
- ✅ Automatikus ZIP kicsomagolás
- ✅ Hitelesítés SHA-512 és SHA3-512 hash-ekkel
- ✅ SOAP 1.2 kommunikáció MTOM mellékletekkel

## Cloud Sync Service Funkciók

- ✅ Multi-tenant architektúra (user-specifikus NAV credentials)
- ✅ Automatikus napi szinkronizálás (cron job)
- ✅ Manuális szinkronizálás API végponton keresztül
- ✅ Napi bevételek aggregálása (csak aktuális év, sikeres nyugták)
- ✅ Adalo adatbázis integráció
- ✅ REST API endpoints (health check, sync status)
- ✅ API key alapú autentikáció

## Telepítés

```bash
pip install requests
```

## Használat

### 1. Státusz lekérdezése

```bash
python3 opg.py status --ap A29201112
```

**Kimenet:**
```
✓ Státusz lekérdezés sikeres
  AP szám: A29201112
  Utolsó kommunikáció: 2025-10-23T07:36:36Z
  Utolsó fájl dátuma: 2025-10-24T00:00:00Z
  Elérhető fájlok: 740 - 763 (24 db)
```

### 2. Naplófájlok letöltése

```bash
# Megadott tartomány letöltése
python3 opg.py files --ap A29201112 --start 740 --end 763 --out ./downloads

# Csak egy fájl letöltése
python3 opg.py files --ap A29201112 --start 740 --end 740 --out ./downloads

# Összes elérhető fájl letöltése (end nélkül)
python3 opg.py files --ap A29201112 --start 740 --out ./downloads
```

**Kimenet:**
```
✓ Sikeresen letöltve 4 fájl
  Mentve: downloads/
  P7B fájlok: 4 db
```

### Debug mód

Debug információk megjelenítéséhez add hozzá a `--debug` flaget:

```bash
python3 opg.py status --ap A29201112 --debug
python3 opg.py files --ap A29201112 --start 740 --end 743 --out ./downloads --debug
```

Ez kiírja:
- A teljes XML kérést
- HTTP válasz headereket
- Signature számítás részleteit
- Nyers SOAP választ

## Hitelesítési adatok beállítása

A hitelesítési adatok az `opg.py` fájl elején találhatók:

```python
TECH_LOGIN      = "..."           # Technikai felhasználó login
TECH_PASSWORD   = "..."           # Jelszó
SIGNING_KEY     = "..."           # signKey (KÖTŐJELEKKEL!)
EXCHANGE_KEY    = "..."           # exchangeKey (opcionális)
TAX_NUMBER_8DIG = "..."           # Adószám első 8 számjegye
AP_NUMBER       = "..."           # AP szám (pl. A29201112)
```

**FONTOS:** A `SIGNING_KEY`-t az eredeti formátumban kell megadni, **kötőjelekkel együtt**!

## Fájl struktúra

Letöltés után a fájlok a következő struktúrában jelennek meg:

```
downloads/
├── attachment_0.zip                  # Letöltött ZIP
├── attachment_0_unzipped/            # Kibontott mappa
│   └── A29201112_77317012_20251009175837_740.p7b
├── attachment_1.zip
├── attachment_1_unzipped/
│   └── A29201112_77317012_20251010010326_741.p7b
...
```

A P7B fájlok aláírt PKCS#7 konténerek, amelyek tartalmazzák a pénztárgép naplóját.

## P7B fájlok kinyerése

Az `extract_p7b.py` script segítségével kinyerheted az XML tartalmat a P7B konténerekből:

```bash
# Egy fájl kinyerése
python3 extract_p7b.py opg_downloads/attachment_0_unzipped/A29201112_77317012_20251009175837_740.p7b

# Több fájl kinyerése wildcard-dal
python3 extract_p7b.py opg_downloads/*/A*.p7b

# Kimeneti mappa megadása
python3 extract_p7b.py opg_downloads/*/A*.p7b --out-dir ./extracted_xml
```

**Kimenet:**
```
Feldolgozás: A29201112_77317012_20251009175837_740.p7b
  ✓ Regex-alapú kinyerés sikeres
  → Mentve: extracted_xml/A29201112_77317012_20251009175837_740.xml
  Méret: 26,028 bytes, 113 sor

============================================================
✓ Sikeres: 1
```

### XML struktúra

A kinyert XML fájlok a következő elemeket tartalmazzák:

- **LON** - Log file indítás (fájl azonosítók, hash)
- **INF** - Pénztárgép információk (típus, firmware, SIM kártya adatok, helyszín)
- **STA** - Státusz információk (tárterület, akkumulátor, stb.)
- **OPR** - Műveleti információk (adatforgalom, hálózat)
- **POS** - GPS koordináták időbélyeggel
- **NYN** - Nyugták/Bizonylatok (a tényleges eladási adatok!)
- **EVT** - Események (kommunikáció a NAV szerverrel, hibaüzenetek)

**Példa nyugta (NYN elem):**
```xml
<NYN>
  <RSR>11</RSR>
  <BSR>5669</BSR>
  <DTS>2025-10-22T01:52:12+02:00</DTS>
  <TSZ>77317012</TSZ>
  <NSZ>0468/00002</NSZ>
  <ITL>
    <NA>VITELDÍJ</NA>
    <PN>GY.05</PN>
    <UN>4480</UN>
    <QY>1,000</QY>
    <SU>4480</SU>
    <VC>E00</VC>
  </ITL>
  <RND>0</RND>
  <SUM>4480</SUM>
  ...
</NYN>
```

## Parancsok összefoglalója

```bash
# Help
python3 opg.py -h
python3 opg.py status -h
python3 opg.py files -h

# Státusz
python3 opg.py status --ap <AP_SZÁM> [--debug] [--use-exchange-key]

# Fájlok
python3 opg.py files --ap <AP_SZÁM> --start <SZÁM> [--end <SZÁM>] [--out <MAPPA>] [--debug]
```

## Gyakori problémák

### INVALID_REQUEST_SIGNATURE

Ha ezt a hibát kapod:
- Ellenőrizd, hogy a `SIGNING_KEY` **kötőjelekkel** van-e megadva (pl. `0f-aac2-...`)
- Próbáld meg az `EXCHANGE_KEY`-t használni: `--use-exchange-key`
- Ellenőrizd, hogy a kulcsok érvényesek és aktívak a NAV portálon

### HTTP 403

- Ellenőrizd az endpoint URL-t
- Ellenőrizd, hogy a technikai felhasználó jogosult-e az OPG API használatára

### Nincs elérhető fájl

Ha a státusz `0 - 0` tartományt mutat:
- A pénztárgép még nem küldött naplót a NAV-hoz
- Ellenőrizd, hogy helyes AP számot használsz-e

## API dokumentáció

- GitHub: https://github.com/nav-gov-hu/Online-Cash-Register-Logfile
- NAV OPG portál: https://onlineszamla.nav.gov.hu

## Issue-k és megoldások

A kód a következő GitHub issue-k alapján készült:
- [#30](https://github.com/nav-gov-hu/Online-Cash-Register-Logfile/issues/30) - Content-Type és pattern követelmények
- [#31](https://github.com/nav-gov-hu/Online-Cash-Register-Logfile/issues/31) - Wrapper elemek
- [#38](https://github.com/nav-gov-hu/Online-Cash-Register-Logfile/issues/38) - Namespace-ek
- [#66](https://github.com/nav-gov-hu/Online-Cash-Register-Logfile/issues/66) - Timestamp formázás signature számításhoz

## Technikai részletek

- **SOAP 1.2** protokoll
- **SHA-512** password hash (NAGYBETŰS)
- **SHA3-512** request signature (NAGYBETŰS)
- **Timestamp formátum XML-ben**: `YYYY-MM-DDTHH:MM:SS.sssZ` (milliszekundum pontosság)
- **Timestamp formátum signature-ben**: `YYYYMMDDHHMMSS` (másodperc pontosság, 14 karakter)
- **requestId pattern**: `[+a-zA-Z0-9_]{1,30}` (max 30 karakter)
- **softwareId pattern**: `[0-9A-Z\-]{18}` (pontosan 18 karakter)

---

# Cloud Sync Service Deployment

## Architektúra

A Cloud Sync Service Render.com-on fut és két komponensből áll:

1. **Web Service** (`web_api.py`): Flask REST API a manuális és automatikus szinkronizáláshoz
2. **Cron Job** (`cron_sync.py`): Napi automatikus szinkronizálás 02:00 UTC-kor

## Adalo Adatbázis Integráció

### Users collection (`t_13c9aa8bd9dd423b8118565dec7fb3de`)

Szükséges mezők:
- `id` (Number, auto)
- `Email` (Email)
- `first_name` (Text)
- `onlinepenztargep` (True/False) - **OPG sync enable/disable flag** (FONTOS!)
- `navlogin` (Text) - NAV technikai felhasználó login
- `navpassword` (Text) - NAV jelszó
- `signKey` (Text) - NAV signing key (kötőjelekkel!)
- `exchangeKey` (Text) - NAV exchange key (opcionális)
- `taxNumber` (Text) - 8 számjegyű adószám
- `apnumber` (Text) - AP szám (pl. A29200455)
- `lastbizonylatszinkron` (Date/Time) - Utolsó szinkronizálás ideje
- `lastbizonylatletoltve` (Text) - Utoljára letöltött fájl sorszáma

**FONTOS:** Csak azok a userek lesznek szinkronizálva, akiknél `onlinepenztargep = true`!

### opginvoices collection (`t_22imanannzgjm04zm2rbifxzm`)

Szükséges mezők:
- `id` (Number, auto)
- `user_adoszama` (Text) - User adószáma
- `user_opginvoice` (Relationship) - Kapcsolat a users collection-nel
- `fajl_sorszama` (Text) - Fájl sorszáma
- `volt_tranzakcio` (Text) - Nyugták száma
- `bizonylatsummary` (Text) - Bruttó összeg (HUF)
- `fajldatuma` (Date) - Dátum (YYYY-MM-DD)

## Render.com Deployment

### 1. Repo előkészítése

```bash
git add .
git commit -m "Add cloud sync service"
git push origin main
```

### 2. Render.com projekt létrehozása

1. Menj a https://render.com oldalra és jelentkezz be
2. New → Blueprint
3. Connect GitHub repository
4. A `render.yaml` automatikusan felismeri a konfigurációt

### 3. Environment változók beállítása

A Render dashboard-on állítsd be a következő titkosított változókat:

```
ADALO_API_KEY=5zhnd694f4hggnz8fk1g3n0vr
API_KEY=your_secure_random_api_key_here
```

A többi változó már be van állítva a `render.yaml`-ban.

### 4. Deploy

A Render automatikusan indítja a deploy-t. Két service jön létre:
- `opg-sync-api` (Web service)
- `opg-sync-cron` (Daily cron job)

## API Endpoints

### Health Check

```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "opg-sync-service",
  "timestamp": "2025-11-25T17:30:00.000Z"
}
```

### Sync Status

Lekérdezi az összes user szinkronizálási státuszát.

```bash
curl -X GET "https://opg-sync-api.onrender.com/api/status" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Response:**
```json
{
  "success": true,
  "timestamp": "2025-11-25T17:30:00.000Z",
  "total_users": 10,
  "users": [
    {
      "user_id": 1,
      "user_name": "Brúnó Szubally",
      "user_email": "szubally.bruno@gmail.com",
      "ap_number": "A29200455",
      "last_sync": "2025-11-20T02:00:00.000Z",
      "last_file_number": "1079"
    }
  ]
}
```

### Automatic Sync (All Users)

Szinkronizálja az összes usert, akiknél eltelt 10+ nap az utolsó szinkron óta.

```bash
curl -X POST "https://opg-sync-api.onrender.com/api/sync/all" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "days_threshold": 10,
    "current_year": 2025
  }'
```

**Response:**
```json
{
  "success": true,
  "timestamp": "2025-11-25T17:30:00.000Z",
  "total_users": 5,
  "successful": 4,
  "failed": 1,
  "user_results": [
    {
      "user_id": 1,
      "user_name": "Brúnó Szubally",
      "user_email": "szubally.bruno@gmail.com",
      "success": true,
      "message": "Synced 10 files, created 8 daily revenue records",
      "files_synced": 10,
      "revenues_created": 8
    }
  ]
}
```

### Manual Sync (Single User)

Manuálisan szinkronizál egy adott usert (függetlenül a 10 napos threshold-tól).

```bash
curl -X POST "https://opg-sync-api.onrender.com/api/sync/1" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "current_year": 2025
  }'
```

**Response:**
```json
{
  "success": true,
  "timestamp": "2025-11-25T17:30:00.000Z",
  "user_id": 1,
  "user_name": "Brúnó Szubally",
  "user_email": "szubally.bruno@gmail.com",
  "message": "Synced 5 files, created 4 daily revenue records",
  "files_synced": 5,
  "revenues_created": 4
}
```

## Lokális Fejlesztés

### 1. Környezet előkészítése

```bash
# Dependencies telepítése
pip install -r requirements.txt

# .env fájl létrehozása
cp .env.example .env
# Szerkeszd a .env fájlt és add meg az API kulcsokat
```

### 2. Adalo tesztelés

```bash
# Adalo client tesztelése
python3 adalo_client.py

# Sync service tesztelése
python3 sync_service.py
```

### 3. Web API indítása

```bash
# Development mode
python3 web_api.py

# Production mode (Gunicorn)
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 web_api:app
```

### 4. API tesztelése lokálisan

```bash
# Health check
curl http://localhost:5000/health

# Sync all users
curl -X POST http://localhost:5000/api/sync/all \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json"

# Sync single user
curl -X POST http://localhost:5000/api/sync/1 \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json"
```

## Működési Logika

### Automatikus Napi Szinkronizálás

1. **Cron job indul** (naponta 02:00 UTC-kor)
2. **Users lekérdezése** Adalo-ból
3. **Szűrés**: csak azok, akiknél eltelt 10+ nap az utolsó szinkron óta
4. **Minden userre**:
   - NAV státusz lekérdezése (elérhető fájlok)
   - Új fájlok letöltése (last_file_number óta)
   - XML feldolgozás és nyugták kinyerése
   - Napi aggregálás (aktuális év, csak sikeres nyugták)
   - Adalo opginvoices rekordok létrehozása
   - User sync státusz frissítése

### Napi Aggregálás Szabályok

- **Current year csak**: Csak az aktuális év nyugtái (DTS mező alapján)
- **Sikeres nyugták**: Töröltek kihagyása (CNC=1 nyugták)
- **Bruttó összeg**: SUM mező (forintban)
- **Egy rekord naponta**: Ugyanazon nap összes nyugtája összesítve

### Rate Limiting

- Adalo API: 5 request/sec (0.2s delay között)
- NAV API: Nincs hivatalos limit, de 120s timeout
- Retry logic: 429 (rate limit) esetén 1s várakozás és újrapróbálkozás

## Fájlok

### Core Components
- `opg.py` - NAV API kliens (SOAP kommunikáció, P7B extraction)
- `adalo_client.py` - Adalo REST API wrapper
- `sync_service.py` - Szinkronizálási logika (NAV + XML + aggregáció)
- `web_api.py` - Flask REST API endpoints
- `cron_sync.py` - Cron job script

### Configuration
- `requirements.txt` - Python dependencies
- `render.yaml` - Render.com deployment config
- `.env.example` - Environment változók template

### Documentation
- `README.md` - Teljes dokumentáció
- `extract_p7b.py` - Standalone P7B extraction tool (opcionális)

## Troubleshooting

### "Missing NAV credentials" hiba

Ellenőrizd, hogy a user-nek be vannak-e állítva az összes szükséges mező:
- `navlogin`
- `navpassword`
- `signKey` (kötőjelekkel!)
- `taxNumber`
- `apnumber`

### "Failed to query NAV status" hiba

- Ellenőrizd, hogy az AP szám helyes-e
- Ellenőrizd, hogy a NAV credentials érvényesek-e
- Próbáld meg az exchange key-t használni (ha van)

### "No new files to sync" üzenet

Ez normális, ha már minden fájl le van töltve. A user `lastbizonylatletoltve` értéke megegyezik a NAV szerver max file number-ével.

### Rate limit exceeded

Ha túl sok user van, állítsd be a cron job gyakoriságát ritkábbra, vagy növeld a delay-t az `adalo_client.py`-ban.

## Költségek (Render.com)

- **Starter Plan**: $7/hónap (web service + cron job)
- **Free Plan**: Korlátozott óraszám (750 óra/hónap), alvó üzemmód 15 perc inaktivitás után

## Biztonság

- API key authentication minden véd végponton
- HTTPS kommunikáció
- NAV credentials titkosítatlanul tárolva Adalo-ban (később titkosítás ajánlott)
- Environment változók titkosítva Render.com-on

## Licenc

MIT
