import os
from pathlib import Path
from typing import List, Dict, Any
import google.generativeai as genai
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from supabase import create_client, Client

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

genai.configure(api_key=GEMINI_API_KEY)
PDF_DIR = Path("data/pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_embeddings():
    return GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=GEMINI_API_KEY)

def embed_texts(texts: List[str]) -> List[List[float]]:
    return get_embeddings().embed_documents(texts)

def index_pdf(pdf_path: Path) -> int:
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    for page in pages:
        page.metadata["volume"] = pdf_path.stem
        page.metadata["filename"] = pdf_path.name
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120, separators=["\n\n", "\n", ".", " ", ""])
    chunks = splitter.split_documents(pages)
    supabase = get_supabase()
    supabase.table("documents").delete().eq("filename", pdf_path.name).execute()
    texts = [c.page_content for c in chunks]
    embeddings = embed_texts(texts)
    rows = []
    for i, c in enumerate(chunks):
        rows.append({
            "content": c.page_content,
            "embedding": embeddings[i],
            "filename": pdf_path.name,
            "volume": pdf_path.stem,
            "page": c.metadata.get("page", 0),
        })
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        supabase.table("documents").insert(rows[i:i+batch_size]).execute()
    return len(chunks)

def index_all_pdfs() -> Dict[str, int]:
    return {p.name: index_pdf(p) for p in PDF_DIR.glob("*.pdf")}

def list_indexed_volumes() -> List[Dict[str, Any]]:
    supabase = get_supabase()
    result = supabase.table("documents").select("filename, volume").execute()
    volumes = {}
    for row in (result.data or []):
        fname = row.get("filename", "")
        if fname and fname not in volumes:
            volumes[fname] = {"filename": fname, "volume": row.get("volume", fname)}
    pdfs = {p.name for p in PDF_DIR.glob("*.pdf")}
    for v in volumes.values():
        v["file_exists"] = v["filename"] in pdfs
    return list(volumes.values())
