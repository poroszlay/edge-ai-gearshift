# Az Edge AI fokozatváltási labor teljes útmutatója

Ez a dokumentum a projekt céljától a működő alkalmazás használatáig vezet
végig. Nem feltételez gépi tanulási vagy mikrokontrolleres előismeretet.
Először a fogalmakat és az összefüggéseket magyarázza el, majd bemutatja
az indítást, az alkalmazás részeit és az eredmények értelmezését.

## Tartalomjegyzék

1. [Mire való a projekt, és miért hasznos?](#cel)
2. [Miből áll egy menet és egy bemeneti ablak?](#ablakok)
3. [Honnan tudjuk, mi lenne a helyes döntés?](#szabalyreferencia)
4. [Hogyan készül az adatkészlet?](#adatkeszlet)
5. [Hogyan tanul a modell?](#tanitas)
6. [Hogyan kerül a modell az ESP32-re?](#beagyazas)
7. [Mi történik egy alkalmazásfutás közben?](#adatfolyam)
8. [Mit mérünk, és mit jelentenek az eredmények?](#meresek)
9. [A frontend telepítése és indítása](#frontend)
10. [A szimulátor indítása külön folyamatként](#tcp)
11. [Futtatás ESP32-vel](#esp32)
12. [Az alkalmazás részei és feladataik](#modulok)
13. [Mentés és gyakori indítási problémák](#hibakereses)
14. [Alapfogalmak szótára](#fogalmak)

<a id="cel"></a>

## 1. Mire való a projekt, és miért hasznos?

A projekt azt vizsgálja, hogy egy kis neurális hálózat képes-e megtanulni
egy előre meghatározott fokozatváltási szabály viselkedését, és hogy ez a
hálózat egy ESP32 mikrokontrolleren mennyi idő és memória felhasználásával
futtatható. Az ESP32 egy kis számítógépet tartalmazó lapka; a panel ennek
USB-n csatlakoztatható fejlesztői változata. Sokkal szűkösebb erőforrásai
vannak, mint egy asztali PC-nek.

Képzelj el egy leegyszerűsített, kétfokozatú hajtást. Ismerjük a sebességet,
a gázpedálállást, az emelkedőt, az aktuális fokozatot és az utolsó váltás óta
eltelt időt. Ezek alapján háromféle döntés születhet:

| Döntés | Programbeli név | Jelentés |
| --- | --- | --- |
| Visszaváltás | `downshift` | A második fokozatból az elsőbe kellene váltani. |
| Tartás | `hold` | Az aktuális fokozat maradjon. |
| Felváltás | `upshift` | Az első fokozatból a másodikba kellene váltani. |

A projekt teljes kísérleti láncot valósít meg:

```text
Szintetikus menetek előállítása
  → elvárt döntések hozzárendelése szabályokkal
  → modell tanítása PC-n
  → átalakítás mikrokontrolleren futtatható formára
  → futtatás ESP32-n
  → döntések, időigény és memóriaigény ellenőrzése
  → megjelenítés és export a PC-s felületen
```

Ez azért hasznos, mert a gépi tanulás beágyazott alkalmazásánál a modell
elkészítése csak egy lépés. A bemenetet mindenhol ugyanúgy kell értelmezni,
a modellnek el kell férnie az eszközön, és az eredménynek időben kell
elkészülnie. A projekt ezeket együtt, megismételhető kísérlettel vizsgálja.
Az „Edge AI” arra utal, hogy a tanított modell az adatfeldolgozáshoz közeli
kis eszközön fut, nem egy távoli felhős szerveren.

**A jelenlegi alkalmazás laboratóriumi bemutató.** A bemenetek mesterségesen
generált jelek, és a döntéseket egy egyszerű szabályrendszerhez hasonlítjuk.
A projekt nem igazol járműves optimalitást, energiamegtakarítást vagy közúti
alkalmazhatóságot. A modell döntéseit megfigyeljük és mérjük; nincs tényleges
váltó, amelyet a bemutató vezérelne.

Felmerülhet: ha már ismerjük a szabályt, miért tanítunk rá modellt? Ebben a
laborban a szabály ismert viszonyítási pont: pontosan megmondható, mikor
hibázik a tanult modell. Az egyszerű szabály közvetlen programozása is
lehetséges lenne. A kísérlet értéke a **referencia megtanulásának**, az
eszközre átvitelnek és a mérésnek a bemutatása; önmagában nem bizonyítja,
hogy itt a neurális hálózat jobb megoldás a szabálynál.

<a id="ablakok"></a>

## 2. Miből áll egy menet és egy bemeneti ablak?

### Egy minta: pillanatfelvétel az állapotról

Egy **minta** az öt bemeneti jel egy adott időpontban felvett értéke.
A projekt 50 milliszekundumonként készít mintát, tehát másodpercenként
húszszor. Az időbélyeg azt mondja meg, mikor készült a minta.

| Jel | Jelentés | Egység és megengedett érték | Példa |
| --- | --- | --- | --- |
| `v` | Sebesség | 0–80 km/h | `40` |
| `u` | Gázpedálállás | 0–1; a 0,2 itt 20%-os állás | `0.2` |
| `s` | Emelkedő | −10 és +10 közötti százalékérték | `0` sík úton |
| `g` | Aktuális fokozat | Pontosan 1 vagy 2 | `1` |
| `tau` | Az utolsó váltás óta eltelt idő | Nemnegatív másodperc | `3` |

Egy ilyen pillanatfelvétel tömören: `[40, 0.2, 0, 1, 3]`.
A sorrend mindig `[v, u, s, g, tau]`. A számok sorrendjének felcserélése
megváltoztatná a jelentésüket, akkor is, ha továbbra is öt számot küldenénk.

A **menet** egymáshoz tartozó minták időrendi sorozata, például egy
kétperces gyorsítási forgatókönyv. Minden menetnek külön azonosítója van.

### Egy ablak: húsz egymást követő pillanatfelvétel

Az **ablak** a menet egy rövid, összefüggő részlete. Ebben a projektben
mindig húsz egymást követő mintát tartalmaz, a legrégebbitől a legújabbig.
A modell egyszerre ezt a húsz mintát kapja meg, és az ablak végén fennálló
helyzethez ad egyetlen döntést.

```text
Minta sorszáma:     1   2   3  ...  19  20  21  22
Első ablak:       [---------------------]
Második ablak:        [---------------------]
Harmadik ablak:           [---------------------]
```

Az első ablak az 1–20., a második a 2–21., a harmadik a 3–22. mintát
fogja össze. Ezt **csúszóablaknak** nevezzük: új minta érkezésekor a
legrégebbi kiesik, az új bekerül. A szomszédos ablakok tehát 19 közös mintát
tartalmaznak; nem húsz teljesen új mintából áll minden új bemenet.

Az első húsz időbélyeg lehet `0, 50, 100, …, 950` ms. Így az ablak első
és utolsó mintája között **950 ms** telik el. Gyakran közel egy másodperces
előzményként gondolhatunk rá, de a pontos időbeli átfogás 0,95 másodperc.
Az első 19 minta után még nincs teljes ablak. Egy 120 másodperces,
2400 mintás menetből ezért `2400 − 20 + 1 = 2381` teljes ablak készül.

### Mire jó az ablak?

Egyetlen pillanatfelvétel csak a jelenlegi értékeket adná át. Az ablak
rövid előzményt is biztosít: például láthatóvá teszi, hogy a sebesség éppen
emelkedik vagy csökken. A projekt szabályreferenciája konkrétan az utolsó
öt minta sebességét, gázpedálállását és emelkedőjét átlagolja. Ehhez is
előzményekre van szükség. A modell mind a húsz mintát megkapja, tehát
szélesebb előzményből tanulhatja meg a referencia döntését.

A húszmintás méret rögzített projektbeli döntés; a jelenlegi kísérlet nem
bizonyítja, hogy minden feladathoz ez lenne az ideális ablakhossz.
Csak jelenlegi és múltbeli adatok használhatók, jövőbeli minták nem.
Két külön menetből nem készülhet közös ablak.

### Miért van száz modellbemenet, ha csak öt jel van?

Mert mind az öt jel húsz időpontból szerepel: `20 × 5 = 100` szám.
A modell előtt a kétdimenziós, húszsoros táblát egyetlen számsorrá alakítjuk:

```text
[v1, u1, s1, g1, tau1, v2, u2, s2, g2, tau2, …, v20, u20, s20, g20, tau20]
```

Ez a **lapítás**. Az időbeli sorrend a számok helyében marad meg.
A modellbemenetbe az azonosítók és az időbélyegek nem kerülnek bele;
az időbélyegek a helyes mintaköz ellenőrzéséhez szükségesek.

A felület **Ablakok JSONL** mezőjében egy már elkészített ablakfájlt
választhatsz. A JSONL szöveges formátum: soronként egy JSON-objektumot,
itt egy teljes ablakot tartalmaz. Az objektumban szerepel az ablak és a
menet azonosítója, a húsz időbélyeg és a húsz ötelemű minta. A fájl tehát
bemeneti adat, nem maga a tanított modell. Üres mező esetén a felület
demoablakokat készít, ezért az első próbához nem kell saját fájlt írnod.

<a id="szabalyreferencia"></a>

## 3. Honnan tudjuk, mi lenne a helyes döntés?

A **szabályreferencia** egy determinisztikus Python-függvény: azonos érvényes
ablakra mindig ugyanazt a döntést adja. Ez szolgáltatja a tanításhoz az
elvárt választ, más néven a **címkét**. Itt a „helyes” azt jelenti, hogy a
laborban elfogadott szabállyal egyezik, nem azt, hogy valódi közúton optimális.

A referencia először ellenőrzi a teljes ablakot. Hiányzó jel, hibás
mintaszám, nem megfelelő mintaköz vagy tartományon kívüli érték esetén
hibát ad, nem talál ki döntést. Ezután:

1. Kiszámítja az utolsó öt minta sebességének, gázpedálállásának és
   emelkedőjének átlagát.
2. Meghatározza a felváltási küszöböt:
   `v_up = 30 + 20 × átlag(u) + 0,5 × átlag(s)` km/h.
3. A visszaváltási küszöb ennél 10 km/h-val alacsonyabb: `v_down = v_up − 10`.
4. Ha a legutóbbi mintában a váltás óta még nem telt el 1 másodperc,
   tartást kér.
5. Egyébként első fokozatban a felső küszöb fölött felváltást, másodikban
   az alsó küszöb alatt visszaváltást kér. Minden más esetben tartást ad.

**Konkrét példa:** az utolsó öt mintában a gázpedál átlaga 0,2, az emelkedő
0%, a sebesség átlaga 40 km/h. A felső küszöb `30 + 20 × 0,2 = 34 km/h`,
az alsó `24 km/h`. Ha az aktuális fokozat 1 és `tau = 3 s`, a döntés
felváltás, mert 40 nagyobb 34-nél. Ha ugyanitt `tau = 0,5 s`, a döntés
tartás, mert a váltás utáni egy másodperces tiltás még érvényes.
Második fokozatban, 20 km/h átlagsebességnél és feloldott tiltásnál
visszaváltás lenne az eredmény.

A két eltérő küszöb közötti sávot **hiszterézisnek** nevezzük: segít
elkerülni, hogy egyetlen küszöb körüli kis ingadozás oda-vissza váltást
kérjen. Az egy másodperces tiltás külön védelem a túl sűrű váltás ellen.
Pontosan a küszöbön tartás történik; pontosan egy másodpercnél a tiltás
már feloldódik.

Két külön „referencia” fordul elő a projektben:

- A **szabályreferencia** azt mondja meg, mit szeretnénk megtanítani.
- A **PC-s modellreferencia** ugyanazt a tanított INT8-modellt futtatja a
  PC-n, amely az ESP32-re kerül. Azt ellenőrizzük vele, hogy az eszközön
  ugyanaz a számítás történik-e.

A modell tehát egyezhet tökéletesen a PC-s modellreferenciával úgy is,
hogy mindkét helyen eltér a szabályreferenciától. Az egyik a portolás,
a másik a tanulás minőségéről szól.

<a id="adatkeszlet"></a>

## 4. Hogyan készül az adatkészlet?

### Mesterséges menetek és elvárt válaszok

Az adatgenerátor öt menettípushoz állít elő jeleket: gyorsítás, egyenletes
haladás, emelkedő, lassítás és váltási küszöbök környéki helyzetek.
Ezek egyszerű laborprofilok, nem mért közúti menetek és nem részletes
járműdinamikai szimulációk.

Az alapkonfiguráció 200 darab, egyenként 120 másodperces menetet készít.
Az alapmenetek mellett kisebb véletlen eltéréseket tartalmazó, zajos
változatok is vannak. A zaj célja, hogy ne minden példa tökéletesen sima
jel legyen. A **seed** egy rögzített kezdőérték a véletlenszám-generáláshoz:
azonos forráskóddal, konfigurációval és megfelelő környezettel a kísérlet
megismételhető.

A generátor teljes ablakonként meghívja a szabályreferenciát. Így keletkezik
a tanítási pár: **bemeneti ablak + elvárt döntés**. A generált menetben a
referencia váltási döntése a következő mintában módosítja a fokozatot,
és frissül a váltás óta eltelt idő is. Az adatgenerálásnak ez része;
a későbbi mérési visszajátszás már rögzített ablakokat használ, ott a modell
döntése nem írja át az állapotot.

### Miért kell tanító-, validációs és teszthalmaz?

Ha csak a tanításhoz használt példákon vizsgálnánk a modellt, nem derülne
ki, hogy új helyzetekben is működik-e. Ezért három rész készül:

| Részhalmaz | Arány; menetszám az alapkonfigurációban | Mire használjuk? |
| --- | --- | --- |
| Tanító (`train`) | 70%; 140 menet | Ezekből a példákból módosulnak a modell súlyai. Az INT8-kalibráció is innen kap adatot. |
| Validációs (`validation`) | 15%; 30 menet | Ezen választjuk ki a mentett modellváltozatot és hasonlítjuk össze a jelölteket. |
| Lezárt teszt (`test`) | 15%; 30 menet | A már kiválasztott, befagyasztott modell végső értékelésére szolgál. |

A felosztás **teljes menetcsaládok szerint, az ablakok képzése előtt**
történik. Egy alapmenet és zajos változatai együtt maradnak. Ez különösen
fontos a csúszóablakok miatt: a szomszédos ablakok szinte ugyanazok.
Ha véletlenszerűen szórnánk őket a három halmazba, a modell a tanítás során
majdnem láthatná a vizsgapéldákat is. Ez az **adatszivárgás**, amely
túlzottan kedvező eredményt mutathatna.

A jelenlegi `dataset-v2` ellenőrzése a részhalmazok közötti pontos
modellbemenet-másolatokat is kizárja. A korábbi v1 adatkészletnél ilyen
átfedés előfordult, ezért annak tesztje nem alkalmas végső értékelésre.
A pontos másolatok kizárása azonban nem teszi a mesterséges profilokat
reprezentatív közúti adathalmazzá.

A lezárás ellenőrzi a címkéket, a felosztást, az osztályok és határesetek
jelenlétét, és rögzíti az állományok ellenőrzőösszegeit. A teszteredmény
ismeretében nem hangoljuk vissza ugyanarra a teszthalmazra a modellt.
A generált nagy adatfájlokat a repó nem tárolja; a konfigurációk,
előállító kód és kis ellenőrzési állományok viszont megmaradnak.

<a id="tanitas"></a>

## 5. Hogyan tanul a modell?

### Mit jelent itt a modell?

A modell egy számszerű függvény: száz bemeneti számból három kimeneti
értéket számol. Belső, tanulható paraméterei a **súlyok** és az
**eltolások**. A tanítás ezeket módosítja úgy, hogy a bemeneti ablakhoz
lehetőleg a szabályreferencia által adott osztályt válassza.
Ez **felügyelt tanulás**, mert minden tanítópéldához ismert az elvárt válasz.

A jelenlegi befagyasztott modell egy **MLP**, azaz többrétegű perceptron,
`100 → 64 → 32 → 3` felépítéssel:

- **100 bemenet:** a húsz minta öt-öt skálázott értéke.
- **64 és 32 rejtett egység:** egymás után elvégzett tanulható számítások.
  Minden egység súlyozott összeget és eltolást számol. A rejtett rétegek
  ReLU művelete a negatív eredményt nullára cseréli, a pozitívat megtartja;
  ez teszi lehetővé a puszta lineáris összefüggésnél összetettebb viselkedést.
- **3 kimenet:** a visszaváltás, tartás és felváltás értéke, ebben a sorrendben.
  A softmax az FP32-háló kimenetét 0 és 1 közötti, összesen 1-et adó
  osztályértékekké alakítja. A legnagyobb értékű osztály lesz a döntés.

Szemléltető kimenet lehet `[0,05; 0,15; 0,80]`: ekkor a felváltást
választjuk. Ez nem mért projektadat. A nagyobb érték nem garancia a helyes
válaszra. Az ESP32-s export ezeket kvantált egész kódokkal reprezentálja.
A háló a lapított ablakot egyben értékeli; a korábbi ablakhívások között
nem épít külön tanulható memóriát.

### Miért skálázzuk a jeleket?

A nyers sebesség akár 80, a gázpedál legfeljebb 1, az eltelt idő pedig
10 másodperc fölé is nőhet. A rögzített skálázás kezelhetőbb tartományba
hozza őket, és közös jelentést biztosít a tanítás és a firmware számára:

```text
[v/80, u, s/10, g−1, min(tau, 10)/10]
```

Például a `[40, 0.2, 0, 1, 3]` minta átalakítva
`[0.5, 0.2, 0, 0, 0.3]`. A tíz másodpercnél hosszabb váltásmentes idő
ugyanúgy 1 lesz: a modell nem különbözteti meg például a 12 és a 30
másodpercet. Ez az előre elfogadott bemeneti szerződés része.
Előbb mindig az érvényességet vizsgáljuk; a skálázás nem javítja meg a
hibás bemenetet.

### A tanítás menete lépésről lépésre

1. A program betölti a tanítóablakokat és címkéiket, ellenőrzi az
   adatkészlet azonosítóját, és előállítja a százszámos bemeneteket.
2. Létrehozza a hálózatot kezdeti súlyokkal. Ekkor még nem tanulta meg a feladatot.
3. A példákat megkevert sorrendben, kisebb csoportokban adja a hálónak.
   Ezt a csoportot **tanítási batchnek** nevezzük; a jelenlegi konfigurációban
   legfeljebb 512 ablakból áll.
4. A háló kiszámítja a kimeneteket, a **veszteségfüggvény** pedig számmal
   jellemzi az elvárt osztályhoz képesti hibát. Itt kategóriák közötti
   választáshoz használt keresztentrópia a veszteség.
5. A visszaterjesztés kiszámítja, hogyan függ a hiba a súlyoktól.
   Az **Adam optimalizáló** ezek alapján kis lépésekben módosítja őket.
   A lépések nagyságát a tanulási ráta is befolyásolja.
6. Egy teljes végighaladás a tanítópéldákon egy **epoch**. Minden epoch
   után validáció következik, súlymódosítás nélkül.
7. A program csak javuló validációs makro-F1 esetén ment új legjobb
   állapotot. Ha elég sok epochon át nincs javulás, korán leáll.
8. A mentett modellekből INT8-export készül; a jelöltek közötti választás
   a validációs INT8-eredmény alapján történik. A kiválasztott csomagot
   befagyasztjuk, majd külön elvégezzük a végső tesztet.

A kiválasztott konfiguráció legfeljebb 160 epochot enged, 35 epochnyi
javulás nélküli türelemmel. A megőrzött legjobb állapot a 97. epochból
származik; ez nem azt jelenti, hogy összesen csak 97 epoch futott.

A tartás sokkal gyakoribb a váltásoknál. Egy mindig tartást mondó modell
emiatt sok példát eltalálhatna, mégis elmulasztaná a feladat lényegét.
A tanítás ezért a ritkább osztályok hibáinak nagyobb súlyt ad; a jelenlegi
konfiguráció ezt a tanítóadat osztálygyakoriságából számolja.
Ez segíthet, de nem garantál megfelelő minőséget.

**A modell nem tanul a GUI használata közben.** A tanítás PC-n, külön
munkafolyamatban történik TensorFlow-val. A GUI és az ESP32 a már tanított
modellt használja. Egy CSV-export vagy új mérési futás nem módosít súlyokat.
A kipróbáláshoz ezért nincs szükség újratanításra.

### Ha a tanítást is ki szeretnéd próbálni

Az alkalmazás indításához ezeket a lépéseket nem kell elvégezni.
Új kísérlethez külön környezetet és új kimeneti könyvtárakat használj;
a befagyasztott `models/mlp-v2/` csomagot ne írd felül. Az alábbi példa
Python 3.13-at és a repó gyökeréből indított Bash-parancsokat feltételez:

```bash
# Külön környezet a tanításhoz, a GUI környezetétől függetlenül.
python3.13 -m venv .venv-model
.venv-model/bin/python -m pip install -r requirements-model.txt

# Új adatkészlet előállítása; a kimeneti könyvtár még ne létezzen.
.venv-model/bin/python -m pc.dataset generate data/generated/guide-v2 \
  --config config/dataset-v2.json
```

A generálás után nézd át a `data/generated/guide-v2/report.json` jelentést:
mindhárom részhalmazban jelen vannak-e az osztályok, a váltási események
és a határesetek, és nincs-e részhalmazok közötti bemenetegyezés.
Ezután következhet a lezárás, tanítás, export és validáció:

```bash
.venv-model/bin/python -m pc.dataset seal data/generated/guide-v2
.venv-model/bin/python -m pc.dataset verify data/generated/guide-v2
mkdir -p results/guide-training

# A jelenlegi befagyasztott modellével azonos tanítási konfiguráció.
.venv-model/bin/python -m pc.model train \
  --dataset data/generated/guide-v2 --config config/model-v2-capacity.json \
  --output results/guide-training/candidate

# Az export a mentett hálót alakítja át; nem indít új tanítást.
.venv-model/bin/python -m pc.model export \
  --dataset data/generated/guide-v2 \
  --keras results/guide-training/candidate/model.keras \
  --output results/guide-training/candidate/export
.venv-model/bin/python -m pc.model audit \
  results/guide-training/candidate/export/model.tflite

# Az FP32 és INT8 modell kiértékelése a validációs adatokon.
.venv-model/bin/python -m pc.model evaluate \
  --dataset data/generated/guide-v2 \
  --keras results/guide-training/candidate/model.keras \
  --export results/guide-training/candidate/export \
  --output results/guide-training/candidate/validation.json
```

A tanítás a gép teljesítményétől függően hosszabb ideig tarthat. A
`history.json` az epochok alatti fejlődést, a `validation.json` a minőségi
jelentést tartalmazza. Ha valamelyik kimeneti könyvtár már létezik,
a következő kísérlethez válassz új nevet. Ez a parancssor új kísérletet
készít: nem váltja le automatikusan sem a GUI által elvárt modellt,
sem a panel firmware-ét. A történeti eredmények pontos reprodukálásához
az eredeti forrás- és függőségverziók is szükségesek; a részletes
[modellleírás](model.md) ezek megőrzött nyomait is felsorolja.

<a id="beagyazas"></a>

## 6. Hogyan kerül a modell az ESP32-re?

### FP32 és INT8: ugyanaz a feladat, eltérő számábrázolással

Tanításkor a háló jellemzően 32 bites lebegőpontos, **FP32** számokat
használ. A beágyazott futtatáshoz **INT8-kvantálás** készül: a megfelelő
értékeket −128 és 127 közötti, nyolcbites egész kódokkal közelítjük.
A skála és a nullpont írja le, melyik egész kód milyen valós értéket jelent.

Ez durvább felbontás, ezért két közeli szám ugyanarra a kódra kerekedhet.
A kvantálás csökkenti az érintett értékek tárolási méretét, és egész
aritmetikájú végrehajtást tesz lehetővé; tényleges sebességét az eszközön
mérjük meg. A teljes memóriaigénybe a modell mellett a munkaterületek és
a kommunikációs pufferek is beletartoznak. Egyes belső értékek, például
az akkumulátorok és biasok, INT32-t használnak.

Az export **kalibrációhoz** 1024 kiválasztott tanítóablakot használ. Ezek
segítenek meghatározni az ábrázolandó értéktartományokat. Ez nem újabb
felügyelt tanítás, és nem használhat validációs vagy tesztadatot.
Az export ellenőrzése megvizsgálja, hogy a létrejött modell valóban a
megengedett egész műveleteket és bemeneti/kimeneti típusokat tartalmazza-e.

### A modellfájltól a panelen futó programig

A `model.keras` a tanított hálózat mentése, a `model.tflite` az eszközre
szánt exportált modell. A `tools/embed-model.py` a modellcsomagból
C/C++ headerfájlokat készít. Ezeket az ESP-IDF fejlesztőkörnyezettel
belefordítjuk a **firmware-be**, vagyis a panelen futó programba.
A feltöltés ezt a programot írja a panel flashmemóriájába.

Az ESP32-n a **TensorFlow Lite Micro** futtatókörnyezet hajtja végre a
modellt. A PC-s TensorFlow tanít, a mikrokontrolleres futtatókörnyezet
pedig a már kész hálózat számítását végzi.

A **befagyasztás** azt jelenti, hogy rögzítjük a kiválasztott modellfájlt,
konfigurációt és metaadatokat. A SHA-256 ellenőrzőösszeg a fájl tartalmának
azonosítója. Ezzel ellenőrizzük, hogy a PC és a firmware valóban azonos
modellváltozatról beszél. Új modell kipróbálása új csomagot és a megfelelő
firmware frissítését igényli; a GUI modellazonosító-mezője önmagában nem
tölt új modellt a panelre.

A PC-n és az ESP32-n a nyers ablak ellenőrzésének, a skálázásnak,
a sorrendnek és a kvantálás kerekítésének is egyeznie kell. Ha ezek
eltérnek, ugyanaz a modellfájl is más bemenetből számolhatna.

<a id="adatfolyam"></a>

## 7. Mi történik egy alkalmazásfutás közben?

### A PC és az eszköz munkamegosztása

A PC választja ki a bemeneti ablakokat és a futási módot, szervezi a
kommunikációt, megjeleníti az eredményeket és menti az eseménynaplót.
Az ESP32 fogadja az ablakokat, előfeldolgozza őket, futtatja a modellt,
és rögzíti az idő- és memóriaadatokat. A felület háttérszálon végezteti
az adatátvitelt, hogy közben az ablak kezelhető maradjon.

A kommunikáció szöveges JSON Lines üzenetekkel történik, hardveren UART-on,
a külön szimulátor esetén TCP-n. A kliens és az eszköz megállapodik a
futás azonosítójában, majd az alapműveletek:

| Művelet | Jelentés | Miért külön lépés? |
| --- | --- | --- |
| `start` | Futás indítása és az eszköz adatainak ellenőrzése. | Az eredmények azonosított futáshoz tartoznak. |
| `load` | Bemeneti ablakok előtöltése. | A mért végrehajtás előtt már az eszközön legyenek az adatok. |
| `execute` | A betöltött ablakok feldolgozása. | A számítás ideje külön vizsgálható az adatátviteltől. |
| `fetch` | A tárolt eredmények lekérése. | A végrehajtást nem kell folyamatos eredményküldéssel megszakítani. |

Az eszköz korlátos memóriájához illeszkedve egy adag legfeljebb nyolc
ablakot tartalmaz. A teljes teszt sok egymást követő kis adaggal dolgozható
fel. Ez az **eszközoldali adag** más fogalom, mint a tanítás 512 ablakos
batchmérete.

### Élő megfigyelés és terhelésmérés

**Élő módban** a kliens egy-egy ablakot küld, megvárja az eredményt,
majd folytatja a visszajátszást. A grafikon így folyamatosan frissül.
Az „élő” itt a megjelenítés módját jelenti: a jelenlegi alkalmazásban
rögzített vagy demoablakok visszajátszása történik, nem csatlakoztatott
járműszenzorok adatgyűjtése.

**Terhelésmérésben** kis ablakkészletet töltünk elő, amelyet az eszköz
ismételten feldolgoz. Végrehajtás közben nincs UART-adatforgalom; az
összegyűjtött eredményeket csak utána kéri le a PC. Így a soros átvitel és
a grafikonrajzolás nem része a mért MCU-feldolgozási szakasznak.
A grafikon átmeneti csendje ezért elvárt viselkedés.

A teljes teszt minőségellenőrzése ettől külön munkafolyamat: minden
lezárt tesztablakot feldolgoz, és nem hagyja ki azokat terhelési határidő
miatt. A néhány ablakot ismétlő benchmark nem helyettesíti ezt.

### Mire való a szimulátor?

A beépített és a TCP-szimulátor az eszköz kommunikációját utánozza.
Így ESP32 nélkül is kipróbálható a kliens, a felület, a hibakezelés és
az export. **Nem a tanított modellt és nem egy autó mozgását szimulálja:**
érvényes, feldolgozott ablakra rögzített `hold` döntést ad.
Az idő virtuális, a memóriaadat becslés; minden esemény `simulated:true`.
A valódi ESP32 saját INT8-modellt futtat, mért adatokat szolgáltat,
és `simulated:false` jelölést használ.

Az adatgenerátor és az eszközszimulátor tehát eltérő feladatot végez:
az előbbi tanulási meneteket hoz létre, az utóbbi a kommunikáló panelt
helyettesíti fejlesztés és kipróbálás közben.

<a id="meresek"></a>

## 8. Mit mérünk, és mit jelentenek az eredmények?

### Három külön kérdésre válaszolunk

| Kérdés | Összehasonlítás vagy mérés | Mire ad választ? |
| --- | --- | --- |
| Megtanulta a modell a szabályreferenciát? | Modell döntése ↔ szabályreferencia címkéje | A referencia megtanulásának minőségére. |
| Ugyanazt számolja az ESP32, mint a PC? | Azonos modell PC-s ↔ MCU-s bemeneti és kimeneti kódjai | A portolási helyességre. |
| Időben és megfelelő memóriahasználattal fut? | MCU-idők, határidők, memóriaadatok | Az adott hardveren és terhelés mellett mért futási költségre. |

Egy gyors modell lehet pontatlan, és egy pontos modell lehet túl lassú.
A PC–MCU egyezés önmagában egyik minőségi vagy teljesítménycélt sem helyettesíti.

### A döntési minőség mérőszámai

A **pontosság** (`accuracy`) az összes eltalált döntés aránya. Erősen
eltérő osztálygyakoriságnál ez félrevezető lehet. Szemléltető esetben,
ha száz példából 98 tartás, a mindig tartást mondó modell 98%-ot érne el,
de az összes váltást elvétené.

Ezért osztályonként is mérünk:

- **Precision:** a modell által például felváltásnak jelölt esetek közül
  mennyi volt valóban felváltás a szabályreferencia szerint?
- **Recall:** az összes elvárt felváltás közül mennyit talált meg a modell?
- **F1:** a precision és recall harmonikus átlaga,
  `2 × precision × recall / (precision + recall)`.
- **Makro-F1:** a három osztály F1-értékének egyszerű átlaga. A ritka
  váltások így ugyanakkora súlyt kapnak, mint a gyakori tartás.

A **tévesztési mátrix** táblázatba rendezi a valódi és a becsült osztályokat:
a sor a referencia, az oszlop a modell döntése. Főátlója a találatokat,
a többi mező a tévesztés irányát mutatja. Például külön látható,
hányszor mondott tartást a modell elvárt visszaváltás helyett.

### Határidők és túlterhelés

A terhelési profilban **T** a feladatok tervezett indításai közötti idő,
**D** pedig a tervezett indítástól számított határidő. A projektben
`T = D = 10, 20, 50 vagy 100 ms`. A 10 ms-os profil tehát sűrűbb
feldolgozást kér, mint a 100 ms-os. Ez nem változtatja meg az ablakok
**50 ms-os mintaközét**: ugyanazokat az előre elkészített bemeneteket
más végrehajtási gyakorisággal ismételjük.

| Státusz | Jelentés |
| --- | --- |
| `ok` | A feldolgozás sikerült, és időben befejeződött. |
| `late` | A feldolgozás elindult, de az eredeti határidő után ért véget. |
| `missed` | Az időzített feladat kimaradt, például még foglalt volt a végrehajtó. |
| `invalid_window` | Érvénytelen bemenet; nincs érvényes döntés. |
| `model_error`, `memory_error` | Modellfuttatási vagy memóriahiba; nincs érvényes döntés. |

Például 10 ms-os periódus és 25 ms-os feldolgozás mellett a 0 ms-nál
indított feladat csak 25 ms-nál készül el: `late`. A 10 és 20 ms-ra
tervezett feladatok közben kimaradnak: `missed`. Nincs korlátlan várakozási
sor, amely elrejtené a túlterhelést. A kimaradás beleszámít az ütemezett
feladatok számába; nem pótoljuk észrevétlenül.

Profilonként 100 **bemelegítő** feladat után három 1000-es mért sorozat
fut. A bemelegítés a kezdeti állapot hatásainak elkülönítésére szolgál.
Mind a négy profil együtt 400 bemelegítő és 12 000 mért feladatot jelent.
Ez a bemelegítés más, mint az ablakképzés eleji 19 mintás várakozás.

### Milyen időt és memóriát látunk?

Az **inferenciaidő** a hálózat közvetlen futtatási ideje. A **teljes
MCU-feldolgozási idő** az előfeldolgozást, kvantálást, inferenciát és
utófeldolgozást is tartalmazza. A határidő teljesülésénél a tervezett
indítás és a befejezés közötti idő számít, így az indítási késés is fontos.
Az UART-átvitel és a PC várakozása külön költség, nem inferenciaidő.

A **heap** dinamikusan használható memória, a **szabad heap** az abból
még rendelkezésre álló rész. A modellnek ezen felül rögzített munkaterülete
is van, a **tensor arena**, valamint bemeneti és eredménypufferek.
Ezek különböző mutatók; a szabad heapből önmagában nem számítható ki
a modell teljes memóriaigénye. A GUI hardveres memóriagrafikonja a sorozat
utáni szabad heapet mutatja, a szimulátoré viszont csak becsült munkakészletet.

### Hol tart jelenleg a projekt?

Az alábbiak megőrzött eredmények a befagyasztott `mlp-v2` modellről és
a dokumentált, 2026. október 23-i hardveres kampányból; az útmutató
bővítésekor nem futtattunk új tanítást vagy paneles mérést.

| Vizsgálat | Megőrzött eredmény | Értelmezés |
| --- | --- | --- |
| Validációs INT8 makro-F1 | Körülbelül 0,7029 | A legalább 0,95-ös cél nem teljesült. |
| Teljes lezárt teszt makro-F1 | Körülbelül 0,7607, 71 430 ablakon | A végső teszten mért referenciaegyezés; nem új modellválasztási alap. |
| PC–ESP32 portolási egyezés | Mind a 71 430 ablaknál egyező döntés, maximális kimeneti kódeltérés 0 | A dokumentált teljes tesztben ugyanazt számolta a két futtatás. |
| Négyprofilos benchmark | 12 000 mért feladatból 12 000 `ok` | A rögzített kis munkakészlettel nem volt késés, kimaradás vagy feldolgozási hiba. |
| Inferenciaidő mediánja | Körülbelül 0,833 ms minden profilban | A közvetlen hálózatfuttatás ideje, nem a teljes adatúté. |
| Legnagyobb megfigyelt teljes MCU-feldolgozási idő | Körülbelül 2,870 ms | Megfigyelt maximum az adott futásokban, nem minden lehetséges helyzetre bizonyított felső korlát. |

A makro-F1 értéke nem azonos az összes helyes döntés százalékával.
A projekt működő végpontok közötti adatúttal és sikeres portolási méréssel
rendelkezik, de a referencia megtanulásának kitűzött minőségi célja még
nem teljesült. A minőségjavítás külön feladat. A benchmark eredményét
nem terjesztjük ki automatikusan minden bemenetre vagy más hardverre.

A részletes eredmények forrása a [modell dokumentációja](model.md),
a [paneles ellenőrzési napló](evidence/issue-7/verification.md) és a
[bemutató eredményösszesítése](demo-guide.md#7-mérési-elszámolás-és-eredmények).
Az alábbi használati részek önmagukban is elegendők az első szimulátoros
próbához; a további hivatkozások a részletes műszaki ellenőrzést szolgálják.

<a id="frontend"></a>

## 9. A frontend telepítése és indítása

Az alábbi parancsokat Bash alatt, a repó gyökeréből futtasd.

Python 3.10 vagy újabb verzió, pip, venv és grafikus asztali munkamenet
szükséges. Az ESP32 POSIX UART-kapcsolatának támogatott környezete Linux.
Debian/Ubuntu alatt szükség esetén telepítsd az alapvető rendszerfüggőségeket:

```bash
sudo apt-get update
sudo apt-get install python3-venv libegl1 libopengl0
```

Hozz létre egy Python-környezetet, és telepítsd a frontend függőségeit:

```bash
python3 -m venv .venv-ui
.venv-ui/bin/python -m pip install -r requirements-ui.txt
.venv-ui/bin/python -m gearshift.gui
```

A későbbi indításokhoz csak az utolsó parancs szükséges. A Python explicit
elérési útjának használatakor nem kell aktiválni a környezetet. Az asztali
környezettől függően a Qt további rendszerkönyvtárakat igényelhet.

### Első futtatás: beépített szimulátor

1. Az **Eszköz** mezőt hagyd **Beépített eszközszimulátor** állásban.
   Külön folyamat indítása nem szükséges.
2. Az **Üzemmód** maradjon **Élő megfigyelés**.
3. Az **Ablakok JSONL** mezőt hagyd üresen; így 200 generált demoablakot használ.
4. Kattints az **Indítás** gombra. Az eredmények beérkezésekor frissülnek
   a számlálók és a feldolgozási idő grafikonja.
5. Befejezés után a **CSV-export…** gombbal mentsd az összegyűjtött eseményeket.
   Új futás előtt exportálj: az új futás lecseréli a memóriában az előzőt.

Terhelésméréshez válaszd az **Előtöltött terhelésmérés** módot és egy vagy
több 10/20/50/100 ms-os profilt. Profilonként 100 bemelegítő feladat és
három, egyenként 1000 mért feladatból álló sorozat fut. Üres bemeneti mező
esetén nyolc demoablakot használ. A grafikonok az egyes végrehajtási
sorozatok utáni eredménylekéréskor frissülnek. A szimulátor virtuális időt
használ, ezért a terhelésmérés sokkal gyorsabban befejeződik, mint hardveren.

A szimulátor rögzített `hold` döntést ad, `simulator_stub` eredetjelöléssel.
Az időadata virtuális, a memóriaérték becslés. A felület, a protokoll és az
export folyamatát lehet vele kipróbálni; a tanított modellt nem futtatja.

<a id="tcp"></a>

## 10. Opcionális: a szimulátor indítása külön folyamatként

Ebben a módban a PC-s kliens és a szimulált eszköz közötti TCP-kapcsolatot
próbálhatod ki. Egy második terminálban, a repó gyökeréből indítsd el:

```bash
.venv-ui/bin/python -m gearshift.simulator --port 8765
```

Indítsd el a frontendet a 9. szakasz parancsával. Válaszd a **TCP
eszközszimulátor** lehetőséget, a host legyen `127.0.0.1`, a port `8765`,
majd indíts egy futást. A szimulátor a Ctrl+C billentyűkombinációval
állítható le; addig futva marad.

Frontend nélkül is futtathatod az alkalmazást. Az alábbi parancsokhoz csak
a Python szabványos könyvtára szükséges; JSONL eseménynaplókat hoznak létre:

```bash
python3 -m gearshift.client --demo --mode live --output live.jsonl
python3 -m gearshift.client --demo --mode benchmark --output benchmark.jsonl
```

Ha a parancssori klienst a külön TCP-szimulátorhoz szeretnéd csatlakoztatni,
hagyd el a `--demo` kapcsolót, és add meg a
`--host 127.0.0.1 --port 8765` paramétereket.

<a id="esp32"></a>

## 11. Opcionális: futtatás ESP32-vel

Használd a `models/mlp-v2/` könyvtárban található befagyasztott modellt;
újratanítás nem szükséges. A panelre először telepíteni kell az inferencia
firmware-ét. Az ESP-IDF 5.5.1 telepítéséhez és a panel eléréséhez kövesd az
[ESP32 fejlesztőkörnyezetének útmutatóját](esp32-bringup.md), majd a
[firmware fordításának és feltöltésének lépéseit](demo-guide.md#4-sdk-panelazonosítás-firmware).
A feltöltés felülírja a panel jelenlegi programját. A fordítandó alkalmazás:
`firmware/esp32/inference/`.

A firmware feltöltése után:

1. Csatlakoztasd a panelt USB-n. Zárj be minden soros monitort, amely a portját használja.
2. **Minden új futás előtt** reseteld a panelt, és várd meg a rendszerindítást.
3. Indítsd el a frontendet, és válaszd az **ESP32 UART** eszközt.
4. Az **UART port** legyen az eszköz tényleges elérési útja, például
   `/dev/ttyUSB0`. A repó inferencia-firmware-éhez az **UART baud** értéke `921600`.
5. Az elvárt modell SHA-256 azonosítója maradjon a mellékelt modellé:
   `6d5ac8613d301ca06de2ca9a4cfbadf3cd40c7c75a7af419505eaa9fcbb25f79`.
6. Élő futáshoz válaszd a `models/mlp-v2/reference-windows.jsonl` bemenetet.
   Indítsd el, várd meg a befejezést, majd exportáld a CSV-t.
7. Terhelésméréshez reseteld újra a panelt, és használd a
   `docs/evidence/issue-7/benchmark-windows.jsonl` fájlt. Terhelésmérésben
   legfeljebb nyolc bemeneti ablak engedélyezett; az élő referenciafájl ennél többet tartalmaz.

Az ESP32 UART kiválasztása 120 másodpercre állítja a kérés időtúllépését.
A terhelésmérési sorozat alatt az ESP32 UART-forgalom nélkül számol;
a grafikonok utána frissülnek. Mind a négy profil futtatása hardveren
nagyjából 12 percig tarthat. A hardveres grafikonok a mért MCU-feldolgozási
időt és a sorozat utáni szabad heapet mutatják. A hardveres események
`simulated:false` jelölést kapnak.

A parancssori hardveres futtatásról, a nyers UART-forgalom rögzítéséről és
a PC–MCU összevetésről a [bemutató útmutatójában](demo-guide.md#5-rögzített-bemenet-cli-pc-s-összevetés)
és az [inferencia útmutatójában](esp32-inference.md) olvashatsz.

<a id="modulok"></a>

## 12. Az alkalmazás részei és feladataik

A futás közbeni adatút:

```text
Asztali felület → mérési munkamenet → kliens → JSONL protokoll
                                               ├─ beépített/TCP szimulátor
                                               └─ UART → ESP32 inferencia-firmware
Eredmények → munkamenet → grafikonok és CSV-export
```

| Rész | Helye | Feladata |
| --- | --- | --- |
| Asztali felület | `gearshift/gui.py` | Eszköz-, üzemmód- és bemenetválasztás, grafikonok, számlálók, indítás, leállítás és export. |
| Mérési munkamenet | `gearshift/measurement.py` | Háttérszálon futtatja a klienst, gyűjti az eseményeket, és CSV-t olvas, illetve ír. |
| PC-s kliens | `gearshift/client.py` | Elindítja a futásokat, betölti az ablakokat, végrehajtást kér, lekéri az eredményeket és naplózza az eseményeket. A GUI és a CLI közösen használja. |
| Kommunikációs protokoll | `gearshift/protocol.py` | Verziózott JSON Lines keretezés, üzenetellenőrzés és kérés-válasz átvitel. |
| Eszközszimulátor | `gearshift/simulator.py` | PC-n valósítja meg az eszköz kommunikációs szerződését, virtuális ütemezéssel és rögzített döntésekkel. |
| UART-adapter | `gearshift/uart.py` | POSIX soros kapcsolat, időtúllépések és opcionális nyers RX/TX-rögzítés. |
| ESP32 inferenciaalkalmazás | `firmware/esp32/inference/` | Kezeli az eszközparancsokat, ellenőrzi és előfeldolgozza az ablakokat, majd TensorFlow Lite Micro segítségével futtatja a beágyazott INT8-modellt. |
| MCU-mérőmodul | `firmware/esp32/components/measurement/` | Ütemezi a feladatokat, rögzíti az időbélyegeket és a határidők teljesülését, valamint memóriát mintavételez. |
| Szabályreferencia | `pc/reference.py` | A laboratóriumi szabályok alapján determinisztikus elvárt döntéseket ad. |
| Adatkészlet-generálás | `pc/dataset.py`, `config/dataset-*.json` | Reprodukálható szintetikus meneteket és ablakokat generál, külön tanító-, validációs és tesztmenetekkel. |
| Modell-előkészítés | `pc/model.py`, `config/model-*.json` | Tanítja az MLP-t, INT8 TFLite-modellt exportál, és kiszámítja a PC-s referenciakimeneteket. |
| Befagyasztott modellcsomag | `models/mlp-v2/`, `gearshift/frozen_export.py` | Tárolja a kiválasztott modellt és metaadatait; ellenőrzi a befagyasztott állományokat és az ellenőrzőösszegeket. |
| Modell beágyazása a firmware-be | `tools/embed-model.py` | Az ellenőrzött modellcsomagból a firmware által használt headerfájlokat készít. |
| Végső teszt előkészítése | `gearshift/campaign.py` | Előkészíti a lezárt tesztadatkészletet a végső kiértékeléshez. |
| Eredményelemzés | `gearshift/porting.py`, `run_report.py`, `profiler.py`, `uart_evidence.py` | Összeveti a PC és az MCU kimeneteit, összesíti az idő- és memóriaadatokat, és ellenőrzi a kommunikációs bizonyítékokat. Mind a négy modul a `gearshift/` alatt található. |
| Tesztek és bizonyítékok | `tests/`, `docs/evidence/`, `results/` | Sorrendben: automatizált ellenőrzések, megőrzött bizonyítékok és helyben generált eredmények. |

A többi firmware-könyvtár külön fejlesztési ellenőrzéseket szolgál:
a `bringup/` kompatibilitási példákat tartalmaz, a `model_probe/` a modell
műveleteinek támogatását vizsgálja, a `measurement/` pedig mérési
próbaalkalmazás. Az asztali bemutató az `inference/` firmware-t használja.

A modell minden bemenete egy 20 mintából álló ablak, 50 ms-os mintaközzel.
Mintánként öt jel szerepel: sebesség, gázpedál, emelkedő, fokozat és a váltás
óta eltelt idő. Ez 100 bemeneti értéket ad a befagyasztott
100 → 64 → 32 → 3 MLP számára. A mértékegységeket, érvényességi szabályokat
és a JSONL formátumot az [adatszerződés](data-contract.md) írja le.

Az offline adatkészlet-generálás és modelltanítás elkülönül a frontend
futtatásától. Ezek a `requirements-model.txt` függőségeit használják
(TensorFlow; a dokumentált modellkörnyezet Python 3.13-at használ).
A lépések reprodukálásához kövesd az [adatkészlet útmutatóját](dataset.md)
és a [modell útmutatóját](model.md).

<a id="hibakereses"></a>

## 13. Mentés és gyakori indítási problémák

A CSV-fájlok kereshető oszlopokat és egy `event_json` oszlopot tartalmaznak;
az utóbbi minden eseményt teljes egészében megőriz. A grafikonokon az utolsó
2000 eredmény látszik, az export viszont az összes begyűjtött eseményt
tartalmazza. Élő módban ablakonként érkezik eredmény. Terhelésmérésben egy
kis, előtöltött munkakészlet ismétlésével mérjük a terhelés alatti végrehajtást.

Leállítás vagy időtúllépés után a futás részleges marad. A már beérkezett
eredmények exportálhatók, de a részleges futás nem befejezett mérés.
Az események exportálásig a RAM-ban maradnak, ezért az alkalmazás bezárása
előtt mentsd őket.

| Tünet | Ellenőrizendő |
| --- | --- |
| `No module named PySide6` vagy `pyqtgraph` | A `requirements-ui.txt` függőségeit ugyanazzal a `.venv-ui/bin/python` értelmezővel telepítsd, amellyel a GUI-t indítod. |
| Nem sikerül létrehozni a venv-et | Telepítsd a Python-verziódhoz tartozó `python3-venv` rendszercsomagot. |
| A Qt nem éri el a kijelzőt, vagy nem tudja betölteni a platformbővítményét | Grafikus asztali munkamenetben indítsd, és telepítsd a hiányzó Qt-platformkönyvtárakat. A `QT_QPA_PLATFORM=offscreen` automatizált ellenőrzésre szolgál. |
| A TCP-kapcsolatot elutasítja a rendszer | Indítsd el külön a szimulátort, és egyeztesd a hostot és a portot. A beépített szimulátorhoz nem kell szerver. |
| UART-hozzáférési hiba vagy sikertelen kapcsolat | Ellenőrizd a port elérési útját, a soros hozzáférési jogosultságokat, a baudot és azt, hogy más folyamat használja-e a portot; lásd az [ESP32 útmutatóját](esp32-bringup.md). |
| A második hardveres futás sikertelen | Reseteld a panelt, és várd meg a rendszerindítást; a firmware rendszerindításonként egy futásazonosítót fogad el. |
| A terhelésmérés grafikonja átmenetileg nem frissül | Az eredmények lekérése az egyes végrehajtási sorozatok után történik. A hardveres időtúllépés maradjon 120 másodperc. |

További részletek: [felület és CSV](measurement-ui.md),
[kommunikáció](communication.md) és [teljes bemutató](demo-guide.md).

<a id="fogalmak"></a>

## 14. Alapfogalmak szótára

| Fogalom | Jelentés ebben a projektben |
| --- | --- |
| Minta | Egy időpont öt állapotértéke: sebesség, gázpedál, emelkedő, fokozat és váltás óta eltelt idő. |
| Mintaköz | Két egymást követő minta időbeli távolsága; itt 50 ms. |
| Menet | Egy forgatókönyvhöz tartozó teljes, időrendi mintasorozat. |
| Menetcsalád | Egy alapmenet és az abból képzett változatok együttese; egyben tartjuk az adatfelosztás során. |
| Ablak | Húsz egymást követő minta, amelyhez egy döntés tartozik. |
| Csúszóablak | Új minta érkezésekor egy mintával továbbtolódó ablak; a legutóbbi húsz mintát tartja meg. |
| Bemeneti jellemző, feature | A modellnek átadott számszerű bemenet egyik eleme. Itt egy ablak száz skálázott értéket ad. |
| Lapítás | A húsz ötelemű minta egyetlen százszámos sorozattá alakítása, rögzített sorrendben. |
| Címke, label | Az ablakhoz rendelt elvárt osztály, amelyet a szabályreferencia határoz meg. |
| Osztály | A három válaszlehetőség egyike: visszaváltás, tartás vagy felváltás. |
| Osztályindex és döntési érték | A tárolt osztályindex 0/1/2; a hozzá tartozó váltási döntés −1/0/+1. A kettő nem cserélhető fel. |
| Szabályreferencia | A laborfeltevések szerinti determinisztikus címkéző; azt adja meg, mit tanítunk a modellnek. |
| Referencia megtanulása | A tanult modell döntéseinek egyezése a szabályreferenciával korábban nem látott menetszakaszokon. |
| Hiszterézis | Eltérő fel- és visszaváltási küszöb alkalmazása az oda-vissza váltási igény csökkentésére. |
| Szintetikus adat | Programmal létrehozott adat; nem tényleges közúti mérés. |
| Seed | A véletlenszám-generálás rögzített kezdőértéke a megismételhetőséghez. |
| Adatszivárgás | Amikor a kiértékeléshez szánt információ közvetlenül vagy közvetve bekerül a tanulási folyamatba. |
| Tanítóhalmaz | Azok a példák, amelyek alapján a súlyokat módosítjuk. |
| Validációs halmaz | Külön példák a modellállapotok és jelöltek kiválasztásához. |
| Lezárt teszthalmaz | A befagyasztott modell végső értékelésére fenntartott adatok. |
| Neurális hálózat, MLP | Egymást követő tanulható számítási rétegek; itt száz bemenetből három osztályértéket képeznek. |
| Súly és eltolás, bias | A hálózat tanítás során módosuló paraméterei. |
| Hiperparaméter | A tanítás előtt megadott beállítás, például a tanulási ráta, rétegméret vagy batchméret. |
| Epoch | Egy teljes végighaladás a tanítópéldákon. |
| Tanítási batch | Egy súlyfrissítéshez feldolgozott példacsoport; itt legfeljebb 512 ablak. |
| Eszközoldali adag | Egyszerre előtöltött ablakcsoport; itt legfeljebb nyolc ablak. |
| Veszteségfüggvény | A tanításkor csökkenteni kívánt számszerű hiba. Nem ugyanaz, mint a jelentett makro-F1. |
| Adam | A hálózat paramétereinek frissítését végző optimalizáló algoritmus. |
| Checkpoint | A modell tanítás közben elmentett állapota. |
| Korai leállítás | A tanítás befejezése, ha a validációs eredmény a megadott ideig nem javul. |
| Inferencia | Egy már tanított modell futtatása adott bemenetre, súlymódosítás nélkül. |
| Előfeldolgozás | A nyers jelek ellenőrzése és a modellnek megfelelő alakra, skálára hozása. |
| Kvantálás | Valós értékek véges felbontású egész kódokkal történő közelítése. |
| FP32 / INT8 | 32 bites lebegőpontos / 8 bites előjeles egész számábrázolás. |
| Kalibráció | A kvantált export értéktartományainak meghatározása tanítópéldák segítségével. |
| Befagyasztott modell | Rögzített, azonosított modellcsomag, amelyet a következő kísérletek nem írnak felül. |
| SHA-256, ellenőrzőösszeg | A fájltartalomból számított lenyomat; az azonos verzió és a változatlanság ellenőrzésére szolgál. |
| Manifest | Az adatkészlet tartalmát, verzióját és ellenőrzőösszegeit leíró állomány. |
| PC-s modellreferencia | A beágyazott modell PC-n számított kimenete, amellyel az MCU eredményét összevetjük. |
| Portolási helyesség | Ugyanazon modell azonos bemenethez tartozó kimeneteinek egyezése a PC-s és mikrokontrolleres futtatás között. |
| Firmware | A mikrokontrollerre fordított és feltöltött program. |
| ESP-IDF | Az ESP32 firmware-ének fordításához és feltöltéséhez használt fejlesztőkörnyezet. |
| TensorFlow / TensorFlow Lite Micro | Előbbi a PC-s tanításhoz is használt keretrendszer, utóbbi a mikrokontrolleres modellfuttató környezet. |
| Frontend, GUI | Az alkalmazás grafikus kezelőfelülete; itt PySide6 asztali ablak. |
| CLI | Parancssori felület; terminálból indított használat grafikus ablak nélkül. |
| Kliens | A futást kezdeményező és az eszközműveleteket szervező PC-s programrész. |
| Protokoll | A kommunikáló felek üzeneteire, sorrendjére és hibakezelésére vonatkozó megállapodás. |
| UART és baud | Soros adatátviteli kapcsolat és annak jelátviteli sebessége; a két fél beállításának egyeznie kell. |
| TCP | A külön folyamatként futó helyi szimulátorhoz használt hálózati kapcsolat. |
| JSONL | Soronként egy JSON-objektumot tartalmazó szöveges fájl vagy üzenetfolyam. |
| CSV | Táblázatos szöveges fájl, például a mérési események exportjához. |
| Eseménynapló | A futás beállításait, üzeneteit, eredményeit és állapotváltozásait rögzítő sorozat. |
| Benchmark, terhelésmérés | Szabályozott végrehajtási terhelés alatt végzett idő- és memóriavizsgálat. |
| Periódus és határidő | A tervezett indítások közti idő, illetve az egy feladat befejezésére rendelkezésre álló idő. |
| Heap / tensor arena | Dinamikus memóriaterület / a modell tenzorainak és köztes számításainak fenntartott munkaterület. |
| Makro-F1 | Az osztályonkénti F1-értékek átlaga; mindhárom osztályt azonos súllyal veszi figyelembe. |
| Tévesztési mátrix | Az elvárt és a becsült osztályok találatait és tévesztéseit összesítő táblázat. |

Olvasás utáni első gyakorlathoz indítsd el a beépített szimulátort a
[9. szakasz](#frontend) alapján. Próbálj először élő futást, majd
terhelésmérést 25 ms-os virtuális feldolgozási idővel és 10, illetve 50 ms-os
profillal. Az előbbinél megjelenő késések és kimaradások, illetve az utóbbinál
időben elkészülő feladatok megmutatják az ütemezés működését. Az exportált
CSV-ben az `event_json` mező segítségével ugyanazok az események később is
visszanézhetők. Ez a gyakorlat a szimulátort használja, ezért nem igazol
ESP32-teljesítményt vagy modellminőséget.
