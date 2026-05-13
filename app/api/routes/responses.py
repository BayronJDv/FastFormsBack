from fastapi import APIRouter, HTTPException, status

from schemas.response import ResponseCreate, ResponseResult
from services import supabase_service

router = APIRouter(prefix="/responses", tags=["Responses"])


@router.post(
    "/",
    response_model=ResponseResult,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar las respuestas de un encuestado",
)
def create_response(payload: ResponseCreate):
    """
    US-08 — Persiste una respuesta (tabla `responses`) junto con sus `answers`.

    - 404 si la encuesta no existe.
    - 409 si la encuesta no está activa para recibir respuestas.
    """
    try:
        return supabase_service.create_response(payload)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
