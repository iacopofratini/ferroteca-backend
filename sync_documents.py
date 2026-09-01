from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Dict, Any

import google.generativeai as genai
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from supabase import Client, create_client

# ---------------------------------------------------------------------------
# Variabili ambiente obbligatorie
# ---------------------------------------------------------------------------
GEMINI_API_KEY          = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL            = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
DOCS_ROOT_FOLDER        = Path(os.environ.get("DOCS_ROOT_FOLDER", "")).expanduser().resolve()

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL non impostata")
if not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY non impostata")
if not os.environ.get("DOCS_ROOT_FOLDER"):
    raise RuntimeError("DOCS_ROOT_FOLDER non impostata")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY non impostata")

genai.configure(api_key=GEMINI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

CHUNK_SIZE    = 800
CHUNK_OVERLAP = 120
BATCH_SIZE    = 50


# ---------------------------------------------------------------------------
# Struttura dati
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DocumentFile:
    abs_path: Path
    rel_path: str
    category: str
    filename: str
    file_hash: str


# ---------------------------------------------------------------------------
# Utilità filesystem
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def iter_pdf_files(root: Path) -> Iterator[Path]:
    for current_root, _, files in os.walk(root):
        current_dir = Path(current_root)
        for name in files:
            if name.lower().endswith(".pdf"):
                yield current_dir / name


def build_document_file(path: Path, root: Path) -> DocumentFile:
    rel_path = path.relative_to(root).as_posix()
    parts    = path.relative_to(root).parts
    category = parts[0] if len(parts) > 1 else "Root"
    return DocumentFile(path, rel_path, category, path.name, sha256_file(path))


def scan_documents(root: Path) -> list[DocumentFile]:
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Root folder non valida: {root}")
    return [build_document_file(p, root) for p in iter_pdf_files(root)]


# ---------------------------------------------------------------------------
# Utilità DB
# ---------------------------------------------------------------------------
def get_registry() -> dict[str, str]:
    print("[DB] Lettura sync_registry...", flush=True)
    result = supabase.table("sync_registry").select("source_path, file_hash").execute()
    print(f"[DB] {len(result.data or [])} record nel registro", flush=True)
    return {row["source_path"]: row["file_hash"] for row in (result.data or [])}


def remove_from_db(rel_path: str) -> None:
    supabase.table("documents").delete().eq("source_path", rel_path).execute()
    supabase.table("sync_registry").delete().eq("source_path", rel_path).execute()
    print(f"  [RIMOSSO] {rel_path}", flush=True)


def upsert_registry(doc: DocumentFile) -> None:
    supabase.table("sync_registry").upsert({
        "source_path": doc.rel_path,
        "filename":    doc.filename,
        "category":    doc.category,
        "file_hash":   doc.file_hash,
    }).execute()


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
def get_embedder() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=GEMINI_API_KEY
    )


def embed_texts(texts: List[str]) -> List[List[float]]:
    return get_embedder().embed_documents(texts)


# ---------------------------------------------------------------------------
# Indicizzazione di un singolo PDF
# ---------------------------------------------------------------------------
def index_document(doc: DocumentFile) -> int:
    print(f"  [LOAD] {doc.rel_path}", flush=True)
    try:
        loader = PyPDFLoader(str(doc.abs_path))
        pages  = loader.load()
    except Exception as exc:
        print(f"  [ERRORE LOAD] {doc.rel_path}: {exc}", flush=True)
        return 0

    for page in pages:
        page.metadata["filename"]    = doc.filename
        page.metadata["volume"]      = doc.abs_path.stem
        page.metadata["source_path"] = doc.rel_path
        page.metadata["category"]    = doc.category
        page.metadata["source_file"] = doc.filename
        page.metadata["file_hash"]   = doc.file_hash

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_documents(pages)
    if not chunks:
        print(f"  [SKIP] {doc.rel_path} — nessun chunk prodotto", flush=True)
        return 0

    texts      = [c.page_content for c in chunks]
    embeddings = embed_texts(texts)

    rows = []
    for i, chunk in enumerate(chunks):
        rows.append({
            "content":     chunk.page_content,
            "embedding":   embeddings[i],
            "filename":    doc.filename,
            "volume":      doc.abs_path.stem,
            "page":        chunk.metadata.get("page", 0),
            "source_path": doc.rel_path,
            "category":    doc.category,
            "source_file": doc.filename,
            "file_hash":   doc.file_hash,
        })

    for i in range(0, len(rows), BATCH_SIZE):
        supabase.table("documents").insert(rows[i:i + BATCH_SIZE]).execute()

    print(f"  [OK] {doc.rel_path} — {len(chunks)} chunk inseriti", flush=True)
    return len(chunks)


# ---------------------------------------------------------------------------
# Orchestratore principale
# ---------------------------------------------------------------------------
def sync_and_index() -> None:
    print(f"\nScansione root: {DOCS_ROOT_FOLDER}", flush=True)
    disk_docs  = scan_documents(DOCS_ROOT_FOLDER)
    disk_index = {d.rel_path: d for d in disk_docs}
    db_registry = get_registry()

    # 1. Rimuovi dal DB i file non piu presenti su disco
    for rel_path in list(db_registry.keys()):
        if rel_path not in disk_index:
            print(f"  [FILE RIMOSSO DAL DISCO] {rel_path}", flush=True)
            remove_from_db(rel_path)

    # 2. Individua file nuovi o modificati
    to_index: list[DocumentFile] = []
    for doc in disk_docs:
        db_hash = db_registry.get(doc.rel_path)
        if db_hash is None:
            print(f"  [NUOVO] {doc.rel_path}", flush=True)
            to_index.append(doc)
        elif db_hash != doc.file_hash:
            print(f"  [MODIFICATO] {doc.rel_path}", flush=True)
            remove_from_db(doc.rel_path)
            to_index.append(doc)
        else:
            print(f"  [OK — invariato] {doc.rel_path}", flush=True)

    print(f"\nFile da indicizzare: {len(to_index)} | Invariati: {len(disk_docs) - len(to_index)}", flush=True)

    if not to_index:
        print("Nessun file da reindicizzare. Sync completato.", flush=True)
        return

    # 3. Indicizza i file nuovi o modificati
    total_chunks = 0
    for i, doc in enumerate(to_index, 1):
        print(f"\n[{i}/{len(to_index)}] Indicizzazione: {doc.rel_path}", flush=True)
        chunks = index_document(doc)
        if chunks > 0:
            upsert_registry(doc)
        total_chunks += chunks
        time.sleep(0.3)   # evita rate limit API Gemini

    print(f"\nSync completato. {len(to_index)} file processati, {total_chunks} chunk totali inseriti.", flush=True)


if __name__ == "__main__":
    sync_and_index()
