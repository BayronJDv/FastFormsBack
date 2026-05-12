"""
Dependencias y guards reutilizables de la capa de API.

`assert_survey_in_status` centraliza la regla de inmutabilidad (US-04): una
encuesta solo puede modificarse mientras esté en alguno de los estados
permitidos. Por defecto el único estado editable es ``draft``, pero la función
recibe ``allowed_statuses`` para poder reutilizarse con otros estados futuros.
"""

from typing import Iterable, Optional

from fastapi import HTTPException, status

# Estados en los que una encuesta (y sus preguntas) puede editarse.
EDITABLE_STATUSES = ("draft",)


def assert_survey_in_status(
    survey: Optional[dict],
    allowed_statuses: Iterable[str] = EDITABLE_STATUSES,
) -> dict:
    """
    Valida que la encuesta exista y esté en uno de los estados permitidos.

    - 404 si la encuesta no existe.
    - 403 si la encuesta está en un estado distinto a los permitidos
      (p. ej. ya fue publicada).
    """
    allowed = tuple(allowed_statuses)

    if survey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Encuesta no encontrada.",
        )

    if survey.get("status") not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Operación no permitida: la encuesta está en estado "
                f"'{survey.get('status')}'. Solo se permite cuando está en: "
                f"{', '.join(allowed)}."
            ),
        )

    return survey
