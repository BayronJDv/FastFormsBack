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
# Proveedor: "local" (openai/whisper, por defecto, sin API key) u "openai".
WHISPER_PROVIDER=local
WHISPER_LOCAL_MODEL=base                 # tiny/base/small/medium/large/turbo
WHISPER_DEFAULT_LANGUAGE=es              # opcional
WHISPER_WARMUP=true                      # pre-carga el modelo en el arranque

# Solo si WHISPER_PROVIDER=openai:
# OPENAI_API_KEY=<tu-api-key-de-openai>
# WHISPER_MODEL=whisper-1
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

El backlog de voz se apoya en **Whisper**. El servicio está encapsulado en
`app/services/whisper_service.py` y expuesto a través de
`POST /api/v1/transcribe/`. Soporta dos proveedores, seleccionables con la
variable `WHISPER_PROVIDER`:

| `WHISPER_PROVIDER` | Qué usa | Requisitos |
| --- | --- | --- |
| `local` (por defecto) | Paquete open-source [`openai/whisper`](https://github.com/openai/whisper). Corre el modelo en la propia máquina. | `pip install -r requirements.txt` (incluye `openai-whisper` + `imageio-ffmpeg` con el binario empaquetado). **Sin API key ni cuota.** |
| `openai` | API hospedada de OpenAI (`whisper-1`). | `OPENAI_API_KEY` con saldo disponible. |

> ¿Te salió un error `429 insufficient_quota`? Es de billing de OpenAI, no del
> código. Con `WHISPER_PROVIDER=local` (el valor por defecto) la transcripción
> corre en tu máquina sin costo ni cuota.

### Requisitos del proveedor local (recomendado)

1. `pip install -r requirements.txt` instala `openai-whisper` (arrastra
   `torch`) y `imageio-ffmpeg`, que trae el binario de `ffmpeg` empaquetado.
   **No necesitas instalar `ffmpeg` en el sistema** — el servicio decodifica
   el audio invocando ese binario por su ruta absoluta y le entrega a Whisper
   el arreglo de audio ya decodificado (evita el `WinError 2` de Windows,
   donde el binario empaquetado no se llama literalmente `ffmpeg`).
2. Si preferís usar el `ffmpeg` del sistema (o lo necesitás para otras
   tareas), también funciona:
   - Debian/Ubuntu: `sudo apt install ffmpeg`
   - macOS: `brew install ffmpeg`
   - Windows: `choco install ffmpeg` o descarga oficial y agregar al `PATH`.
3. La primera transcripción descarga los pesos del modelo
   (`WHISPER_LOCAL_MODEL`, por defecto `base` ≈ 140 MB) y los cachea en
   `~/.cache/whisper`.
4. Tabla `answers` con las columnas `is_voice` (US-17) y `language` (US-18).
   Ver `base.sql` y las migraciones idempotentes que incluye. El backend
   tolera bases sin estas columnas (reintenta sin ellas), pero el feature
   solo queda completo tras aplicarlas.

Tamaños de modelo disponibles (mayor = más preciso y más lento):
`tiny`, `base`, `small`, `medium`, `large`, `turbo`. Para español, `small`
o `medium` dan buen balance si la máquina lo permite.

El modelo se **pre-carga en el arranque** (warm-up en un hilo). Se puede
desactivar con `WHISPER_WARMUP=false` para arrancar más rápido y cargarlo
de forma perezosa en el primer `/transcribe`.

### Cómo consumir el endpoint

`POST /api/v1/transcribe/` — `multipart/form-data` con:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `audio` | archivo | webm / mp3 / wav, ≤ 60 s, ≤ 10 MB |
| `language` | string (opcional) | ISO 639-1 (`es`), `auto` para detectar (US-18), o vacío |
| `task` | string (opcional) | `transcribe` (def.) o `translate` → inglés (US-18) |
| `normalize` | string (opcional) | `code` para normalizar a código de encuesta (US-19) |

Respuesta (`200 OK`):

```json
{
  "text": "Hola mundo",
  "language": "es",
  "confidence": 0.95,
  "segments": [{ "start": 0.0, "end": 1.2, "text": "Hola mundo" }],
  "normalized_code": null
}
```

Errores: `400` (formato), `413` (excede 10 MB), `401` (sin JWT — opcional),
`502` (fallo del proveedor) y `503` (modelo local no cargado).

Ejemplos con `curl`:

```bash
# Transcripción simple (es)
curl -X POST http://localhost:8000/api/v1/transcribe/ \
  -F "audio=@clip.webm" -F "language=es"

# Detección automática de idioma (US-18)
curl -X POST http://localhost:8000/api/v1/transcribe/ \
  -F "audio=@clip.webm" -F "language=auto"

# Código de encuesta por voz (US-19)
curl -X POST http://localhost:8000/api/v1/transcribe/ \
  -F "audio=@clip.webm" -F "normalize=code"
```

### Multilingüe (US-18)

`language=auto` deja que Whisper detecte el idioma del audio sin
configuración previa; el idioma detectado vuelve en `language` y se persiste
en `answers.language` para etiquetarlo en el dashboard. `task=translate` usa
el modo de traducción de Whisper para devolver el texto en inglés (útil para
unificar el análisis de respuestas multilingües).

> El paso opcional "LLM → español" descrito en el backlog queda como
> follow-up: este stack no tiene un proveedor LLM configurado. La capacidad
> de traducción de Whisper (`task=translate`) sí está disponible.

### Código por voz (US-19)

Con `normalize=code`, el backend pasa la transcripción por
`services/voice_code.normalize_spoken_code`, que convierte números y letras
dictados a una cadena `[A-Z0-9]` ("a siete equis nueve ka" → `A7X9K`,
"A-7-X-9-K" → `A7X9K`). El frontend muestra el código interpretado para
confirmar antes de validar.

### Modelo y umbral de confianza

Whisper no expone una probabilidad por respuesta, pero sí `avg_logprob`
por segmento (tanto el modelo local como la API en `verbose_json`). El
servicio promedia esos valores y devuelve un score en `[0, 1]`. El frontend
lo usa como umbral para la selección por voz (US-15) antes de marcar una
opción automáticamente.
