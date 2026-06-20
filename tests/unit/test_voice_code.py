"""US-19 — Tests de normalización de código de encuesta dictado por voz."""

import sys
from unittest.mock import MagicMock

_mock_supabase = MagicMock()
sys.modules.setdefault(
    "supabase", MagicMock(create_client=lambda url, key: _mock_supabase)
)

import app.main  # noqa: F401  (configura sys.path)
from app.services.voice_code import normalize_spoken_code


class TestNormalizeSpokenCode:
    def test_codigo_ya_pegado(self):
        assert normalize_spoken_code("A7X9K") == "A7X9K"

    def test_codigo_pegado_en_minusculas(self):
        assert normalize_spoken_code("a7x9k") == "A7X9K"

    def test_numeros_en_palabras(self):
        assert normalize_spoken_code("siete") == "7"
        assert normalize_spoken_code("a siete b dos") == "A7B2"

    def test_letras_deletreadas_en_espanol(self):
        assert normalize_spoken_code("a siete equis nueve ka") == "A7X9K"

    def test_separadores_y_puntuacion(self):
        assert normalize_spoken_code("A-7-X-9-K") == "A7X9K"
        assert normalize_spoken_code("A 7 X 9 K") == "A7X9K"
        assert normalize_spoken_code("a, siete. x; nueve k") == "A7X9K"

    def test_acentos_y_mayusculas(self):
        assert normalize_spoken_code("é 7") == "E7"

    def test_frase_doble_u(self):
        assert normalize_spoken_code("doble u 3") == "W3"

    def test_i_griega(self):
        assert normalize_spoken_code("i griega 5") == "Y5"

    def test_texto_vacio(self):
        assert normalize_spoken_code("") == ""
        assert normalize_spoken_code("   ") == ""

    def test_mezcla_palabras_y_digitos(self):
        # "be" -> B, "ocho" -> 8, "2" -> 2, "ene" -> N
        assert normalize_spoken_code("be ocho 2 ene") == "B82N"
