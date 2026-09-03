# Ferroteca — Audit tecnico e architetturale
*Data: 1 settembre 2026*

## 1. Cos'è, oggi

Ferroteca è un assistente RAG per procedure ferroviarie italiane:

- **Backend**: FastAPI (Python), deployato su Render (`https://ferroteca-backend.onrender.com`, hardcoded nel frontend), repo GitHub `iacopofratini/ferroteca-backend`.
- **Frontend**: singolo file `index.html` (HTML/CSS/JS vanilla, ~19 KB), tema chiaro/scuro, discretamente curato — **ma senza alcun repository git**: non versionato, non tracciato, nessuna cronologia.
- **Vector DB**: Supabase (Postgres + pgvector), tabella `documents`, ricerca via RPC `match_documents` (cosine similarity, HNSW).
- **Embedding**: Google Gemini.
- **LLM risposta**: `gemini-2.5-flash`.
- **Corpus**: ~450 MB di PDF normativi ferroviari in locale (`ferroteca-backend/data/pdfs`), esclusi da git.

Il file `README.md` del backend porta però un frontmatter da **Hugging Face Space** (`sdk: docker`, `app_port: 7860`), mentre il remote git è solo GitHub → Render. È un residuo di un tentativo di deploy su HF Spaces mai ripulito, oppure un doppio deploy non più coordinato col frontend. Da chiarire e consolidare su un'unica piattaforma.

## 2. La base architetturale è valida

Non c'è motivo tecnico per buttare via tutto e ripartire da zero. La scelta FastAPI + pgvector + Gemini + frontend statico è proporzionata alla scala del progetto (un assistente documentale interno, non un prodotto multi-tenant), lo stack è mainstream e ben supportato, e il codice di business logic (`services/rag.py`) è corto, leggibile, senza astrazioni superflue. Il problema di Ferroteca non è "il codice è scritto male": è che il progetto è cresciuto per iterazioni manuali senza igiene di repository, e questo ha prodotto vincoli concreti che vanno risolti prima di aggiungere altre funzionalità (la sync OneDrive in roadmap, in particolare, amplificherebbe ogni problema esistente).

## 3. Problemi reali, in ordine di gravità

### 3.1 Tre pipeline di indicizzazione divergenti, con modelli di embedding diversi

Esistono tre implementazioni separate della stessa logica (carica PDF → chunk → embed → upsert su Supabase):

| File | Modello embedding usato |
|---|---|
| `services/rag.py` (produzione, usato da `/api/documents/upload` e `/reindex`) | `models/gemini-embedding-001` |
| `sync_documents.py` (script di sync da cartella locale/OneDrive) | `models/embedding-001` |
| `services/reindex_ieac_accm.py` (script una tantum) | `models/gemini-embedding-001` |

`sync_documents.py` usa un **modello di embedding diverso** da quello usato in produzione per rispondere alle domande. Se questo script viene eseguito, inserisce vettori generati da uno spazio semantico diverso nella stessa tabella `documents` interrogata da `rag.py`: la ricerca per similarità coseno confronterebbe embedding non comparabili, degradando silenziosamente (senza errori visibili) la qualità delle risposte proprio sui documenti sincronizzati. Questo è il rischio più serio del progetto: un bug che non si manifesta come crash, ma come risposte progressivamente peggiori.

`sync_documents.py` inoltre scrive/legge colonne (`source_path`, `category`, `file_hash`, tabella `sync_registry`) che non compaiono nello schema documentato in `ferroteca_memoria_progetto.md` — la documentazione di progetto è disallineata rispetto allo schema reale del database.

### 3.2 Nessuna autenticazione sugli endpoint di scrittura

`app.py` monta CORS con `allow_origins=["*"]`, e gli endpoint `/api/documents/upload`, `/api/documents/reindex`, `/api/documents/{filename}` (DELETE) non richiedono alcuna credenziale. Chiunque conosca l'URL Render può caricare PDF arbitrari, cancellare documenti indicizzati o forzare una re-indicizzazione completa (costo Gemini a carico tuo). Per un archivio di normativa ferroviaria aziendale, è un'esposizione da chiudere prima di qualunque altro intervento — basterebbe una API key condivisa in header su questi tre endpoint.

### 3.3 Frontend non versionato

`ferroteca-frontend/` è una cartella con un solo file, senza `.git`. L'unica "cronologia" sono le versioni precedenti salvate a mano in `File utili:backup/HTML prova/` (prototipo + v1.1–v1.4). Se quel file locale si perde o viene sovrascritto per errore, non c'è modo di recuperarlo se non da un backup manuale. Va messo sotto controllo di versione (anche solo aggiungendolo come secondo repo, o come cartella nel repo backend).

### 3.4 Materiale sensibile fuori controllo

`File utili:backup/keys.rtf` (696 byte) è un file di testo con — a giudicare dal nome — credenziali, seduto fuori da qualunque `.gitignore` o repository, in una cartella "backup" generica. Non ne ho letto il contenuto per non esporlo in questa sessione, ma va trattato come una fuga di credenziali potenziale: spostalo in un password manager e revoca/ruota qualunque chiave API contenuta, poi elimina il file.

### 3.5 Pulizia di repository

- `services/data/pdfs/` — cartella vuota, residuo di una struttura precedente (i PDF ora vivono in `data/pdfs/`).
- `File Backup funzionanti/` — versioni vecchie di `documents.py` e `rag.py` sciolte nella cartella radice, fuori da git, senza indicazione di quando risalgano o perché siano state tenute.
- `venv/` dentro `ferroteca-backend/` — l'ambiente virtuale Python è fisicamente nella cartella del progetto; il `.gitignore` attuale (`__pycache__/`, `*.pyc`, `.env`, `data/pdfs/`, `*.pdf`) **non esclude `venv/`**. L'indice git risulta piccolo (939 byte, quindi verosimilmente venv non è mai stato aggiunto), ma è una svista da correggere subito aggiungendo `venv/` al `.gitignore` prima che qualcuno lanci un `git add -A` distratto.
- Dipendenze non pinnate in `requirements.txt` (`google-genai>=1.7.0`, `supabase>=2.15.0`, `httpx>=0.28.1` senza upper bound): un aggiornamento a monte di queste librerie può rompere silenziosamente il backend in produzione senza che tu abbia cambiato una riga di codice.

### 3.6 Persistenza dei PDF sul deploy

Il backend gira in un container (Render, con `Dockerfile` che crea `data/pdfs/` vuota a ogni build). Se i PDF vengono caricati via `/upload` direttamente sul servizio deployato (anziché indicizzati da locale con `sync_documents.py`), e il piano Render non ha un disco persistente collegato, quei file vengono persi a ogni redeploy o riavvio. Non è un problema per le risposte in chat (che leggono solo da Supabase), ma lo è per gli endpoint che controllano l'esistenza fisica del file (`file_exists` in `list_indexed_volumes`) e per qualunque futura funzione che debba riaprire il PDF originale (punto 9.2 della roadmap, "Apri a pagina X"). Va verificato se Render ha un persistent disk montato su `data/pdfs`; altrimenti la fonte di verità dei file deve restare Supabase Storage o il disco locale con sync esplicita.

### 3.7 Documenti di arricchimento mancanti nella cartella locale (lacuna aziendale, non di questo progetto)

`data/pdfs/` contiene, oltre ai 29 testi principali, sei sottocartelle di
arricchimento (`DE`, `DGI`, `IMPATTI`, `NOTE`, `PE`, `RFI-FILE NORMATIVI
MISTI`, 259 file). Mappando quali file di arricchimento si collegano a quale
testo principale (metodo e dati completi in `docs/enrichment_mapping.md` /
`.json`), sono emersi **52 documenti citati esplicitamente da un file
"impatto" ufficiale RFI come contenenti una modifica**, ma assenti dalla
cartella locale — quasi tutti datati 2023-2025. Iacopo conferma che la
cartella locale è copia integrale di quella condivisa aziendale: se mancano
qui, mancano anche lì. Non è un problema introdotto da questo lavoro né
risolvibile da codice — va segnalato/recuperato in azienda. Elenco completo
in `docs/enrichment_mapping.md`, sezione "Documenti citati ma assenti dalla
cartella locale".

## 4. Riscrivere da zero o no?

**No.** Non ci sono vincoli architetturali che giustifichino un rewrite: lo stack è corretto per lo scopo, il volume di codice è piccolo (poche centinaia di righe totali), e i problemi individuati sono tutti risolvibili con refactoring mirato, non con una riscrittura. Buttare via il lavoro esistente peggiorerebbe la situazione — perderesti la pipeline RAG già funzionante e testata in produzione (memoria progetto conferma: ricerca semantica operativa, costi tracciati, billing attivo) per ricostruire da capo qualcosa di equivalente.

## 5. Piano d'intervento consigliato (in ordine)

1. **Blocca il rischio silenzioso**: prima di eseguire ancora `sync_documents.py`, allinea il modello di embedding a `models/gemini-embedding-001` (uguale a `rag.py`) — o meglio, elimina la duplicazione: estrai un unico modulo di indicizzazione condiviso tra `rag.py`, `sync_documents.py` e `reindex_ieac_accm.py`.
2. **Aggiungi autenticazione minima** (header con API key) su upload/reindex/delete.
3. **Metti il frontend sotto git**, anche solo come sottocartella del repo backend o come repo separato collegato.
4. **Rimuovi/ruota `keys.rtf`** e sposta eventuali credenziali in un gestore password o in variabili d'ambiente della piattaforma di deploy.
5. **Ripulisci la cartella**: elimina `services/data/pdfs` vuota, archivia (o elimina dopo verifica) `File Backup funzionanti/` e `File utili:backup/HTML prova/`, aggiungi `venv/` al `.gitignore`.
6. **Aggiorna `ferroteca_memoria_progetto.md`** con lo schema reale della tabella `documents` (incluse le colonne aggiunte da `sync_documents.py`) e chiarisci la piattaforma di deploy effettiva (Render, non Hugging Face — o rimuovi il frontmatter HF se non più in uso).
7. **Pinna le dipendenze** in `requirements.txt`.
8. Solo dopo questi punti, riprendi la roadmap (sync OneDrive, storage PDF su Supabase, cronologia chat) — implementarla ora moltiplicherebbe i problemi esistenti invece di risolverli.

## 6. In sintesi

Ferroteca è un prototipo funzionante costruito bene per essere stato assemblato a mano senza un team: la logica RAG è solida, il frontend è curato, il costo per volume è tracciato. Ma è cresciuto senza igiene di repository — tre pipeline di indicizzazione che divergono silenziosamente, un frontend senza versionamento, endpoint di scrittura aperti a chiunque, e credenziali fuori posto. Sono tutti problemi da "messa in sicurezza e consolidamento", non da riscrittura. Il prossimo passo con il ritorno più alto è il punto 1 (allineare gli embedding): è l'unico bug che potrebbe già star degradando le risposte senza che tu te ne accorga.
