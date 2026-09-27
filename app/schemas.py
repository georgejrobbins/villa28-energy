from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ThermostatReadingSchema(BaseModel):
    device_id: str
    device_name: str
    ambient_temperature: Optional[float] = None
    target_temperature: Optional[float] = None
    humidity: Optional[float] = None
    hvac_status: str
    mode: str
    eco_mode: bool
    connectivity: str
    timestamp: datetime

class SolarReadingSchema(BaseModel):
    installation_id: str
    instantaneous_power: Optional[float] = None
    daily_generation: Optional[float] = None
    grid_import_power: Optional[float] = None
    grid_export_power: Optional[float] = None
    battery_soc: Optional[float] = None
    timestamp: datetime

class CurrentStateSchema(BaseModel):
    thermostats: list[ThermostatReadingSchema]
    solar: list[SolarReadingSchema]
