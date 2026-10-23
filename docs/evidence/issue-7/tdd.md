# #7 TDD

Felhasználói jóváhagyás: 2026-10-23, „Igen”.

Tesztelési határok:
- Firmware load/execute/fetch: protokoll, ütemezés és hibák; fizikai UART nélkül.
- Nyers ablak → MCU-modellkimenet: külön előfeldolgozás/kvantálás és azonos INT8 bemenet.
- UART-kliens → export/jelentés: eredet, teljes elszámolás, minőség és portolás.
- Valódi ESP32: élő mód és négyprofilos benchmark idő-/memóriaadatai.

Befagyasztott modell: mlp-v2, 6d5ac8613d301ca06de2ca9a4cfbadf3cd40c7c75a7af419505eaa9fcbb25f79.
A teszthalmaz nem modellválasztási adat. A tűrés elemenként 1, osztályegyezés kötelező.
