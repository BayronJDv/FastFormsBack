"""
Tests para las 3 tareas asignadas:
  1. Validaciones: encuestas sin preguntas, preguntas sin enunciado/opciones
  2. Endpoint POST /api/v1/surveys/ — recibe y guarda en Supabase
  3. (Validaciones cubren también el caso de preguntas sin opciones/enunciado)
"""

import sys
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Mock de Supabase antes de importar la app (solo para tests unitarios)
_mock_supabase = MagicMock()
sys.modules.setdefault("supabase", MagicMock(create_client=lambda url, key: _mock_supabase))

from app.main import app

client = TestClient(app)

# ─────────────────────────────────────────────
# Payload base válido (reutilizable en los tests)
# ─────────────────────────────────────────────
SURVEY_VALIDA = {
    "title": "Encuesta de prueba",
    "questions": [
        {
            "content": "¿Cuál es tu color favorito?",
            "question_type": "open",
            "options": None,
            "position": 1,
        },
        {
            "content": "¿Qué lenguaje prefieres?",
            "question_type": "multiple_choice",
            "options": ["Python", "JavaScript", "Go"],
            "position": 2,
        },
        {
            "content": "¿Usarías esta app de nuevo?",
            "question_type": "yes_no",
            "options": None,
            "position": 3,
        },
    ],
}

# ─────────────────────────────────────────────
# Mock de Supabase para no depender de la DB real
# ─────────────────────────────────────────────
def mock_supabase_exitoso():
    """Simula que Supabase guarda correctamente."""
    survey_guardada = {
        "id": "uuid-survey-001",
        "creator_id": "temp-creator-id",
        "title": "Encuesta de prueba",
        "status": "draft",
        "unique_code": "A7X9K",
        "created_at": "2025-01-01T00:00:00",
        "closed_at": None,
        "questions": [
            {
                "id": "uuid-q-001",
                "survey_id": "uuid-survey-001",
                "content": "¿Cuál es tu color favorito?",
                "question_type": "open",
                "options": None,
                "position": 1,
            },
            {
                "id": "uuid-q-002",
                "survey_id": "uuid-survey-001",
                "content": "¿Qué lenguaje prefieres?",
                "question_type": "multiple_choice",
                "options": ["Python", "JavaScript", "Go"],
                "position": 2,
            },
            {
                "id": "uuid-q-003",
                "survey_id": "uuid-survey-001",
                "content": "¿Usarías esta app de nuevo?",
                "question_type": "yes_no",
                "options": None,
                "position": 3,
            },
        ],
    }
    mock = MagicMock()
    mock.return_value = survey_guardada
    return mock


# ══════════════════════════════════════════════
# TAREA 1 — Validación: encuesta sin preguntas
# ══════════════════════════════════════════════
class TestValidacionEncuesta:

    def test_encuesta_sin_preguntas_retorna_422(self):
        payload = {**SURVEY_VALIDA, "questions": []}
        response = client.post("/api/v1/surveys/", json=payload)
        assert response.status_code == 422
        errores = response.json()["detail"]
        mensajes = [e["msg"] for e in errores]
        assert any("al menos 1 pregunta" in m for m in mensajes)

    def test_encuesta_sin_titulo_retorna_422(self):
        payload = {**SURVEY_VALIDA, "title": "   "}
        response = client.post("/api/v1/surveys/", json=payload)
        assert response.status_code == 422

    def test_encuesta_con_mas_de_12_preguntas_retorna_422(self):
        pregunta_base = {
            "content": "Pregunta genérica",
            "question_type": "open",
            "options": None,
        }
        preguntas = [{**pregunta_base, "position": i} for i in range(1, 14)]  # 13 preguntas
        payload = {**SURVEY_VALIDA, "questions": preguntas}
        response = client.post("/api/v1/surveys/", json=payload)
        assert response.status_code == 422
        errores = response.json()["detail"]
        mensajes = [e["msg"] for e in errores]
        assert any("12 preguntas" in m for m in mensajes)

    def test_encuesta_con_posiciones_duplicadas_retorna_422(self):
        payload = {
            **SURVEY_VALIDA,
            "questions": [
                {"content": "Pregunta A", "question_type": "open", "options": None, "position": 1},
                {"content": "Pregunta B", "question_type": "open", "options": None, "position": 1},
            ],
        }
        response = client.post("/api/v1/surveys/", json=payload)
        assert response.status_code == 422


# ══════════════════════════════════════════════
# TAREA 2 — Validación: preguntas sin enunciado u opciones
# ══════════════════════════════════════════════
class TestValidacionPreguntas:

    def test_pregunta_sin_enunciado_retorna_422(self):
        preguntas = [{"content": "   ", "question_type": "open", "options": None, "position": 1}]
        payload = {**SURVEY_VALIDA, "questions": preguntas}
        response = client.post("/api/v1/surveys/", json=payload)
        assert response.status_code == 422
        errores = response.json()["detail"]
        mensajes = [e["msg"] for e in errores]
        assert any("enunciado" in m for m in mensajes)

    def test_multiple_choice_sin_opciones_retorna_422(self):
        preguntas = [
            {"content": "¿Cuál prefieres?", "question_type": "multiple_choice", "options": None, "position": 1}
        ]
        payload = {**SURVEY_VALIDA, "questions": preguntas}
        response = client.post("/api/v1/surveys/", json=payload)
        assert response.status_code == 422
        errores = response.json()["detail"]
        mensajes = [e["msg"] for e in errores]
        assert any("opción múltiple" in m for m in mensajes)

    def test_multiple_choice_con_una_sola_opcion_retorna_422(self):
        preguntas = [
            {"content": "¿Cuál prefieres?", "question_type": "multiple_choice", "options": ["Solo una"], "position": 1}
        ]
        payload = {**SURVEY_VALIDA, "questions": preguntas}
        response = client.post("/api/v1/surveys/", json=payload)
        assert response.status_code == 422

    def test_multiple_choice_con_opcion_vacia_retorna_422(self):
        preguntas = [
            {"content": "¿Cuál prefieres?", "question_type": "multiple_choice", "options": ["Python", ""], "position": 1}
        ]
        payload = {**SURVEY_VALIDA, "questions": preguntas}
        response = client.post("/api/v1/surveys/", json=payload)
        assert response.status_code == 422

    def test_pregunta_open_con_opciones_retorna_422(self):
        preguntas = [
            {"content": "Escribe algo", "question_type": "open", "options": ["no debería estar"], "position": 1}
        ]
        payload = {**SURVEY_VALIDA, "questions": preguntas}
        response = client.post("/api/v1/surveys/", json=payload)
        assert response.status_code == 422

    def test_yes_no_con_opciones_retorna_422(self):
        preguntas = [
            {"content": "¿Te gustó?", "question_type": "yes_no", "options": ["Sí", "No"], "position": 1}
        ]
        payload = {**SURVEY_VALIDA, "questions": preguntas}
        response = client.post("/api/v1/surveys/", json=payload)
        assert response.status_code == 422


# ══════════════════════════════════════════════
# TAREA 3 — Endpoint: guarda en Supabase correctamente
# ══════════════════════════════════════════════
class TestEndpointCrearEncuesta:

    @patch("app.api.routes.surveys.supabase_service.create_survey", new_callable=mock_supabase_exitoso)
    def test_encuesta_valida_retorna_201(self, mock_create):
        response = client.post("/api/v1/surveys/", json=SURVEY_VALIDA)
        assert response.status_code == 201

    @patch("app.api.routes.surveys.supabase_service.create_survey", new_callable=mock_supabase_exitoso)
    def test_respuesta_incluye_codigo_unico(self, mock_create):
        response = client.post("/api/v1/surveys/", json=SURVEY_VALIDA)
        data = response.json()
        assert "unique_code" in data
        assert len(data["unique_code"]) == 5

    @patch("app.api.routes.surveys.supabase_service.create_survey", new_callable=mock_supabase_exitoso)
    def test_respuesta_incluye_preguntas(self, mock_create):
        response = client.post("/api/v1/surveys/", json=SURVEY_VALIDA)
        data = response.json()
        assert "questions" in data
        assert len(data["questions"]) == 3

    @patch("app.api.routes.surveys.supabase_service.create_survey", new_callable=mock_supabase_exitoso)
    def test_estado_inicial_es_draft(self, mock_create):
        response = client.post("/api/v1/surveys/", json=SURVEY_VALIDA)
        data = response.json()
        assert data["status"] == "draft"

    @patch(
        "app.api.routes.surveys.supabase_service.create_survey",
        side_effect=RuntimeError("Error al guardar la encuesta en la base de datos."),
    )
    def test_error_de_supabase_retorna_500(self, mock_create):
        response = client.post("/api/v1/surveys/", json=SURVEY_VALIDA)
        assert response.status_code == 500
        assert "Error al guardar" in response.json()["detail"]