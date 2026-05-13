from pydantic import BaseModel, field_validator
from typing import List, Optional

from schemas.question import QuestionType


class DraftQuestionPayload(BaseModel):
    """Pregunta dentro de un borrador.

    Schema relajado: permite enunciado vacio y opciones incompletas
    porque un borrador representa trabajo en curso que el usuario quiere
    poder retomar mas tarde.
    """

    content: Optional[str] = ""
    question_type: QuestionType
    options: Optional[List[str]] = None
    position: int


class DraftPayload(BaseModel):
    """Crear o actualizar un borrador.

    Acepta titulo vacio y 0 a 12 preguntas para permitir guardado parcial.
    """

    title: Optional[str] = ""
    questions: List[DraftQuestionPayload] = []

    @field_validator("title")
    @classmethod
    def normalizar_titulo(cls, v: Optional[str]) -> str:
        return (v or "").strip()

    @field_validator("questions")
    @classmethod
    def validar_limite(cls, v: List[DraftQuestionPayload]) -> List[DraftQuestionPayload]:
        if len(v) > 12:
            raise ValueError("La encuesta no puede tener mas de 12 preguntas.")
        return v
