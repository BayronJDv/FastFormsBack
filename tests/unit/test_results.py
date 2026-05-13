"""
Tests US-10 — Resultados: lógica de agregación y endpoint GET /surveys/{id}/results.
"""

import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# Mock de Supabase antes de importar la app (solo para tests unitarios)
_mock_supabase = MagicMock()
sys.modules.setdefault("supabase", MagicMock(create_client=lambda url, key: _mock_supabase))

from app.main import app
from app.services import supabase_service

client = TestClient(app)
_OWNER = "832071cb-5f6a-4d2d-8c0c-901cd13e78ad"


class TestAgregacionOpciones:

    def test_porcentajes_por_opcion(self):
        options, total = supabase_service._aggregate_choice(
            ["Sí", "Sí", "Sí", "No"], ["Sí", "No"]
        )
        assert total == 4
        by_option = {o["option"]: o for o in options}
        assert by_option["Sí"]["count"] == 3
        assert by_option["Sí"]["percentage"] == 75.0
        assert by_option["No"]["count"] == 1
        assert by_option["No"]["percentage"] == 25.0

    def test_opcion_sin_respuestas_es_cero(self):
        options, total = supabase_service._aggregate_choice([], ["A", "B", "C"])
        assert total == 0
        assert all(o["count"] == 0 and o["percentage"] == 0.0 for o in options)
        assert {o["option"] for o in options} == {"A", "B", "C"}

    def test_respuestas_fuera_de_opciones_declaradas_se_incluyen(self):
        options, total = supabase_service._aggregate_choice(
            ["A", "A", "Otro"], ["A", "B"]
        )
        assert total == 3
        by_option = {o["option"]: o["count"] for o in options}
        assert by_option["A"] == 2
        assert by_option["B"] == 0
        assert by_option["Otro"] == 1


class TestGetSurveyResultsServicio:

    def _fake_supabase(self, questions, response_ids, answers):
        fake = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "questions":
                (
                    tbl.select.return_value.eq.return_value.order.return_value.execute.return_value.data
                ) = questions
            elif name == "responses":
                (
                    tbl.select.return_value.eq.return_value.execute.return_value.data
                ) = [{"id": rid} for rid in response_ids]
            elif name == "answers":
                (
                    tbl.select.return_value.in_.return_value.execute.return_value.data
                ) = answers
            return tbl

        fake.table.side_effect = table
        return fake

    def test_agrega_respuestas_por_tipo_de_pregunta(self):
        survey = {"id": 5, "title": "Encuesta", "status": "active", "creator_id": _OWNER}
        questions = [
            {"id": 1, "survey_id": 5, "content": "Comentarios", "question_type": "open", "options": None, "position": 1},
            {"id": 2, "survey_id": 5, "content": "¿Recomendarías?", "question_type": "yes_no", "options": None, "position": 2},
            {"id": 3, "survey_id": 5, "content": "Color favorito", "question_type": "multiple_choice", "options": ["Rojo", "Azul"], "position": 3},
        ]
        answers = [
            {"question_id": 1, "answer_text": "Todo bien"},
            {"question_id": 1, "answer_text": "Mejorar soporte"},
            {"question_id": 2, "answer_text": "Sí"},
            {"question_id": 2, "answer_text": "No"},
            {"question_id": 2, "answer_text": "Sí"},
            {"question_id": 3, "answer_text": "Rojo"},
            {"question_id": 3, "answer_text": "Rojo"},
            {"question_id": 3, "answer_text": "Azul"},
        ]
        fake = self._fake_supabase(questions, [10, 11, 12], answers)
        with patch.object(supabase_service, "supabase", fake):
            result = supabase_service.get_survey_results(survey)

        assert result["survey_id"] == 5
        assert result["total_responses"] == 3
        q_by_id = {q["question_id"]: q for q in result["questions"]}
        assert q_by_id[1]["texts"] == ["Todo bien", "Mejorar soporte"]
        assert q_by_id[1]["total_answers"] == 2
        yn = {o["option"]: o for o in q_by_id[2]["options"]}
        assert yn["Sí"]["count"] == 2
        assert round(yn["Sí"]["percentage"]) == 67
        assert yn["No"]["count"] == 1
        mc = {o["option"]: o for o in q_by_id[3]["options"]}
        assert mc["Rojo"]["count"] == 2
        assert mc["Azul"]["count"] == 1

    def test_sin_respuestas_devuelve_estructura_vacia(self):
        survey = {"id": 9, "title": "Vacía", "status": "active", "creator_id": _OWNER}
        questions = [
            {"id": 1, "survey_id": 9, "content": "Abierta", "question_type": "open", "options": None, "position": 1},
            {"id": 2, "survey_id": 9, "content": "Sí/No", "question_type": "yes_no", "options": None, "position": 2},
        ]
        fake = self._fake_supabase(questions, [], [])
        with patch.object(supabase_service, "supabase", fake):
            result = supabase_service.get_survey_results(survey)

        assert result["total_responses"] == 0
        q_by_id = {q["question_id"]: q for q in result["questions"]}
        assert q_by_id[1]["texts"] == []
        assert q_by_id[1]["total_answers"] == 0
        assert all(o["count"] == 0 for o in q_by_id[2]["options"])


class TestEndpointResultados:

    @patch("app.api.routes.surveys.supabase_service.get_survey", return_value=None)
    def test_encuesta_inexistente_retorna_404(self, _mock_get):
        response = client.get("/api/v1/surveys/999/results")
        assert response.status_code == 404

    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "title": "T", "status": "active", "creator_id": "otro-usuario"},
    )
    def test_usuario_no_creador_retorna_403(self, _mock_get):
        response = client.get("/api/v1/surveys/1/results")
        assert response.status_code == 403

    @patch("app.api.routes.surveys.supabase_service.get_survey_results")
    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "title": "T", "status": "active", "creator_id": _OWNER},
    )
    def test_creador_obtiene_resultados_200(self, _mock_get, mock_results):
        mock_results.return_value = {
            "survey_id": 1,
            "title": "T",
            "status": "active",
            "total_responses": 2,
            "questions": [
                {
                    "question_id": 1,
                    "content": "Abierta",
                    "question_type": "open",
                    "total_answers": 2,
                    "texts": ["hola", "mundo"],
                },
                {
                    "question_id": 2,
                    "content": "Sí/No",
                    "question_type": "yes_no",
                    "total_answers": 2,
                    "options": [
                        {"option": "Sí", "count": 1, "percentage": 50.0},
                        {"option": "No", "count": 1, "percentage": 50.0},
                    ],
                },
            ],
        }
        response = client.get("/api/v1/surveys/1/results")
        assert response.status_code == 200
        data = response.json()
        assert data["total_responses"] == 2
        assert data["questions"][0]["texts"] == ["hola", "mundo"]
        assert data["questions"][1]["options"][0]["option"] == "Sí"


class TestEndpointCerrarEncuesta:

    @patch("app.api.routes.surveys.supabase_service.get_survey", return_value=None)
    def test_cerrar_encuesta_inexistente_retorna_404(self, _mock_get):
        response = client.patch("/api/v1/surveys/999/close")
        assert response.status_code == 404

    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "status": "active", "creator_id": "otro-usuario"},
    )
    def test_cerrar_encuesta_ajena_retorna_403(self, _mock_get):
        response = client.patch("/api/v1/surveys/1/close")
        assert response.status_code == 403

    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "status": "draft", "creator_id": _OWNER},
    )
    def test_cerrar_encuesta_no_activa_retorna_409(self, _mock_get):
        response = client.patch("/api/v1/surveys/1/close")
        assert response.status_code == 409

    @patch("app.api.routes.surveys.supabase_service.close_survey")
    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "status": "active", "creator_id": _OWNER},
    )
    def test_cerrar_encuesta_activa_retorna_200(self, _mock_get, mock_close):
        mock_close.return_value = {
            "id": 1,
            "creator_id": _OWNER,
            "title": "Encuesta",
            "status": "closed",
            "unique_code": "ABCDE",
            "created_at": "2025-01-01T00:00:00",
            "closed_at": "2025-02-01T00:00:00",
        }
        response = client.patch("/api/v1/surveys/1/close")
        assert response.status_code == 200
        assert response.json()["status"] == "closed"
        mock_close.assert_called_once_with(1)
