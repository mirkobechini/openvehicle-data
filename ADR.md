# Architecture Decision Record

**Progetto:** openvehicle-data
**Data:** 2026-09-18
**Autore:** Mirko Bechini

## Decisione

Database open source di marchi, modelli, varianti e specifiche tecniche di autovetture, a partire dal mercato italiano. Dati esposti tramite dataset versionato (CSV/JSON/Parquet/SQLite), API REST di sola lettura e server MCP online, in modo che app, agenti AI e software di gestione flotte possano consultarli. Ogni dato è aggiornato e verificato: ogni campo riporta fonte, licenza, data di ultima verifica e stato di verifica.

## Contesto

Non esiste un catalogo aperto e affidabile di marchi e modelli con specifiche tecniche per il mercato italiano. Nasce dall'esperienza con un progetto di gestione flotta, che non ne ha una fonte. Pubblico: chiunque (app, agenti, sviluppatori, analisti). Gratuito e open source ora; un livello a pagamento è possibile in futuro ma non è in questa fase.

## Piattaforme scelte

- Frontend: pagine statiche minime (`service/site/`, HTML/CSS/JS senza framework) per la ricerca, il lookup da libretto, la sfoglia del catalogo e la copertura dei dati; l'uso principale resta API, server MCP e dataset
- Backend: Python 3.12+, FastAPI (con uvicorn come server ASGI), Pydantic, SDK MCP ufficiale Python; httpx e pandas per l'import, Playwright solo per siti brand che richiedono JavaScript
- Database: SQLite (master, sola lettura in produzione) + export Parquet/JSON; accesso con il modulo standard `sqlite3`, senza ORM
- Deploy: API e server MCP su Render (un solo servizio), indirizzo `onrender.com` del servizio per API e MCP; dominio proprio `openvehicle.mirkobechini.com` su Cloudflare rimandato; dataset su GitHub Releases; refresh pianificato con GitHub Actions
- Repository: git dedicato (`main` + `dev`, come da AGENT_FLOW.md), separato dal repository padre AI_developed
- Test: pytest + coverage (100% obbligatorio)

## Componenti principali

Struttura del repository: `core/` (modelli Pydantic e storage, condivisi), `pipeline/` (batch offline: importer, validazione, verifica, export; non viene deployata) e `service/` (API FastAPI + server MCP: il microservizio deployato su Render, che legge il dataset prodotto dalla pipeline).

- **Schema/modelli**: Pydantic; marchio → modello → generazione → variante → motore, con ID stabili e alias, categoria e anni di validità.
- **Storage**: unico modulo di accesso al database, per poter passare a Postgres senza toccare le API.
- **Importer**: uno per fonte (EEA CO₂ come catalogo principale; RDW e Traficom come riscontro; Wikidata per gli ID marchio), ognuno con provenienza e licenza; cardata.wiki e i siti dei marchi restano rimandati (vedi Decisioni architetturali).
- **Validazione/qualità**: controlli di range, unità, duplicati e conflitti tra fonti prima della pubblicazione.
- **Verifica**: stato per campo (fonte singola vs confermato da due fonti indipendenti) e `last_verified`.
- **Pipeline di refresh**: re-import pianificato, rilevamento cambiamenti e changelog tra versioni del dataset.
- **Identificativi italiani**: riferimenti al mercato italiano (es. numeri di omologazione) e ricerca per marchio/modello/motore.
- **API REST**: sola lettura, ricerca e filtri, documentazione OpenAPI automatica.
- **Server MCP**: trasporto Streamable HTTP, pubblico e in sola lettura, sugli stessi dati delle API.
- **Export dataset**: file statici versionati con changelog.
- **Pagine web** (`service/site/`): `/` (ricerca e lookup da libretto), `/browse` (sfoglia per marchio) e `/coverage` (copertura dei campi), con una barra di navigazione comune.

## Decisioni architetturali

Versione sintetica. Il dettaglio completo (misure su dati reali, bug trovati, metodo di verifica) è in [DECISIONS-LOG.md](DECISIONS-LOG.md); le fonti dati (licenze, copertura, fonti scartate) sono in [SOURCES.md](SOURCES.md).

- **Prima versione (v0.1) solo con fonti aperte a licenza chiara**: EEA CO₂ come catalogo principale, RDW come riscontro, Wikidata solo per gli ID di marchio (licenze in SOURCES.md). Scraping dei siti dei marchi, cardata.wiki, dataset MIT e contributi utente rimandati a dopo permessi e parere legale. Limiti noti: niente allestimenti; passo/carreggiata solo 2019-2022; nomi come li scrive l'EEA (maiuscolo); auto meno recenti assenti.
- **Importer EEA** (`pipeline/importers/eea.py`): endpoint SQL REST con aggregazione lato server, solo categoria M1; una variante è marchio + modello + tipo/variante/versione di omologazione (D.2); valori misurati presi dalla combinazione più frequente, motori contraddittori risolti per immatricolazioni. Nome del marchio in testa al modello tolto quando resta almeno una parola, le grafie restano alias.
- **Un solo repository, pipeline e servizio separati**: il dataset è il prodotto principale, il servizio è un livello sottile di sola lettura; `core/` condiviso evita duplicazione dei modelli.
- **Prodotto dati con API, non app**: il valore sta nei dati, consumati da più client (dataset + API + MCP).
- **Open source ora, pagamento eventuale poi**: scelto per adozione e fiducia; API predisposta a chiavi/rate limit futuri, non implementati ora.
- **SQLite invece di Postgres**: dataset piccolo e in sola lettura, zero server da gestire; accesso isolato in un modulo per poter cambiare in seguito.
- **ID stabili dalla chiave naturale, persistiti**: formato `prefisso_slug` (`make_id`); un nome corretto diventa un alias, mai un nuovo ID.
- **`sqlite3` standard invece di SQLAlchemy**: schema piccolo, accesso isolato in `core/storage.py` (`Store`); un ORM avrebbe senso solo con Postgres.
- **Export statici come canale primario** (`pipeline/export.py`): gli utenti usano i dati senza dipendere dall'API. Produce DB SQLite, CSV per tabella, `dataset.json`, `manifest.json`, changelog; parte solo se la validazione non trova errori. Parquet rimandato (richiede `pyarrow`, non approvato).
- **API REST** (`service/app.py`): factory `create_app(db)`, solo GET sotto `/api/v1`, paginazione `{total, limit, offset, items}`, filtri combinati per intersezione. Un `Store` di sola lettura per richiesta (SQLite non condiviso tra thread). CORS aperto, nessuna autenticazione, rate limit applicativo.
- **Metadati di paginazione**: ogni lista restituisce `total`, `count`, `has_more`, `next_offset`, per evitare che un client conti male una lista lunga.
- **Filtro per marchio sulle varianti** (`brand_id`): risolto passando da modelli e generazioni, combinato per intersezione con gli altri filtri.
- **Id inesistenti e refusi**: un id inesistente nei filtri è un errore (404/`ToolError`), con suggerimento `Did you mean` se c'è qualcosa di simile; la ricerca ha lo stesso suggerimento quando non trova nulla.
- **Server MCP** (`service/mcp_server.py`): sette tool di sola lettura, schema di output dichiarato, query condivise con l'API REST (`service/queries.py`) così i due canali non divergono. Montato su `/mcp` (Streamable HTTP, stateless); protezione DNS rebinding disattivata di proposito (server pubblico, di sola lettura).
- **Schema di output dei tool MCP verificato come un client**: `status` (campo calcolato) va dichiarato esplicitamente nello schema di provenienza (`ProvenanceOut`), altrimenti un client con validazione rigorosa rifiuta la risposta.
- **Testo esterno nei tool MCP**: nomi/alias anomali (troppo lunghi o con caratteri non stampabili) diventano `[removed]` prima di rispondere, contro la prompt injection via dati esterni.
- **Deploy su Render** (`Dockerfile`, `render.yaml`): un solo servizio Docker per API e MCP; il database è incorporato nell'immagine da una release GitHub con `ADD --checksum`, non scaricato all'avvio. Indirizzo `onrender.com` (il dominio proprio è rimandato, slot Render pieni). Piano free: standby dopo 15 minuti.
- **Conteggio delle immatricolazioni** (`registrations`): non filtra modelli rari, ma dà a ogni voce un peso visibile; ordinamento e soglia minima disponibili su API e MCP.
- **Correzioni riviste a mano** (`pipeline/importers/corrections.json`): file piccolo e in revisione (non una regola automatica) per marchi scritti in modi diversi e modelli mal attribuiti nella fonte; ogni voce ha una ragione obbligatoria. Canale previsto per i contributi supervisionati via pull request.
- **Famiglie di modelli** (`Family`, `pipeline/importers/families.json`): raggruppano modelli che per alcuni marchi sono in realtà lo stesso veicolo con allestimento/motore diverso (BMW, Mercedes-Benz, Audi...). Regole riviste per marchio, mai una regola universale; un marchio senza regole tiene una famiglia per modello (mai auto diverse unite per caso). Esposte su API e MCP (`list_families`, filtro `family_id`).
- **Nomi che differiscono solo per i separatori**: uniti quando lo stesso modello è scritto con spazi/trattini/punti diversi (non il segno `+` né il punto tra cifre, che distinguono auto diverse). Maiuscole non toccate per scelta: una conversione automatica sbaglierebbe nomi come `KA`, `C-HR`, `ID.4`.
- **Numero di omologazione UE sulle varianti** (`Variant.type_approval`): numero base (senza l'estensione), identifica il tipo non la variante. Fonte principale RDW, poi anche EEA (colonna `TAN`), che ha portato la copertura dal 47% al 99,97%.
- **Codici tipo, variante e versione** (`Variant.type_code`/`variant_code`/`version_code`): dalla carta di circolazione (D.2), servono ad agganciare un documento a una variante precisa quando il numero di omologazione non basta.
- **Indici sulle ricerche frequenti**: aggiunti su `variants` e sulle tabelle collegate dopo aver misurato scansioni complete costose (omologazione, ordinamento per immatricolazioni, carburante).
- **Ricerca da carta di circolazione**: `GET /api/v1/variants`/`list_variants` accettano numero di omologazione + i tre codici D.2, in intersezione con gli altri filtri; nessun endpoint o campo dedicato.
- **Cache HTTP**: risposte `GET /api/v1/*` con `Cache-Control` e `ETag` forte derivato da versione dataset/software/percorso/query, per il tier Render che si addormenta e riparte a freddo.
- **Copertura dei campi** (`core/coverage.py`, `GET /api/v1/coverage`): quota di varianti con ogni campo tecnico, totale e per marchio, pesata anche per immatricolazioni; stampata a ogni build per vedere un calo prima della release.
- **Anni osservati per variante** (`Variant.years`): elenco degli anni con immatricolazioni reali, non solo l'intervallo `year_from`/`year_to`, per non far risultare una variante presente in un anno in cui non fu venduta.
- **Filtri delle varianti come oggetto** (`service.queries.VariantQuery`): sostituisce 15 parametri posizionali con un modello Pydantic validato, per eliminare il rischio di scambiare l'ordine di due filtri testuali.
- **`eea._load` in passi**: funzione unica divisa in funzioni più piccole e testabili (nomi, raggruppamento, valori annuali, catalogo); stessa importazione verificata prima/dopo.
- **Limite di richieste e header** (`service.headers.RateLimit`): rate limit applicativo in memoria (120 richieste/60s per client) perché non c'è Cloudflare davanti al servizio; più CSP, Permissions-Policy e HSTS.
- **Posti, massa F.2 e classe Euro** (`Variant.seats`/`max_mass_kg`/`environmental_class`): dal RDW, per compilare un veicolo dalla carta di circolazione; impostati solo dove vuoti, con fonte singola.
- **Importer come stadi con registro** (`pipeline/importers/__init__.py`): `Ctx`, protocollo `Importer`, `stages()` sostituiscono le chiamate dirette a `eea.run`/`rdw.run`/`wikidata.run`; una nuova fonte è una riga in più.
- **Ricerca a più parole e senza accenti**: `q` si divide in parole, ognuna senza accenti e case-insensitive, tutte devono comparire nel nome o negli alias (AND).
- **Versione dello schema** (`core.storage.SCHEMA_VERSION`): scritta nel dataset, controllata all'avvio del servizio; un dataset di un'altra versione non fa partire `create_app` (fail-safe su Render, resta attiva la versione precedente).
- **Dipendenze fissate con hash**: `requirements.lock`/`requirements-dev.lock` generati in CI con `pip-compile --generate-hashes`, immagine base fissata per digest, installazione con `--require-hashes`.
- **Pagina iniziale** (`service/site/`): `/` serve una pagina statica senza framework né build, con ricerca per nome e da carta di circolazione; CSP propria del sito, accessibilità verificata con axe-core (0 violazioni).
- **Scheda dei risultati**: intestazione con sintesi (carburante, cilindrata, potenza), sezioni nascoste se vuote, campo della carta di circolazione accanto a ogni riga, pulsante «Copy codes».
- **Icona del browser**: logo dello sviluppatore come favicon (SVG + PNG di fallback per Safari/iOS).
- **Prototipi di interfaccia diventati pagine reali** (Browse, Coverage): colore principale arancione (coerente con un altro progetto dello sviluppatore); `service/site/common.js` condivide gli helper già scritti per la pagina di ricerca. Contrasto del colore corretto dopo un difetto trovato con axe-core.
- **Aggiornamento mensile dei dati con una sola approvazione** (`refresh.yml`): pubblica una pre-release, sposta il pin del Dockerfile su un branch e apre una PR verso `main`; l'unica azione umana è il merge. Controllo guardia: nessuna tabella può ridursi oltre il 5% senza bloccarsi.
- **Tentativi ripetuti nei download** (`pipeline/http.py`): errori 5xx/429/di trasporto ripetuti fino a 3 volte con attesa crescente, perché un job mensile non deve fallire per un errore passeggero di una fonte esterna.
- **Wikidata: solo gli ID dei marchi**, da un file rivisto a mano (`pipeline/importers/wikidata.json`), non un importer SPARQL automatico: l'abbinamento per nome è troppo ambiguo (marchio vs gruppo, omonimi) e i modelli hanno elementi doppi o sbagliati su Wikidata.
- **Più anni dall'EEA (2019-2025)**: un solo anno lasciava fuori quasi tutto il parco circolante; unione per variante su più anni, un campo tecnico preso dall'anno più recente che lo ha.
- **Seconda fonte: RDW (Paesi Bassi)**: riscontro indipendente per portare i campi tecnici a `confirmed`, con tolleranze per arrotondamento (massa, passo). EEA e RDW condividono la fonte ultima (il certificato di omologazione), quindi l'accordo protegge da errori di trascrizione, non da errori del costruttore.
- **Terza fonte: Traficom (Finlandia)**: stesso ruolo di RDW, copertura indipendente (dettaglio in SOURCES.md).
- **Limite di dimensione sullo scaricamento di Traficom**: controllo esplicito sulla dimensione della risposta prima di passarla a `zipfile`/`csv`, perché il file è uno scarico completo senza paginazione lato server.
- **RDW: potenza**: verificata sul motore (non sulla variante), tramite un blocco di targhe interrogate solo in memoria, mai salvate né loggate. CO2 esclusa dalla verifica per scelta dell'utente: troppo variabile tra auto della stessa variante per essere un controllo affidabile.
- **Refresh pianificato (solo avviso)**: `refresh.yml` apre una issue con il changelog se i dati cambiano, non pubblica mai una release da solo: pubblicare resta una decisione del developer.
- **Modello di provenienza e serializzazione**: `FieldProvenance` ignora lo `status` derivato in ingresso (sempre ricalcolato), perché l'SDK MCP riconvalida l'output contro lo schema dichiarato.
- **Provenienza per campo**: consente di scartare una fonte problematica senza perdere il resto e di dichiarare la licenza di ogni dato.
- **Fonti**: vedi [SOURCES.md](SOURCES.md).
- **Stato di verifica derivato, mai scritto a mano**: `conflict` se le fonti riportano valori diversi, `confirmed` se almeno due fonti distinte concordano, altrimenti `single_source`. Limite noto: l'indipendenza è misurata con `source_id` distinti, quindi una fonte che copia un'altra conterebbe due volte.
- **Validazione: errori bloccanti e warning** (`pipeline/validation.py`): bloccano il build i duplicati, un campo senza provenienza, una fonte sconosciuta o con licenza non verificata, un valore senza prova. Sono solo warning i valori fuori range plausibile e i conflitti tra fonti (già pubblicati nel dato).
- **Playwright solo dove serve**: fallback per siti dinamici, perché pesante e fragile.
- **Licenza dati CC BY 4.0** (alternativa: ODbL): richiede solo attribuzione, compatibile con le fonti in ingresso, massimizza l'adozione anche commerciale.
- **Licenza codice Apache-2.0** (alternativa: MIT): aggiunge concessione esplicita di brevetti e protezione per i contributori. File separati per dati (`LICENSE-DATA`) e codice (`LICENSE`).
- **Sottodominio di primo livello** (`openvehicle.mirkobechini.com`): il certificato gratuito di Cloudflare copre solo `*.mirkobechini.com`, non i sottodomini di secondo livello.
- **Python come stack**: import, API e MCP condividono gli stessi modelli Pydantic in un unico linguaggio; alternativa TypeScript scartata (ecosistema dati meno maturo).
- **Server MCP remoto senza login**: pubblico e di sola lettura; abusi limitati dal rate limit applicativo. Chiavi API rimandate al livello a pagamento.
- **Contributi degli utenti (fase successiva)**: solo tramite pull request sui file dati, con controlli automatici, fonte obbligatoria e revisione del maintainer; "confermato" solo con seconda fonte.

## Vincoli

- Dati aggiornati e verificati (requisito primario).
- Nessuna lib non dichiarata qui senza approvazione.
- Solo dati di cui la licenza consente il riuso; sono vietate le fonti proprietarie (es. vbalagovic/cars-dataset, auto-data.net).
- EEA: CC BY 4.0 con attribuzione all'EEA, confermata a livello di dataset dalla scheda metadati (nessuna limitazione di accesso pubblico) il 2026-09-19, per il dataset 2025 provvisorio. Da ricontrollare per ogni nuova versione o anno importato, e la fonte `eea-co2` va rimarcata come verificata con la nuova data.
- cardata.wiki: dati CC BY 4.0 ma contribuiti dagli utenti e non verificati; i termini dell'API vietano l'export massivo per creare un servizio concorrente. Usare solo i download pubblici e chiedere conferma scritta ai gestori prima dell'import massivo. Mai da sola sufficiente per lo stato "confermato".
- Siti dei marchi: contano i termini d'uso (contratto) anche se i fatti non sono protetti dal diritto d'autore (CGUE, C-30/14 Ryanair), e l'estrazione sostanziale può violare il diritto sui generis sulle banche dati. Controllo ToS/robots.txt per ogni sito, estrazione limitata ai fatti, mai il catalogo intero in blocco.
- Attribuzione: file `NOTICE` con le fonti (EEA, cardata.wiki, ecc.) e campo fonte/licenza su ogni record, per rispettare la CC BY dei dati in ingresso e in uscita.
- Disclaimer e marchi: README e dataset dichiarano che il progetto non è affiliato ai costruttori, che marchi e nomi appartengono ai rispettivi titolari e che i dati sono forniti "as is", senza garanzie, da verificare prima di usi critici per la sicurezza. Nessun logo.
- Privacy: nessun dato personale nel dataset; API e server MCP registrano il minimo (log con IP) e pubblicano una breve informativa privacy (fatta: `PRIVACY.md`, collegata dal README). La cronologia git mostra i nomi dei contributori: va detto nella guida ai contributi.
- Contributi: quando si aprono, richiedono fonte su ogni modifica e Developer Certificate of Origin (DCO, `Signed-off-by`). Un CLA va valutato prima di un eventuale livello a pagamento.
- Regola sulle fonti: un importer non può essere unito a `dev` finché la licenza della sua fonte non è verificata e registrata (con data e link) nel repository.
- Il registro di omologazione trovato su data.europa.eu è del Regno Unito (VCA), senza licenza indicata: escluso. Il dataset MIT "parco circolante" ha licenza non verificata: non usato finché non confermata.
- Tier gratuito di Render: avvio a freddo dopo inattività; accettabile per la demo.
- Convenzioni del repository: AGENTS.md e AGENT_FLOW.md (branch, issue, commit atomici, test, 100% coverage).
- Mercato italiano per primo.

## Cosa NON è in scope

- In v0.1: scraping dei siti dei marchi, import da cardata.wiki e dal dataset MIT, contributi degli utenti (vedi Feature future e Vincoli).
- Veicoli diversi dalle autovetture: solo categoria UE **M1** (passeggeri, fino a 8 posti oltre al conducente). Esclusi furgoni N1 (anche derivati da auto), camion N2/N3, categoria L (moto, scooter, quadricicli, microcar), autobus M2/M3, rimorchi, veicoli agricoli e speciali (incluse conversioni camper). Il campo `category` è previsto nello schema per estensioni future.
- Ricerca per targa o telaio; nessun dato di proprietari o personali.
- Prezzi, quotazioni, annunci.
- Account utente e login.
- Scritture tramite API (sola lettura; modifiche solo via pull request).
- Copia di testi, immagini o documenti dai siti dei marchi.
- Livello a pagamento (chiavi API, rate limit per piano) in questa fase.

## Feature future pianificate

- Contributi degli utenti tramite pull request (flusso supervisionato descritto sopra)
- Campi energia/EV: batteria, autonomia, ricarica
- Dati aggiuntivi: intervalli di manutenzione, misure pneumatici, costi di gestione (TCO)
- Chiavi API, rate limit per piano e livello a pagamento
- Altre categorie di veicoli (furgoni N1, moto categoria L) grazie al campo `category`
- Altri mercati oltre l'Italia (Europa)
- Nomi e descrizioni multilingua
- SDK client (Python, TypeScript)
- Migrazione a Postgres se il carico lo richiede

Da decidere o da fare dopo i dati 0.9.0 (2026-09-20):

- **Rate limit di Render già fatto, resta solo il dominio**: il rate limit applicativo è attivo dal 2026-10-19 (`service.headers.RateLimit`, 120 richieste/minuto per client); resta da decidere solo il livello successivo (dominio dietro Cloudflare, piano `starter` per togliere lo standby). Decisioni dell'utente sul costo; procedura in `DEPLOY.md`.
- **CO₂ con una seconda fonte affidabile**: RDW dà la CO₂ per targa; con una targa per variante concorda esattamente nel 60% dei casi e entro 5 g/km nel 94% (la CO₂ varia tra auto della stessa variante), quindi resta `single_source` per scelta. Servirebbero molte targhe per variante o un'altra fonte.
- **Fonti dati aggiuntive**: valutazione delle fonti usate, scartate e in corso di verifica in [SOURCES.md](SOURCES.md) (aggiornato il 2026-10-20).
- **ID Wikidata**: 12 marchi restano ambigui o senza un elemento sicuro (Seres/DFSK condivisi, smart la cui voce è la società mista, nomi EEA senza elemento come DR, EVO, Olmedo...), ognuno da verificare con una riga in `wikidata.json`. Dei 20 marchi originariamente senza ID, 6 hanno già un ID verificato (Renault, Mini, Smart, Alpine, DR, Seres) e 2 si sono rivelati errori di nome, non lacune Wikidata (Ssangyong → KG Mobility, Jaguar Land Rover Limited → Land Rover, corretti in `corrections.json`): dettaglio in DECISIONS-LOG.md. Da aggiungere ai controlli del refresh: verificare che gli ID non siano stati uniti o rimossi.
- **Regole di famiglia**: con McLaren e Caterham i marchi con regole sono 50. Riesaminati i 42 marchi rimasti senza regole (2026-09-20): gli altri non hanno gruppi di nomi (una famiglia per modello è già giusta) oppure hanno gruppi di modelli diversi (Tesla `MODEL 3`/`Y`/`S`/`X`, Land Rover `RANGE ROVER SPORT`/`EVOQUE`, DFSK `FENGON 5`/`500`/`600`); DR, EVO e Sportequipe restano senza regole perché i loro nomi si sovrappongono (`5.0`, `50`, `DR3.0`, `DR30`, `EVO 5`, `5`, `6`) e non c'è una regola sicura. Nuove regole solo se compaiono nomi nuovi.
- **Nomi da mostrare (2026-10-21)**: `service/site/common.js` ha una tabella `DISPLAY` piccola e rivista a mano (`KA`→`Ka`, `KA+`→`Ka+`) usata solo nelle 3 pagine web, non nei dati/ID/ricerca. Volutamente non un algoritmo: `C-HR`, `ID.4`, `DS 7`, `GT R` sono esempi di nomi che una conversione automatica sbaglierebbe (visti in DECISIONS-LOG.md), quindi resta un elenco di eccezioni da ampliare a mano, non una regola generale.
