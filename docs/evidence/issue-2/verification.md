# #2 ellenőrzési és átadási napló

Dátum: 2026-10-18. Ág: `feat/issue-2-esp32-bringup`.
Külön worktree: `/tmp/edge-ai-gearshift-issue-2`, kiindulás: `dda8783`.
A fő munkapéldány meglévő, nem követett tervezési dokumentuma változatlan.

## Elfogadási feltételek

| Feltétel | Tényleges állapot | Bizonyíték / hiány |
| --- | --- | --- |
| SDK-, komponens- és Python-verzió, források | Teljesült a PC-s környezetre | [Útmutató](../../esp32-bringup.md), lock, `environment.log`, `python-packages.txt` |
| Célchip, flashméret, port | **Hardveren nyitott** | `esp32` buildcél és 2 MiB konfiguráció; a CP2102 /dev/ttyUSB0 látható, a chip és a fizikai flashméret ismeretlen |
| Dokumentált alapminta-build | Teljesült | `basic-build.log` (tényleges parancs és buildkivonat) |
| Dokumentált következtetési build | Teljesült | `inference-build.log`, sikeres fordítás |
| Feltöltés és soros kimenet | **Nem teljesült, nyitott** | A soros port megnyitása EACCES hibával megállt; nem történt feltöltés |
| Ismételt következtetés, váratlan reset nélkül | **Nem teljesült, nyitott** | Hardveren megfigyelt futásszám: **0**; futásidő nem mért |
| Modell megnevezése és értelmezése | Teljesült | Hivatalos INT8 hello_world szinuszmodell; nem a saját fokozatváltási MLP |
| Reprodukálási lépések és akadályok | Teljesült | `docs/esp32-bringup.md`, jelen napló |

**A #2 teljes hardveres elfogadása nem igazolt; az issue nyitva marad.**
A sikeres keresztfordítás nem hardveres futtatás.

## Környezet és tényleges telepítési akadályok

Debian 13.7, x86_64; a részletes parancskimenet az `environment.log` fájlban.
Kezdetben nem volt `idf.py`, CMake és működő `python3 -m venv`.
A rendszerfüggőségek telepítési kísérlete `sudo: a password is required`
hibával megállt; rendszertelepítés nem történt.

A tényleges buildhez használt, rendszertelepítést nem igénylő parancsok:

```bash
# SDK-klónozás az útmutató szerint, ebben a futásban /tmp/gearshift-esp-idf alá.
curl -fL https://bootstrap.pypa.io/virtualenv/3.13/virtualenv.pyz -o /tmp/gearshift-virtualenv.pyz
python3 /tmp/gearshift-virtualenv.pyz /tmp/gearshift-build-venv
/tmp/gearshift-build-venv/bin/pip install cmake==3.31.6
export IDF_TOOLS_PATH=/tmp/gearshift-idf-tools
export PATH=/tmp/gearshift-build-venv/bin:$PATH
/tmp/gearshift-esp-idf/install.sh esp32
```

Az utolsó parancs telepítette a fordítóeszközöket, de az aktív venv miatt
az IDF saját Python-környezetének létrehozásánál megállt:
`This script was called from a virtual environment`.
A hiányzó Debian `ensurepip` miatt a venv-et a PyPA virtualenv készítette el,
majd a hivatalos IDF-telepítő telepítette bele a függőségeket:

```bash
python3 /tmp/gearshift-virtualenv.pyz /tmp/gearshift-idf-tools/python_env/idf5.5_py3.13_env --app-data /tmp/gearshift-virtualenv-cache
IDF_TOOLS_PATH=/tmp/gearshift-idf-tools /usr/bin/python3 /tmp/gearshift-esp-idf/tools/idf_tools.py install-python-env
. /tmp/gearshift-esp-idf/export.sh
bash firmware/esp32/bringup/build.sh basic
bash firmware/esp32/bringup/build.sh inference
```

A futáskor alkalmazott Espressif Python-korlátlista:
`espidf.constraints.v5.5.txt`; a tényleges telepített verziók:
`python-packages.txt`. A Python 3.13.5 megfelelt az IDF függőségellenőrzésének.
A fordító verzióját a buildnaplók rögzítik. Más Python nem volt szükséges.

## Buildellenőrzés eredménye

Mindkét dokumentált build ténylegesen lefutott, kilépési kódjuk 0.
Az alapminta binárisa 156096 byte (`0x261c0`), a következtetési mintáé
209248 byte (`0x33160`); mindkettő belefér az 1 MiB alkalmazáspartícióba.
Ez fájlméret, nem futás közbeni memóriaigény vagy mérési eredmény.
Fordító: Xtensa GCC 14.2.0, `esp-14.2.0_20241119`.
A TFLM upstream fordítása paraméterárnyékolási (`-Wshadow`) figyelmeztetéseket adott;
a build sikeres, a warningokat a kivonat megőrzi.

A verziózott `.log` fájlok sorvégi whitespace-je normalizált.
A `*-build.log` fájlok jelölt kivonatok, az eredeti teljes napló SHA-256
azonosítójával. A teljes naplók és `sdkconfig` fájlok helyben a
`results/issue-2/` alatt megmaradtak. Az effektív fő beállítások az
`effective-config.log` fájlban; a forrás, lock, konfiguráció és binárisok
azonosítói a `SHA256SUMS` fájlban. A teljes generált konfiguráció és bináris
nem került Gitbe. A bináris hash a konkrét buildet azonosítja; útvonal és
buildidő miatt új buildnél eltérhet.

További ellenőrzés: `bash -n firmware/esp32/bringup/build.sh`,
`git diff --check`, valamint az upstream C/C++ források bytepontos
összevetése. A minták futtatási logikáját nem módosítottuk.

## Hardver és következő lépés

A felhasználó által korábban megadott panel: WiFi-s ESP-WROOM-32,
`211-161007` jelöléssel. Ez nem ellenőrzött pontos fejlesztőpanel-típus.
A sandboxból a `python -m serial.tools.list_ports -v` eredménye
`no ports found` volt (`environment.log`). A sandboxon kívüli tényleges
ellenőrzés viszont CP2102 USB–UART eszközt talált (`host-ports.log`):

- Port: `/dev/ttyUSB0`.
- Stabil név: `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0`.
- USB VID:PID: `10C4:EA60`, sorozatszám: `0001`.
- Jogosultság: `root:dialout`, `crw-rw----`; `richie` nem tagja a `dialout` csoportnak.
- Az esptool `chip_id` és `flash_id` tényleges próbája EACCES hibával
  megállt (`chip-id.log`, `flash-id.log`). A CP2102 az USB-hidat azonosítja,
  nem bizonyítja a chip vagy flash típusát. Feltöltés nem történt.

Következő konkrét lépés: a felhasználó a saját termináljában futtassa:
`sudo setfacl -m u:richie:rw /dev/ttyUSB0`. Az agent nem tudja megadni
a sudo-jelszót. Ezután `chip_id` és `flash_id`, alapminta-feltöltés/soros
ellenőrzés, majd legalább 100 folyamatos szinuszkövetkeztetés megfigyelése.
USB-újracsatlakoztatás után az ideiglenes ACL-t újra be kell állítani.
A hardveres naplókat, valódi futásszámot és reseteket ezután lehet hozzáadni;
ezek nélkül nem jelölhető teljesnek az issue.
