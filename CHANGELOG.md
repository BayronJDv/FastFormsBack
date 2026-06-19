# Changelog

## Sprint 4 — Voz (Whisper)

### Whisper local (openai/whisper) como proveedor por defecto
- `whisper_service.py` ahora soporta dos proveedores vía `WHISPER_PROVIDER`:
  - `local` (**por defecto**): paquete open-source
    [`openai-whisper`](https://github.com/openai/whisper), corre el modelo en la
    propia máquina. Sin API key, sin cuota, sin billing.
  - `openai`: API hospedada (`whisper-1`), requiere `OPENAI_API_KEY` con saldo.
- `imageio-ffmpeg` agregado al `requirements.txt`: trae un binario de `ffmpeg`
  empaquetado como dependencia Python, así no es necesario instalar `ffmpeg`
  en el sistema.
- El proveedor local ahora **decodifica el audio él mismo** (`_load_audio`)
  invocando ffmpeg por su **ruta absoluta** y le pasa a Whisper un arreglo
  numpy ya decodificado, en lugar de dejar que `openai-whisper` invoque
  `ffmpeg` por nombre. Esto resuelve el
  `WinError 2 — The system cannot find the file specified` en Windows, donde
  el binario de `imageio-ffmpeg` tiene un nombre versionado
  (p. ej. `ffmpeg-win64-v4.2.2.exe`) y no se resolvía vía PATH. Si no hay
  `imageio-ffmpeg`, cae al `ffmpeg` del sistema.
- Mensaje de error específico cuando `ffmpeg` no se encuentra o falla al
  decodificar.
- Motivación: la API hospedada devuelve `429 insufficient_quota` si la cuenta
  de OpenAI no tiene saldo. El proveedor local evita esa dependencia.
- Nuevas variables `WHISPER_PROVIDER` y `WHISPER_LOCAL_MODEL` (default `base`).
- El modelo local se carga una sola vez (cache en memoria); el audio se vuelca
  a un temporal para que `ffmpeg` lo decodifique.
- Mensaje de error específico cuando la API hospedada responde 429.
- Dependencia `openai-whisper>=20231117` agregada a `requirements.txt`.
- Tests de selección de proveedor y de la ruta local en
  `tests/unit/test_transcribe.py`.

### US-12 · Infra: Servicio de Transcripción (Whisper)
- Nuevo endpoint `POST /api/v1/transcribe/` que recibe un archivo de audio
  multipart (`audio`) y un parámetro opcional `language` (por defecto `es`).
  Devuelve `{text, language, confidence}`.
- Validaciones: formato webm/mp3/wav, tamaño ≤ 10 MB. Errores HTTP estándar:
  400 (formato), 413 (tamaño), 401 (sin JWT), 502 (fallo del proveedor).
- Nueva configuración `OPENAI_API_KEY` / `WHISPER_MODEL` / `WHISPER_DEFAULT_LANGUAGE`
  en `app/core/config.py`.
- Nuevo servicio `app/services/whisper_service.py` (validación + cliente OpenAI).
- Nuevo schema `TranscribeResponse`.
- Dependencia `openai>=1.40.0` agregada a `requirements.txt`.
- Tests `tests/unit/test_transcribe.py`: happy path, formato inválido (400),
  audio grande (413), sin JWT (401), fallo del proveedor (502).

### US-17 · Resultados: Respuestas por Voz
- Campo `is_voice` (bool, default false) en `AnswerCreate` / `AnswerResult` y
  en el `INSERT` sobre la tabla `answers`. Permite distinguir respuestas
  dictadas en el dashboard.
- Migración SQL acompañante en `FastFormsFront/base.sql` (idempotente).

## Sprint 3 — Análisis y Cierre

### US-10 · Resultados: Visualización Core
- Nuevo endpoint `GET /api/v1/surveys/{id}/results` que agrega las respuestas:
  porcentajes por opción para preguntas `multiple_choice` / `yes_no` y lista de
  textos para preguntas `open`. Solo el creador autenticado puede consultarlo
  (403 en caso contrario, 404 si la encuesta no existe).
- Nuevos schemas `OptionResult` / `QuestionResult` / `SurveyResults`.
- Nuevos servicios `get_survey_results` y `_aggregate_choice` (lógica de
  agregación) en `app/services/supabase_service.py`.
- Tests en `tests/unit/test_results.py` (agregación + endpoint).

### US-09 · Gestión: Confirmación de Cierre
- Nuevo endpoint `PATCH /api/v1/surveys/{id}/close` que cambia el estado a
  `closed` y setea `closed_at` (acción irreversible). Valida que solo el creador
  pueda cerrar su encuesta y que esté actualmente `active`.
- Nuevo servicio `close_survey`.

### US-06 · Acceso: Estado de Encuesta Cerrada
- Sin cambios de backend: la validación de código (US-05) ya devuelve el estado
  de la encuesta. El ajuste de copy vive en el frontend.

### Refactor menor
- `app/api/routes/surveys.py`: helper `_get_owned_survey_or_error` reutilizado
  por los endpoints de publicar / cerrar / resultados.

## Sprint 2 — Publicación y Respuesta

### US-04 · Lógica: Publicación e Inmutabilidad
- Nuevo guard reutilizable `assert_survey_in_status` en `app/api/deps.py` que
  centraliza la regla de inmutabilidad (por defecto solo es editable el estado
  `draft`, parametrizable para estados futuros).
- Nuevo endpoint `PATCH /api/v1/surveys/{survey_id}/publish` que cambia el
  estado de la encuesta a `active` ("Publicada"). Valida propiedad y que la
  encuesta esté en borrador.
- `POST /api/v1/surveys/{survey_id}/questions/` y los nuevos
  `PUT`/`PATCH /api/v1/surveys/{survey_id}/questions/{question_id}` rechazan con
  **403** cualquier modificación si la encuesta ya fue publicada. La protección
  vive en la capa de API.
- Nuevo schema `QuestionUpdate` para ediciones parciales de preguntas.

### US-02 · Panel: Gestión de Estados
- Nuevo endpoint `GET /api/v1/surveys/` que devuelve las encuestas del usuario
  autenticado (header `x-creator-id` hasta que Auth/US-01 esté integrado) con su
  estado actual (`draft` / `active` / `closed`).
- Nuevo servicio `list_surveys_by_creator`.

### US-08 · Recolección: Confirmación de Envío
- Nuevos schemas `ResponseCreate` / `AnswerCreate` / `ResponseResult` en
  `app/schemas/response.py`.
- Nuevo endpoint `POST /api/v1/responses/` que persiste la respuesta y sus
  `answers` de forma atómica (con rollback manual). Devuelve 404 si la encuesta
  no existe y 409 si no está activa.
- Nuevo servicio `create_response`.

### Tests
- `tests/unit/test_immutability.py` — cobertura de inmutabilidad y publicación.
- `tests/unit/test_responses.py` — cobertura del endpoint y del servicio de
  respuestas.
