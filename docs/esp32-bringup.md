# ESP32 bringup – #2

## Cél és állapot

A [#2 issue](https://github.com/poroszlay/edge-ai-gearshift/issues/2) hivatalos
alapmintájának és következtetési mintájának reprodukálható projektje.
Ez a kompatibilitási próba **nem a projekt saját MLP-je**, nem igazol
portolási helyességet, döntési minőséget vagy hardveres teljesítményt.

A tényleges elfogadási állapot és a futtatási bizonyíték:
[ellenőrzési napló](evidence/issue-2/verification.md).
Hardveres feltétel csak a valódi panelről származó napló alapján teljesíthető.

## Verzióválasztás és hivatalos források

| Elem | Rögzítés | Indok / forrás |
| --- | --- | --- |
| ESP-IDF | v5.5.1, `fcae32885b0296b32044cb99ecbdc50d98dddb83` | [Hivatalos Linux setup](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32/get-started/linux-macos-setup.html), Python >=3.9 |
| esp-tflite-micro | 1.3.5, upstream `5f31ea08cee30ef3c2a1dfe7357f4be4048bc044` | [Verziózott registry](https://components.espressif.com/components/espressif/esp-tflite-micro/versions/1.3.5/readme), a verzió manifestje IDF >=5.0-t kér |
| esp-nn | 1.1.1 | A TFLM >=1.1.1 függőségét pontos verzióra rögzítjük |
| Python | 3.13.5, elkülönített IDF-környezet | A tényleges telepítés/build ellenőrzi a kompatibilitást; nem kellett más Python-verzió |
| CMake | 3.31.6 | Az IDF >=3.16 követelményét teljesíti |

Nem a legújabb verzió automatikus követése a cél, hanem újrafordítható
kompatibilitási alap. A tranzitív komponenseket a projekthez tartozó
`dependencies.lock` rögzíti. A források eredete:
[UPSTREAM.md](../firmware/esp32/bringup/UPSTREAM.md).

## Folytatás meglévő környezetből

Először a **hoston** ellenőrizd a portot és a hozzáférést; a sandboxban
hiányzó eszköz nem bizonyítja, hogy a hoston sincs port:

```bash
ls -l /dev/serial/by-id/ /dev/ttyUSB0
id
getfacl /dev/ttyUSB0
python3 -c 'import os; fd=os.open("/dev/ttyUSB0", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK); os.close(fd); print("OPEN OK")'
```

EACCES esetén a felhasználó saját termináljában:
`sudo setfacl -m u:richie:rw /dev/ttyUSB0`, majd ismételd meg a megnyitási
próbát. USB-újracsatlakoztatás után az ACL elveszhet. Az ACL önmagában
nem igazol sikeres chipazonosítást vagy futást.

A 2026-10-19-i [folytatás](evidence/issue-2/verification.md#hardveres-folytatás-2026-10-19)
ismét EACCES hibát adott. A korábban használt `/tmp`-beli SDK, toolchain,
worktree és binárisok már hiányoznak. Előbb ellenőrizd a meglévő SDK és
projektenkénti build/config/flash-argumentumok helyét és hash-eit; ha
megmaradtak, használd őket új telepítés és build nélkül. A korábbi hashlista
nem helyettesíti a hiányzó binárisokat. Ha valóban hiányoznak, az alábbi
rögzített környezet helyreállítása és új build indokolt; az új binárisokhoz
új hash-ek és teljes konfiguráció szükséges. A hosszabb távon szükséges SDK-t
és mérési bizonyítékot tartós könyvtárban őrizd, a `/tmp` törölhető.

## Telepítés Debianon

Bash terminál, a repó gyökerében. Az SDK-t és a toolchaint a repón kívül
tartsd. A `GEARSHIFT_SDK_ROOT` tetszőleges írható hely lehet.

```bash
sudo apt-get update
sudo apt-get install git wget flex bison gperf python3 python3-pip python3-venv cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0
export GEARSHIFT_SDK_ROOT="$HOME/gearshift-sdk"
mkdir -p "$GEARSHIFT_SDK_ROOT"
git clone --branch v5.5.1 --depth 1 --recursive --shallow-submodules https://github.com/espressif/esp-idf.git "$GEARSHIFT_SDK_ROOT/esp-idf"
export IDF_TOOLS_PATH="$GEARSHIFT_SDK_ROOT/tools"
"$GEARSHIFT_SDK_ROOT/esp-idf/install.sh" esp32
. "$GEARSHIFT_SDK_ROOT/esp-idf/export.sh"
idf.py --version
python --version
```

Az `IDF_TOOLS_PATH` értékét és az `export.sh` betöltését minden új
terminálban ismételd meg. Ne futtasd az IDF telepítőjét aktív másik venv-ből.
A jelenlegi gép sudo nélküli telepítési kerülőútját a bizonyítéknapló tartalmazza.

## Fordítás

```bash
bash firmware/esp32/bringup/build.sh basic
bash firmware/esp32/bringup/build.sh inference
```

A build rögzített célja `esp32`; ez az ESP-WROOM-32 alapján választott
**buildcél**, nem a csatlakoztatott chip azonosításának bizonyítéka.
Mindkét projekt alapbeállítása: flash DIO, 40 MHz, **2 MiB konfigurált
kapacitás**, CPU 240 MHz, UART0 115200 baud, nincs PSRAM-feltételezés.
A 2 MiB nem mért flashméret. A tényleges flash azonosítása kötelező feltöltés
előtt. A watchdogok alapértelmezésben bekapcsolva maradnak. A következtetési
mintán teljesítményre optimalizáló fordítás fut. Nincs hozzáadott WiFi-funkció.

A teljes effektív konfiguráció a projektenként generált `sdkconfig` fájlban
van; ezt a futási bizonyítékkal együtt őrizd meg. Új alapkonfiguráció
ellenőrzéséhez tiszta munkapéldányban fordíts; a már létező `sdkconfig`
értékei elsőbbséget élveznek a defaults felett. Ne másold át egyik projekt
buildkönyvtárát vagy konfigurációját a másikba.

## A valódi panel azonosítása

Csatlakoztasd a panelt adatátvitelre alkalmas USB-kábellel. Ellenőrizd a
panel feliratát, és jegyezd fel a pontos típust vagy az ismeretlen adatokat.
A `211-161007` jelölés önmagában nem bizonyít paneltípust vagy flashméretet.

```bash
python -m serial.tools.list_ports -v
ls -l /dev/serial/by-id/
# A tényleges eszközt add meg, lehetőleg stabil by-id útvonallal:
export GEARSHIFT_PORT=/dev/serial/by-id/A_TENYLEGES_ESZKOZ
mkdir -p results/issue-2
set -o pipefail
python -m esptool --chip auto --port "$GEARSHIFT_PORT" chip_id 2>&1 | tee results/issue-2/chip-id.log
python -m esptool --chip auto --port "$GEARSHIFT_PORT" flash_id 2>&1 | tee results/issue-2/flash-id.log
```

Az IDF-hez telepített esptool verzió `chip_id`/`flash_id` parancsait használd.
Ha nincs port: kábel, USB-csatlakozás és kernelnapló ellenőrzése; ha nincs
jogosultság: a soros eszköz csoportját és a felhasználó tagságát ellenőrizd.
Ezek nélkül a hardverpróba nyitott marad. Ha a chip nem ESP32, ne töltsd fel
az előállított firmware-t. Eltérő flash- vagy bootkövetelmény esetén előbb
módosítsd és dokumentáld a konfigurációt, majd fordíts újra.

## Feltöltés és megfigyelés

A flash parancs a panel korábbi programját felülírja. Előbb az alapmintát,
azután a következtetési mintát töltsd fel. Minden soros terminálból lépj ki,
mielőtt másik eszközt indítasz ugyanarra a portra.

```bash
idf.py -C firmware/esp32/bringup/basic -p "$GEARSHIFT_PORT" flash 2>&1 | tee results/issue-2/basic-flash.log
idf.py -C firmware/esp32/bringup/basic -p "$GEARSHIFT_PORT" monitor 2>&1 | tee results/issue-2/basic-monitor.log
# Kilépés: Ctrl+]. Ezután:
idf.py -C firmware/esp32/bringup/inference -p "$GEARSHIFT_PORT" flash 2>&1 | tee results/issue-2/inference-flash.log
idf.py -C firmware/esp32/bringup/inference -p "$GEARSHIFT_PORT" monitor 2>&1 | tee results/issue-2/inference-monitor.log
```

Az alapminta `Hello world!`, chip-, flash- és heapadatot ír ki, majd
visszaszámlálás után **szándékosan újraindul**. A `Restarting now.` utáni
reset az upstream minta része. Ezt ne keverd a következtetési próba
stabilitásával. Az esptool `flash_id` naplója az irányadó a fizikai
flashkapacitáshoz; a bootkimenet a konfigurált kapacitást is tükrözheti.

A következtetési minta beágyazott, INT8 **szinuszbecslő hello_world**
modellje 500 ms-onként ad `x_value: ..., y_value: ...` sort; egy ciklus
20 következtetés. Nem dolgoz fel fokozatváltási ablakokat. Megfigyelési
terv: legalább 100 egymást követő sikeres következtetés (kb. 50 s),
a boot kezdetétől rögzített folyamatos naplóval, hiba és váratlan reset nélkül.
Ez helyi bringup-próbaterv, nem az issue által előírt teljesítményküszöb.

```bash
# Ez csak a sikeres kimeneti sorok számát adja, önmagában nem PASS:
grep -c '^x_value: ' results/issue-2/inference-monitor.log
# A teljes naplót is vizsgáld meg; az alábbi keresés csak segítség:
grep -En 'rst:|Guru Meditation|panic|Brownout|watchdog|failed|Invoke failed|schema version' results/issue-2/inference-monitor.log
```

Egy induláskori reset megengedett; megfigyelés közbeni újabb boot/reset,
allokációs vagy Invoke-hiba sikertelen próbát jelent. A sorok összeadása több
reset közül nem bizonyít folyamatos működést. Jegyezd fel a pontos sikeres
futásszámot, időtartamot, modellt, kódverziót és minden hibát. A forrásmodell
azonosítója a `main/model.cc` SHA-256 értéke; a build binárisait és a teljes
konfigurációt szintén ellenőrzőösszeggel őrizd meg.

## Bizonyíték és folytatás

A `results/issue-2/` tartalmazza a helyi teljes naplókat és binárisokat;
nagy vagy gépspecifikus állományt ne adj automatikusan Githez. A kis,
ellenőrizhető kivonatokat és SHA-256 értékeket a
`docs/evidence/issue-2/verification.md` mellett rögzítsd, a sikertelen
futtatásokat is megtartva. Hardver hiányában ne tölts ki mintakimenetekkel
semmilyen eredménymezőt.

A saját mérő firmware, UART-protokoll és saját MLP-integráció külön issue
feladata. A #2 nem zárható le a hardveres feltételek bizonyítéka nélkül.
