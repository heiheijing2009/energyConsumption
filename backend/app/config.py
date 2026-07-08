from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"
RUNS_DIR = STORAGE_DIR / "runs"
UPLOADS_DIR = STORAGE_DIR / "uploads"
STATIC_DIR = Path(__file__).resolve().parent / "static"
DB_PATH = DATA_DIR / "app.db"

APP_SECRET = os.getenv("APP_SECRET", "change-this-secret-before-production")
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "12"))

DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123456")

for path in (DATA_DIR, STORAGE_DIR, RUNS_DIR, UPLOADS_DIR):
    path.mkdir(parents=True, exist_ok=True)
