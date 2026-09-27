"""Provider boundary only. No unverified Sungrow requests are sent."""
REQUIRED_DOCUMENTATION = [
    "Official regional Developer API base URL and API version",
    "OAuth authorization and token endpoints, grant types, scopes and client authentication method",
    "Read-only installation listing endpoint and installation identifier field",
    "Read-only telemetry endpoint, request parameters and response examples",
    "Field names and units for generation, power, grid import/export, battery power and state of charge",
    "API signing requirements, rate limits, timezone and timestamp format",
]

class SungrowAPIClient:
    @staticmethod
    def get_installations():
        raise NotImplementedError("Sungrow is paused pending official Developer API documentation")
