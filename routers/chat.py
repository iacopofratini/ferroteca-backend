from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.rag import ask

router = APIRouter()


class QuestionRequest(BaseModel):
    question: str


@router.post("/ask")
def ask_question(req: QuestionRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="La domanda non può essere vuota.")
    return ask(req.question)
