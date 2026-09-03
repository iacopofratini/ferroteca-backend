# Ferroteca — Decision Log

Log delle decisioni prese sessione per sessione, aggiornato nel momento in cui
vengono prese (non a fine sessione). Formato: cosa deciso, perché, fatto,
prossimo passo. Per il log strutturato in stile ADR (alternative scartate) vedi
`docs/DECISIONS.md` una volta creato (punto 7 del piano di consolidamento).

---

## 2026-09-01 — Avvio consolidamento pre-presentazione aziendale

**Deciso:** lavorare su branch dedicato `chore/llm-provider-consolidation`,
mai direttamente su `main`; nessun push al remote senza conferma esplicita.
**Perché:** vincolo esplicito del progetto — main deve restare uno stato noto
e stabile finché Iacopo non approva un diff.
**Fatto:** branch creato da `main`.
**Prossimo passo:** aprire un confronto/PR locale (diff) prima di ogni push.

**Deciso:** committare come primo commit sul branch lo stato già presente in
cartella ma mai salvato in git (aggiornamento SDK Gemini in app.py/rag.py/
requirements.txt, fix minori in routers/documents.py, gli script
sync_documents.py e reindex_ieac_accm.py, cartella docs/), senza modificarlo.
**Perché:** quei file sono necessari al funzionamento dell'app o al lavoro
richiesto (non erano "scarto" come inizialmente sembrava a Iacopo); tenerli
in un commit separato dal lavoro nuovo mantiene la cronologia leggibile.
**Fatto:** commit `c5e3ea0`. Aggiunto anche `venv/` e `.DS_Store` a
`.gitignore` (erano tracciati/non ignorati per svista).
**Prossimo passo:** costruire `services/llm_provider.py` sopra questa base.

**Deciso:** verificare l'esistenza di righe con embedding dal modello
sbagliato su Supabase con una query di sola lettura via REST (curl +
credenziali già in `.env`), non con lo script Python (venv rotto, vedi sotto).
**Perché:** Iacopo ha approvato esplicitamente questa modalità; è read-only,
nessun costo Gemini, nessuna scrittura.
**Fatto:** confermato che `sync_documents.py` è stato eseguito in passato
(`sync_registry`: 339 righe, 294 file distinti). Dei 14 file oggi indicizzati
in `documents` (10.605 chunk totali), tutti e 14 risultano essere stati
toccati dallo script col modello sbagliato in qualche momento. La tabella
`documents` non ha più le colonne (`source_path`, `category`, `file_hash`)
che servirebbero per capire riga per riga quali chunk sono "sporchi" — quindi
`sync_documents.py`, se rilanciato oggi così com'è, fallirebbe con un errore
Postgres (colonna inesistente) invece di corrompere altro silenziosamente.
**Prossimo passo:** una volta pronto `llm_provider`, ri-indicizzare da zero
i 14 volumi oggi presenti con la pipeline corretta (più economico e più
sicuro che tentare di isolare le righe contaminate).

**Deciso:** creare `services/llm_provider.py` come unico punto che parla con
l'SDK Gemini, con un'interfaccia astratta (`LLMProvider`, con `embed()` e
`generate()`) implementata oggi da `GeminiProvider`. `rag.py`,
`sync_documents.py` e `reindex_ieac_accm.py` passano tutti da lì.
**Perché:** era il compito esplicito del punto 1 dell'audit — risolve insieme
il bug (modello di embedding diverso in `sync_documents.py`) e il problema
architetturale (tre punti diversi che parlavano con l'SDK ognuno a modo suo).
L'interfaccia astratta, non solo una funzione condivisa, rende più semplice
cambiare provider in futuro (oggi Gemini è provvisorio, vedi vincoli di
progetto) senza toccare `rag.py` o gli script di indicizzazione.
**Fatto:** modulo creato; i tre file aggiornati per usarlo. Il retry sui
limiti di frequenza (HTTP 429) di Gemini, prima duplicato/assente nei vari
file, ora vive centralizzato dentro `GeminiProvider.embed()`.
**Prossimo passo:** aggiungere test/verifica con chiamata reale (comporta un
piccolo costo Gemini, da fare con l'ok di Iacopo) prima di considerare il
punto 1 completamente chiuso. Restano aperti: pinnare `requirements.txt`
(punto 6) e decidere cosa fare della colonna mancanti `source_path` in
`sync_documents.py` (vedi nota sotto).

**Aperto — schema `sync_documents.py` disallineato:** lo script scrive/legge
`source_path`, `category`, `file_hash` (tabella `documents`) che non esistono
più nello schema reale. Da decidere con Iacopo: (a) aggiungere quelle colonne
a Supabase per riportare lo script allo schema previsto, o (b) semplificare
lo script per usare solo le colonne che esistono oggi (`filename`, `volume`,
`page`, `content`, `embedding`), perdendo il tracciamento fine per cartella/
categoria. Non ancora deciso — lo script resta non eseguibile fino ad allora
(coerente col vincolo "non eseguire sync_documents.py").

**Deciso:** svuotare la tabella `documents` su Supabase e ripopolarla da
zero con la pipeline corretta, invece di cercare di isolare le righe con
embedding dal modello sbagliato. Prima i 14 file già indicizzati (fatto ora),
poi — solo dopo una revisione manuale di Iacopo della cartella locale
`data/pdfs/` per escludere materiale obsoleto — un caricamento pulito completo.
**Perché:** con solo 14 file coinvolti, ripartire da zero è più semplice ed
economico che tracciare riga per riga quali chunk sono "sporchi" (la tabella
non ha più le colonne che servirebbero per distinguerli). Approvato da
Iacopo il 2026-09-01.
**Fatto:** cancellate tutte le 10.605 righe di `documents` via REST Supabase
(DELETE filtrato su `id=not.is.null`, sola tabella `documents`, non toccata
`sync_registry` né alcun file locale). Verificato conteggio 0 righe dopo la
cancellazione.
**Prossimo passo:** Iacopo revisiona `data/pdfs/` a mano; poi si ricarica
tutto con `index_all_pdfs()` (endpoint `/api/documents/reindex` o script),
che ora usa `llm_provider` col modello corretto. Nel frattempo la chat
risponderà "non ho trovato informazioni" a ogni domanda — comportamento
temporaneo atteso, non un errore.

**Deciso:** riorganizzata la cartella di lavoro `ferroteca-app-code/`:
contenuto non sensibile di `File utili:backup/` e `File Backup funzionanti/`
spostato in `_archivio-personale/`; rimossi `services/data/pdfs` (vuota),
`venv/` (rotto), `__pycache__`, `.DS_Store` sparsi. Creato un `CLAUDE.md`
tampone al primo livello di `ferroteca-app-code/` (il progetto ha ancora due
repo separati, non un monorepo — vedi punto 2 del piano, deciso a parte).
**Perché:** pulizia visiva richiesta da Iacopo, senza toccare nulla che il
codice usi davvero (verificato: nessun riferimento nel codice a quelle
cartelle, mai state sotto git).
**Fatto:** anche `keys.rtf` ed `env` — i due file con probabili credenziali
— spostati (solo `mv`, mai letti) dentro `_archivio-personale/`, con
autorizzazione esplicita di Iacopo che sapeva cosa contenevano. Le due
cartelle originali, rimaste vuote, sono state eliminate. Restano da ruotare/
gestire manualmente da Iacopo (non è cambiato: solo la posizione, non lo
stato "da gestire").
**Prossimo passo:** nessuno per questo intervento; i due file restano in
attesa di rotazione/eliminazione da parte di Iacopo.

## 2026-09-01 (continua) — Lavoro autonomo in attesa della revisione di data/pdfs

Iacopo ha rimandato a domani la revisione manuale di `data/pdfs/`; nel
frattempo ho proseguito solo su cose che non richiedevano una sua decisione.

**Deciso:** pinnare in `requirements.txt` le dipendenze non ancora fissate
(`google-genai`, `langchain-google-genai`, `supabase`, `httpx`), risolvendo
le versioni in un ambiente pulito.
**Perché:** punto 6 dell'audit — versioni con `>=` possono rompere il
backend in produzione con un aggiornamento a monte senza che nessuno abbia
cambiato una riga di codice.
**Fatto:** versioni risolte due volte per conferma (Python 3.14 e 3.12,
stesso risultato): `google-genai==2.21.0`, `langchain-google-genai==2.1.5`,
`supabase==2.31.0`, `httpx==0.28.1`.
**Da sapere:** risolte con Python 3.12/3.14 in locale, non 3.11 come il
`Dockerfile` di produzione (Python 3.11 non disponibile su questa macchina).
Alta probabilità che siano identiche (nessun marker di versione Python nei
requisiti di questi pacchetti), ma da confermare al prossimo deploy reale,
non garantito al 100%.

**Deciso:** scrivere `docs/DECISIONS.md` (log ADR) e `docs/BLUEPRINT.md`
(architettura + schema reale + incognite per l'adozione aziendale) — punto
7 del piano.
**Perché:** erano tra i pochi compiti del piano eseguibili senza bisogno di
input di Iacopo in tempo reale; sono per lo più la messa per iscritto di
decisioni già prese in questa sessione o nei vincoli di partenza.
**Fatto:** entrambi i file creati. Segnato esplicitamente cosa è "deciso e
fatto" vs "proposto, non ancora eseguito" (es. monorepo, autenticazione),
per non presentare come completo qualcosa che non lo è. Schema del database
in BLUEPRINT.md verificato via query diretta a Supabase (solo due tabelle
esistono oggi: `documents`, `sync_registry` — confermato l'elenco completo,
non solo quelle già note).

**Verificato (non un'azione, solo un controllo):** il frontmatter Hugging
Face Space in `README.md` (`sdk: docker`, `app_port: 7860`) è ancora
presente; nessun remote git verso Hugging Face configurato (solo GitHub →
Render). Non posso stabilire da qui se esista uno Space HF davvero attivo
sul tuo account — te lo chiedo prima di toccare il file, come richiesto
dall'audit.

**Nota — venv rotto:** `ferroteca-backend/venv/bin/python3` è un symlink
rotto che punta a `/Users/iacopofratini/venv/bin/python3` (percorso fuori
dal progetto, non più esistente). L'ambiente virtuale locale non è
utilizzabile così com'è; da ricreare quando serve eseguire script Python in
locale (non necessario per il lavoro di oggi, fatto via REST/curl).

## 2026-09-02 — Merge del branch di consolidamento in `main` e push

**Deciso:** fondere `chore/llm-provider-consolidation` in `main` e pubblicare
su GitHub (fine del lavoro isolato su branch, `main` torna a essere la base
attiva su cui lavorare).
**Perché:** Iacopo ha confermato esplicitamente dopo aver visto il diff e un
controllo di rischio (variabili d'ambiente invariate, `python-dotenv`
presente come dipendenza transitiva, nessuna funzione mancante, Python 3.11
di produzione compatibile con le versioni pinnate).

**Trovato durante il push (non previsto):** `origin/main` su GitHub conteneva
35 commit mai scaricati in locale (`914b85d..3bba5e9`), fatti direttamente
dall'editor web di GitHub tra il 10 e il 20 maggio 2026 — pattern
riconoscibile (un file alla volta, messaggio automatico "Update X.py").
Il riferimento locale a `origin/main` era rimasto fermo a `914b85d` perché
non era mai stato rifatto un `fetch` da allora. Push iniziale respinto da
Git stesso (nessun danno: nessuna sovrascrittura avvenuta).
**Verificato prima di risolvere:** confronto riga per riga tra la versione
di maggio di `services/rag.py`/`requirements.txt` e quella di settembre —
identiche nella logica (stessa migrazione a `google-genai`, stesse funzioni
`list_indexed_volumes`/`debug_index_status` byte-per-byte), l'unica
differenza è che settembre estrae il codice Gemini in
`services/llm_provider.py`; i pin esatti di settembre rientrano tutti negli
intervalli larghi (`>=`) scelti a maggio. Non erano due soluzioni in
competizione ma la stessa correzione fatta due volte per due strade diverse.
**Fatto:** merge di `origin/main` risolto tenendo la versione di settembre
per i due file in conflitto (nessuna perdita di modifiche, verificato con
diff a zero righe residue dopo la risoluzione); pubblicato su GitHub
(`main` ora a `e4c37cf`). Render dovrebbe ripartire in automatico.
**Chiarito (2026-09-02, poco dopo):** i 35 commit di maggio via editor web
erano di Iacopo stesso, su richiesta di una sessione Claude precedente che
lo guidava a modificare righe direttamente su GitHub durante lo sviluppo —
non un'anomalia. Resta comunque vero che quel modo di lavorare crea rami di
modifiche scollegati dai `fetch` locali; da tenere a mente se ricapita.
**Prossimo passo:** confermare che Render ha effettivamente ridistribuito
`e4c37cf` e che l'app risponde; poi procedere col ricaricamento pulito di
`data/pdfs/` (già riorganizzata da Iacopo in testi principali + sottocartelle
di arricchimento `DE`/`DGI`/`IMPATTI`/`NOTE`/`PE`/`RFI-FILE NORMATIVI MISTI` —
vedi nota separata: la distinzione tra i due livelli è già un campo
`category` in `sync_documents.py`, ma nessun codice usa ancora quel campo per
trattare l'arricchimento come integrazione al testo principale invece che
come fonte a sé stante — da progettare).

**Confermato (2026-09-03):** Render ha ridistribuito, app funzionante
(libreria vuota come atteso, tabella `documents` svuotata il 2026-09-01).

## 2026-09-03 — Mappatura arricchimento → testi principali

**Deciso:** quando l'app risponde a una domanda su un testo principale che
ha arricchimenti collegati (Note/DE/PE/DGI che lo modificano o integrano),
deve recuperare anche le informazioni di quei file, non solo il testo
principale.
**Perché:** richiesta esplicita di Iacopo — l'arricchimento esiste apposta
per correggere/aggiornare il testo principale; ignorarlo darebbe risposte
corrette solo alla data del testo principale, non allo stato normativo reale.

**Deciso:** capire quale file di arricchimento si collega a quale testo
principale con uno script + Gemini 2.5 Flash (non con `llm_provider.py`:
è un lavoro una tantum e usa a mano l'SDK Gemini via script separato, non il
motore live dell'app — non crea nessun legame in più con Gemini rispetto a
quello già deciso come provvisorio, vedi `docs/DECISIONS.md`).
**Perché:** i 30 file "impatto" nella cartella `IMPATTI` sono indici
ufficiali RFI che dicono "le modifiche a questo volume sono nel documento X"
ma non contengono la modifica stessa (osservazione di Iacopo, che conosce il
dominio); più affidabile leggerli e seguire i riferimenti che indovinare dal
contenuto sparso dei restanti file. Costo trascurabile (budget approvato:
sotto 5$).
**Fatto:** letti i 30 "impatti" (10 citazioni/file in media, 98 file
locali trovati tra quelli citati); sui 131 file rimasti non citati da
nessun impatto, classificazione diretta del contenuto con Gemini (125
collegati, 6 senza collegamento chiaro). Risultato: 253 file di
arricchimento su 259 (97%) hanno oggi un collegamento candidato a un testo
principale. Dati completi in `docs/enrichment_mapping.json`, riepilogo
leggibile in `docs/enrichment_mapping.md`. Spesa reale stimata sotto i 2$
(inclusi tentativi falliti per un bug del "thinking" nascosto di Gemini 2.5
Flash che troncava le risposte — risolto disattivandolo con
`thinking_config=ThinkingConfig(thinking_budget=0)`).
**Da sapere:** i collegamenti trovati leggendo il contenuto sono suggeriti
da un modello leggero, non verificati uno per uno da una persona — una
volta ha restituito un codice testo inesistente ("DET"). Da trattare come
buona base, non verità assoluta, finché non c'è un controllo a campione.
Trovati anche 52 documenti citati come contenenti modifiche ma assenti in
locale (vedi `docs/AUDIT.md` punto 3.7) — lacuna aziendale reale, non
di questo lavoro.
**Prossimo passo:** progettare come `services/rag.py` (funzione `ask()`) e
lo schema Supabase useranno `enrichment_mapping.json` per includere
l'arricchimento nella risposta — non ancora implementato, da discutere con
Iacopo prima di toccare il motore live.

**Confermato (2026-09-03, stesso giorno):** Iacopo conferma che i 46/52
documenti mancanti sono un buco aziendale reale (cartella locale = copia
integrale di quella condivisa), non un problema di questo lavoro — restano
segnalati in AUDIT.md 3.7, nessuna azione da parte mia. Confermato anche
l'uso di API esterne economiche per lavori massivi come pratica generale,
non solo per Ferroteca — annotata in `~/claude-config/WORKING_PRACTICES.md`.

**Deciso:** implementare in `services/rag.py` il recupero dell'arricchimento
durante `ask()`, usando solo i 98 collegamenti "certi" (da citazione), non
i 125 "suggeriti dal contenuto" (restano in sospeso finché non c'è un
controllo a campione).
**Fatto:** aggiunte `load_enrichment_map()`, `enrichment_file_paths()`,
`index_enrichment_files()`, `fetch_document_chunks()`; `ask()` ora, per ogni
testo principale trovato tra i risultati, recupera anche gli arricchimenti
collegati e li passa a Gemini in una sezione separata "AGGIORNAMENTI
CORRELATI"; `list_indexed_volumes()` filtra l'arricchimento per non farlo
comparire come libro a sé nella libreria dell'app.
**Bug trovati e corretti prima di eseguire:**
1. Una f-string con una barra rovesciata dentro le graffe — sintassi valida
   solo da Python 3.12, ma Render usa 3.11: avrebbe mandato in crash l'app
   al primo avvio. Trovato rileggendo il codice, non in produzione.
2. Verificato (con un inserimento di prova poi cancellato) che la RPC
   `match_documents` restituisce davvero la colonna `filename` — l'ipotesi
   su cui si basa tutto il meccanismo di collegamento.

**Fatto — indicizzazione reale eseguita (2026-09-03):** 29 testi principali
+ 98 arricchimenti indicizzati su Supabase in produzione (tabella
`documents` svuotata il 2026-09-01, ora ripopolata). Costo reale contenuto
(budget approvato: speso in API). Durante l'esecuzione, un file conteneva un
carattere nullo (NUL, \x00) nel testo estratto, rifiutato da Postgres — corretto
ripulendo il testo prima dell'inserimento (`index_pdf`), poi rieseguito da
capo (idempotente: cancella e reinserisce per filename, nessun duplicato).
**Trovati due problemi reali durante la verifica finale:**
1. **2 testi principali e 63 arricchimenti "certi" producono 0 pezzi di
   testo** — sono scansioni immagine senza livello di testo sotto,
   invisibili alla ricerca finché non c'è OCR (non implementato, vedi
   AUDIT.md 3.8). La mappatura dei collegamenti resta corretta, ma il
   contenuto reale recuperabile è molto meno del previsto.
2. **Bug preesistente (non introdotto oggi) trovato durante il test**:
   `list_indexed_volumes()`/`debug_index_status()` leggevano la tabella
   senza paginazione — Supabase tronca silenziosamente a 1000 righe per
   richiesta. Con sole centinaia di righe (prima di oggi) il bug era
   invisibile; con 26.920 righe reali la libreria mostrava 9 volumi invece
   di 27. Corretto con lettura paginata (`fetch_all_rows`), verificato:
   ora 27/27 volumi visibili, 26.920 pezzi totali confermati.
**Verificato funzionante:** una domanda di prova reale (`ask()`) ha
prodotto una risposta corretta con fonti multiple e formattazione attesa.
**Prossimo passo:** commit e push del codice; poi, se Iacopo conferma,
valutare separatamente un passaggio OCR per i documenti scansionati (costo
e portata da stimare a parte, non incluso in questo lavoro).

**Idea rimandata (2026-09-03):** dalla risposta, poter cliccare sul numero
di pagina citato e aprire il PDF originale proprio a quella pagina (i
browser supportano `#page=N` su un link diretto al PDF). Tecnicamente
semplice, ma **bloccata da un problema già noto** (AUDIT.md 3.6): i PDF
veri non esistono sul server Render in produzione, solo il testo estratto
in Supabase — la cartella `data/pdfs/` riparte vuota a ogni deploy. Serve
prima decidere dove vivono i PDF in produzione (candidato: Supabase
Storage, costo piccolo ma reale, da verificare). Iacopo conferma: priorità
bassa, dopo aver sistemato le fondamenta di oggi — non implementare ora.
