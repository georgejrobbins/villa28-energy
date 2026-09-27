from datetime import datetime
from urllib.parse import quote
import requests
from app.config import get_settings
from app.google.auth import GoogleOAuthFlow
from app.utils.retry import retry_with_backoff

class SDMClient:
    BASE_URL = "https://smartdevicemanagement.googleapis.com/v1"

    @staticmethod
    @retry_with_backoff()
    def list_devices():
        project = quote(get_settings().device_access_project_id, safe="")
        url = f"{SDMClient.BASE_URL}/enterprises/{project}/devices"
        response = requests.get(url, headers={"Authorization": f"Bearer {GoogleOAuthFlow.access_token()}"}, timeout=20)
        if response.status_code == 401:
            response = requests.get(url, headers={"Authorization": f"Bearer {GoogleOAuthFlow.access_token(force_refresh=True)}"}, timeout=20)
        response.raise_for_status()
        return [d for d in response.json().get("devices", []) if d.get("type") == "sdm.devices.types.THERMOSTAT"]

    @staticmethod
    def parse_thermostat_reading(device):
        traits = device.get("traits", {})
        def trait(name): return traits.get("sdm.devices.traits." + name, {})
        mode = trait("ThermostatMode").get("mode", "UNKNOWN")
        eco = trait("ThermostatEco")
        setpoint = trait("ThermostatTemperatureSetpoint")
        heat, cool = setpoint.get("heatCelsius"), setpoint.get("coolCelsius")
        if eco.get("mode") == "MANUAL_ECO":
            heat, cool = eco.get("heatCelsius"), eco.get("coolCelsius")
        target = heat if mode == "HEAT" else cool if mode == "COOL" else None
        relations = device.get("parentRelations", [])
        name = trait("Info").get("customName") or next((p.get("displayName") for p in relations if p.get("displayName")), None) or "Nest thermostat"
        return {"device_id": device["name"].split("/")[-1], "device_name": name,
                "ambient_temperature": trait("Temperature").get("ambientTemperatureCelsius"),
                "humidity": trait("Humidity").get("ambientHumidityPercent"),
                "target_temperature": target, "target_heat_temperature": heat, "target_cool_temperature": cool,
                "hvac_status": trait("ThermostatHvac").get("status", "UNKNOWN"), "mode": mode,
                "eco_mode": eco.get("mode") == "MANUAL_ECO", "eco_state": eco.get("mode", "UNKNOWN"),
                "connectivity": trait("Connectivity").get("status", "UNKNOWN"),
                "timestamp": datetime.utcnow(), "source": "poll"}
