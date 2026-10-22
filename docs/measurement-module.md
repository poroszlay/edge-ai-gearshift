# ESP32 mérőmodul (#5)

A modul saját modell nélkül fejleszthető és átadható a #7 integrációjának.
A mellékelt próbaterhelés **25 ms-os mesterséges CPU-terhelés**, nem MLP,
szabályreferencia vagy tanult döntés. Az aktuális build-, teszt- és paneles
állapotot az [ellenőrzési napló](evidence/issue-5/verification.md) rögzíti.

## Publikus interfész és mérési pontok

A `firmware/esp32/components/measurement/include/measurement.h` hordozható
C++17 interfésze:

```cpp
Result run(Config config, Clock& clock, Workload& workload,
           Record* records, size_t capacity);
```

- `Config`: 1..1000 ütemezett feladat, 10000/20000/50000/100000 µs periódus,
  1..8 előtöltött ablak. A hívó birtokolja az ablakokat és az eredménypuffert.
- `Clock`: monoton mikrosekundumos óra és abszolút időpontig várakozás.
  `wait_until_us` nem térhet vissza a cél előtt. A hívó biztosítja, hogy az
  epoch és a sorozathossz összege reprezentálható legyen `int64_t` értékként.
- `Workload`: `prepare(window_index)`, `invoke()`, `finish()`. Ezek együtt
  egy feladatot valósítanak meg. A runtime-adapter saját előfeldolgozást,
  kvantálást, inferenciát és utófeldolgozást kapcsolhat ide.
- Az adapter `none`, `invalid_window`, `model_error` vagy `memory_error`
  eredményt ad. Hiba után a következő feldolgozási szakasz már nem fut.
  A mérőmodul nem ad döntési címkét, és nem alakít hibát tartás döntéssé.
- A `Result.error` konfigurációs/puffermérethibát jelez; ilyenkor nulla
  feladat fut. Egy feldolgozott feladat hibája a saját `Record.error` mezője;
  a sorozat további időpontjai továbbra is elszámolódnak.

Minden `Record` tartalmazza az ütemezési és ablakindexet, státuszt, hibát,
illetve ezeket a sorozat saját epochjához viszonyított időket [µs]:

| Mező | Mérési pont |
| --- | --- |
| `scheduled_us` | Eredeti időrács: index × periódus |
| `started_us` | Közvetlenül a `prepare` előtt |
| `inference_started_us` | Sikeres `prepare` után, az `invoke` előtt |
| `inference_finished_us` | Az `invoke` visszatérése után |
| `finished_us` | Az utolsó végrehajtott feldolgozási szakasz után |

Inferenciaidő = a két inferencia-időpont különbsége. Teljes MCU-feldolgozás
= `finished_us - started_us`; elő-/utófeldolgozást és a köztes mérési
instrumentációt is tartalmazza. A futás megszakításai beleszámítanak.
Indítási késés = `started_us - scheduled_us`, válaszidő =
`finished_us - scheduled_us`. Hiányzó idő C++-ban `-1`, JSON-ban `null`.

Az ütemező egyetlen végrehajtót használ, feladatsor nélkül. Az előző feladat
befejezése előtti időrácspont `missed`; az ütemező felébredésekor már teljesen
lejárt időrés szintén `missed`. A még le nem járt időrésben késleltetett
indítás engedett, de az eredeti határidő marad érvényes. Pontosan határidős
befejezés `ok`; azon túli befejezés `late`. Feldolgozási hiba `failed`,
hibakóddal. Ezek egymást kizáró státuszok.

Az utolsó elindított feladatot bevárjuk. `Result.end_us` legalább count × T,
illetve az utolsó befejezés; így a sorozat végén sincs rejtett függő feladat.
Reset vagy megszakított export esetén nincs teljes futást igazoló lezárás.

## Próbafirmware és reprodukálás

Hoston C++17 fordító és Python 3.10+ szükséges, ESP-IDF nélkül:

```bash
python3 -m unittest discover -s tests -p test_mcu_measurement.py -v
python3 -m unittest discover -s tests -p test_profiler.py -v
python3 -m unittest discover -s tests -p test_measurement_evidence.py -v
mkdir -p results/issue-5
g++ -std=c++17 -Wall -Wextra -Werror -pedantic \
  -Ifirmware/esp32/components/measurement/include \
  firmware/esp32/components/measurement/measurement.cc \
  firmware/esp32/measurement/main/probe.cc -o results/issue-5/probe
results/issue-5/probe > results/issue-5/host-benchmark.jsonl
python3 -m gearshift.profiler results/issue-5/host-benchmark.jsonl \
  --require-benchmark > results/issue-5/host-benchmark-report.json
results/issue-5/probe --live > results/issue-5/host-live.jsonl
python3 -m gearshift.profiler results/issue-5/host-live.jsonl
```

A hostóra virtuális: nincs falióra szerinti többperces várakozás; minden
ilyen futás `simulated:true`, az MCU-heap/stack mezők `null` értékűek.

Panelhez a [bringup útmutató](esp32-bringup.md) ESP-IDF v5.5.1 környezete
szükséges. A mérőprojektnek nincs TFLM- vagy #6-modellfüggősége. A két mód
külön buildet és konfigurációt kap; meglévő SDK-t ne telepíts újra.

```bash
# A saját SDK elhelyezésének megfelelő export.sh betöltése után:
bash firmware/esp32/measurement/build.sh benchmark
bash firmware/esp32/measurement/build.sh live
```

A generált fájlok: `firmware/esp32/measurement/build/{benchmark,live}/`.
Módkonfiguráció változásakor az adott build generált `sdkconfig` fájlja
elsőbbséget élvez a defaults felett; a két könyvtárat ne keverd össze.
Alapbeállítás: ESP32, DIO/40 MHz/4 MiB flash, CPU 240 MHz, UART0 115200 baud,
teljesítményre fordítás, 1000 Hz RTOS tick, főfeladat CPU1-en. Watchdogok
bekapcsolva maradnak; WiFi-t, rádiót és PSRAM-ot a program nem indít.

A runtime az `esp_timer_get_time()` órát használja. Az ütemezési várakozás
abszolút célra történik, a hosszabb várakozás RTOS-alvás. A 25 ms-os
`invoke` szakasz szándékosan aktív CPU-terhelés; a mért ideje tartalmazhat
megszakításokat. Az előfeldolgozás négy rögzített, szabályos 20×5 ablakon
ellenőriz és a közös szerződéssel skáláz; az utófeldolgozás ellenőrzőösszeget
képez, döntést nem. Az adatokat a kimenet nem módosítja.

Benchmarkban mind a négy profilhoz 100 bemelegítő és 3×1000 mért ütemezett
feladat tartozik: 16 sorozat, 12400 rekord. Az ablakindex mindig az
ütemezési index modulo ablakszám, kimaradáskor is. Élő próbában három
külön ablak fut, külön egyfeladatos adagban, 50 ms periódussal.

A sorozat eleji kiírás után `fflush` és az SDK ESP32-re javított
`esp_rom_output_tx_wait_idle()` függvénye kiüríti a TX-et. A `run` alatt
nincs UART-küldés/olvasás vagy formázás. Eredmények és memóriaadatok csak
utána mennek ki. ESP32-n minden exportált feladatrekord után egy RTOS-tick
várakozás engedi futni az idle feladatot; enélkül a polling UART-driver
hosszú exportja watchdog-jelzést okozhat. A várakozás csak az UART-szünet
része, nem a mért végrehajtásé. A `series_end.uart_wait_us` a korábbi végrehajtás vége és
az aktuális `run` hívás előtti mérési pont közötti teljes szünet: tartalmazza
az eredményátvitelt, a következő `series_start` fejléc átvitelét és a TX
kiürítését is. Az értéket a végrehajtás előtt lezárjuk, utána exportáljuk.
Az első sorozatnál a kiindulópont a `run_start` kiírása utáni időpont.
Ez főként átviteli idő, nem tiszta UART-driveridő, és nem része az
MCU-feldolgozási időnek. A kompatibilitás miatt megtartott
`series_start.uart_wait_us` csak a fejléc előtti részintervallum.

A profiler az új `series_end` mezőt használja, `uart_wait_scope=complete`
jelöléssel. Régi exportnál a fejlécbeli részértéket mutatja,
`uart_wait_scope=before_header` jelöléssel; ebből teljes szünet nem
állítható elő. A teljes érték nem lehet kisebb a fejléc előtti részértéknél.

### Paneles futtatás

A már benchmark firmware-rel feltöltött panel 25 másodperces, külön indítható
watchdog-regressziója (reseteli a panelt, párhuzamos portolvasó nélkül):

```bash
GEARSHIFT_TEST_ESP32_PORT=/dev/ttyUSB0 python -m unittest discover \
  -s tests -p test_measurement_hardware.py -v
```

Portváltozó nélkül a hardveres teszt kimarad a szokásos tesztfutásból.
Ez csak a korábban hibázó exportút rövid regressziója; a teljes négyprofilos
benchmarkot és az élő módot külön kell lefuttatni.


Előbb a hoston ellenőrizd a portot és a megnyithatóságot, majd a chipet és a
fizikai flashméretet. Azonosítatlan vagy eltérő panelre ne tölts ESP32-buildet.
EACCES esetén a saját terminálban adható hozzáférés:
`sudo setfacl -m u:richie:rw /dev/ttyUSB0`.

```bash
export GEARSHIFT_PORT=/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0
python -m esptool --chip auto --port "$GEARSHIFT_PORT" chip_id
python -m esptool --chip auto --port "$GEARSHIFT_PORT" flash_id

# Ez felülírja a panel programját. Az azonosított panelre:
idf.py -C firmware/esp32/measurement \
  -B firmware/esp32/measurement/build/live \
  -p "$GEARSHIFT_PORT" flash
python docs/evidence/issue-2/hardware-2026-10-19/capture_serial.py \
  "$GEARSHIFT_PORT" 10 results/issue-5/live-serial.log

idf.py -C firmware/esp32/measurement \
  -B firmware/esp32/measurement/build/benchmark \
  -p "$GEARSHIFT_PORT" flash
python docs/evidence/issue-2/hardware-2026-10-19/capture_serial.py \
  "$GEARSHIFT_PORT" 1400 results/issue-5/benchmark-serial.log
```

A korábbi capture-eszköz a reset előtt megnyitja az UART-ot és a teljes
bájtfolyamot megőrzi. A benchmark tényleges időben fut: a 25 ms-os terhelés
és a 115200 baud eredményátvitel miatt hosszú. Hiányzó lezáráskor a felvétel
részleges, nem sikeres. Minden sorozat külön folytonos mérés; a sorozatok
közötti UART-szünet miatt a teljes kampány nem egyetlen folytonos benchmark.

A nyers napló megtartása mellett a JSONL külön kinyerhető:

```bash
python3 - <<'PY'
import json
from pathlib import Path
for mode in ('live', 'benchmark'):
    source = Path(f'results/issue-5/{mode}-serial.log')
    rows = [json.loads(line) for line in source.read_bytes().splitlines()
            if line.startswith(b'{')]
    Path(f'results/issue-5/{mode}.jsonl').write_text(
        ''.join(json.dumps(row, allow_nan=False) + '\n' for row in rows))
PY
python3 -m gearshift.profiler results/issue-5/live.jsonl
python3 -m gearshift.profiler results/issue-5/benchmark.jsonl --require-benchmark
```

A nyers naplót is ellenőrizni kell reset, watchdog, panic, brownout és
allokációs hiba szempontjából. A JSON-kivonat önmagában nem igazol stabilitást
vagy fizikai UART-csendet. A chip/flash-, build-, flash- és ellenőrző napló,
teljes `sdkconfig`, forrásverzió és binárishash a mérési bizonyíték része.

## Export, statisztikák és memória

Az önálló bizonyítékformátum `schema=gearshift.measurement.v1`, JSON Lines.
Nem a `docs/communication.md` szerinti vezérlőprotokoll új verziója.
Egy fájl egy futás: `run_start`, sorozatonként `series_start`,
`series_memory`, `task` rekordok, `series_end`, végül `run_complete`.

A fejléc tartalmazza a futásazonosítót, módot, eredetjelölést, terhelésnevet,
SDK-t, CPU MHz-et és várt darabszámot. A batch_id a sorozatot, index a
feladatot, window_index a `series_start.window_ids` megfelelő elemét jelöli.
A fizikai panel `simulated:false` jelölése mellett a terhelés neve továbbra
is `synthetic_delay_25ms`; ettől nem válik saját modell mérésévé.

Az elemző teljes elszámolást, indexeket, ablaksorrendet, időrácsot, egymást
nem átfedő feldolgozást, státusz/idő összhangot és memóriaértékeket ellenőriz.
Hibánál nem ír sikeres jelentést, kilépési kódja 1. A `--require-benchmark`
a négy teljes, helyes sorrendű 100+3×1000 profilt is megköveteli.
Kapcsolat-/eszközhibás vagy resetelt felvételt nem javít automatikusan.

Minden sorozat külön statisztikát kap; a bemelegítés `phase=warmup`, ezért
nem olvad a mért sorozatokba. Időstatisztika csak `ok` és `late` feladatokra
készül. A medián szokásos medián, p95 = rendezett minta `ceil(0.95*n)`-edik
eleme, maximum megfigyelt maximum, nem bizonyított WCET. Az inferencia/s
a sikeresen befejezett feldolgozások száma / `end_us` másodpercben, a rácsvég
és az utolsó befejezés bevárásával, UART-szünet nélkül. A hibaarány:
100 × (late + missed + failed) / összes ütemezett feladat. Minden feladat
egyszer szerepel; hiányzó mérés nem nulla. A nyers hibaidők megmaradnak.

Memóriaadatok byte-ban, KiB = byte / 1024:

| Forrás/mező | Jelentés és átfedés |
| --- | --- |
| Build `size.json`: `used_dram` | Linker szerinti statikus DRAM; tartalmazza a statikus ablak-/eredménypuffereket |
| Build `used_iram` | RAM-ban tárolt kód és vektorok, külön a statikus adatoktól |
| `result_buffer_bytes`, `window_buffer_bytes` | Részhalmazok a statikus RAM-on belül; az utóbbi a skálázott bemenetet is tartalmazza |
| `model_workspace_bytes` | Ebben a próbában null: nincs modell-arena; #7 jelzi, statikus vagy heapbeli arena-e |
| `free_heap_bytes`, `largest_free_block_bytes` | MALLOC_CAP_8BIT heap pillanatképe; nem teljes/szabad fizikai RAM |
| `minimum_free_heap_bytes` | Előtte boot óta, utána a sorozat lokális minimuma (`minimum_scope`); a heaprégiók minimumai eltérő időben is keletkezhetnek |
| `stack_high_water_bytes` | A főfeladat indulása óta legkisebb szabad stack; a heapből allokált stackkel átfedhet |
| `.bin` tényleges fájlmérete | Alkalmazás firmware-képe fejlécekkel/paddinggel; nem az ELF debugmérete |
| `model_bytes` | Ebben a próbában null: nincs modell; saját modellnél a beágyazott modellbyte-ok külön mérete |

A sorozat utáni memória-pillanatkép az eredményformázás előtt készül; a
lokális minimumfigyelő is leáll az átvitel előtt. A memóriamutatók nem
összeadható, független RAM-fogyasztások. A futtatás nem allokál: a puffer
előre lefoglalt. A mintavétel előtte/utána történik, nem minden feladatnál.

## #7-átadás és fennmaradó integráció

1. A firmware saját projektjéhez add hozzá az ESP-IDF `measurement` modult.
   A #6 runtime-adaptere valósítsa meg a `Workload` interfészt; a mérőmag
   nem igényel változtatást a modell cseréjéhez.
2. A hívó a `prepare` szakaszban ellenőrizze a nyers ablakot, alkalmazza a
   közös skálázást és a modell kvantálását. Az `invoke` csak a runtime
   hívása; a `finish` a kimenet ellenőrzése és osztálydöntése. Külön
   rögzítendő a modellhash, kvantálás, osztálysorrend és numerikus INT8-kimenet.
3. A #4 szerinti load/execute/fetch illesztést a #7 adja hozzá. Megmarad a
   nyolcas ablak-, 1000-es eredmény- és 16-os fetch-korlát. Az execute előtt
   előtöltés és TX-drain, utána ack/fetch; a hívó sem végezhet UART-ot vagy
   naplózást a `Workload` műveleteiben.
4. A `failed/invalid_window` kommunikációs megfelelője `invalid_window`,
   döntés nélkül. A modell-/memóriahiba külön eszközhiba; a #7 a meglévő
   szerződés felelős integrációjában rögzíti a továbbítását. A próbafirmware
   nyers hibaidői nem kerülhetnek érvényes döntésként a szimulációs sémába.
5. A main kliens, GUI és CSV ma kizárólag szimulációt fogad. A paneles
   eredetkezelés és UART-adapter a #7 feladata; nem szabad a valódi
   eredményt `simulated:true` értékre átírni kompatibilitási kerülőútként.
6. A teljes tesztadat minőségi vizsgálata külön, adagokban történik.
   A benchmark ismételt munkakészlete nem helyettesíti azt. A saját MLP
   minősége és a PC/MCU portolási helyesség nincs ezzel a modullal igazolva.

Hivatalos források: [ESP Timer v5.5.1](https://github.com/espressif/esp-idf/blob/v5.5.1/components/esp_timer/include/esp_timer.h),
[heap API](https://github.com/espressif/esp-idf/blob/v5.5.1/components/heap/include/esp_heap_caps.h),
[ESP32 UART-idle javítás](https://github.com/espressif/esp-idf/blob/v5.5.1/components/esp_rom/patches/esp_rom_uart.c),
[Xtensa StackType_t](https://github.com/espressif/esp-idf/blob/v5.5.1/components/freertos/FreeRTOS-Kernel/portable/xtensa/include/freertos/portmacro.h).
