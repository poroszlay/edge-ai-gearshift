---
title: "Projektmunka II. félév – előrehaladási dokumentáció, 1–2. hét"
document_type: elorehaladasi_dokumentacio
semester: 2
weeks: [1, 2]
source_file: "projektmunka_elorehaladasi_dokumentacio_masodik_het.pdf"
status: "specifikáció és előkészítési terv; a megvalósításra váró lépések külön jelölve"
---

# Előrehaladási dokumentáció – 1–2. hét

**Projekt:** Mesterséges intelligencia alkalmazása a mikrokontrolleres alkalmazásokban. Kéthetente bővülő haladási tervek és beszámolók.

## 1. fejezet – A laboralkalmazás előkészítése

A konzulens elfogadta a II. félévi laboralkalmazás ötletét. A mikrobusz a III. félévtől lesz elérhető; addig szintetikus menetszakaszokkal készülhet elő a beágyazott modellek összehasonlítása. **A számszerű beállítások kiinduló laborfeltevések.**

## 1. hét – Tesztfeladat, referencia és mérési protokoll

### Feladat és osztályok

Feltételezett, két előremeneti fokozatú elektromos hajtás következő döntésének becslése:

| Döntés | Döntésérték | Osztályindex |
|---|---:|---:|
| Visszaváltás | -1 | 0 |
| Tartás | 0 | 1 |
| Felváltás | +1 | 2 |

A vizsgálat az azonos adatokkal ESP32-n, majd NPU-s eszközön elérhető döntési minőséget, futásidőt és memóriaigényt értékeli. **A tényleges járműves energiamegtakarítás igazolása későbbi feladat.**

### Modellbemenetek

| Bemenet | Jelölés | Laborbeli tartomány / szabály |
|---|---|---|
| Sebesség | `v` | 0–80 km/h |
| Gyorsítási igény | `u` | 0–1, dimenzió nélküli igényjel |
| Útemelkedés | `s` | -10…+10% |
| Aktuális fokozat | `g` | 1 vagy 2 |
| Utolsó váltás óta eltelt idő | `τ` | másodperc; a modellbemenet 10 s-nál telítődik |

### Bemeneti ablak és szabályalapú referencia

- **Mintavétel:** 50 ms.
- **Egy döntés bemenete:** 20 egymást követő minta × 5 érték = 100 érték, időrendben, jövőbeli adat nélkül.
- **Címkézés:** a címkéző az utolsó 5 mintából átlagolja `v`, `u`, `s` értékét; `g` és `τ` a legfrissebb minta döntés előtti állapota.
- **Felváltási küszöb:** `v_fel = 30 + 20 × u_átlag + 0,5 × s_átlag` [km/h].
- **Visszaváltási küszöb:** `v_le = v_fel - 10` [km/h].

**Döntési sorrend:**

1. Ha `τ < 1 s`, a döntés **tartás (0)**.
2. Egyébként ha `g = 1` és `v_átlag > v_fel`, a döntés **felváltás (+1)**.
3. Egyébként ha `g = 2` és `v_átlag < v_le`, a döntés **visszaváltás (-1)**.
4. Minden más esetben **tartás (0)**.

**Határesetek:** küszöbegyezéskor tartás; `τ = 1 s` esetén a váltás már engedhető. Hiányos vagy érvénytelen bemenet külön hibajelzést kap (nem egy negyedik döntési osztály).

### Referencia-ellenőrző példák

| `v_átlag` | `u_átlag` | `s_átlag` | `g` | `τ` | Elvárt döntés és indok |
|---:|---:|---:|---:|---:|---|
| 45 km/h | 0,2 | 0% | 1 | 3 s | Felváltás: 45 > 34 km/h. |
| 20 km/h | 0,8 | 5% | 2 | 3 s | Visszaváltás: 20 < 38,5 km/h. |
| 34 km/h | 0,2 | 0% | 1 | 3 s | Tartás: egyenlőség a felső küszöbön. |
| 45 km/h | 0,2 | 0% | 1 | 0,3 s | Tartás: még nem telt el 1 s. |

### Mérési terv

- Modellenként azonos bemenet, súlyok és INT8-kivitel; `batch = 1`.
- Rögzített órajelek és szoftververziók.
- 100 bemelegítő és `3 × 1000` mért futás.
- Külön mérendő inferenciaidő és teljes MCU-feldolgozási idő: medián, p95, megfigyelt maximum.
- Mérendő RAM-igény és modell-/programméret.
- Az időmérés a kész eredményig tart, NPU-adatmozgatással, de soros küldés nélkül.
- Döntési minőség: makro-F1 és tévesztési mátrix.
- Portolás ellenőrzése: ugyanazon INT8-modell PC-s és MCU-s kimenetének összevetése.
- A szabálycímkékkel való egyezés **a referencia megtanulását** méri, nem valós járműves optimális működést.

## 2. hét – Tesztadatok, laborprofilok és megvalósítási döntések

### Adatterv

Python-generátor **fog előállítani** összefüggő gyorsítási, egyenletes haladási, emelkedős, lassítási és küszöb körüli menetszakaszokat; külön esetek vizsgálják a váltás utáni tiltást és a hibás jeleket.

A CSV minden sora tartalmazza a menetazonosítót, időbélyeget, öt bemenetet (`v`, `u`, `s`, `g`, `τ`) és az elvárt döntést. A fokozat és a váltási idő frissítése **csak a következő mintában** jelenik meg. Rögzítendő a véletlenmag, a konfiguráció és a címkéző verziója.

### Adatfelosztás

- Tanító/validációs/teszt arány: **70/15/15%**.
- Felosztás teljes menetszakaszok szerint, **az ablakok képzése előtt**.
- Egy menet és zajos változatai ugyanabba a részhalmazba kerülnek.
- Mindhárom osztály darabszámát ellenőrizni kell.
- A végső tesztkészletet le kell zárni.
- A normalizálás tanult paraméterei és az INT8-kalibráció mintái kizárólag a tanítórészből származnak [2].

### Adatút és terhelés

**Adatút:** PC előtölti az ablakokat USB-UART-on → MCU következtet és mér → PC naplóz → CSV/JSON-export.

A modellválasz **nem módosítja** a visszajátszott bemenetet.

**Laborprofilok:** `T = D = 10/20/50/100 ms`, ahol `T` az indítási periódus, `D` a határidő. Ezek **függetlenek az 50 ms-os jel-mintavételtől**.

Mérendő a határidőt túllépő vagy kimaradó feladatok aránya, az inferencia/s és a futási hibák. Az UART-várakozás külön naplózandó.

### Eszköz- és modellterv

- **ESP32 kiinduló környezet:** ESP-IDF + esp-tflite-micro [1].
- **Első neurális modell:** kis MLP, amely a 20 × 5 ablak 100 elemre lapított változatát kapja.
- **Későbbi modell:** kompakt CNN, amely ugyanezen ablak időbeli szerkezetét használja.
- **Összehasonlítási alapok:** CPU-s döntési fa és közvetlen szabályfuttatás.
- **NPU-s panel és SDK:** a konkrét típus nyitott. A rétegek, tensoralakok, INT8-támogatás, memória és CPU-ra kerülő műveletek ellenőrzése a típus ismeretében végezhető el.

### Átadás a 3. hétre: státusz és következő lépések

**E dokumentum szerint rögzített specifikáció:** feladat, címkézés, adatút és mérés.

**Még végrehajtandó:** adatgenerátor, lezárt adatkészlet és hardveres kompatibilitási próba elkészítése.

**3. hét tervezett kezdése:** ESP32-környezet beállítása, mintafuttatás, valamint idő-, memória- és hibamérő firmware-modul fejlesztése.

**Hardverfüggőség:** az NPU-s panelt legkésőbb a 8. hétre kell biztosítani; késésekor a CPU-s fejlesztés folytatható.

## Hivatkozások és dokumentumalap

A dokumentum alapja a csatolt 14 hetes ütemterv, az első két hét kontextusfájlja és a konzulensi elfogadásról adott visszajelzés.

Műszaki források (eredeti dokumentumban ellenőrizve: 2026.09.22.):

1. Espressif: *TensorFlow Lite Micro for Espressif Chipsets*.
2. Google AI Edge: *Post-training integer quantization*.

> **LLM kontextusmegjegyzés:** Az itt rögzített műszaki értékek laborfeltevések és specifikációk. Ne kezeld a tervezett adatgenerálást, hardveres mérést vagy modellportolást már elvégzett munkaként. A tágabb féléves tervet a `projektmunka_temavazlat.md` tartalmazza.
