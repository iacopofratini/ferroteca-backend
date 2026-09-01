import os
from pathlib import Path
from typing import List, Dict, Any

from google import genai
from google.genai import types
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from supabase import create_client, Client

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL   = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY", "")

_genai_client = genai.Client(api_key=GEMINI_API_KEY)

PDF_DIR = Path("data/pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=GEMINI_API_KEY,
    )


def embed_texts(texts: List[str]) -> List[List[float]]:
    embedder = get_embeddings()
    return embedder.embed_documents(texts, output_dimensionality=768)


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
            "content":   chunks[i].page_content,
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


def ask(question: str, top_k: int = 6) -> Dict[str, Any]:
    embedder    = get_embeddings()
    q_embedding = embedder.embed_query(question, output_dimensionality=768)

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

    context_parts, sources, seen = [], [], set()
    for doc in docs:
        volume = doc.get("volume", "Sconosciuto")
        page   = doc.get("page", "?")
        context_parts.append(f"[Fonte: {volume} — pagina {page}]\n{doc['content']}")
        key = f"{volume} — pagina {page}"
        if key not in seen:
            sources.append({"volume": volume, "page": page})
            seen.add(key)

    context = "\n\n---\n\n".join(context_parts)
    prompt  = f"""Sei Ferroteca, assistente esperto di procedure ferroviarie italiane.
Rispondi SOLO dai documenti forniti. Se non trovi l'informazione dì: "Non presente nei manuali caricati."
Non usare conoscenza esterna. Cita sempre volume e pagina.

DOCUMENTI:
{context}

DOMANDA: {question}

RISPOSTA (1. Sintesi 2. Procedura dettagliata 3. Fonte):"""

    response = _genai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=8192,
        ),
    )
    return {"answer": response.text, "sources": sources}


def list_indexed_volumes() -> List[Dict[str, Any]]:
    supabase = get_supabase()
    result   = supabase.table("documents").select("filename, volume").execute()
    volumes  = {}
    for row in (result.data or []):
        fname = row.get("filename", "")
        if fname and fname not in volumes:
            volumes[fname] = {"filename": fname, "volume": row.get("volume", fname)}
    pdfs = {p.name for p in PDF_DIR.glob("*.pdf")}
    for v in volumes.values():
        v["file_exists"] = v["filename"] in pdfs
    return list(volumes.values())


def debug_index_status() -> Dict[str, Any]:
    supabase = get_supabase()
    result   = supabase.table("documents").select("filename, volume").execute()
    rows     = result.data or []
    counts: Dict[str, int] = {}
    for row in rows:
        fname = row.get("filename", "unknown")
        counts[fname] = counts.get(fname, 0) + 1
    return {"total_chunks": len(rows), "per_file": counts}
