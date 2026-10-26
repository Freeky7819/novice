# Povzetki na telefonu — navodila za Damjana

Stran ostane na GitHub Pages. Nov povzetek ob kliku pripravi **en Cloudflare Worker `novice-povzetki`**, hrani ga **en KV namespace `SUMMARIES`** in pošlje GitHubu dogodek `povzetek`. Drugih Cloudflare virov ta rešitev ne potrebuje in jih ne ustvarja. Lokalni `server.py` ostane uporaben brez osebne kode.

**Ta PR ničesar ne objavi na Cloudflare. Pred vsakim deployem, ustvarjanjem vira ali drugo spremembo računa mora asistent najprej povedati točen poseg in počakati na tvojo potrditev.** Tudi `secret put` je sprememba oziroma objava različice Workerja. OAuth prijavo in vse vnose skrivnosti opraviš ti. Asistent ne bere, ne izpisuje in ne vpisuje vrednosti `ANTHROPIC_API_KEY`, `NOVICE_KODA` ali `GITHUB_TOKEN_NOVICE`; ne pošiljaj jih v klepet, Git ali posnetek zaslona.

## 1. Račun in lokalna orodja

Ustvari/prijavi svoj [Cloudflare račun](https://dash.cloudflare.com/). Upoštevana so [uradna navodila Agent Setup](https://developers.cloudflare.com/agent-setup/prompt.md): Cloudflare skills se namestijo v Codexovo mapo skills, MCP pa se registrira z:

```powershell
codex mcp add cloudflare --url https://mcp.cloudflare.com/mcp
codex mcp login cloudflare
```

Če prvi ukaz že odpre OAuth, dodatni `login` ni potreben. Prijavo/odobritev opraviš sam v brskalniku. Na računalniku, kjer je bil pripravljen ta PR, so skills in MCP že nameščeni, OAuth pa je uspel. Za nalaganje novih MCP orodij po potrebi ponovno odpri Codex. To ni dovoljenje za spreminjanje računa. Dodatni izbirni `cf` CLI ni potreben; uporabljamo zahtevani Wrangler.

Najprej združi ta PR, da je workflow `Shrani povzetek` na glavni veji. Posodobi lokalni repozitorij. Potrebuješ Node.js 22 in Python 3.12. V korenu repozitorija:

```powershell
.\.venv\Scripts\python.exe prepare_worker.py
cd worker
npm ci
npx --no-install wrangler login
```

Wrangler ima svojo OAuth prijavo; v brskalniku jo potrdiš ti. Izberi pravi Cloudflare račun. `wrangler whoami` lahko preveri prijavljeni račun; pri več računih v `wrangler.toml` dodaj njegov javni `account_id`, da je cilj nedvoumen. Ne ustvarjaj dodatnih okolij ali preview virov.

## 2. En KV namespace

Pred tem korakom potrdimo: **ustvariti samo KV namespace `SUMMARIES` na tvojem izbranem računu**. Nato:

```powershell
npx --no-install wrangler kv namespace create SUMMARIES
```

Vrnjeni javni `id` vpiši v `worker/wrangler.toml` namesto `REPLACE_WITH_KV_NAMESPACE_ID`; `binding` ostane `SUMMARIES`. Če namespace že obstaja, uporabi njegov ID, ne ustvarjaj drugega. ID ni skrivnost. V konfiguraciji ni Durable Objectov, D1, R2, Queues ali drugih virov.

## 3. Prva objava Workerja

Pred tem korakom potrdimo: **objaviti kodo tega PR kot en Worker `novice-povzetki`, povezati obstoječi KV, brez dodatnih virov**. Nato v mapi `worker`:

```powershell
npx --no-install wrangler deploy
```

Brez skrivnosti ta različica ne dela AI klicev. Wrangler izpiše pravi HTTPS naslov Workerja. Ne uporabljaj izmišljenega URL-ja: poddomena je odvisna od tvojega računa. Za vse nadaljnje objave in spremembe nastavitev velja enako: najprej opis in tvoja potrditev. V PR ni workflowa za samodejni Cloudflare deploy.

## 4. Osebna koda in tri skrivnosti

Kodo ustvari **sam v svojem terminalu**, da je asistent ne vidi:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Shrani jo v svoj upravljalnik gesel. Isti niz uporabi za `NOVICE_KODA` in pozneje v nastavitvah strani na telefonu. Ne izmisli si kratke kode in je ne prilepi v klepet.

V GitHubu ustvari **fine-grained personal access token**:

1. Profil → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Resource owner: **Freeky7819**. Določi rok veljavnosti, npr. 30 ali 90 dni.
3. Repository access: **Only select repositories → novice**.
4. Repository permissions: **Contents → Read and write**. Metadata read je samodejen. Ne dodajaj dostopa do drugih repozitorijev, Actions write ali administracije.
5. Žeton ustvariš in preneseš v Cloudflare sam. Po poteku ga zamenjaš z novim z istim omejenim obsegom. Žeton omogoča zahtevani [repository_dispatch s Contents write](https://docs.github.com/en/rest/repos/repos#create-a-repository-dispatch-event).

Pripravi svoj Anthropic API ključ iz računa ponudnika. Nato po opisu in potrditvi **vsakega posameznega posega** sam izvedi naslednje ukaze v mapi `worker`. Vrednosti vneseš v skrito vprašanje Wranglerja, ne v ukaz:

```powershell
npx --no-install wrangler secret put ANTHROPIC_API_KEY
npx --no-install wrangler secret put NOVICE_KODA
npx --no-install wrangler secret put GITHUB_TOKEN_NOVICE
```

To so ukazi `wrangler secret put <IME>` z lokalno nameščenim Wranglerjem. Ne uporabljaj `echo`, argumenta z vrednostjo, `.env` datoteke v repozitoriju ali bulk izpisa skrivnosti. [Cloudflare secret put](https://developers.cloudflare.com/workers/configuration/secrets/) sam objavi novo različico Workerja; dodatni deploy samo zaradi teh vnosov ni potreben. Asistent teh treh ukazov ne izvede namesto tebe.

## 5. Naslov API in telefon

Pravi Worker URL vpiši v `config/ai.yaml` v polje `api_url`, npr. zamenjaj prazni niz z **dejanskim naslovom iz izpisa deploya** (brez skrivnosti). Za skupno privzeto nastavitev zaženi `python prepare_worker.py` oziroma ustrezni Python iz `.venv`, shrani spremembi `config/ai.yaml` in `data/config.json` v Git ter objavi Pages. Frontend uporablja polje `summary_api` iz javnega configa. Pred dejansko objavo je to polje namenoma prazno, ker računova poddomena še ni znana.

Lahko tudi takoj, brez spremembe skupne nastavitve, na telefonu odpreš **https://freeky7819.github.io/novice/** → zobnik → **Naslov API** in vneseš svoj HTTPS Worker URL. Polje privzeto pokaže URL iz configa, ko je ta nastavljen; osebna izbira ga preglasi. Dovoljen je korenski Worker URL ali isti URL s koncem `/api/summary`.

V **Osebna koda** vnesi ustvarjeni niz. Polje je tipa password; koda in osebni naslov se shranita samo v localStorage te naprave (napaka shrambe ne sesuje strani). Koda se pošlje samo izbranemu API v glavi `X-Novice-Koda`, nikoli v URL-ju. Anthropic ključ in GitHub žeton ostaneta v Cloudflare secrets, ne na telefonu.

Klikni **Povzeto** ali **Po domače** na članku brez povzetka. Oba načina nastaneta v enem klicu in se shranita. Brez kode lahko bereš že objavljene ali na napravi shranjene povzetke; novi klik pokaže navodilo za vnos kode. Lokalni `server.py` uporablja svojo relativno pot in ne zahteva kode ali oddaljenega API.

## 6. Kaj preveriti po objavi

- Na telefonu odpri oba načina istega članka: samo prvi pripravi rezultat. Pod kartico piše osnova: dostopno besedilo, javni del, izvleček ali naslov.
- V GitHub **Actions → Shrani povzetek** preveri uspešen tek in commit `data: povzetek <id>`. Po objavi Pages je rezultat na voljo tudi drugi napravi brez kode. Povzetki so javni; skrivnosti niso del dogodka ali commita.
- Če objava v GitHub ne uspe, rezultat ostane v KV in na kartici vidiš pojasnilo. Po vsaj 90 sekundah na napravi brez lokalnega predpomnilnika ponovno zahtevaj isti ID; Worker ponovi samo neuspešno pošiljanje, brez novega AI klica. Že sprejet dispatch pomeni sprejem dogodka, ne jamstva uspešnega workflowa: neuspešen workflow ponovi z **Re-run jobs**. Pri spremembi modela stare neobjavljene dogodke preveri pred ponovno objavo.
- Napačna koda vrne 401 brez podrobnosti; tuj ali manjkajoč Origin 403. CORS je omejen na `https://freeky7819.github.io`, zato test iz druge lokalne spletne strani ni podprt. Lokalni Python zagon še naprej deluje kot prej.

## Varovalke in omejitve

Brskalnik sme poslati samo `{"id":"..."}`. ID mora biti v javnem feedu (predpomnilnik 5 minut), vir omogočen in ne izločen. Cache v KV ali `data/summaries.json` ima prednost pred novim klicem. Koda se primerja s konstantnočasnim `crypto.subtle.timingSafeEqual` nad dvema SHA-256 zgoščenkama enake dolžine.

Članek se bere samo prek HTTP(S), brez gesel in nestandardnih vrat, samo z izrecnih domen tega vira iz `data/config.json`; enaka kontrola velja po vsaki preusmeritvi in za robots.txt. Brez poljubnih URL-jev. Robots prepoved, crawl-delay/request-rate, paywall, zavrnitev ali napaka pomenijo naslov/izvleček, brez obhoda. Največ 15 sekund za celotno branje, 1 MB članka, 64 KiB robots in 12.000 znakov izluščenega besedila. Worker izlušči odstavke/naslove iz article/main, brez menijev, skript in stranskih blokov; nekatere strani zato uporabijo izvleček. Google News ne dovoljuje obiska poljubne domene drugega medija.

Prompt, slog in model se izvozijo iz istih Python navodil ter `config/style.md`/`config/ai.yaml` z `prepare_worker.py`; CI prepreči zastarel izvoz. Izhod ima samo `neutral`, `mine`, `topics`, vsak povzetek do 600 znakov, brez kotnih oklepajev/HTML in samo veljavne teme. Zavrnejo se tudi podvojeni JSON ključi. Ni orodij ali modelom usmerjenih URL-jev. Napaka/invalidni izhod porabi poskus in vrne 502, brez samodejne ponovitve.

Privzeto **50 poskusov/dan UTC** (`AI_MAX_PER_DAY` v Wrangler configu), tudi napake, ponovni poskus istega ID po 90 sekundah. Vsak poskus dobi unikaten trajni zapis v KV pred AI klicem; dnevni zapisi se hranijo tri dni. **KV je eventually consistent in nima atomskih rezervacij: ob res sočasnih zahtevah v različnih instancah/regijah dnevni limit in preprečevanje dvojnega klica nista stroga globalna garancija.** Lokalna varovala omejijo sočasne zahteve v isti instanci. Ostajamo pri zahtevanih enem Workerju in enem KV; za strogo garancijo bi potrebovali dodatnega koordinatorja, ki ni del tega PR. Na Anthropic računu nastavi še ustrezno omejitev porabe. [Razlaga KV omejitev](https://developers.cloudflare.com/kv/concepts/how-kv-works/).

Vsi trije Pages workflowi imajo `concurrency: pages`, `queue: max`, brez prekinitve trenutnega teka. To prepreči običajno zamenjavo čakajočega dogodka z novejšim; vrsta ima platformno omejitev 100 čakajočih tekov. Dispatch validator preveri ID, omogočen vir, izključitve, točne ključe, dolžine, teme, HTML, model in čas še pred pisanjem datoteke; payload se nikoli ne vstavi v ukazno lupino. Commit doda samo `data/summaries.json`, sledi pull --rebase in push. Workflow sam objavi Pages, ker push z GITHUB_TOKEN ne sproži običajnega push workflowa. Neveljaven dogodek pade brez commita.

Skrivnosti, prompti in besedilo članka se ne beležijo; v KV sta samo rezultat in evidenca poskusov/pošiljanja. Ni `console.log` ali izpisov izjem. Samodejna Cloudflare observability je izključena, da ne shranjujemo dodatnih podatkov zahtev.

## Preverjanje pred posegi v račun

V korenu: `python -m unittest discover -s tests`, `node --test tests/test_frontend.cjs`, `python prepare_worker.py --check`. V `worker`: `npm ci`, `npm test`, `npx --no-install wrangler deploy --dry-run`. Zadnji ukaz samo preveri lokalno pakiranje, ne objavlja in ne ustvarja virov. 63 Python testov, 7 frontend testov in 13 Worker testov uporablja lažen Anthropic/GitHub in tudi dejanski lokalni Workers runtime s testnim KV/HTMLRewriter. Ni pravih AI klicev ali oddaljenih zapisov.
