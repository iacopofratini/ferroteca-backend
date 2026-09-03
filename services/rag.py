import json
import os
from pathlib import Path
from typing import List, Dict, Any

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from supabase import create_client, Client

from services import llm_provider

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

PDF_DIR = Path("data/pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)

ENRICHMENT_MAP_PATH = Path("docs/enrichment_mapping.json")


def main_text_filenames() -> set:
    """Nomi file (con .pdf) dei 29 testi principali, primo livello di PDF_DIR.

    Attenzione: legge il disco locale. In produzione (Render) `data/pdfs/`
    riparte vuota a ogni deploy (AUDIT.md 3.6) — questa funzione restituisce
    un insieme vuoto li'. Non usarla per decidere cosa mostrare/recuperare
    a runtime: usare invece `enrichment_filenames()` (basata su
    enrichment_mapping.json, presente anche in produzione) in negativo.
    Resta utile solo in locale, per l'indicizzazione.
    """
    return {p.name for p in PDF_DIR.glob("*.pdf")}


def enrichment_filenames() -> set:
    """Nomi file (senza sottocartella) di tutti gli arricchimenti "certi" mappati.

    Basata su docs/enrichment_mapping.json, che e' nel repository e quindi
    presente anche nel container Render — a differenza di main_text_filenames(),
    funziona correttamente anche in produzione.
    """
    if not ENRICHMENT_MAP_PATH.exists():
        return set()
    data  = json.loads(ENRICHMENT_MAP_PATH.read_text())
    names = set()
    for entry in data.get("mappatura_per_volume", {}).values():
        names.update(Path(rel).name for rel in entry.get("da_citazione", []))
    return names


def load_enrichment_map() -> Dict[str, List[str]]:
    """Volume principale -> nomi file di arricchimento collegati.

    Usa solo i collegamenti "da_citazione" (confermati da un file "impatto"
    ufficiale RFI). Quelli "da_contenuto" (suggeriti da Gemini, non
    verificati) restano esclusi finche' non c'e' un controllo a campione
    (decisione del 2026-09-03, vedi docs/DECISION_LOG.md).
    """
    if not ENRICHMENT_MAP_PATH.exists():
        return {}
    data = json.loads(ENRICHMENT_MAP_PATH.read_text())
    result = {}
    for volume, entry in data.get("mappatura_per_volume", {}).items():
        files = [Path(rel).name for rel in entry.get("da_citazione", [])]
        if files:
            result[volume] = files
    return result


def enrichment_file_paths() -> List[Path]:
    """Percorsi reali dei file di arricchimento "certi", per l'indicizzazione."""
    if not ENRICHMENT_MAP_PATH.exists():
        return []
    data = json.loads(ENRICHMENT_MAP_PATH.read_text())
    rel_paths = set()
    for entry in data.get("mappatura_per_volume", {}).values():
        rel_paths.update(entry.get("da_citazione", []))
    return [PDF_DIR / rel for rel in sorted(rel_paths)]


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def embed_texts(texts: List[str]) -> List[List[float]]:
    return llm_provider.embed(texts)


def index_pdf(pdf_path: Path) -> int:
    loader = PyPDFLoader(str(pdf_path))
    pages  = loader.load()
    for page in pages:
        page.metadata["volume"]   = pdf_path.stem
        page.metadata["filename"] = pdf_path.name

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_documents(pages)

    supabase = get_supabase()
    supabase.table("documents").delete().eq("filename", pdf_path.name).execute()

    texts      = [c.page_content for c in chunks]
    embeddings = embed_texts(texts)

    rows = [
        {
            "content":   chunks[i].page_content.replace("\x00", ""),
            "embedding": embeddings[i],
            "filename":  pdf_path.name,
            "volume":    pdf_path.stem,
            "page":      chunks[i].metadata.get("page", 0),
        }
        for i in range(len(chunks))
    ]

    batch_size = 50
    for i in range(0, len(rows), batch_size):
        supabase.table("documents").insert(rows[i : i + batch_size]).execute()

    return len(chunks)


def index_all_pdfs() -> Dict[str, int]:
    return {p.name: index_pdf(p) for p in PDF_DIR.glob("*.pdf")}


def index_enrichment_files() -> Dict[str, int]:
    """Indicizza i file di arricchimento "certi" (collegati da un impatto RFI)."""
    return {p.name: index_pdf(p) for p in enrichment_file_paths() if p.exists()}


def fetch_document_chunks(filename: str) -> List[Dict[str, Any]]:
    supabase = get_supabase()
    result = (
        supabase.table("documents")
        .select("content, page, volume")
        .eq("filename", filename)
        .order("page")
        .execute()
    )
    return result.data or []


def ask(question: str, top_k: int = 6) -> Dict[str, Any]:
    q_embedding = llm_provider.embed([question])[0]

    supabase = get_supabase()
    result   = supabase.rpc(
        "match_documents",
        {"query_embedding": q_embedding, "match_count": top_k},
    ).execute()

    docs = result.data or []
    if not docs:
        return {
            "answer":  "Non ho trovato informazioni rilevanti nei manuali caricati.",
            "sources": [],
        }

    context_parts, sources, seen, included_filenames = [], [], set(), set()
    for doc in docs:
        volume = doc.get("volume", "Sconosciuto")
        page   = doc.get("page", "?")
        context_parts.append(f"[Fonte: {volume} — pagina {page}]\n{doc['content']}")
        key = f"{volume} — pagina {page}"
        if key not in seen:
            sources.append({"volume": volume, "page": page})
            seen.add(key)
        if doc.get("filename"):
            included_filenames.add(doc["filename"])

    # Arricchimento: per ogni testo principale trovato tra i risultati, recupera
    # anche gli aggiornamenti/correzioni collegati (solo i collegamenti "certi",
    # confermati da un impatto RFI — vedi docs/DECISION_LOG.md 2026-09-03).
    enrichment_map = load_enrichment_map()
    enr_filenames = enrichment_filenames()
    main_volumes = {doc.get("volume") for doc in docs if doc.get("filename") not in enr_filenames}

    enrichment_parts = []
    for volume in main_volumes:
        for filename in enrichment_map.get(volume, []):
            if filename in included_filenames:
                continue
            included_filenames.add(filename)
            chunks = fetch_document_chunks(filename)
            if not chunks:
                continue
            enr_volume = chunks[0].get("volume", filename)
            full_text  = "\n".join(c.get("content", "") for c in chunks)
            enrichment_parts.append(f"[Aggiornamento — {enr_volume}, collegato a {volume}]\n{full_text}")
            sources.append({"volume": enr_volume, "page": "intero documento", "aggiornamento_di": volume})

    context = "\n\n---\n\n".join(context_parts)
    prompt_sections = f"""DOCUMENTI:
{context}"""
    if enrichment_parts:
        enrichment_text = "\n\n---\n\n".join(enrichment_parts)
        prompt_sections += f"""

AGGIORNAMENTI CORRELATI (correzioni/integrazioni ai documenti sopra — controlla se modificano quanto scritto e segnalalo nella risposta):
{enrichment_text}"""

    prompt = f"""Sei Ferroteca, assistente esperto di procedure ferroviarie italiane.
Rispondi SOLO dai documenti forniti. Se non trovi l'informazione dì: "Non presente nei manuali caricati."
Non usare conoscenza esterna. Cita sempre volume e pagina. Se un aggiornamento correlato modifica o integra
un documento principale, segnalalo esplicitamente nella risposta invece di ignorarlo.

{prompt_sections}

DOMANDA: {question}

RISPOSTA (1. Sintesi 2. Procedura dettagliata 3. Fonte):"""

    answer = llm_provider.generate(prompt)
    return {"answer": answer, "sources": sources}


def fetch_all_rows(select_cols: str, page_size: int = 1000) -> List[Dict[str, Any]]:
    """Legge tutte le righe di `documents`, paginando.

    Supabase/PostgREST limita di default una singola risposta a 1000 righe:
    con piu' di 1000 chunk in tabella (caso reale da quando l'arricchimento
    e' stato indicizzato, 2026-09-03) un `.select().execute()` semplice
    tronca i risultati in silenzio, senza errore.
    """
    supabase = get_supabase()
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        batch = supabase.table("documents").select(select_cols).range(start, start + page_size - 1).execute()
        data = batch.data or []
        rows.extend(data)
        if len(data) < page_size:
            break
        start += page_size
    return rows


def list_indexed_volumes() -> List[Dict[str, Any]]:
    """Elenco mostrato in libreria nell'app: solo i testi principali.

    Gli arricchimenti (Note/DE/PE/DGI, indicizzati per essere recuperati da
    ask() quando pertinenti) restano fuori da qui apposta: non sono libri a
    se' stanti, non devono comparire come tali nell'elenco visibile.
    """
    enr_filenames = enrichment_filenames()
    local_pdfs    = main_text_filenames()  # vuoto in produzione, vedi nota sopra la funzione
    volumes = {}
    for row in fetch_all_rows("filename, volume"):
        fname = row.get("filename", "")
        if fname and fname not in enr_filenames and fname not in volumes:
            volumes[fname] = {"filename": fname, "volume": row.get("volume", fname)}
    for v in volumes.values():
        v["file_exists"] = v["filename"] in local_pdfs
    return list(volumes.values())


def debug_index_status() -> Dict[str, Any]:
    rows = fetch_all_rows("filename, volume")
    counts: Dict[str, int] = {}
    for row in rows:
        fname = row.get("filename", "unknown")
        counts[fname] = counts.get(fname, 0) + 1
    return {"total_chunks": len(rows), "per_file": counts}
