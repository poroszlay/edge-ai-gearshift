# Első MLP, teljes INT8-export és PC-s referencia (#6)

A modell a **szabályreferencia megtanulását** méri szintetikus laborjeleken.
A PC-s referencia és az ESP32-fordítás nem helyettesíti a #7 portolási
helyességi és valódi paneles vizsgálatát.

A kis kiválasztott FP32-checkpoint és INT8-modell a verziózott
`models/mlp-v1/` könyvtárban marad; a teljes generált adatok és a nagy
buildtermékek nem kerülnek Gitbe.

A tényleges eredmények, checksumok, red→green naplók és a #7 átadása:
[ellenőrzési jegyzőkönyv](evidence/issue-6/verification.md).

## Környezet és adatok

Python 3.13.5, TensorFlow 2.20.0, CPU. Az összes feloldott csomagverzió:
[requirements-lock.txt](evidence/issue-6/requirements-lock.txt). A modellhez
szükséges függőségek elkülönülnek a standard library alapú adatgenerálástól,
kommunikációtól és a felület függőségeitől.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r docs/evidence/issue-6/requirements-lock.txt
. tools/model-env.sh
python -m unittest discover -s tests -p test_model.py -v
```

Debianon a `venv`-hez a megfelelő `python3.13-venv` csomag szükséges.
Ebben a munkamenetben a Python hiányzó ensurepip modulja miatt a hivatalos
`https://bootstrap.pypa.io/get-pip.py` segítségével kapott pipet a már
létrehozott, elkülönített `/tmp/gearshift-issue6-venv`. Nem történt globális
Python-csomagtelepítés. A `tools/model-env.sh` a determinisztikus CPU-s
futás beállításait és a párhuzamos szálak korlátozását tartalmazza.

Az eredeti dataset-v2 reprodukálása a [dataset dokumentáció](dataset.md)
szerint történik, az eredeti generátor-/címkézőforrásból. A felhasznált ID:
`ef6f8048efec22e32cc44fd4c58b08052359ab6880ee52c2257e3da59f27ba4a`.
A `generate`, majd `seal` után:

```bash
cmp data/generated/dataset-v2/manifest.json docs/evidence/issue-3/v2/manifest.json
cmp data/generated/dataset-v2/test-lock.json docs/evidence/issue-3/v2/test-lock.json
python -m pc.dataset verify data/generated/dataset-v2
```

A `verify` tesztadat-olvasása integritás-/címkeaudit, nem modellértékelés.
A modellpipeline a tanításhoz és kalibrációhoz csak `train.csv`-t,
checkpoint-választáshoz és összehasonlításhoz csak `validation.csv`-t nyit.
A tesztadatot nem használja. A CLI `evaluate` kizárólag validációt értékel.
A teljes lezárt tesztértékelés a befagyasztott modellre, a #7-ben történik.

## Tanítás, export, validáció

Új kimeneti könyvtárakba, a repository gyökeréből:

```bash
mkdir -p results/issue-6
python -m pc.model train --dataset data/generated/dataset-v2 \
  --config config/model-v1.json --output results/issue-6/baseline
python -m pc.model export --dataset data/generated/dataset-v2 \
  --keras results/issue-6/baseline/model.keras --output results/issue-6/baseline/export
python -m pc.model audit results/issue-6/baseline/export/model.tflite
python -m pc.model evaluate --dataset data/generated/dataset-v2 \
  --keras results/issue-6/baseline/model.keras --export results/issue-6/baseline/export \
  --output results/issue-6/baseline/validation.json
```

Az első modell 100 → 32 → 16 → 3, két ReLU rejtett réteggel és softmax
kimenettel. A változatlan osztálysorrend: `downshift`, `hold`, `upshift`;
az index 0/1/2, a döntési érték -1/0/+1. A konfiguráció rögzíti a seedet,
Adam tanulási rátáját, batchméretet, epochkorlátot és türelmet.
Minden epoch validációs makro-F1-et kap; csak szigorú javulás cseréli a
checkpointot, holtversenyben a korábbi marad. A korai leállítás is kizárólag
validációs. Az ablakok közti menetfelosztás változatlan.

A ritka osztályok miatt második jelöltként a `config/model-v1-weighted.json`
fut, külön kimeneti könyvtárban. Osztálysúlya a tanítócímkék gyakoriságának
inverz négyzetgyöke, a tanítóablakok átlagos súlyára normalizálva.
Ha szükséges, ugyanez a konfiguráció 20261023 és 20261024 seeddel ismétlődik,
megőrzött konfigurációval. Az architektúra mindvégig az induló háló marad.
A jelöltek közül a teljes validáció INT8 makro-F1-e dönt; holtversenyben a
korábbi jelölt nyer. A 0,95 alatti eredmény nem teljesült cél.

A tanítás kimenete: `model.keras`, teljes `config.json`, `training.json`,
`history.json`, `validation-fp32.json`. Az export: `model.tflite`, `audit.json`,
`export.json`. A két összehasonlítható minőségi jelentést a `validation.json`
tartalmazza: makro-F1, osztályonként precision/recall/F1/support, tévesztési
mátrix (sor=referencia, oszlop=modell), egyezési arány és eltérésszám.
Hiányzó osztályhoz vagy nulla nevezőhöz a metrika 0-t rendel.

A kalibráció determinisztikusan, osztályonként szétterített tanítóablakokat
választ, alapértéken 1024-et. A pontos azonosítólista és az eredeti FP32-modell
SHA-256 értéke az `export.json` része. A kalibráció nem illeszt skálázást
validációs vagy tesztablakhoz.

A konverter `TFLITE_BUILTINS_INT8` műveletekre és INT8 IO-ra korlátozott.
Az audit az **elkészült FlatBuffert** olvassa: minden tenzor INT8 vagy
megengedett INT32 bias/alakleíró, az IO `[1,100]` → `[1,3]`, pozitív skálákkal
és érvényes nullpontokkal. Lebegőpontos, Flex/custom és nem támogatott
műveleteknél hibát ad. A tényleges műveletverziókat és per-channel skálákat
is megőrzi, majd a TFLite reference integer kernelekkel következtet.
Az INT32 bias és az egész akkumuláció nem lebegőpontos visszaesés.

Hivatalos források:

- [Teljes integer konverzió](https://developers.google.com/edge/litert/conversion/tensorflow/quantization/post_training_integer_quant).
- [Espressif 1.3.5 komponens](https://components.espressif.com/components/espressif/esp-tflite-micro/versions/1.3.5/readme).
- [Rögzített INT8 fully-connected kernel](https://github.com/espressif/esp-tflite-micro/blob/5f31ea08cee30ef3c2a1dfe7357f4be4048bc044/tensorflow/lite/micro/kernels/esp_nn/fully_connected.cc).
- [Rögzített INT8 softmax kernel](https://github.com/espressif/esp-tflite-micro/blob/5f31ea08cee30ef3c2a1dfe7357f4be4048bc044/tensorflow/lite/micro/kernels/esp_nn/softmax.cc).

## PC-s referencia API és fájlformátum

```python
from pc.model import ReferenceModel

reference = ReferenceModel('results/issue-6/baseline/export')
result = reference.predict(window)
# Külön portolási út, pontosan 100 INT8 kóddal:
result = reference.predict_int8(codes, window_id='trip:19', trip_id='trip')
```

A `window` a [meglévő kommunikációs szerződés](communication.md) objektuma:
`window_id`, `trip_id`, 20 elemű `timestamps_ms`, 20 × 5-ös `samples`.
A `gearshift.protocol.preprocess` ellenőriz és skáláz, nem másik előfeldolgozó.
A skálázás a Python binary64 műveleteivel történik, majd a 100 érték float32-re
alakul, ugyanúgy, mint az adatkészlet ablakainál. A kvantálás float32 osztás,
`round-half-away-from-zero(x/scale) + zero_point`, végül [-128,127] telítés.
A #7-nek ezt a műveleti sorrendet is ellenőriznie kell; a nyers bemenet
korábbi float32-re szűkítése határértéknél eltérést okozhat.

A sikeres `pc-reference-v1` rekord tartalmazza a `status=ok`, `model_id`
(a TFLite-fájl SHA-256-a), `dataset_id`, `input_version`, `window_id`,
`trip_id`, `input_int8[100]`, `output_int8[3]`, `class_index`, `action`,
`decision` és `decision_source=int8_mlp` mezőket. A nyers út a
`input_float32[100]` értékeket is megőrzi. Az argmax holtversenyben a kisebb
indexet választja. Az INT8 kimenet numerikus kód, nem döntési címke.

Hibás ablak `invalid_window`, hibás kvantált bemenet `invalid_input`,
futtatási hiba `model_error` státuszt kap, `error` mezővel és döntés nélkül.
Hibás vagy eltérő modell/metadata már a betöltéskor hibát okoz.

```bash
python -m pc.model reference --export results/issue-6/baseline/export \
  --input windows.jsonl --output pc-reference.jsonl --run-id pc-run-1
```

Egy bemeneti JSON-sorhoz egy eredménysor készül; a fájlos út `run_id`-t is
hozzáad. Meglévő kimenet nem írható felül. Hibás JSON megszakítja a folyamatot
nemnulla kilépési kóddal: az addig elkészült fájl ilyenkor részleges.
Ez önálló PC-s referenciaformátum, nem módosítja a v1 soros üzenetsémát.

## Célkörnyezeti próba

A saját `firmware/esp32/model_probe` projekt az auditált modell teljes
bájtsorát fordítja be; nincs kézzel átírt vagy szinuszmodellre cserélt súly.
Az ESP-IDF 5.5.1 környezet betöltése után:

```bash
export GEARSHIFT_MODEL_PATH="$PWD/results/issue-6/baseline/export/model.tflite"
idf.py -C firmware/esp32/model_probe -DIDF_TARGET=esp32 reconfigure build
```

Modellútvonal-váltáskor kötelező a `reconfigure`, hogy az új bájtsor
kerüljön a generált headerbe. Az azonos útvonalon módosult fájlt a CMake
configure-függősége is követi.

A komponensverziók: esp-tflite-micro 1.3.5, esp-nn 1.1.1. A projekt külön
buildet, sdkconfigot és dependency lockot használ; nem módosítja a #5-öt.
A regisztrált műveletek FullyConnected, Softmax, Reshape és ReLU; a konkrét
modell auditja mutatja, melyek szerepelnek ténylegesen a gráfban.
A 32 KiB próbaaréna **nem igazolt sajátmodell-memóriaigény**. A forrásban
lévő AllocateTensors/Invoke ellenőrzések és PASS-sor csak valódi futáskor
számítanak runtime-bizonyítéknak. A build sikere kizárólag fordítási/linkelési
bizonyíték. A panel feltöltése és teljes integrációja a #7 feladata.

## A kis referenciacsomag újraállítása

Új kimeneti fájlnevekkel:

```bash
python tools/model-reference-windows.py --dataset data/generated/dataset-v2 \
  --output reference-windows-repeat.jsonl
python -m pc.model reference --export models/mlp-v1 \
  --input reference-windows-repeat.jsonl --output pc-reference-repeat.jsonl \
  --run-id issue6-pc-reference-v1
cmp reference-windows-repeat.jsonl docs/evidence/issue-6/reference-windows.jsonl
cmp pc-reference-repeat.jsonl docs/evidence/issue-6/pc-reference.jsonl
```

A script kizárólag validációs ablakokat választ, a sorrend rögzített. A
referenciafájlok nem fedik le a teljes tesztet, és nem MCU-eredmények.

A teljes jelöltlista reprodukálásához a fenti train/export/evaluate parancsokat
az alábbi párokkal kell futtatni, külön, új kimeneti könyvtárakba:

| Jelölt | Tanítási konfiguráció |
| --- | --- |
| baseline | `config/model-v1.json` |
| weighted-20261022 | `config/model-v1-weighted.json` |
| weighted-20261023 | `config/model-v1-weighted-20261023.json` |
| weighted-20261024 | `config/model-v1-weighted-20261024.json` |

A kalibráció mindegyiknél 1024 tanítóablak, a sorrend és azonosítók az
exportmetaadatban vannak. A közzétett modell kiválasztását a megőrzött
`selection.json` rögzíti; a lezárt teszteredmény nem lehet új kiválasztási bemenet.
