Allineato a: 2026-09-01 — vedi ultima voce di `docs/DECISION_LOG.md`

# Ferroteca — Blueprint architetturale

Stato reale del sistema oggi, non aspirazionale: dove non è ancora
costruito qualcosa lo dico esplicitamente, invece di descriverlo come se
esistesse già. Questo è il documento da usare in presentazione aziendale.

## 1. Architettura attuale — diagramma testuale

```
┌─────────────────────┐
│  Frontend            │  index.html statico (HTML/CSS/JS vanilla)
│  ferroteca-frontend/  │  nessun repository git proprio (AUDIT.md 3.3)
└──────────┬───────────┘
           │ HTTPS, URL Render hardcoded nel JS
           ▼
┌─────────────────────┐
│  Backend             │  FastAPI, deploy Render (Docker)
│  ferroteca-backend/   │  repo: github.com/iacopofratini/ferroteca-backend
│                       │
│  routers/documents.py │  upload / reindex / delete — OGGI SENZA AUTH
│  routers/chat.py      │  /api/chat/ask — OGGI SENZA AUTH
│  services/rag.py      │  logica RAG: chunking, ricerca, prompt
└──────────┬───────────┘
           │
           ▼
┌─────────────────────┐
│  services/llm_provider │  unico punto che parla col provider AI
│  (GeminiProvider oggi) │  embed() / generate() — vedi DECISIONS.md
└──────────┬───────────┘
           │
           ▼
┌─────────────────────┐         ┌──────────────────────┐
│  Gemini (Google)      │         │  Supabase              │
│  gemini-embedding-001 │         │  Postgres + pgvector    │
│  gemini-2.5-flash     │         │  chiamato DIRETTAMENTE  │
│  provvisorio — vedi    │         │  da services/rag.py,    │
│  vincoli di progetto   │         │  non dietro un'astrazione│
└───────────────────────┘         └──────────────────────┘
```

**Nota architetturale aperta:** `services/rag.py` chiama Supabase
direttamente (`create_client`, `.table()`, `.rpc()`). Non esiste ancora uno
strato `VectorStore`/`UserStore` che isoli i dettagli specifici di Supabase
(RPC `match_documents`, Auth, eventuale Storage) dalla logica RAG — è la
condizione posta dal punto 4 del piano di consolidamento per rendere
plausibile una futura migrazione (es. Azure Container Apps) senza
riscrittura. Non ancora fatto.

## 2. Schema reale del database (verificato via Supabase REST, 2026-09-01)

Tabelle effettivamente esposte oggi: **solo `documents` e `sync_registry`.**
`user_roles` e `training_questions` **non esistono ancora** — fanno parte
dei punti 3 e 5 del piano, non ancora implementati.

### `documents` (tabella di produzione, interrogata da `rag.py`)

| Colonna | Note |
|---|---|
| `id` | chiave primaria |
| `filename` | nome del PDF sorgente |
| `volume` | nome del volume (oggi = nome file senza estensione) |
| `page` | numero di pagina del chunk |
| `content` | testo del chunk |
| `embedding` | vettore pgvector |
| `created_at` | timestamp inserimento |

Svuotata il 2026-09-01 dopo la scoperta del bug sul modello di embedding
(vedi `DECISION_LOG.md`) — in attesa di ricaricamento pulito.

### `sync_registry` (usata solo da `sync_documents.py`)

| Colonna | Note |
|---|---|
| `id` | chiave primaria |
| `source_path` | percorso relativo del file nella cartella sincronizzata |
| `filename` | nome file |
| `category` | prima cartella del percorso (categoria) |
| `file_hash` | hash SHA-256, per capire se un file è cambiato |
| `synced_at` | timestamp sync |

**Disallineamento noto:** `sync_documents.py` scrive/legge anche
`source_path`, `category`, `file_hash` sulla tabella `documents` — colonne
che oggi **non esistono** su `documents` (solo su `sync_registry`). Lo
script quindi fallirebbe se eseguito così com'è. Decisione da prendere:
aggiungere le colonne a `documents` o semplificare lo script (vedi
`DECISION_LOG.md`, voce 2026-09-01).

### `user_roles` — pianificata, non ancora creata (punto 3)

Prevista: `user_id` (riferimento a Supabase Auth), `ruolo`
(`operatore`/`admin`).

### `training_questions` — pianificata, non ancora creata (punto 5)

Prevista: domanda generata, stato (`draft`/`approvata`), nessun campo che
colleghi risposte o punteggi a un utente specifico (vedi `DECISIONS.md`,
voce sul non-tracciamento).

## 3. Cosa serve per l'adozione aziendale — incognite aperte

Da verificare con l'azienda prima di un eventuale go-live, non assunzioni:

- **SSO / Entra ID**: nessuna conferma che l'azienda voglia/possa fornire
  un provider OIDC aziendale. Il modello di ruoli (punto 3) è progettato
  per aggiungerlo senza riscrivere permessi, ma resta da confermare se e
  quando arriverà.
- **Hosting definitivo**: Render/Supabase sono adeguati per prototipo e
  presentazione, non è dato per scontato che lo restino dopo un'eventuale
  adozione ufficiale. Lo stack aziendale è Microsoft 365/Copilot — verosimile
  ma non confermato un'eventuale migrazione ad Azure (Container Apps).
- **Persistenza dei PDF caricati**: da verificare se il piano Render ha un
  disco persistente collegato a `data/pdfs/` — altrimenti i file caricati
  via `/upload` (non tramite sync da locale) si perdono a ogni redeploy
  (AUDIT.md 3.6). Non blocca le risposte in chat (che leggono solo da
  Supabase), ma blocca funzioni che riaprono il PDF originale.
- **Integrazione OneDrive**: dipende dalla conferma aziendale sui permessi
  Microsoft 365 — va tenuta disaccoppiata (es. dietro un flag) finché quella
  conferma non arriva (punto 8 del piano).
- **Layer VectorStore/UserStore**: non ancora costruito (vedi sezione 1) —
  condizione per una migrazione infrastrutturale senza riscrittura della
  logica RAG.
