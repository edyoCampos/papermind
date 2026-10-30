"""App FastAPI do PaperMind."""
import logging
import time

from fastapi import FastAPI, Request

from app.api.errors import register_handlers
from app.api.routes import router
from app.core.config import get_settings

logging.basicConfig(level=get_settings().log_level)
log = logging.getLogger("papermind.api")

app = FastAPI(title="PaperMind")
register_handlers(app)
app.include_router(router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    log.info("%s %s -> %d (%.0f ms)", request.method, request.url.path, response.status_code,
             (time.time() - t0) * 1000)
    return response
