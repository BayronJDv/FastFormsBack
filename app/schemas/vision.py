"""US-Vision — Schemas del generador de encuestas desde imágenes con Gemini Vision."""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional

from schemas.question import QuestionType


class VisionRequest(BaseModel):
    """Entrada del endpoint POST /api/v1/surveys/generate-from-image."""

    language: str = Field(
        default="es",
        min_length=2,
        max_length=8,
        description='Código ISO del idioma de salida (ej. "es", "en", "pt-BR").',
    )
    context: str = Field(
        default="",
        max_length=500,
        description="Contexto opcional del usuario para orientar la encuesta.",
    )
    num_questions: int = Field(
        default=5,
        ge=1,
        le=12,
        description="Número de preguntas a generar (1-12).",
    )

    @field_validator("language")
    @classmethod
    def language_normalizado(cls, v: str) -> str:
        return v.strip().lower()


class VisionQuestion(BaseModel):
    """Pregunta generada por Gemini Vision desde una imagen."""

    content: str
    question_type: QuestionType
    options: Optional[List[str]] = None
    position: int

    @field_validator("content")
    @classmethod
    def content_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El enunciado de la pregunta no puede estar vacío.")
        return v.strip()

    @field_validator("options")
    @classmethod
    def opciones_no_vacias(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            if any(not opt or not opt.strip() for opt in v):
                raise ValueError("Ninguna opción puede estar vacía.")
        return v

    @model_validator(mode="after")
    def validar_opciones_segun_tipo(self) -> "VisionQuestion":
        if self.question_type == QuestionType.MULTIPLE_CHOICE:
            if not self.options or len(self.options) < 2:
                raise ValueError(
                    "Las preguntas de opción múltiple deben tener al menos 2 opciones."
                )
        elif self.question_type in (QuestionType.OPEN, QuestionType.YES_NO):
            if self.options:
                raise ValueError(
                    f"Las preguntas de tipo '{self.question_type}' no deben incluir opciones."
                )
        return self


class VisionResponse(BaseModel):
    """Salida que el frontend inyecta en el formulario de creación."""

    title: str
    description: str = ""
    questions: List[VisionQuestion]

    @field_validator("title")
    @classmethod
    def title_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El título de la encuesta no puede estar vacío.")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_strip(cls, v: str) -> str:
        return (v or "").strip()
