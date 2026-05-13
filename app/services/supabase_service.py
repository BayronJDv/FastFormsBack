import random
import string
from typing import Optional

from core.config import supabase
from schemas.survey import SurveyCreate


def _generate_unique_code(length: int = 5) -> str:
    """Genera un codigo alfanumerico en mayusculas (ej: A7X9K)."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def create_survey(payload: SurveyCreate, creator_id: str) -> dict:
    """
    Inserta la encuesta y sus preguntas en Supabase dentro de una operacion
    atomica manual (insert survey -> insert questions).

    Retorna el registro completo de la encuesta con sus preguntas.
    Lanza una excepcion si alguna operacion falla.
    """

    # 1. Generar codigo unico (reintenta si ya existe)
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
        # Rollback manual: eliminar la encuesta recien creada
        supabase.table("surveys").delete().eq("id", survey_id).execute()
        raise RuntimeError("Error al guardar las preguntas. La encuesta fue revertida.")

    survey["questions"] = questions_result.data
    return survey


def _get_available_code(max_attempts: int = 10) -> str:
    """Genera un codigo que no exista todavia en la tabla surveys."""
    for _ in range(max_attempts):
        code = _generate_unique_code()
        existing = (
            supabase.table("surveys").select("id").eq("unique_code", code).execute()
        )
        if not existing.data:
            return code
    raise RuntimeError(
        "No se pudo generar un codigo unico despues de varios intentos."
    )


def get_survey_by_code(code: str) -> Optional[dict]:
    """Retorna la encuesta (con preguntas) a partir del codigo unico."""
    result = (
        supabase.table("surveys")
        .select("*, questions(*)")
        .eq("unique_code", code.upper())
        .execute()
    )
    return result.data[0] if result.data else None


# ---------------------------------------------------------------------------
# Borradores
# ---------------------------------------------------------------------------

def _replace_questions(survey_id: int, questions) -> list:
    """Elimina y reinserta todas las preguntas asociadas a un borrador.

    Lo usamos al guardar/actualizar un borrador para que el snapshot persistido
    refleje exactamente lo que el usuario ve en pantalla al momento de guardar.
    """
    supabase.table("questions").delete().eq("survey_id", survey_id).execute()
    if not questions:
        return []
    questions_data = [
        {
            "survey_id": survey_id,
            "content": (q.content or "").strip(),
            "question_type": q.question_type.value,
            "options": q.options,
            "position": q.position,
        }
        for q in questions
    ]
    result = supabase.table("questions").insert(questions_data).execute()
    return result.data or []


def create_draft(payload, creator_id: str) -> dict:
    """Crea un borrador (status='draft') con sus preguntas (pueden estar incompletas)."""
    unique_code = _get_available_code()
    survey_data = {
        "creator_id": creator_id,
        "title": payload.title or "(sin titulo)",
        "status": "draft",
        "unique_code": unique_code,
    }
    survey_result = supabase.table("surveys").insert(survey_data).execute()
    if not survey_result.data:
        raise RuntimeError("Error al guardar el borrador en la base de datos.")
    survey = survey_result.data[0]
    survey["questions"] = _replace_questions(survey["id"], payload.questions)
    return survey


def update_draft(survey_id: int, payload, creator_id: str) -> dict:
    """Actualiza un borrador existente y sustituye sus preguntas."""
    existing = (
        supabase.table("surveys")
        .select("*")
        .eq("id", survey_id)
        .eq("creator_id", creator_id)
        .execute()
    )
    if not existing.data:
        raise LookupError("Borrador no encontrado.")
    if existing.data[0]["status"] != "draft":
        raise PermissionError("Solo se pueden editar encuestas en estado borrador.")

    update_data = {"title": payload.title or "(sin titulo)"}
    updated = (
        supabase.table("surveys")
        .update(update_data)
        .eq("id", survey_id)
        .execute()
    )
    survey = updated.data[0] if updated.data else existing.data[0]
    survey["questions"] = _replace_questions(survey_id, payload.questions)
    return survey


def get_survey_by_id(survey_id: int) -> Optional[dict]:
    """Retorna una encuesta (con preguntas) por su id."""
    result = (
        supabase.table("surveys")
        .select("*, questions(*)")
        .eq("id", survey_id)
        .execute()
    )
    return result.data[0] if result.data else None


def list_drafts(creator_id: str) -> list:
    """Lista los borradores del usuario, mas recientes primero."""
    result = (
        supabase.table("surveys")
        .select("*, questions(*)")
        .eq("creator_id", creator_id)
        .eq("status", "draft")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []
