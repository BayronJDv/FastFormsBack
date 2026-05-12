"""
Tests US-08 — Endpoint POST /api/v1/responses/

Verifican el guardado de respuestas, las validaciones de entrada y el mapeo
de errores del servicio a códigos HTTP.
"""

import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# Mock de Supabase antes de importar la app (solo para tests unitarios)
_mock_supabase = MagicMock()
sys.modules.setdefault("supabase", MagicMock(create_client=lambda url, key: _mock_supabase))

from app.main import app

client = TestClient(app)

PAYLOAD_VALIDO = {
    "survey_id": 10,
    "answers": [
        {"question_id": 1, "answer_text": "Mi respuesta abierta"},
        {"question_id": 2, "answer_text": "Excelente"},
        {"question_id": 3, "answer_text": "Sí"},
    ],
}

RESPONSE_GUARDADA = {
    "id": 99,
    "survey_id": 10,
    "submitted_at": "2025-01-01T00:00:00",
    "answers": [
        {"id": 1, "response_id": 99, "question_id": 1, "answer_text": "Mi respuesta abierta"},
        {"id": 2, "response_id": 99, "question_id": 2, "answer_text": "Excelente"},
        {"id": 3, "response_id": 99, "question_id": 3, "answer_text": "Sí"},
    ],
}


class TestCrearResponse:

    @patch("app.api.routes.responses.supabase_service.create_response", return_value=RESPONSE_GUARDADA)
    def test_response_valida_retorna_201(self, _mock_create):
        response = client.post("/api/v1/responses/", json=PAYLOAD_VALIDO)
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 99
        assert data["survey_id"] == 10
        assert len(data["answers"]) == 3

    def test_response_sin_answers_retorna_422(self):
        response = client.post("/api/v1/responses/", json={"survey_id": 10, "answers": []})
        assert response.status_code == 422

    def test_answer_con_texto_vacio_retorna_422(self):
        response = client.post(
            "/api/v1/responses/",
            json={"survey_id": 10, "answers": [{"question_id": 1, "answer_text": "   "}]},
        )
        assert response.status_code == 422

    @patch(
        "app.api.routes.responses.supabase_service.create_response",
        side_effect=LookupError("La encuesta indicada no existe."),
    )
    def test_encuesta_inexistente_retorna_404(self, _mock_create):
        response = client.post("/api/v1/responses/", json=PAYLOAD_VALIDO)
        assert response.status_code == 404

    @patch(
        "app.api.routes.responses.supabase_service.create_response",
        side_effect=ValueError("La encuesta no está activa para recibir respuestas."),
    )
    def test_encuesta_no_activa_retorna_409(self, _mock_create):
        response = client.post("/api/v1/responses/", json=PAYLOAD_VALIDO)
        assert response.status_code == 409

    @patch(
        "app.api.routes.responses.supabase_service.create_response",
        side_effect=RuntimeError("Error al guardar la respuesta en la base de datos."),
    )
    def test_error_de_base_de_datos_retorna_500(self, _mock_create):
        response = client.post("/api/v1/responses/", json=PAYLOAD_VALIDO)
        assert response.status_code == 500


class TestServicioCrearResponse:
    """Prueba la lógica del servicio con un cliente de Supabase simulado."""

    def _fake_supabase(self, *, survey, response_row, answers_rows):
        fake = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "surveys":
                tbl.select.return_value.eq.return_value.execute.return_value.data = (
                    [survey] if survey else []
                )
            elif name == "responses":
                tbl.insert.return_value.execute.return_value.data = (
                    [response_row] if response_row else []
                )
            elif name == "answers":
                tbl.insert.return_value.execute.return_value.data = answers_rows
            return tbl

        fake.table.side_effect = table
        return fake

    def test_create_response_persiste_y_retorna_answers(self):
        from app.schemas.response import ResponseCreate
        from app.services import supabase_service

        payload = ResponseCreate(**PAYLOAD_VALIDO)
        fake = self._fake_supabase(
            survey={"id": 10, "status": "active"},
            response_row={"id": 99, "survey_id": 10, "submitted_at": "2025-01-01T00:00:00"},
            answers_rows=RESPONSE_GUARDADA["answers"],
        )

        with patch.object(supabase_service, "supabase", fake):
            result = supabase_service.create_response(payload)

        assert result["id"] == 99
        assert len(result["answers"]) == 3

    def test_create_response_encuesta_no_activa_lanza_value_error(self):
        import pytest
        from app.schemas.response import ResponseCreate
        from app.services import supabase_service

        payload = ResponseCreate(**PAYLOAD_VALIDO)
        fake = self._fake_supabase(
            survey={"id": 10, "status": "draft"},
            response_row=None,
            answers_rows=[],
        )

        with patch.object(supabase_service, "supabase", fake):
            with pytest.raises(ValueError):
                supabase_service.create_response(payload)
