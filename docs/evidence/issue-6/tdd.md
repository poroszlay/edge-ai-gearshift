# #6 TDD: jóváhagyott teszthatárok

A felhasználó a tervezési egyeztetésben mindhárom határt jóváhagyta:

1. Tanítás/export CLI: adatfelhasználás, reprodukálhatóság, artefaktumok;
   önmagában nem igazol MCU-futást.
2. PC-s referencia API: nyers ablakból INT8 bemenet/kimenet, döntés,
   azonosítók és hibakezelés; önmagában nem igazol portolási helyességet.
3. Exportaudit és célkörnyezeti próba: tényleges integer gráf, kvantálás,
   alakok és TFLM-kompatibilitás; nem teljes minőség-/terhelésmérés.

Egy ciklus egy tesztből, tényleges RED futásból, minimális implementációból
és GREEN futásból áll. A számozott naplók a futások tényleges kimenetei.
Nincs belső kollaborátor-mock vagy privát függvényre írt teszt.

A numerikus metrikák és a kvantálás a PC-s referencia nyilvános API-jának
részei; a várt értékek kézzel ellenőrzött példák, nem implementációmásolatok.

## Ciklusok

| Ciklus | Nyilvános viselkedés | RED oka |
| --- | --- | --- |
| 01 | Kerekítés és INT8-telítés | Hiányzó modellmodul |
| 02 | Ritka osztályok és makro-F1 | Hiányzó referencia-metrika API |
| 03 | Valódi FP32 TFLite elutasítása | Hiányzó FlatBuffer-audit API |
| 04 | Split/purpose hozzáférési korlátok | Hiányzó adatbetöltési API |
| 05 | Valódi INT8-export, kalibrációs eredet | Hiányzó export API |
| 06 | Tanítás CLI, megőrzött checkpoint/proveniencia | CLI nem állított elő modellt |
| 07 | Nyers és kvantált referencia, hibastátusz | Hiányzó referencia API |
| 08 | Teljes validáció FP32/INT8 összevetése CLI-n | Hiányzó evaluate parancs |
| 09 | Referencia JSONL, azonosítók és hibás ablak | Hiányzó reference parancs |

A 06-os ciklus első GREEN-kísérlete a kétmásodperces fixture hiányzó
visszaváltási osztálya miatt helyesen elutasított tanítás volt. A fixture
4 s-ra bővült; a sikertelen kísérlet külön naplóban megmaradt.

A 07-es ciklus teljesen nullás súlyú fixture-je a TFLite natív
`allocate_tensors` hívását SIGABRT-tal megszakította. A natív stack és a
kimenet megmaradt. A nem degenerált, azonos három oszlopú 0,01 súlymátrix
ugyanúgy függetlenül ellenőrizhető, egyenlő softmax kimenetet ad, és lefut.
Ez a teszt továbbra is a [-43,-43,-43] INT8 kimenetet és a döntetlen
argmax szabályát ellenőrzi. Nem változott a konverter vagy az elfogadási cél.

A 08-as ciklus fixture-jének kézi számlálását javítottuk: a 4 s-os kanonikus
küszöbprofilban a 30. minta felváltás (ötmintás v-átlag 36,4 > 34), az 50.
visszaváltás (15 < 24, tau=1). A 70. mintánál v=24 < 34, g=1, ezért nincs
újabb felváltás. A 61 ablakból 1/59/1 a három osztály darabszáma. A hibás
első elvárás naplója is megmaradt; az elvárás nem az osztályozási metrika
implementációjából származik.

A célkörnyezeti buildpróba a harmadik jóváhagyott határ manuális integrációs
ellenőrzése: a tanítás előtt egy tanítatlan, azonos alakú teljes INT8-export
fordult le, majd a kiválasztott modell is külön újraellenőrzést kap.
Ez nem automatizált MCU-runtime teszt, és nincs hardveres PASS állítás.
