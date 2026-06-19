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


class TestSeleccionDeProveedor:
    """`transcribe_audio` despacha al proveedor configurado en settings."""

    def test_provider_local_es_el_default(self):
        with patch.object(
            whisper_service.settings, "WHISPER_PROVIDER", "local"
        ), patch.object(
            whisper_service, "_transcribe_local", return_value=("local", "es", 0.8)
        ) as mock_local, patch.object(
            whisper_service, "_transcribe_openai"
        ) as mock_openai:
            text, lang, conf = whisper_service.transcribe_audio(
                "clip.webm", "audio/webm", b"\x00\x01", language="es"
            )

        assert (text, lang, conf) == ("local", "es", 0.8)
        mock_local.assert_called_once()
        mock_openai.assert_not_called()

    def test_provider_openai_usa_la_api(self):
        with patch.object(
            whisper_service.settings, "WHISPER_PROVIDER", "openai"
        ), patch.object(
            whisper_service, "_transcribe_openai", return_value=("api", "es", 0.9)
        ) as mock_openai, patch.object(
            whisper_service, "_transcribe_local"
        ) as mock_local:
            result = whisper_service.transcribe_audio(
                "clip.webm", "audio/webm", b"\x00\x01", language="es"
            )

        assert result == ("api", "es", 0.9)
        mock_openai.assert_called_once()
        mock_local.assert_not_called()

    def test_local_sin_paquete_lanza_provider_error(self):
        # Forzamos que el modelo no esté cacheado y que el import falle.
        with patch.object(whisper_service, "_local_model", None), patch.dict(
            sys.modules, {"whisper": None}
        ):
            with pytest.raises(whisper_service.TranscriptionProviderError):
                whisper_service._get_local_model()

    def test_local_transcribe_usa_el_modelo_cacheado(self):
        fake_model = MagicMock()
        fake_model.transcribe.return_value = {
            "text": "  hola mundo ",
            "language": "es",
            "segments": [{"avg_logprob": -0.1}, {"avg_logprob": -0.3}],
        }
        with patch.object(whisper_service, "_get_local_model", return_value=fake_model):
            text, lang, conf = whisper_service._transcribe_local(
                "clip.webm", b"\x00\x01", "es"
            )

        assert text == "hola mundo"
        assert lang == "es"
        assert conf is not None and 0 < conf <= 1
        fake_model.transcribe.assert_called_once()

    def test_ffmpeg_no_encontrado_mensaje_claro(self):
        """FileNotFoundError de ffmpeg se traduce a un mensaje accionable."""
        fake_model = MagicMock()
        fake_model.transcribe.side_effect = FileNotFoundError(
            2, "The system cannot find the file specified", "ffmpeg"
        )
        with patch.object(whisper_service, "_get_local_model", return_value=fake_model):
            with pytest.raises(whisper_service.TranscriptionProviderError) as exc_info:
                whisper_service._transcribe_local("clip.webm", b"\x00\x01", "es")

        assert "ffmpeg" in str(exc_info.value).lower()
        assert "imageio-ffmpeg" in str(exc_info.value)

    def test_ensure_ffmpeg_prepend_al_path(self, tmp_path):
        """`_ensure_ffmpeg_on_path` agrega el dir del binario al PATH del proceso."""
        fake_dir = str(tmp_path)
        fake_exe = str(tmp_path / "ffmpeg.exe")
        fake_module = MagicMock(get_ffmpeg_exe=lambda: fake_exe)

        original_path = os.environ.get("PATH", "")
        with patch.dict(sys.modules, {"imageio_ffmpeg": fake_module}), patch.object(
            whisper_service, "_ffmpeg_path_ready", False
        ):
            try:
                whisper_service._ensure_ffmpeg_on_path()
                assert fake_dir in os.environ["PATH"].split(os.pathsep)
            finally:
                os.environ["PATH"] = original_path
                whisper_service._ffmpeg_path_ready = False
