# Novice

Osebni RSS/Atom feed za znanost, fiziko, vesolje, energijo, AI, strojno opremo in novice iz ZDA. F1 prikazuje izvirne naslove in izvlečke virov (način **Uradno**). Izvlečki niso prevedeni.

Vanilla HTML/CSS/JS, brez frameworka, npm odvisnosti ali build koraka. Python zajema samo RSS/Atom, ne celotnih člankov. Brez strežnika, baze, ključev ali prijave.

## Vklop GitHub Pages

1. Združi PR za F1 v `main`.
2. Odpri **Settings → Pages → Build and deployment → Source → GitHub Actions**. Ne izberi »Deploy from a branch«.
3. Odpri **Actions → Objavi Novice → Run workflow → main → Run workflow**. Če je samodejni prvi zagon po združitvi PR že uspel, ročni zagon ni potreben. Če je spodletel pred vklopom Pages, ga ponovi.
4. Po uspešnem zagonu odpri **https://freeky7819.github.io/novice/**. Workflow vrne tudi povezavo v okolju `github-pages`.
5. **Actions → Osveži novice → Run workflow** ročno preveri zajem. Nato urnik `*/30 * * * *` sam zajema vire približno vsakih 30 minut. GitHub lahko zagon zamakne; pri neaktivnih javnih repozitorijih lahko urnik po 60 dneh izključi.

Objava uporablja priložena workflowa `pages.yml` in `fetch.yml`. Samo prenese statične datoteke na Pages; ničesar ne prevaja ali gradi. `data/config.json` je javni izvoz nastavitev, da brskalnik ne potrebuje YAML knjižnice.

Na iPhonu odpri objavljeno stran v **Safariju → Deli → Dodaj na domači zaslon**. Manifest ima relativni `scope` in `start_url`, PNG ikoni ter minimalen service worker. Namestitev na dejanskem iPhonu še ni preizkušena. Shranjevanje feeda za uporabo brez povezave ostaja za F4.

## Lokalni zagon

Potrebuješ Python 3.12:

```sh
python -m pip install -r requirements.txt
python fetch.py
python -m http.server 8765
```

Odpri `http://localhost:8765/`. Če želiš samo pogledati priložene podatke, zadostuje zadnji ukaz. Spletno aplikacijo lahko gostiš v korenu ali pod `/novice/`, saj so vse poti relativne.

## Viri in teme

- V `config/sources.yaml` uredi `id`, `name`, `url`, `topics` in `enabled`.
- V `config/topics.yaml` uredi oznake, ključne besede in `exclude_keywords`.
- Teme članka so unija tem vira in zaznanih ključnih besed. Kratke ključne besede, kot je AI, se ujemajo na mejah besed.
- Nastavitve na strani filtrirajo prikaz na posamezni napravi. V `localStorage` so shranjene izbire tem, virov in videza; napaka shrambe ne prepreči uporabe aplikacije.
- Gumb osveži ponovno naloži zadnji objavljeni JSON. Ne sproži GitHub Actions ali neposrednega branja RSS v brskalniku.

Podatki hranijo do 500 člankov iz zadnjih sedmih dni, razvrščenih od najnovejših. ID je SHA-1 normaliziranega URL-ja. Pri izpadu vira ostanejo prejšnji članki do izteka sedmih dni; opozorilo je v `data/status.json` in nastavitvah aplikacije. Vnosom brez datuma ostane čas prvega zaznavanja, dokler so v hranjenem feedu.

Rezultati preverjanja vseh osmih virov so v [docs/feeds.md](docs/feeds.md). Discoverjev izhodiščni `/rss` je vračal HTTP 403; popravljen je na preverjen `/rss/all`. Zajem ob napaki poskusi RSS autodiscovery na domači strani vira. Če vir tudi tam ne deluje, zabeleži napako in nadaljuje.

## Dovoljenja in varnost

`fetch.yml` loči zajem (samo `contents: read`, brez shranjenih Git poverilnic), shranjevanje podatkov (`contents: write`) in objavo (`pages: write`, `id-token: write`). Samo opravilo `commit` ima `contents: write`; v njem ni izvajanja RSS obdelave ali nameščanja odvisnosti in dodaja samo `data/*.json`. GitHub dovoljenja veljajo za celoten repozitorij in jih **ni mogoče tehnično omejiti samo na mapo**. Omejitev poti zato zagotavlja izrecni `git add -- data/*.json`. Pred commitom preveri razlike.

`status.json` beleži čas vsakega preverjanja, zato se lahko spremeni tudi, kadar ni novih člankov. `feed.json` ob nespremenjenih člankih ohrani prvotni `generated_at` in se ne prepisuje.

Vse besedilo v brskalniku se vstavi prek `textContent`, brez `innerHTML`. Povezave dopuščajo samo HTTP(S) in odpirajo izvirnik z `noopener noreferrer`. HTML iz izvlečkov se odstrani, dolžina je omejena na 400 znakov. Omrežni prenosi so časovno in velikostno omejeni, preverijo javne naslove in preusmeritve.

Repozitorij in Pages sta predvidena kot javna. Ne shranjuj zasebnih URL-jev, gesel ali drugih skrivnosti v konfiguracijo. V F1 ni API klicev za AI, Issue-flowa, gruč ali oznak novega obiska. Datoteka s slogom za »Po domače« je vhod za poznejšo F2.

## Preverjanje

```sh
python -m unittest discover -s tests -v
node --check app.js
node --check sw.js
```

Node je potreben le za preverjanje sintakse, ne za delovanje ali objavo aplikacije. CI izvaja iste teste ob PR. Vključeni so preverjanje čiščenja HTML, nevarnih URL-jev, izolacije napake vira, autodiscovery, datumov, izključitev, shranjevanja brez sprememb in ohranitve podatkov pri izpadu. Prikaz je preverjen tudi v brskalniku pri širini 360 px.
