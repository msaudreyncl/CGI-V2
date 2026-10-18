"""
config.py — Application settings loaded from .env
"""

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    # App
    APP_ENV:   str   = os.getenv("APP_ENV", "development")
    APP_HOST:  str   = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT:  int   = int(os.getenv("APP_PORT", "8000"))
    APP_DEBUG: bool  = os.getenv("APP_DEBUG", "true").lower() == "true"

    # Database
    DB_HOST:     str = os.getenv("DB_HOST", "localhost")
    DB_PORT:     int = int(os.getenv("DB_PORT", "3306"))
    DB_NAME:     str = os.getenv("DB_NAME", "cgi_db")
    DB_USER:     str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )

    @staticmethod
    def _project_path(value: str) -> str:
        path = Path(value)
        return str(path if path.is_absolute() else PROJECT_ROOT / path)

    # JWT
    JWT_SECRET:         str = os.getenv("JWT_SECRET", "CHANGE_ME")
    JWT_ALGORITHM:      str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

    # YOLOv8
    YOLO_MODEL_PATH:  str   = _project_path(os.getenv("YOLO_MODEL_PATH", "models/cgi_yolov8.pt"))
    YOLO_CONFIDENCE:  float = float(os.getenv("YOLO_CONFIDENCE", "0.50"))

    # File storage
    UPLOAD_DIR: str = _project_path(os.getenv("UPLOAD_DIR", "backend/static/uploads"))

    # Pricing API
    PRICE_API_URL:            str   = os.getenv("PRICE_API_URL", "")
    PRICE_API_KEY:            str   = os.getenv("PRICE_API_KEY", "")
    PRICE_API_SYMBOL:         str   = os.getenv("PRICE_API_SYMBOL", "COFFEE")
    PRICE_BASE_CURRENCY:      str   = os.getenv("PRICE_BASE_CURRENCY", "PHP")
    PRICE_CACHE_TTL_SECONDS:  int   = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "3600"))
    PRICE_FALLBACK_PHP_PER_KG: float = float(os.getenv("PRICE_FALLBACK_PHP_PER_KG", "300.00"))

    # Pi node HTTP server (pi_server.py)
    PI_NODE_URL: str = os.getenv("PI_NODE_URL", "http://localhost:5000")

    # Thermal printer
    THERMAL_PRINTER_TYPE: str = os.getenv("THERMAL_PRINTER_TYPE", "network")
    THERMAL_PRINTER_HOST: str = os.getenv("THERMAL_PRINTER_HOST", "192.168.1.100")
    THERMAL_PRINTER_PORT: int = int(os.getenv("THERMAL_PRINTER_PORT", "9100"))
    THERMAL_PRINTER_USB_VID: str = os.getenv("THERMAL_PRINTER_USB_VID", "0x04b8")
    THERMAL_PRINTER_USB_PID: str = os.getenv("THERMAL_PRINTER_USB_PID", "0x0202")

    # CORS
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost,http://localhost:8080,http://127.0.0.1,http://127.0.0.1:8080").split(",")
        if o.strip()
    ]

    # Weight enforcement
    WEIGHT_MIN_G: float = 340.0
    WEIGHT_MAX_G: float = 360.0


@lru_cache()
def get_settings() -> Settings:
    return Settings()
