# Povzetki ob kliku: lokalna različica

Klik na **Povzeto** ali **Po domače** za članek brez povzetka sproži eno zahtevo. Strežnik poskusi prebrati javno dostopno besedilo tega članka in z enim AI klicem pripravi oba načina. Med čakanjem kartica pokaže »Pripravljam povzetek …«. Nadaljnji preklopi uporabijo shranjeni rezultat. Odpiranje strani, izbira privzetega načina in RSS urnik ne sprožajo novih AI klicev.

## Zagon na Windows

V mapi repozitorija zaženi:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe start_local.py
```

Zaganjalnik vpraša za ključ izbranega ponudnika; vnos je skrit in ostane samo v okolju procesa, brez datoteke ali zgodovine ukazov. Ključa ne pošiljaj v klepet. Enter brez ključa omogoči samo že shranjene povzetke. Odpri **http://127.0.0.1:8765/** in pusti terminal odprt. Navaden `python -m http.server` ne podpira povzemanja ob kliku.

Če je ključ že v okolju procesa (`ANTHROPIC_API_KEY` oziroma `OPENAI_API_KEY`), lahko zaženeš tudi `server.py`. Obstoječega GitHub Secreta lokalna aplikacija ne more prebrati. Za menjavo ponudnika pred zagonom nastavi `$env:AI_PROVIDER='openai'` ali `'anthropic'`; model določa `config/ai.yaml` oziroma `AI_MODEL`. Privzeti ponudnik ostaja Anthropic.

## Kaj se pošlje in shrani

- Brskalnik pošlje `POST /api/summary` z JSON `{"id":"<ID iz feeda>"}`. Ne sprejema poljubnega URL-ja ali navodil. Odgovor vsebuje `id`, `neutral`, `mine`, `topics`, `basis`, `cached`.
- Strežnik poišče ID v trenutnem feedu in preveri omogočen vir ter izključitve. Spoštuje robots.txt, preverja javne naslove/preusmeritve ter omeji prenos na 1 MB in približno 20 sekund. Strani z omejitvami crawl-delay/request-rate konservativno preskoči. Plačilnih zidov in zavrnitev ne obide.
- Ponudniku pošlje naslov, izvleček, ime vira in največ 12.000 znakov izluščenega besedila. Slog »Po domače« vodi `config/style.md`. Članek je nezaupanja vreden podatek, brez dostopa do orodij ali drugih člankov.
- Oznaka pod kartico pove, ali je osnova dostopno besedilo, samo javni del, izvleček ali naslov. Besedilo je lahko skrajšano; oznaka ne jamči celotnega članka. Če branje ne uspe, povzetek jasno temelji na naslovu/izvlečku.
- Stroga validacija zahteva samo `neutral`, `mine`, `topics`, največ 600 znakov na povzetek, brez HTML in samo dovoljene teme. Neveljaven izhod se zavrže. Frontend uporablja `textContent`, localStorage pa je zaščiten s try/catch.
- Uspešna rezultata in evidenca poskusov se shranita v **`.local/on-demand.json`**, ki je izključena iz Gita in spletnega strežnika. Surovi HTML, besedilo članka, prompti in ključ se ne shranjujejo ali izpisujejo. Brskalnik shrani oba povzetka tudi na napravi. Obstoječi `data/summaries.json` ostane berljiv brez ponovnega plačila.

## Limiti in napake

Privzeto je največ **200 poskusov na dan UTC** (`AI_ON_DEMAND_MAX_PER_DAY` oziroma `max_per_day`). V današnje štetje so vključeni tudi stari paketni poskusi. Napake štejejo; ponovnega samodejnega klica ni. Ročni ponovni klik je mogoč po 90 sekundah. Sočasni kliki istega članka delijo rezultat; rezervacija pred klicem prepreči prekoračitev dnevnega limita pri različnih člankih v istem procesu. Ne zaženi več procesov nad isto lokalno shrambo in je ne briši za redno čiščenje.

Manjkajoč ključ vrne 503, dnevni limit/kratek razmik 429, izključen članek 403, neznan ID 404, neuspešen ali neveljaven AI odgovor 502. Kartica pokaže razumljivo sporočilo, izvirnik pa ostane dosegljiv. Preklop nazaj na Uradno med čakanjem ostane izbran tudi po prihodu povzetka.

## GitHub Pages in poznejše gostovanje

Ta PR pripravi lokalno storitev; **ne objavi strežniške funkcije**. GitHub Pages še naprej prikazuje novice in že shranjene povzetke. Za nove povzetke na telefonu bo treba pozneje gostiti API ter dodati ustrezno avtentikacijo in skupno trajno shrambo/omejevanje porabe. Lokalni strežnik posluša izključno na 127.0.0.1, preverja Host/Origin in ne daje ključev brskalniku. Kot tak ni namenjen javni objavi.

`config/ai.yaml` ima `mode: on_demand`; RSS workflow nima več AI ključev in izvaja samo povezovanje obstoječih povzetkov z `AI_MAX_PER_RUN=0`. Tudi istoimenska repozitorijska spremenljivka je bila ob pripravi nastavljena na 0, da stara različica med čakanjem na merge ne ustvarja novih povzetkov. Zajem RSS ostaja vsakih 30 minut.

Strošek nastane samo pri novem zahtevanem povzetku, oba načina sta vključena v isti klic. Izračun je `novi članki × (vhodni tokeni × vhodna cena + izhodni tokeni × izhodna cena) / 1.000.000`. Polno besedilo porabi več vhodnih tokenov kot prejšnji naslov/izvleček; strošek je odvisen od tega, koliko člankov dejansko odpreš. Limit števila klicev ni denarna kapica.

Po [ceniku Anthropic](https://platform.claude.com/docs/en/about-claude/pricing), preverjenem 25. 10. 2026, Haiku 5.5 za kratke prompte stane 0,10 USD/milijon vhodnih in 0,50 USD/milijon izhodnih tokenov. Pri predpostavljenih 6.000 vhodnih in 600 izhodnih tokenih je to približno **0,0009 USD na nov članek**: 20 kliknjenih novih člankov približno 0,018 USD/dan, 50 približno 0,045 USD/dan, 200 približno 0,18 USD/dan. Trenutnih 351 hranjenih člankov / 7 dni pomeni grobo 50 člankov/dan, vendar se po novem obračunajo samo zahtevani, še neshranjeni povzetki. To ni izmerjena poraba ali zagotovljena zgornja meja; dolžina, tokenizacija in cene se lahko spremenijo, davki niso vključeni.

## Preverjanje

55 Python testov in 4 frontend testi uporabljajo lažne ponudnike, lažen prenos člankov in lokalni HTTP strežnik, brez plačljivih klicev. Pokriti so izbira samo zahtevanega članka, oba rezultata, predpomnilnik po ponovnem zagonu, sočasni kliki in limiti, izpadi, robots, zasebne preusmeritve, nezaupanja vredni izhodi ter prikaz med čakanjem in po ponovnem nalaganju.
