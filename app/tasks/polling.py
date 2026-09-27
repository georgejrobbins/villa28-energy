import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from app.config import get_settings
from app.database import SessionLocal
from app.models import OAuthToken, ThermostatReading, SolarReading
from app.google.sdm_client import SDMClient
from app.utils.crypto import encryption_ready

logger = logging.getLogger(__name__)
status = {"state": "waiting", "last_success": None, "device_count": 0}

def poll_once():
    settings = get_settings()
    if not settings.google_configured or not encryption_ready():
        status["state"] = "configuration_required"
        return
    with SessionLocal() as db:
        connected = db.scalar(select(OAuthToken.id).where(OAuthToken.provider == "google"))
    if not connected:
        status["state"] = "connection_required"
        return
    devices = SDMClient.list_devices()
    with SessionLocal.begin() as db:
        db.add_all(ThermostatReading(**SDMClient.parse_thermostat_reading(d)) for d in devices)
    status.update(state="connected", last_success=datetime.utcnow().isoformat() + "Z", device_count=len(devices))
    logger.info("Nest polling completed: %s thermostats", len(devices))

solar_status = {"state": "waiting", "last_success": None, "installation_count": 0}

def poll_sungrow_once():
    from app.sungrow.api_client import SungrowAPIClient
    if not get_settings().sungrow_configured or not encryption_ready():
        solar_status["state"] = "configuration_required"
        return
    with SessionLocal() as db:
        connected = db.scalar(select(OAuthToken.id).where(OAuthToken.provider == "sungrow"))
    if not connected:
        solar_status["state"] = "connection_required"
        return
    rows = SungrowAPIClient.get_readings()
    with SessionLocal.begin() as db:
        db.add_all(SolarReading(**row) for row in rows)
    solar_status.update(state="connected", last_success=datetime.utcnow().isoformat() + "Z", installation_count=len(rows))
    logger.info("Sungrow polling completed: %s installations", len(rows))

async def provider_loop(poll, provider_status, name, minimum):
    while True:
        try:
            await asyncio.to_thread(poll)
        except Exception as exc:
            provider_status["state"] = "error"
            logger.error("%s polling failed (%s); retrying at next interval", name, type(exc).__name__)
        await asyncio.sleep(max(minimum, get_settings().polling_interval_seconds))

async def start_polling():
    await asyncio.gather(provider_loop(poll_once, status, "Nest", 30),
                         provider_loop(poll_sungrow_once, solar_status, "Sungrow", 300))
