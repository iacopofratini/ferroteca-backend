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
