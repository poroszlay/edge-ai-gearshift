# #5 ellenőrzés és átadás — 2026-10-22

Az implementáció és mindkét ESP32 build elkészült. A hostos ellenőrzések
sikeresek. **A paneles elfogadás nyitott:** a hoston létező `/dev/ttyUSB0`
megnyitása EACCES hibát ad; flash, valódi idő-/heapmérés és UART-csend
hardveres igazolása nem történt. Az issue teljes hardveres elfogadása nem
állítható teljesítettnek.

Branch: `feat/issue-5-measurement`; munkapéldány:
`/tmp/edge-ai-gearshift-issue-5`; alap: `b4c5fb2727f023ec31283712fdf1b49de7b7ba25`.
Az aktuális #5, #4, #6 és #7 issue-kban nem volt komment. Követelményforrás:
AGENTS.md és hivatkozott agentdokumentumai, GLOSSARY.md, közös adat-,
kommunikációs, modell-/mérési szerződés és fejlesztési kontextus.

## Elvégzett ellenőrzések

| Ellenőrzés | Tényleges eredmény |
| --- | --- |
| Teljes regresszió, `QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v` | 65 teszt, 51,258 s, OK; 7 GUI-teszt kihagyva a hiányzó Qt-függőségek miatt |
| Új C++ publikus futtatóinterfész | 7 viselkedési próba egy hostos fordítás/futtatás teszten keresztül |
| Közös próbafirmware hostos benchmarkja | 16 sorozat, 400 bemelegítő + 12000 mért feladat, minden index elszámolt |
| Élő próbafirmware hoston | 3 ablak, külön sorozatok, új futásazonosító minden indításkor |
| Exportelemző CLI | Nyers idők, elszámolás, memóriaadatok, hibás/hiányos felvételek és szigorú benchmark-protokoll ellenőrizve |
| AddressSanitizer + UndefinedBehaviorSanitizer | Mind a 7 C++ próba PASS, diagnosztika nélkül; leak-ellenőrzés kikapcsolva |
| ESP-IDF v5.5.1 benchmark build | Sikeres, alkalmazáskép 233408 byte, figyelmeztetés nélkül |
| ESP-IDF v5.5.1 live build | Sikeres, alkalmazáskép 233328 byte, figyelmeztetés nélkül |
| Mindkét build statikus adatai | used_dram=69784 byte; used_iram=49451 byte; a részhalmazokat nem adjuk ezekhez újra hozzá |
| Hostoldali portmegnyitás és esptool chipazonosítás | PermissionError / errno 13; chipazonosítás nem sikerült |

A sandbox a socketet használó meglévő teszteket tiltja; a teljes regresszió
ezért hoston futott. A 7 GUI-skip változatlan felületet érint; a mérőmag,
próbaprogram és elemző GUI nélkül ellenőrzött. Napló: [tests.log](tests.log).

Az SDK a `/tmp/gearshift-issue5-sdk/esp-idf` alatt, a toolok
`/tmp/gearshift-issue5-sdk/tools` alatt találhatók. ESP-IDF commit:
`fcae32885b0296b32044cb99ecbdc50d98dddb83`. A rendszerből hiányzott pip,
ensurepip, CMake és Ninja: elkülönített `/tmp` Python-környezetbe kerültek,
rendszerkönyvtár-módosítás nélkül. Az IDF saját környezete `venv
--without-pip` és pip bootstrap után az eredeti `idf_tools.py
install-python-env` paranccsal települt, az IDF v5.5 constraints alapján.
A verziók/csomagok az [environment.log](environment.log) fájlban vannak.

Az első build a deprecated `esp_rom_uart_tx_wait_idle` függvény feloldásán
elakadt. Az SDK forrásának ellenőrzése után az ESP32-re javított
`esp_rom_output_tx_wait_idle` került a kódba; mindkét végleges build sikeres.
Az első kísérlet naplója is megmaradt, nem helyettesíti a végleges buildeket.

## TDD-bizonyíték

A TDD skill előírása szerinti három teszthatárt a felhasználó a tervezéskor
kifejezetten jóváhagyta: C++ publikus futtatóinterfész, exportelemző CLI,
próbafirmware soros kimenete. Fizikai soros kimenetet jogosultság hiányában
nem teszteltünk; a közös próbaprogram kimenete hostos virtuális órával futott.

Minden szelet tesztváltoztatással és ténylegesen hibázó futással indult,
majd az ahhoz szükséges implementációval lett zöld. Nem készült előre
teljes tesztcsomag. Az órát mint fizikai függőséget helyettesítjük, a
mérőmag belső együttműködőit nem mockoljuk.

| Ciklus | Új viselkedés / red oka |
| --- | --- |
| 01 | Külön inferencia- és feldolgozási intervallum; hiányzó mérőmodul |
| 02 | 25 ms / 10 ms: late, missed, missed, late; utolsó feladat bevárása |
| 03 | Elégtelen eredménypuffer külön hibaként, végrehajtás nélkül |
| 04 | Korlátos darabszám, ablakszám és a négy ismert profil |
| 05 | Modellhiba nem sikeres feladat, nincs utófeldolgozás |
| 06 | Lejárt időrések kihagyása, késői indulás eredeti határideje |
| 07 | Nyers túlterhelési export statisztikái; hiányzó elemző CLI |
| 08 | Részleges és duplikált export nem teljes futás |
| 09 | Ellentmondó időpontok, státuszok és ablakindexek elutasítása |
| 10 | Közös próbaprogram teljes 12400-as exportja; hiányzó próbafirmware |
| 11 | Teljes 100 + 3×1000 protokollt kikényszerítő CLI-opció |
| 12 | Külön megőrzött és ellenőrzött memória-pillanatképek |
| 13 | Élő próba, külön egyablakos adagok |
| 14 | Hibás futás-/sorozatmetaadatok elutasítása, bool nem darabszám |
| 15 | Időminta körüli preempció nem hoz létre lejárt kezdésű feladatot |
| 16 | Minden indítás külön futásazonosítót kap |

Az `NN-red.log` és `NN-green.log` párok a tényleges futások naplói.
02–16 között a parancs, kilépési kód és forrás-/teszthash is rögzített;
minden red nem nulla, minden green nulla, páronként a tesztforrások
azonosak. 01-ben a teljes unittest kimenet őrzi a hibát és a sikert, külön
JSON-fejléc nélkül. A red állapotok történeti bizonyítékok, a végleges
forrás újrafuttatásakor már zöldnek kell lenniük.

A 10-es ciklus köztes fordítási hibája és a 12-es ciklus javított teszt-
behúzási hibája külön naplóban maradt. A 12-red már a javított teszt
tényleges hiányzó kimeneti mezőjét mutatja; szintaktikai hiba nem számít
viselkedési red bizonyítéknak.

## Hostos eredmény és reprodukálás

A [reprodukálási és interfészleírás](../../measurement-module.md) parancsai
a végleges forrással lefutottak. Teljes hostexport:
`results/issue-5/host-benchmark.jsonl`; elemzett eredmény:
[host-benchmark-report.json](host-benchmark-report.json). Ez virtuális
25 ms-os terhelés, **nem hardveres inferenciateljesítmény**.

Mindhárom mért sorozatban ugyanazok a darabszámok:

| T=D [ms] | ok | late | missed | failed | Határidőre nem teljesült |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10 | 0 | 334 | 666 | 0 | 100% |
| 20 | 0 | 500 | 500 | 0 | 100% |
| 50 | 1000 | 0 | 0 | 0 | 0% |
| 100 | 1000 | 0 | 0 | 0 | 0% |

A 10 ms-os sorozat utolsó elindított feladata a rácsvég után fejeződik be;
ezért a jelentés nevezője 10,015 s, nem kerekítjük vissza 10 s-ra.
Az [élő jelentés](host-live-report.json) szintén `simulated:true`.
A hostos heap-/stackmutatók nullok; a C++ pufferek tényleges méretei nem
állíthatók az ESP32 teljes RAM-fogyasztásának.

Független kéziszámításos példa: a
[statistics-example.jsonl](statistics-example.jsonl) 1..20 ms időtartamaiból
medián 10,5 ms, nearest-rank p95 19 ms, maximum 20 ms, 2 s alatt 20 sikeres
feladatból 10/s adódik. Ezeket a CLI tényleges kimenetével ellenőriztük:

```bash
python3 -m gearshift.profiler docs/evidence/issue-5/statistics-example.jsonl
```

A nagy exportok és generált binárisok nincsenek Gitben. A `manifest.json`
megőrzi a források, a két build binárisainak/map/config/flashállományainak
és a teljes hostexportoknak az ellenőrzőösszegét és méretét. Új futás új
run_id-t kap, ezért az új export nem byte-azonos a korábbi felvétellel.
A `/tmp` munkapéldány, SDK és buildek törölhetők; azonos hash-ek csak a
megőrzött konkrét artefaktumokra vonatkoznak, a forrás és a recept Gitben van.

Az összegyűjtött bizonyíték ellenőrzése a repo gyökerében:

```bash
sha256sum -c docs/evidence/issue-5/SHA256SUMS
python3 - <<'PY'
import hashlib, json
from pathlib import Path
m = json.loads(Path('docs/evidence/issue-5/manifest.json').read_text())
for name, expected in m['source_sha256'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
for name, metadata in m['local_artifacts'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == metadata['sha256'], name
print('Source and preserved local artifact hashes OK')
PY
```

## Fennmaradó hiányok és #7-átadás

- Hoston a CP2102 stabil by-id útvonala és `/dev/ttyUSB0` látszik, de a
  felhasználó nem dialout-tag, a port nem nyitható. A tényleges
  [hardware-preflight.log](hardware-preflight.log) megőrzi a megnyitás és
  az esptool hibáját. Sandboxbeli hiányból nem következtettünk panelhiányra.
- Porthozzáférés után a dokumentált chip-/flashazonosítás, live és teljes
  benchmark flash/futtatás, nyers soros napló, fizikai UART-csend és
  stabilitásvizsgálat hátravan. A firmware-ből következő UART-kizárás
  nem helyettesíti a fizikai ellenőrzést. Ezt nem jelöljük teljesítettnek.
- Saját modell-arena és modellméret nem mérhető ebben a próbában: nincs
  saját modell. A null itt nem nulla byte-os működő modellt jelent.
- A #7 átadási interfésze és lépései a
  [mérőmodul leírásának végén](../../measurement-module.md) vannak: runtime-
  adapter, nyers előfeldolgozás/kvantálás, load/execute/fetch illesztés,
  hardveres eredetkezelés és hibatovábbítás. A meglévő kliens/GUI/CSV
  szimulációs szerződését ez az issue nem írta át.
- A #6-ra nem vártunk, annak fájljait és branchét nem módosítottuk.
  Modellminőség, teljes tesztadat-értékelés és portolási helyesség továbbra
  is #6/#7 feladat, nem ennek a mesterséges terhelésnek az eredménye.


## #17 review-kommentek javítása — 2026-10-22

Az UART-szünet hiányos elszámolása javítva. A `series_end.uart_wait_us`
az előző végrehajtás vége és az aktuális `run` előtti időpont közötti teljes
szünetet rögzíti, a következő fejléc átvitelével és TX-drainnel együtt.
A `series_start` korábbi részértéke kompatibilitási okból megmarad.
A profiler a teljes értéket használja; régi exportnál a hiányos mérési
határt `uart_wait_scope=before_header`, újnál `complete` jelöli.

A felhasználó jóváhagyta a próbafirmware JSONL-exportja és a profiler
jelentése tesztelési határt. Három egymást követő red → green szelet:

1. A benchmark exportteszt 16 teljes, egyenként 7000 µs-os szünetet várt,
   és először a hiányzó `series_end.uart_wait_us` miatt elbukott. A hostos
   TX-drainhez fordításkor beállított 7000 µs virtuális átviteli késleltetés
   után a firmware exportja és a profiler jelentése is helyes. Az eredeti
   400 bemelegítő + 12000 mért feladat és túlterhelési elszámolás megmarad.
2. A negatív, nem egész, bool, null vagy a fejléc előtti részértéknél kisebb
   teljes szünetet a CLI kezdetben elfogadta (öt bukás), a javítás elutasítja.
3. A régi és új export mérési határának jelölését ellenőrző teszt először
   hiányzó `uart_wait_scope` miatt elbukott; a javítás után sikeres.

Ellenőrzések a javított forráson:

- Teljes regresszió a sandboxon kívül, helyi socketekkel:
  **67 teszt, 54,356 s, OK, 7 GUI-skip**; [napló](review-fixes-tests.log).
- ESP-IDF v5.5.1 benchmark és live build: **mindkettő exit 0**.
  Helyi naplók: `/tmp/issue5-review-{benchmark,live}-build.log`.
- `git diff --check`: sikeres.

**A paneles review-pont továbbra is nyitott.** A sandboxon kívüli hoston
látható a CP2102 `/dev/ttyUSB0` és a dokumentált by-id útvonal, de a port
`os.open` próbája `PermissionError: errno=13` hibát adott. Nem történt
flash, paneles live/benchmark futás, idő-/heapmérés vagy fizikai UART-csend
igazolása. A folytatáshoz a felhasználó saját termináljában adhat hozzáférést:
`sudo setfacl -m u:richie:rw /dev/ttyUSB0`; utána a fent dokumentált
azonosítási és paneles ellenőrzési lépések szükségesek. A hostos késleltetés
kizárólag regressziós szimuláció, nem hardveres bizonyíték.
