# Preverjanje RSS/Atom virov

Preverjeno: `2026-10-25T01:10:57Z` (UTC). Živi HTTP prenosi in razčlenjevanje s feedparser.

| Vir | Veljaven feed | Preverjeni URL |
| --- | --- | --- |
| Nature | DA | https://www.nature.com/nature.rss |
| Scientific American | DA | https://www.scientificamerican.com/platform/syndication/rss/ |
| Phys.org | DA | https://phys.org/rss-feed/ |
| Discover Magazine | DA | https://www.discovermagazine.com/rss/all |
| The Daily Galaxy | DA | https://dailygalaxy.com/feed/ |
| MarkTechPost | DA | https://www.marktechpost.com/feed/ |
| Wccftech | DA | https://wccftech.com/feed/ |
| Google News · U.S. | DA | https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSkwyMHZNRGxqTjNjd0VnVmxiaTFWVXlnQVAB?hl=en-US&gl=US&ceid=US:en |

Vseh 8 konfiguriranih virov deluje. Shranjeni feed vsebuje 332 člankov, od tega 238 s slikovnim URL-jem. Število vključuje še veljavne članke prejšnjih zajemov.

## Popravek Discover Magazine

Izhodiščni `https://www.discovermagazine.com/rss` je vrnil HTTP 403. Poskus RSS autodiscovery na domači strani in na `/page/rss` je prav tako naletel na HTTP 403. Javna RSS povezava `https://feeds.feedburner.com/AllDiscovermagazinecomContent` preusmeri na uradni `https://www.discovermagazine.com/rss/all`, ki vrne veljaven feed. Zato je YAML popravljen na neposredni uradni URL.

Števila se spreminjajo s časom. To je preverjanje povezljivosti iz lokalnega okolja; prvi zagon Actions lahko pokaže drugačen rezultat zaradi omejitev posameznega ponudnika. Napaka se zabeleži v `data/status.json` in ne zruši ostalih virov.

## Slike

Prednost imajo slike iz RSS (media:content, media:thumbnail, slikovni enclosure). Kjer jih ni, se enkrat preveri og:image v glavi članka. Brez dostopne slike se prikaže nevtralno CSS ozadje teme. Slikovne datoteke niso kopirane v repo. Veljaven slikovni URL še ne zagotavlja, da bo strežnik slike dovolil nalaganje v vsakem brskalniku.
