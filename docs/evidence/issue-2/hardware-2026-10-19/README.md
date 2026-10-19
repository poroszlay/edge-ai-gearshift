# Hardveres futás – 2026-10-19

A #2 hivatalos mintáinak valódi ESP32-próbája. A következtetési modell
az esp-tflite-micro 1.3.5 INT8 hello_world szinuszmodellje, **nem a saját
fokozatváltási MLP**; nem portolási helyesség- vagy teljesítménymérés.
A legutóbbi állapotot a [verification.md](../verification.md) rögzíti.

## Reprodukálás ezen a gépen

A korábbi `/tmp` SDK és buildek hiányoztak. A hozzáférés ellenőrzése után
az ESP-IDF v5.5.1 környezetet állítottuk helyre, a rögzített komponensekkel.
A felhasználó által megadott `setfacl` azonnal működött, logout nélkül.
Az alábbi parancsok Bashban, a worktree gyökeréből értendők:

```bash
export IDF_TOOLS_PATH=/tmp/gearshift-idf-tools
export PATH=/tmp/gearshift-hardware-venv/bin:$PATH
. /tmp/gearshift-esp-idf/export.sh
export GEARSHIFT_PORT=/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0
export GEARSHIFT_RUN="$PWD/results/issue-2/hardware-2026-10-19"
export GEARSHIFT_CAPTURE="$PWD/docs/evidence/issue-2/hardware-2026-10-19/capture_serial.py"
mkdir -p "$GEARSHIFT_RUN"
set -e
set -o pipefail
python -m esptool --chip auto --port "$GEARSHIFT_PORT" chip_id 2>&1 | tee "$GEARSHIFT_RUN/chip-id.log"
python -m esptool --chip auto --port "$GEARSHIFT_PORT" flash_id 2>&1 | tee "$GEARSHIFT_RUN/flash-id.log"
```

A tényleges kezdeti azonosításhoz az azonos esptool 4.12.0-t tartalmazó
`/tmp/gearshift-hardware-venv/bin/python` futott; a feltöltésekhez és a
rögzítéshez már az IDF saját Python-környezete. A chip ESP32-D0WD-V3 v3.1,
a flash 4 MiB, ezért a defaults a próba előtt 4 MiB-ra módosult.
Ha más chipet mérsz, ne töltsd fel automatikusan ezeket a binárisokat.

```bash
bash firmware/esp32/bringup/build.sh basic > "$GEARSHIFT_RUN/basic-build.log" 2>&1
bash firmware/esp32/bringup/build.sh inference > "$GEARSHIFT_RUN/inference-build.log" 2>&1
```

A következő parancsok **felülírják a panel programját**. Először az
alapmintát kell feltölteni, visszaellenőrizni és megfigyelni:

```bash
(
  cd firmware/esp32/bringup/basic/build
  python -m esptool --chip esp32 --port "$GEARSHIFT_PORT" --baud 460800 --before default_reset --after hard_reset write_flash @flash_args 2>&1 | tee "$GEARSHIFT_RUN/basic-flash.log"
  python -m esptool --chip esp32 --port "$GEARSHIFT_PORT" verify_flash 0x1000 bootloader/bootloader.bin 0x8000 partition_table/partition-table.bin 0x10000 hello_world.bin 2>&1 | tee "$GEARSHIFT_RUN/basic-verify-flash.log"
)
python "$GEARSHIFT_CAPTURE" "$GEARSHIFT_PORT" 18 "$GEARSHIFT_RUN/basic-monitor.log"
```

Ezután a következtetési minta következik, a panel programjának újabb
felülírásával:

```bash
(
  cd firmware/esp32/bringup/inference/build
  python -m esptool --chip esp32 --port "$GEARSHIFT_PORT" --baud 460800 --before default_reset --after hard_reset write_flash @flash_args 2>&1 | tee "$GEARSHIFT_RUN/inference-flash.log"
  python -m esptool --chip esp32 --port "$GEARSHIFT_PORT" verify_flash 0x1000 bootloader/bootloader.bin 0x8000 partition_table/partition-table.bin 0x10000 hello_world.bin 2>&1 | tee "$GEARSHIFT_RUN/inference-verify-flash.log"
)
python "$GEARSHIFT_CAPTURE" "$GEARSHIFT_PORT" 62 "$GEARSHIFT_RUN/inference-monitor.log"
```

A mellékelt `capture_serial.py` 115200 baudon, normál bootállapotban tartott
DTR-rel, 100 ms RTS/EN impulzussal indítja a panelt. Az UART-ot már a reset
elengedése előtt megnyitja; a `.log` a teljes, nyers soros bájtfolyam, nincs
szűrés, sorvég-normalizálás vagy hibasor-eltávolítás. A ROM-üzenet első
sorában indulási karaktertöredék is látszik; ezt is változatlanul megtartottuk. A `.log.json` az UTC
kezdést, monoton időtartamot és a beolvasott blokkok időpontját/offsetjét
rögzíti. Ez nem következtetési futásidőmérés; a blokkok időbélyegei UART-
megfigyelési időpontok. A port zárása a megfigyelés végét követi.

Az alapminta visszaszámlálás utáni `Restarting now.` és szoftveres resetje
szándékos. A következtetési mintában az indulás után minden újabb reset,
pánik, allokációs vagy Invoke-hiba sikertelen próbát jelent; a teljes
naplót kell ellenőrizni, nem csak a kimeneti sorok számát.

## Ellenőrzés és tényleges eredmény

```bash
python3 docs/evidence/issue-2/hardware-2026-10-19/analyze_capture.py docs/evidence/issue-2/hardware-2026-10-19
(cd docs/evidence/issue-2/hardware-2026-10-19 && sha256sum -c SHA256SUMS)
# A worktree-ben meglévő binárisokhoz és teljes helyi buildnaplókhoz:
sha256sum -c docs/evidence/issue-2/hardware-2026-10-19/ARTIFACT_SHA256SUMS
```

A mellékelt `analysis.json` a fenti elemző tényleges kimenete:
**124 folyamatos következtetés, 62,174 s rögzítés, 0 váratlan reset**.
A 20 elemű bemeneti sorrend hat teljes cikluson és további négy mintán
át egyezett; a kimenetek végesek. Az első és utolsó kimenet UART-blokkjának
megfigyelési távolsága 61,471 s. Az alapminta 18,159 s alatt egy szándékos
újraindulást végzett. Mindkét flash-visszaellenőrzés mindhárom szegmensre
`verify OK` eredményt adott. A teljes nyers soros naplókat külön is
ellenőriztük: allokációs/Invoke-hiba, pánik vagy későbbi boot nem látszik.

Mindkét boot Boya flashhez használt általános driverre figyelmeztet;
ez megmaradt a nyers naplóban. A buildben upstream `-Wshadow` warningok
voltak, sikeres fordítás mellett. A konkrét forrás-/projektverziókat és
a próba értelmezési korlátját a szülő [verification.md](../verification.md)
részletezi. A raw logok saját `.gitattributes` szabálya megőrzi a CRLF és
CRCRLF sorvégeket, valamint a portlista záró szóközeit.

## Állományok

A nyers azonosítási, feltöltési, flash-visszaellenőrzési és soros naplók itt
vannak. A két teljes generált `sdkconfig` külön snapshotként szerepel.
A buildnaplók jelölt kivonatok; a teljes eredetik hash-e és a feltöltött
binárisok hash-e külön manifestben azonosítja az adott futást. A korábbi
sikertelen EACCES naplók a szülőkönyvtárban változatlanul megmaradnak.
