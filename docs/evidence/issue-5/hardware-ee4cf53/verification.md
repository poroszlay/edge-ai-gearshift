# Paneles mérőmodul-ellenőrzés — 2026-10-22

Forrás: `ee4cf53`; ESP-IDF v5.5.1; mesterséges 25 ms CPU-terhelés,
**nem saját MLP-mérés**. A pontos forrás-, SDK- és artefaktumazonosítók a
[manifestben](manifest.json) vannak. Panelazonosítás: [identity.json](identity.json).

## Reprodukált hiba és TDD

A felhasználó engedélyezte a porthozzáférés javítását és a publikus
JSONL/profiler, illetve bizonyítékellenőrző parancsok tesztelési határát.
A host `sudo`-jelszót igényelt; a felhasználó a saját termináljában futtatta:
`sudo setfacl -m u:richie:rw /dev/ttyUSB0`. Ezután chip- és flashazonosítás,
majd tényleges feltöltés történt.

A `4cb661c` firmware live próbája sikeres volt, de a benchmark hosszú,
115200 baud eredményexportja `task_wdt` jelzést okozott, amely a JSON-sor
közepébe íródott. A 25 másodperces ismétlés ugyanezt reprodukálta:
IDLE1 éhezett, CPU1-en a `main` futott. A backtrace feloldása:
`uart_ll_get_txfifo_len → uart_tx_char → uart_write → printf → nullable_time`.
Tehát az alapértelmezett polling UART-írás hosszú ideig nem engedte futni
az idle feladatot; nem a mért inferencia közbeni hibát fedtük el.

Az `ee4cf53` javítás ESP32-n minden eredménysor után `vTaskDelay(1)`-et
hív, kizárólag az exportban, a `run()` mérési szakaszán kívül. A watchdog
bekapcsolva marad. Az idő beleszámít a következő teljes adagközi szünetbe.
A 25 másodperces paneles regresszió előbb [piros](watchdog-red-summary.log),
majd [zöld](watchdog-green.log). Hoston a mérőmag mindhárom tesztje sikeres.

A hardveres regresszió a már benchmark firmware-rel feltöltött panelen fut:

```bash
GEARSHIFT_TEST_ESP32_PORT=/dev/ttyUSB0 python -m unittest discover \
  -s tests -p test_measurement_hardware.py -v
```

A portváltozó nélkül a szokásos tesztfutás nem nyúl a panelhez. A 25 s-os
próba a korábbi hiba helyéig jut, de nem helyettesíti a teljes kampányt.

## Teljes futás és UART-csend ellenőrzése

Mindkét mód tényleges paneles futása sikeres. A benchmark 795,952 s alatt
lezárult: 400 bemelegítő + 12000 mért feladat, 16 sorozat, hiányzó feladat
és sérült JSON-sor nélkül. A live próba 3/3 ablakot `ok` státusszal lezárt.
A profiler mindkét exportot elfogadta (`simulated:false`); a benchmarkon
`--require-benchmark` ellenőrizte a teljes négyprofilos protokollt.

| T=D [ms] | ok / sorozat | late | missed | failed |
| --- | ---: | ---: | ---: | ---: |
| 10 | 0 | 334 | 666 | 0 |
| 20 | 0 | 500 | 500 | 0 |
| 50 | 1000 | 0 | 0 | 0 |
| 100 | 1000 | 0 | 0 | 0 |

Mindhárom mért ismétlésben azonos a státuszelszámolás. A mesterséges
invoke-idő mediánja 25,000–25,001 ms, megfigyelt maximuma 25,002 ms.
A minimum szabad heap 246840 byte, a legkisebb szabad stack 2092 byte;
a statikus DRAM 69784 byte, IRAM 49451 byte. A benchmark firmware 233488,
a live firmware 233408 byte. Ezek egymással átfedő, külön értelmezendő
mutatók, nem összeadandó fogyasztások.

A hoston megfigyelt fogadási csend és a firmware végrehajtási ideje közti
legnagyobb eltérés a 16 benchmark-sorozatban 0,832 ms alatt, a három live
sorozatban 0,409 ms alatt volt. Az összes nyers naplóban egyetlen várt
boot van, watchdog/panic/brownout/heap-hiba nélkül. A Boya flash általános
driverének bootfigyelmeztetése megmaradt; a feltöltés visszaellenőrzése és
a futások sikeresek.

Eredmények: [benchmark-jelentés](benchmark-report.json),
[live-jelentés](live-report.json), [benchmark UART-csend](benchmark.silence.json),
[live UART-csend](live.silence.json), [nyers live napló](live-serial.log).
A teljes regresszió [naplója](tests.log): **70 teszt, 52,009 s, OK, 8 skip**.
Hét GUI-skip hiányzó függőségek miatt, egy hardveres skip portváltozó nélkül;
a külön indított paneles watchdog-regresszió sikeres. A nyers adatok helye: `results/issue-5/hardware-ee4cf53/`.
A buildnaplók, teljes sdkconfigok és linker-méretjelentések ebben a Gitben
verziózott bizonyítékkönyvtárban vannak. A feltöltés sikerét és az átvitt
képek visszaellenőrzését a flashnaplók rögzítik.

A [capture_uart.py](../capture_uart.py) megnyitja a CP2102 portot, resetel,
majd kizárólag fogad, a `run_complete` eseményig vagy timeoutig. Megőrzi
az eredeti bájtfolyamot és minden fogadott darab host-monoton időbélyegét.
A [analyze_uart.py](../analyze_uart.py) a fejléc utolsó bájtjának és az első
sorozat utáni memóriabájt fogadásának különbségét hasonlítja a sorozat
mért idejéhez (50 ms host/USB-toleranciával). A két pont között a nyers
bájtfolyamban nincs további sor vagy fogadott adat. A host a végrehajtás
alatt nem küld adatot; a firmware a TX-et indulás előtt kiüríti.

Ez tényleges, fizikai CP2102 kapcsolaton megfigyelt UART-fogadási csend.
A host időbélyege nem logikai analizátoros elektromos élidőmérés, és nem
igazol jövőbeli legrosszabb futásidőt. A nyers naplókat külön ellenőrizzük
watchdog, panic, brownout, heap-hiba és a várt boot utáni újraindulás ellen.

Az adott mód firmware-ének dokumentált feltöltése után, más portolvasó nélkül:

```bash
python docs/evidence/issue-5/capture_uart.py /dev/ttyUSB0 1500 \
  results/issue-5/hardware-ee4cf53/benchmark-serial.log
python3 docs/evidence/issue-5/analyze_uart.py \
  results/issue-5/hardware-ee4cf53/benchmark-serial.log \
  results/issue-5/hardware-ee4cf53/benchmark
python3 -m gearshift.profiler \
  results/issue-5/hardware-ee4cf53/benchmark.jsonl --require-benchmark
```

Élő módhoz a live buildet kell feltölteni; `15` másodperces timeout és
`live-serial.log`/`live` kimenet használható, `--require-benchmark` nélkül.
A capture eszköz Python-környezete pyserialt igényel; a JSONL-elemzéshez
csak a projekt alapfüggőségei kellenek.


Az UART-csend elemzőjének utólag javított sorrendellenőrzése a megőrzött
nyers felvételeket is elfogadja. Az újraellenőrzés forrásverziója és
azonosítói: [uart-review-b2108ed/manifest.json](../uart-review-b2108ed/manifest.json).
A korábban rögzített csendjelentések byteazonosan újra előálltak.
