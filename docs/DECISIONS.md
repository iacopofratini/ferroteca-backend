# Ferroteca — Decision Log (ADR leggero)

Formato: data, decisione, alternative scartate, motivazione. Per il log
cronologico "cosa deciso oggi, fatto, prossimo passo" vedi
`docs/DECISION_LOG.md` — questo file è la versione sintetica e stabile,
pensata per essere letta anche fuori sessione (es. in presentazione).

Stato di ogni voce indicato esplicitamente: **Deciso e fatto** / **Deciso,
non ancora eseguito** / **Proposto, in attesa di conferma**.

---

## Perché pgvector (Supabase) come vector database

**Stato:** Deciso e fatto (scelta di partenza del progetto).

**Decisione:** usare l'estensione pgvector di Postgres, dentro Supabase,
invece di un vector database dedicato (Pinecone, Weaviate, Qdrant...).

**Alternative scartate:** un vector DB dedicato — scartato perché
aggiungerebbe un servizio esterno in più da pagare e gestire, per un volume
di dati (poche migliaia di chunk oggi, ordine delle decine di migliaia a
corpus completo) che Postgres gestisce senza problemi.

**Motivazione:** Supabase era già nello stack per altri motivi (nel
percorso di adozione aziendale servirà comunque un database relazionale per
ruoli utente e banco domande di training) — pgvector evita di introdurre un
secondo sistema di storage solo per la ricerca semantica. Coerente con la
regola "budget prima" del progetto.

## Perché chunk_size=800 / chunk_overlap=120

**Stato:** Deciso e fatto (scelta di partenza del progetto, invariata).

**Decisione:** dividere ogni PDF in frammenti (chunk) di circa 800 caratteri,
con una sovrapposizione di 120 caratteri tra un frammento e il successivo.

**Alternative scartate:** chunk più grandi (es. per pagina intera) —
scartati perché renderebbero il contesto passato al modello più costoso e
meno mirato; chunk più piccoli — scartati perché rischiano di spezzare una
procedura ferroviaria a metà, perdendo il contesto necessario a rispondere
correttamente.

**Motivazione:** 800/120 è un compromesso comune per documenti procedurali
in prosa (non tabellari): abbastanza contesto per una procedura completa,
overlap sufficiente a non perdere il filo tra un chunk e l'altro.

## Perché un modulo `llm_provider` astratto, non l'SDK Gemini diretto

**Stato:** Deciso e fatto (2026-09-01).

**Decisione:** centralizzare ogni chiamata al provider LLM/embedding dietro
un'interfaccia stabile (`embed()`, `generate()`) in `services/llm_provider.py`,
implementata oggi da `GeminiProvider`.

**Alternative scartate:** lasciare ogni script con la propria chiamata
diretta all'SDK — è lo stato che ha causato il bug più grave del progetto
(vedi `AUDIT.md` 3.1: `sync_documents.py` usava un modello di embedding
diverso da `rag.py`, imbedding non comparabili nella stessa tabella).

**Motivazione:** due problemi in uno. Primo, un solo punto dove il modello/
i parametri sono definiti elimina la classe di bug "due file, due
configurazioni diverse". Secondo, il provider è dichiaratamente provvisorio
(Gemini scelto solo per costo in fase di test) — cambiarlo in futuro
significa toccare un file, non cacciare le chiamate SDK sparse nel codice.

## Perché Supabase Auth ora, non SSO aziendale

**Stato:** Proposto, in attesa di implementazione (punto 3 del piano).

**Decisione prevista:** login email/password via Supabase Auth nel
prototipo, con un modello di ruoli (`operatore`/`admin`) disaccoppiato dal
provider di identità.

**Alternative scartate:** aspettare la conferma aziendale su Entra ID/SSO
prima di costruire qualunque autenticazione — scartata perché bloccherebbe
la presentazione: senza autenticazione minima oggi, gli endpoint di
scrittura restano aperti a chiunque (AUDIT.md 3.2).

**Motivazione:** Supabase Auth è già nello stack, permette di partire
subito. Il punto critico è progettare il modello di ruoli come strato
separato dal "come ti autentichi" — così quando arriverà (se arriverà) la
conferma su Entra ID, si aggiunge un provider OIDC senza riscrivere permessi
e ruoli.

## Perché monorepo (proposto)

**Stato:** Proposto, esecuzione rimandata — decisione di dettaglio non
ancora presa (nome del repo GitHub, coordinamento con Render).

**Decisione prevista:** unire `ferroteca-backend/` e `ferroteca-frontend/`
in un unico repository (`apps/backend/`, `apps/frontend/`).

**Alternative scartate:** mantenere i due repo separati — è lo stato
attuale, ma è un limite storico di un tool che non lavorava direttamente
sulla cartella, non una scelta architetturale (il frontend oggi non ha
nemmeno un repository git proprio, vedi AUDIT.md 3.3).

**Motivazione:** un solo prodotto, un solo team, una cronologia unica.
Rimandato perché tocca la configurazione di deploy Render e va deciso con
calma se rinominare il repo GitHub o mantenere il nome attuale.

## Perché nessun tracciamento server-side dei risultati di training

**Stato:** Deciso e fatto (vincolo di progetto, punto 5 non ancora
implementato ma la decisione sul tracciamento è già presa).

**Decisione:** il modulo training (banco domande generate e approvate) non
salva né punteggi né storico delle risposte per utente sul server. Le
risposte dell'esercitazione, se salvate, restano solo lato client
(export locale), mai inviate né conservate sul backend.

**Alternative scartate:** tracciare i risultati per dare feedback nel
tempo all'operatore — scartata esplicitamente: l'obiettivo è che nessuno si
senta valutato durante l'esercitazione, e l'app è dichiaratamente a scopo
illustrativo, non un sistema di certificazione.

**Motivazione:** coerente con l'altro vincolo di progetto (niente audit
trail delle domande in chat) — Ferroteca non deve diventare uno strumento
di sorveglianza sugli operatori.
