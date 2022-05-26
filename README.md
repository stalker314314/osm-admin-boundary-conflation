# Import prostornih jedinica

## Install

Linux is far convenient to install all these Python packages. On Windows, your best bet is Conda, but here are brief instractions for Debian:
```
sudo apt install proj-bin libproj-dev
python -m pip install -r requirements.txt 
```

## English

Tools to help with conflation of admin_level boundary ways from some external truth to OSM while preserving history.
Given `shapely` line, this tool can (heuristically) find and move nodes of existing OSM way (and add/remove nodes while doing it).
It also takes care of edge cases:
* boundary is national border,
* boundary share part of way with some other relation, like national park,
* boundary contains node that is part of some other relation,
* boundary contains node that has some other tags, like traffic light
* ...

Project was conceived as a helper for Serbian cadastre import, but can be used outside of it with some hacking.
Most important logic is in `conflate.py`. Contact author if you want to find your way around.

Project uses local overpass server instance using docker. If you do not set up your own server, change all occurrences of
"http://localhost:12345/api/..." to public server (instead of couple of hours, it can take days!). If you need fresh data,
either configure local overpass to do minutely updates, or use public instances.

## Srpski

Alat za uvoz registra prostornih jedinica iz otvorenih podataka RGZ-a.

Projekat je završen manje-više, tema na forumu je na https://forum.openstreetmap.org/viewtopic.php?pid=773121.

Ovaj projekat je u stanju da:
* Skine RGZ podatke automatizovano i od takvih CSV-ova napravi .shp i .osm fajlove
* Skine OSM podatke iz geofabric-a u lokalnu overpass instancu
* Uradi analizu gde je konflacija moguća i da proizvede HTML fajl sa rezultatima
  * Svaki way ima analizu da li je konflacija urađena već, da li je moguća i ako nije moguća - zašto nije
  (to mogu biti razni razlozi - od toga da je put deo neke druge relacije (šuma), da je deo državne granice, da je vezan za
  neki čvor (semafor, ...) i razni drugi)
* Tamo gde je konflacija moguća, alat može da je automatizovano izvede (uz provere da novonapravljeni put nije mnogo pomeren i sl.)
* Posle može da izmeri za svaku opštinu i naselje koji je procenat poklapanja površina
* Na kraju, sve ovo može da se automatizuje i da za nekih 30min-1h skripta uradi početno merenje, zatim skine i parsira
novi RGZ, uporedi sa prethodnih stanjem, i pošalje na Telegram poruku ukoliko se neko naselje ili opština pogoršala.
Onda učita novi OSM i vidi da li se tu nešto pogoršalo u odnosu na početno merenje. Ova skripta može da se pokreće dnevno.

Fajlovi od interesa:
* `measurement.sh` &mdash; skripta koja može da se pokrene jednom dnevno i da pošalje na Telegram ako primeti da je stanje lošije nego juče
* `refresh-rgz-data.sh` &mdash; skripta koja skida sve .csv-ove sa RGZ sajta i napravi .shp i .osm fajlove
+ `refresh-osm-data.sh` &mdash; skripta koja sa geofabrika skine .pbf i učita ga u lokalnu overpass instancu
* `rpj-to-geometry.py` &mdash; konvertuje ulazne (RGZ) .csv fajlove u EPSG32634 shapefile-ove
* `measure_quality_naselja.py` &mdash; skripta koja generiše `measure_quality_naselja.csv` koji spaja naselja iz RPJ-a i OSM-a i gleda koliko se slažu
* `conflate.py` &mdash; glavna skripta koja generiše `conflate-progress.pickle` (python pickle format) fajl koji
  analizira koji way-ovi mogu da se conflate-uju i radi automatsku konflaciju
* `conflate-statistics.py` &mdash; skripta koja na osnovu `conflate-progress.pickle` izbacuje `index.html` stranu sa rezultatima conflate-ovanja
* `send_notifications.py` &mdash; finalna skripta koja poredi merenja pre i posle i šalje na Telegram (treba podesiti token od Telegram bota i kanal na koji da se šalju obaveštenja)
* `preklapanja.py` &mdash; skripta koja iz naselja.csv generiše .csv fajl sa wkt geometrijama sa novoformiranim, conflate-ovanim putevima
* `translation.py` &mdash; uzet sa projekta https://github.com/maxerickson/michigantownships i koristi se za generisanje naselja.osm fajla
* `add_maticni_broj.py` &mdash; jednokratna skripta koja je iz ulaznog `measure_quality_naselja.csv` dodavala automatski u OSM `ref:RS:naselje` i `ref:RS:opstina` tamo gde je mogla

Projekat koristi lokalnu instancu overpass servera. Skripta da vidite kako podešava overpass je u `refresh-osm-data.sh`.
Ako ne podesite Vaš server, promenite sve instance "http://localhost/overpassapi..." na javne servere (ali ono što traje
par sati će tada trajati danima!). Ako vam trebaju podaci svežiji od jednog dana, ili namestite overpass da radi češća
ažuriranja, ili koristite javne instance.

Da bi vam ovo sve radilo, morate da postavite:
* fajl `osm-password` u kome je samo jedna linija sa `<username>:<password>` sadržajem (logovanje na OSM).
  Nije potrebno ako ne planirate da skripta za konflaciju radi automatsko submitovanje changeset-ova
* fajl `rgz-password` u kome je samo jedna linija sa `<username>:<password` sadržajem (logovanje na RGZ sajt).
  Nije potrebno ako ne planirate da skidate .csv fajlove sa RGZ sajta
* `OVERPASS_DIR` - env promenljiva kojom postavljate root putanju do instance overpass servera. Nije potrebno ako ne
  koristite lokalni overpass server ili ne koristite `refresh-osm-data.sh` skriptu
* `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` - env promenljive za Telegram bota (identifikacija bota i gde da šalje obaveštenja).
  Nije potrebno ako se ne koristi slanje obaveštenja o pogoršanom stanju OSM-a.
