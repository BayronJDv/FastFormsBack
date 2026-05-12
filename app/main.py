import sys
from pathlib import Path

# Asegurar que el directorio app/ esté en el path de Python
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import surveys, questions
 
app = FastAPI(
    title="FastForms API",
    description="Backend para la creación y distribución de encuestas.",
    version="0.2.0",
)

# ---------------------------------------------------------------
# CORS — ajusta los orígenes cuando tengas el dominio del front
# ---------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # TODO: agregar dominio de producción
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


# ---------------------------------------------------------------
# Health check
# ---------------------------------------------------------------
@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": "FastForms API"}
