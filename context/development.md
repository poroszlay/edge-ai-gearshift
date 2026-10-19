# Projektmunka - fejlesztési kontextus új LLM-munkamenethez

**Projekt:** Mesterséges intelligencia alkalmazása a mikrokontrolleres alkalmazásokban  
**Állapotdátum:** 2026-09-22.  
**Kontextusverzió:** 1.0  
**Aktuális szakasz:** II. félév, az 1-2. hét előkészítése teljesítve; a 3. héttől fejlesztés következik.  
**Nyelv:** magyar magyarázatok; a kódban következetes angol azonosítók használhatók.

> **Implementációs frissítés (2026-10-18, #2):** az ESP32 hivatalos alap- és
> következtetési mintaprojektje a `firmware/esp32/bringup/` alatt található.
> A tényleges build- és hardverállapotot a
> [#2 ellenőrzési napló](../docs/evidence/issue-2/verification.md) rögzíti;
> az alábbi forrásalapú induló állapotot erre a feladatra ez egészíti ki.

## 1. Az LLM feladata és a folytatás módja

Légy a projekt fejlesztési mentora és technikai segítője. Az alábbi specifikációból kiindulva vezess végig a PC-s adatgenerálás, az ESP32-firmware, a modellfejlesztés, a soros kommunikáció, a kezelőfelület, a mérések és a dokumentálás folyamatán. A cél működő, megérthető és reprodukálható laboralkalmazás készítése.

Az első két hét feladatspecifikációját és tervezési eredményeit tekintsd meglévő alapnak. A beszámoló ugyanakkor kifejezetten hátralévő feladatként nevezi meg az adatgenerátort, a lezárt adatkészletet és a hardveres kompatibilitási próbát. Ne következtess a hetek teljesítéséből kész programokra vagy már lefutott mérésekre.

Munkamód:

1. Először állapítsd meg a tényleges fejlesztőkörnyezetet és a már létező fájlokat; utána a legközelebbi végrehajtható feladattal haladj.
2. Adj rövid áttekintést, majd egy kezelhető munkacsomagot. Minden lépéshez tartozzon cél, szükséges fájl/parancs, várt eredmény és ellenőrzés.
3. A parancsokat igazítsd az operációs rendszerhez és a ténylegesen telepített verziókhoz. Jelezd, melyik könyvtárban és melyik terminálban kell futtatni őket.
4. Ha kódot adsz, nevezd meg a fájlt és azt, hogy új fájlról, teljes cseréről vagy részleges módosításról van-e szó. A megoldás legyen érthető, kis egységekben kipróbálható.
5. Az új fogalmakat röviden magyarázd el. Különítsd el a PC-n végzett tanítást, a PC-s referenciafuttatást és az MCU-n végzett következtetést.
6. Hardveres eredményt csak valódi futtatás vagy a felhasználó visszajelzése után tekints igazoltnak. Mintakimenetet és becslést mindig jelölj annak.
7. Hibánál kérd el a pontos parancsot, a releváns naplót és a verziókat; egyszerre egy valószínű okot vizsgálj. Ne kezdj indokolatlanul teljes újratelepítésbe.
8. Rögzített specifikációt csak indokolt, dokumentált döntéssel módosíts. A hiányzó részletekre tegyél javaslatot, és különböztesd meg a javaslatot az elfogadott döntéstől.
9. A könyvtárak, SDK-k, hardverek támogatását és az API-k használatát megvalósításkor hivatalos dokumentációból ellenőrizd. Ne találj ki verziót, telepítési parancsot vagy NPU-képességet.
10. Minden lezárt munkacsomag után frissítsd a haladási naplót és a következő munkamenetnek átadható állapotot. Kéthetente segíts a tényleges eredményekből beszámolót készíteni.

Ez a fájl önálló kezdőkontextus: az alapfeladat megértéséhez nem szükséges a korábbi beszélgetés. A fejlesztés későbbi állapotának megítéléséhez viszont a tényleges kódot, konfigurációt és naplókat is be kell kérni.

## 2. Források és a tények kezelése

| Jel | Forrás | Szerepe |
| --- | --- | --- |
| F1 | `projektmunka_temavazlat.md`, 1 oldal; „Témaleírás és II. félévi ütemterv” | A négy féléves cél, a laborrendszer terve, a mérési alapelvek és a 14 hetes ütemezés. A műszaki forráslista dátuma: 2026-09-13. |
| F2 | `projektmunka_elorehaladasi_dokumentacio_masodik_het.md`, 2 oldal | Az 1-2. hét részletes specifikációja, döntései és a 3. hétre átadott tényleges állapot. A műszaki forráslista dátuma: 2026-09-22. |
| U1 | A felhasználó kérése e kontextus készítésekor | Az első két hét teljesítve; most a fejlesztéshez kér lépésenkénti LLM-támogatást. |

Az aktuális állapotot U1 és F2 alapján értelmezd; F1 az eredeti terv. Például F1 a 2. hétre rögzített tesztadatokat tervezett, F2 viszont az adatgenerátort és az adatkészlet lezárását még hátralévő feladatként jelöli. Ezért ezek specifikációja elkészült, megvalósításuk nem igazolt.

A következő fejezetekben a **rögzített** tartalom F1/F2-ből származik. A **javasolt** munkabontás, fájlszerkezet, sémák és ellenőrzések e kontextus fejlesztést segítő kiegészítései; nem a konzulens által külön jóváhagyott új követelmények. A **nyitott** részleteket a megvalósítás során kell eldönteni.

F2 utal egy korábbi kontextusfájlra, de annak tartalma nem volt e dokumentum forrása. Ez a kontextus a két csatolt PDF-re és U1-re épül.

## 3. A projekt célja és határai

A hosszú távú cél autonóm járművek irányításának kiegészítése erőforrásokra és feladatra optimalizált beágyazott AI-algoritmusokkal. A későbbi célalkalmazás egy elektromos mikrobusz fokozatváltási döntéseinek optimalizálása környezeti és belső járműparaméterek alapján. [F1]

| Félév | Tartalom | Állapot |
| --- | --- | --- |
| I. | Edge AI / TinyML szakirodalmi feldolgozás | Elvégezve. |
| II. | Laboratóriumi tesztalkalmazás jármű nélkül | Folyamatban; most indul a fejlesztés. |
| III. | Mikrobusz-hozzáférés, implementáció és ellenőrzés | Későbbi szakasz. |
| IV. | Összesített kiértékelés és diplomamunka | Későbbi szakasz. |

A konzulens a II. félévi laboralkalmazás ötletét elfogadta. A mikrobusz a III. félévtől lesz elérhető. A jelenlegi feladat szintetikus menetszakaszokon azt vizsgálja, milyen döntési minőség, futásidő és memóriaigény érhető el ESP32-n, majd NPU-s eszközön. [F2]

**Értelmezési korlátok:** a két előremeneti fokozat és a számszerű beállítások laborfeltevések. A szabály alapján előállított címkékhez mért egyezés a referencia megtanulását méri. Ebből önmagában nem igazolható optimális járműirányítás, tényleges járműves energiamegtakarítás vagy valós járműkövetelmények teljesítése. Ezek ellenőrzése a későbbi járműves szakasz feladata.

## 4. Mi készült el, és mi nincs még igazolva?

| Terület | Állapot a fejlesztés indulásakor |
| --- | --- |
| Laboralkalmazás koncepciója | Konzulens által elfogadva F2 szerint. |
| Tesztfeladat, jelek, kimenetek, címkézési szabály | Specifikáció elkészült. |
| Adatgenerálás, adatfelosztás és visszajátszás | Terv elkészült; generátor és lezárt adatkészlet még elkészítendő. |
| Mérési protokoll és laborprofilok | Terv rögzítve; mérési eredmény nincs bemutatva. |
| ESP32-fejlesztőkörnyezet | Kiinduló technológia megnevezve; telepítés és működő próba nincs igazolva. |
| PC-s referencia | Viselkedése specifikálva; futó implementáció nincs mellékelve. |
| Firmware, soros protokoll, UI | Fejlesztendő; meglévő kód nincs mellékelve. |
| MLP/CNN, INT8-export, döntési fa | Tervezett; tanított modell vagy eredmény nincs mellékelve. |
| NPU-s panel és SDK | Pontos típus nyitott; legkésőbb a 8. hétre szükséges. |

Ha a felhasználó azóta készített kódot vagy végzett mérést, ezt az új bizonyíték alapján vezesd át. Ne kezdd újra a már igazoltan működő munkát.

## 5. Rögzített feladat- és adatspecifikáció

### 5.1. Kimenet

A feltételezett kétfokozatú elektromos hajtás következő döntését kell becsülni. [F2, 1. oldal]

| Döntés | Döntési érték | Osztályindex |
| --- | --- | --- |
| Visszaváltás | -1 | 0 |
| Tartás | 0 | 1 |
| Felváltás | +1 | 2 |

Az osztályindex és a döntési érték külön fogalom: például a `0` osztályindex visszaváltást jelent. Hiányos vagy érvénytelen bemenet külön hibajelzést kap; ez nem negyedik tanítandó döntési osztály, és nem címkézhető automatikusan tartásnak.

### 5.2. Bemenetek és ablak

| Jel | Jelentés | Egység | Laborbeli tartomány |
| --- | --- | --- | --- |
| `v` | Sebesség | km/h | 0-80 |
| `u` | Gyorsítási igény | Dimenzió nélküli | 0-1 |
| `s` | Útemelkedés | % | -10 és +10 között |
| `g` | Aktuális fokozat, döntés előtt | Fokozat | 1 vagy 2 |
| `tau` / `τ` | Utolsó váltás óta eltelt idő | Másodperc | A modellbemenet 10 s-nál telítődik. |

A telítés a modellbemenetre vonatkozik; a belső időszámláló és a CSV-beli tárolás pontos megoldását külön rögzíteni kell. A negatív eltelt idő érvényességének kezelését az adatellenőrzés részeként határozd meg.

- Jel-mintavétel: **50 ms**, azaz 20 Hz.
- Egy modellbemenet: **20 egymást követő minta × 5 jel**, időrendben.
- Csak az aktuális és korábbi minták használhatók; jövőbeli adat nem.
- Az MLP az ablak **100 elemre lapított** változatát kapja.
- A későbbi kompakt CNN ugyanennek az ablaknak az időbeli szerkezetét használja.
- A 20 minta 20 mintavételi helyet jelent; az első és utolsó időbélyeg különbsége szabályos mintavételnél 19 × 50 = 950 ms. Az ablak pontos indexelését dokumentálni kell.

**Javasolt megvalósítási konvenció:** a jeloszlopok sorrendje `[v, u, s, g, tau]`, a sorok sorrendje legrégebbitől a legújabbig; az MLP lapítása mintánként történik. Ezt a generátor, a tanítás, az export és a firmware közös szerződéseként kell rögzíteni. A futtatókörnyezet szerinti végleges tensoralakok még nyitottak.

### 5.3. Determinisztikus címkéző / szabályalapú referencia

Az ablak **utolsó öt mintájából** átlagolandó `v`, `u` és `s`. A `g` és `tau` a **legfrissebb minta döntés előtti állapota**. [F2, 1. oldal]

```text
v_atlag = mean(az utolsó 5 minta v értékei)
u_atlag = mean(az utolsó 5 minta u értékei)
s_atlag = mean(az utolsó 5 minta s értékei)
g       = a legfrissebb minta fokozata, döntés előtt
tau     = a legfrissebb minta eltelt ideje, döntés előtt

v_fel = 30 + 20 * u_atlag + 0.5 * s_atlag    # km/h
v_le  = v_fel - 10                          # km/h

ha a bemenet hiányos vagy érvénytelen:
    külön hibajelzés; nincs érvényes döntési címke
egyébként ha tau < 1.0:
    tartás          # döntési érték 0, osztályindex 1
egyébként ha g == 1 és v_atlag > v_fel:
    felváltás       # döntési érték +1, osztályindex 2
egyébként ha g == 2 és v_atlag < v_le:
    visszaváltás    # döntési érték -1, osztályindex 0
egyébként:
    tartás          # döntési érték 0, osztályindex 1
```

A küszöbfeltételek **szigorú** egyenlőtlenségek: küszöbegyezéskor tartás. Pontosan `tau = 1 s` esetén már engedhető váltás. Az útemelkedést a képlet százalékos számértékkel használja: 5%-hoz `s = 5` tartozik.

| Ellenőrző eset: `v_atlag`, `u_atlag`, `s_atlag`; `g`; `tau` | Elvárt döntés | Indok |
| --- | --- | --- |
| 45 km/h, 0,2, 0%; 1; 3 s | Felváltás, index 2 | `v_fel = 34`; 45 > 34. |
| 20 km/h, 0,8, 5%; 2; 3 s | Visszaváltás, index 0 | `v_fel = 48,5`, `v_le = 38,5`; 20 < 38,5. |
| 34 km/h, 0,2, 0%; 1; 3 s | Tartás, index 1 | Egyenlőség a felső küszöbön. |
| 45 km/h, 0,2, 0%; 1; 0,3 s | Tartás, index 1 | Az 1 s váltási tiltás még él. |

**Javasolt további ellenőrzések:** alsó küszöbön egyenlőség; `tau` közvetlenül 1 s alatt és pontosan 1 s-nál; szélső bemenetek; hiányzó minta, hibás fokozat, NaN/Inf; rossz jelsorrend; 20 helyett más ablakhossz. Az érvényességi szabályokat külön specifikálni kell.

### 5.4. Szintetikus adatgenerálás

Python-generátor készít összefüggő gyorsítási, egyenletes haladási, emelkedős, lassítási és váltási küszöb körüli menetszakaszokat. Külön esetek vizsgálják a váltás utáni tiltást és a hibás jeleket. [F2, 1-2. oldal]

Rögzített adatkezelési szabályok:

- A CSV minden sora menetazonosítót, időbélyeget, az öt bemenetet és az elvárt döntést tartalmazza.
- A döntéshez a döntés előtti állapot tartozik; a fokozat és a váltási idő frissítése csak a következő mintában jelenik meg.
- A véletlenmagot, a generálási konfigurációt és a címkéző verzióját rögzíteni kell.
- A menetszakaszok felosztása **70% tanító / 15% validációs / 15% teszt** arányban történik, **ablakképzés előtt**.
- Egy menet és annak zajos változatai ugyanabba a részhalmazba kerülnek.
- Ellenőrizni kell mindhárom osztály darabszámát; a végső tesztkészletet le kell zárni.
- A normalizálás tanult paraméterei és az INT8-kalibráció mintái kizárólag a tanítórészből származhatnak.

**Javasolt minimális CSV-séma:**

```text
run_id,timestamp_ms,v_kmh,u,s_percent,g,tau_s,expected_action,class_index
```

Az oszlopnevek, az időbélyeg egysége és a kétféle címke együttes tárolása javaslat; a megvalósításban véglegesíteni kell. A hibás minták számára külön státusz/hibakód vagy elkülönített hibatesztállomány szükséges, kitalált döntési címke nélkül.

**Nyitott részletek:** adatmennyiség, menethosszak, jel- és zajparaméterek, kezdeti állapot, a váltást követő `tau` időléptetése, az első teljes ablak előtti sorok kezelése, ablaklépés, érvényességi szabályok és az osztályarányok kezelése. Ezekhez adj egyszerű, dokumentált kezdőjavaslatot. Az ablak nem nyúlhat át másik menetbe; a teszteredmény alapján ne hangold vissza a generátort vagy a modellt ugyanarra a lezárt tesztkészletre.

### 5.5. Visszajátszás és a visszacsatolás határa

A PC USB-UART-on előtölti az ablakokat. Az MCU következtet és mér; a PC fogadja az eredményeket, naplóz, megjelenít és CSV/JSON-formátumba exportál. **A modell válasza nem módosítja a visszajátszott bemenetet.** [F2, 2. oldal]

Az adatgenerálás közbeni referenciaállapot-frissítés és a mérés közbeni rögzített visszajátszás eltérő szerepű. A CPU/NPU és a modellek összehasonlíthatóságához ugyanazokat az előállított ablakokat kell visszajátszani. A zárt hurkú járműirányítás nem e laborbenchmark része.

## 6. Hardver, szoftver és modellirány

| Elem | Rögzített kiindulás / állapot |
| --- | --- |
| Első MCU | ESP-WROOM-32 alapú ESP32, NPU nélkül. A pontos fejlesztőpanel és a rendelkezésre álló memória még ellenőrizendő. |
| Firmware-környezet | ESP-IDF + `esp-tflite-micro` a beszámoló szerint. A kompatibilis verziókat a telepítéskor kell ellenőrizni és rögzíteni. |
| PC-s oldal | Python-alapú generálás; tanítás és referenciafuttatás PC-n. Az operációs rendszer és a csomagverziók ismeretlenek. |
| Első modell | Kis MLP, 100 elemre lapított ablak, INT8, batch = 1. Rétegszám és neuronszám nincs rögzítve. |
| Második neurális modell | Kompakt CNN, ugyanazokból az ablakokból, az időbeli szerkezet használatával; INT8. A konkrét konvolúciós megoldás nyitott. |
| Összehasonlítási alapok | CPU-s döntési fa és a közvetlen determinisztikus szabályfuttatás. |
| Második MCU | NPU-s panel; típusa, SDK-ja és érkezése még tisztázandó. |
| Kapcsolat | USB-UART; protokoll, baud rate, pufferméret és hibakezelés még tervezendő. |
| Kezelőfelület | F1 ajánlása: PySide6 + pyqtgraph helyi eszközvezérléshez és élő grafikonokhoz. Ez ajánlott irány, nem már megvalósított UI. |

F1 alternatívaként Dash + Plotly böngészős dashboardot, illetve Streamlit elemző prototípust említ; ezeknél a folyamatos adatgyűjtést külön rétegben kell kezelni. Új felületet csak konkrét igény alapján válassz a javasolt helyi alkalmazás helyett.

A kezelőfelület tervezett funkciói: adat-, modell- és eszközválasztás; indítás/leállítás; élő grafikonok; eredmények összehasonlítása; CSV/JSON-export. Az adatforrást, a modellfuttatást és a mérést külön modulokként kell kezelni. [F1]

Az NPU kiválasztásakor ellenőrizendő a rétegek és tensoralakok támogatása, a teljes INT8-adatút, a memóriaigény, a fordító és a CPU-ra visszaeső műveletek. NPU-gyorsítást csak igazoltan gyorsítón futó műveletekre állíts. A CPU-s fejlesztést az NPU hiánya miatt nem kell felfüggeszteni.

## 7. Rögzített mérési protokoll

### 7.1. Összehasonlíthatóság

- Modellenként a CPU/NPU-vizsgálatban azonos bemenet, súlyok, INT8-kivitel és **batch = 1** szükséges.
- Az MLP és a CNN külön modell; az „azonos súlyok” az egyazon modell külön eszközös futtatására vonatkozik.
- Órajelek és szoftververziók rögzítendők.
- A mérési terv **100 bemelegítő + 3 × 1000 mért futás**. A bemelegítők nem kerülnek a mért futások statisztikájába.
- Az MCU-időmérés a kész eredményig tart; az NPU-adatmozgatás beleértendő, a soros küldés nem.
- A közvetlen szabályfuttatás és a döntési fa CPU-s összehasonlítási alap. Ne kezeld őket INT8 neurális modellként.

### 7.2. Kötelező és opcionális metrikák

| Terület | Mit kell rögzíteni? | Értelmezés |
| --- | --- | --- |
| Idő | Inferencia és teljes MCU-feldolgozás külön; medián, p95, megfigyelt maximum [ms] | Teljes MCU-feldolgozás elő- és utófeldolgozással. A megfigyelt maximum nem bizonyított legrosszabb esetű időkorlát. |
| Memória | Statikus RAM, modell-munkaterület és futás közbeni használat külön [KiB]; modell- és programméret | A memóriaértékek jelentését és esetleges átfedését dokumentálni kell. |
| Döntési minőség | Makro-F1 és tévesztési mátrix a címkézett tesztadaton | A szabályreferenciához mért minőség. |
| Portolási helyesség | Ugyanazon INT8-modell PC-s és MCU-s kimenetének eltérése | Külön a tanult modell minőségétől; az egyezési tűrés még rögzítendő. |
| Terhelés | Inferencia/s; határidőre nem teljesült feladatok aránya | Az összes ütemezett feladathoz viszonyítva, a kimaradók figyelembevételével. |
| Stabilitás | Futási hibák és memóriaváltozás | A megfigyelési idővel és körülményekkel együtt. |
| UART | Várakozás külön naplózva | Ne mosódjon össze az MCU-feldolgozási idővel. |
| Energia | Opcionális mJ/inferencia, külső műszerrel | Rögzített tápági mérési határ; műszer nélkül nem igazolt mérési eredmény. |

Portolási összevetésnél a puszta egyező osztálydöntés mellett a numerikus modellkimenetek eltérését is érdemes naplózni. A kvantálás skáláit, nullpontjait, adattípusait és a bemenet előfeldolgozását a modell mellett kell megőrizni. Ez fejlesztési javaslat a hibák elkülönítésére.

### 7.3. Laboratóriumi terhelési profilok

```text
T = D = 10 ms
T = D = 20 ms
T = D = 50 ms
T = D = 100 ms
```

`T` az indítási periódus, `D` a válaszadási határidő. Ezek **függetlenek az 50 ms-os jel-mintavételtől**. A rövidebb periódus nem változtatja meg a már elkészült ablak fizikai időbeli tartalmát. A profilok mesterséges laborterhelések, nem igazolt járműkövetelmények.

Javasolt egyértelmű elszámolás:

```text
határidőre nem teljesült [%] =
    100 * (határidőre be nem fejezett ütemezett feladatok száma)
        / (összes ütemezett feladat száma)
```

A későn befejezett és a kimaradt feladatok ne számítódjanak kétszer. A határidőt a tervezett indításhoz kell viszonyítani; a késedelmes indítás ne tűnjön el a csak tényleges kezdéstől mért futásidőben. A várólista, túlterhelés, kimaradás és a mérés végén függőben maradó feladatok kezelése még véglegesítendő.

### 7.4. CPU/NPU-gyorsulás

```text
gyorsulás = t_CPU / t_NPU
```

Csak azonos statisztikák aránya használható: például medián/medián vagy p95/p95, azonos mérési határok mellett. Két eltérő panel összevetése rendszerszintű eredmény; önmagában nem izolálja az NPU hatását. Ha támogatott, ugyanazon panelen CPU- és NPU-módú mérést is kell végezni. A CPU-ra eső műveleteket külön jelölni kell. [F1]

**Még rögzítendő mérési részletek:** az időbélyegek pontos helye, az előfeldolgozás PC/MCU közötti felosztása, a bemelegítés és ismétlések indítási rendje, a p95 számítása, a bemenetek sorrendje, az előtöltés/pufferelés, a referenciaeltérés toleranciája és a stabilitásvizsgálat időtartama. Konkrét minőségi vagy RAM-küszöböt a források nem írnak elő; ne találj ki jóváhagyott követelményt.

## 8. A hátralévő félév eredeti ütemezése

Az alábbi hetek F1 tervét követik. A még hiányzó adatgenerátort és adatlezárást F2 alapján be kell illeszteni a fejlesztés elejére, a modell tanítása elé. Naptári határidők nem ismertek.

| Hét | Feladat | Elvárt eredmény |
| --- | --- | --- |
| 3. | ESP32 és firmware; idő-, memória- és hibamérő modul | Működő kiinduló környezet és mérési alap. |
| 4. | USB-UART és UI-váz; adatforrás, modellfuttatás, mérés szétválasztása | Moduláris PC-MCU kapcsolat. |
| 5. | MLP tanítása tanítóadaton; INT8-export; PC-s referencia | Exportált és ellenőrzött első modell. |
| 6. | Élő grafikonok, terhelési profilok, CSV-export; próbamérések | Használható mérési és megjelenítési folyamat. |
| 7. | **Mérföldkő 1: v0.1** | ESP32 + 1 modell; rögzített tesztadat; PC-s ellenőrzés; élő idő-/RAM-grafikon; export. |
| 8. | NPU-panel, fordító és művelettámogatás ellenőrzése; mintafuttatás | Igazolt NPU-s fejlesztési alap. |
| 9. | Kompakt CNN és döntési fa; közös tesztadat, PC-s referencia, portolás | További összehasonlítható modellek. |
| 10. | CPU/NPU-módok; automatikus tesztsor; terhelésvizsgálat | Ismételhető mérési automatizálás. |
| 11. | Mérési kampány: idő, memória, helyesség, stabilitás; műszerrel energia | Nyers mérési adatok és futási metaadatok. |
| 12. | Gyorsulás, határidők, erőforrásigény és tesztminőség értékelése | Alátámasztott összehasonlítás. |
| 13. | Dokumentálás, reprodukálhatóság; III. félévi illesztés előkészítése | Újrafuttatható projekt és dokumentáció. |
| 14. | **Mérföldkő 2: v1.0** | 2 MCU és legalább 2 közös neurális modell; jármű nélküli összehasonlító mérések, grafikonok, export és jegyzőkönyv. |

Az NPU-s panelnek legkésőbb a 8. hétre rendelkezésre kell állnia. Késéskor a CPU-s mérések és a portolás előkészítése folytatható, az NPU-összehasonlítást át kell ütemezni. A két MCU-s mérföldkő ettől még nem tekinthető teljesítettnek.

## 9. Javasolt fejlesztési munkacsomagok a kezdéshez

Ez a bontás a rögzített terv végrehajtását segíti. A meglévő eredmények alapján rövidíthető; nem állítja, hogy bármelyik lépés már megtörtént.

### A. Környezet és hardver azonosítása

**Cél:** kideríteni, pontosan mire lehet építeni.

Kérdezd meg az operációs rendszert, a panel pontos típusát/feliratát, az USB-kapcsolatot és az eddig telepített eszközöket. Ha nem ismert a panel, kérj képet vagy feliratot. Kérd be a meglévő projektkönyvtárat, verziókat és esetleges hibát.

**Kimenet:** rövid környezetleírás a tényleges panellel, célchippel, soros porttal, Python-, ESP-IDF- és komponensverziókkal. Ismeretlen adatok maradjanak ismeretlenként jelölve.

**Ellenőrzés:** az SDK elérhető, a panel felismerhető; az első hivatalos alapminta fordítása, feltöltése és soros kimenete működik. Ez a környezetet igazolja, nem a saját modellt.

### B. Következtetési mintafuttatás és mérő firmware

**Cél:** működő kiindulás a saját MLP előtt.

A választott ESP-IDF/`esp-tflite-micro` verzióhoz tartozó hivatalos mintával ellenőrizd a következtetés futását. Ezután kis modulokban alakítsd ki az időmérést, a memóriaadatok rögzítését és a hibakódokat. A soros kiírás kerüljön a mért szakaszon kívülre. Nagy adatkészletet ne feltételezz az ESP32 RAM-jában: a pufferelést a tényleges kapacitáshoz kell igazítani.

**Kimenet:** fordítható, feltölthető firmware; értelmezhető nyers idő-, memória- és hibainformáció; rögzített buildkonfiguráció.

**Ellenőrzés:** ismételt futások befejeződnek, nincs váratlan újraindulás, az idő- és memóriaértékek egysége és mérési helye ismert. Minta- vagy mesterséges munkaterhelés eredményét ne címkézd a saját MLP mérésének.

### C. PC-s szabályreferencia és adatgenerátor

**Cél:** a rögzített szabályból ellenőrzött, reprodukálható adatút legyen, legkésőbb az 5. heti tanítás előtt.

Először valósítsd meg és ellenőrizd a címkézőt az 5.3. szakasz eseteivel. Utána készíts kis generált menetszakaszt, majd ablakokat; ellenőrizd a döntés előtti állapotot, az időrendet és a következő mintában megjelenő frissítést. Véglegesítsd a nyitott adatsémát és a kezdeti ablakok kezelését, majd készítsd el a teljes generálást és a csoportos adatfelosztást.

**Kimenet:** generátor, szabályreferencia, konfiguráció, tanító/validációs/teszt szétosztás, osztályszámok és lezárt tesztkészlet. Javasolt fájlonkénti ellenőrzőösszeggel megjelölni az adatverziót.

**Ellenőrzés:** azonos seed és konfiguráció azonos adatot ad; nincs menet- vagy változatátfedés a részhalmazok között; nincs jövőbeli adat; a címkék egyeznek a referenciával. A hibatesztek ne szennyezzék címkézett érvényes mintaként a minőségmérést.

### D. Soros adatút és UI-váz

**Cél:** egy ismert ablak eljusson a PC-ről az MCU-ra, és az azonosítható eredmény visszaérkezzen.

Először UI nélkül, kis PC-s parancssori klienssel érdemes igazolni a kommunikációt. Rögzítsd az üzenetkeretezést, az ablak- és futásazonosítókat, az adattípust, a küldési sorrendet, a hibaválaszokat és az időtúllépést. Ezután kapcsolódjon hozzá a 4. heti UI-váz; a kommunikációs és naplózó réteg önállóan is működjön.

**Kimenet:** soros protokoll leírása, működő PC-MCU próba és kezdeti felület.

**Ellenőrzés:** bemenet és válasz egyértelműen párosítható; hibás vagy megszakadt átvitel észlelhető; a felület nem akadályozza az adatgyűjtést; a UART-várakozás elkülönül a feldolgozási időtől.

### E. Első MLP és ESP32-integráció

**Cél:** ugyanaz a tanított, INT8-kvantált modell ellenőrizhetően fusson PC-n és ESP32-n.

A rétegeket a támogatott műveletekhez és a rendelkezésre álló memóriához válaszd. A tanítórészen taníts; a validációs részt használd a modellválasztáshoz. Az INT8-kalibrációhoz csak tanítóadat kerüljön. Őrizd meg a modellt, az előfeldolgozás paramétereit, a kvantálási adatokat, az osztálysorrendet és a konverziós konfigurációt. A PC-n ellenőrzött INT8-modellt portold a firmware-be.

**Kimenet:** modellartefaktum, PC-s referenciakimenetek, működő ESP32-futtatás és eltéréskimutatás.

**Ellenőrzés:** azonos ablakokon, azonos előfeldolgozással vizsgáld az eltérést. A rossz címkeegyezést és a PC/MCU közötti portolási hibát külön elemezd. A végső tesztet ne használd ismételt modellhangolásra.

### F. Mérési lánc és v0.1 lezárása

**Cél:** az ESP32 + 1 modell teljes folyamata kezelhető és dokumentálható legyen.

Kapcsold össze a terhelési profilokat, az élő idő-/RAM-grafikonokat és az exportot. Rövid próbamérések után futtasd a rögzített protokollt. A mérföldkövet a 7. heti feltételek alapján ellenőrizd, és rögzítsd az ismert korlátokat. Csak ezután tekintsd stabil alapnak az NPU-s és második modelles bővítéshez.

## 10. Javasolt projektszerkezet és megőrzendő eredmények

A következő útvonalak ajánlások; nem létező fájlok felsorolása. Már meglévő projekt esetén annak szerkezetét használd, ha megfelelő.

| Útvonal | Feladat |
| --- | --- |
| `README.md` | Telepítés, fordítás, futtatás és a projekt áttekintése. |
| `config/` | Generálási, modell- és mérési konfigurációk. |
| `pc/reference/` | Determinisztikus címkéző és PC-s modellreferencia. |
| `pc/data/` | Generálás, adatellenőrzés, felosztás, ablakképzés. |
| `pc/training/` | Modellépítés, tanítás, kvantálás, export, kiértékelés. |
| `pc/transport/` | Soros kommunikáció. |
| `pc/measurement/` | Tesztsorok, naplózás, statisztikák, export. |
| `pc/ui/` | Kezelőfelület és grafikonok. |
| `firmware/esp32/` | ESP-IDF-projekt, modellfuttatás és MCU-mérés. |
| `firmware/npu_target/` | A később kiválasztott NPU-s cél megvalósítása. |
| `data/`, `models/`, `results/` | Verziózott adatok, modellek és elkülönített mérési futások. |
| `tests/` | A címkézés, időrend, adatfelosztás és PC/MCU-egyezés lényegi ellenőrzései. |
| `docs/` | Protokoll, döntésnapló, környezetleírás, kétheti beszámolók. |

A forráskódot és konfigurációkat érdemes Gitben követni. A nagy adat- és modellfájlok kezelését külön döntsd el; ellenőrzőösszeggel és verzióazonosítóval mindenképpen legyenek a kódállapothoz köthetők.

Egy mérési eredményhez legalább a következők tartozzanak:

- futásazonosító és dátum; kód-/firmware-verzió;
- eszköz és végrehajtási mód; órajelek, SDK és futtatókörnyezet;
- modellazonosító/verzió, kvantálás, előfeldolgozás;
- adatverzió, ablaksorrend, mérési profil, bemelegítő és mért futások száma;
- nyers eredmények, hibák, kimaradások és az alkalmazott mérési határok;
- összesítés: statisztikák, minőség, memória, ismert korlátok.

A kétheti beszámolóban külön szerepeljen a tervezett feladat, az elvégzett munka, annak bizonyítéka, az eltérés/akadály és a következő két hét célja. Csak ténylegesen elkészült munkát fogalmazz meg elvégzettként.

## 11. Az új munkamenet első lépése

Az első válaszodban legfeljebb néhány mondatban jelezd, hogy a 3. heti fejlesztés következik. Ne ismételd meg az egész dokumentumot és ne kezdd újra a témaválasztást.

Ha a következő adatok még hiányoznak, legfeljebb három tömör kérdéssel tisztázd őket:

1. Milyen operációs rendszeren és verzión fogunk fejleszteni?
2. Pontosan milyen ESP32-panel van kéznél, és csatlakoztatható-e most a géphez?
3. Mi van már telepítve vagy elkészítve: ESP-IDF, Python-környezet, mintaprojekt, saját kód vagy adatok; van-e jelenlegi hiba?

A válaszok után az **A munkacsomag** legközelebbi hiányzó lépésével kezdj. Ha a környezet már működik, a **B munkacsomagra** térj át. Ha a hardver átmenetileg nem elérhető, haladj a **C munkacsomag** PC-s referencia- és adatfeladataival; ezt ne nevezd hardveres igazolásnak. Az NPU részleteit akkor tisztázd, amikor a modell- és eszközkompatibilitás tervezéséhez szükséges, a 8. heti függőséget szem előtt tartva.

**Az egyes fejlesztési válaszok javasolt szerkezete:**

1. Most ezt érjük el: egy konkrét eredmény.
2. Ezért szükséges: rövid kapcsolat a projekttel.
3. Ezeket a lépéseket végezd el: fájlok, kód és parancsok.
4. Így ellenőrizd: várt viselkedés, releváns kimenet.
5. Ezt küldd vissza / ezt jegyezzük fel: a folytatáshoz szükséges bizonyíték.

Ne kérj minden kis részlethez külön jóváhagyást. A visszajelzést ott várd meg, ahol a következő lépés a valódi futási eredménytől függ.

## 12. Frissíthető állapot és munkamenet-átadás

A következő blokk **a jelenlegi, forrásokból ismert induló állapotot** tartalmazza. Minden érdemi fejlesztési alkalom végén frissítsd a tényleges eredményekből, hogy a következő LLM ugyanonnan folytathassa.

```yaml
context_version: "1.0"
last_updated: "2026-09-22"
semester: 2
next_planned_week: 3
current_phase: "fejlesztés indítása"

completed:
  - "I. félévi Edge AI / TinyML szakirodalmi szakasz"
  - "II. félévi 1-2. hét előkészítése és specifikációja"
  - "Laborötlet konzulensi elfogadása a beszámoló szerint"

implementation_evidence:
  code_received: false
  dataset_received: false
  trained_model_received: false
  hardware_run_verified: false
  measurement_results_received: false

environment:
  os: "ismeretlen"
  board_family: "ESP-WROOM-32 alapú ESP32"
  exact_board: "ismeretlen"
  serial_port: "ismeretlen"
  python_version: "ismeretlen"
  esp_idf_version: "ismeretlen"
  esp_tflite_micro_version: "ismeretlen"
  npu_board_and_sdk: "nyitott"

artifacts:
  repository_or_project_path: "nem ismert"
  last_working_commit: "nincs átadva"
  data_version: "még nincs igazolva"
  model_version: "még nincs igazolva"
  latest_measurement: "nincs átadva"

current_blocker: "A tényleges fejlesztőkörnyezet és a meglévő fájlok még nem ismertek."
next_concrete_action: "OS, pontos panel és telepített környezet tisztázása; első működő ESP32-minta."
pending:
  - "Adatgenerátor és ellenőrzött szabályreferencia"
  - "Adatfelosztás, ablakképzés és lezárt tesztkészlet"
  - "Hardveres kompatibilitási próba és mérő firmware"
  - "Soros adatút, UI, modellfejlesztés és későbbi mérési kampány"
  - "NPU-s panel és SDK biztosítása legkésőbb a 8. hétre"
```

A `false` értékek azt jelentik, hogy e kontextushoz nem érkezett megvalósítási bizonyíték; nem azt, hogy a felhasználónál biztosan semmi nem létezik.

Egy későbbi átadásban szerepeljen a legutóbbi sikeres parancs, az ellenőrzés eredménye, az érintett fájlok és verziók, az aktuális hiba, az új döntések indoka és a következő egyetlen végrehajtható feladat. A megoldott akadályokat töröld az aktuális akadályok közül, a döntéseket őrizd meg a naplóban.

## 13. A forrásokban megnevezett műszaki támpontok

Ezek az eredeti PDF-ek hivatkozási támpontjai; ez a kontextus nem végezte el a dokumentációk új webes ellenőrzését. Megvalósításkor a pontos, aktuális hivatalos oldalt és a használt verziót rögzíteni kell.

- Espressif: ESP32-WROOM-32; TensorFlow Lite Micro for Espressif Chipsets.
- Google AI Edge: Post-training integer quantization.
- MLCommons: MLPerf Tiny, mint az F1-ben megnevezett mérési támpont.
- Qt: QSerialPort; PyQtGraph dokumentáció.
- Alternatív felületekhez: Dash Live Updates; Streamlit Fragments.

## 14. Rövid indítóüzenet a felhasználótól

Az alábbi szöveg opcionálisan bemásolható e fájl csatolása mellé:

> Olvasd el a csatolt projektkontextust, és abból kiindulva segíts megvalósítani a projektet. Az első két hét előkészítése kész; most a 3. heti fejlesztés indul. Először tisztázzuk a fejlesztőkörnyezetemet és az ESP32-panelem típusát, majd egyenként vezess végig a szükséges lépéseken. Mindig mondd meg, mit kell létrehoznom vagy futtatnom, hogyan ellenőrzöm az eredményt, és mit küldjek vissza a folytatáshoz. A kész specifikációt használd alapként, a tényleges megvalósítás állapotát pedig a fájljaim és a futási eredmények alapján vezesd.
