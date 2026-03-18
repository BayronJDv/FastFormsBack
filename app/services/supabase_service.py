import random
import string
from typing import Optional

from app.core.config import supabase
from app.schemas.survey import SurveyCreate


def _generate_unique_code(length: int = 5) -> str:
    """Genera un código alfanumérico en mayúsculas (ej: A7X9K)."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def create_survey(payload: SurveyCreate, creator_id: str) -> dict:
    """
    Inserta la encuesta y sus preguntas en Supabase dentro de una operación
    atómica manual (insert survey → insert questions).

    Retorna el registro completo de la encuesta con sus preguntas.
    Lanza una excepción si alguna operación falla.
    """

    # 1. Generar código único (reintenta si ya existe)
    unique_code = _get_available_code()

    # 2. Insertar la encuesta
    survey_data = {
        "creator_id": creator_id,
        "title": payload.title,
        "status": "draft",
        "unique_code": unique_code,
    }

    survey_result = supabase.table("surveys").insert(survey_data).execute()

    if not survey_result.data:
        raise RuntimeError("Error al guardar la encuesta en la base de datos.")

    survey = survey_result.data[0]
    survey_id = survey["id"]

    # 3. Insertar las preguntas vinculadas a la encuesta
    questions_data = [
        {
            "survey_id": survey_id,
            "content": q.content,
            "question_type": q.question_type.value,
            "options": q.options,
            "position": q.position,
        }
        for q in payload.questions
    ]

    questions_result = supabase.table("questions").insert(questions_data).execute()

    if not questions_result.data:
        # Rollback manual: eliminar la encuesta recién creada
        supabase.table("surveys").delete().eq("id", survey_id).execute()
        raise RuntimeError("Error al guardar las preguntas. La encuesta fue revertida.")

    survey["questions"] = questions_result.data
    return survey


def _get_available_code(max_attempts: int = 10) -> str:
    """Genera un código que no exista todavía en la tabla surveys."""
    for _ in range(max_attempts):
        code = _generate_unique_code()
        existing = (
            supabase.table("surveys").select("id").eq("unique_code", code).execute()
        )
        if not existing.data:
            return code
    raise RuntimeError(
        "No se pudo generar un código único después de varios intentos."
    )


def get_survey_by_code(code: str) -> Optional[dict]:
    """Retorna la encuesta (con preguntas) a partir del código único."""
    result = (
        supabase.table("surveys")
        .select("*, questions(*)")
        .eq("unique_code", code.upper())
        .execute()
    )
    return result.data[0] if result.data else None