"""
Tests US-10 (CSV) — Exportar resultados de una encuesta a CSV.
"""

import csv
import io
import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

_mock_supabase = MagicMock()
sys.modules.setdefault("supabase", MagicMock(create_client=lambda url, key: _mock_supabase))

from app.main import app
from app.services import supabase_service

# OJO: api.deps y app.api.deps son módulos distintos en sys.modules.
# Debemos usar la misma referencia que usa el router (surveys.py).
from app.api.routes import surveys as _surveys_module

_OWNER = "832071cb-5f6a-4d2d-8c0c-901cd13e78ad"

# Override de autenticación usando la función que realmente usa el router
_original_get_user_id = _surveys_module.get_current_user_id
app.dependency_overrides[_original_get_user_id] = lambda: _OWNER

client = TestClient(app)
AUTH_HEADER = {"Authorization": "Bearer fake-token"}


class TestGetSurveyResponsesRaw:

    def _fake_supabase(self, questions, responses, answers):
        fake = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "questions":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value.data = questions
            elif name == "responses":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value.data = responses
            elif name == "answers":
                tbl.select.return_value.in_.return_value.order.return_value.execute.return_value.data = answers
            return tbl

        fake.table.side_effect = table
        return fake

    def test_responses_raw_con_datos(self):
        questions = [
            {"id": 1, "content": "Nombre", "question_type": "open", "position": 1},
            {"id": 2, "content": "Edad", "question_type": "open", "position": 2},
        ]
        responses = [
            {"id": 10, "submitted_at": "2025-01-01T12:00:00"},
            {"id": 11, "submitted_at": "2025-01-02T13:00:00"},
        ]
        answers = [
            {"response_id": 10, "question_id": 1, "answer_text": "Juan"},
            {"response_id": 10, "question_id": 2, "answer_text": "30"},
            {"response_id": 11, "question_id": 1, "answer_text": "María"},
            {"response_id": 11, "question_id": 2, "answer_text": "25"},
        ]
        fake = self._fake_supabase(questions, responses, answers)
        with patch.object(supabase_service, "supabase", fake):
            rows = supabase_service.get_survey_responses_raw(1)

        assert len(rows) == 4
        assert rows[0] == {
            "response_id": 10,
            "submitted_at": "2025-01-01T12:00:00",
            "question_position": 1,
            "question_content": "Nombre",
            "question_type": "open",
            "answer_text": "Juan",
        }

    def test_sin_respuestas_devuelve_lista_vacia(self):
        fake = self._fake_supabase([{"id": 1, "content": "Q", "question_type": "open", "position": 1}], [], [])
        with patch.object(supabase_service, "supabase", fake):
            rows = supabase_service.get_survey_responses_raw(1)
        assert rows == []

    def test_orden_correcto_por_response_y_position(self):
        questions = [
            {"id": 1, "content": "A", "question_type": "open", "position": 2},
            {"id": 2, "content": "B", "question_type": "open", "position": 1},
        ]
        responses = [
            {"id": 20, "submitted_at": "2025-01-01T00:00:00"},
            {"id": 19, "submitted_at": "2025-01-01T00:00:00"},
        ]
        answers = [
            {"response_id": 19, "question_id": 1, "answer_text": "X"},
            {"response_id": 19, "question_id": 2, "answer_text": "Y"},
            {"response_id": 20, "question_id": 1, "answer_text": "Z"},
            {"response_id": 20, "question_id": 2, "answer_text": "W"},
        ]
        fake = self._fake_supabase(questions, responses, answers)
        with patch.object(supabase_service, "supabase", fake):
            rows = supabase_service.get_survey_responses_raw(1)

        expected_order = [(19, 1), (19, 2), (20, 1), (20, 2)]
        assert [(r["response_id"], r["question_position"]) for r in rows] == expected_order


class TestEndpointCSV:

    @patch("app.api.routes.surveys.supabase_service.get_survey", return_value=None)
    def test_encuesta_inexistente_retorna_404(self, _mock_get):
        response = client.get("/api/v1/surveys/999/results/csv", headers=AUTH_HEADER)
        assert response.status_code == 404

    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "title": "T", "status": "active", "creator_id": "otro-usuario"},
    )
    def test_usuario_no_creador_retorna_403(self, _mock_get):
        response = client.get("/api/v1/surveys/1/results/csv", headers=AUTH_HEADER)
        assert response.status_code == 403

    @patch("app.api.routes.surveys.supabase_service.get_survey_responses_raw")
    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "title": "Encuesta", "status": "active", "creator_id": _OWNER},
    )
    def test_exportar_csv_con_respuestas(self, _mock_get, mock_raw):
        mock_raw.return_value = [
            {
                "response_id": 10,
                "submitted_at": "2025-01-01T12:00:00",
                "question_position": 1,
                "question_content": "Nombre",
                "question_type": "open",
                "answer_text": "Juan",
            },
            {
                "response_id": 10,
                "submitted_at": "2025-01-01T12:00:00",
                "question_position": 2,
                "question_content": "Edad",
                "question_type": "open",
                "answer_text": "30",
            },
        ]

        response = client.get("/api/v1/surveys/1/results/csv", headers=AUTH_HEADER)
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment; filename=" in response.headers["content-disposition"]
        assert "encuesta_1_resultados.csv" in response.headers["content-disposition"]

        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)
        assert rows[0] == ["ID Respuesta", "Fecha de envío", "# Pregunta", "Pregunta", "Tipo", "Respuesta"]
        assert rows[1] == ["10", "2025-01-01T12:00:00", "1", "Nombre", "open", "Juan"]
        assert rows[2] == ["10", "2025-01-01T12:00:00", "2", "Edad", "open", "30"]

    @patch("app.api.routes.surveys.supabase_service.get_survey_responses_raw", return_value=[])
    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "title": "Vacía", "status": "active", "creator_id": _OWNER},
    )
    def test_exportar_csv_sin_respuestas_solo_encabezados(self, _mock_get, mock_raw):
        response = client.get("/api/v1/surveys/1/results/csv", headers=AUTH_HEADER)
        assert response.status_code == 200

        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0] == ["ID Respuesta", "Fecha de envío", "# Pregunta", "Pregunta", "Tipo", "Respuesta"]
