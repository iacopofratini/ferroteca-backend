# Prompt di avvio — Ferroteca, consolidamento pre-presentazione aziendale

Copia questo prompt come primo messaggio della sessione Claude Code, aperta nella cartella `ferroteca-app-code/` (contiene oggi `ferroteca-backend/`, repo git collegato a `https://github.com/iacopofratini/ferroteca-backend.git`, e `ferroteca-frontend/`, senza repo).

---

Stai lavorando su Ferroteca, un assistente RAG per procedure ferroviarie italiane (FastAPI + Supabase pgvector + un provider LLM). Oggi è un prototipo amatoriale funzionante; l'obiettivo di questa fase è renderlo presentabile a un'azienda ferroviaria per una futura adozione ufficiale — quindi non solo "far funzionare le cose", ma costruire una base che regga un'eventuale migrazione verso infrastruttura e canali di identità aziendali, pur senza ancora sapere quali saranno esattamente (l'azienda usa OneDrive/Copilot Microsoft, ma non c'è ancora nessuna conferma su SSO/Entra ID o hosting per Ferroteca).

Prima di scrivere una sola riga di codice, leggi per intero `ferroteca-backend/docs/AUDIT.md`: contiene l'audit tecnico completo del progetto (1 settembre 2026) con tutti i problemi noti, la loro gravità e le motivazioni. Non procedere finché non l'hai letto e capito.

Il progetto NON va riscritto da zero — l'audit lo esclude esplicitamente. È un consolidamento mirato. Lavora in modo incrementale: un commit logico per intervento, messaggio di commit chiaro, niente big-bang. Ogni intervento con impatto strutturale (rinominare il repo, spostare cartelle, cambiare provider) va confermato con me prima di essere eseguito, anche se elencato sotto come raccomandazione.

## Vincoli non negoziabili

- Non toccare `data/pdfs/` (450 MB di corpus normativo, fonte di verità, materiale rfi.it senza problemi di copyright) e non eseguire `sync_documents.py` finché il punto 1 sotto non è risolto.
- Non leggere né spostare il contenuto di `File utili:backup/keys.rtf`: segnalami solo che esiste e va gestito da me manualmente (rotazione chiavi + eliminazione). Non includerlo mai in un commit.
- Nessuna modifica va pushata su un remote GitHub senza mio ok esplicito: lavora su branch e fammi vedere il diff prima di ogni push.
- Utenti reali previsti: operatori di stazione (DM/DMO/DCO) in sola consultazione ed esercitazione, più un livello admin per gestione documenti/DB/sviluppo. Il modello di permessi deve riflettere questi due livelli fin da subito.
- Niente audit trail delle domande/risposte in chat: l'app è dichiaratamente a scopo illustrativo/di esercitazione, le risposte non fanno fede a livello di sicurezza operativa. Non aggiungere tracciamento delle query non richiesto.
- Il provider LLM/embedding è **provvisorio** (oggi Gemini, scelto solo per costo in fase di test; verrà sostituito a fine testing con un modello più efficiente). Non hardcodare chiamate dirette a un SDK Gemini sparse nei file — vedi punto 1.

## Interventi da fare, in quest'ordine

### 1. Bug silenzioso più grave + astrazione del provider LLM (blocca tutto il resto)
`sync_documents.py` usa `models/embedding-001`, mentre `services/rag.py` (produzione) e `services/reindex_ieac_accm.py` usano `models/gemini-embedding-001`. Oltre a essere un bug (righe in Supabase con embedding di spazi semantici diversi, degrado silenzioso della ricerca), è sintomo dello stesso problema architetturale: tre punti diversi che parlano direttamente con l'SDK Gemini, ognuno a modo suo.
Risolvi le due cose insieme: crea un unico modulo `llm_provider` (o simile) che espone un'interfaccia stabile — `embed(texts) -> vectors`, `generate(prompt) -> text` — dietro cui oggi gira Gemini. Tutti e tre i punti di ingresso (upload API, sync da cartella, reindex singolo) e il futuro modulo training (punto 5) devono passare da lì, mai dall'SDK direttamente. Verifica se in Supabase esistono già righe indicizzate col modello sbagliato e proponimi come identificarle/ripulirle.

### 2. Consolidamento in monorepo
I due repo sono separati solo per un limite storico di un tool che non lavorava direttamente sulla cartella, non per scelta architetturale — vanno uniti. Proponimi (non eseguire senza conferma) una struttura tipo:
```
ferroteca/
├── apps/
│   ├── backend/     (contenuto attuale di ferroteca-backend, ripulito)
│   └── frontend/    (contenuto attuale di ferroteca-frontend)
├── docs/
│   ├── AUDIT.md
│   ├── DECISIONS.md
│   └── BLUEPRINT.md
├── CLAUDE.md
└── README.md
```
Valuta se conviene rinominare il repo GitHub da `ferroteca-backend` a `ferroteca` o mantenere il nome attuale per non rompere il collegamento con Render — presentami il trade-off, decido io. I deploy Render backend/frontend restano separati impostando la "root directory" per servizio sulla sottocartella corretta.

### 3. Autenticazione e permessi per ruoli
Utenti reali: operatori (consultazione + esercitazione) e admin (gestione documenti/DB/sviluppo). Serve un vero modello a due livelli:
- Usa **Supabase Auth** (già nello stack) con una tabella `user_roles` che assegna `operatore` / `admin` a ogni utente.
- Middleware backend che valida il JWT Supabase su ogni richiesta: `operatore` accede a `/api/chat/ask` e al modulo training in consultazione; `upload`, `reindex`, `delete` e revisione del banco domande (punto 5) restano riservati ad `admin`.
- **Progetta questo livello disaccoppiato dal provider di identità**: login email/password via Supabase Auth oggi, ma domani potrebbe servire SSO Entra ID — l'obiettivo è aggiungere un provider OIDC senza rifare il modello di ruoli/permessi. Documenta questa scelta in `docs/DECISIONS.md`.
- Frontend: schermata di login minimale, token passato nelle chiamate API.
- Restringi `allow_origins` CORS all'origine reale del frontend invece di `*`.

### 4. Infrastruttura trattata come sostituibile, non definitiva
Render e Supabase vanno bene per questa fase (prototipo/presentazione), ma se l'azienda adotta Ferroteca ufficialmente è probabile che chieda hosting sotto la propria governance (lo stack aziendale è Microsoft 365/Copilot, quindi verosimilmente Azure). Il backend è già containerizzato (`Dockerfile`): è la base che rende plausibile una futura migrazione (es. Azure Container Apps) senza riscrittura — a condizione che i dettagli specifici di Supabase (RPC `match_documents`, Auth, eventuale Storage) restino isolati dietro un layer di accesso dati pulito, mai sparsi nella business logic. Applica questo principio quando tocchi `services/rag.py` e il resto: la logica RAG non deve sapere che il DB è "Supabase", deve parlare con un'interfaccia tipo `VectorStore`/`UserStore`. Documenta la scelta in `docs/BLUEPRINT.md`.

### 5. Modulo Training (nuova funzionalità)
Generatore di domande casuali sulla normativa, a partire dai volumi già indicizzati, per l'esercitazione degli operatori. Riferimento aziendale: esiste già un applicativo simile (non AI) chiamato **GC App (Gestione della Circolazione APP)**, usato dai DCO — se ti fornisco materiale su come funziona, allinea terminologia/UX a quello, è un pattern che gli utenti già conoscono.
Requisiti:
- **Banco domande con revisione**: le domande sono generate (via il modulo `llm_provider` del punto 1, non chiamate dirette a un SDK) e salvate in una tabella (es. `training_questions`, stato draft/approvata). Solo un admin le rivede e le approva prima che diventino visibili agli operatori — mai generazione al volo mostrata direttamente.
- **Nessun tracciamento server-side dei risultati per utente**: niente punteggio/storico persistito lato backend collegato all'identità dell'operatore — l'obiettivo è che nessuno si senta valutato. Le risposte dell'esercitazione possono essere salvate/esportate **solo lato client**, dall'utente stesso (es. generazione CSV/PDF nel browser), senza mai passare né restare sul server.

### 6. Igiene di repository
- Aggiungi `venv/` al `.gitignore`.
- Rimuovi la cartella vuota `services/data/pdfs/`.
- Pinna tutte le dipendenze in `requirements.txt`.
- Verifica il frontmatter Hugging Face Space in `README.md`: se non è un deploy attivo, segnalamelo prima di rimuoverlo.
- Decidi con me cosa fare di `File Backup funzionanti/` e `File utili:backup/HTML prova/` (archiviare fuori dal repo attivo o eliminare dopo mia conferma).

### 7. Documentazione mancante, riflettendo lo stato reale (non aspirazionale)
- `CLAUDE.md` — contesto per sessioni future: stack, struttura cartelle del monorepo, comandi per far girare backend/frontend in locale, dove vivono le variabili d'ambiente, modello di ruoli, vincoli noti (rimanda a `docs/AUDIT.md`).
- `docs/DECISIONS.md` — decision log in formato ADR leggero (data, decisione, alternative scartate, motivazione). Includi almeno: perché pgvector, perché chunk_size=800/overlap=120, perché Supabase Auth ora e non SSO, perché monorepo, perché provider LLM astratto, perché niente tracciamento risultati training.
- `docs/BLUEPRINT.md` — architettura attuale con diagramma testuale (frontend → backend → provider LLM astratto → Supabase), schema reale delle tabelle (`documents`, `sync_registry`, `user_roles`, `training_questions`), e una sezione esplicita "Cosa serve per l'adozione aziendale" che elenca gli incogniti aperti (conferma SSO, hosting definitivo, eventuale migrazione ad Azure) da verificare con l'azienda prima del go-live — questo è il documento che porterai in presentazione.

### 8. Solo dopo aver completato 1–7
Se resta budget, proponi (non implementare senza conferma) come affrontare la sync automatica da OneDrive della vecchia roadmap, spiegando quali dei punti sopra erano bloccanti per farla in sicurezza — e nota che l'integrazione OneDrive reale dipenderà comunque dalla conferma aziendale sui permessi Microsoft 365, quindi va tenuta disaccoppiata (es. dietro un flag) finché quella conferma non arriva.

## Al termine di ogni punto

Riportami: cosa hai cambiato, perché, cosa NON hai potuto verificare (es. se non hai accesso a Supabase per controllare righe con embedding sbagliato), e cosa resta aperto per me da decidere.
