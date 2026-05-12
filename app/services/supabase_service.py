import random
import string
from typing import Optional

from core.config import supabase
from schemas.survey import SurveyCreate


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


def get_survey(survey_id: int) -> Optional[dict]:
    """Retorna la encuesta (sin preguntas) a partir de su id, o None si no existe."""
    result = supabase.table("surveys").select("*").eq("id", survey_id).execute()
    return result.data[0] if result.data else None


def list_surveys_by_creator(creator_id: str) -> list:
    """US-02 — Retorna todas las encuestas creadas por el usuario indicado."""
    result = (
        supabase.table("surveys")
        .select("*")
        .eq("creator_id", creator_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def set_survey_status(survey_id: int, new_status: str) -> dict:
    """Cambia el estado de una encuesta y retorna el registro actualizado."""
    result = (
        supabase.table("surveys")
        .update({"status": new_status})
        .eq("id", survey_id)
        .execute()
    )
    if not result.data:
        raise RuntimeError("No se pudo actualizar el estado de la encuesta.")
    return result.data[0]


def create_response(payload) -> dict:
    """
    US-08 — Persiste una respuesta (tabla responses) y sus answers asociadas.

    Operación atómica manual: insert response → insert answers (con rollback).
    Lanza:
      - LookupError si la encuesta no existe.
      - ValueError si la encuesta no está activa.
      - RuntimeError ante un fallo de la base de datos.
    """
    survey = get_survey(payload.survey_id)
    if survey is None:
        raise LookupError("La encuesta indicada no existe.")
    if survey.get("status") != "active":
        raise ValueError("La encuesta no está activa para recibir respuestas.")

    response_result = (
        supabase.table("responses").insert({"survey_id": payload.survey_id}).execute()
    )
    if not response_result.data:
        raise RuntimeError("Error al guardar la respuesta en la base de datos.")

    response = response_result.data[0]
    response_id = response["id"]

    answers_data = [
        {
            "response_id": response_id,
            "question_id": answer.question_id,
            "answer_text": answer.answer_text,
        }
        for answer in payload.answers
    ]

    answers_result = supabase.table("answers").insert(answers_data).execute()
    if not answers_result.data:
        # Rollback manual
        supabase.table("responses").delete().eq("id", response_id).execute()
        raise RuntimeError(
            "Error al guardar las respuestas. La operación fue revertida."
        )

    response["answers"] = answers_result.data
    return response
