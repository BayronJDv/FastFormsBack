import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Fast Forms API"
    
    # Intentamos leer las variables
    URL: str = os.getenv("SUPABASE_URL")
    KEY: str = os.getenv("SUPABASE_KEY")

    def __init__(self):
        # Validación crítica: Si no existen, el servidor no debe ni arrancar
        if not self.URL or not self.KEY:
            raise RuntimeError(
                "❌ ERROR: No se encontraron SUPABASE_URL o SUPABASE_KEY en el .env. "
                "Revisa el archivo .env o las variables de entorno."
            )

settings = Settings()

# Inicialización global del cliente
supabase: Client = create_client(settings.URL, settings.KEY)