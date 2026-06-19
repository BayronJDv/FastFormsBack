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

# US-12 — Servicio de transcripción (Whisper)
OPENAI_API_KEY=<tu-api-key-de-openai>
WHISPER_MODEL=whisper-1                  # opcional
WHISPER_DEFAULT_LANGUAGE=es              # opcional
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
| `POST` | `/api/v1/transcribe/` | Transcribe un audio corto con Whisper (US-12). |

> Mientras Auth (US-01) no esté integrado, el `creator_id` se toma del header
> `x-creator-id`.

## Voz con Whisper (US-12 a US-17)

El backlog de voz se apoya en la API de **Whisper** de OpenAI. El servicio
está encapsulado en `app/services/whisper_service.py` y expuesto a través de
`POST /api/v1/transcribe/`.

### Requisitos

1. Cuenta de OpenAI con acceso a la API de audio.
2. Variable `OPENAI_API_KEY` configurada en el `.env`.
3. Tabla `answers` con la columna `is_voice` (ver `base.sql` y la migración
   idempotente que incluye, necesaria para US-17).

### Cómo consumir el endpoint

`POST /api/v1/transcribe/` — `multipart/form-data` con:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `audio` | archivo | webm / mp3 / wav, ≤ 60 s, ≤ 10 MB |
| `language` | string (opcional) | ISO 639-1, por defecto `es` |

Respuesta (`200 OK`):

```json
{ "text": "Hola mundo", "language": "es", "confidence": 0.95 }
```

Errores: `400` (formato), `413` (excede 10 MB), `401` (sin JWT) y `502`
(fallo del proveedor).

Ejemplo con `curl`:

```bash
curl -X POST http://localhost:8000/api/v1/transcribe/ \
  -H "Authorization: Bearer <token>" \
  -F "audio=@clip.webm" \
  -F "language=es"
```

### Modelo y umbral de confianza

`whisper-1` no expone una probabilidad por respuesta, pero sí `avg_logprob`
por segmento. El servicio promedia esos valores y devuelve un score en
`[0, 1]`. El frontend lo usa como umbral para la selección por voz
(US-15) antes de marcar una opción automáticamente.
