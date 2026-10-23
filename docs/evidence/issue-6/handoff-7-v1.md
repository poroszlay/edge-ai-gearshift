# Átadás a #7-nek

## Befagyasztott modell és adat

A kiválasztás kizárólag a teljes validációs részhalmaz INT8 makro-F1-e
alapján történt; a lezárt teszt nem kapott modellértékelést.
[selection.json](selection.json) a négy jelöltet és a befagyasztást rögzíti.

- Modell: [models/mlp-v1/model.tflite](../../../models/mlp-v1/model.tflite).
- Modellazonosító / SHA-256:
  `527bc3e722f8b2902fbf5a56e8872b185888b4939c4e5d6a7ff87175b786f1f9`.
- FP32 checkpoint, konfiguráció, tanítási proveniencia, audit, kvantálás és
  kalibrációs ablaklista ugyanebben a `models/mlp-v1/` könyvtárban.
- Dataset-v2:
  `ef6f8048efec22e32cc44fd4c58b08052359ab6880ee52c2257e3da59f27ba4a`.
- Érvényes eredménymezők és a PC API: [modell dokumentáció](../../model.md).
- Minőségi állapot: **a 0,95 makro-F1 cél nem teljesült**; INT8 validáció
  0,6812082449675506, FP32 0,7193671440035141. Ez nem teszteredmény.

Az osztálysorrend `downshift, hold, upshift`, index 0/1/2, action -1/0/+1.
A bemenet `[1,100]`, a kimenet `[1,3]`, mindkettő INT8. Az audit az aktuális
FC/SOFTMAX műveletverziókat és minden tenzor skáláját/nullpontját tartalmazza.
A biasok INT32 típusúak; ez nem float visszaesés. A reference interpreter
`BUILTIN_REF` kerneleket használ, delegate nélkül.

## Két külön portolási út

1. A [pc-reference.jsonl](pc-reference.jsonl) `input_int8` mezőjét add át az
   MCU-nak. Az osztálydöntésnek egyeznie kell, minden numerikus kimeneti elem
   eltérése legfeljebb **1 INT8 kódérték**. Ne lazítsd automatikusan a tűrést.
2. A [reference-windows.jsonl](reference-windows.jsonl) nyers ablakait is
   dolgozd fel: érvényesség → rögzített skálázás → float32 → kvantálás.
   A PC `input_float32` és `input_int8` mezőivel külön vesd össze ezt az utat,
   hogy az előre kvantált út ne fedjen el előfeldolgozási hibát.

A 11 validációs ablak mindhárom referenciacímkét és a tau=0,95, tau=1,
tau>10 eseteket tartalmazza. Ez kis portolási ellenőrzőkészlet, nem a teljes
minőségi vagy teljesítményeloszlás. Az inputfájl `reference_class_index`
mezője a szabályreferencia címkéje; a PC modell ettől eltérhet. A portolási
helyességet az MCU és a **PC modell** kimenete között kell vizsgálni.

A skálázás a PC-n binary64, utána float32-re szűkítés; kvantáláskor
float32 osztás, félértéknél nullától távolodó kerekítés, nullpont hozzáadása,
majd INT8-telítés történik. Ezt a sorrendet határértékeknél is ellenőrizd.
Az argmax holtversenyben a kisebb indexet választja. Hibás bemenetnek nincs
érvényes döntése; a modell-, kommunikációs és memóriahiba sem tartás.

## Firmware és teljes mérés

A `firmware/esp32/model_probe` önálló projekt a rögzített IDF 5.5.1 /
esp-tflite-micro 1.3.5 / esp-nn 1.1.1 alaphoz. A tanítás előtti kis exporttal
és a kiválasztott modellel is fordítási/linkelési próbát kap. A végső build
beágyazott headerének bájtjait a kiválasztott `.tflite` fájllal külön összevetjük.
Ez nem helyettesíti az AllocateTensors/Invoke **valódi paneles** futását.
A próbaaréna 32 KiB mérete nem igazolt szükséges munkaterület.

A #5 külön branchben/worktree-ben dolgozik; mérőmodulját a #6 nem módosította.
A #7-ben az aktuális #5 interfészt és a meglévő JSON Lines szerződést kell
összekötni a modellel. A szimulátor jelenlegi `simulator_stub` kimenete
nem helyettesíthető csendben hardveres eredménnyel vagy tanult modellel.

A #7-re marad:

- A teljes lezárt teszt 71430 ablakának egyszeri minőségi értékelése és a
  PC/MCU numerikus eltérések külön jelentése. Nincs tesztalapú visszahangolás.
- Minden ablak és eltérés visszakeresése run/window/model/dataset azonosítóval.
- A rögzített nyers állapot visszajátszása; a modell döntése nem módosítja.
- Élő és előtöltött, UART nélküli benchmark mód, #5 mérési határaival.
- T=D=10/20/50/100 ms, profilonként 100 bemelegítő és 3×1000 ütemezett feladat;
  minden kimaradás, túllépés, idő-, memóriaadat és UART-várakozás elszámolása.
- Modell, firmware, effektív sdkconfig, órajelek, panel és binárisok checksumai.

A minőségi cél hiánya ismert korlát. Későbbi tanítási/architektúra-kísérletet
új modellverzióként, tanító/validációs adaton kell végezni, a lezárt teszt
visszacsatolása nélkül. A jelenlegi jelöltek között nem történt architektúraváltás.
