"""
Test de integración — US-03
Verifica que el endpoint POST /api/v1/surveys/ guarda realmente en Supabase.

Requisitos:
  - El archivo .env debe tener SUPABASE_URL y SUPABASE_KEY válidos.
  - Supabase debe estar accesible desde la máquina donde se ejecuta el test.

Ejecución:
  pytest tests/test_surveys_integration.py -v
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import supabase

client = TestClient(app)

# UUID válido para tests — coincide con _TEST_CREATOR_ID en el route
TEST_CREATOR_ID = "832071cb-5f6a-4d2d-8c0c-901cd13e78ad"
HEADERS = {"x-creator-id": TEST_CREATOR_ID}

SURVEY_INTEGRACION = {
    "title": "[TEST] Encuesta de integración",
    "questions": [
        {
            "content": "¿Cómo te enteraste de FastForms?",
            "question_type": "open",
            "options": None,
            "position": 1,
        },
        {
            "content": "¿Qué plan usarías?",
            "question_type": "multiple_choice",
            "options": ["Gratuito", "Pro", "Enterprise"],
            "position": 2,
        },
        {
            "content": "¿Recomendarías FastForms?",
            "question_type": "yes_no",
            "options": None,
            "position": 3,
        },
    ],
}


@pytest.fixture(autouse=True)
def limpiar_encuesta_de_prueba():
    """
    Limpia la encuesta creada durante el test para no contaminar la DB.
    Se ejecuta después de cada test automáticamente.
    """
    yield
    # Teardown: eliminar encuestas de prueba por título
    resultado = (
        supabase.table("surveys")
        .select("id")
        .eq("title", "[TEST] Encuesta de integración")
        .execute()
    )
    for survey in resultado.data:
        supabase.table("questions").delete().eq("survey_id", survey["id"]).execute()
        supabase.table("surveys").delete().eq("id", survey["id"]).execute()


class TestIntegracionGuardarEncuesta:

    def test_encuesta_se_guarda_en_supabase_y_retorna_201(self):
        response = client.post("/api/v1/surveys/", json=SURVEY_INTEGRACION, headers=HEADERS)
        assert response.status_code == 201

    def test_encuesta_guardada_tiene_id_real(self):
        response = client.post("/api/v1/surveys/", json=SURVEY_INTEGRACION, headers=HEADERS)
        data = response.json()
        assert "id" in data
        assert isinstance(data["id"], int)
        assert data["id"] > 0

    def test_encuesta_guardada_tiene_codigo_unico_de_5_caracteres(self):
        response = client.post("/api/v1/surveys/", json=SURVEY_INTEGRACION, headers=HEADERS)
        data = response.json()
        assert "unique_code" in data
        assert len(data["unique_code"]) == 5
        assert data["unique_code"].isupper() or data["unique_code"].isalnum()

    def test_encuesta_existe_realmente_en_supabase(self):
        response = client.post("/api/v1/surveys/", json=SURVEY_INTEGRACION, headers=HEADERS)
        data = response.json()
        survey_id = data["id"]

        # Consultar directamente en Supabase
        resultado = (
            supabase.table("surveys").select("*").eq("id", survey_id).execute()
        )
        assert len(resultado.data) == 1
        assert resultado.data[0]["title"] == "[TEST] Encuesta de integración"
        assert resultado.data[0]["status"] == "draft"

    def test_preguntas_existen_en_supabase(self):
        response = client.post("/api/v1/surveys/", json=SURVEY_INTEGRACION, headers=HEADERS)
        data = response.json()
        survey_id = data["id"]

        # Consultar preguntas directamente en Supabase
        resultado = (
            supabase.table("questions")
            .select("*")
            .eq("survey_id", survey_id)
            .execute()
        )
        assert len(resultado.data) == 3

    def test_codigo_unico_no_se_repite_en_dos_encuestas(self):
        response1 = client.post("/api/v1/surveys/", json=SURVEY_INTEGRACION, headers=HEADERS)
        response2 = client.post("/api/v1/surveys/", json=SURVEY_INTEGRACION, headers=HEADERS)
        assert response1.json()["unique_code"] != response2.json()["unique_code"]