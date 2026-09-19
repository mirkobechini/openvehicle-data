# Architecture Decision Record

**Progetto:** openvehicle-data
**Data:** 2026-09-18
**Autore:** Mirko Bechini

## Decisione

Database open source di marchi, modelli, varianti e specifiche tecniche di autovetture, a partire dal mercato italiano. Dati esposti tramite dataset versionato (CSV/JSON/Parquet/SQLite), API REST di sola lettura e server MCP online, in modo che app, agenti AI e software di gestione flotte possano consultarli. Ogni dato è aggiornato e verificato: ogni campo riporta fonte, licenza, data di ultima verifica e stato di verifica.

## Contesto

Non esiste un catalogo aperto e affidabile di marchi e modelli con specifiche tecniche per il mercato italiano. Nasce dall'esperienza con un progetto di gestione flotta, che non ne ha una fonte. Pubblico: chiunque (app, agenti, sviluppatori, analisti). Gratuito e open source ora; un livello a pagamento è possibile in futuro ma non è in questa fase.

## Piattaforme scelte

- Frontend: nessuno (solo API, server MCP e dataset)
- Backend: Python 3.12+, FastAPI, Pydantic, SDK MCP ufficiale Python; httpx e pandas per l'import, Playwright solo per siti brand che richiedono JavaScript
- Database: SQLite (master, sola lettura in produzione) + export Parquet/JSON; accesso con il modulo standard `sqlite3`, senza ORM
- Deploy: API e server MCP su Render (un solo servizio), sottodomini Cloudflare `openvehicle-api.mirkobechini.com` e `openvehicle-mcp.mirkobechini.com` (nomi provvisori); dataset su GitHub Releases; refresh pianificato con GitHub Actions
- Repository: git dedicato (`main` + `dev`, come da AGENT_FLOW.md), separato dal repository padre AI_developed
- Test: pytest + coverage (100% obbligatorio)

## Componenti principali

Struttura del repository: `core/` (modelli Pydantic e storage, condivisi), `pipeline/` (batch offline: importer, validazione, verifica, export; non viene deployata) e `service/` (API FastAPI + server MCP: il microservizio deployato su Render, che legge il dataset prodotto dalla pipeline).

- **Schema/modelli**: Pydantic; marchio → modello → generazione → variante → motore, con ID stabili e alias, categoria e anni di validità.
- **Storage**: unico modulo di accesso al database, per poter passare a Postgres senza toccare le API.
- **Importer**: uno per fonte (EEA CO₂, Wikidata, cardata.wiki, siti dei marchi), ognuno con provenienza e licenza.
- **Validazione/qualità**: controlli di range, unità, duplicati e conflitti tra fonti prima della pubblicazione.
- **Verifica**: stato per campo (fonte singola vs confermato da due fonti indipendenti) e `last_verified`.
- **Pipeline di refresh**: re-import pianificato, rilevamento cambiamenti e changelog tra versioni del dataset.
- **Identificativi italiani**: riferimenti al mercato italiano (es. numeri di omologazione) e ricerca per marchio/modello/motore.
- **API REST**: sola lettura, ricerca e filtri, documentazione OpenAPI automatica.
- **Server MCP**: trasporto Streamable HTTP, pubblico e in sola lettura, sugli stessi dati delle API.
- **Export dataset**: file statici versionati con changelog.

## Decisioni architetturali

- **Prima versione (v0.1) solo con fonti aperte a licenza chiara**: Wikidata (CC0), EEA CO₂ (CC BY 4.0, conferma a livello di dataset in sospeso) e RDW (CC0, riscontro). Rimandati a versioni successive, dopo permessi e parere legale: scraping dei siti dei marchi, cardata.wiki, dataset MIT e contributi degli utenti. Limiti noti di v0.1: niente allestimenti/equipaggiamenti, dimensioni limitate a passo e carreggiata, auto meno recenti assenti.
- **Un solo repository, con pipeline e servizio separati**: il prodotto principale è il dataset, il servizio è un livello sottile di sola lettura; `core/` condiviso evita duplicazione dei modelli. Alternativa scartata: cartella `microservizi/`, riservata a servizi a scopo singolo.
- **Prodotto dati con API, non app**: alternativa app dedicata → scelta dataset + API + MCP, perché il valore sta nei dati e va consumato da più client.
- **Open source ora, pagamento eventuale poi**: alternativa a pagamento subito → scelta gratuito, per adozione e fiducia. Dataset con licenza aperta; API predisposta a chiavi e rate limit in futuro, senza implementarli ora.
- **SQLite invece di Postgres**: dataset piccolo e in sola lettura, zero server da gestire, clonabile dai contributori. Accesso al database isolato in un modulo per poter cambiare in seguito.
- **ID stabili: generati una volta dalla chiave naturale, poi persistiti**: formato `prefisso_slug` (`brand_fiat`, `model_fiat-500`, `gen_...`, `eng_...`, `var_...`) prodotto da `make_id`. Dopo la pubblicazione un ID non si ricalcola mai: un nome corretto o rinominato diventa un alias, non un nuovo ID. Alternativa scartata: hash del nome, illeggibile e comunque instabile se il nome cambia.
- **`sqlite3` standard invece di SQLAlchemy**: schema piccolo, nessuna dipendenza in più, e l'accesso è comunque isolato in `core/storage.py` (`Store`, con `put`/`get`/`find` generici sui modelli Pydantic e apertura `ro=True` per il servizio). Un ORM avrebbe senso solo passando a Postgres, quando la migrazione dello storage andrà rivalutata. Le chiavi esterne sono attive, quindi una variante senza generazione o motore viene rifiutata.
- **Export statici come canale primario**: gli utenti possono usare i dati senza dipendere dall'API.
- **Provenienza per campo**: consente di scartare una fonte problematica senza perdere il resto e di dichiarare la licenza di ogni dato.
- **Fonti**: Wikidata (scheletro e ID, CC0), EEA CO₂ (dati misurati, filtrati per l'Italia, CC BY 4.0), RDW Paesi Bassi (dati di omologazione, CC0, opzionale come riscontro), cardata.wiki (CC BY 4.0, con attribuzione, solo candidato da verificare), siti dei marchi (solo fatti: nomi di modelli, generazioni, motorizzazioni; niente testi, immagini o documenti). Prima di ogni scraping si controllano ToS e robots.txt del sito.
- **Stato di verifica derivato, mai scritto a mano**: per ogni campo lo stato si calcola dalle prove raccolte. `conflict` se le fonti riportano valori diversi; `confirmed` se almeno due fonti distinte concordano; altrimenti `single_source`. Lo stato `conflict` estende i due stati inizialmente previsti, perché il merge deve segnalare i disaccordi. Limite noto: l'indipendenza è misurata con `source_id` distinti, quindi una fonte che copia un'altra conterebbe due volte; da modellare prima di aggiungere fonti derivate (es. cardata.wiki). Una fonte è utilizzabile solo se `license_checked` è valorizzato (regola sugli importer).
- **Validazione: errori bloccanti e warning** (`pipeline/validation.py`): sono errori che fermano il build i duplicati di marchio/modello/variante (nome o alias uguali dopo normalizzazione), un campo di specifica senza provenienza, una fonte sconosciuta o con licenza non verificata e un valore salvato che nessuna prova supporta. Sono solo warning i valori fuori dall'intervallo plausibile, una cilindrata che sembra in litri, gli anni di una variante fuori dalla generazione e i conflitti tra fonti. I conflitti non bloccano perché lo stato `conflict` è già pubblicato nel dato e fermare il build a ogni disaccordo tra fonti lo renderebbe inutilizzabile. Le soglie di plausibilità sono un punto di partenza da tarare con i dati reali.
- **Playwright solo dove serve**: fallback per siti dinamici, perché pesante e fragile.
- **Licenza dati CC BY 4.0** (alternativa: ODbL): la CC BY richiede solo l'attribuzione, quindi è compatibile con le fonti in ingresso (cardata.wiki è CC BY 4.0, Wikidata è CC0), massimizza l'adozione anche da parte di aziende e non ostacola un futuro livello a pagamento. L'ODbL impone la condivisione delle modifiche allo stesso modo (share-alike): proteggerebbe da chi rivende il dataset senza contribuire, ma scoraggia l'uso commerciale e complica le fonti miste. Da riconfermare dopo la verifica della licenza EEA.
- **Licenza codice Apache-2.0** (alternativa: MIT): come MIT è permissiva, ma aggiunge una concessione esplicita di brevetti e la protezione per i contributori, utile per un progetto aperto ai contributi e con un possibile uso commerciale futuro. File separati per dati (`LICENSE-DATA`) e codice (`LICENSE`).
- **Sottodomini di primo livello** (`openvehicle-api.mirkobechini.com`): il certificato gratuito di Cloudflare copre solo `*.mirkobechini.com`, non i sottodomini di secondo livello (es. `mcp.api.mirkobechini.com`).
- **Python come stack**: import e pulizia dati, API e MCP condividono gli stessi modelli Pydantic in un unico linguaggio; alternativa TypeScript scartata perché l'ecosistema di elaborazione dati (pandas, Parquet) è più maturo in Python.
- **Server MCP remoto senza login**: pubblico e di sola lettura; abusi gestiti con rate limit Cloudflare. Chiavi API rimandate al livello a pagamento.
- **Contributi degli utenti (fase successiva)**: solo tramite pull request sui file dati, con controlli automatici, fonte obbligatoria e revisione del maintainer; "confermato" solo con seconda fonte. Non in v1, ma i campi di provenienza lo prevedono già.

## Vincoli

- Dati aggiornati e verificati (requisito primario).
- Nessuna lib non dichiarata qui senza approvazione.
- Solo dati di cui la licenza consente il riuso; sono vietate le fonti proprietarie (es. vbalagovic/cars-dataset, auto-data.net).
- EEA: licenza generale CC BY 4.0 (con attribuzione all'EEA), ma la pagina del dataset CO₂ non indica termini propri: leggere la scheda metadati o scrivere all'EEA prima della prima pubblicazione.
- cardata.wiki: dati CC BY 4.0 ma contribuiti dagli utenti e non verificati; i termini dell'API vietano l'export massivo per creare un servizio concorrente. Usare solo i download pubblici e chiedere conferma scritta ai gestori prima dell'import massivo. Mai da sola sufficiente per lo stato "confermato".
- Siti dei marchi: contano i termini d'uso (contratto) anche se i fatti non sono protetti dal diritto d'autore (CGUE, C-30/14 Ryanair), e l'estrazione sostanziale può violare il diritto sui generis sulle banche dati. Controllo ToS/robots.txt per ogni sito, estrazione limitata ai fatti, mai il catalogo intero in blocco.
- Attribuzione: file `NOTICE` con le fonti (EEA, cardata.wiki, ecc.) e campo fonte/licenza su ogni record, per rispettare la CC BY dei dati in ingresso e in uscita.
- Disclaimer e marchi: README e dataset dichiarano che il progetto non è affiliato ai costruttori, che marchi e nomi appartengono ai rispettivi titolari e che i dati sono forniti "as is", senza garanzie, da verificare prima di usi critici per la sicurezza. Nessun logo.
- Privacy: nessun dato personale nel dataset; API e server MCP registrano il minimo (log con IP) e pubblicano una breve informativa privacy. La cronologia git mostra i nomi dei contributori: va detto nella guida ai contributi.
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
- Interfaccia web per esplorare il catalogo
