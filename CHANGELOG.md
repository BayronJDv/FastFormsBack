# Changelog

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
