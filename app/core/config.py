import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Fast Forms API"

    def __init__(self):
        self.URL: str = os.getenv("SUPABASE_URL", "")
        self.KEY: str = os.getenv("SUPABASE_KEY", "")
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        # Proveedor de transcripcion: "local" (openai/whisper, sin costo ni
        # cuota) u "openai" (API hospedada). Por defecto usamos el local.
        self.WHISPER_PROVIDER: str = os.getenv("WHISPER_PROVIDER", "local").lower()
        # Modelo de la API hospedada (provider="openai").
        self.WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "whisper-1")
        # Modelo del paquete local openai-whisper (tiny/base/small/medium/large/turbo).
        self.WHISPER_LOCAL_MODEL: str = os.getenv("WHISPER_LOCAL_MODEL", "base")
        self.WHISPER_DEFAULT_LANGUAGE: str = os.getenv("WHISPER_DEFAULT_LANGUAGE", "es")

        if not self.URL or not self.KEY:
            raise RuntimeError(
                "❌ ERROR: No se encontraron SUPABASE_URL o SUPABASE_KEY en el .env. "
                "Revisa el archivo .env o las variables de entorno."
            )

        if not self.URL.startswith("https://"):
            raise RuntimeError(
                "❌ ERROR: SUPABASE_URL debe comenzar con 'https://'. "
                f"Valor actual: '{self.URL}'"
            )

settings = Settings()

# Inicialización global del cliente
supabase: Client = create_client(settings.URL, settings.KEY)