from pydantic import BaseModel, field_validator
from typing import List
from datetime import datetime


class AnswerCreate(BaseModel):
    question_id: int
    answer_text: str
    is_voice: bool = False

    @field_validator("answer_text")
    @classmethod
    def answer_no_vacia(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("La respuesta no puede estar vacía.")
        return v.strip()


class ResponseCreate(BaseModel):
    survey_id: int
    answers: List[AnswerCreate]

    @field_validator("answers")
    @classmethod
    def al_menos_una_respuesta(cls, v: List[AnswerCreate]) -> List[AnswerCreate]:
        if not v:
            raise ValueError("Debes responder al menos una pregunta.")
        return v


class AnswerResult(BaseModel):
    id: int
    response_id: int
    question_id: int
    answer_text: str
    is_voice: bool = False


class ResponseResult(BaseModel):
    id: int
    survey_id: int
    submitted_at: datetime
    answers: List[AnswerResult]
