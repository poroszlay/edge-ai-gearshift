# #6 ellenőrzési jegyzőkönyv — 2026-10-22

## Követelmények és végrehajtási határ

Forrás: a [#6 issue](https://github.com/poroszlay/edge-ai-gearshift/issues/6)
aktuális törzse (komment nélkül), #3/#5/#7 issue-k, AGENTS.md, GLOSSARY.md,
a közös adat-/modell-/mérési szerződések és a #2/#3 megőrzött bizonyítékai.
A végrehajtás külön `feat/issue-6-int8-mlp` branchben,
`/tmp/edge-ai-gearshift-issue-6` worktree-ben, `b4c5fb2` alapból történt.
A párhuzamos #5 külön worktree-jét, kódját, soros portját és mérési
interfészeit nem módosítottuk. A helyreállított SDK-t olvasóként használtuk,
saját model_probe projekt-/konfiguráció-/buildkönyvtárral.

A felhasználó jóváhagyta a három teszthatárt. A kilenc red→green ciklus,
a javított fixture-elvárások és a natív TFLite-hiba naplója:
[tdd.md](tdd.md), `red-01.log`–`red-09.log`, `green-01.log`–`green-09.log`.

## Adatfelhasználás

A dataset-v2 újragenerált manifestje és lezárása bájtra egyezik a #3 v2
bizonyítékaival; a `pc.dataset verify` teljes auditja sikeres.
Az adatverzió `ef6f8048efec22e32cc44fd4c58b08052359ab6880ee52c2257e3da59f27ba4a`.
A manifest SHA-256-a `b45896680afa82671dd18450e56b85ffb4fbfa58a1a90218eaf8a95f45cb45bb`.
Naplók: [dataset-identity.log](dataset-identity.log), [dataset-verify.log](dataset-verify.log).

Tanítás és 1024 ablakos INT8-kalibráció: kizárólag train (333340 ablak).
Checkpoint-/jelöltválasztás: kizárólag validation (71430 ablak).
A lezárt tesztet csak az integritásaudit olvasta; **modellteszt-értékelés,
tesztalapú modellválasztás, kalibráció vagy visszahangolás nem történt**.
Nincs illesztett normalizálás, új felosztás, adatgenerátor- vagy címkeváltoztatás.

## Mért validáció és kiválasztás

Mind a négy jelölt az induló 100 → 32 → 16 → 3 MLP, két ReLU réteggel és
softmax kimenettel. Adam lr=0,001, batch=1024, max. 100 epoch, patience=15.
A súlyozott jelöltek train-osztályszámokból kapott inverz négyzetgyökös
súlyokat használnak. Nincs architektúraváltás. A második változat oka a
ritka váltási osztályok gyenge baseline-validációja; a további két seed az
előre rögzített próbakeret része. Minden konfiguráció és epoch megmaradt a
[candidates](candidates/) könyvtárban.

| Jelölt | Kiválasztott epoch | FP32 makro-F1 | INT8 makro-F1 |
| --- | ---: | ---: | ---: |
| baseline | 48 | 0.685654 | 0.616319 |
| weighted-20261022 | 51 | 0.719367 | 0.681208 |
| weighted-20261023 | 32 | 0.666150 | 0.614180 |
| weighted-20261024 | 24 | 0.660902 | 0.622922 |

A validációs INT8 makro-F1 szerinti nyertes `weighted-20261022`, 51. epoch.
A [selection.json](selection.json) befagyasztja a kiválasztást.
**A makro-F1 ≥ 0,95 cél nem teljesült.** Nem jelöljük teljesítettnek a #6
minőségi feltételét. A működő pipeline és integer adatút ettől külön igazolt.

A kiválasztott modell INT8 osztályonkénti eredménye:

| Osztály | Support | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| downshift | 284 | 0.566265 | 0.827465 | 0.672389 |
| hold | 70854 | 0.996831 | 0.994439 | 0.995634 |
| upshift | 292 | 0.353474 | 0.400685 | 0.375602 |

Tévesztési mátrix: sor=szabályreferencia, oszlop=modell,
`[downshift, hold, upshift]` sorrendben.

```text
FP32: [[246, 38, 0], [127, 70250, 477], [0, 91, 201]]
INT8: [[235, 49, 0], [180, 70460, 214], [0, 175, 117]]
```

Az FP32/INT8 döntésegyezés 0.993518130, eltérés 463 ablak.
Ez kvantálási összevetés PC-n, nem portolási helyesség és nem MCU-eredmény.
A részletes, kerekítetlen [validation.json](../../../models/mlp-v1/validation.json)
mindkét jelentést tartalmazza. A 99% fölötti accuracy önmagában nem igazolja
a ritka osztályok megtanulását.

## Tényleges INT8 és célkörnyezet

A kiválasztott `.tflite` **7568 bájt**, SHA-256:
`527bc3e722f8b2902fbf5a56e8872b185888b4939c4e5d6a7ff87175b786f1f9`.
INT8 IO: `[1,100]` → `[1,3]`. Bemeneti scale=0.005345386452972889,
zero_point=-60; kimeneti scale=0.00390625,
zero_point=-128.
Az audit tényleges FC v4 / SOFTMAX v2 műveleteket talál. A ReLU-k FC-be
fuzionáltak. Nincs float/hibrid/Flex/custom tensor vagy művelet; a három bias
INT32. A minden tenzorra kiterjedő típus-/alak-/kvantálási leltár:
[audit.json](../../../models/mlp-v1/audit.json).
A konverter beállításai és a kalibrációs ablaklista:
[export.json](../../../models/mlp-v1/export.json).

A rögzített Espressif 1.3.5 fully-connected és softmax forrása INT8 ágat,
a fully-connected per-channel súlyokat is kezel. A hivatalos forráslinkek
és reprodukáló parancsok a [modell leírásában](../../model.md) vannak.
Az aktuálisan használt források hash-e és környezet: [environment.json](environment.json).

A tanítás előtt a tanítatlan, azonos alakú MLP INT8-exportja sikeresen
fordult/linkelődött ESP32-re; utána a **kiválasztott saját modell** is.
IDF 5.5.1, esp-tflite-micro 1.3.5, esp-nn 1.1.1, esp32, CPU 240 MHz,
4 MiB DIO flash, PSRAM-feltételezés nélkül. A transzitív dependency lock
verziózott a model_probe projektben. Naplók: [smoke-build.log](smoke-build.log),
[final-build.log](final-build.log); effektív sdkconfig és binárishash-ek megőrizve.
Az [embedded-model.json](embedded-model.json) külön igazolja, hogy a végső
build generált headerében pontosan a kiválasztott modell bájtjai szerepelnek.
Modellútvonal-váltáskor explicit `reconfigure` történt.

Az első sandboxos build cache-írási korláton, majd az első CMake-változat
az IDF korai komponensfelderítésében használt relatív template-útvonalon
bukott. A sandboxon kívüli build és a komponens regisztrációja utáni,
abszolút template-útvonalas konfigurálás megoldotta ezeket. Az eredeti
stdout/stderr naplók a [build-failures](build-failures/) könyvtárban maradtak.

**Panelre feltöltés és MCU-runtime próba nem történt a #6-ban.** A 32 KiB
próbaaréna nem mérési eredmény. Sajátmodell-futási időt, RAM-igényt,
PC/MCU-egyezést vagy hardveres teljesítményt nem állítunk ebből a buildből.

## Reprodukálás és regresszió

A [modell dokumentáció](../../model.md) az elkülönített telepítést, mind a
négy konfigurációt, tanítást/exportot/validációt, referenciát és ESP32-buildet
reprodukáló parancsokat tartalmazza. Az összes Python-csomag pontos verziója:
[requirements-lock.txt](requirements-lock.txt).

A kiválasztott modell teljes tanítása másodszor is lefutott: a 66 epochos
előzmény bájtra azonos, minden FP32 súlytömb bitre azonos. Bizonyíték:
[training-reproduction.json](training-reproduction.json),
[training-reproduction.log](training-reproduction.log).
A `.keras` ZIP archívum mentési dátumának metaadata eltér, ezért annak
bájtszintű egyezését nem állítjuk. Az eredeti checkpoint változatlanul megmarad.
Az eredeti checkpointból ismételt INT8-export és exportmetaadat bájtra
azonos: [export-reproduction.sha256](export-reproduction.sha256).

A megismételt teljes tanítás checkpointjából készített új INT8-export is
bájtra azonos a kiválasztott modellel:
[full-reproduction-export.sha256](full-reproduction-export.sha256).

A 11 ablakos nyers referencia és PC-s INT8-kimenete második generálás/
futtatás után is bájtra azonos. Nem a tesztadatból származnak.
A kis modell (INT8 + FP32), konfiguráció és proveniencia verziózott;
a teljes generált adat és a nagy buildtermékek kizártak.

Teljes regresszió: **66 teszt, OK, 7 kihagyás**. A 9 új modellteszt valódi
TensorFlow/TFLite konverziót, inferenciát és CLI-folyamatot futtat, mock nélkül.
A 7 opcionális GUI-teszt PySide6 hiányában kimaradt; a felület nem módosult.
Napló: [regression.log](regression.log). Az első standard-library sandboxfutás
socketkorlátozáson bukott; a helyi socketet engedő teljes újrafuttatás sikeres.
A függőség nélküli munkafolyamatok a modellteszteket explicit kihagyják;
külön CI-job telepíti és futtatja a modellcsomagokat.

## Átadás és fennmaradó hiányok

A [#7 átadási jegyzék](handoff-7.md) megadja a befagyasztott modellt, két
külön portolási adatútját, a változatlan ±1 INT8 kódértékű tűrést és a nyitott
hardveres/minőségi/terhelésmérési feladatokat. A meglévő UART-séma változatlan.
A #5 aktuális mérőinterfészének integrációját a #7 végzi.

Nyitott: a 0,95 makro-F1 cél, a kvantálás okozta minőségromlás okának további
vizsgálata, valódi paneles sajátmodell-futás, teljes lezárt tesztértékelés,
PC/MCU-portolási helyesség, nyers előfeldolgozás MCU-ellenőrzése és teljes
idő-/memória-/terhelésmérés. A ritka osztályok gyengesége megfigyelés; sem a
szintetikus profilok reprezentativitását, sem a hiba pontos okát nem bizonyítja.
Új tanítási vagy architektúra-kísérlet csak új, dokumentált modellverzióként,
tanító/validációs adatokon következhet; a teszt nem hangolási visszacsatolás.
A #6 issue minőségi célja nem lett késznek nyilvánítva, issue-lezárás nem történt.


## PR #18 review-javítások (2026-10-22)

A felhasználó a `quantize` és `ReferenceModel.predict_int8` publikus
interfészeket jóváhagyta teszthatárként. Mindkét javítás külön red→green
ciklusban készült, belső komponensek mockolása nélkül.

- Kvantálás: a megőrzött modell skálájával a pozitív és negatív félérték,
  illetve közvetlen float32 szomszédai szerepelnek a regresszióban. A régi
  összeadás a félérték alatti abszolút értéket is felfelé kerekítette.
  Az osztás továbbra is float32; a hozzáadás float64-re szélesítése megőrzi
  a különbséget. [Bukó teszt](review-rounding-red.log),
  [sikeres tesztek](review-rounding-green.log).
- Hibás INT8-bemenet: az egyenetlen beágyazott lista korábban ValueError
  kivételt okozott. Most azonosítókkal és error mezővel ellátott invalid_input
  rekord keletkezik, döntési mezők nélkül; a következő érvényes hívás működik.
  [Bukó teszt](review-input-red.log), [sikeres teszt](review-input-green.log).
- A teljes modellteszt-csomag: **11 teszt, OK, kihagyás nélkül**,
  valódi TensorFlow/TFLite futással: [napló](review-model-regression.log).
- A dokumentált reference CLI újrafuttatása után a 11 archivált ablak
  PC-referenciája `cmp` szerint bájtra azonos. A modell és az archivált
  minőségi eredmények nem változtak. Újratanítás és tesztadat-értékelés
  nem történt. `git diff --check` sikeres.
