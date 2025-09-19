import os

from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv('.env.local')

@dataclass
class Config:
    db_path: str = os.getenv("APP_DB_PATH", "./data/app.db")
    secret_key_path: str = os.getenv("APP_SECRET_KEY_PATH", "./data/secret.key")


cfg = Config()

os.makedirs("./data", exist_ok=True)