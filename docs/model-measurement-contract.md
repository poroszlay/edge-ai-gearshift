# Modell és mérés: elfogadott döntések

## Generálási szabadság

A konkrét jelprofilok, seed és kezdeti zajparaméterek megválasztása az
implementáló agent feladata. Kötelező a konfiguráció, reprodukálhatóság,
osztály-, váltási esemény- és határeset-lefedési kimutatás. Az első adatok
ellenőrzése előzze meg a tesztadat lezárását. Teszteredmény alapján ugyanaz
a lezárt tesztkészlet nem módosítható vissza.

## Első modell

Induló MLP: 100 → 32 → 16 → 3, két ReLU rejtett réteggel, teljes INT8-export.
A konkrét futtatókörnyezet művelettámogatását először ellenőrizni kell.
A modellválasztás kizárólag a validációs rész alapján történhet; szükséges
módosítás indoka és konfigurációja megőrzendő.

Validációs cél: makro-F1 legalább 0,95, mindhárom osztály külön értékelésével.
A lezárt teszthalmazon a tényleges eredményt jelentjük, nem választunk
új modellt az alapján. A gyengébb minőség nem minősíthető teljesített célnak,
de a működő adatút és mérés bemutatható, a korláttal együtt.

## Portolási helyesség

Azonos INT8-bemenet esetén az osztálydöntés egyezzen, a kimeneti eltérés
elemenként legfeljebb egy kvantálási lépés (INT8 kódban legfeljebb 1) lehet.
Az eltéréseket naplózni kell; az agent nem lazíthat automatikusan a tűrésen.
Külön vizsgálandó a nyers ablak előfeldolgozása és kvantálása, hogy az
előre kvantált bemenetek ne fedjenek el adatútbeli hibát.

## Minőségellenőrzés és terhelés

A minőségellenőrzés adagokban feldolgozza a teljes tesztablak-készletet.
Az adaghatárokon megengedett az UART-kommunikáció; minden ablak elszámolandó.

A folyamatos terhelésmérés előtöltött, memóriába férő ablakkészletet ismétel,
UART-szünet nélkül. Profilonként 100 bemelegítő, majd három, egyenként
1000 ütemezett feladatból álló mért sorozat készül. A kimaradások az 1000
ütemezett feladat részei, nem pótlódnak észrevétlenül új feladatokkal.
A használt ablakazonosítók és sorrend megőrzendők; az ismételt készlet
teljesítménye nem állítható a teljes tesztadat teljesítményeloszlásának.

A terhelési profilok T=D=10/20/50/100 ms. A határidő a tervezett indítástól
számítódik; a foglalt végrehajtó miatt kimaradt és a későn befejeződő
feladatot összesen legfeljebb egyszer kell a nem teljesültekhez számolni.

## Két eszközüzemmód

Élő megfigyelésben az eszköz ablakonként feldolgoz és eredményt küld,
a grafikon folyamatosan frissül. A soros műveletek a külön mért inferencia- /
MCU-feldolgozási szakaszon kívül történnek; ez nem a folyamatos terhelési benchmark.

Terhelésmérésben a memóriába előtöltött ablakok UART-kommunikáció nélkül
futnak. Az eredményátvitel és grafikonfrissítés a sorozat után történik.
A négy terhelési profil következtetései ebből az üzemmódból származnak.
Mindkét mód valódi panelen is működik; a felület és export jelzi az üzemmódot.

Az elfogadott előfeldolgozás a `docs/data-contract.md` rögzített skálázása.
