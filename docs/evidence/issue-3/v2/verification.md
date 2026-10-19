# #3 / PR #16: P1 adatszivárgás javítása, dataset-v2

Kiinduló PR-head: `5377292cb6e544d27f8708b600eb8a5ada9fdca3`, meglévő
`feat/issue-3-synthetic-dataset` branch, `/tmp/edge-ai-gearshift-issue-3`
worktree. A GitHub teljes review-, inline komment- és általános kommentlistája
alapján egy finding volt: [P1 – fáziseltolt alapmenetek közötti adatszivárgás](https://github.com/poroszlay/edge-ai-gearshift/pull/16#issuecomment-6273429812).

## Finding ellenőrzése és javítása

A finding igazolt, elfogadva. A két konkrét fel-/visszaváltási ablakmásolatot
a korábban jóváhagyott `make_plan` → `generate_run` → `iter_windows`
publikus teszthatáron először bukó regresszió reprodukálta (`red-profile.log`).
A teljes v1 adatkészlet csak olvasó, 476200 modellablakos auditja megismételte
a reviewer számait: 35228 validációs és 35023 tesztablak tanítóablak-másolat;
a validáció/teszt párban további 34705 tesztablak egyezett. Az audit kilépési
kódja 1, a részletes eredmény `v1-overlap.json` és `v1-overlap.stderr`.

A v2 minden családhoz önálló, seedelt profilrealizációt rendel, a részhalmaztól
függetlenül. A periódus, sebesség-/igényszorzó és emelkedőparaméterek is
változnak; a családok nem ugyanazon idősor fázismásolatai. Egy család alapmenete
és minden zajos/fáziseltolt leszármazottja továbbra is azonos profilseedhez,
családhoz és részhalmazhoz tartozik. A profilt azonosító metaadat nem válik
modellbemenetté. A részhalmazkiosztás továbbra is ablakolás előtt történik.

Új, csak olvasó `audit-overlap` CLI és beépített export-/verify-/seal-kapu
vizsgálja a teljes, ténylegesen skálázott 100 elemű bemenet egyezését mindhárom
részhalmazpárban, minden osztályra és a zajos változatokra is. Az audit nincs
menetazonosítóhoz, időbélyeghez vagy címkéhez kötve; a tau telítését is figyelembe
veszi. A bemeneti ujjlenyomat képzése és a számlálás a [sémaleírásban](../../../dataset.md)
szerepel. A részhalmazon belüli ismétlődések megengedettek.

További TDD-lépések:

- `red-audit.log`: eltérő azonosítójú és nyers tau-jú, de azonos skálázott
  ablakok vizsgálata először a hiányzó CLI miatt bukott; most mindhárom pár
  egyezését jelzi és nemnulla kóddal tér vissza.
- `red-gate.log`: érvényes állapotú, érvényes referenciacímkéjű, helyes
  ablakindexű és frissített checksumú tanítóablak-másolat diagnózisából
  hiányzott a konkrét átfedésészlelés. Most a `verify` és a `seal` kifejezetten
  a részhalmazok közötti bemenetegyezést utasítja el, lezárás nem keletkezik.
- A rövidített, de mind a 200 menetet és zajos változatot tartalmazó regresszió
  közvetlen `Window.features` tuple-egyezéssel is vizsgálja mindhárom párt,
  az audit SHA-256 implementációjától függetlenül.

Teljes regresszió: `python3 -m unittest discover -s tests -v`, **48 teszt OK**
(a korábbi 44 + 4 új teszt), Python 3.13.5. Teljes napló: `tests.log`.
A sockettesztek miatt a teljes futás helyi socketküldést engedő környezetben
történt. A szabályreferencia és a rögzített skálázás változatlan.

## Új adatverzió és a v1 megőrzése

Az adatváltozás oka kizárólag az igazolt adatszivárgás. Nem történt
modelltanítás, modellválasztás vagy modellteszt-eredményen alapuló hangolás.
A seed, a 200 × 120 s méret, az 50 ms-os mintavétel és a zajamplitúdók
azonosak a v1-ével. A CSV nyers mintasémája változatlan, a `runs.csv` bővült
a `profile_seed` mezővel; a sémaverzió `dataset-v2`, a generátor `synthetic-v2`.

A v1 adatkönyvtára és lezárása érintetlen, összes adat-checksuma és a lezárt
manifest checksumja újraellenőrizve. A `docs/evidence/issue-3/` gyökerének
régi fájljai, `SHA256SUMS` állománya és a régi konfiguráció nem módosultak.
A v1 történeti reprodukálása a `5377292` commitból lehetséges, de a v1 teszt
nem használható szivárgásmentes végső értékelésként. Az új `verify`/`seal`
nem hitelesíti újra a történeti v1 sémát szivárgásmentesként; a csak olvasó
`audit-overlap` diagnosztikára elfogadja.

## Teljes méretű v2 ellenőrzése, lezárás előtt

Az első teljes generálás jelentését lezárás előtt ellenőriztem:
`coverage_ok=true`, `coverage_errors=[]`. Minden típusból 28/6/6 menet,
összesen 100/100 kezdeti fokozat. Minden részhalmazban jelen van mindhárom
osztály, mindkét váltási irány és az összes előírt határeset. A 476200 ablak
teljes összevetése mindhárom párban **0** másolatot mutatott, a zajos
változatokkal együtt. Részletes számlálók: `report.json`.

| Részhalmaz | Menet / család | Minta | Ablak | Visszaváltás | Tartás | Felváltás |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tanító | 140 / 70 | 336000 | 333340 | 1496 | 330347 | 1497 |
| Validációs | 30 / 15 | 72000 | 71430 | 284 | 70854 | 292 |
| Teszt | 30 / 15 | 72000 | 71430 | 296 | 70833 | 301 |

Új dataset-verzióazonosító:
`ef6f8048efec22e32cc44fd4c58b08052359ab6880ee52c2257e3da59f27ba4a`.
Az új teszt- és ablak-checksumokat a külön v2 `test-lock.json` őrzi.

## Reprodukálás

A repository gyökeréből, új kimeneti könyvtárakba:

```bash
python3 -m unittest discover -s tests -v
python3 -m pc.dataset generate data/generated/dataset-v2 --config config/dataset-v2.json
python3 -m pc.dataset generate data/generated/dataset-v2-repeat --config config/dataset-v2.json
diff -r data/generated/dataset-v2 data/generated/dataset-v2-repeat
cat data/generated/dataset-v2/report.json
python3 -m pc.dataset seal data/generated/dataset-v2
python3 -m pc.dataset verify data/generated/dataset-v2
```

A teljes méretű második generálás összevetése és a lezárt v2 auditja a
`reproduction.log` és `verify.log` fájlban rögzített. Nagy generált adatok
továbbra sem kerülnek Gitbe. A v2 kis bizonyítékfájljainak checksumait a
helyi `SHA256SUMS` őrzi, a régi v1 ledger módosítása nélkül.

## Elutasítások, akadályok és korlátok

Elutasított finding nincs. Az egyetlen P1 findingot teljes egészében
elfogadtam; nyitott végrehajtási akadály nincs. A review-visszaellenőrzést
a reviewer végzi, threadet nem zártam le.

A profilok továbbra is szintetikus laborjelek, nem reprezentatív közúti
adatok; az osztályeloszlás erősen tartásdomináns. Az egzakt másolatok kizárása
nem bizonyítja a hasonló laborprofilok statisztikai függetlenségét és nem
INT8-kvantálás utáni egyezésvizsgálat. A lezárt teszt kizárólag végső
értékelésre használható, modellválasztásra/normalizálás illesztésére/
INT8-kalibrációra nem. Az audit a lenyomatok számával növekvő memóriát használ.
