"""
US-17 — Tolerancia a bases sin la migracion `answers.is_voice` aplicada.

Si la columna no existe (postgres 42703), tanto el insert de respuestas como
la consulta de resultados deben reintentar sin esa columna y comportarse
como antes de US-17, en vez de romper toda la app con un 500.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

_mock_supabase = MagicMock()
sys.modules.setdefault(
    "supabase", MagicMock(create_client=lambda url, key: _mock_supabase)
)

# Cargar app.main establece el sys.path para que `from core.config` funcione.
import app.main  # noqa: F401
from app.services import supabase_service


class _MissingColumnError(Exception):
    """Simula el APIError que devuelve postgrest cuando la columna falta."""

    def __str__(self):
        return (
            "{'message': 'column answers.is_voice does not exist', 'code': '42703'}"
        )


@pytest.fixture(autouse=True)
def _reset_cache():
    """Resetea el cache de feature detection antes de cada test."""
    supabase_service._answers_has_is_voice = None
    yield
    supabase_service._answers_has_is_voice = None


class TestDeteccionColumnaFaltante:
    def test_missing_column_reconoce_42703(self):
        exc = _MissingColumnError()
        assert supabase_service._missing_column(exc, "is_voice") is True

    def test_missing_column_no_confunde_otros_errores(self):
        assert (
            supabase_service._missing_column(RuntimeError("network"), "is_voice")
            is False
        )


class TestCreateResponseSinColumna:
    """`create_response` reintenta sin `is_voice` cuando la columna no existe."""

    def _payload(self):
        from app.schemas.response import ResponseCreate

        return ResponseCreate(
            survey_id=10,
            answers=[
                {"question_id": 1, "answer_text": "Mi respuesta", "is_voice": True}
            ],
        )

    def _fake_supabase(self):
        fake = MagicMock()
        answers_inserts = []

        def table(name):
            tbl = MagicMock()
            if name == "surveys":
                tbl.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": 10, "status": "active"}
                ]
            elif name == "responses":
                tbl.insert.return_value.execute.return_value.data = [
                    {"id": 99, "survey_id": 10, "submitted_at": "2025-01-01T00:00:00"}
                ]
                tbl.delete.return_value.eq.return_value.execute.return_value = MagicMock()
            elif name == "answers":
                def insert(rows):
                    answers_inserts.append(rows)
                    insert_result = MagicMock()
                    # Primer intento: contiene is_voice -> falla.
                    if any("is_voice" in row for row in rows):
                        insert_result.execute.side_effect = _MissingColumnError()
                    else:
                        insert_result.execute.return_value.data = [
                            {
                                "id": 1,
                                "response_id": 99,
                                "question_id": 1,
                                "answer_text": "Mi respuesta",
                            }
                        ]
                    return insert_result

                tbl.insert.side_effect = insert
            return tbl

        fake.table.side_effect = table
        return fake, answers_inserts

    def test_reintenta_sin_is_voice_y_cachea_feature_flag(self):
        fake, inserts = self._fake_supabase()

        with patch.object(supabase_service, "supabase", fake):
            result = supabase_service.create_response(self._payload())

        # 1) Devuelve la respuesta sin romper.
        assert result["id"] == 99
        # 2) El primer intento incluyo is_voice, el segundo no.
        assert any("is_voice" in row for row in inserts[0])
        assert all("is_voice" not in row for row in inserts[1])
        # 3) Se cachea el flag para que siguientes inserts ya no lo intenten.
        assert supabase_service._answers_has_is_voice is False


class TestGetSurveyResultsSinColumna:
    """`get_survey_results` reintenta el SELECT sin `is_voice` cuando falta."""

    def _fake_supabase(self):
        fake = MagicMock()
        selects_seen = []

        def table(name):
            tbl = MagicMock()
            if name == "questions":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
                    {
                        "id": 1,
                        "content": "Comentarios",
                        "question_type": "open",
                        "options": None,
                    }
                ]
            elif name == "responses":
                tbl.select.return_value.eq.return_value.execute.return_value.data = [
                    {"id": 50}
                ]
            elif name == "answers":
                def select(columns):
                    selects_seen.append(columns)
                    select_result = MagicMock()
                    if "is_voice" in columns:
                        select_result.in_.return_value.execute.side_effect = (
                            _MissingColumnError()
                        )
                    else:
                        select_result.in_.return_value.execute.return_value.data = [
                            {"question_id": 1, "answer_text": "Excelente servicio"}
                        ]
                    return select_result

                tbl.select.side_effect = select
            return tbl

        fake.table.side_effect = table
        return fake, selects_seen

    def test_devuelve_resultados_con_is_voice_false_por_defecto(self):
        fake, selects = self._fake_supabase()
        survey = {"id": 7, "title": "T", "status": "active"}

        with patch.object(supabase_service, "supabase", fake):
            result = supabase_service.get_survey_results(survey)

        # El primer SELECT pide is_voice; el segundo ya no.
        assert "is_voice" in selects[0]
        assert "is_voice" not in selects[1]
        # La respuesta es valida y el text_entry queda con is_voice=False.
        open_q = result["questions"][0]
        assert open_q["texts"] == ["Excelente servicio"]
        assert open_q["text_entries"] == [
            {"text": "Excelente servicio", "is_voice": False}
        ]
