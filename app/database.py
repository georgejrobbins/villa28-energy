import hashlib
import logging
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

logger = logging.getLogger(__name__)
url = get_settings().database_url
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+psycopg://", 1)
elif url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
if not url:
    raise RuntimeError("DATABASE_URL must reference the Railway PostgreSQL service")
engine = create_engine(url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

def get_db():
    with SessionLocal() as db:
        yield db

def init_db():
    """Transactional, tracked migrations; serialize simultaneous deployments."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Production migrations require PostgreSQL")
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(280028)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
        for path in sorted((Path(__file__).resolve().parents[1] / "migrations").glob("*.sql")):
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            previous = conn.execute(text("SELECT checksum FROM schema_migrations WHERE name=:name"), {"name": path.name}).scalar()
            if previous:
                if previous != checksum:
                    raise RuntimeError(f"Applied migration was modified: {path.name}")
                continue
            # Files contain plain DDL only; no procedural blocks or semicolons in strings.
            for statement in sql.split(";"):
                if statement.strip():
                    conn.execute(text(statement))
            conn.execute(text("INSERT INTO schema_migrations (name, checksum) VALUES (:name, :checksum)"), {"name": path.name, "checksum": checksum})
            logger.info("Applied migration %s", path.name)
