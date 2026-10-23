# Saját INT8 MLP az ESP32-n (#7)

A `firmware/esp32/inference` a befagyasztott **mlp-v2** modellt kapcsolja a
közös JSON Lines v1 protokollhoz és a #5 mérőmodulhoz. Azonosítók:

- INT8 SHA-256: `6d5ac8613d301ca06de2ca9a4cfbadf3cd40c7c75a7af419505eaa9fcbb25f79`.
- Adat: `ef6f8048efec22e32cc44fd4c58b08052359ab6880ee52c2257e3da59f27ba4a`.
- 100 → 64 → 32 → 3; osztálysorrend: downshift, hold, upshift.
- ESP-IDF 5.5.1, esp-tflite-micro 1.3.5, esp-nn 1.1.1; CPU 240 MHz,
  1000 Hz tick, főfeladat CPU1-en, DIO/40 MHz/4 MiB flash, UART0 **921600 baud**.
- Statikus 32 KiB tensorarena; nincs PSRAM-, rádió- vagy WiFi-indítás.

A [paneles ellenőrzés](evidence/issue-7/verification.md) külön rögzíti a
portolási helyességet, minőséget és teljesítményt. A befagyasztott modell
0,7029 validációs makro-F1-e nem teljesíti a 0,95-ös célt; javítása #19.
A teszteredmény nem szolgál új modell kiválasztására.

## Fordítás és panel

A meglévő [SDK-környezetet](esp32-bringup.md) használd. Azonosítatlan
panelre ne tölts. A chip-, flashazonosító és a feltöltés naplója a bizonyíték része.

```bash
export IDF_TOOLS_PATH=/sajat/sdk/tools
. /sajat/sdk/esp-idf/export.sh
python -m esptool --chip auto --port /dev/ttyUSB0 chip_id
python -m esptool --chip auto --port /dev/ttyUSB0 flash_id
bash firmware/esp32/inference/build.sh
idf.py -C firmware/esp32/inference -p /dev/ttyUSB0 flash
```

Az `embed-model.py` a csomag összes befagyasztott checksumát ellenőrzi,
a modellből számolja a beágyazott modellazonosítót, és ellenőrzi az
interfész-metaadatokat. A CMake a modellcsomag megváltozásakor újrakonfigurál.
Más csomag explicit `-DGEARSHIFT_MODEL_DIR=/abszolut/csomag` opcióval adható
meg; a befagyasztott v2 felülírása nem része a folyamatnak.
A runtime AllocateTensors után ellenőrzi az INT8 alakokat és a két I/O
tenzor skáláját/nullpontját is. Az inferenciahibák strukturált rekordok;
a TFLM DebugLog linkeléskor csendes adapterre kerül, így hibaágon sincs UART
az inferencia alatt. A FullyConnected a rögzített upstream referencia-kernel,
`TFLITE_SINGLE_ROUNDING=1` beállítással a main és TFLM komponensben. Ez egyezik
a befagyasztott PC BUILTIN_REF aritmetikájával; a Softmax az ESP-NN változat.
A kerekítési eltérés diagnózisa és regressziója az ellenőrzési napló része.

Meglévő `sdkconfig` elsőbbséget élvez a defaults előtt. A 921600 beállításhoz
`ESP_CONSOLE_UART_CUSTOM=y`, UART0, TX=1, RX=3 szükséges; az alapértelmezett
UART-választás visszaállítaná a baudot 115200-ra. Az effektív sdkconfigot
és a build `config/sdkconfig.h` fájlját ellenőrizd és őrizd meg.

## Futtatás

Egy boot egy run_id-t fogad. Új futáshoz reset szükséges. A segédscript
resetel, megvárja az indulást, és új, még nem létező eredménykönyvtárba ír.
A portot egyszerre egy folyamat használhatja; a POSIX-adapter kizárólagosan
nyitja. Az ACL szükség esetén a saját terminálból adható:
`sudo setfacl -m u:richie:rw /dev/ttyUSB0`.

```bash
# SDK export.sh betöltése után, a repó gyökeréből:
bash tools/run-esp32.sh live results/issue-7/live-repeat \
  models/mlp-v2/reference-windows.jsonl

# Legfeljebb 8, a 16384 byte-os load keretbe férő, rögzített nyers ablak:
bash tools/run-esp32.sh benchmark results/issue-7/benchmark-repeat \
  docs/evidence/issue-7/benchmark-windows.jsonl
python3 -m gearshift.run_report results/issue-7/benchmark-repeat/events.jsonl \
  --require-benchmark > results/issue-7/benchmark-repeat/report.json
```

Élő módban ablakonkénti eredményátvitel történik. Benchmarkban a négy
profilhoz külön 100 bemelegítő + 3×1000 ütemezett feladat tartozik, az
előtöltött munkakészlet ismétlésével. Az execute teljes mért szakaszában nincs
soros írás/olvasás, JSON-formázás vagy eredményátvitel; a TX-puffer előtte
kiürül. Az ACK csak a futás befejezése után készül. A `fetch` legfeljebb 8
rekordot ad (a közös 16-os felső határon belül), így a 100 bemeneti kód és
három kimeneti kód az azonosítókkal együtt is elfér a keretben.
A foglalt végrehajtó miatt kimaradt feladat nem pótlódik. A késői befejezés
az eredeti indítási időponthoz képest számított határidőre vonatkozik,
a feldolgozás időtartama ilyenkor önmagában lehet T-nél rövidebb.

A kliens közvetlenül is futtatható reset és boot után:

```bash
python3 -m gearshift.client --serial /dev/ttyUSB0 --baud 921600 \
  --model-id 6d5ac8613d301ca06de2ca9a4cfbadf3cd40c7c75a7af419505eaa9fcbb25f79 \
  --timeout 120 --input models/mlp-v2/reference-windows.jsonl \
  --capture-prefix results/issue-7/manual-wire --output results/issue-7/manual.jsonl
```

A 120 s-os kérés-timeout a 100 s-os sorozatot is lefedi. Megszakítás,
timeout, hibás válasz vagy eszközreset után nincs automatikus újraküldés.
A nyers `.rx`/`.tx` fájlok minden átvitt bájtot megőriznek, a
`.chunks.jsonl` az irányt, fájloffsetet és monoton hostidőt. Ez a hoston
megfigyelt kommunikáció bizonyítéka; nem logikai analizátoros buszmérés.

## Két külön numerikus ellenőrzés

A nyers ablak útja: érvényesség → binary64 skálázás → float32 szűkítés →
float32 osztás → nullától távolodó félkerekítés → nullpont → INT8-telítés.
A tau csak a modellbemenetben telítődik, az eredeti ablak változatlan.
Az argmax döntetlenben a kisebb indexet választja.

A külön előre kvantált ablak csak `window_id`, `trip_id`, `input_int8`
mezőket hordoz; nyers `samples`/`timestamps_ms` mezővel együtt érvénytelen.
Ezzel azonos INT8-kódokat kap a PC és az MCU. A nyers út külön vizsgálata
kötelező, mert ezt az előre kvantált út nem ellenőrzi.

```bash
python -m gearshift.porting --reference models/mlp-v2/pc-reference.jsonl \
  --events results/issue-7/live-repeat/events.jsonl \
  --output results/issue-7/live-repeat/porting.json
```

A bemeneti kódoknak pontosan egyezniük kell; a kimeneti eltérés legfeljebb
1, az osztálydöntés kötelezően azonos. Minden nem nulla eltérés run/window/
model azonosítóval bekerül a jelentésbe, a még tűrésen belüli eltérés is.
A korlát átlépése hibás kilépést ad. Hiányos vagy ismételt ablak, hibás
kimenet, eltérő modell, szimulált eredet vagy befejezetlen futás esetén
nem készül sikeres portolási jelentés.

## Teljes lezárt teszt és külön minőségi jelentés

Az alábbi előkészítés csak a `final-evaluation/test` jogosultságú adatutat
használja. Ellenőrzi a manifestet, test-lockot és forrásfájl-hasheket, majd
minden ablakra egyszer kiszámítja a PC INT8-referenciát. Nem tanít és nem
választ modellt. Új eredménykönyvtár szükséges, felülírás nincs.

```bash
# requirements-model.txt szerinti környezetben:
. tools/model-env.sh
python -m gearshift.campaign --dataset data/generated/dataset-v2 \
  --export models/mlp-v2 --output results/issue-7/final-test-repeat
# SDK export.sh betöltése után:
bash tools/run-esp32.sh quality results/issue-7/quality-repeat \
  results/issue-7/final-test-repeat/windows.jsonl
# Modellkörnyezetben:
python -m gearshift.porting \
  --reference results/issue-7/final-test-repeat/reference.jsonl \
  --events results/issue-7/quality-repeat/events.jsonl \
  --output results/issue-7/quality-repeat/porting-quality.json
```

A `purpose=quality` a benchmark üzemmódban az előtöltött 1..8 ablakot
pontosan egyszer, egymás után járja végig, határidő és kimaradás nélkül;
`period_ms=0`, a nem ütemezett `scheduled_ms` mező minden rekordban 0.
Ez nem teljesítménymérés vagy ismételt terhelési profil. Az eredményeken `phase=quality` szerepel.
A teljes teszt makro-F1-e és tévesztési mátrixa külön a minőségi részbe kerül;
a portolási eltérések saját listát kapnak. A négyprofilos benchmark
ablakismétlései nem helyettesítik a teljes teszt minőségi vizsgálatát.
Nyers referenciaablakokkal az előfeldolgozás külön ellenőrzött.

## Idő és memória

A firmware ugyanazt a #5 futtatót és mérési pontokat használja.
A `processing_ms` = `finished_us-started_us`, az inferencia a két inference
időpont különbsége; a nyers időpontok exportálhatók. A `uart_wait_us` az
előző execute vége és a következő execute indulása közötti teljes szünet,
beleértve az exportot, hostvárakozást, előtöltést és TX-drain-t. Nem tiszta
UART-driveridő és nem része az MCU-feldolgozásnak.

Memória-pillanatképek: a sorozat előtt boot óta mért minimum, utána a
sorozat lokális minimuma; heap, legnagyobb szabad blokk és stack high-water.
A mintavétel a JSON-formázás előtt, az execute-on kívül történik.
A statikus tensorarena, a `Device` teljes statikus állapota, annak
ablak-/eredménypuffer-részhalmazai külön méretet kapnak. Ezek nem
összeadható független RAM-fogyasztások. A linker DRAM/IRAM, firmware-bináris
méret, modellméret és a teljes effektív sdkconfig a build bizonyíték része.

Modellhiba, memóriahiba és érvénytelen ablak külön státusz, döntés és
modellkimenet nélkül. Kommunikációs hiba részleges futás; nincs érvényes
hold döntéssé alakítás. A `run_report` a numerikus rekordokat ellenőrzi,
majd a meglévő #5 profilerrel ellenőrizteti a teljes ütemezési és
memóriaelszámolást. Bemelegítést és mért sorozatokat külön kezel.

A nyers UART-felvétel önálló ellenőrzése:

```bash
python3 -m gearshift.uart_evidence results/issue-7/benchmark-repeat/wire \
  --output results/issue-7/benchmark-repeat/uart-audit.json
```

Az ellenőrző minden bájtot és kérés/válasz-párt elszámol. Nem dobja el a
JSON-on kívüli watchdog/panic/reset szöveget. Az execute után elsőként
megfigyelt válaszbájt nem érkezhet a mért végrehajtás vége előtt. A
hostidőbélyegek külön, explicit 2 ms-os műszerezési engedményt kapnak;
ez nem módosítja az INT8 numerikus tűrést vagy a feladatok határidejét.

A UART-szünetre a kliens és a jelentéskészítő hostidő szerinti felső
korlátot is alkalmaz (szomszédos execute-ACK-k köze + 1 s). Ez egy
konzervatív konzisztenciakapu, nem a mért érték módosítása vagy a
feladathatáridő lazítása. Hibás értékkel a futás részleges marad.
A diagnosztikai és végső benchmarkfutás külön run_id-t kap.
