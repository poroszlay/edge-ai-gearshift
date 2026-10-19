# Reprodukálható szintetikus adatkészlet (#3)

A `pc.dataset` a [közös adatszerződés](data-contract.md) szerinti meneteket
és modellbemeneteket állítja elő. Minden döntést a meglévő
`pc.reference.label_window` ad; a generátor nem vezet be másik címkézőt.
Python 3.10 vagy újabb szükséges, külső csomag és hardver nélkül.

Az aktuális adat-/generátorverzió **dataset-v2 / synthetic-v2**. A v1-ben
külön családok között is ugyanazon periodikus jel fáziseltolásai szerepeltek;
ez azonos modellablakokat juttatott külön részhalmazokba. A v1 lezárt tesztje
emiatt nem alkalmas a referencia megtanulásának végső értékelésére. A régi
adatok és a `docs/evidence/issue-3/` gyökerében megőrzött manifest, lezárás és
hash-ek változatlanok. A v2 külön könyvtárban és új azonosítóval készül;
az ok és az új eredmények a [v2 ellenőrzési jegyzőkönyvében](evidence/issue-3/v2/verification.md)
szerepelnek. A seed, a méret és a zajamplitúdók nem változtak.

## Reprodukálás és lezárás

A repository gyökeréből, új kimeneti könyvtárakba:

```bash
python3 -m unittest discover -s tests -v
python3 -m pc.dataset generate data/generated/dataset-v2 --config config/dataset-v2.json
python3 -m pc.dataset generate data/generated/dataset-v2-repeat --config config/dataset-v2.json
diff -r data/generated/dataset-v2 data/generated/dataset-v2-repeat
cat data/generated/dataset-v2/report.json
python3 -m pc.dataset seal data/generated/dataset-v2
python3 -m pc.dataset verify data/generated/dataset-v2
python3 -m pc.dataset audit-overlap data/generated/dataset-v2
```

A `generate` még nem zárja le a tesztadatot. Előbb ellenőrizni kell a
`report.json` osztály-, esemény- és határeset-lefedését. A `seal` ezt követően
újraellenőrzi az összes ellenőrzőösszeget, a menetfelosztást, időrendet,
állapotátmenetet, címkét, ablakindexet és a jelentést. Hiányos lefedésből nem
készül `test-lock.json`. A részhalmazok között azonos tényleges modellbemenet
szintén lezárási hiba; a `verify` újraszámolja ezt az ellenőrzést is.
A `verify` lezárás előtt és után is futtatható;
a lezárás tényét külön jelzi, és nem módosít adatot.

A kimeneti könyvtár nem létezhet a generáláskor. A lezárási fájl kizárólag
újként hozható létre; nincs felülíró kapcsoló. Sikertelen generálás részleges
könyvtárat hagyhat hátra; csak teljes, manifesttel rendelkező és sikeresen
ellenőrzött adat használható. Új próbához új könyvtárat kell választani.

A lezárt teszt kizárólag végső értékelésre használható. Modellválasztás a
validációs részen történik; normalizálási paraméterek és INT8-kalibráció
kizárólag a tanítórészből származhatnak. A rögzített skálázás nem illeszt
paramétert. Teszteredmény alapján ugyanaz a lezárt tesztadat nem módosítható;
egy későbbi generátorváltozás új verzióazonosítót kap, a régi manifest és
lezárás megőrzendő. A fájlok közvetlen olvasását az eszköz nem tudja
hozzáférés-szabályozással korlátozni; a fogyasztók kötelessége a szerepek
betartása.

## Konfiguráció és profilok

A teljes kiinduló konfiguráció: [`config/dataset-v2.json`](../config/dataset-v2.json).
A `--config` JSON-objektum elhagyott mezői a `Config` alapértékeit kapják;
a feloldott konfiguráció mindig bekerül a kimenetbe. Ismeretlen mező vagy
érvénytelen érték hibát okoz.

| Mező | Alapérték, jelentés |
| --- | --- |
| `seed` | 20261019, nemnegatív egész |
| `duration_s` | 120, pozitív egész másodperc |
| `runs_per_type` | 40, az alap- és zajos menetek együttes száma típusonként |
| `noisy_variants` | 1, egy alapmenethez tartozó zajos változatok száma |
| `noise_v`, `noise_u`, `noise_s` | 0.15 km/h, 0.005, 0.03 százalékpont; véges, nemnegatív zajamplitúdó |
| `period_samples` | 240, legalább 40 egész minta; az első négy profil periódusának alapértéke |

Típusonként a menetcsaládok száma `runs_per_type / (noisy_variants + 1)`.
Ez 20 pozitív egész többszöröse kell legyen: így a 70/15/15 arány pontos,
és az összes menet fele mindkét fokozatból indul. Az alapméret 100
alapmenet és 100 zajos változat, összesen 200 menet, 40 mind az öt típusból.

A profilok periodikus, determinisztikus laborjelek. A v2 minden családhoz
saját gyökér-realizációt rendel, a seed és családazonosító SHA-256 hash-éből
képzett `profile_seed` alapján; ennek meghatározása nem függ a részhalmaztól.
A család minden leszármazottja ugyanazt a gyökérprofilt kapja.
Az első négy profil `q` háromszögjelének tartománya 0..1.
Az alábbi alapformákból készülnek az önálló realizációk:

| `kind` | `v`, `u`, `s` |
| --- | --- |
| `acceleration` – gyorsítás | `12+52q`, `0.55+0.3q`, `0` |
| `cruise` – egyenletes haladás | `35+1.5q`, `0.05+0.9q`, `0` |
| `uphill` – emelkedő | `20+40q`, `0.5`, `2+8q` |
| `deceleration` – lassítás | `64-52q`, `0.1+0.1q`, `-2` |
| `threshold` – küszöbkörnyék | 200 mintás lépcsős sebességsorozat az adott család fel-/visszaváltási küszöbéhez viszonyítva |

A küszöbprofil kanonikus példájának (`profile_seed=0`, `u=0.2`, `s=0`)
sebessége a 0-tól számozott periódusban:
0..29: 34; 30..34: 46; 35..50: 15; 51..55: 46; 56..59: 15;
60..89: 24; 90..119: 23.8; 120..149: 34; 150..179: 34.2;
180..189: 24.2; 190..199: 24 km/h. Ez küszöbegyezést, közeli
értékeket és a váltás utáni tiltás alatt ellentétes igényt is előállít.

A családok fázisa egyenletesen elosztott, seedelt eltolással. Ezen túl a v2
minden családhoz külön mintáz periódust a `period_samples` 75..125%-ának
egész tartományából, legalább 40 mintával; sebességszorzót 0.85..1.1,
igényszorzót 0.85..1.05, emelkedőeltolást -2..2 (1/128 lépésben), és az
emelkedős profilhoz 0.75..1 emelkedőszorzót. A gyorsítás/egyenletes/lassítás
sebességét és igényét a megfelelő szorzó módosítja; az emelkedőeltolás
hozzáadódik az alapprofilhoz. Az emelkedős profil sebesség- és igényszorzót,
valamint emelkedőszorzót kap. Ezek fizikai bemeneti változatosságot adnak;
a családazonosító és a profilseed nem kerül a modellbemenetbe.

A küszöbprofil családonkénti igénye 16..192 közötti egész /256, emelkedése
a fenti 1/128 lépésű eltolás. Az alap sebességsorozat minden értéke az adott
család felső küszöbe és 34 km/h különbségével tolódik el. A binárisan pontos
paraméterek megőrzik a valódi küszöbegyezést. A profilképlet itt csak jelet
állít elő, minden tanítási címkét továbbra is a szabályreferencia ad.

Egy család minden változatának profilseedje, fázisa és kezdeti fokozata azonos;
új fázis- vagy zajváltozat sem tekinthető új, külön felosztható gyökérprofilnak.
A teljes menetek eltérősége önmagában nem elégséges ellenőrzés: az export,
ellenőrzés és lezárás minden részhalmazpár tényleges modellablakait is összeveti.
A zaj külön, a seedből és menetazonosítóból SHA-256-tal magozott
`random.Random` példányból származik. A mintánként és jelenként független,
egyenletes `[-amplitúdó,+amplitúdó]` zaj után a szintetikus jel a megengedett
tartományra korlátozott. Ez a jel előállításának része; a hibás bemenetek
nem kerülnek automatikus javításra. Minden zajos változat állapotát és címkéit
a saját zajos jeleiből, újra a szabályreferenciával állítjuk elő.

## Felosztás, idő és döntés előtti állapot

A `make_plan(Config)` kizárólag menetleírókból készít felosztást, még
mintagenerálás és ablakolás előtt. Típusonként a családok SHA-256 szerint
seedelt sorrendben 70/15/15 arányban kerülnek a részhalmazokba. Egy alapmenet
és minden zajos változata oszthatatlan család. Alapértéken típusonként
14/3/3 család, 28/6/6 menet, összesen 140/30/30 menet keletkezik.
A menetazonosítók minden részhalmazban különböznek.

A 120 s intervallum `[0,120000)` ms: 2400 minta, az utolsó időbélyeg
119950 ms. A belső eltelt idő egész milliszekundumban számolódik; a CSV
`tau` mezője másodperc. Kezdetben `tau=10`, a fokozat családonként felváltva
1 és 2. Az első 19 mintának nincs teljes ablaka, így státusza `warmup`,
címkéje üres, váltás nem történik. Az első döntés a 20. mintánál, 950 ms-nál
keletkezik. Ezután minden mintánál a legutóbbi 20 nyers minta kerül a
referenciához. A sor mindig a döntés **előtti** `g/tau` értéket tartalmazza.

Váltás után a következő sorban az új fokozat és `tau=0.05` szerepel;
egyébként az eltelt idő 50 ms-mal nő. A nyers `tau` nem telítődik.
A modellablak csak múltbeli és jelenlegi mintát tartalmaz, időrendben,
mintánként `[v/80,u,s/10,g-1,min(tau,10)/10]` sorrendben, 100 értékre lapítva.
Érvényesség-ellenőrzés előzi meg a skálázást. Menethatáron az ablak nem
folytatható; az `iter_windows` ilyen bemenetre hibát jelez. A visszajátszott
állapotot a fogyasztó modell kimenete nem módosíthatja.

Nyilvános Python-interfész:

```python
from pc.dataset import Config, generate_run, iter_windows, make_plan

config = Config()
plan = make_plan(config)
run = generate_run(plan["train"][0], config)
for window in iter_windows(run):
    assert len(window.features) == 100
    # window: run_id, window_id, timestamp_ms, features, action, class_index
```

Az `iter_windows` nyers minták iterálható sorozatát fogadja, és változtathatatlan
`Window` eredményeket ad; nem módosítja a bemenetet. A `RunSpec` mezői:
`run_id,family_id,kind,initial_gear,variant,phase_samples,profile_seed`. A 0-s
profilseed a kanonikus, kézzel ellenőrizhető alapformát választja; a `make_plan`
a családonként seedelt realizációkat használja. A `generate_run`
egy teljes menet sorait adja vissza. A nyers adatok meneteként kerülnek memóriába;
az átfedés-audit ezen túl az egyedi ablakok SHA-256 ujjlenyomatait és első
azonosítóit őrzi, tehát memóriája az egyedi ablakok számával nő. Nem tárolja
a teljes ablakhalmaz 100 elemű bemeneteit.

## Fájlok és CSV-séma

UTF-8, fejléc, vesszőelválasztás, pont tizedesjel, LF sorvég. Nincsenek
abszolút útvonalak vagy futási időbélyegek a kimenetben.

| Fájl | Tartalom |
| --- | --- |
| `config.json` | Teljes feloldott generálási konfiguráció |
| `runs.csv` | `split,run_id,family_id,kind,initial_gear,variant,phase_samples,profile_seed`; `variant=0` az alapmenet |
| `train.csv`, `validation.csv`, `test.csv` | `run_id,timestamp_ms,v,u,s,g,tau,action,class_index,status` |
| `*-windows.csv` | `window_id,run_id,start_timestamp_ms,timestamp_ms,action,class_index` |
| `invalid.jsonl` | Kilenc külön hibás ablak, hibastátusz és `null` címkék |
| `report.json` | Részhalmazonkénti méret, típusok, osztályok, események és határesetek; `overlap`: minden részhalmazpár tényleges bemenetegyezései és példái |
| `manifest.json` | Sémaverzió, konfiguráció, generátor-/címkézőverzió és forrás-SHA-256, Python-verzió, minden adatfájl SHA-256 értéke, teljes `dataset_id` |
| `test-lock.json` | Csak sikeres lezárás után: dataset-verzióazonosító, manifest-, teszt- és tesztablak-SHA-256, felhasználási tilalmak |

A nyers mezők egységei és tartományai a [szabályreferencia szerződését](rule-reference.md)
követik. `timestamp_ms`, `g`, `action`, `class_index` egész; `v,u,s,tau`
szám. `status=ok` esetén az `action` -1/0/+1, az osztályindex 0/1/2.
Az első 19 sorban `status=warmup`, mindkét címkemező üres. A CSV-ből
beolvasott számmezőket a fogyasztó a dokumentált típusra alakítja, és csak
`ok` sorhoz tartozó teljes ablakot használhat modellbemenetként.

Az ablakfájl a nyers adathoz tartozó index, nem 100 elemű feature-másolat.
`window_id=run_id:mintaindex`, az első index 19. Minden index egyetlen menet
20 sorát jelöli, végpontjai között 950 ms van. Menetenként 2381,
összesen 476200 átfedő ablak keletkezik; ezek nem független menetek.

A hibás állomány szabványos JSON Lines. A NaN és ±végtelen a
`{"$float":"nan"}`, `{"$float":"inf"}`, `{"$float":"-inf"}` taggel
szerepel, így nincs nem szabványos JSON-szám. A nyilvános
`read_invalid_cases(Path(...))` visszaállítja a nem véges számokat.
Ezek kizárólag hibakezelési tesztek: nem tartoznak a három érvényes
adat-részhalmazba, és soha nincs érvényes döntési címkéjük.

## Lefedési kapu és korlátok

Minden részhalmazban jelen kell lennie mind az öt menettípusnak, mindkét
kezdeti fokozatnak, mindhárom osztálynak és mindkét váltási iránynak.
Az eseményszám a nemnulla referenciadöntések száma, az utolsó sor döntésével
együtt; az utolsó döntéshez már nincs következő sor ugyanabban a menetben.
Külön számlált a fel-/visszaváltási küszöbegyezés és a 0.25 km/h-n belüli
nem egyenlő érték, a `tau=0.95`, `tau=1`, nyers `tau>10`, valamint a
tiltás miatt elnyomott fel- és visszaváltási igény. Küszöböt csak az adott
fokozatban, feloldott tiltás mellett számolunk. Tiltott igénynél az eredeti
ablak másolatában kizárólag a legutolsó `tau` lesz 1; az ellentétes döntést
itt is a meglévő referencia adja. Ez diagnosztika, nem új tanítási címke.

Bármely hiány lezárási hiba, rövid vagy eltérően paraméterezett generálásnál
is. Az egyedi profilokat és a zajt a teszt lezárása előtt kell elfogadni;
a generátor nem keres automatikusan a lezárt teszten jobban teljesítő seedet.

Az `overlap.matching_windows` mindhárom párnál nullát kell mutasson.
A későbbi részhalmaz minden ablaka egyszer számít, ha legalább egy korábbi
részhalmazbeli másolata van. A lenyomat a 100 skálázott modellérték
big-endian IEEE-754 binary64 sorozatának SHA-256 értéke, a -0/+0 egységesítésével.
Nincs benne menet-/ablakazonosító, időbélyeg, címke vagy más metaadat.
Ugyanazon részhalmazon belüli ismétlődés megengedett; részhalmazok közötti
egyezés minden osztálynál hiba. A vizsgálat a zajos változatokra is kiterjed.

A kizárólag olvasó `audit-overlap KÖNYVTÁR` a három nyers CSV-ből újra
ellenőrzi és skálázza az ablakokat, majd JSON-jelentést ad; egyezésnél
1-es, egyezés nélkül 0-s kilépési kóddal. Ez szándékosan önálló bemeneti
átfedésvizsgálat, nem helyettesíti a manifest-, állapot- és címkeauditot.
A v1 diagnosztikájára is használható, semmit nem zár újra és nem ír át:

```bash
python3 -m pc.dataset audit-overlap data/generated/dataset-v1
```

A régi verzió eredeti reprodukálásához a `5377292` commit kódját és a régi
`config/dataset-v1.json` konfigurációt kell használni külön checkoutban.
A v2 `verify`/`seal` nem fogadja el a történeti v1 sémát új, szivárgásmentes
tesztkészletként; a v1 eredeti lezárása és checksumai ettől megmaradnak.

A profilok egyszerű, ismétlődő laborjelek, a küszöbprofil szándékosan ugrásos.
Nem járműdinamikai modell és nem reprezentatív közúti adathalmaz. Az osztályok
erősen kiegyensúlyozatlanok; az átfedő ablakok eseményei ritkák. A referenciával
való egyezés a **referencia megtanulását** méri. A bájtszintű reprodukálást
azonos forrásverzióval és Python-verzióval ellenőrizzük; más futtatókörnyezetben
külön ellenőrzés szükséges. A manifest önmagát nem hash-eli: annak hash-ét a
lezárás rögzíti, a kis bizonyítékfájlokat Git őrzi. A teljes generált adatok
a Gitből kizárt `data/generated/` könyvtárban maradnak.
Az egzakt ablakmásolatok kizárása nem bizonyítja a hasonló laborprofilok
statisztikai függetlenségét, és nem jelent kvantálás utáni azonosságvizsgálatot.
