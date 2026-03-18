from pydantic import BaseModel, field_validator, model_validator
from typing import List, Optional
from enum import Enum
from datetime import datetime

from app.schemas.question import QuestionCreate, QuestionResponse


class SurveyStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


class SurveyCreate(BaseModel):
    title: str
    questions: List[QuestionCreate]

    # Para que una encuesta debe tener un titulo no vacio
    @field_validator("title")
    @classmethod
    def titulo_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El título de la encuesta no puede estar vacío.")
        return v.strip()

    # Para que una encuesta sea valida debe tener al menos 1 pregunta
    @field_validator("questions")
    @classmethod
    def validar_preguntas(cls, v: List[QuestionCreate]) -> List[QuestionCreate]:
        if not v:
            raise ValueError("La encuesta debe tener al menos 1 pregunta.")
        if len(v) > 12:
            raise ValueError("La encuesta no puede tener más de 12 preguntas.")
        return v

    # Las posiciones de cada pregunta deben ser unicas dentro de la encuesta
    
    @model_validator(mode="after")
    def validar_posiciones(self) -> "SurveyCreate":
        positions = [q.position for q in self.questions]
        if len(positions) != len(set(positions)):
            raise ValueError("Dos o más preguntas tienen la misma posición.")
        return self


class SurveyResponse(BaseModel):
    id: int
    creator_id: str
    title: str
    status: SurveyStatus
    unique_code: str
    created_at: datetime
    closed_at: Optional[datetime]
    questions: Optional[List[QuestionResponse]] = None