# #7 ellenőrzési napló — 2026-10-23

Branch: `issue-7-esp32-int8-integration`.

## Forrás és cél

A #6 által befagyasztott mlp-v2 változatlan:
`6d5ac8613d301ca06de2ca9a4cfbadf3cd40c7c75a7af419505eaa9fcbb25f79`.
Adatverzió: `ef6f8048efec22e32cc44fd4c58b08052359ab6880ee52c2257e3da59f27ba4a`.
Nincs új tanítás, kalibráció, tesztalapú modellválasztás vagy tűrésmódosítás.
A reprodukálás: [ESP32 INT8 MLP](../../esp32-inference.md).

Panel: ESP32-D0WD-V3 rev 3.1, 40 MHz kristály, 4 MiB flash,
MAC `3c:8a:1f:77:57:dc`, CP2102 UART, `/dev/ttyUSB0`.
Azonosítás: [chip](chip-id.log), [flash](flash-id.log).
A hoston kezdetben hiányzott az ACL; a felhasználó megadása után a port
megnyitható volt. A sandbox nem látta a panelt, a futás a hoston történt.

Rögzített környezet: IDF 5.5.1, esp-tflite-micro 1.3.5, esp-nn 1.1.1,
240 MHz, CPU1 főfeladat, 1000 Hz tick, UART0/TX1/RX3 921600 baud.
A watchdogok bekapcsolva maradtak. Az SDK helyreállított helye
`/tmp/gearshift-sdk/`; új környezetben a [bringup leírás](../../esp32-bringup.md)
szerint reprodukálandó. A pip a hiányzó rendszer-ensurepip miatt elkülönített
venvben lett helyreállítva; CMake 3.31.6 és Ninja ugyanoda került.

## TDD

A [tesztelési határokat](tdd.md) a felhasználó jóváhagyta. A számozott
`*-red.log` / `*-green.log` fájlok megőrzik a lépésenkénti visszacsatolást:

1. Paneles INT8-eredményséma és szigorúan megmaradó szimulátorséma.
2. Kliens → CSV: eredet, model/numeric/timing/memory mezők veszteségmentesen.
3. POSIX UART valódi pszeudoterminálon: keretek és abszolút timeout.
4. Natív C++ nyers előfeldolgozás a 11 befagyasztott PC-referenciával és
   a félérték szomszédjait is megkülönböztető kerekítéssel.
5. Firmware load/execute/fetch: függő eredmények védelme, lapozás,
   hibás ablak, túlterhelés minden ütemezett feladatra.
6. Teljes minőségellenőrzés korlátos adagokkal, minden ablak pontosan egyszer.
7. Külön bemeneti és kimeneti portolási hiba, teljes lefedés, minőségi mátrix.
8. Valódi paneles CLI; GUI eredet-/mértadat-kezelése, hibás beállítás lezárása.
9. Nyers UART-bájtrögzítés és a végrehajtás előtti válasz elutasítása.
10. A határidő az eredeti rácshoz tartozik; hiányos memória nem érvényes mérés.
11. Befagyasztás nélkül nincs hozzáférés a lezárt teszthez.
12. A minőségi mód nem időzített benchmark: nincs határidő miatti kihagyás.

A natív firmware tesztjének 25 ms-os `HostRuntime` szereplője külső runtime
próbahelyettesítő, `simulated:true`; nem saját MLP és nem hardverbizonyíték.
A hosttesztek cJSON-másolata pontosan az IDF 5.5.1 által használt 1.7.18
commit; licence és eredete a `tests/vendor/cjson/` alatt található.

## Portolási eltérés diagnózisa

A 11 nyers átadási ablak kezdetben bájtra egyezett:
[eredeti paneles napló](initial-live-115200.jsonl). A gyors UART-ra váltás
először timeoutot okozott: az alapértelmezett IDF UART-választás felülírta a
baudot 115200-ra. A CUSTOM választás és az effektív sdkconfig ellenőrzése
után a 921600-as élő adatút sikeres lett: [nyersablakos napló](initial-live.jsonl).

A kezdeti teljes minőségi kampányt **23352 ablak után részlegesként
leállítottuk**. Egy ablaknál a kimeneti eltérés 5 volt, ezért a futás nem
igazol portolási helyességet. A részleges napló helyben
`results/issue-7/test-campaign/`; nincs run_complete. A teljes eltérés és
visszakeresési azonosítók: [numeric-difference.json](numeric-difference.json).

Minimális reprodukció: `acceleration-0004-v1:375`, azonos 100 INT8 kód,
PC `[-120,120,-128]`, MCU `[-125,125,-128]`. Újraindítás után egyetlen
ablakkal is reprodukálható: [előtte](numeric-before.json).
A [bemenet](numeric-regression-windows.jsonl) és
[PC-kimenet](numeric-regression-reference.jsonl) kizárólag numerikus
regresszió; ez teszthalmazból származó diagnosztika, nem tanítási/validációs adat.

Vizsgált hipotézisek, egyenként:

- Csak FC referencia-kernel: az 5 kódos eltérés megmaradt.
  [Eredmény](numeric-reference-fc.json).
- Csak Softmax referencia-kernel: az eltérés megmaradt.
  [Eredmény](numeric-reference-softmax.json).
- Közös requantálási kerekítés: a PC egyszeres kerekítést használ,
  a korábbi MCU-út kettőset. A [független számítás](rounding-probe.py) és
  [naplója](rounding-probe.log) a PC 7/8/9 tenzorait vizsgálja. Kettős
  kerekítéssel 1/3/1 eltérő elem; egyszeressel 0/0/0. Az utolsó FC-kimenet
  `[92,95,-14]` helyett `[92,96,-14]` volt; ezt a Softmax erősítette fel.

Javítás: a rögzített upstream referencia-FC explicit regisztrációja és
`TFLITE_SINGLE_ROUNDING=1` a main és TFLM komponensben. A Softmax az eredeti
ESP-NN változat. A modellbyte-ok és kvantálási metaadatok változatlanok.
A [paneles numerikus regresszió](numeric-single-rounding.json) eltérése **0**.
Az egyszeres kerekítéssel végzett 12 ablakos teljes hardveres regresszió
(nyers átadás + hibát kiváltó INT8 bemenet) sikeres:
[hardveres tesztnapló](hardware-regression-green.log).

## Lezárt teszt PC-minősége

A teljes **71430 ablak** egyszeri PC INT8-értékelése:
[pc-quality.json](pc-quality.json). Makro-F1: **0,760699131233148**.
A tévesztési mátrix sorai a valódi, oszlopai a modell osztályai,
sorrendjük downshift/hold/upshift:

```text
[[  294,     2,   0],
 [  237, 70416, 180],
 [    0,   107, 194]]
```

A korábbi validációs eredmény 0,7028518838863791; a 0,95 cél továbbra sem
ért el. A minőségjavítás #19, a teszteredmény nem lett visszacsatolva.
A teljes MCU-értékelés **71430/71430 ablakkal sikeresen lezárult**.
A 100 elemű bemenetek és a 3 elemű kimenetek minden kódja egyezik;
osztálydöntésbeli eltérés nincs, maximális kimeneti eltérés **0**
(a megengedett felső határ változatlanul 1). A MCU minőségi mátrixa és
makro-F1-e pontosan a fenti PC-érték.
[Teljes portolási és minőségi jelentés](porting-quality.json).

A minőségi mód 8929 előtöltött adagot dolgozott fel, mindegyik ablakot
pontosan egyszer, határidő miatti kihagyás nélkül. Az összes 26788
kérés/válasz-pár és 101087345 UART-bájt elszámolt:
[UART-ellenőrzés](quality-uart-audit-summary.json). A legkisebb megfigyelt
csendes intervallum a mért végrehajtási időt 6606 µs-mal meghaladta; az
ellenőrző explicit 2000 µs hostidőbélyeg-engedményt használ. Ez hoston
megfigyelt csend, nem logikai analizátoros buszmérés.

## Végső forrás, build és élő adatút

Firmware- és numerikus kampánykliens: `2d0fefed989e81cab008047c11cf7dc2ea07d95d`.
A végső, számlálót ellenőrző benchmarkkliens és GUI: `aeef05f211183d70c912a6d86463b39b7483d2e0`.
A végső bináris project_version értéke `2d0fefe`, dirty jelölés nélkül.
A [buildnapló](final-runtime-build.log) és [feltöltési napló](final-runtime-flash.log)
ezután új élő, minőségi és benchmark futásokat kapott. A generált modellheader
13696 byte-ja külön újra SHA-256-ellenőrzött. Az
[aritmetikai fordítási bizonyíték](arithmetic-compile-proof.json) a közös
kvantálási rutinra és a referencia-FC-re is igazolja a SINGLE_ROUNDING=1-et.

| Méret | Byte |
| --- | ---: |
| Alkalmazás `.bin` | 306512 |
| Beágyazott modell | 13696 |
| Linker statikus DRAM | 131016 |
| Linker IRAM | 53279 |
| Statikus tensorarena | 32768 |
| Teljes statikus Device állapot | 69792 |
| Eredménypufferek a Device-on belül | 60000 |
| Ablakpuffer a Device-on belül | 9600 |

A részhalmazok nem összeadandók. A 32 KiB az allokált arena, nem az
elméletileg legkisebb szükséges arena. A [méretjelentés](size.json),
[effektív sdkconfig](sdkconfig) és a környezetek csomagzárai
([modell/GUI](model-ui-requirements-lock.txt), [SDK](sdk-requirements-lock.txt))
megmaradtak.

Az új runtime 11 nyers ablakos, tényleges paneles élő futása:
[nyers kliensnapló](final-live.jsonl), [portolás](live-porting.json),
[idő/memória](live-measurement.json), [UART](live-uart-audit.json).
Bemeneti/kimeneti eltérés 0. Ez a nyers út külön bizonyítéka, nem a teljes
71430-as készlet minőségi vagy időeloszlásának helyettesítése.

A tényleges élő napló visszajátszása a felületen:
[GUI-kép](gui-hardware-replay.png). A CSV oda-vissza olvasása megőrzi az
összes eseményt és a `simulated:false` eredetet. A következő eszköz
kiválasztása sem címkézheti át a meglévő adatokat; külön red→green
regresszió: `21-origin-*`. A modell-/memóriahibákat a natív firmware
interfészen is ellenőriztük, döntés és kimenet nélkül: `22-runtime-errors-*`.

Végső teljes regresszió: **102 teszt, OK, 2 opcionális panelteszt kihagyva**
([napló](final-guard-tests.log)). A saját modell 12 ablakos paneltesztje külön
**1/1 sikeres**, lásd fent.

## UART-szünetmetaadat elutasítása és védelmi regresszió

Az első teljes benchmark `d52856bc585a4603b6bc40c5eceefa78` futásában minden
feladat elszámolt és határidőn belüli volt, de a `p100-s2` válasz
`uart_wait_us=683924967` értéke összeegyeztethetetlen a hoston mért
ACK-közzel. A nyers UART-bájtokban is ez a szám szerepel; nem exporthiba.
Az érték eszköz-/átviteli eredete nem bizonyított, ezért nem javítottuk
vagy helyettesítettük becsléssel. A felvétel helye
`results/issue-7/uart-counter-anomaly/`; ez nem elfogadott végső időmetaadat.

A determinisztikus szoftverhiba a hiányzó konzisztenciavizsgálat volt:
a kliens/elemző pozitív számként elfogadta a lehetetlen várakozást.
A `23-uart-counter-*` red→green kör ezt a nyilvános kliens- és jelentési
interfészen reprodukálja. Az új ellenőrzés az egymást követő execute-ACK-k
hostidőközét felső korlátként használja, explicit 1 s konzervatív
host/eszköz-időzítési tartalékkal. Ez nem módosít mérési értéket,
INT8-tűrést vagy feladathatáridőt; túllépése hibás, részleges futást ad.
A régi nyers felvétel elutasítása: [napló](uart-counter-rejection.log),
[eredeti válasz és időköz](uart-counter-anomaly.json).
A teljes minőségi felvétel várakozásértékei ezt a korlátot utólag is teljesítik.

## Végső négyprofilos benchmark

Az új kliensellenőrzéssel végzett benchmark **sikeresen lezárult**.
Run_id: `8183cf68d8cc4307a1d883b0f4adf51b`; firmware: `2d0fefe`,
kliens/elemző: `aeef05f`. **16 sorozat, 12400 ütemezett feladat:
400 bemelegítő + 12000 mért**, hiány nélkül. Minden feladat `ok`;
late=0, missed=0, failed=0. Minden UART-szünet átment az új
hostidő-konzisztenciavizsgálaton. Nincs értékjavítás vagy kérés-újraküldés.
[Teljes jelentés](benchmark-report.json), [összesítés](benchmark-summary.json),
[UART-ellenőrzés](benchmark-uart-audit.json).

A profilok három mért sorozatának összes 3000 rekordjából számolt
medián/p95/megfigyelt maximum, ms-ban; bemelegítés nélkül.
A maximum nem bizonyított WCET.

| T=D [ms] | Ütemezett | ok | late | missed | failed | Inferencia [ms] | MCU-feldolgozás [ms] |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 10 | 3000 | 3000 | 0 | 0 | 0 | 0.833/0.834/2.027 | 1.648/1.650/2.865 |
| 20 | 3000 | 3000 | 0 | 0 | 0 | 0.833/0.834/2.028 | 1.650/1.650/2.869 |
| 50 | 3000 | 3000 | 0 | 0 | 0 | 0.833/0.833/2.029 | 1.649/1.650/2.870 |
| 100 | 3000 | 3000 | 0 | 0 | 0 | 0.833/0.834/2.025 | 1.649/1.650/2.864 |

A négy rögzített nyers ablak sorrendjét a
[benchmark-windows.jsonl](benchmark-windows.jsonl) őrzi. Ez ismételt
munkakészlet, nem a teljes tesztadat időeloszlása. A mért feladatok az
eredeti rácson, UART nélkül futottak; határidejük a tervezett indulástól
számítódott. A teljes MCU-sorozatidő 558000007 µs.
Az inferencia/s értéke a sorozatok MCU-idejére, UART-szünet nélkül értendő.

Minden sorozat előtt/után memória-pillanatkép készült. Legkisebb szabad
heap a sorozatokban 136280 B, boot óta
81172 B; legkisebb szabad main-stack
14140 B. Eltérő hatókörű, nem összeadható mutatók.

A sorozatokat megelőző eszközoldali szünetek külön, µs-ban szerepelnek;
tartalmazzák az átvitelt és a hostvárakozást is. Az utolsó eredményátvitel
a nyers host-/UART-naplóban marad meg, nem MCU-feldolgozási idő.
A teljes hostfutás 710.924 s volt.

Az UART-ellenőrző mind a 1585 kérés/válasz-párt és az összes
bájtot elszámolta; mind a 16 végrehajtásnál igazolt a hoston megfigyelt
csend. Reset/watchdog/panic szöveget nem szűrtünk ki a bájtfolyamból.
A teljes benchmark-CSV eseményről eseményre azonos eredménnyel olvasható vissza.

## Közvetlen GUI–panel végellenőrzés

A végső GUI nemcsak visszajátszással, hanem valódi UART-kapcsolattal,
a Session háttérszálán keresztül is ellenőrzött. Mindkét mód külön
panelresetet és run_id-t kapott.

- Élő: 11 nyers átadási ablak, 11 ok eredmény, valódi inferencia/MCU-idő és heap.
- Benchmark: a 10 ms-os profil 100 bemelegítő + 3×1000 mért feladata, mind ok;
  a grafikon a sorozatok utáni fetch alatt frissült. A teljes négyprofilos
  kanonikus mérés ettől külön, fent szerepel.
- Mindkét mód minden eseménye `simulated:false`, a kiválasztott mode megmaradt.
- A GUI saját exportháttérszálán készült két teljes CSV visszaolvasása
  eseményről eseményre azonos volt a Session-naplóval.

[Automatizált fizikai ellenőrzés naplója](gui-hardware-check.log),
[ellenőrző harness](gui-hardware-check.py),
[élő képernyő](gui-hardware-live.png),
[benchmark képernyő](gui-hardware-benchmark.png).
A harness az adott `/tmp/gearshift-sdk` környezet elérési útját rögzíti,
kimeneti könyvtárat nem ír felül. Ezek tényleges paneles futások;
a korábbi külön replay-kép ettől továbbra is elkülönül.

## Artefaktumok és ellenőrzőösszegek

A nagy nyers felvételek, referencia- és ablakfájlok, CSV-k, ELF és binárisok
a helyi `results/issue-7/` könyvtárban maradtak, nincsenek automatikusan
Gitbe téve. Azonosításuk: [manifest.json](manifest.json), benne a forráscommit,
forrásfájl-hashek, panel, runtime, futásazonosítók és minden végső helyi
artefaktum SHA-256 értéke. A helyi fő könyvtárak:

- `final-build/`: a ténylegesen feltöltött binárisok, ELF, effektív konfiguráció.
- `final-live/`: 11 nyers átadási ablak, eseménynapló, CSV, UART.
- `final-test/`: 71430 lezárt PC-referencia és hozzá tartozó INT8-bemenet.
- `final-quality/`: teljes MCU-futtatás, portolás/minőség és nyers UART.
- `final-benchmark/`: a négyprofilos teljes mérés, CSV, nyers UART és elemzés.
- `gui-live/`, `gui-benchmark/`: a közvetlen GUI–panel futások és CSV-k.

Az egyes futások külön resetet és run_id-t kaptak; nincs automatikus
kommunikációs újrapróbálás. A hibás kettős-kerekítésű részfutás külön
diagnosztikai eredmény maradt, nem olvadt a sikeres jelentésbe.

A Gitben tárolt kis bizonyítékok ellenőrzése a repó gyökeréből:

```bash
sha256sum -c docs/evidence/issue-7/SHA256SUMS
```

A helyi nagy artefaktumok ellenőrzése:

```python
import hashlib, json
from pathlib import Path
manifest = json.loads(Path('docs/evidence/issue-7/manifest.json').read_text())
for name, expected in manifest['local_artifacts_sha256'].items():
    h = hashlib.sha256()
    with open(name, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    assert h.hexdigest() == expected, name
```
