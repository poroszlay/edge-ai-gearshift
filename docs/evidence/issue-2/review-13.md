# #13 review megállapításának elbírálása

Dátum: 2026-10-18. Vizsgált PR HEAD: `bdee15c890d20cdb96bb7b3981f5788eeed61af7`.
A `git fetch origin feat/issue-2-esp32-bringup` után a távoli és helyi HEAD
azonos volt; a külön `/tmp/edge-ai-gearshift-issue-2` worktree tiszta volt.
A meglévő PR branchén készült ez a dokumentációs kiegészítés.

## Megállapítás és döntés

A [review](https://github.com/poroszlay/edge-ai-gearshift/pull/13)
egyetlen megállapítása a chip-/flashazonosítás, feltöltés és ismételt,
váratlan reset nélküli következtetés hiányzó hardveres bizonyítéka.
Soronkénti review-megjegyzés nem volt.

**Implementációs hibaként elutasítva; nyitott elfogadási hiányként fenntartva.**
Nem készült firmware-módosítás, mert a megállapítás nem mutat hibás kódutat.
Konkrét bizonyítékok:

- A [#2 issue](https://github.com/poroszlay/edge-ai-gearshift/issues/2)
  elfogadási feltétele kifejezetten előírja: „Hardver nélkül ezt
  részfeladatként nyitva kell hagyni.”
- A [verification.md](verification.md) elfogadási táblázata már a vizsgált
  commitban nyitottnak jelölte a chipet, flashméretet, feltöltést és soros
  futást; a megfigyelt hardveres következtetésszám **0**.
- A [chip-id.log](chip-id.log) és [flash-id.log](flash-id.log) tényleges
  `[Errno 13] Permission denied` hibát rögzít. Ezek nem igazolnak
  chipazonosítást vagy hardveres futást.
- A PR draft, leírása nyitottnak nevezi a hardveres elfogadást;
  a review maga is kimondja, hogy a megállapítás nem igazolt implementációs hiba.

Az elfogadási követelményt nem töröltük és nem tekintjük teljesítettnek.
A #2 nyitva marad. A [hardveres folytatás](verification.md#hardver-és-következő-lépés)
szerinti hozzáférés, azonosítás, feltöltés és tényleges folyamatos napló
szükséges a teljes elfogadáshoz. Ebben az ellenőrzésben hardverművelet nem történt.

## Újrafuttatott ellenőrzések

A meglévő, dokumentált ESP-IDF-környezetben, ugyanebben a worktree-ben:

| Ellenőrzés | Eredmény |
| --- | --- |
| `bash firmware/esp32/bringup/build.sh basic` | exit 0, meglévő build újrafuttatása; 156096 byte, partícióellenőrzés sikeres |
| `bash firmware/esp32/bringup/build.sh inference` | exit 0, meglévő build újrafuttatása; 209248 byte, partícióellenőrzés sikeres |
| `bash -n firmware/esp32/bringup/build.sh` | exit 0 |
| `git diff --check` | exit 0 |
| Upstream C/C++ és CMake-fájlok bytepontos összevetése | Mind a 14 fájl egyezik a helyi hivatalos SDK/TFLM forrással, a beágyazott modell is |
| `sha256sum -c docs/evidence/issue-2/SHA256SUMS` | 10 egyezés; a két alkalmazásbináris eltér a korábbi buildtől |

Az alkalmazásbinárisok eltérése nem új hiba: a korábbi
[buildnapló](verification.md#buildellenőrzés-eredménye) kifejezetten konkrét
buildazonosítóként írja le a hash-t, és jelzi a buildidő/útvonal miatti
eltérés lehetőségét. A korábbi bizonyíték hash-eit megőriztük;
a forrásmodell, lock, defaults, generált konfigurációk, bootloaderek és
partíciós táblák ellenőrzőösszege egyezik.

Az újrafuttatás teljes buildnaplói helyben: `/tmp/pr13-basic-build.log`,
`/tmp/pr13-inference-build.log`. SHA-256 azonosítóik és az aktuális
alkalmazásbinárisok azonosítói:

```text
b49e9ba770f2da7f6b9dacd25afae6296879eeb7c7f99a3c56b9c37de8df34bf  /tmp/pr13-basic-build.log
736ef8a3bb83ae2d8a382587214b620d332da17303488426acbae30b3c680b3c  /tmp/pr13-inference-build.log
b55d29adc82b0ff1c79b6e767b23e0562d5d5232bcd6842d319d45478403c602  firmware/esp32/bringup/basic/build/hello_world.bin
c706fb34c069814247dde8001b5282f57d3df7889a7bf0dc2b783b618c91997d  firmware/esp32/bringup/inference/build/hello_world.bin
```
