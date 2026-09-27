"""Read-only OAuth V2 endpoints verified in the official Developer Portal."""
import math
from app.sungrow.auth import SungrowOAuthFlow, SungrowError, post
from app.utils.retry import retry_with_backoff

# Plant points: W for power, Wh for daily yield. Missing measurements remain null.
POINTS = ["83033", "83022", "83129", "83102", "83072", "83238"]

class SungrowAPIClient:
    @staticmethod
    @retry_with_backoff()
    def read(path, payload):
        if path not in {"/openapi/platform/queryPowerStationList", "/openapi/platform/getPowerStationRealTimeData"}:
            raise ValueError("Unsupported read-only endpoint")
        return post(path, {"lang": "_en_US", **payload}, SungrowOAuthFlow.access_token())

    @staticmethod
    def get_installations():
        plants = []
        for page in range(1, 101):
            data = SungrowAPIClient.read("/openapi/platform/queryPowerStationList", {"page": page, "size": 10})
            rows = data.get("pageList")
            if not isinstance(rows, list):
                raise SungrowError("Unexpected plant list schema")
            plants.extend(rows)
            if len(rows) < 10 or len(plants) >= int(data.get("row_count", 100000)):
                return plants
        raise SungrowError("Plant pagination limit exceeded")

    @staticmethod
    def get_readings():
        plants = SungrowAPIClient.get_installations()
        readings = []
        for plant in plants:
            plant_id = str(plant["ps_id"])
            data = SungrowAPIClient.read("/openapi/platform/getPowerStationRealTimeData", {
                "ps_id_list": [plant_id], "point_id_list": POINTS,
                "is_get_point_dict": "1", "is_get_revenue": "0"})
            rows = data.get("device_point_list")
            if not isinstance(rows, list) or data.get("fail_ps_id_list"):
                raise SungrowError("Plant telemetry unavailable")
            for row in rows:
                if str(row.get("ps_id")) == plant_id:
                    readings.append(SungrowAPIClient.parse_reading(row))
        return readings

    @staticmethod
    def parse_reading(row):
        def number(key, divisor=1):
            try:
                value = float(row[key]) / divisor
                return value if math.isfinite(value) else None
            except (KeyError, TypeError, ValueError):
                return None
        return {"installation_id": str(row["ps_id"]),
                "installation_name": row.get("ps_name"),
                "provider_time": row.get("device_time"),
                "grid_import_daily": number("p83102", 1000),
                "grid_export_daily": number("p83072", 1000),
                "battery_power": number("p83238"),
                "instantaneous_power": number("p83033"),
                "daily_generation": number("p83022", 1000),
                "battery_soc": number("p83129")}
