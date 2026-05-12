import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from services.rag import index_pdf, index_all_pdfs, list_indexed_volumes, debug_index_status, PDF_DIR

router = APIRouter()

@router.get("/")
def get_documents():
    return list_indexed_volumes()

@router.get("/debug")
def debug_documents():
    return debug_index_status()

@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo file PDF accettati.")
    dest = PDF_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        chunks = index_pdf(dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Errore: {str(e)}")
    return {"message": "PDF indicizzato.", "filename": file.filename, "chunks": chunks}

@router.post("/reindex")
def reindex_all():
    results = index_all_pdfs()
    return {"message": "Re-indicizzazione completata.", "files": results, "total_chunks": sum(results.values())}

@router.delete("/{filename}")
def delete_document(filename: str):
    from supabase import create_client
    import os

    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    supabase.table("documents").delete().eq("filename", filename).execute()

    pdf_path = PDF_DIR / filename
    if pdf_path.exists():
        pdf_path.unlink()

    return {"message": f"{filename} rimosso."}
