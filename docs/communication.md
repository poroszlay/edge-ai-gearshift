# JSON Lines v1: kliens és eszköz

Python 3.10+ szükséges, külső függőség nincs. A repó gyökeréből:

```bash
python3 -m gearshift.client --demo --output simulation-live.jsonl
python3 -m gearshift.client --demo --mode benchmark --output simulation-benchmark.jsonl
python3 -m unittest discover -s tests -v
```

Külön folyamatokban: `python3 -m gearshift.simulator --port 8765`, majd
`python3 -m gearshift.client --port 8765 --mode live`. A szimulátor csak
loopback TCP-n figyel. A `--demo` valódi helyi socketpárt használ.
A `Wire` bytefolyam-keretezése UART-on is alkalmazandó; soros port adapter és
firmware ebben a repóban még nincs. A firmware v1 implementációjának ezt a
szerződést kell követnie; paneles kompatibilitás nincs igazolva.

## Keretezés és korlátok

UTF-8 JSON objektum + LF; a méret LF-fel együtt legfeljebb 16384 byte.
JSON NaN/Infinity tilos. Legfeljebb 8 ablak tölthető elő; a teljes load
üzenetnek is bele kell férnie a mérethatárba. Legfeljebb 1000 eredmény
marad eszközoldalon; fetch válaszonként legfeljebb 16 rekord.
Nincs feladatsor, egy kapcsolat egy futás, egyszerre egy kérés.
Újrafuttatáshoz új kapcsolat és új run_id szükséges.
A kérések automatikusan nem ismétlődnek: kapcsolatvesztés után a futás
hiányos, nem tekinthető sikeresnek. A kliens kilépési kódja hiba esetén 1.
A timeout alapértéke 5 s, parancssorból állítható. Olvasáskor egy teljes
keret abszolút határideje, tehát a lassan csorgó byte-ok sem hosszabbítják.
Az eszköz keretezési hibára error választ küld, majd bont. Kapcsolatvesztés
észlelhető a kliensnél EOF-ként; erre már nincs garantálható hibaválasz.

## Közös mezők és állapotgép

Minden kérés: `v:1`, `type`, `request_id`, `run_id`, `mode`.
Az azonosítók 1..64 nyomtatható ASCII karakterből álló sztringek.
A kliens request_id-ja kapcsolaton belül növekvő. A mód `live` vagy
`benchmark`, futás közben nem változtatható. A válasz azonos v/request_id/
run_id/mode mezőket hordoz, és `simulated:true` mezőt tartalmaz.
Ez a kliens szándékosan kizárólag szimulációt fogad el; hardveradapternek
explicit eredetkezelést kell adnia, nem írhatja át a jelölést csendben.
Ismeretlen további mezők figyelmen kívül hagyhatók. Ismeretlen type hibás.

| Kérés | További mezők | Válasz |
| --- | --- | --- |
| start | nincs | ack |
| load | batch_id, windows (1..8) | ack + batch_id, count |
| execute | batch_id, count, period_ms | ack + batch_id, count, period_ms, uart_during_execution:false, simulated_memory_bytes |
| fetch | batch_id, offset (0-tól) | results + batch_id, offset, total, records |

Sorrend: start → load → execute → fetch ismételve a teljes eredményig.
Ezután új load engedett. A kliens minden eredményt lekér az új load előtt;
az eszköz batch_pending hibával elutasítja az új load-ot, amíg minden
eredményindex nem szerepelt fetch válaszban. Részleges, ismételt vagy csak az
utolsó oldalt lekérő fetch nem oldja fel a tiltást. Teljes lekérés után az új
load lecseréli az előző eredménytárat. Az execute egyszer
engedett adagonként; minden következő execute új load-ot igényel.
A load visszaigazolása garantálja az adag befogadását, az execute ack a
feldolgozás végét. Az execute alatt nincs küldés/olvasás az eszközön.

`error` válasz: közös mezők + `code`. Keretezési hiba esetén a nem
kiolvasható request_id null; a run_id/mode az aktív futásé, vagy null.
Kódok: invalid_json, invalid_message, message_too_large, timeout,
unsupported_version, invalid_identity, invalid_mode, run_already_started,
run_or_mode_mismatch, invalid_batch, batch_pending, invalid_state,
invalid_live_count, invalid_profile, invalid_offset, unknown_command.
A kliens külön jelzi a megszakadást és az eltérő válaszazonosítót is.

## Ablak és eredmény

A window objektum kötelező mezői: window_id, trip_id, timestamps_ms, samples.
20 darab nemnegatív egész milliszekundumos időbélyeg, pontosan 50 ms lépéssel,
egy meneten belül. A 20 samples sor sorrendje `[v,u,s,g,tau]` a
[data-contract](data-contract.md) szerint. Egy objektum egy trip_id-t hordoz;
a forrásnak kell garantálnia a menetazonosságot és a minták eredetét.
Az érvényesség ellenőrzése megelőzi az előfeldolgozást; tau>10 érvényes,
csak a modellbemenetben telítődik. Érvénytelen jel külön invalid_window
rekordot eredményez, döntési címke nélkül. Nem javítjuk automatikusan.

Minden eredmény: index (az execute-on belüli ütemezési sorszám), window_id,
batch_id, scheduled_ms, status. A kliens ellenőrzi az ablakok sorrendjét.
A státusz ok/late esetén processing_ms, decision és decision_source is van;
missed esetén nincs feldolgozási idő vagy döntés; invalid_window esetén error
adja az okot, nem üres sztringként. Az index és scheduled_ms nemnegatív egész
(bool nem megengedett); scheduled_ms=index×period_ms. A processing_ms véges,
nemnegatív szám; ok esetén legfeljebb period_ms, late esetén annál nagyobb.
Missed és invalid_window rekordban processing_ms, decision és decision_source
tiltott; error csak invalid_window esetén megengedett és kötelező.
A szimulátor döntése mindig hold, decision_source=simulator_stub.
A kliens ezt a szimulációs eredménysémát is ellenőrzi; hiányzó, hibás vagy
ellentmondó mező esetén failure eseménnyel és hibával leáll, run_complete nélkül.
Ez nem szabályreferencia, tanult modell vagy portolási helyesség igazolása.
A processing_ms alapértéke 3, a szimulátor `--duration-ms` opciójával állítható,
virtuális idő, nem a PC végrehajtási ideje. simulated_memory_bytes az ablakok
100×4 byte-os becslése; nem tényleges RAM-mérés.

## Módok és mérési elszámolás

Live: adagonként egy ablak, count=1; feldolgozás után azonnali fetch.
Benchmark: rögzített, előtöltött ablakkészlet ciklikusan ismételve, T=D
10/20/50/100 ms. Profilonként 100 bemelegítő és három 1000-es mért sorozat.
A kliens külön phase/series mezővel jelöli ezeket. A teljes bemenet itt
legfeljebb nyolc ablak; ez nem a teljes tesztadat minőségi értékelője.
Az időrács index×T; foglalt végrehajtónál missed, befejezés>D esetén late.
Egy feladatnak pontosan egy státusza van; kimaradás nem pótlódik.
A szimulátor a teljes execute-ot virtuális időben számolja ki, UART nélkül,
majd küld ack-ot; eredmények csak ezután kérhetők le.

Az export JSONL minden sora v/run_id/mode/simulated mezős. Megőrzi a
send/receive üzeneteket, batch_start/batch_end határokat, a monoton
host_elapsed_ms időpontokat és inter_batch_wait_ms adagközi szüneteket, az ablakok
sorrendjét, phase/series értékeket és a failure/run_complete állapotot.
A receive uart_wait_ms hostoldali kérés-válasz várakozás, az execute esetén
feldolgozásra várást is tartalmazhat; nem MCU-feldolgozási idő. Az
adagközi szünetet nem adjuk a processing_ms-hoz. A napló időadatainak
szimulációs eredete minden sorban jelölt, valódi hardveres eredményként
nem használhatók. A result exportsor csak a fent dokumentált eredménymezőket emeli ki a
rekordból; az extra rekordmezők nem írhatják át a kliens metaadatait és
figyelmen kívül maradnak. Az eredeti válasz a receive esemény message
objektumában továbbra is megmarad. A fájl csak run_complete esetén teljes.

## Példa

```json
{"v":1,"type":"start","request_id":"1","run_id":"demo","mode":"live"}
{"v":1,"type":"ack","request_id":"1","run_id":"demo","mode":"live","simulated":true}
{"v":1,"type":"execute","request_id":"3","run_id":"demo","mode":"live","batch_id":"b1","count":1,"period_ms":50}
{"v":1,"type":"fetch","request_id":"4","run_id":"demo","mode":"live","batch_id":"b1","offset":0}
{"v":1,"type":"results","request_id":"4","run_id":"demo","mode":"live","simulated":true,"batch_id":"b1","offset":0,"total":1,"records":[{"index":0,"window_id":"w0","batch_id":"b1","scheduled_ms":0,"status":"ok","processing_ms":3,"decision":"hold","decision_source":"simulator_stub"}]}
```

A start és execute közé load kell teljes 20 mintás ablakkal. Másolható,
teljes kérés- és válaszpéldákat a fenti demo exportja tartalmaz.
Saját bemenet: `--input windows.jsonl`, soronként egy window objektum.
Élő módban a teljes bemenet lehet nyolcnál több ablak is: a kliens egyablakos
adagokban mindet feldolgozza. A 16384 byte-os keretkorlát minden egyes load-ra
érvényes; a nyolcas teljes bemeneti korlát csak a benchmark munkakészletéé;
az alak a `gearshift.client.example_window` függvényből is előállítható.

## Elfogadási ellenőrzés

Automatizált: két mód, 12400 benchmark-feladat, ablakpárosítás, hibás JSON,
túlméret, verzióhiba, EOF, timeout, darabolt/összevont keretek,
érvénytelen ablakok, előfeldolgozás és túlterhelés. Futtatás:
`python3 -m unittest discover -s tests -v`.

Hardver: **nem futtatott**, nincs csatlakoztatott panel/firmware.
A firmware-rel azonos szerződés dokumentált; tényleges firmware-kompatibilitás,
UART nélküli fizikai futás és kétmódú paneles működés továbbra is ellenőrizendő.
