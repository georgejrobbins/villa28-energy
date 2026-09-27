import asyncio
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from app.config import get_settings
from app.database import SessionLocal
from app.models import ThermostatEvent, ThermostatReading

logger = logging.getLogger(__name__)
status = {"state": "configuration_required", "last_event": None}

def process_event(data, message_id):
    update = data.get("resourceUpdate", {})
    name = update.get("name", "")
    if "/devices/" not in name:
        return False
    traits = update.get("traits", {})
    # Ignore camera/doorbell events and non-thermostat devices.
    with SessionLocal.begin() as db:
        previous = db.scalar(select(ThermostatReading).where(ThermostatReading.device_id == name.split("/")[-1]).order_by(ThermostatReading.timestamp.desc(), ThermostatReading.id.desc()).limit(1))
        if previous is None and not any("Thermostat" in key for key in traits):
            return False
        event_id = data.get("eventId")
        duplicate = db.scalar(select(ThermostatEvent.id).where(or_(ThermostatEvent.pubsub_message_id == message_id, ThermostatEvent.provider_event_id == event_id if event_id else False)))
        if duplicate:
            return False
        stamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        db.add(ThermostatEvent(device_id=name.split("/")[-1], event_type="traits_changed",
            new_value=",".join(key.rsplit(".", 1)[-1] for key in traits)[:255],
            timestamp=stamp, pubsub_message_id=message_id, provider_event_id=event_id,
            payload=json.dumps(update, separators=(",", ":"))))
        # Preserve event ordering. A late partial event cannot safely replace a newer snapshot.
        # Initial readings come from a full SDM poll so partial events never fabricate state.
        if previous and stamp >= previous.timestamp:
            values = {col.name: getattr(previous, col.name) for col in ThermostatReading.__table__.columns if col.name != "id"}
            mapping = {"Temperature": {"ambientTemperatureCelsius": "ambient_temperature"},
                       "Humidity": {"ambientHumidityPercent": "humidity"},
                       "ThermostatHvac": {"status": "hvac_status"},
                       "ThermostatMode": {"mode": "mode"},
                       "Connectivity": {"status": "connectivity"},
                       "Info": {"customName": "device_name"},
                       "ThermostatTemperatureSetpoint": {"heatCelsius": "target_heat_temperature", "coolCelsius": "target_cool_temperature"},
                       "ThermostatEco": {"mode": "eco_state"}}
            for suffix, fields in mapping.items():
                for field, dest in fields.items():
                    change = traits.get("sdm.devices.traits." + suffix, {})
                    if field in change: values[dest] = change[field]
            values["eco_mode"] = values["eco_state"] == "MANUAL_ECO"
            if "sdm.devices.traits.ThermostatEco" in traits or "sdm.devices.traits.ThermostatMode" in traits:
                # Mode switches can invalidate a setpoint not supplied by the partial event.
                setpoint = traits.get("sdm.devices.traits.ThermostatEco" if values["eco_mode"] else "sdm.devices.traits.ThermostatTemperatureSetpoint", {})
                values["target_heat_temperature"] = setpoint.get("heatCelsius")
                values["target_cool_temperature"] = setpoint.get("coolCelsius")
            values["target_temperature"] = values["target_heat_temperature"] if values["mode"] == "HEAT" else values["target_cool_temperature"] if values["mode"] == "COOL" else None
            values.update(timestamp=stamp, source="event")
            db.add(ThermostatReading(**values))
    status["last_event"] = datetime.utcnow().isoformat() + "Z"
    return True

def message_callback(message):
    try:
        process_event(json.loads(message.data), message.message_id)
        message.ack()
    except IntegrityError:
        # Unique constraints provide race-safe deduplication across deliveries.
        with SessionLocal() as db:
            data = json.loads(message.data)
            found = db.scalar(select(ThermostatEvent.id).where(or_(ThermostatEvent.pubsub_message_id == message.message_id, ThermostatEvent.provider_event_id == data.get("eventId") if data.get("eventId") else False)))
        message.ack() if found else message.nack()
    except Exception as exc:
        logger.error("Pub/Sub event processing failed (%s)", type(exc).__name__)
        message.nack()

async def run_subscriber():
    settings = get_settings()
    if not settings.google_pubsub_subscription or not settings.google_service_account_json:
        status["state"] = "configuration_required"
        return
    delay = 5
    while True:
        subscriber = future = None
        try:
            credentials = service_account.Credentials.from_service_account_info(json.loads(settings.google_service_account_json))
            subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
            future = subscriber.subscribe(settings.google_pubsub_subscription, callback=message_callback,
                flow_control=pubsub_v1.types.FlowControl(max_messages=10), await_callbacks_on_shutdown=True)
            status["state"] = "listening"
            await asyncio.to_thread(future.result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            status["state"] = "error"
            logger.error("Pub/Sub connection failed (%s); reconnecting", type(exc).__name__)
        finally:
            if future:
                future.cancel()
                try:
                    await asyncio.to_thread(future.result, timeout=10)
                except Exception:
                    pass
            if subscriber: subscriber.close()
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60)
