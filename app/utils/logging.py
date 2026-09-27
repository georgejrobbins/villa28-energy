import logging
import json
from datetime import datetime
from app.config import get_settings

settings = get_settings()

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)

def setup_logging():
    """Configure structured JSON logging"""
    logging.getLogger("uvicorn.access").disabled = True
    logger = logging.getLogger()
    logger.setLevel(settings.log_level)

    # Remove existing handlers
    logger.handlers = []

    handler = logging.StreamHandler()
    formatter = JSONFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

logger = setup_logging()
