# Edge AI fokozatváltási labor

PC-s szabályreferencia szintetikus menetszakaszok címkézéséhez, valamint
GUI-tól és modelltréningtől független kommunikációs próba.

A kommunikációs próba Python 3.10+ verziót igényel; a szabályreferencia
Python 3.13.5 alatt ellenőrizve. Külső csomag és hardver nem szükséges.
A repository gyökerében:

```bash
python3 -m gearshift.client --demo --mode live
python3 -m gearshift.client --demo --mode benchmark
python3 -m unittest discover -s tests -v
```

A kommunikációs próba kimenete szimuláció, nem hardvermérés. Protokoll,
külön folyamatokban futtatás, korlátok és elfogadási ellenőrzés:
[kommunikáció](docs/communication.md).

A szabályreferencia használatát, adatmezőit, hibastátuszait és az #1 issue
elfogadási ellenőrzéseit a [szabályreferencia szerződése](docs/rule-reference.md)
írja le.

Adat- és állapotszerződés: [data-contract](docs/data-contract.md).
Modell és mérés: [model-measurement-contract](docs/model-measurement-contract.md).
