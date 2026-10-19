# PC-s szabályreferencia

Az #1 issue megvalósítása. A szabályreferencia a laborfeltevések szerinti
döntést adja; a referencia megtanulását szolgáló címkéző.

## Használat

```python
from pc.reference import label_window

samples = [
    dict(run_id="example", timestamp_ms=i * 50,
         v=45, u=0.2, s=0, g=1, tau=3)
    for i in range(20)
]
result = label_window(samples)
assert (result.status, result.action, result.class_index) == ("ok", 1, 2)
```

Nyilvános seam: `pc.reference.label_window(samples) -> LabelResult`.
A felhasználó ezt a tesztelési határt jóváhagyta.
A függvény nem módosítja a bemenetet, és nem frissít állapotot.
A `LabelResult` változtathatatlan eredmény, mezői `status`, `action`,
`class_index`. Csak `status == "ok"` mellett használható tanítási címke.

## Bemeneti szerződés

Egy 20 elemű lista vagy tuple, legrégebbitől a legújabb mintáig.
Minden minta egy szótár az alábbi kötelező mezőkkel; további mezők
megengedettek. A jelek nyers értékek, előfeldolgozás nélkül.

| Mező | Típus, egység, megengedett érték |
| --- | --- |
| `run_id` | Nem üres, nem csak szóközökből álló szöveg; minden mintában azonos |
| `timestamp_ms` | Nemnegatív Python `int`, milliszekundum |
| `v` | Véges Python `int` vagy `float`, 0..80 km/h |
| `u` | Véges Python `int` vagy `float`, 0..1 |
| `s` | Véges Python `int` vagy `float`, -10..10 százalékérték |
| `g` | Python `int` vagy `float`, pontosan 1 vagy 2 |
| `tau` | Véges, nemnegatív Python `int` vagy `float`, másodperc |

Nincs szöveg–szám konverzió, a `bool` nem számjel.
Az egymást követő időbélyegek különbsége pontosan 50 ms, tolerancia nélkül.
Az első időbélyeg tetszőleges nemnegatív egész; az ablak átfogása 950 ms.
Az egész milliszekundum elkerüli az időrács lebegőpontos bizonytalanságát.
Az ablak nem nyúlhat át másik menetbe.

A `tau > 10` érvényes nyers idő; a telítés a későbbi modellbemenet feladata.
A függvény az összes mintát validálja, beleértve az átlagolásból kimaradó
első 15 mintát is, és csak ezután alkalmazza az időzárat és a döntési szabályt.
A generátor felel a múltbeli állapotátmenetek előállításáért; a címkéző a
kapott döntés előtti állapotot értékeli, és nem ellenőrzi annak dinamikáját.

## Döntés és hibák

Az utolsó öt minta `v`, `u`, `s` jeleinek számtani átlaga alapján
`v_up = 30 + 20 * mean(u) + 0.5 * mean(s)` és `v_down = v_up - 10`.
A legfrissebb minta `tau < 1` értékénél tartás; egyébként `g=1` és
`mean(v)>v_up` esetén felváltás, `g=2` és `mean(v)<v_down` esetén
visszaváltás. Minden más érvényes eset tartás. Küszöbegyezéskor tartás;
pontosan 1 másodpercnél a váltás már engedélyezett.

| Döntés | `action` | `class_index` |
| --- | ---: | ---: |
| Visszaváltás | -1 | 0 |
| Tartás | 0 | 1 |
| Felváltás | 1 | 2 |

Minden hibánál `action is None` és `class_index is None`.

| `status` | Jelentés |
| --- | --- |
| `ok` | Érvényes ablak és döntés |
| `invalid_type` | Hibás ablak-, minta- vagy jeltípus |
| `invalid_window_length` | Nem 20 minta |
| `missing_signal` | Hiányzó kötelező mező |
| `invalid_run` | Hibás vagy eltérő menetazonosító |
| `non_finite_value` | NaN vagy végtelen jel/időbélyeg |
| `out_of_range` | Tartományon kívüli jel |
| `invalid_sampling_time` | Hibás időbélyegtípus, negatív idő vagy nem 50 ms lépés |

Több egyidejű hiba esetén az első észlelt hiba kerül visszaadásra.
Az ellenőrzés sorrendje: ablak típusa és hossza; mintánként típus,
mezőhiány, menetazonosító, jeltípus, időbélyeg numerikus típusa,
véges értékek, jeltartományok, majd időrács. Nincs automatikus javítás.

Ez a Python-bemenet szerződése. CSV-beolvasót vagy -írót az #1 nem vezet
be; a későbbi adatgenerátor a mezőket ezekkel az egységekkel tudja átadni.

## Elfogadási ellenőrzések

Futtatás a repository gyökerében, külső csomag és hardver nélkül:

```bash
python3 -m unittest discover -s tests -v
```

| #1 elfogadási feltétel | Teszt a `tests/test_reference.py` fájlban |
| --- | --- |
| Négy dokumentált példa | `test_documented_*` (4 teszt) |
| Alsó/felső küszöbegyezés | `test_lower_threshold_equality_holds`, `test_documented_upper_threshold_equality_holds` |
| Tau=1 s és közvetlenül alatta | `test_one_second_unlocks_both_directions` (`math.nextafter(1, 0)`) |
| Utolsó öt minta, legfrissebb állapot | `test_only_last_five_samples_are_averaged`, `test_each_of_v_u_s_is_averaged_over_all_five_recent_samples`, `test_latest_predecision_state_is_used`, `test_downshift_uses_latest_gear_not_the_preceding_four` |
| Öt külön hibakategória, címke nélkül | `test_invalid_window_length_has_no_label`, `test_missing_signal_anywhere_has_no_label_even_during_lockout`, `test_non_finite_signal_anywhere_has_no_label`, `test_out_of_range_signal_anywhere_has_no_label`, `test_sampling_requires_nonnegative_integer_milliseconds_and_50ms_steps` |
| Döntésérték és osztályindex elválasztása | `test_action_is_not_the_class_index` |

További ellenőrzések: menethatár, típushibák, tartományvégek, 10 s feletti
tau, nagy egész számok, valamint a bemenet változatlansága.

## Ellenőrzött állapot és átadás

Python 3.13.5, `python3 -m unittest discover -s tests -v`: **21 teszt OK**.
A TDD-lépések során a hiányzó modul, majd a visszaváltás, időzár, öt
hibakategória, menethatár, típuskezelés és nagy egész számok hibája először
bukó ellenőrzéssel jelent meg, majd az adott viselkedés implementálása
után sikeres lett. A már helyesen működő határesetek további regressziós
ellenőrzést kaptak.

A következő adatgenerátor-feladat ezen az interfészen címkézhet teljes
ablakokat. Az adatgenerátor, modell, soros kommunikáció és hardveres
mérés továbbra is külön feladat.
