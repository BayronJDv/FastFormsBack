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
        self.WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "whisper-1")
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