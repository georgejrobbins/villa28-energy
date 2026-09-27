from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.database import engine

router = APIRouter()

@router.get("/health")
def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "disconnected"})
