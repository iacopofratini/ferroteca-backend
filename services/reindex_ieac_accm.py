import os
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from supabase import create_client, Client

from services import llm_provider

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = (BASE_DIR / ".." / "data" / "pdfs").resolve()
PDF_DIR.mkdir(parents=True, exist_ok=True)


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def reindex_pdf(pdf_name: str, batch_size: int = 10, sleep_between_batches: float = 1.2, embed_pause: float = 0.8) -> int:
    pdf_path = PDF_DIR / pdf_name
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF non trovato: {pdf_path}")

    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    for page in pages:
        page.metadata["volume"] = pdf_path.stem
        page.metadata["filename"] = pdf_path.name

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_documents(pages)

    supabase = get_supabase()
    print(f"Skipping delete for {pdf_path.name}")

    rows = []
    pending_texts = []
    pending_chunks = []

    def flush_embeddings():
        nonlocal rows, pending_texts, pending_chunks
        if not pending_texts:
            return
        embs = llm_provider.embed(pending_texts)
        for idx, emb in enumerate(embs):
            c = pending_chunks[idx]
            rows.append({
                "content": c.page_content,
                "embedding": emb,
                "filename": pdf_path.name,
                "volume": pdf_path.stem,
                "page": c.metadata.get("page", 0),
            })
        pending_texts = []
        pending_chunks = []
        time.sleep(embed_pause)

    for c in chunks:
        pending_texts.append(c.page_content)
        pending_chunks.append(c)
        if len(pending_texts) >= 5:
            flush_embeddings()

    flush_embeddings()

    for i in range(0, len(rows), batch_size):
        while True:
            try:
                supabase.table("documents").insert(rows[i:i + batch_size]).execute()
                time.sleep(sleep_between_batches)
                break
            except Exception as e:
                if "57014" in str(e):
                    print(f"Timeout on insert batch {i}, retrying in 5s...")
                    time.sleep(5)
                    continue
                raise

    return len(chunks)


if __name__ == "__main__":
    target = "IEAC ACCM.pdf"
    print(f"Reindexing {target}...")
    n = reindex_pdf(target)
    print(f"OK {target}: {n} chunks")