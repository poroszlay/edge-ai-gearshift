---
title: "Mesterséges intelligencia alkalmazása a mikrokontrolleres alkalmazásokban – témaleírás és II. félévi ütemterv"
document_type: projektterv
semester: 2
source_file: "projektmunka_temavazlatpdf(1)"
status: "terv; a modellek, metrikák és heti feladatok projektjavaslatok"
---

# Mesterséges intelligencia alkalmazása a mikrokontrolleres alkalmazásokban

## Téma és cél

Autonóm járművek optimális irányításának kiegészítése beágyazott AI-algoritmusokkal; a feladatra és erőforrásokra optimalizált megoldások kutatása és összehasonlítása. A későbbi célalkalmazás az elektromos mikrobusz fokozatváltási döntéseinek optimalizálása környezeti és belső járműparaméterekből.

**Négy félév:** I. Edge AI / TinyML szakirodalom (elvégezve); II. laboratóriumi tesztalkalmazás; III. hozzáférés a mikrobuszhoz, implementáció és ellenőrzés; IV. összesített kiértékelés és diplomamunka.

## A II. félév vizsgálati terve – jármű nélkül

- **Hardver:** ESP-WROOM-32 alapú ESP32, NPU nélkül [1], valamint később érkező NPU-s MCU.
- **Modellek:** kis MLP és kompakt CNN, INT8; CPU-s döntési fa összevetéshez.
- **Tesztelés:** mentett mesterséges vagy nyilvános adatok; tanítás és referenciafuttatás PC-n, következtetés az MCU-n.
- **Korlát:** a járműves döntésminőség és a tényleges időzítési követelmények ellenőrzése a III. félév feladata.

## Javasolt metrikák [2]

- **Idő [ms]:** inferencia és teljes MCU-feldolgozás (elő-/utófeldolgozással); medián, p95, mért maximum.
- **Memória [KiB]:** statikus RAM, modell-munkaterület és futás közbeni használat külön; modell-/programméret.
- **Helyesség:** eltérés a PC-s INT8-kimenettől; címkézett tesztadaton makro-F1 és tévesztési mátrix.
- **Terhelés:** inferencia/s; határidőre nem teljesült / összes ütemezett feladat [%].
- **Stabilitás:** hibák, memóriaváltozás.
- **Energia [mJ/inferencia]:** opcionális, külső műszerrel, rögzített tápági mérési határon.

## UI-választás és működés

| Megoldás | Értékelés |
|---|---|
| PySide6 + pyqtgraph [3–4] | Javasolt: helyi PC-s eszközvezérlés, soros kapcsolat és élő grafikonok. |
| Dash + Plotly [5] | Böngészős dashboardhoz jó; külön adatgyűjtő réteggel. |
| Streamlit [6] | Gyors elemző prototípus; a folyamatos gyűjtést külön kell kezelni. |

**Funkciók:** USB-UART; adat-, modell- és eszközválasztás; indítás/leállítás; élő grafikonok és összehasonlítás; CSV/JSON-export.

**Laborprofilok:** `T = D = 10/20/50/100 ms`; `T`: indítási periódus, `D`: válaszadási határidő. Kísérleti terhelések, járműkövetelménytől függetlenül.

**Mérési protokoll:** modellenként azonos bemenet, súlyok, INT8 és 1-es batch; rögzített órajelek és szoftververziók; 100 bemelegítő + 3 × 1000 mért futás. MCU-időmérés a kész eredményig, NPU-adatmozgatással, soros küldés nélkül.

**Gyorsulás:** `tCPU / tNPU`, azonos statisztikából. Eltérő panelek rendszerszintű összevetése; az NPU hatásához, ha támogatott, azonos panelen CPU/NPU-mérés; CPU-ra eső műveletek jelölése.

## 14 hetes munkaterv és mérföldkövek

| Hét | Logikai egység | Feladat és elvárt eredmény |
|---|---|---|
| 1. | Előkészítés | Tesztfeladat, bemenet/kimenet, PC-s referencia és mérési protokoll terve. |
| 2. | Előkészítés | Rögzített tesztadatok, laborprofilok; modellek és NPU/SDK egyeztetése. |
| 3. | Fejlesztés | ESP32 és firmware; idő-, memória- és hibamérő modul elkészítése. |
| 4. | Fejlesztés | USB-UART, UI-váz; adatforrás, modellfuttatás és mérés szétválasztása. |
| 5. | Fejlesztés | MLP tanítása tanítóadaton, INT8 export; ellenőrzés PC-s referenciával. |
| 6. | Fejlesztés | Élő grafikonok, terhelési profilok és CSV-export; próbamérések. |
| 7. | Mérföldkő 1 | v0.1: ESP32 + 1 modell; rögzített tesztadat, PC-s ellenőrzés, élő idő-/RAM-grafikon és export. |
| 8. | Bővítés | NPU-s panel, fordító és művelettámogatás ellenőrzése; mintafuttatás. |
| 9. | Bővítés | Kompakt CNN és döntési fa; közös tesztadat, PC-s referencia és portolás. |
| 10. | Bővítés | CPU/NPU-módok, automatikus tesztsor és laboratóriumi terhelésvizsgálat. |
| 11. | Mérés és lezárás | Mérési kampány: idő, memória, helyesség, stabilitás; műszerrel energia. |
| 12. | Mérés és lezárás | Gyorsulás, határidők, erőforrásigény és tesztadaton mért minőség értékelése. |
| 13. | Mérés és lezárás | Dokumentálás, reprodukálhatóság; III. félévi járműillesztés előkészítése. |
| 14. | Mérföldkő 2 | v1.0: 2 MCU, legalább 2 közös neurális modell; jármű nélküli összehasonlító mérések, grafikonok, export és jegyzőkönyv. |

**Függőség:** az NPU-s panel legkésőbb a 8. hétre szükséges. Késés esetén CPU-mérések és portolási előkészítés folytatható; az NPU-összehasonlítás átütemezendő.

## Műszaki források (eredeti dokumentumban: 2026.09.13.)

1. Espressif: ESP32-WROOM-32.
2. MLCommons: MLPerf Tiny.
3. Qt: QSerialPort.
4. PyQtGraph.
5. Dash: Live Updates.
6. Streamlit: Fragments.

> **LLM kontextusmegjegyzés:** Ez a fájl a projekttervet rögzíti, nem igazolja a tervezett feladatok elvégzését vagy a mérési eredményeket. A részletes, 1–2. heti specifikációt a `projektmunka_elorehaladasi_dokumentacio_masodik_het.md` tartalmazza.
