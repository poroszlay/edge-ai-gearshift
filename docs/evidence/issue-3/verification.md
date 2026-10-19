# #3 elfogadási ellenőrzések

Alap: `origin/main` = `c3ef45d`. Külön worktree és
`feat/issue-3-synthetic-dataset` branch. Python 3.13.5, kizárólag standard
könyvtár. A meglévő `pc/reference.py` változatlan.

## TDD és publikus teszthatárok

A felhasználó a generátor, a felosztás/ablakolás és az exportáló/lezáró CLI
publikus teszthatárait az első teszt megírása előtt jóváhagyta.
A lépések egyenként, bukó teszt → minimális megvalósítás sorrendben készültek:

| Teszt/viselkedés | Előtte | Utána |
| --- | --- | --- |
| Döntés csak a következő mintában frissít állapotot | `ModuleNotFoundError: pc.dataset` | A 30. mintán felváltás, 31.-en g=2/tau=0.05; 49.-en tau=0.95/tartás, 50.-en tau=1/visszaváltás |
| Menetcsaládonkénti felosztás | Hiányzó `make_plan` | 140/30/30 menet, 100 oszthatatlan család, 100/100 kezdeti fokozat |
| Öt profil és seedelt zaj | A két különböző seed zajos menete azonos volt | Különböző profilok, azonos seedre azonos zaj, minden címke a referenciából |
| Konfiguráció és menetleíró validálása | Érvénytelen értékek nem okoztak hibát | Hibás konfiguráció és menetleíró elutasítva |
| Ablak és skálázás | Hiányzó `iter_windows` | 20. mintától 100 elem, kizárólag múlt/jelen, nyers tau megmarad |
| Reprodukálható export | A CLI nem állított elő kimeneti könyvtárat | Minden fájl bájtra azonos, manifest és forrásverzió rögzített |
| Lefedési kapu | Hiányzó `report.json` | Hiányos lefedés nem zárható le, minden részhalmaz külön ellenőrzött |
| Külön hibás adatok | Hiányzó `read_invalid_cases` | Kilenc külön, szabványos JSON-eset, érvényes címke nélkül |
| Tesztlezárás és sérülésvizsgálat | Hiányzó `verify` parancs | Lezárás megőrzött, felülírás/újrazárás/sérült adat elutasítva |
| Eltérő alapmenetek | Teljesen azonos alap-jelprofilok előfordultak | Az alapméret mind a 20 alap-jelprofilja eltér minden típusban |

Teljes végső futás: `python3 -m unittest discover -s tests -v`:
**44 teszt OK** (34 meglévő és 10 új). A teljes kimenet: `tests.log`.
A kommunikációs sockettesztek sandboxban `PermissionError` miatt nem tudtak
futni; a sikeres teljes futás helyi socketküldést engedő környezetben történt.

## Alapméret és lefedés, lezárás előtt

Az első generálás `report.json` fájlját a `seal` indítása előtt ellenőriztem.
`coverage_ok=true`, hiányzó lefedési elem nincs. Mind az öt típusból
tanító/validációs/teszt részhalmazonként 28/6/6 menet van. A kezdeti
fokozatok összesítve 100/100 arányúak. A teljes, részletes kimutatás:
`report.json`.

| Részhalmaz | Menet / család | Minta | Ablak | Visszaváltás (0) | Tartás (1) | Felváltás (2) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tanító | 140 / 70 | 336000 | 333340 | 1604 | 330136 | 1600 |
| Validációs | 30 / 15 | 72000 | 71430 | 332 | 70750 | 348 |
| Teszt | 30 / 15 | 72000 | 71430 | 346 | 70739 | 345 |
| Összesen | 200 / 100 | 480000 | 476200 | 2282 | 471625 | 2293 |

A nemnulla döntések egyben váltási események; a tartás nem esemény.
Minden részhalmazban pozitív a küszöbegyezések, küszöbközeli esetek,
tau=0.95, tau=1, tau>10 és mindkét irányú tiltott igény számlálója.

## Reprodukálási parancsok

A parancsokat a repository gyökeréből, új könyvtárakkal kell futtatni:

```bash
python3 -m unittest discover -s tests -v
python3 -m pc.dataset generate data/generated/dataset-v1 --config config/dataset-v1.json
python3 -m pc.dataset generate data/generated/dataset-v1-repeat --config config/dataset-v1.json
diff -r data/generated/dataset-v1 data/generated/dataset-v1-repeat
cat data/generated/dataset-v1/report.json
python3 -m pc.dataset seal data/generated/dataset-v1
python3 -m pc.dataset verify data/generated/dataset-v1
```

A konfiguráció és a források verziója a `manifest.json` fájlban szerepel;
a teszt lezárását a `test-lock.json` őrzi. A teljes generált állományok
egy példánya körülbelül 63 MiB, és nem kerül Gitbe. A kis bizonyítékfájlok
ellenőrzőösszegeit a `SHA256SUMS` rögzíti.

A teljes méretű második generálás mind a 11 közös fájlja bájtra azonos az
elsőével; a `diff` kilépési kódja 0. Az összevetéskor az első készlet már
lezárt volt, ezért a csak ott létező `test-lock.json` kimaradt az összevetésből.
A lezárt első készlet külön teljes `verify` auditot kapott.

Megőrzött dataset-verzióazonosító:
`7537958c902a6c325507fa3f3b2e56ff9000a9ca9824b2e3d5b27b26098f7e4e`.
Teszt-CSV SHA-256:
`2d3ed27b6528cc7745753a780da50b886c3714bb5b9747228ef36fbe25ea550d`.

## Fennmaradó korlátok

- Ismétlődő szintetikus laborprofilok, ugrásos küszöbprofil; nincs igazolt
  járműdinamika vagy közúti reprezentativitás.
- A tartásosztály körülbelül 99%; az átfedő ablakok nem független menetek.
  Nincs itt végzett modellválasztás vagy teszthalmaz alapján finomított modell.
- A bájtszintű reprodukálás azonos forrás és Python 3.13.5 mellett ellenőrzött.
  A CI meglévő Python 3.10/3.13 mátrixa a teljes tesztkészletet futtatja.
- A lezárás és a Gitben megőrzött hash-ek azonosítást és sérülésészlelést
  adnak; a fájlok közvetlen olvasását/átírását nem tiltják operációs rendszer
  szinten. A lezárt teszt nem használható modellválasztásra, normalizálás
  illesztésére vagy INT8-kalibrációra.
- A 20 mintás ablak előtti 19 sor címke nélküli bemelegítés. A verziózott
  CSV-séma és további megvalósítási részletek: [adatkészlet](../../dataset.md).
