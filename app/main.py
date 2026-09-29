import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.utils.logging import logger
from app.database import init_db
from app.config import get_settings
from app.routes import health, auth, api
from app import home_presence
from app.security import require_owner
from app.tasks.polling import start_polling
from app.google.pubsub_handler import run_subscriber

@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(init_db)
    tasks = []
    if get_settings().background_tasks_enabled:
        tasks = [asyncio.create_task(start_polling()), asyncio.create_task(run_subscriber())]
    logger.info("villa28-energy started; read-only monitoring")
    try:
        yield
    finally:
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

app = FastAPI(title="villa28-energy", version="1.2.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(home_presence.router)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(api.router)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers["X-Frame-Options"] = "DENY"
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response

@app.get("/", dependencies=[Depends(require_owner)])
def root():
    return FileResponse(static_dir / "index.html")
