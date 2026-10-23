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
A teljes MCU-értékelést és négyprofilos benchmarkot a javított runtime-mal
új, külön naplójú kampány igazolja; az eredmények rögzítése folyamatban.
