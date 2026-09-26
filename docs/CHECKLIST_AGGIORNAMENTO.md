Allineato a: 2026-09-26

# Checklist di ogni aggiornamento — cosa deve seguire una modifica

Regola generale di Iacopo: ogni modifica si porta dietro, senza che debba
chiederlo, l'aggiornamento di tutto ciò che la racconta o ne dipende.
Due strumenti:
1. questa tabella, da ripassare a ogni modifica;
2. `python3 scripts/check-coerenza.py` (dalla cartella `ferroteca-backend`),
   **prima di ogni commit**: se segnala PROBLEMI non si committa; gli AVVISI
   si leggono e si valutano.

## Se cambi… → aggiorna anche…

| Se la modifica… | …aggiorna anche | Controllato dallo script |
|---|---|---|
| **qualunque cosa** (è una decisione) | nuova voce datata `## AAAA-MM-GG` in `docs/DECISION_LOG.md` (subito); poi rileggi e alza `Allineato a` in `../CLAUDE.md`, `AUDIT.md`, `BLUEPRINT.md`, `DECISIONS.md` e in questo file | sì |
| risolve o apre un **problema noto** | tabella "Stato dei punti" in cima a `docs/AUDIT.md` (+ sezione 3.x) | no: da ricordare |
| cambia **come funziona `ask()`**, lo schema Supabase o l'architettura | `docs/BLUEPRINT.md` (diagramma, "come risponde", schema) | no: da ricordare |
| è una **scelta con alternative scartate** | voce in `docs/DECISIONS.md` | no: da ricordare |
| tocca **codice Python** | deve girare su Python 3.11 (Render) | sì: sintassi 3.11 + f-string |
| chiama il **provider AI** (Gemini oggi) | solo tramite `services/llm_provider.py` | sì: import diretti dell'SDK |
| cambia la **mappatura arricchimenti** | `docs/enrichment_mapping.md` (versione leggibile) insieme al `.json` | sì: JSON valido, nomi univoci |
| legge dati **a runtime in produzione** | non usare i PDF su disco (vuoti su Render): solo Supabase e file del repository | no: da ricordare |
| legge **molte righe** da Supabase | paginare con `.range()` e un ordine esplicito (limite silenzioso di 1000 righe) | no: da ricordare |
| cambia qualcosa di **visibile nel frontend** (`ferroteca-frontend/index.html`, senza git) | prova su telefono e computer, tema chiaro e scuro; salva una copia prima di modificare | no: da verificare a occhio |
| va **online** | commit e push su GitHub sono passi separati, ognuno su conferma di Iacopo con il diff mostrato prima; Render ridistribuisce da solo dopo il push | — |
| contiene **credenziali** | mai in git (`.env` è ignorato) | sì: file di credenziali tracciati |
