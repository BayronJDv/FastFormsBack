from pydantic import BaseModel
from typing import List, Optional

from schemas.question import QuestionType
from schemas.survey import SurveyStatus


class OptionResult(BaseModel):
    option: str
    count: int
    percentage: float


class TextAnswer(BaseModel):
    """US-17 / US-18 — Texto de respuesta abierta + origen y idioma."""

    text: str
    is_voice: bool = False
    language: Optional[str] = None


class QuestionResult(BaseModel):
    question_id: int
    content: str
    question_type: QuestionType
    total_answers: int
    # Para preguntas de opción (multiple_choice / yes_no)
    options: Optional[List[OptionResult]] = None
    # Para preguntas abiertas (open) — lista plana, retrocompatible.
    texts: Optional[List[str]] = None
    # US-17 — Variante enriquecida con flag de voz, usada por el dashboard.
    text_entries: Optional[List[TextAnswer]] = None


class SurveyResults(BaseModel):
    survey_id: int
    title: str
    status: SurveyStatus
    total_responses: int
    questions: List[QuestionResult]
