from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from enum import Enum


class QuestionType(str, Enum):
    OPEN = "open"
    MULTIPLE_CHOICE = "multiple_choice"
    YES_NO = "yes_no"


class QuestionCreate(BaseModel):
    content: str
    question_type: QuestionType
    options: Optional[List[str]] = None
    position: int

    # Para que una pregunta sea valida no debe tener un enunciado vacio

    @field_validator("content")
    @classmethod
    def content_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El enunciado de la pregunta no puede estar vacío.")
        return v.strip()

    # Para una pregunta de opcion multiple, se debe marcar por lo menos una opcion
    @field_validator("options")
    @classmethod
    def opciones_no_vacias(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            if any(not opt or not opt.strip() for opt in v):
                raise ValueError("Ninguna opción puede estar vacía.")
        return v

    # Las preguntas de opcion multiple deben tener al menos 2 opciones, y si son de otro tipo no deben tener opciones
    @model_validator(mode="after")
    def validar_opciones_segun_tipo(self) -> "QuestionCreate":
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


class QuestionResponse(BaseModel):
    id: int
    survey_id: int
    content: str
    question_type: QuestionType
    options: Optional[List[str]]
    position: int