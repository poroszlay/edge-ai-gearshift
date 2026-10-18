# Edge AI fokozatváltási labor

A GUI-tól és modelltréningtől független kommunikációs próba (Python 3.10+):

```bash
python3 -m gearshift.client --demo --mode live
python3 -m gearshift.client --demo --mode benchmark
python3 -m unittest discover -s tests -v
```

A kimenet szimuláció, nem hardvermérés. Protokoll, külön folyamatokban
futtatás, korlátok és elfogadási ellenőrzés: [kommunikáció](docs/communication.md).

Adat- és állapotszerződés: [data-contract](docs/data-contract.md).
Modell és mérés: [model-measurement-contract](docs/model-measurement-contract.md).
