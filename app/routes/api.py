from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import ThermostatReading, SolarReading, OAuthToken
from app.config import get_settings
from app.security import require_owner
from app.utils.crypto import encryption_ready
from app.tasks.polling import status as polling_status, solar_status
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
        solar_connected = db.scalar(select(OAuthToken.id).where(OAuthToken.provider == "sungrow")) is not None
    return {"google": {"configured": settings.google_configured, "connected": connected,
                        "encryption_ready": encryption_ready(), "polling": dict(polling_status), "pubsub": dict(pubsub_status)},
            "sungrow": {"configured": settings.sungrow_configured, "connected": solar_connected, "encryption_ready": encryption_ready(), "polling": dict(solar_status)},
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

@router.get('/thermostat-timeline')
def thermostat_timeline(day: str | None = None):
    from datetime import timezone
    from zoneinfo import ZoneInfo
    from fastapi import HTTPException
    from app.thermostat_timeline import build_timeline
    local_zone = ZoneInfo('Asia/Dubai')
    now = datetime.now(timezone.utc)
    try:
        selected = datetime.strptime(day, '%Y-%m-%d').date() if day else now.astimezone(local_zone).date()
    except ValueError:
        raise HTTPException(422, 'Use a date in YYYY-MM-DD format')
    local_start = datetime.combine(selected, datetime.min.time(), tzinfo=local_zone)
    start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    end = min((local_start+timedelta(days=1)).astimezone(timezone.utc), now).replace(tzinfo=None)
    if start >= end:
        raise HTTPException(422, 'Choose today or an earlier date')
    tolerance = max(600, get_settings().polling_interval_seconds * 2)
    with SessionLocal() as db:
        devices = latest(db,ThermostatReading,ThermostatReading.device_id)
        result=[]
        for device in devices:
            rows = db.scalars(select(ThermostatReading).where(
                ThermostatReading.device_id == device.device_id,
                ThermostatReading.timestamp >= start-timedelta(seconds=tolerance),
                ThermostatReading.timestamp <= end
            ).order_by(ThermostatReading.timestamp,ThermostatReading.id)).all()
            result.append({'device_id':device.device_id,'device_name':device.device_name,
                           **build_timeline(rows,start,end,tolerance)})
    return {'day':str(selected),'timezone':'Asia/Dubai','start':start.isoformat()+'Z',
            'end':end.isoformat()+'Z','devices':result,'gap_minutes':tolerance/60,
            'polling_seconds':get_settings().polling_interval_seconds,
            'stages_available':False,'occupancy_available':False,'nest_schedule_available':False}

@router.get('/solar-timeline')
def solar_timeline(hours: int = Query(24,ge=1,le=720)):
    from app.solar_history import solar_intervals
    since=datetime.utcnow()-timedelta(hours=hours)
    gap=max(660,get_settings().polling_interval_seconds*2+60)
    result=[]
    with SessionLocal() as db:
        for plant in latest(db,SolarReading,SolarReading.installation_id):
            rows=db.scalars(select(SolarReading).where(SolarReading.installation_id==plant.installation_id,
                SolarReading.timestamp>=since-timedelta(seconds=gap)).order_by(SolarReading.timestamp,SolarReading.id)).all()
            samples=solar_intervals(rows,gap)
            samples=[r for r in samples if r['timestamp']>=since.isoformat()+'Z']
            result.append({'installation_id':plant.installation_id,'name':plant.installation_name,'readings':samples})
    return {'installations':result,'timezone':'Asia/Dubai','note':'Energy is the change between consecutive provider samples, normally about five minutes. Resets and gaps are omitted. This is not a revenue-grade meter.'}

@router.get('/export-history')
def export_history(provider: str = Query(pattern='^(nest|solar)$'),days: int = Query(30,ge=1,le=90)):
    import csv,io
    from fastapi import HTTPException
    from fastapi.responses import Response
    model=ThermostatReading if provider=='nest' else SolarReading
    with SessionLocal() as db:
        rows=db.scalars(select(model).where(model.timestamp>=datetime.utcnow()-timedelta(days=days)).order_by(model.timestamp,model.id).limit(200001)).all()
        if len(rows)>200000:
            raise HTTPException(422,'Too many readings. Choose fewer days.')
        columns=[c.name for c in model.__table__.columns if c.name!='id']
        output=io.StringIO();writer=csv.writer(output);writer.writerow(columns)
        for row in rows:
            values=serialize(row)
            # Treat provider names as text, not spreadsheet formulas.
            writer.writerow([("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for v in (values[k] for k in columns)])
    return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="villa28-{provider}-{days}days.csv"'})
