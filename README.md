# FastForms — Backend

API REST de **FastForms**, una plataforma de encuestas rápidas. Construida con
**FastAPI** y **Supabase** (Postgres + Auth).

## Stack

- Python 3.11+
- FastAPI + Uvicorn
- Supabase (cliente `supabase-py`)
- Pydantic v2 para validación
- Pytest + httpx para tests

## Estructura

```
app/
  main.py              # Punto de entrada, CORS y registro de routers
  core/config.py       # Configuración y cliente global de Supabase
  api/
    deps.py            # Guards reutilizables (p. ej. inmutabilidad de encuestas)
    routes/
      surveys.py       # Crear, listar y publicar encuestas
      questions.py      # Agregar / editar preguntas (bloqueado si está publicada)
      responses.py      # Registrar respuestas de los encuestados
  schemas/             # Modelos Pydantic (survey, question, response)
  services/
    supabase_service.py # Acceso a datos sobre Supabase
tests/
  unit/                # Tests con Supabase simulado
  integration/         # Tests contra una instancia real de Supabase
```

## Configuración

Crea un archivo `.env` en la raíz del repo:

```
SUPABASE_URL=https://<tu-proyecto>.supabase.co
SUPABASE_KEY=<tu-anon-o-service-key>
```

## Ejecutar en local

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

La API queda en `http://localhost:8000` y la documentación interactiva en
`http://localhost:8000/docs`.

## Tests

```bash
# Solo unitarios (no requieren credenciales)
pytest tests/unit -v

# Integración (requiere .env con credenciales válidas de Supabase)
pytest tests/integration -v
```

## Endpoints principales

| Método | Ruta | Descripción |
| --- | --- | --- |
| `POST` | `/api/v1/surveys/` | Crea una encuesta con sus preguntas (estado `draft`). |
| `GET` | `/api/v1/surveys/` | Lista las encuestas del usuario autenticado y su estado. |
| `PATCH` | `/api/v1/surveys/{id}/publish` | Publica la encuesta (`draft` → `active`). |
| `POST` | `/api/v1/surveys/{id}/questions/` | Agrega una pregunta (403 si la encuesta está publicada). |
| `PUT` / `PATCH` | `/api/v1/surveys/{id}/questions/{qid}` | Edita una pregunta (403 si la encuesta está publicada). |
| `POST` | `/api/v1/responses/` | Registra las respuestas de un encuestado. |

> Mientras Auth (US-01) no esté integrado, el `creator_id` se toma del header
> `x-creator-id`.
