"""US-12 — Tests del endpoint POST /api/v1/transcribe."""

import io
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
        fake_result = ("Hola mundo", "es", 0.95)
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


class TestSinAutenticacion:
    """US-14 — Los encuestados anonimos tambien pueden transcribir audio."""

    def test_sin_jwt_es_aceptado(self):
        # Limpiamos cualquier override que otros tests hayan dejado activo.
        app.dependency_overrides.clear()
        with patch(
            "app.api.routes.transcribe.whisper_service.transcribe_audio",
            return_value=("hola", "es", 0.9),
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
