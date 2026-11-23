from fastapi import APIRouter, Request

from api.exception_handlers import error_response

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live():
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request):
    if not request.app.state.store.ready():
        return error_response(request, 503, "NOT_READY", "The database is unavailable.")
    return {"status": "ready"}
