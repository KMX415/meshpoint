from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from src.api.auth.dependencies import require_admin
from .settings import Settings

router = APIRouter(prefix="/api/p25", tags=["p25"], dependencies=[Depends(require_admin)])
_listener = None


def init_routes(listener):
    global _listener
    _listener = listener


def reset_routes():
    global _listener
    _listener = None


def listener():
    if _listener is None:
        raise HTTPException(503, "P25 is not initialized")
    return _listener


@router.get("/status")
async def status():
    return listener().status()


@router.post("/start")
async def start(settings: Settings):
    try:
        await listener().start(settings)
    except ValueError as error:
        raise HTTPException(422, str(error))
    except (RuntimeError, OSError) as error:
        raise HTTPException(503, str(error))
    return listener().status()


@router.post("/stop")
async def stop():
    await listener().stop()
    return listener().status()


@router.get("/stream")
async def stream():
    receiver = listener()
    if not receiver.running:
        raise HTTPException(409, "Start P25 before playing audio")
    queue = receiver.subscribe()
    async def chunks():
        try:
            while data := await queue.get():
                yield data
        finally:
            receiver.unsubscribe(queue)
    return StreamingResponse(chunks(), media_type="audio/mpeg", headers={"Cache-Control":"no-store", "X-Accel-Buffering":"no"})
