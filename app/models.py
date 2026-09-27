from sqlalchemy import Column, String, Float, DateTime, Integer, Boolean, Text, Index
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime

class ThermostatReading(Base):
    __tablename__ = "thermostat_readings"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    device_name = Column(String)
    ambient_temperature = Column(Float, nullable=True)
    target_temperature = Column(Float, nullable=True)
    target_heat_temperature = Column(Float, nullable=True)
    target_cool_temperature = Column(Float, nullable=True)
    eco_state = Column(String, nullable=True)
    source = Column(String, default="poll")
    humidity = Column(Float, nullable=True)
    hvac_status = Column(String)  # "HEATING", "COOLING", "OFF"
    mode = Column(String)  # "HEAT", "COOL", "HEATCOOL", "OFF"
    eco_mode = Column(Boolean, default=False)
    connectivity = Column(String)  # "ONLINE", "OFFLINE"
    timestamp = Column(DateTime, default=func.now(), index=True)

    __table_args__ = (
        Index('idx_device_timestamp', 'device_id', 'timestamp'),
    )

class ThermostatEvent(Base):
    __tablename__ = "thermostat_events"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    event_type = Column(String)  # "temperature_change", "mode_change", "connectivity_change"
    old_value = Column(String, nullable=True)
    new_value = Column(String)
    timestamp = Column(DateTime, default=func.now(), index=True)
    provider_event_id = Column(String, nullable=True, unique=True)
    payload = Column(Text, nullable=True)
    pubsub_message_id = Column(String, nullable=True, unique=True)  # For deduplication

class SolarReading(Base):
    __tablename__ = "solar_readings"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, nullable=True)
    installation_id = Column(String, index=True)
    available_generation = Column(Float, nullable=True)
    instantaneous_power = Column(Float, nullable=True)
    daily_generation = Column(Float, nullable=True)
    grid_import_power = Column(Float, nullable=True)
    grid_export_power = Column(Float, nullable=True)
    battery_power = Column(Float, nullable=True)
    battery_soc = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=func.now(), index=True)

    __table_args__ = (
        Index('idx_installation_timestamp', 'installation_id', 'timestamp'),
    )

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, index=True)  # "google" or "sungrow"
    user_id = Column(String)
    access_token = Column(Text)
    refresh_token = Column(Text, nullable=True)  # Encrypted
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class OAuthState(Base):
    __tablename__ = "oauth_states"
    state_hash = Column(String(64), primary_key=True)
    expires_at = Column(DateTime, nullable=False)
