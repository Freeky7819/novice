# Novice

Osebni RSS/Atom feed za znanost, fiziko, vesolje, energijo, AI, strojno opremo in novice iz ZDA. Način **Uradno** prikazuje izvirne naslove in izvlečke virov. F2 doda slovenska načina **Povzeto** in **Po domače**, ko sta povzetka na voljo. Pod 600 px je glava visoka 64 px, uvod pa se skrči na vrstico z datumom in stanjem zajema.

Frontend je vanilla HTML/CSS/JS, brez frameworka ali build koraka. Python zajema RSS/Atom in slike. Lokalna storitev pripravi oba AI povzetka šele ob kliku ter poskusi prebrati javno dostopno besedilo izbranega članka. Za telefon je v mapi `worker/` pripravljena Cloudflare storitev; nastavitev računa, tri skrivnosti in vsaka objava zahtevajo Damjanov ročni korak oziroma potrditev. Navodila so v [docs/telefon.md](docs/telefon.md). Ključ ponudnika AI je potreben samo za nove povzetke, nikoli v brskalniku.

## Vklop GitHub Pages

1. Združi PR za F1 v `main`.
2. Odpri **Settings → Pages → Build and deployment → Source → GitHub Actions**. Ne izberi »Deploy from a branch«.
3. Odpri **Actions → Objavi Novice → Run workflow → main → Run workflow**. Če je samodejni prvi zagon po združitvi PR že uspel, ročni zagon ni potreben. Če je spodletel pred vklopom Pages, ga ponovi.
4. Po uspešnem zagonu odpri **https://freeky7819.github.io/novice/**. Workflow vrne tudi povezavo v okolju `github-pages`.
5. **Actions → Osveži novice → Run workflow** ročno preveri zajem. Nato urnik `*/30 * * * *` sam zajema vire približno vsakih 30 minut. GitHub lahko zagon zamakne; pri neaktivnih javnih repozitorijih lahko urnik po 60 dneh izključi.

Vsi trije workflowi za objavo (`pages.yml`, `fetch.yml`, `shrani-povzetek.yml`) uporabljajo skupino `pages` in `queue: max`, zato se objave vrstijo. Samo prenese statične datoteke na Pages; ničesar ne prevaja ali gradi. `data/config.json` je javni izvoz nastavitev, da brskalnik ne potrebuje YAML knjižnice.

Na iPhonu odpri objavljeno stran v **Safariju → Deli → Dodaj na domači zaslon**. Manifest ima relativni `scope` in `start_url`, PNG ikoni ter minimalen service worker. Namestitev na dejanskem iPhonu še ni preizkušena. Shranjevanje feeda za uporabo brez povezave ostaja za F4.

## Lokalni zagon

Potrebuješ Python 3.12. V PowerShellu:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe start_local.py
```

Ključ vneseš skrito ob zagonu; Enter brez ključa omogoči branje že shranjenih povzetkov. Odpri **http://127.0.0.1:8765/** in pusti terminal odprt. Novi povzetki se pripravijo samo ob kliku; oba načina se shranita. Navaden statični strežnik novih povzetkov ne izvaja. Navodila za ponudnika, omejitve in poznejše gostovanje so v [docs/on-demand.md](docs/on-demand.md).

## Viri in teme

- V `config/sources.yaml` uredi `id`, `name`, `url`, `topics` in `enabled`. Polje `excerpt: false` izključi izvleček tega vira (npr. pri Google News).
- V `config/topics.yaml` uredi oznake, ključne besede in `exclude_keywords`.
- Teme članka so unija tem vira in zaznanih ključnih besed. Ključne besede se ujemajo na mejah besed. Kratice z vsemi velikimi črkami (AI, LLM, NVIDIA) se ujemajo case-sensitive, ostale besede in fraze case-insensitive. Teme se ob zajemu ponovno izračunajo tudi za hranjene članke.
- Nastavitve na strani filtrirajo prikaz na posamezni napravi. V `localStorage` so shranjene izbire tem, virov in videza; napaka shrambe ne prepreči uporabe aplikacije.
- Gumb osveži ponovno naloži zadnji objavljeni JSON. Ne sproži GitHub Actions ali neposrednega branja RSS v brskalniku.

Podatki hranijo do 500 člankov iz zadnjih sedmih dni, razvrščenih od najnovejših. ID je SHA-1 normaliziranega URL-ja. Pri izpadu vira ostanejo prejšnji članki do izteka sedmih dni; opozorilo je v `data/status.json` in nastavitvah aplikacije. Vnosom brez datuma ostane čas prvega zaznavanja, dokler so v hranjenem feedu.

## Slike in priprava sloga

Vsak članek ima `image` (izvirni URL ali `null`). Prednost imajo `media:content`, `media:thumbnail` in slikovni `enclosure`. Nato se uporabi prvi varen `<img src>` v `content:encoded` / `content[].value`. Slike z znano širino ali višino pod 100 px se preskočijo. Če slike ni, se preveri `og:image` v HTML glavi, z običajnim brskalniškim User-Agentom, timeoutom 5 sekund in omejitvijo 512 KiB. Prenos se ustavi ob koncu glave in ne izlušči besedila članka.

Čas poskusa se zapiše v `image_tried_at`, število pa v `image_attempts`. Po neuspehu je dovoljen največ en ponovni poskus, najmanj 24 ur pozneje (skupaj največ dva poskusa OG). Zapisi stare različice brez teh polj se ob nadgradnji enkrat preverijo. Slika, ki se pozneje pojavi neposredno v feedu, se lahko uporabi tudi po doseženem limitu OG.

Za `gnews-us` se OG ne preverja in `image` ostane `null`. Iz `<source url="...">` se shranita `publisher` in `publisher_domain`; vrstica vira prikaže ime medija in »prek Google News«. Pripona » - Ime medija« se odstrani iz prikazanega naslova. Hranjene stare vnose brez teh podatkov dopolnimo le, če se ime na koncu naslova ujema s parom medij/domena, potrjenim v trenutnem feedu. Google News ima `excerpt: false`, zato seznam drugih naslovov ne nastopa niti kot izvleček niti kot vhod za teme.

Sličice prepoznamo po širini media:thumbnail/content pod 400 px ali vzorcih URL (/tmb/, /thumb, -t.jpg, -150x150 …). Zanje najprej poskusimo OG; če ne uspe, ostane prvotna sličica. Pri naslednjem zajemu se uspešno pridobljena večja slika ohrani. Brskalnik preveri tudi dejanski `naturalWidth`: pod 400 px kartica dobi razred `thumb` in 96 × 96 px sliko levo ob naslovu.

Slike ostanejo na izvirnih strežnikih in se ne kopirajo v repo. Brskalnik uporabi `loading="lazy"`, `referrerpolicy="no-referrer"`, razmerje 16 : 9 in `object-fit: cover`. Brez slike ali ob napaki nalaganja je kartica kompaktna: vir, čas, naslov in oznake, brez velikega placeholderja ali izvlečka v načinu Uradno. Izbrani AI povzetek se prikaže tudi na taki kartici.

`config/style.md` vodi slog »Po domače«. V nastavitvah izberi privzeti način, na kartici pa ga lahko spremeniš samo za ta članek. Če povzetka ni, ga klik pripravi in pokaže stanje čakanja ali jasno napako. Podrobnosti lokalnega zagona in menjave ponudnika so v [docs/on-demand.md](docs/on-demand.md). Za telefon nastavi Worker URL in osebno kodo po [docs/telefon.md](docs/telefon.md).

Rezultati začetnega preverjanja osmih virov so v [docs/feeds.md](docs/feeds.md). Discoverjev izhodiščni `/rss` je vračal HTTP 403; popravljen je na preverjen `/rss/all`. Zajem ob napaki poskusi RSS autodiscovery na domači strani vira. Če vir tudi tam ne deluje, zabeleži napako in nadaljuje.

## Dovoljenja in varnost

`fetch.yml` loči zajem (samo `contents: read`, brez shranjenih Git poverilnic), shranjevanje podatkov (`contents: write`) in objavo (`pages: write`, `id-token: write`). Samo opravilo `commit` ima `contents: write`; v njem ni izvajanja RSS obdelave ali nameščanja odvisnosti in dodaja samo `data/*.json`. GitHub dovoljenja veljajo za celoten repozitorij in jih **ni mogoče tehnično omejiti samo na mapo**. Omejitev poti zato zagotavlja izrecni `git add -- data/*.json`. Pred commitom preveri razlike.

`status.json` beleži čas vsakega preverjanja, zato se lahko spremeni tudi, kadar ni novih člankov. `feed.json` ob nespremenjenih člankih ohrani prvotni `generated_at` in se ne prepisuje.

Vse besedilo v brskalniku se vstavi prek `textContent`, brez `innerHTML`. Povezave dopuščajo samo HTTP(S) in odpirajo izvirnik z `noopener noreferrer`. HTML iz izvlečkov se odstrani, dolžina je omejena na 400 znakov. Omrežni prenosi so časovno in velikostno omejeni, preverijo javne naslove in preusmeritve.

Repozitorij in Pages sta predvidena kot javna. Ne shranjuj zasebnih URL-jev, gesel ali drugih skrivnosti v konfiguracijo. AI se kliče samo ob kliku: lokalno v Python storitvi ali na telefonu prek Workerja. Ključ ostane v okolju procesa oziroma Cloudflare secretu. RSS workflow nima AI ključev in ne ustvarja novih povzetkov. Worker uporablja Anthropic Haiku iz konfiguracije; lokalna storitev podpira tudi OpenAI. Issue-flow, gruče, oznake novega obiska in F5/F6 še niso implementirani.

## Preverjanje

```sh
python -m unittest discover -s tests -v
node --check app.js
node --check sw.js
node --test tests/test_frontend.cjs
```

Node je potreben le za preverjanje sintakse in frontend testov, ne za delovanje ali objavo aplikacije. CI izvaja iste teste ob PR. Vključeni so preverjanje čiščenja HTML, nevarnih URL-jev, izolacije napake vira, autodiscovery, datumov, izključitev, shranjevanja brez sprememb in ohranitve podatkov pri izpadu. Prikaz je preverjen tudi v brskalniku pri širini 360 px.
