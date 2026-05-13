"""
Tests US-04 — Publicación e inmutabilidad.

Verifican que:
  - No se pueden agregar/editar preguntas de una encuesta publicada (403).
  - El endpoint de publicación valida estado y propiedad.
"""

import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

# Mock de Supabase antes de importar la app (solo para tests unitarios)
_mock_supabase = MagicMock()
sys.modules.setdefault("supabase", MagicMock(create_client=lambda url, key: _mock_supabase))

from app.main import app

client = TestClient(app)

_OWNER_ID = "832071cb-5f6a-4d2d-8c0c-901cd13e78ad"
QUESTION_UPDATE = {"content": "Pregunta editada"}
NEW_QUESTION = {
    "content": "Nueva pregunta",
    "question_type": "open",
    "options": None,
    "position": 1,
}

PUBLISHED_SURVEY = {"id": 1, "status": "active", "creator_id": _OWNER_ID}
DRAFT_SURVEY = {"id": 1, "status": "draft", "creator_id": _OWNER_ID}


class TestInmutabilidadPreguntas:

    @patch("app.api.routes.questions.supabase_service.get_survey", return_value=PUBLISHED_SURVEY)
    def test_editar_pregunta_de_encuesta_publicada_retorna_403(self, _mock_get):
        response = client.put("/api/v1/surveys/1/questions/5", json=QUESTION_UPDATE)
        assert response.status_code == 403
        assert "no permitida" in response.json()["detail"].lower()

    @patch("app.api.routes.questions.supabase_service.get_survey", return_value=PUBLISHED_SURVEY)
    def test_patch_pregunta_de_encuesta_publicada_retorna_403(self, _mock_get):
        response = client.patch("/api/v1/surveys/1/questions/5", json=QUESTION_UPDATE)
        assert response.status_code == 403

    @patch("app.api.routes.questions.supabase_service.get_survey", return_value=PUBLISHED_SURVEY)
    def test_agregar_pregunta_a_encuesta_publicada_retorna_403(self, _mock_get):
        response = client.post("/api/v1/surveys/1/questions/", json=NEW_QUESTION)
        assert response.status_code == 403

    @patch("app.api.routes.questions.supabase_service.get_survey", return_value=None)
    def test_editar_pregunta_de_encuesta_inexistente_retorna_404(self, _mock_get):
        response = client.put("/api/v1/surveys/999/questions/5", json=QUESTION_UPDATE)
        assert response.status_code == 404

    @patch("app.api.routes.questions.supabase.table")
    @patch("app.api.routes.questions.supabase_service.get_survey", return_value=DRAFT_SURVEY)
    def test_editar_pregunta_de_encuesta_borrador_funciona(self, _mock_get, mock_table):
        edited = {
            "id": 5,
            "survey_id": 1,
            "content": "Pregunta editada",
            "question_type": "open",
            "options": None,
            "position": 1,
        }
        (
            mock_table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data
        ) = [edited]

        response = client.put("/api/v1/surveys/1/questions/5", json=QUESTION_UPDATE)
        assert response.status_code == 200
        assert response.json()["content"] == "Pregunta editada"


class TestPublicacionEncuesta:

    @patch("app.api.routes.surveys.supabase_service.get_survey", return_value=None)
    def test_publicar_encuesta_inexistente_retorna_404(self, _mock_get):
        response = client.patch("/api/v1/surveys/999/publish")
        assert response.status_code == 404

    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "status": "active", "creator_id": _OWNER_ID},
    )
    def test_publicar_encuesta_ya_publicada_retorna_409(self, _mock_get):
        response = client.patch("/api/v1/surveys/1/publish")
        assert response.status_code == 409

    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "status": "draft", "creator_id": "otro-usuario"},
    )
    def test_publicar_encuesta_ajena_retorna_403(self, _mock_get):
        response = client.patch("/api/v1/surveys/1/publish")
        assert response.status_code == 403

    @patch("app.api.routes.surveys.supabase_service.set_survey_status")
    @patch(
        "app.api.routes.surveys.supabase_service.get_survey",
        return_value={"id": 1, "status": "draft", "creator_id": _OWNER_ID},
    )
    def test_publicar_encuesta_borrador_retorna_200(self, _mock_get, mock_set_status):
        mock_set_status.return_value = {
            "id": 1,
            "creator_id": _OWNER_ID,
            "title": "Encuesta",
            "status": "active",
            "unique_code": "ABCDE",
            "created_at": "2025-01-01T00:00:00",
            "closed_at": None,
        }
        response = client.patch("/api/v1/surveys/1/publish")
        assert response.status_code == 200
        assert response.json()["status"] == "active"
        mock_set_status.assert_called_once_with(1, "active")
