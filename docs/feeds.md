# Preverjanje RSS/Atom virov

Preverjeno: `2026-10-25T00:59:23Z` (UTC). Živi HTTP prenosi in razčlenjevanje s feedparser, brez vzorčnih člankov.

| Vir | Veljaven feed | Članki zadnjih 7 dni | Preverjeni URL |
| --- | --- | ---: | --- |
| Nature | DA | 75 | https://www.nature.com/nature.rss |
| Scientific American | DA | 50 | https://www.scientificamerican.com/platform/syndication/rss/ |
| Phys.org | DA | 30 | https://phys.org/rss-feed/ |
| Discover Magazine | DA | 20 | https://www.discovermagazine.com/rss/all |
| The Daily Galaxy | DA | 50 | https://dailygalaxy.com/feed/ |
| MarkTechPost | DA | 10 | https://www.marktechpost.com/feed/ |
| Wccftech | DA | 20 | https://wccftech.com/feed/ |
| Google News · U.S. | DA | 70 | https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSkwyMHZNRGxqTjNjd0VnVmxiaTFWVXlnQVAB?hl=en-US&gl=US&ceid=US:en |

Vseh 8 konfiguriranih virov deluje. Noben vir ob tem preverjanju ni nedosegljiv.

## Popravek Discover Magazine

Izhodiščni `https://www.discovermagazine.com/rss` je vrnil HTTP 403. Poskus RSS autodiscovery na domači strani in na `/page/rss` je prav tako naletel na HTTP 403. Javna RSS povezava `https://feeds.feedburner.com/AllDiscovermagazinecomContent` preusmeri na uradni `https://www.discovermagazine.com/rss/all`, ki vrne veljaven feed z 20 vnosi. Zato je YAML popravljen na neposredni uradni URL. Tudi `https://feeds.feedburner.com/DiscoverMag` vrne veljaven feed, vendar uporabljamo neposrednega.

Števila se spreminjajo s časom. To je preverjanje povezljivosti iz lokalnega okolja; prvi zagon Actions lahko pokaže drugačen rezultat zaradi omejitev posameznega ponudnika. Napaka se zabeleži v `data/status.json` in ne zruši ostalih virov.
