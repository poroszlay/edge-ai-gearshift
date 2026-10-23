# Edge AI fokozatváltási labor

Szintetikus menetszakaszokon végzett, mikrokontrolleres fokozatváltási
döntésbecslés és laboratóriumi értékelés.

- [ESP32-fejlesztőkörnyezet és hivatalos minták (#2)](docs/esp32-bringup.md)
- [Közös adatszerződés](docs/data-contract.md)
- [Modell- és mérési szerződés](docs/model-measurement-contract.md)
- [ESP32 mérőmodul, reprodukálás és #7-átadás (#5)](docs/measurement-module.md)
- [Szintetikus adatkészlet, reprodukálás és tesztlezárás (#3)](docs/dataset.md)
- [MLP-tanítás, teljes INT8-export és PC-s referencia (#6)](docs/model.md)
- [PySide6 mérőfelület és CSV-export](docs/measurement-ui.md)

A bringup szinuszmodellje hivatalos kompatibilitási próba. A saját
100 → 64 → 32 → 3, befagyasztott `mlp-v2` MLP tanítása, INT8-exportja és tényleges validációs
eredményei a [modell dokumentációjában](docs/model.md) követhetők. A saját
modell paneles portolási helyessége és terhelésmérése a #7 feladata.
A kiválasztott INT8-modell validációs makro-F1-e 0,7029; a 0,95-ös cél
nem teljesült, a minőségjavítás a [#19 feladatban](https://github.com/poroszlay/edge-ai-gearshift/issues/19) folytatódik.
