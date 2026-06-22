import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Asegurar que el directorio app/ esté en el path de Python
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import surveys, questions, responses, transcribe


@asynccontextmanager
async def lifespan(app: FastAPI):
    """US-12 — Warm-up del modelo Whisper local en el arranque.

    Se controla con `WHISPER_WARMUP` (por defecto activado). Se hace en un
    hilo para no bloquear el arranque; si falla, el primer /transcribe
    reportará el 503 si procede.
    """
    if os.getenv("WHISPER_WARMUP", "true").lower() in ("1", "true", "yes"):
        import threading

        from services import whisper_service

        threading.Thread(target=whisper_service.warm_up, daemon=True).start()
    yield


app = FastAPI(
    title="FastForms API",
    description="Backend para la creación y distribución de encuestas.",
    version="0.2.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------
# CORS — ajusta los orígenes cuando tengas el dominio del front
# ---------------------------------------------------------------
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_url.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------
# Routers
# ---------------------------------------------------------------
app.include_router(surveys.router, prefix="/api/v1")
app.include_router(questions.router, prefix="/api/v1")
app.include_router(responses.router, prefix="/api/v1")
app.include_router(transcribe.router, prefix="/api/v1")


# ---------------------------------------------------------------
# Health check
# ---------------------------------------------------------------
@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": "FastForms API"}
