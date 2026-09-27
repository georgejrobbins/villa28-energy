import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from app.config import get_settings
from app.database import SessionLocal
from app.models import OAuthToken, ThermostatReading
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

async def start_polling():
    while True:
        try:
            await asyncio.to_thread(poll_once)
        except Exception as exc:
            status["state"] = "error"
            logger.error("Nest polling failed (%s); retrying at next interval", type(exc).__name__)
        await asyncio.sleep(get_settings().polling_interval_seconds)
