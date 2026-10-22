# #5 ellenőrzés és átadás — 2026-10-22

A mérőmodul hostos és paneles ellenőrzése sikeres. Az ESP32-D0WD-V3
(rev. v3.1, 4 MB flash) panelen a live próba három ablakot, a benchmark
400 bemelegítő és 12000 mért ütemezett feladatot számolt el. A terhelés
**mesterséges 25 ms CPU-terhelés, nem saját MLP-mérés**. A saját modell
integrációja a #7 feladata.

A jogosultsági akadályt a felhasználó a kért port-ACL beállításával oldotta
fel. A valódi futás ezután watchdog-hibát tárt fel a hosszú UART-exportban;
a javítás és a paneles red → green regresszió részleteit a
[paneles jegyzőkönyv](hardware-ee4cf53/verification.md) rögzíti.

## Aktuális ellenőrzési eredmények

| Ellenőrzés | Eredmény |
| --- | --- |
| Teljes regresszió | 70 teszt, 52,009 s, OK; 7 GUI-skip és 1 külön indítandó hardveres teszt kihagyva |
| Külön paneles watchdog-regresszió | Javítás előtt FAIL, utána PASS, 25 s-os reprodukció |
| ESP-IDF v5.5.1 benchmark/live build | Mindkettő sikeres |
| Chip-/flashazonosítás és feltöltések | ESP32-D0WD-V3, 4 MB; flash-visszaellenőrzések sikeresek |
| Paneles live mód | 3/3 ablak ok, valódi idő- és memóriaadatok |
| Paneles benchmark | 16 sorozat, mind a 12400 ütemezett feladat elszámolt, szigorú profiler-ellenőrzés sikeres |
| UART-csend | 16 benchmark- és 3 live-végrehajtási intervallumban nincs fogadott adat; host/USB-idő és MCU-idő eltérése <1 ms |
| Nyers naplók | Egy várt boot/futás módonként; nincs watchdog, panic, brownout vagy heap-hiba |
| Verziók és ellenőrzőösszegek | Elkülönített eredeti/UART-javított/paneles manifestek, friss teljes hashlista |

Az UART-csend fizikai CP2102 kapcsolaton, fogadott bájtok monoton host-
időbélyegeiből megfigyelt csend. Ez nem elektromos élidőmérés vagy jövőbeli
WCET-igazolás. A Boya flash általános driverére vonatkozó bootfigyelmeztetés
megmaradt; a visszaellenőrzött feltöltés és mindkét futás sikeres.

## Forrás- és bizonyítékverziók

- **Eredeti:** `73aa42573aed0bc624c4ff1a21d3dda03301a728`.
  Az [eredeti manifest](original-73aa425/manifest.json), hashlista és
  jegyzőkönyv bytepontos másolata az `original-73aa425/` alatt van.
  A gyökérbeli korábbi buildnaplók és jelentések ehhez az állapothoz tartoznak.
  A régi binárisokat a buildkönyvtárak újrafordítása felülírta; elérhetőségüket
  nem állítjuk. Az archivált jegyzőkönyvek relatív linkjeit az eredeti
  Git-verzió könyvtárszerkezetében kell értelmezni.
- **UART-szünet javítása:** `4cb661c271551975202d90b6342ee83b18ab5a9f`.
  A [manifest](review-4cb661c/manifest.json), a buildnaplók, sdkconfigok,
  méretadatok, friss hostjelentések és az akkori jegyzőkönyv a
  `review-4cb661c/` alatt vannak. A nagy artefaktumok külön másolatai a
  `results/issue-5/review-4cb661c/` alatt maradnak.
- **Paneles watchdog-javítás:** `ee4cf53` (teljes azonosító a manifestben).
  Az [aktuális manifest](hardware-ee4cf53/manifest.json), buildnaplók,
  sdkconfigok, méretadatok, red/green és teljes tesztnaplók, valamint a
  hardveres jelentések a `hardware-ee4cf53/` alatt vannak. A nagy artefaktumok
  a `results/issue-5/hardware-ee4cf53/` alatt maradnak. A manifest külön
  jelöli a korábbi, hibás `4cb661c` paneles diagnosztikai felvételeit.

A gyökérbeli `manifest.json` az aktuális paneles manifest byteazonos
másolata. A `source_commit` és a `source_sha256` együtt azonosítja a tényleges
fordítási forrást; a bootban szereplő `ee4cf53-dirty` leíró a még nem
commitolt bizonyítékdokumentációt is érzékeli. A feltöltött ELF bootban
közölt hash-prefixe egyezik a megőrzött ELF ellenőrzőösszegével.

A tartós helyi artefaktumarchívum helyét, méretét és SHA-256 azonosítóját az
[archive.json](hardware-ee4cf53/archive.json) rögzíti. Nagy nyers napló vagy
bináris nem kerül Gitbe. Az archívum a repository gyökerében kibontható;
megőrzi a manifestekben hivatkozott `results/issue-5/...` útvonalakat.

## Reprodukálható ellenőrzés

A jelenlegi teljes Gitben megőrzött bizonyítékcsomag, beleértve az eredeti
metaadatokat és az új verziókat:

```bash
sha256sum -c docs/evidence/issue-5/SHA256SUMS
python3 -m unittest discover -s tests -p test_measurement_evidence.py -v
```

Az aktuális forrás és a megőrzött helyi artefaktumok ellenőrzése a repo
gyökerében, szükség esetén a helyi archívum kibontása után:

```bash
python3 - <<'PY'
import hashlib, json, subprocess
from pathlib import Path
m = json.loads(Path('docs/evidence/issue-5/manifest.json').read_text())
for name, expected in m['source_sha256'].items():
    committed = subprocess.check_output(['git', 'show', m['source_commit'] + ':' + name])
    assert hashlib.sha256(committed).hexdigest() == expected, name
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
for name, metadata in m['local_artifacts'].items():
    data = Path(name).read_bytes()
    assert len(data) == metadata['bytes'], name
    assert hashlib.sha256(data).hexdigest() == metadata['sha256'], name
print('Current source and preserved local artifact hashes OK')
PY
```

A korábbi `review-4cb661c` manifest forrásai a benne megadott Git-commitból
ellenőrizendők; nem a később módosult munkafából. Az eredeti hashlista az
eredeti fájlokon, külön munkakönyvtárban ellenőrizhető:

```bash
original_dir=$(mktemp -d /tmp/gearshift-issue5-original.XXXXXX)
git archive 73aa42573aed0bc624c4ff1a21d3dda03301a728 | tar -x -C "$original_dir"
(cd "$original_dir" && sha256sum -c docs/evidence/issue-5/SHA256SUMS)
```

A visszaállítás a Gitben megőrzött forrást és bizonyítékot állítja elő,
nem a régi, nem verziózott binárisokat. Új fordításhoz a kívánt forráscommit
külön munkapéldánya és a [dokumentált buildrecept](../../measurement-module.md)
használandó. Új fordítás saját manifestet kap: a buildidő és a Git-leíró
miatt nem ígérünk byteazonos új binárist.

## TDD és átadás

A felhasználó jóváhagyta a publikus firmware JSONL/profiler, illetve a
bizonyítékellenőrző parancsok tesztelési határát. A review javításai:

- A teljes UART-szünetből hiányzó fejléc/TX-drain: 7 ms-os virtuális
  átvitellel bukó regresszió, majd teljes `series_end.uart_wait_us` és
  profiler `complete` jelölés; régi exportnál `before_header`.
- Hibás szünetadatok és régi/új export megkülönböztetése: külön red → green
  szeletek, a `review-4cb661c` bizonyítékban rögzítve.
- Hiányzó verziózott manifest és elavult hashlista: előbb hiányzó manifest,
  majd konkrét `verification.md: FAILED`, utána sikeres forrás- és
  hashlista-ellenőrzés. A red/green naplók verziózottan megmaradnak.
- Paneles elfogadás: a fizikai próba watchdog-hibát reprodukált; a minimális
  exportjavítás után a rövid regresszió és a teljes kampány is sikeres.

A mérőmag `run()` interfésze és mérési szakasza változatlan. A saját modell
elő-/utófeldolgozása, a #4 vezérlőprotokoll firmware-illesztése és a saját
modell portolási helyessége a #7 integrációja. A mesterséges túlterhelés
nem tanult modell teljesítménye. PR-merge és issue-lezárás nem történt.
