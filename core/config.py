import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    DB_PATH: str = os.getenv("DB_PATH", "./secure_records.db")
    SERVICE_HOST: str = os.getenv("SERVICE_HOST", "0.0.0.0")
    SERVICE_PORT: int = int(os.getenv("SERVICE_PORT", "8000"))

settings = Settings()