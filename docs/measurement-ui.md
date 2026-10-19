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
`simulated_memory_bytes` becslését mutatja byte-ban, host eltelt idő szerint;
ez az előtöltött ablakok becsült mérete, nem teljes vagy szabad MCU-RAM.
A számlálók külön kezelik a live/warmup/measured fázist és a négy státuszt.

## CSV-séma és visszaolvasás

UTF-8, vessző elválasztó, fejléc, szabványos CSV-idézés. Egy sor egy kliens-
vagy futásesemény. A kereshető skalármezők: v, run_id, mode, simulated,
event, host_elapsed_ms, batch_id, phase, series, period_ms, index, window_id,
scheduled_ms, status, processing_ms, decision, decision_source, error,
request_id. Hiányzó mérés üres mező, nem nulla. Minden sor `simulated=True`.

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

Nincs UART-/panelválasztó adapter a main kliensben: a felület beépített és
TCP eszközszimulátort kínál. Hardveres működés, valódi inferenciaidő/RAM,
tanult modell és portolási helyesség nincs igazolva; ezek a #4 integrációjára
várnak. A döntés továbbra is `hold`/`simulator_stub`. A szimulációs jelölés
nem kapcsolható ki. A benchmark legfeljebb nyolc rögzített ablakot ismétel;
nem a teljes tesztadat minőségellenőrzése.

A teljes eseménynapló RAM-ban marad az exportig, alkalmazásösszeomlás ellen
nem tartós. Saját bemenet legfeljebb 100000 ablak lehet; benchmarkban a
kliens nyolcas korlátja érvényes. Nagy élő bemenet sok memóriát használhat.
A megjelenített 2000 pontos korlát az exportot nem csonkolja. Az automatizált
átadás offscreen Qt-t használ, a natív fájlválasztókat tesztben helyettesíti;
asztali ablakkezelős és paneles kézi ellenőrzés nem történt.
