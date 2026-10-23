# PySide6 mérőfelület és CSV-export (#8)

Telepítés és indítás a repó gyökeréből (Python 3.10+):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-ui.txt
.venv/bin/python -m gearshift.gui
```

Debian/Ubuntu alatt a venv létrehozásához a Python-verzióhoz tartozó
`python3-venv` rendszerkomponens szükséges. A CLI és szimulátor továbbra is
Qt nélkül fut. Linux grafikus környezetben a Qt platformfüggőségei is szükségesek.

## Felhasználói folyamat

1. Válaszd a beépített szimulátort, vagy indíts külön
   `python3 -m gearshift.simulator --port 8765` folyamatot és válaszd a TCP
   szimulátort a megfelelő host/port értékkel.
2. Válassz élő megfigyelést vagy előtöltött terhelésmérést. Benchmark esetén
   jelöld ki a kívánt T=D=10/20/50/100 ms profilokat; mindegyik az elfogadott
   100 bemelegítő + három 1000-es sorozatot futtatja.
3. Opcionálisan válassz saját, a kommunikációs szerződés szerinti JSONL
   ablakfájlt. Üresen élő módban 200, benchmarkban nyolc demoablakot használ.
   A beépített szimulátor virtuális feldolgozási ideje állítható; 25 ms
   beállítással a 10 és 20 ms profilban late/missed feladatok is megjelennek.
4. Indíts. Élő módban minden ablak után érkezik eredmény; a visszajátszás
   50 ms hostoldali szünete a mérésen kívül van. Benchmark esetén az execute
   előbb befejeződik, utána jön a fetch és a grafikonfrissítés. A szimulátor
   virtuális időben fut; nem kell 1000×T falióraidőt várni.
5. Leállításkor a kliens socketje megszakad, nincs automatikus újrapróbálás.
   A futás részleges, a már beérkezett eredmények megmaradnak. A végállapot
   és a timeout/kapcsolat-/eszközhiba szövege látható marad export után is.
6. Befejezés vagy leállítás után válassz CSV-exportot. Új futás új run_id-t
   kap és lecseréli a memóriában tárolt előző futást; előbb exportáld azt.

## Rétegek és elszámolás

`gui.Window → measurement.Session → client.Client → protocol.Wire`

A GUI nem képez modellbemenetet, nem implementál protokollt és nem számít
eszközoldali ütemezést. Ugyanazt a Client/batch/execute/fetch adatutat
használja, mint a CLI. A kliens új opcionális profilválasztása és
megszakításellenőrzése alapértelmezésben nem változtatja meg a CLI futását.
Az azonosított eszközhibaválaszok teljes üzenete is bekerül a receive naplóba.

A hálózat, bemenetolvasás és CSV-írás Python háttérszálon történik. A GUI
50 ms-os QTimerrel, ciklusonként legfeljebb 1000 eseményt dolgoz fel; a
korlátos (512 eseményes) értesítési sor telítődése csak a hostoldali,
execute-on kívüli adatátvitelt késleltetheti. Nem hoz létre eszközfeladatsort.
Bezáráskor a GUI aszinkron megvárja a leállást és az esetleges export végét.
A kapcsolódás feloldása és a fájlrendszerműveletek az operációs rendszer
visszatéréséig tarthatnak; ezek alatt az eseménykezelő tovább fut.

Az időgrafikon utolsó 2000 beérkezett feladatát mutatja, bemelegítéssel
együtt, ms egységgel. A vízszintes tengely beérkezési sorszám, nem egy
profilokon átívelő eszközidőrács. Missed/invalid_window esetén nincs kitalált
feldolgozási idő: a görbe megszakad. A memóriagrafikon az execute ack
ellenőrzött `simulated_memory_bytes` becslését mutatja byte-ban a kliens
`batch_memory` eseményéből, host eltelt idő szerint;
ez az előtöltött ablakok becsült mérete, nem teljes vagy szabad MCU-RAM.
A számlálók külön kezelik a live/warmup/measured fázist és a négy státuszt.
Hibás vagy hiányzó memóriamező hibás, részleges futást eredményez; a nyers ACK
exportálható marad, a felület pedig ismét indítható. A nyers receive események
közvetlenül nem kerülnek a memóriagrafikonra.

## CSV-séma és visszaolvasás

UTF-8, vessző elválasztó, fejléc, szabványos CSV-idézés. Egy sor egy kliens-
vagy futásesemény. A kereshető skalármezők: v, run_id, mode, simulated,
event, host_elapsed_ms, batch_id, phase, series, period_ms, index, window_id,
scheduled_ms, status, processing_ms, decision, decision_source, error,
request_id. Hiányzó mérés üres mező, nem nulla. Minden sor az eredeti `simulated` jelölést hordozza.

Az `event_json` az esemény teljes, veszteségmentes JSON-reprezentációja:
megmarad a bemeneti trip_id, a nyers minták, az ablaksorrend, a kérés/válasz,
az adagközi szünet, a memóriabecslés és a futásbeállítás is. Ez a kanonikus
visszaolvasási mező; a skaláros oszlopok a kézi keresést segítik.

```python
from gearshift.measurement import read_csv, summary
rows = read_csv('measurement.csv')
print(rows[-1]['event'])  # csak run_complete jelent teljes futást
print(summary(rows))     # (phase, period_ms, series) → státuszszámlálók
```

A scheduled darabszám minden státuszt egyszer tartalmaz, missed nem pótlódik.
Az export a meglévő fájlt sikeres írás után atomikusan cseréli le. Hiba esetén
az előző fájl megmarad, és külön exporthiba jelenik meg. A CSV nem módosítja
a futás sikeres/hibás/leállított végállapotát.

## Ellenőrzés és korlátok

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
```

A GUI-függőségek nélkül a GUI-tesztek skip állapotúak; az átadási ellenőrzés
telepített PySide6/pyqtgraph mellett futott. Részletes bizonyíték:
[issue-8 ellenőrzés](verification/issue-8.md).

A beépített és TCP szimulátor döntése `hold`/`simulator_stub`, eredete
kötelezően szimuláció. A #7 hozzáadta az ESP32 UART-választót, saját INT8
MLP-kimenettel és valódi idő-/memóriaadatokkal; részletei lent. A benchmark
legfeljebb nyolc rögzített ablakot ismétel, nem a teljes tesztadat
minőségellenőrzése.

A teljes eseménynapló RAM-ban marad az exportig, alkalmazásösszeomlás ellen
nem tartós. Saját bemenet legfeljebb 100000 ablak lehet; benchmarkban a
kliens nyolcas korlátja érvényes. Nagy élő bemenet sok memóriát használhat.
A megjelenített 2000 pontos korlát az exportot nem csonkolja. Az automatizált
átadás offscreen Qt-t használ, a natív fájlválasztókat tesztben helyettesíti;
asztali ablakkezelős és paneles kézi ellenőrzés nem történt.

## ESP32 UART (#7)

Az eszközválasztó harmadik eleme az ESP32 UART. Add meg a portot, az
elvárt modell SHA-256 azonosítóját és a firmware-rel egyező baudot
(alapérték: 921600). Új futás előtt reseteld a panelt és várd meg a bootot;
a portot másik terminál/monitor ne tartsa nyitva. A paneles választás
120 s-os kérés-timeoutot állít be a legfeljebb 100 s-os sorozatokhoz.

A fejléc és állapot ESP32-t, a grafikon mért MCU-feldolgozási időt, a
memóriagrafikon sorozat utáni szabad heapet mutat. Modell-/memóriahibának
nincs döntése vagy érvényes időgrafikon-pontja, de saját számlálója van.
A felület továbbra is ugyanazt a Client-et használja, mint a CLI,
nincs külön firmware-protokollja.

A CSV `event_json` mezője megőrzi az INT8 bemenetet/kimenetet, modell- és
adatverziót, nyers időpontokat és a teljes memóriaobjektumot is. Paneles
futásnál minden esemény `simulated:false`; a szimulátor adatai változatlanul
`simulated:true` jelölést kapnak. [Futtatás és paneles bizonyíték](esp32-inference.md).
