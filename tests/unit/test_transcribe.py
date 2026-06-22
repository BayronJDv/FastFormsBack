"""US-12 — Tests del endpoint POST /api/v1/transcribe."""

import io
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_mock_supabase = MagicMock()
sys.modules.setdefault(
    "supabase", MagicMock(create_client=lambda url, key: _mock_supabase)
)

from app.main import app
from app.api.routes import transcribe as transcribe_route

whisper_service = transcribe_route.whisper_service

client = TestClient(app)


def _auth_headers():
    return {"Authorization": "Bearer test-token"}


def _patch_user():
    """Bypass del guard de JWT para tests unitarios."""
    return patch(
        "app.api.deps.get_current_user_id",
        return_value="user-123",
    )


@pytest.fixture
def _override_auth():
    from app.api import deps

    app.dependency_overrides[deps.get_current_user_id] = lambda: "user-123"
    yield
    app.dependency_overrides.pop(deps.get_current_user_id, None)


@pytest.mark.usefixtures("_override_auth")
class TestTranscribeEndpoint:
    def test_happy_path_devuelve_200(self):
        fake_result = {
            "text": "Hola mundo",
            "language": "es",
            "confidence": 0.95,
            "segments": [{"start": 0.0, "end": 1.2, "text": "Hola mundo"}],
        }
        with patch(
            "app.api.routes.transcribe.whisper_service.transcribe_audio",
            return_value=fake_result,
        ):
            response = client.post(
                "/api/v1/transcribe/",
                files={"audio": ("clip.webm", b"\x00\x01\x02", "audio/webm")},
                headers=_auth_headers(),
            )
        assert response.status_code == 200
        body = response.json()
        assert body["text"] == "Hola mundo"
        assert body["language"] == "es"
        assert body["confidence"] == 0.95
        assert body["segments"][0]["text"] == "Hola mundo"

    def test_formato_invalido_retorna_400(self):
        with patch(
            "app.api.routes.transcribe.whisper_service.transcribe_audio",
            side_effect=whisper_service.TranscriptionFormatError(
                "Formato de audio no soportado."
            ),
        ):
            response = client.post(
                "/api/v1/transcribe/",
                files={"audio": ("clip.txt", b"texto", "text/plain")},
                headers=_auth_headers(),
            )
        assert response.status_code == 400

    def test_audio_muy_grande_retorna_413(self):
        with patch(
            "app.api.routes.transcribe.whisper_service.transcribe_audio",
            side_effect=whisper_service.TranscriptionSizeError(
                "El audio excede el limite."
            ),
        ):
            response = client.post(
                "/api/v1/transcribe/",
                files={"audio": ("clip.webm", b"\x00", "audio/webm")},
                headers=_auth_headers(),
            )
        assert response.status_code == 413

    def test_fallo_del_proveedor_retorna_502(self):
        with patch(
            "app.api.routes.transcribe.whisper_service.transcribe_audio",
            side_effect=whisper_service.TranscriptionProviderError("proveedor caido"),
        ):
            response = client.post(
                "/api/v1/transcribe/",
                files={"audio": ("clip.webm", b"\x00", "audio/webm")},
                headers=_auth_headers(),
            )
        assert response.status_code == 502

    def test_modelo_no_cargado_retorna_503(self):
        with patch(
            "app.api.routes.transcribe.whisper_service.transcribe_audio",
            side_effect=whisper_service.ModelNotLoadedError("modelo no cargado"),
        ):
            response = client.post(
                "/api/v1/transcribe/",
                files={"audio": ("clip.webm", b"\x00", "audio/webm")},
                headers=_auth_headers(),
            )
        assert response.status_code == 503

    def test_normalize_code_devuelve_codigo(self):
        """US-19 — con normalize=code el endpoint devuelve normalized_code."""
        fake_result = {
            "text": "a siete equis nueve ka",
            "language": "es",
            "confidence": 0.8,
            "segments": [],
        }
        with patch(
            "app.api.routes.transcribe.whisper_service.transcribe_audio",
            return_value=fake_result,
        ):
            response = client.post(
                "/api/v1/transcribe/",
                files={"audio": ("clip.webm", b"\x00", "audio/webm")},
                data={"normalize": "code"},
                headers=_auth_headers(),
            )
        assert response.status_code == 200
        assert response.json()["normalized_code"] == "A7X9K"


class TestSinAutenticacion:
    """US-14 — Los encuestados anonimos tambien pueden transcribir audio."""

    def test_sin_jwt_es_aceptado(self):
        # Limpiamos cualquier override que otros tests hayan dejado activo.
        app.dependency_overrides.clear()
        with patch(
            "app.api.routes.transcribe.whisper_service.transcribe_audio",
            return_value={"text": "hola", "language": "es", "confidence": 0.9, "segments": []},
        ):
            response = client.post(
                "/api/v1/transcribe/",
                files={"audio": ("clip.webm", b"\x00", "audio/webm")},
            )
        assert response.status_code == 200
        assert response.json()["text"] == "hola"


class TestValidacionAudio:
    """Tests directos sobre `validate_audio`."""

    def test_audio_vacio_lanza_format_error(self):
        with pytest.raises(whisper_service.TranscriptionFormatError):
            whisper_service.validate_audio("clip.webm", "audio/webm", b"")

    def test_audio_grande_lanza_size_error(self):
        big = b"\x00" * (whisper_service.MAX_BYTES + 1)
        with pytest.raises(whisper_service.TranscriptionSizeError):
            whisper_service.validate_audio("clip.webm", "audio/webm", big)

    def test_extension_no_soportada_lanza_format_error(self):
        with pytest.raises(whisper_service.TranscriptionFormatError):
            whisper_service.validate_audio("clip.txt", "text/plain", b"\x00\x01")

    def test_formato_valido_no_lanza(self):
        whisper_service.validate_audio("clip.webm", "audio/webm", b"\x00\x01")
        whisper_service.validate_audio("clip.mp3", "audio/mpeg", b"\x00\x01")
        whisper_service.validate_audio("clip.wav", "audio/wav", b"\x00\x01")


class TestSeleccionDeProveedor:
    """`transcribe_audio` despacha al proveedor configurado en settings."""

    def test_provider_local_es_el_default(self):
        expected = {"text": "local", "language": "es", "confidence": 0.8, "segments": []}
        with patch.object(
            whisper_service.settings, "WHISPER_PROVIDER", "local"
        ), patch.object(
            whisper_service, "_transcribe_local", return_value=expected
        ) as mock_local, patch.object(
            whisper_service, "_transcribe_openai"
        ) as mock_openai:
            result = whisper_service.transcribe_audio(
                "clip.webm", "audio/webm", b"\x00\x01", language="es"
            )

        assert result == expected
        mock_local.assert_called_once()
        mock_openai.assert_not_called()

    def test_provider_openai_usa_la_api(self):
        expected = {"text": "api", "language": "es", "confidence": 0.9, "segments": []}
        with patch.object(
            whisper_service.settings, "WHISPER_PROVIDER", "openai"
        ), patch.object(
            whisper_service, "_transcribe_openai", return_value=expected
        ) as mock_openai, patch.object(
            whisper_service, "_transcribe_local"
        ) as mock_local:
            result = whisper_service.transcribe_audio(
                "clip.webm", "audio/webm", b"\x00\x01", language="es"
            )

        assert result == expected
        mock_openai.assert_called_once()
        mock_local.assert_not_called()

    def test_auto_language_se_traduce_a_none(self):
        """US-18 — language='auto' detecta el idioma (pasa None a Whisper)."""
        captured = {}

        def fake_local(filename, data, language, task):
            captured["language"] = language
            captured["task"] = task
            return {"text": "", "language": "fr", "confidence": None, "segments": []}

        with patch.object(
            whisper_service.settings, "WHISPER_PROVIDER", "local"
        ), patch.object(whisper_service, "_transcribe_local", side_effect=fake_local):
            whisper_service.transcribe_audio(
                "clip.webm", "audio/webm", b"\x00\x01", language="auto", task="translate"
            )

        assert captured["language"] is None
        assert captured["task"] == "translate"

    def test_local_sin_paquete_lanza_model_not_loaded(self):
        # Forzamos que el modelo no esté cacheado y que el import falle.
        with patch.object(whisper_service, "_local_model", None), patch.dict(
            sys.modules, {"whisper": None}
        ):
            with pytest.raises(whisper_service.ModelNotLoadedError):
                whisper_service._get_local_model()

    def test_local_transcribe_decodifica_y_usa_el_modelo(self):
        fake_model = MagicMock()
        fake_model.transcribe.return_value = {
            "text": "  hola mundo ",
            "language": "es",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "hola mundo", "avg_logprob": -0.1},
                {"start": 1.0, "end": 2.0, "text": "", "avg_logprob": -0.3},
            ],
        }
        with patch.object(
            whisper_service, "_get_local_model", return_value=fake_model
        ), patch.object(
            whisper_service, "_load_audio", return_value=[0.0, 0.1, 0.2]
        ) as mock_load:
            result = whisper_service._transcribe_local(
                "clip.webm", b"\x00\x01", "es"
            )

        assert result["text"] == "hola mundo"
        assert result["language"] == "es"
        assert result["confidence"] is not None and 0 < result["confidence"] <= 1
        assert result["segments"][0] == {"start": 0.0, "end": 1.0, "text": "hola mundo"}
        mock_load.assert_called_once()
        # Whisper recibe el arreglo decodificado, no la ruta del archivo.
        args, kwargs = fake_model.transcribe.call_args
        assert args[0] == [0.0, 0.1, 0.2]
        assert kwargs["language"] == "es"
        assert kwargs["task"] == "transcribe"

    def test_load_audio_sin_ffmpeg_mensaje_claro(self):
        """FileNotFoundError del subprocess de ffmpeg da un mensaje accionable."""
        with patch.object(
            whisper_service, "_ffmpeg_exe", return_value="ffmpeg"
        ), patch(
            "app.services.whisper_service.subprocess.run",
            side_effect=FileNotFoundError(2, "not found", "ffmpeg"),
        ):
            with pytest.raises(whisper_service.TranscriptionProviderError) as exc_info:
                whisper_service._load_audio("clip.webm")

        assert "ffmpeg" in str(exc_info.value).lower()
        assert "imageio-ffmpeg" in str(exc_info.value)

    def test_ffmpeg_exe_prefiere_el_binario_empaquetado(self):
        fake_module = MagicMock(get_ffmpeg_exe=lambda: "/bundled/ffmpeg-v4.2.2")
        with patch.dict(sys.modules, {"imageio_ffmpeg": fake_module}):
            assert whisper_service._ffmpeg_exe() == "/bundled/ffmpeg-v4.2.2"

    def test_ffmpeg_exe_cae_al_sistema_si_no_hay_imageio(self):
        with patch.dict(sys.modules, {"imageio_ffmpeg": None}):
            assert whisper_service._ffmpeg_exe() == "ffmpeg"
