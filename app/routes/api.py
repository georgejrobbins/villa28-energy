from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import ThermostatReading, SolarReading, OAuthToken
from app.config import get_settings
from app.security import require_owner
from app.utils.crypto import encryption_ready
from app.tasks.polling import status as polling_status
from app.google.pubsub_handler import status as pubsub_status

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])

def serialize(row):
    values = {col.name: getattr(row, col.name) for col in row.__table__.columns if col.name != "id"}
    for key, value in values.items():
        if isinstance(value, datetime): values[key] = value.isoformat() + "Z"
    return values

def latest(db, model, key):
    ranked = select(model.id, func.row_number().over(partition_by=key, order_by=(model.timestamp.desc(), model.id.desc())).label("rank")).subquery()
    return db.scalars(select(model).join(ranked, ranked.c.id == model.id).where(ranked.c.rank == 1)).all()

@router.get("/current")
def current():
    with SessionLocal() as db:
        return {"thermostats": [serialize(x) for x in latest(db, ThermostatReading, ThermostatReading.device_id)],
                "solar": [serialize(x) for x in latest(db, SolarReading, SolarReading.installation_id)]}

@router.get("/status")
def integration_status():
    settings = get_settings()
    with SessionLocal() as db:
        connected = db.scalar(select(OAuthToken.id).where(OAuthToken.provider == "google")) is not None
    return {"google": {"configured": settings.google_configured, "connected": connected,
                        "encryption_ready": encryption_ready(), "polling": dict(polling_status), "pubsub": dict(pubsub_status)},
            "sungrow": {"state": "deferred", "message": "Pending official API details"},
            "polling_interval_seconds": settings.polling_interval_seconds}

@router.get("/history")
def history(device_id: str | None = None, installation_id: str | None = None, hours: int = Query(24, ge=1, le=720)):
    since = datetime.utcnow() - timedelta(hours=hours)
    result = {}
    with SessionLocal() as db:
        for model, identifier, value, key in [(ThermostatReading, ThermostatReading.device_id, device_id, "thermostats"), (SolarReading, SolarReading.installation_id, installation_id, "solar")]:
            if value:
                rows = db.scalars(select(model).where(identifier == value, model.timestamp >= since).order_by(model.timestamp.desc(), model.id.desc()).limit(10000)).all()
                result[key] = [serialize(x) for x in reversed(rows)]
                result[key + "_limit_reached"] = len(rows) == 10000
    return result

@router.get("/daily-summary")
def daily_summary(days: int = Query(7, ge=1, le=90)):
    since = datetime.utcnow() - timedelta(days=days)
    # Daily generation is a cumulative counter: use each installation's maximum, then sum installations.
    day = func.date(SolarReading.timestamp).label("day")
    with SessionLocal() as db:
        rows = db.execute(select(day, SolarReading.installation_id,
            func.max(SolarReading.daily_generation).label("generation"),
            func.avg(SolarReading.instantaneous_power).label("avg_power"),
            func.max(SolarReading.grid_export_power).label("max_export")
        ).where(SolarReading.timestamp >= since).group_by(day, SolarReading.installation_id)).all()
    groups = {}
    for row in rows:
        key = str(row.day)
        item = groups.setdefault(key, {"date": key, "total_generation": None, "avg_power": None, "max_grid_export": None, "installations": []})
        item["installations"].append({"installation_id": row.installation_id, "daily_generation": row.generation, "avg_power": row.avg_power, "max_grid_export": row.max_export})
        for field, value in [("total_generation", row.generation), ("avg_power", row.avg_power)]:
            if value is not None: item[field] = (item[field] or 0) + value
        if row.max_export is not None: item["max_grid_export"] = max(item["max_grid_export"] or 0, row.max_export)
    return {"summaries": [groups[k] for k in sorted(groups)], "timezone": "UTC", "note": "Average power is the sum of each installation's sample mean; max export is the largest individual installation sample."}
