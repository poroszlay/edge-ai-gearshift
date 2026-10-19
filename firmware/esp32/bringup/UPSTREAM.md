# Hivatalos minták eredete

- `basic/`: ESP-IDF **v5.5.1**, commit
  `fcae32885b0296b32044cb99ecbdc50d98dddb83`,
  `examples/get-started/hello_world` CMake-fájljai és `main/` forrása,
  változtatás nélkül. A C-forrás licence CC0-1.0 (a fejlécében);
  az SDK Apache-2.0 licence a `basic/LICENSE` fájlban szerepel.
- `inference/`: esp-tflite-micro **v1.3.5**, commit
  `5f31ea08cee30ef3c2a1dfe7357f4be4048bc044`,
  `examples/hello_world` CMake-fájljai és `main/` forrásai.
  A C/C++ forrás és a beágyazott szinuszmodell változatlan;
  az `idf_component.yml` helyi override helyett pontos registry-verziókat kér.
  Licenc: Apache-2.0, mellékelve az `inference/LICENSE` fájlban.
- Mindkét `sdkconfig.defaults` saját, konzervatív konfiguráció;
  DIO/40 MHz/4 MiB, UART 115200 baud, CPU 240 MHz.
  A 4 MiB kapacitást a 2026-10-19-i esptool `flash_id` igazolja; a korábbi
  2 MiB feltételezést a hardveres próba előtt módosítottuk.
  Nincs PSRAM-feltételezés, nincs WiFi-funkció. Az upstream minta
  watchdog-kikapcsolásait nem vettük át.

A verziókat és forrásokat a [bringup leírás](../../../docs/esp32-bringup.md)
kapcsolja a reprodukálási lépésekhez és a tényleges ellenőrzési állapothoz.
