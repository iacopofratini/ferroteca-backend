import os
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from services.rag import PDF_DIR, debug_index_status, index_all_pdfs, index_pdf, list_indexed_volumes

router = APIRouter()


@router.get("/")
def get_documents():
    return list_indexed_volumes()


@router.get("/debug")
def debug_documents():
    return debug_index_status()


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo file PDF accettati.")

    dest = PDF_DIR / file.filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
        chunks = index_pdf(dest)
    except HTTPException:
        raise
    except Exception as e:
        try:
            if dest.exists():
                dest.unlink()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Errore: {str(e)}")

    return {"message": "PDF indicizzato.", "filename": file.filename, "chunks": chunks}


@router.post("/reindex")
def reindex_all():
    try:
        results = index_all_pdfs()
        return {"message": "Re-indicizzazione completata.", "files": results, "total_chunks": sum(results.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore: {str(e)}")


@router.delete("/{filename}")
def delete_document(filename: str):
    from supabase import create_client

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    if not supabase_url or not supabase_key:
        raise HTTPException(status_code=500, detail="Supabase non configurato.")

    supabase = create_client(supabase_url, supabase_key)
    supabase.table("documents").delete().eq("filename", filename).execute()

    pdf_path = PDF_DIR / filename
    if pdf_path.exists():
        pdf_path.unlink()

    return {"message": f"{filename} rimosso."}
