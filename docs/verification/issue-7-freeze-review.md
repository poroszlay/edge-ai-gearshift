# PR #20: közös befagyasztási szerződés

Review: [discussion_r4363193691](https://github.com/poroszlay/edge-ai-gearshift/pull/20#discussion_r4363193691).

A PC-s végső értékelés és a firmware-header generátora ugyanazt a
`gearshift.frozen_export.read_frozen_export` adaptert használja. A szerződést
az I/O-t és mutációt nem végző `validate_freeze` függvény ellenőrzi:
`frozen is True`, egyező modell-/adatverzió, a tényleges modell-SHA-256 és
minden deklarált fájl ellenőrzőösszege. A generátor modellinterfész-ellenőrzése
és a PC tényleges TFLite-auditja a saját belépési pontján marad.

A regresszió a két korábban jóváhagyott belépési pontot teszteli. A red
futásban a generátor elfogadta a `frozen: 1`, `frozen: "true"` és eltérő
`dataset_id` eseteket. A javítás után mindkét belépési pont elutasítja ezeket,
a hamis freeze állapotot, az eltérő modellazonosítót és a sérült fájlt is;
a PC a lezárt teszt olvasása előtt megáll.

Ellenőrzések:

- Célzott regresszió: 3 teszt, OK, hat hibás csomagváltozattal.
- SDK Python, `-I`, idegen munkakönyvtár: a generátor importálható telepített
  projekt, NumPy és TensorFlow nélkül. ESP-IDF reconfigure sikeres;
  a közös modul a CMake konfigurációs függőségei között szerepel.
- A befagyasztott mlp-v2 teljes generált headere a javítás előtt/után
  bájtra azonos, SHA-256: `5b71ef72bd549cb59a43ac718e1d5899921520030dc68ed5c176ead886b8b9fd`.
- Teljes regresszió: 105 teszt, OK, 2 opcionális panelteszt kihagyva.
  Az első teljes futás egy meglévő offscreen GUI-tesztnél natív Qt
  összeomlással megszakadt; az elkülönített 10 GUI-teszt és a teljes,
  faulthandlerrel ismételt futás sikeres. GUI-kód nem módosult e javításban.

```bash
python -m unittest discover -s tests -p test_frozen_export.py -v
QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 \
  python -m unittest discover -s tests -v
```

A korábbi paneles bizonyítékok a rögzített korábbi forrásverziókra vonatkoznak;
ez a javítás a build/PC csomagvalidációt egységesíti, nem új paneles mérés.
