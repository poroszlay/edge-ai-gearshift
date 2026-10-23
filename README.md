# Edge AI fokozatváltási labor

Szintetikus menetszakaszokon végzett, mikrokontrolleres fokozatváltási
döntésbecslés és laboratóriumi értékelés.

- [ESP32-fejlesztőkörnyezet és hivatalos minták (#2)](docs/esp32-bringup.md)
- [Közös adatszerződés](docs/data-contract.md)
- [Modell- és mérési szerződés](docs/model-measurement-contract.md)
- [ESP32 mérőmodul, reprodukálás és #7-átadás (#5)](docs/measurement-module.md)
- [Szintetikus adatkészlet, reprodukálás és tesztlezárás (#3)](docs/dataset.md)
- [MLP-tanítás, teljes INT8-export és PC-s referencia (#6)](docs/model.md)
- [Saját INT8 MLP az ESP32-n, portolás és mérések (#7)](docs/esp32-inference.md)
- [PySide6 mérőfelület és CSV-export](docs/measurement-ui.md)

A bringup szinuszmodellje hivatalos kompatibilitási próba. A saját
100 → 64 → 32 → 3, befagyasztott `mlp-v2` MLP tanítása, INT8-exportja és tényleges validációs
eredményei a [modell dokumentációjában](docs/model.md) követhetők. A saját
modell paneles portolási helyességét és terhelésmérését a
[#7 ellenőrzési naplója](docs/evidence/issue-7/verification.md) rögzíti.
A kiválasztott INT8-modell validációs makro-F1-e 0,7029; a 0,95-ös cél
nem teljesült, a minőségjavítás a [#19 feladatban](https://github.com/poroszlay/edge-ai-gearshift/issues/19) folytatódik.
