# #6: ritka váltások és INT8-minőség vizsgálata

Utólagos feladatszétválasztás: a vizsgálat legjobb jelöltje befagyasztva,
a minőségi cél a #19-be került. Lásd a [lezárási átadást](../closure-20261023.md).

A **0,95 validációs makro-F1 cél továbbra sem teljesült**. A közzétett
`models/mlp-v1` modell és korábbi kiválasztási jegyzőkönyve változatlan.
Az alábbi új kísérletek kizárólag tanító- és validációs adatot használnak.
A teszthalmazt nem értékeltük és nem használtuk visszahangolásra.

## Reprodukció és adatfelhasználás

A generátor `config/dataset-v2.json` konfigurációval újra létrehozta az
adatokat. A teljes manifest bájtra egyezik a korábban lezárt v2 manifesttel;
az eredeti `test-lock.json` került a reprodukált könyvtárba. Adatverzió:
`ef6f8048efec22e32cc44fd4c58b08052359ab6880ee52c2257e3da59f27ba4a`.
Az értékelő minden beolvasott tanító-/validációs fájl ellenőrzőösszegét és
címkéjét a meglévő `read_windows` határon ellenőrzi.

Környezet: elkülönített `/tmp/gearshift-quality-venv`, a korábbi
`docs/evidence/issue-6/requirements-lock.txt` csomagverzióival, TensorFlow
2.20.0; `tools/model-env.sh` determinisztikus CPU-beállításokkal.
Új kimeneti nevekkel, a repository gyökeréből:

```bash
. tools/model-env.sh
python -m pc.model evaluate --dataset data/generated/dataset-v2 \
  --export models/mlp-v1 --keras models/mlp-v1/model.keras \
  --output baseline-validation.json
python -m pc.model evaluate --dataset data/generated/dataset-v2 \
  --export models/mlp-v1 --keras models/mlp-v1/model.keras \
  --split train --output baseline-train.json
python -m pc.model export --dataset data/generated/dataset-v2 \
  --keras models/mlp-v1/model.keras --output calibration-64 --calibration-size 64
python -m pc.model evaluate --dataset data/generated/dataset-v2 \
  --export calibration-64 --keras models/mlp-v1/model.keras \
  --output calibration-64-validation.json
```

A 4096 ablakos kísérlet ugyanígy `--calibration-size 4096`-tal, külön
könyvtárban készül. Mindegyik kalibráció csak tanítóablakokat használ.
A helyben megőrzött exportkönyvtárak pontos útjai a `selection.json`-ban
vannak; az `export.json` rögzíti az összes kalibrációs ablak azonosítóját,
forrásmodell-hasht, kvantálási paramétert és konverziós beállítást.

## Alapmodell: reprodukált hiba

| Adatrész | Ablak | FP32 makro-F1 | Kerekített bemenetű FP32 | INT8 makro-F1 |
| --- | ---: | ---: | ---: | ---: |
| tanító | 333340 | 0,759066 | 0,746539 | 0,738194 |
| validáció | 71430 | 0,719367 | 0,753602 | 0,681208 |

Az FP32 már a tanítóadaton is gyenge a ritka osztályokban. A probléma
nem magyarázható kizárólag validációs általánosítási hibával vagy kvantálással.

Validációs osztályonkénti F1:

| Osztály | Support | FP32 F1 | INT8 F1 | FP32 recall | INT8 recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| visszaváltás | 284 | 0,748858 | 0,672389 | 0,866197 | 0,827465 |
| tartás | 70854 | 0,994810 | 0,995634 | 0,991475 | 0,994439 |
| felváltás | 292 | 0,414433 | 0,375602 | 0,688356 | 0,400685 |

A tartás 99% feletti pontossága elfedi a váltási hibákat. Az FP32
127 téves visszaváltást és 477 téves felváltást jelez tartás helyett;
az INT8 180-at és 214-et. Ugyanakkor az elmulasztott felváltások száma
91-ről 175-re nő. Teljes tévesztési mátrixok és osztálymetrikák a JSON-okban.

## Kvantálási hibák elkülönítése

Az FP32-háló ugyanazon, INT8-ból visszaállított bemenettel történő futtatása
elkülöníti a bemeneti kerekítést a további hálózati kvantálástól. Ez utóbbi
együtt foglalja magában a súlyokat, aktivációkat és kimeneti softmaxot;
a mérés nem választja ezeket külön.

Validáción a bemeneti kerekítés 34 új hibát okoz, 242-t kijavít. Ehhez
képest a teljes integer háló további 179 új hibát okoz, 86-ot kijavít.
Ezen belül **83 felváltás válik újonnan hibássá, egy sem javul meg**.
Az eredeti FP32 → INT8 út összesen 84 helyes felváltást veszít el;
a felváltás-romlásból 83 már a kerekített bemenetű FP32 → INT8 lépésben
bekövetkezik. Ez az alapmodell fő kvantálási minőségromlása.

Tanítóadaton a bemeneti kerekítés 387 új / 204 javított hibát,
a további hálózati kvantálás 442 új / 699 javított hibát jelent.
Az eltérő osztályarányok és a hibák osztályonkénti eloszlása miatt az
összhibaszám csökkenése sem garantál jobb makro-F1-et. A két lépés
hibaszámai nem adhatók egyszerűen össze: egymás hibáit is javíthatják.

## Küszöbök és reprezentáció

Az alapmodell inputskálája 0,00534538645. Ez a sebességnél körülbelül
0,427631 km/h, az igénynél 0,005345, a meredekségnél 0,053454
százalékpont, a tau-nál 0,053454 s lépésnek felel meg.

Validáción a visszaváltások **179/284**, a felváltások **247/292** esetben
legfeljebb 0,25 km/h-ra vannak az aktuális fokozathoz tartozó küszöbtől.
Tanítón ugyanez 917/1496 és 1273/1497. A minták jelentős része tehát a
kvantálási lépésnél kisebb különbséget kíván megkülönböztetni.

Az `error_examples` között azonosítóval visszakereshetők küszöbközeli
hibák és váltási tiltás alatti téves váltások is. A példák szétterített
részminták, nem a teljes hibaeloszlás becslései.

Két további, nem modellválasztó diagnosztikai próba:

- `rule-input-probe.py`: a szabály képletét visszaszámolja a már skálázott
  float32 és a visszaállított INT8 bemenetből. Az előbbi sem az eredeti,
  nyers binary64-címkézés: küszöbegyezésnél a skálázás/kerekítés változtathat
  a szigorú összehasonlításon. Ennek makro-F1-e validáción 0,845523, a
  kvantált bemenetből 0,776005. Ezek érzékenységi diagnosztikák, nem tanult
  modelljelöltek vagy az elérhető makro-F1 felső korlátai.
- `alias-probe.py`: a teljes 100 elemű bemenet bájtazonossága szerint keres
  ellentmondó címkéket, adatrészen belül. Tanítón sem float32-ben, sem
  INT8-ban nincs ilyen konfliktus; validáción float32-ben nincs, INT8-ban
  egy csoport van 11 tartás és 1 felváltás címkével. Ez legalább egy
  elkerülhetetlen hibát bizonyít ezen az INT8-rácson, **nem** a 0,95-ös
  cél elérhetetlenségét.

A két script a repository gyökeréből, `PYTHONPATH=.` mellett futtatható.
A diagnosztikai kimenetük a `results/issue-6/quality` könyvtárba kerül;
a megőrzött eredmények itt is megtalálhatók.

## Kalibrációs kísérlet és kapacitás

| Kalibrációs tanítóablak | Validációs INT8 makro-F1 | Visszaváltás F1 | Felváltás F1 |
| --- | ---: | ---: | ---: |
| 64 | 0,693487 | 0,754545 | 0,330808 |
| 1024, eredeti | 0,681208 | 0,672389 | 0,375602 |
| 4096 | 0,677835 | 0,671449 | 0,366509 |

A kalibráció méretének egyszerű növelése nem oldja meg a hibát. A 64-es
jelölt kismértékben javítja a makro-F1-et, de a felváltást rontja.
Mindhárom export teljes integer auditon ment át.

A `config/model-v2-capacity.json` a 100 → 64 → 32 → 3 architektúrát
vizsgálja két ReLU réteggel. Indoka a tanítóadaton is gyenge FP32-minőség;
a bemenet, lapítás és rögzített előfeldolgozás változatlan. Seed 20261022,
Adam 0,0005, batch 512, legfeljebb 160 epoch, türelem 35, kizárólag
trainből számolt inverse-sqrt osztálysúlyok. A legjobb FP32-checkpoint a
97. epoch, validációs makro-F1-e 0,719059; a tanítás a 132. epochnál állt le.
A konfiguráció, teljes history, forrásmodell-hash és eredmények megmaradtak.

| Nagyobb háló adatrésze | FP32 makro-F1 | Kerekített bemenetű FP32 | INT8 makro-F1 |
| --- | ---: | ---: | ---: |
| tanító | 0,757156 | 0,750045 | 0,735625 |
| validáció | 0,719059 | 0,720537 | **0,702852** |

Ez a vizsgált jelöltek legjobb validációs INT8-eredménye, de továbbra is
jóval a cél alatt van. A validációs INT8-mátrix:
`[[282,2,0],[525,70184,145],[0,106,186]]`.
A visszaváltási recall javulása mellett sok a téves visszaváltás; az
összesített javulás nem jelenti minden ritka osztály F1-ének javulását.
Az export integer auditja sikeres, a forrásmodell és a konvertált modell
helyben a `results/issue-6/quality/capacity/` alatt maradt. A pontos fájlhashek
`local-artifacts.sha256`-ban vannak; nagyobb generált állományokat nem
másoltunk automatikusan a verziózott források közé.

Reprodukció:

```bash
python -m pc.model train --dataset data/generated/dataset-v2 \
  --config config/model-v2-capacity.json --output capacity-repeat
python -m pc.model export --dataset data/generated/dataset-v2 \
  --keras capacity-repeat/model.keras --output capacity-repeat/export
python -m pc.model evaluate --dataset data/generated/dataset-v2 \
  --keras capacity-repeat/model.keras --export capacity-repeat/export \
  --output capacity-repeat/validation.json
```

## TDD és ellenőrzések

A korábban jóváhagyott tanítás/export CLI és PC-s referencia teszthatárai:
[`../tdd.md`](../tdd.md). Új teszthatár nem kellett.

1. RED: az `evaluate --split train` nem létezett; GREEN: valódi exporton,
   validációs/tesztfájl nélküli fixture-en tanítóértékelés, három előrejelzési
   út és visszakereshető hibák. A szándékosan közel azonos softmax-kimenetek
   INT8-döntetlenje kézzel ellenőrizhetően 59 új hibát és 1 javítást okoz.
2. RED: a tanítás elutasította a dokumentált nagyobb hálót; GREEN:
   konfigurált két rejtett szélesség, kötelező változtatási indokkal,
   megőrzött validációs kiválasztással és adatverzióval.
3. RED: hiányzott az osztályonkénti kvantálási hibaelszámolás; GREEN:
   valódi osztály szerint külön új/javított hiba és döntésváltozás.

A modelltesztek: **12/12 sikeres**. Teljes regresszió sandboxon kívül:
**84 teszt, OK, 8 kihagyva** (7 GUI-teszt opcionális függőségek nélkül,
1 ESP32-teszt megadott hardverport nélkül).
Az első teljes sandboxfutás socketműveleteknél tiltásba ütközött; ezt nem
tekintjük termékhibának. Az engedélyezett újrafuttatás sikeres.
A célküszöb nem lett átírva, a tesztadat nem lett modellválasztási bemenet.

## Fennmaradó munka

A #6 minőségi cél nyitva marad. Az egyszerű kalibrációs és kapacitásváltoztatás
nem igazolt megoldást. Következő indokolt kísérlet a kvantálást tudatosító
tanítás, valamint az utolsó öt minta és a legfrissebb g/tau kezelését segítő
hálózati szerkezet, változatlan 100 elemű külső bemenettel. Ezeket is kizárólag
tanítón szabad illeszteni, validáción választani, és az integer műveletkészletet
újra auditálni kell. A jelen vizsgálat nem igazol MCU-futást.
