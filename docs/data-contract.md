# Közös adat- és állapotszerződés

Az alábbi döntéseket a felhasználó a tervezési interjúban elfogadta.
A forrásspecifikáció a `context/projektmunka_elorehaladasi_dokumentacio_masodik_het.md`.

## Ablak

- Mintavételi idő: 50 ms.
- Egy ablak 20 minta, legrégebbitől a legújabbig.
- Mintánkénti jelsorrend: `[v, u, s, g, tau]`.
- MLP-bemenet: mintánként lapítva, 100 elem.
- Az első 19 mintából nincs modellbemenet; ezt követően az ablaklépés egy minta.
- Ablak nem nyúlhat át másik menetbe. Csak jelenlegi és múltbeli minta használható.

## Állapot

A generálásban a szabályreferencia döntése a következő mintában jelenik meg
a fokozatban. Váltás után az első következő mintában tau=0,05 s.
Váltás nélkül az eltelt idő mintánként 0,05 s-mal nő.
A modellbemeneti tau 10 s-nál telítődik. Ez nem a belső eltelt idő felső korlátja.
A döntéshez mindig a legfrissebb minta döntés előtti g/tau értéke tartozik.

A mérési visszajátszásban az ablakok rögzítettek; a modell kimenete nem
módosítja a visszajátszott állapotot.

## Érvényesség

Hiányzó jel, nem véges szám, hibás ablakhossz, tartományon kívüli jel vagy
szabálytalan mintavételi idő esetén az ablak külön hibastátuszt kap.
Nincs automatikus javítás, érvényes döntési címke vagy tanításba bevonás.
Hibás esetek külön tesztadatokban szerepelnek.

A dokumentált jeltartományok: v=0..80 km/h, u=0..1, s=-10..10%, g pontosan
1 vagy 2, tau nemnegatív másodperc. A 10 s fölötti valós eltelt idő érvényes,
a modellbemenetben telítendő. Az időbélyegek és a nyers CSV pontos sémája,
illetve az időlépések reprezentációja az implementáló agent dokumentálandó döntése.

## Adatkészlet és kezdeti állapot

Első adatkészlet: 200 darab, egyenként 120 s hosszú menet, egyenlően
elosztva az öt dokumentált menettípus között (gyorsítás, egyenletes haladás,
emelkedő, lassítás, küszöbkörnyék). A 70/15/15 felosztás teljes menetek
szerint, ablakképzés előtt történik; zajos változatok az alapmenettel együtt
maradnak. Az osztályeloszlást és váltási eseményszámot lezárás előtt ellenőrizni kell.
A menetek fele g=1, fele g=2 állapotból indul, kezdetben tau=10 s.
Külön forgatókönyvek ellenőrzik a váltás utáni tiltást.

## Kommunikáció

Az első protokoll verziózott, soronként egy JSON-üzenettel (JSON Lines).
Futás- és ablakazonosító, visszaigazolás és külön hibaválasz szükséges.
Az ablakok kis adagokban előtöltődnek. A mért futási szakaszban nincs soros
küldés/fogadás; az adagok közötti UART-várakozás külön szerepel,
nem MCU-feldolgozási idő. A pontos üzenetséma és pufferhatár a kommunikációs feladat agentjének
dokumentálandó döntése; erre épít a firmware és a felület is.

## Túlterhelés

Nincs korlátlan feladatsor. Ha az előző következtetés miatt egy ütemezett
indítás kimarad, azt kimaradásként kell számolni. A későn befejezett
következtetés határidőtúllépés, egyszer számolva. Az indítások az eredeti
időrácshoz viszonyulnak; a határidő a tervezett indítástól számítódik.

## Eszközszimulátor

Készül PC-s eszközszimulátor a firmware-rel azonos kommunikációs szerződéssel.
Ezzel a kliens, felület és export hardvertől függetlenül fejleszthető.
A szimulált idő-/memóriaadatokat egyértelműen jelölni kell;
nem használhatók hardveres teljesítmény igazolására.

## Rögzített előfeldolgozás

A bemeneti jelek skálázása mintánként: `[v/80, u, s/10, g-1, min(tau,10)/10]`.
Az érvényesség ellenőrzése előzze meg az előfeldolgozást. A tanítás, PC-s
referencia és firmware azonos konvenciót használ; a lapítás változatlan.

## Megvalósítási döntések delegálása

Az agentek dokumentálva megválaszthatják a visszafordítható részleteket:
könyvtárszerkezet, kompatibilis csomagverziók, JSON-/CSV-mezőnevek,
időtúllépések, puffer-/adagméret, tanítási hiperparaméterek.
Az elfogadott viselkedés, adatfelosztás, mérési elszámolás és tűrések
nem módosíthatók önállóan. Az interfészt annak felelős issue-ja rögzíti,
a fogyasztók nem vezetnek be párhuzamos, eltérő sémát.

Forráskód, konfiguráció és kis referenciaállományok Gitbe kerülnek.
A teljes generált adat, modell és mérési eredmény reprodukálási leírással,
verzióval és ellenőrzőösszeggel legyen azonosítható; nagy generált állományokat
ne adj automatikusan a forráskódhoz.
