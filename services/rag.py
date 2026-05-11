import os
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv
import google.generativeai as genai
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from supabase import create_client

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

genai.configure(api_key=GEMINI_API_KEY)
PDF_DIR = Path("data/pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_embedding(text: str) -> List[float]:
    result = genai.embed_content(
        model="models/gemini-embedding-001",
        content=text,
        task_type="retrieval_document",
    )
    return result["embedding"]

def index_pdf(pdf_path: Path) -> int:
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    for page in pages:
        page.metadata["volume"] = pdf_path.stem
        page.metadata["filename"] = pdf_path.name
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = splitter.split_documents(pages)
    supabase = get_supabase()
    supabase.table("documents").delete().eq("filename", pdf_path.name).execute()
    rows = []
    for chunk in chunks:
        rows.append({
            "filename": pdf_path.name,
            "volume": chunk.metadata.get("volume", pdf_path.stem),
            "page": int(chunk.metadata.get("page", 0)),
            "content": chunk.page_content,
            "embedding": get_embedding(chunk.page_content),
        })
    for i in range(0, len(rows), 50):
        supabase.table("documents").insert(rows[i:i+50]).execute()
    return len(rows)

def index_all_pdfs() -> Dict[str, int]:
    results = {}
    for p in PDF_DIR.glob("*.pdf"):
        try:
            results[p.name] = index_pdf(p)
        except Exception:
            results[p.name] = -1
    return results

def list_indexed_volumes() -> List[Dict[str, Any]]:
    supabase = get_supabase()
    result = supabase.table("documents").select("filename, volume").execute()
    seen = {}
    for row in result.data or []:
        fname = row["filename"]
        if fname not in seen:
            seen[fname] = {"filename": fname, "volume": row["volume"]}
    return list(seen.values())

def ask(question: str, top_k: int = 6) -> Dict[str, Any]:
    query_embedding = get_embedding(question)
    supabase = get_supabase()
    result = supabase.rpc(
        "match_documents",
        {"query_embedding": query_embedding, "match_count": top_k},
    ).execute()
    docs = result.data or []
    if not docs:
        return {
            "answer": "Non ho trovato informazioni rilevanti nei manuali caricati.",
            "sources": [],
        }
    context_parts = []
    sources = []
    seen = set()
    for doc in docs:
        volume = doc.get("volume", "Sconosciuto")
        page = doc.get("page", "?")
        content = doc.get("content", "")
        context_parts.append(f"Fonte: {volume} pagina {page}\n{content}")
        key = f"{volume}_pagina_{page}"
        if key not in seen:
            sources.append({"volume": volume, "page": page})
            seen.add(key)
    context = "\n---\n".join(context_parts)
    prompt = f"""Sei Ferroteca, assistente esperto di procedure ferroviarie italiane.
Rispondi SOLO dai documenti forniti. Se non trovi l'informazione di' "Non presente nei manuali caricati."
Non usare conoscenza esterna. Cita sempre volume e pagina.

DOCUMENTI:
{context}

DOMANDA: {question}

RISPOSTA:
1. Sintesi
2. Procedura dettagliata
3. Fonte"""
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config={"temperature": 0.1, "max_output_tokens": 8192},
    )
    return {"answer": model.generate_content(prompt).text, "sources": sources}
