from fastapi import APIRouter, HTTPException
from app.core.config import supabase
# ESTA ES LA LÍNEA QUE TE FALTA:
from app.schemas.question import QuestionCreate 

router = APIRouter(prefix="/surveys/{survey_id}/questions", tags=["questions"])

@router.post("/")
async def add_question(survey_id: int, question: QuestionCreate):
    
    # Validación de límite de 12
    existing = supabase.table("questions").select("id", count="exact").eq("survey_id", survey_id).execute()
    if existing.count >= 12:
        raise HTTPException(status_code=400, detail="Máximo 12 preguntas por encuesta.")

    # Inserción
    res = supabase.table("questions").insert({
        "survey_id": survey_id,
        "content": question.content,
        "question_type": question.question_type,
        "options": question.options
    }).execute()
    
    return res.data