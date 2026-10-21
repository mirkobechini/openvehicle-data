# Fonti dati

Elenco delle fonti dati valutate per openvehicle-data: quelle in uso, quelle scartate (con il motivo) e quelle ancora in valutazione. Il dettaglio delle verifiche (licenza, copertura, metodo di aggancio) è nei log citati; qui resta solo la sintesi.

## Fonti usate

| Fonte | Licenza | Ruolo | Come |
|---|---|---|---|
| EEA e DG Climate Action — CO2 emissions from new passenger cars | CC BY 4.0 (verificata 2026-09-19/2026-09-20) | Catalogo principale: marchi, modelli, varianti, motori, massa, CO2, passo, carreggiata | Endpoint SQL REST con aggregazione lato server, solo categoria M1, Italia, anni 2019-2025; una variante è marchio + tipo/variante/versione di omologazione (D.2) |
| RDW Open Data (Paesi Bassi) — Gekentekende voertuigen | Public Domain (verificata 2026-09-20) | Riscontro indipendente: conferma massa/cilindrica/potenza, imposta `type_approval`, `seats`, `max_mass_kg`, `environmental_class` dove vuoti | Righe per targa raggruppate lato server per marchio/tipo/variante/versione; nessuna targa lascia il server RDW né entra nel database |
| Traficom — Ajoneuvojen avoin data (registro veicoli finlandese) | CC BY 4.0 (verificata 2026-10-20) | Seconda fonte di riscontro indipendente: conferma massa/cilindrata/potenza, imposta `seats` e `max_mass_kg` dove vuoti | Scarico completo (zip, filtro M1 lato client, nessuna aggregazione server); aggancio per marchio + numero di omologazione base + codici variante/versione |
| Wikidata | CC0 (verificata 2026-09-20) | Solo ID di marchio (`Brand.wikidata_id`) | File rivisto a mano (`pipeline/importers/wikidata.json`), nessuna query SPARQL in produzione (vedi `DECISIONS-LOG.md` per il perché) |

## Fonti scartate

| Fonte | Motivo | Data |
|---|---|---|
| Italia — MCTC / ACI-PRA | Nessun registro open per-variante; solo statistiche aggregate (ACI «Autoritratto», ISTAT). Possibile solo come controllo di plausibilità sui totali, non come importer | 2026-10-20 |
| Danimarca — Motorregister / Datafordeler | Nessun registro open; accesso commerciale/autenticato dopo le riforme privacy | 2026-10-20 |
| Svezia — Transportstyrelsen | Nessun registro open; accesso commerciale/autenticato dopo le riforme privacy | 2026-10-20 |
| Repubblica Ceca | Nessun registro open per-veicolo trovato | 2026-10-20 |
| Belgio — DIV | Consultazione targhe solo via EUCARIS (riservato alle autorità); Statbel pubblica solo il sottoinsieme di veicoli coinvolti in incidenti, non il parco completo | 2026-10-20 |
| Germania — KBA | Dati granulari del registro centrale accessibili solo a scopo di ricerca, in sede o per esecuzione remota controllata (Forschungsdatenzentrum); non un download pubblico aperto | 2026-10-20 |
| Norvegia — Statens vegvesen | Scartata **per ora, non per sempre**: l'API di lookup vivo richiede un'identità elettronica norvegese (BankID/Buypass/Commfides) o accesso Altinn per le aziende, non raggiungibile da un progetto non norvegese. Esisteva un dataset bulk aperto equivalente (CC BY 4.0, CSV settimanale, «Teknisk kjøretøyinformasjon»), ma l'hosting (hotell.difi.no) è stato chiuso; Vegvesen dice di lavorare a un servizio proprio, senza data. Da riverificare se e quando torna disponibile | 2026-10-20 |
| Wikidata, oltre gli ID di marchio | Qualità e verificabilità troppo basse per specifiche tecniche fini (massa, potenza): in contrasto con «qualità prima di quantità». Resta in uso solo per gli ID di marchio | 2026-10-20 |

## In valutazione

- **Svizzera — ASTRA (`opendata.astra.admin.ch/ivzod`, dataset `TG-Automobil.txt`)**: candidata buona, **rimandata per scelta di Mirko (2026-10-21)**, non per un problema trovato. Dati di omologazione dal 1995 (massa, potenza, cilindrata, posti, numero di omologazione), formato testo tabellare, nessuna registrazione richiesta, pubblicati come «Open Government Data» (anonimizzati, senza dati del titolare). Resta da confermare la licenza di riuso (non c'è un testo di licenza specifico per questo dataset, non è nel catalogo opendata.swiss, e il pattern più comune dei dataset federali svizzeri vieta l'uso commerciale senza permesso del titolare) e da controllare il campo categoria per isolare M1 — ma la verifica stessa è rimandata a quando il servizio avrà utenti attivi, per non investire tempo su una fonte incerta prima che serva davvero. Da riprendere allora, scrivendo a `fahrzeugdaten.analyse@astra.admin.ch`.
