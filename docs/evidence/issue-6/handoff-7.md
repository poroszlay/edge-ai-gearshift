# Átadás a #7-nek

## Befagyasztott modell és adat

A kiválasztás kizárólag a teljes validációs részhalmaz INT8 makro-F1-e
alapján történt; a lezárt teszt nem kapott modellértékelést.
A jelenlegi átadott modell **mlp-v2**, a 2026-10-23-i kapacitáskísérlet
validációs INT8 makro-F1 szerinti nyertese. A [freeze.json](../../../models/mlp-v2/freeze.json)
és a [SHA256SUMS](../../../models/mlp-v2/SHA256SUMS) rögzíti a befagyasztást.
A korábbi v1 átadás változatlan történeti másolata: [handoff-7-v1.md](handoff-7-v1.md).
A minőségjavítás külön [#19 feladat](https://github.com/poroszlay/edge-ai-gearshift/issues/19),
nem feltétele a #7 megkezdésének. A befagyasztott csomagot nem írjuk felül.

- Modell: [models/mlp-v2/model.tflite](../../../models/mlp-v2/model.tflite).
- Modellazonosító / SHA-256:
  `6d5ac8613d301ca06de2ca9a4cfbadf3cd40c7c75a7af419505eaa9fcbb25f79`.
- FP32 checkpoint, konfiguráció, tanítási proveniencia, audit, kvantálás és
  kalibrációs ablaklista ugyanebben a `models/mlp-v2/` könyvtárban.
- Dataset-v2:
  `ef6f8048efec22e32cc44fd4c58b08052359ab6880ee52c2257e3da59f27ba4a`.
- Érvényes eredménymezők és a PC API: [modell dokumentáció](../../model.md).
- Minőségi állapot: **a 0,95 makro-F1 cél nem teljesült**; INT8 validáció
  0,7028518838863791, FP32 0,7190588743184095. Ez nem teszteredmény.

Az osztálysorrend `downshift, hold, upshift`, index 0/1/2, action -1/0/+1.
A bemenet `[1,100]`, a kimenet `[1,3]`, mindkettő INT8. Az audit az aktuális
FC/SOFTMAX műveletverziókat és minden tenzor skáláját/nullpontját tartalmazza.
A biasok INT32 típusúak; ez nem float visszaesés. A reference interpreter
`BUILTIN_REF` kerneleket használ, delegate nélkül.

## Két külön portolási út

1. A [pc-reference.jsonl](../../../models/mlp-v2/pc-reference.jsonl) `input_int8` mezőjét add át az
   MCU-nak. Az osztálydöntésnek egyeznie kell, minden numerikus kimeneti elem
   eltérése legfeljebb **1 INT8 kódérték**. Ne lazítsd automatikusan a tűrést.
2. A [reference-windows.jsonl](../../../models/mlp-v2/reference-windows.jsonl) nyers ablakait is
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
esp-tflite-micro 1.3.5 / esp-nn 1.1.1 alaphoz. A korábban megőrzött sikeres
build a v1 modellre vonatkozik. A nagyobb v2 modell PC-s integer auditja és
referenciája ellenőrzött, **saját ESP32-buildje és MCU-futtatása még nem**;
a helyi SDK ebben a munkamenetben nem volt elérhető. A #7-ben kötelező az új
modell explicit reconfigure/build próbája és a beágyazott modell hash-ének
ellenőrzése. Ezután szükséges az AllocateTensors/Invoke valódi paneles futása.
A 32 KiB próbaaréna megfelelősége a v2-re sem igazolt.

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
visszacsatolása nélkül. A v2 architektúrája 100 → 64 → 32 → 3; az indok és a konfiguráció a csomagban megmaradt.
